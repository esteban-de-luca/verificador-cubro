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
_RE_PREFIJO = re.compile(r"^\[(BLOQUEADO|ADVERTENCIAS|OK)\]\s+")

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
        ).execute()
        resultados.extend(respuesta.get("files", []))
        page_token = respuesta.get("nextPageToken")
        if not page_token:
            break
    return resultados


def _buscar_subcarpeta_por_nombre(
    servicio: Any, parent_id: str, nombre: str
) -> dict | None:
    """Busca una subcarpeta exacta por nombre dentro de parent_id."""
    for sub in _listar_subcarpetas(servicio, parent_id):
        if sub["name"] == nombre:
            return sub
    return None


def _extraer_estado(nombre: str) -> str:
    """
    Extrae el estado de una carpeta de proyecto a partir de su prefijo.
    Devuelve: 'BLOQUEADO' | 'ADVERTENCIAS' | 'OK' | 'PENDIENTE'.
    """
    m = _RE_PREFIJO.match(nombre)
    return m.group(1) if m else "PENDIENTE"


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
    Subcarpetas "Semana XX" dentro de la carpeta de un responsable,
    ordenadas de más reciente (número mayor) a más antigua.

    Returns:
        Lista de dicts [{id, name, numero}] con el entero de semana añadido.
    """
    raiz_id = config.drive_cuarentena_id()
    carpeta_resp = _buscar_subcarpeta_por_nombre(servicio, raiz_id, responsable)
    if carpeta_resp is None:
        return []

    semanas: list[dict] = []
    for c in _listar_subcarpetas(servicio, carpeta_resp["id"]):
        m = _RE_SEMANA.match(c["name"])
        if m:
            semanas.append({"id": c["id"], "name": c["name"], "numero": int(m.group(1))})
    semanas.sort(key=lambda s: s["numero"], reverse=True)
    return semanas


def listar_proyectos(servicio: Any, semana_id: str) -> list[dict]:
    """
    Proyectos dentro de una carpeta de semana.

    Args:
        servicio: cliente Drive.
        semana_id: ID de la carpeta "Semana XX".

    Returns:
        Lista [{id, name, estado, nombre_limpio}] ordenada alfabéticamente.
        `estado` ∈ {BLOQUEADO, ADVERTENCIAS, OK, PENDIENTE}.
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
        ).execute()
        todos = respuesta.get("files", [])
        resultados.extend(f for f in todos if f.get("mimeType") != MIME_FOLDER)
        page_token = respuesta.get("nextPageToken")
        if not page_token:
            break
    return resultados
