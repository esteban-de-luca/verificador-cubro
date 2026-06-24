"""
sheets_writer.py — Registra cada verificación en un Google Sheet de log.

Hace APPEND de UNA fila por verificación a un Sheet dedicado que ya existe y
que lee otro proyecto (un dashboard). Es independiente de Notion: el registro
en el Sheet se hace al terminar cada verificación, en el mismo punto del flujo
en que antes se escribía en Notion.

Autenticación
-------------
Reutiliza EXACTAMENTE la misma Service Account que el repo usa para Drive
(``drive.cliente.obtener_credenciales``). No se crean credenciales nuevas; el
único requisito es que ``config.DRIVE_SCOPES`` incluya el scope
``https://www.googleapis.com/auth/spreadsheets`` (ya añadido). La Service
Account debe tener acceso de edición al Sheet — lo tiene automáticamente si el
Sheet vive en la misma unidad compartida que las carpetas de Drive.

Contrato con el dashboard (NO cambiar sin coordinar)
----------------------------------------------------
- 14 columnas, en el orden de ``COLUMNAS``.
- ``valueInputOption="RAW"`` (nunca USER_ENTERED): los valores se guardan tal
  cual, sin que Sheets reinterprete fechas/números.
- ``timestamp``: ISO 8601 en UTC, ordenable como texto
  (``datetime.now(timezone.utc).isoformat(timespec="seconds")``).
- ``estado``: minúsculas, uno de bloqueado / advertencias / aprobado.
- ``n_fail`` / ``n_warn`` / ``n_pass``: enteros.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from core.modelos import CheckResult, InformeFinal
from drive.cliente import obtener_credenciales

log = logging.getLogger(__name__)


#: Orden EXACTO de las 14 columnas. El dashboard depende de este orden.
COLUMNAS: list[str] = [
    "timestamp",
    "id_proyecto",
    "estado",
    "responsable",
    "semana_produccion",
    "fecha_analisis",
    "cliente",
    "n_fail",
    "n_warn",
    "n_pass",
    "errores_criticos",
    "advertencias",
    "aspectos_relevantes",
    "link_informe",
]

#: Rango de columnas (A..N = 14 columnas) usado en el append.
_RANGO_COLUMNAS = "A:N"

#: Timeout (s) de cada operación HTTP a la API de Sheets.
_SHEETS_HTTP_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Servicio Sheets — misma Service Account que Drive
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def obtener_servicio_sheets() -> Any:
    """
    Construye (y cachea) el servicio Sheets v4 autenticado con la MISMA
    Service Account que Drive.

    Las verificaciones se registran de forma secuencial (un append por
    verificación, en el hilo principal de Streamlit), por lo que no se
    necesita el lock de serialización que sí usa el cliente de Drive.
    """
    http = AuthorizedHttp(
        obtener_credenciales(),
        http=httplib2.Http(timeout=_SHEETS_HTTP_TIMEOUT),
    )
    return build("sheets", "v4", http=http, cache_discovery=False)


# ---------------------------------------------------------------------------
# Helpers de mapeo InformeFinal -> fila
# ---------------------------------------------------------------------------

def _derivar_estado(n_fail: int, n_warn: int) -> str:
    """bloqueado / advertencias / aprobado (minúsculas) según los conteos.

    Coincide con InformeFinal.estado_global (BLOQUEADO/ADVERTENCIAS/OK) porque
    n_fail = nº de errores críticos y n_warn = nº de advertencias.
    """
    if n_fail > 0:
        return "bloqueado"
    if n_warn > 0:
        return "advertencias"
    return "aprobado"


def _fmt_checks(checks: list[CheckResult]) -> str:
    """Une una lista de checks en una celda multilínea ('\\n')."""
    lineas: list[str] = []
    for c in checks:
        if c.detalle:
            lineas.append(f"{c.id}: {c.desc} — {c.detalle}")
        else:
            lineas.append(f"{c.id}: {c.desc}")
    return "\n".join(lineas)


def _aspectos_relevantes(informe: InformeFinal) -> str:
    """
    Observaciones CNC no reconocidas (C-62 / C-63 en WARN), igual que el campo
    'Notas' que se escribía en Notion. "" si no hay ninguna.
    """
    partes = [
        c.detalle
        for c in informe.checks
        if c.id in ("C-62", "C-63") and c.resultado == "WARN" and c.detalle
    ]
    return "\n".join(partes)


def construir_fila(
    informe: InformeFinal,
    link_informe: str = "",
    ahora: datetime | None = None,
) -> list[Any]:
    """
    Mapea un InformeFinal a la fila de 14 columnas (en el orden de COLUMNAS).

    Args:
        informe:      resultado de la verificación.
        link_informe: enlace al informe en Drive ("" si no hay).
        ahora:        instante a usar para timestamp/fecha (inyectable en tests).
                      Por defecto, datetime.now(timezone.utc).

    Returns:
        Lista de 14 valores: enteros para los conteos, strings para el resto.
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    n_fail = len(informe.errores_criticos)
    n_warn = len(informe.advertencias)
    n_pass = sum(1 for c in informe.checks if c.resultado == "PASS")

    return [
        ahora.isoformat(timespec="seconds"),          # timestamp (ISO 8601, UTC)
        informe.id_proyecto or "",                     # id_proyecto
        _derivar_estado(n_fail, n_warn),               # estado (minúsculas)
        informe.responsable or "",                     # responsable
        informe.semana or "",                          # semana_produccion
        ahora.date().isoformat(),                      # fecha_analisis (YYYY-MM-DD)
        informe.cliente or "",                         # cliente
        n_fail,                                         # n_fail (int)
        n_warn,                                         # n_warn (int)
        n_pass,                                         # n_pass (int)
        _fmt_checks(informe.errores_criticos),         # errores_criticos
        _fmt_checks(informe.advertencias),             # advertencias
        _aspectos_relevantes(informe),                 # aspectos_relevantes
        link_informe or "",                            # link_informe
    ]


