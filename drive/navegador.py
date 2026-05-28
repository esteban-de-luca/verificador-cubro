"""
drive/navegador.py — Listar carpetas y archivos en Drive.

Jerarquía esperada:
    DRIVE_CUARENTENA_ID (raíz)
        ├─ Esteban/
        │   ├─ Semana 18/
        │   │   ├─ [OK] EU-21822_Sabine_Jennes/
        │   │   └─ SP-21493_Belen_Duenas/
        │   └─ Semana 19/
        ├─ Marina/
        └─ ...

Cada función devuelve una lista de dicts con al menos {id, name}.
El estado (prefijo) se extrae del nombre cuando aplica.
"""

from __future__ import annotations

import re
from typing import Any

import config


#: MIME type de carpeta Google Drive.
MIME_FOLDER = "application/vnd.google-apps.folder"

#: Regex para extraer el prefijo de estado del nombre de carpeta.
#: El orden de la alternancia importa: "OK - MANUAL" debe ir antes de "OK"
#: para que la regex no haga match parcial sobre el segundo.
_RE_PREFIJO = re.compile(r"^\[(BLOQUEADO|ADVERTENCIAS|OK - MANUAL|OK)\]\s+")

#: Regex para extraer el número de semana de "Semana XX".
_RE_SEMANA = re.compile(r"Semana\s+0*(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers de query
# ---------------------------------------------------------------------------

def _listar_subcarpetas(servicio: Any, parent_id: str) -> list[dict]:
    """
    Devuelve todas las subcarpetas directas (no recursivo) de parent_id.
    Paginado automáticamente — recorre todas las páginas de la API.
    """
    query = (
        f"'{parent_id}' in parents "
        f"and mimeType = '{MIME_FOLDER}' "
        f"and trashed = false"
    )
    resultados: list[dict] = []
    page_token: str | None = None
    while True:
        respuesta = servicio.files().list(
            q=query,
            fields="nextPageToken, files(id, name, parents)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute(num_retries=2)
        resultados.extend(respuesta.get("files", []))
        page_token = respuesta.get("nextPageToken")
        if not page_token:
            break
    return resultados


def _buscar_subcarpeta_por_nombre(
    servicio: Any, parent_id: str, nombre: str
) -> dict | None:
    """Busca una subcarpeta exacta por nombre dentro de parent_id.

    Filtra por nombre directamente en el servidor (no descarga todas las
    subcarpetas para luego filtrar en Python) — evita timeouts cuando el
    parent tiene muchas subcarpetas.
    """
    nombre_escapado = nombre.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"'{parent_id}' in parents "
        f"and mimeType = '{MIME_FOLDER}' "
        f"and name = '{nombre_escapado}' "
        f"and trashed = false"
    )
    respuesta = servicio.files().list(
        q=query,
        fields="files(id, name, parents)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute(num_retries=2)
    files = respuesta.get("files", [])
    return files[0] if files else None


def _extraer_estado(nombre: str) -> str:
    """
    Extrae el estado de una carpeta de proyecto a partir de su prefijo.
    Devuelve: 'BLOQUEADO' | 'ADVERTENCIAS' | 'OK' | 'OK_MANUAL' | 'PENDIENTE'.

    'OK_MANUAL' indica un override manual aplicado sobre un proyecto que la
    verificación automática había marcado como BLOQUEADO o ADVERTENCIAS.
    """
    m = _RE_PREFIJO.match(nombre)
    if not m:
        return "PENDIENTE"
    capturado = m.group(1)
    return "OK_MANUAL" if capturado == "OK - MANUAL" else capturado


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def listar_responsables(servicio: Any) -> list[dict]:
    """
    Subcarpetas directas de la zona de cuarentena cuyo nombre coincide con
    algún responsable configurado en config.RESPONSABLES.

    Returns:
        Lista de dicts [{id, name}] en el orden definido por config.RESPONSABLES.
    """
    raiz_id = config.drive_cuarentena_id()
    subcarpetas = {c["name"]: c for c in _listar_subcarpetas(servicio, raiz_id)}
    return [subcarpetas[r] for r in config.RESPONSABLES if r in subcarpetas]


def listar_semanas(servicio: Any, responsable: str) -> list[dict]:
    """
    Subcarpetas "Semana XX" e "INCIDENCIAS" dentro de la carpeta de un responsable.
    Las semanas se ordenan de más reciente a más antigua; INCIDENCIAS aparece primero.

    Returns:
        Lista de dicts [{id, name, numero}]. Para INCIDENCIAS, numero=0.
    """
    raiz_id = config.drive_cuarentena_id()
    carpeta_resp = _buscar_subcarpeta_por_nombre(servicio, raiz_id, responsable)
    if carpeta_resp is None:
        return []

    semanas: list[dict] = []
    incidencias: dict | None = None
    for c in _listar_subcarpetas(servicio, carpeta_resp["id"]):
        if c["name"].upper() == "INCIDENCIAS":
            incidencias = {"id": c["id"], "name": c["name"], "numero": 0}
        else:
            m = _RE_SEMANA.match(c["name"])
            if m:
                semanas.append({"id": c["id"], "name": c["name"], "numero": int(m.group(1))})
    semanas.sort(key=lambda s: s["numero"], reverse=True)
    if incidencias:
        semanas.insert(0, incidencias)
    return semanas


def listar_proyectos(servicio: Any, semana_id: str) -> list[dict]:
    """
    Proyectos dentro de una carpeta de semana.

    Args:
        servicio: cliente Drive.
        semana_id: ID de la carpeta "Semana XX".

    Returns:
        Lista [{id, name, estado, nombre_limpio}] ordenada alfabéticamente.
        `estado` ∈ {BLOQUEADO, ADVERTENCIAS, OK, OK_MANUAL, PENDIENTE}.
        `nombre_limpio` es el nombre sin el prefijo de estado.
    """
    proyectos: list[dict] = []
    for c in _listar_subcarpetas(servicio, semana_id):
        estado = _extraer_estado(c["name"])
        nombre_limpio = _RE_PREFIJO.sub("", c["name"])
        proyectos.append({
            "id": c["id"],
            "name": c["name"],
            "estado": estado,
            "nombre_limpio": nombre_limpio,
        })
    proyectos.sort(key=lambda p: p["nombre_limpio"].lower())
    return proyectos


def archivo_existe_en_carpeta(
    servicio: Any, folder_id: str, nombre: str
) -> bool:
    """¿Existe un archivo con `nombre` exacto dentro de `folder_id`?

    Match case-insensitive (Drive devuelve resultados sin distinguir
    mayúsculas para el filtro `name = '…'`).
    """
    nombre_escapado = nombre.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"'{folder_id}' in parents "
        f"and name = '{nombre_escapado}' "
        f"and trashed = false"
    )
    respuesta = servicio.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute(num_retries=2)
    return bool(respuesta.get("files", []))


def listar_archivos(servicio: Any, folder_id: str) -> list[dict]:
    """
    Archivos (no carpetas) dentro de una carpeta dada.

    Returns:
        Lista de dicts [{id, name, mimeType, size}].
    """
    # Nota: usamos solo 'trashed = false' sin filtro mimeType en la query
    # para máxima compatibilidad con Shared Drives; filtramos carpetas en Python.
    query = f"'{folder_id}' in parents and trashed = false"
    resultados: list[dict] = []
    page_token: str | None = None
    while True:
        respuesta = servicio.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute(num_retries=2)
        todos = respuesta.get("files", [])
        resultados.extend(f for f in todos if f.get("mimeType") != MIME_FOLDER)
        page_token = respuesta.get("nextPageToken")
        if not page_token:
            break
    return resultados
