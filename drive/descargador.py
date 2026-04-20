"""
drive/descargador.py — Descarga de archivos en memoria.

Regla dura: los archivos NUNCA se escriben a disco. Todo flujo termina en
`io.BytesIO` y se consume desde ahí por los extractores.
"""

from __future__ import annotations

import io
from typing import Any

from googleapiclient.http import MediaIoBaseDownload

from drive.navegador import listar_archivos


def descargar_archivo(servicio: Any, file_id: str) -> io.BytesIO:
    """
    Descarga un único archivo por su ID a un BytesIO.

    Args:
        servicio: cliente Drive v3.
        file_id: ID del archivo en Drive.

    Returns:
        BytesIO posicionado en el inicio, listo para ser leído.
    """
    request = servicio.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer


_SUBCARPETA_ARCHIVOS = "1-Informacion"


def descargar_carpeta(servicio: Any, folder_id: str) -> dict[str, io.BytesIO]:
    """
    Descarga todos los archivos de una carpeta de proyecto a memoria.

    Si existe una subcarpeta llamada '1-Informacion', descarga los archivos
    de ahí (estructura habitual de CUBRO). Si no existe, usa la carpeta raíz.

    Args:
        servicio: cliente Drive v3.
        folder_id: ID de la carpeta del proyecto.

    Returns:
        Dict {nombre_archivo: BytesIO}.
    """
    from drive.navegador import _buscar_subcarpeta_por_nombre
    sub = _buscar_subcarpeta_por_nombre(servicio, folder_id, _SUBCARPETA_ARCHIVOS)
    carpeta_id = sub["id"] if sub else folder_id

    archivos = listar_archivos(servicio, carpeta_id)
    resultado: dict[str, io.BytesIO] = {}
    for archivo in archivos:
        resultado[archivo["name"]] = descargar_archivo(servicio, archivo["id"])
    return resultado