# ---------------------------------------------------------------------------
# Append
# ---------------------------------------------------------------------------

def _rango_a1(tab: str) -> str:
    """Rango A1 con la pestaña entrecomillada (escapando comillas simples)."""
    tab_escapado = tab.replace("'", "''")
    return f"'{tab_escapado}'!{_RANGO_COLUMNAS}"


def _es_error_de_rango(exc: HttpError) -> bool:
    """True si el HttpError se debe a que la pestaña/rango no existe."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status != 400:
        return False
    msg = str(exc).lower()
    return "unable to parse range" in msg or "not found" in msg


def _primera_hoja(servicio: Any, sheet_id: str) -> str:
    """Título de la primera hoja del libro (fallback si la pestaña no existe)."""
    meta = servicio.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(title,index))",
    ).execute(num_retries=2)
    hojas = meta.get("sheets", [])
    hojas.sort(key=lambda s: s["properties"].get("index", 0))
    return hojas[0]["properties"]["title"]


def _append(servicio: Any, sheet_id: str, rango: str, fila: list[Any]) -> dict:
    return servicio.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=rango,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [fila]},
    ).execute(num_retries=2)


def append_verificacion(
    informe: InformeFinal,
    link_informe: str = "",
    *,
    servicio: Any | None = None,
    sheet_id: str | None = None,
    tab: str | None = None,
    ahora: datetime | None = None,
) -> dict:
    """
    Añade UNA fila con el resultado de la verificación al Sheet de log.

    Args:
        informe:      resultado de la verificación a registrar.
        link_informe: enlace al informe en Drive ("" si no hay).
        servicio:     servicio Sheets v4 (por defecto, el cacheado).
        sheet_id:     ID del Sheet (por defecto, config.log_verif_sheet_id()).
        tab:          pestaña destino (por defecto, config.log_verif_tab()).
        ahora:        instante para timestamp/fecha (inyectable en tests).

    Returns:
        La respuesta de la API de Sheets (dict con 'updates').

    Si la pestaña configurada no existe, cae automáticamente a la primera hoja
    del libro y reintenta una vez.
    """
    servicio = servicio or obtener_servicio_sheets()
    sheet_id = sheet_id or config.log_verif_sheet_id()
    tab = tab or config.log_verif_tab()

    fila = construir_fila(informe, link_informe=link_informe, ahora=ahora)

    try:
        return _append(servicio, sheet_id, _rango_a1(tab), fila)
    except HttpError as exc:
        if not _es_error_de_rango(exc):
            raise
        tab_real = _primera_hoja(servicio, sheet_id)
        log.warning(
            "Pestaña %r no encontrada en el Sheet de log; usando la primera "
            "hoja %r.", tab, tab_real,
        )
        return _append(servicio, sheet_id, _rango_a1(tab_real), fila)


# ---------------------------------------------------------------------------
# Smoke test manual:  python -m sheets_writer [ID_PROYECTO]
# ---------------------------------------------------------------------------

def _smoke(id_proyecto: str = "EU-SMOKE") -> None:
    """Append de una fila de prueba usando las credenciales configuradas.

    Útil para confirmar end-to-end (credenciales + scope + acceso al Sheet)
    sin depender de una verificación completa de Drive.
    """
    informe = InformeFinal(
        id_proyecto=id_proyecto,
        cliente="Cliente de prueba",
        responsable="Esteban",
        semana="Semana 99",
    )
    informe.checks = [
        CheckResult("C-00", "Check de prueba OK", "PASS", "", True, "Inventario"),
        CheckResult(
            "C-63", "Observación CNC de prueba", "WARN",
            "texto CNC no reconocido", False, "Texto CNC",
        ),
    ]
    resp = append_verificacion(
        informe, link_informe="https://drive.google.com/informe_smoke.txt"
    )
    print("Append OK →", resp.get("updates", resp))


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    _smoke(sys.argv[1] if len(sys.argv) > 1 else "EU-SMOKE")
