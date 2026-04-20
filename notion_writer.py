"""
notion_writer.py — Escribe resultados de verificación en Notion.

Crea o actualiza una página en la base de datos "Log Verificaciones Ficheros de
Corte". Si ya existe un registro para el ID de proyecto dado, lo sobreescribe.

Los nombres de propiedades están centralizados en _PROPS para que sean fáciles
de ajustar si la BD de Notion cambia de nombre de columna.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from notion_client import Client, APIResponseError

from core.modelos import InformeFinal

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nombres de propiedades en la BD de Notion (ajustar aquí si cambian)
# ---------------------------------------------------------------------------

_PROPS = {
    "nombre":          "Nombre",            # title
    "id_proyecto":     "ID Proyecto",       # rich_text
    "cliente":         "Cliente",           # rich_text
    "responsable":     "Responsable",       # select
    "semana":          "Semana",            # rich_text
    "estado":          "Estado",            # select: BLOQUEADO | ADVERTENCIAS | APROBADO
    "n_errores":       "Errores",           # number
    "n_avisos":        "Avisos",            # number
    "n_pass":          "PASS",              # number
    "n_skip":          "SKIP",              # number
    "notas":           "Notas",             # rich_text — obs CNC no reconocidas
    "detalle_errores": "Detalle Errores",   # rich_text — errores bloqueantes resumidos
    "fecha":           "Fecha",             # date
}

_MAX_RICH_TEXT = 2000   # límite de Notion para rich_text


# ---------------------------------------------------------------------------
# Helpers de construcción de propiedades
# ---------------------------------------------------------------------------

def _rich(contenido: str) -> dict:
    """Propiedad rich_text con un único bloque de texto."""
    return {
        "rich_text": [
            {"text": {"content": contenido[:_MAX_RICH_TEXT]}}
        ]
    }


def _title(contenido: str) -> dict:
    return {
        "title": [
            {"text": {"content": contenido[:_MAX_RICH_TEXT]}}
        ]
    }


def _select(nombre: str) -> dict:
    return {"select": {"name": nombre}}


def _number(valor: int | float) -> dict:
    return {"number": valor}


def _date(valor: datetime.date) -> dict:
    return {"date": {"start": valor.isoformat()}}


# ---------------------------------------------------------------------------
# NotionWriter
# ---------------------------------------------------------------------------

class NotionWriter:
    """
    Escribe o actualiza un registro de verificación en Notion.

    Args:
        token:       Integration token de Notion (Internal Integration).
        database_id: ID de la base de datos destino.
    """

    def __init__(self, token: str, database_id: str) -> None:
        self._client = Client(auth=token)
        self._db_id = database_id

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def escribir_verificacion(self, informe: InformeFinal) -> str:
        """
        Crea o actualiza el registro de verificación para este proyecto.

        Returns:
            URL de la página Notion creada/actualizada.

        Raises:
            APIResponseError: si la API de Notion responde con error.
        """
        props = self._construir_propiedades(informe)
        existente = self._buscar_existente(informe.id_proyecto)

        if existente:
            log.info("Actualizando página Notion %s para %s",
                     existente["id"], informe.id_proyecto)
            pagina = self._client.pages.update(
                page_id=existente["id"],
                properties=props,
            )
        else:
            log.info("Creando página Notion para %s", informe.id_proyecto)
            pagina = self._client.pages.create(
                parent={"database_id": self._db_id},
                properties=props,
            )

        url: str = pagina.get("url", "")
        log.info("Notion OK → %s", url)
        return url

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _buscar_existente(self, id_proyecto: str) -> dict[str, Any] | None:
        """Devuelve la primera página cuyo «ID Proyecto» coincide, o None."""
        try:
            resp = self._client.databases.query(
                database_id=self._db_id,
                filter={
                    "property": _PROPS["id_proyecto"],
                    "rich_text": {"equals": id_proyecto},
                },
                page_size=1,
            )
            resultados = resp.get("results", [])
            return resultados[0] if resultados else None
        except APIResponseError as exc:
            log.warning("No se pudo buscar registro existente en Notion: %s", exc)
            return None

    def _construir_propiedades(self, informe: InformeFinal) -> dict[str, Any]:
        n_errores = len(informe.errores_criticos)
        n_avisos = len(informe.advertencias)
        n_pass = sum(1 for c in informe.checks if c.resultado == "PASS")
        n_skip = sum(1 for c in informe.checks if c.resultado == "SKIP")

        notas = self._extraer_notas(informe)
        detalle = self._extraer_detalle_errores(informe)

        titulo = f"{informe.id_proyecto}"
        if informe.cliente:
            titulo += f" · {informe.cliente}"

        return {
            _PROPS["nombre"]:          _title(titulo),
            _PROPS["id_proyecto"]:     _rich(informe.id_proyecto),
            _PROPS["cliente"]:         _rich(informe.cliente),
            _PROPS["responsable"]:     _select(informe.responsable) if informe.responsable else _select("—"),
            _PROPS["semana"]:          _rich(informe.semana),
            _PROPS["estado"]:          _select(informe.estado_global),
            _PROPS["n_errores"]:       _number(n_errores),
            _PROPS["n_avisos"]:        _number(n_avisos),
            _PROPS["n_pass"]:          _number(n_pass),
            _PROPS["n_skip"]:          _number(n_skip),
            _PROPS["notas"]:           _rich(notas),
            _PROPS["detalle_errores"]: _rich(detalle),
            _PROPS["fecha"]:           _date(datetime.date.today()),
        }

    def _extraer_notas(self, informe: InformeFinal) -> str:
        """
        Recopila las observaciones CNC no reconocidas (C-63) más cualquier
        advertencia del extractor (C-62) para el campo Notas de Notion.
        """
        partes: list[str] = []
        for c in informe.checks:
            if c.id in ("C-62", "C-63") and c.resultado == "WARN" and c.detalle:
                partes.append(c.detalle)
        return "\n".join(partes)

    def _extraer_detalle_errores(self, informe: InformeFinal) -> str:
        """Resumen de los primeros 10 errores bloqueantes."""
        lines: list[str] = []
        for c in informe.errores_criticos[:10]:
            lines.append(f"{c.id}: {c.desc}")
            if c.detalle:
                lines.append(f"  → {c.detalle}")
        return "\n".join(lines)
