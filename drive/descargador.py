"""
drive/descargador.py — Descarga de archivos en memoria.

Regla dura: los archivos NUNCA se escriben a disco. Todo flujo termina en
`io.BytesIO` y se consume desde ahí por los extractores.

Los archivos de una carpeta se descargan en paralelo (ThreadPoolExecutor)
usando AuthorizedSession (requests, thread-safe) en lugar del cliente Drive
estándar (httplib2, no thread-safe).
"""

from __future__ import annotations

import io
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from google.auth.transport.requests import AuthorizedSession

from drive.navegador import listar_archivos

_SUBCARPETA_ARCHIVOS = "1-Informacion"
_MAX_WORKERS = 8

# Una AuthorizedSession por thread — se crea una sola vez por thread y se reutiliza.
_thread_local = threading.local()


def _session() -> AuthorizedSession:
    from drive.cliente import obtener_credenciales
    if not hasattr(_thread_local, "session"):
        _thread_local.session = AuthorizedSession(obtener_credenciales())
    return _thread_local.session


def descargar_archivo(servicio: Any, file_id: str) -> io.BytesIO:
    """
    Descarga un único archivo por su ID a un BytesIO.
    Usa el servicio Drive v3 estándar (para llamadas fuera del pool de threads).
    """
    from googleapiclient.http import MediaIoBaseDownload
    request = servicio.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer


def _descargar_con_session(file_id: str) -> io.BytesIO:
    """Descarga un archivo usando AuthorizedSession (thread-safe)."""
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
    resp = _session().get(url, params={"alt": "media", "supportsAllDrives": "true"})
    resp.raise_for_status()
    return io.BytesIO(resp.content)


def descargar_carpeta(servicio: Any, folder_id: str) -> dict[str, io.BytesIO]:
    """
    Descarga todos los archivos de una carpeta de proyecto a memoria en paralelo.

    Si existe una subcarpeta llamada '1-Informacion', descarga los archivos
    de ahí (estructura habitual de CUBRO). Si no existe, usa la carpeta raíz.

    Args:
        servicio: cliente Drive v3 (solo para listar/navegar, no para descargar).
        folder_id: ID de la carpeta del proyecto.

    Returns:
        Dict {nombre_archivo: BytesIO}.
    """
    from drive.navegador import _buscar_subcarpeta_por_nombre
    sub = _buscar_subcarpeta_por_nombre(servicio, folder_id, _SUBCARPETA_ARCHIVOS)
    carpeta_id = sub["id"] if sub else folder_id

    archivos = listar_archivos(servicio, carpeta_id)
    if not archivos:
        return {}

    resultado: dict[str, io.BytesIO] = {}
    workers = min(_MAX_WORKERS, len(archivos))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futuros = {
            executor.submit(_descargar_con_session, a["id"]): a["name"]
            for a in archivos
        }
        for futuro in as_completed(futuros):
            nombre = futuros[futuro]
            resultado[nombre] = futuro.result()

    return resultado
