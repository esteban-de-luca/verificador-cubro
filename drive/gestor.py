"""
drive/gestor.py — Operaciones de escritura sobre Drive.

Cubre las dos mutaciones que la app ejecuta:
    1. Renombrar una carpeta de proyecto para reflejar su estado de verificación
       (añadir/reemplazar prefijo `[OK] `, `[ADVERTENCIAS] `, `[BLOQUEADO] `).
    2. Mover una carpeta aprobada a Carpintek (poka-yoke de producción).
"""

from __future__ import annotations

import io
import re
from typing import Any

from googleapiclient.http import MediaIoBaseUpload

from drive.navegador import _RE_PREFIJO


#: Estados válidos aceptados por aplicar_prefijo_estado.
ESTADOS_VALIDOS = frozenset({"bloqueado", "advertencias", "aprobado"})


def renombrar_carpeta(servicio: Any, folder_id: str, nuevo_nombre: str) -> dict:
    """
    Renombra una carpeta de Drive.

    Args:
        servicio: cliente Drive v3.
        folder_id: ID de la carpeta.
        nuevo_nombre: nombre completo que tendrá la carpeta tras la operación.

    Returns:
        Metadata de la carpeta tras el rename: {id, name}.
    """
    return servicio.files().update(
        fileId=folder_id,
        body={"name": nuevo_nombre},
        fields="id, name",
        supportsAllDrives=True,
    ).execute()


def mover_carpeta(servicio: Any, folder_id: str, destino_id: str) -> dict:
    """
    Mueve una carpeta a un nuevo parent, eliminando los parents previos.

    Args:
        servicio: cliente Drive v3.
        folder_id: ID de la carpeta a mover.
        destino_id: ID del nuevo parent (ej. Carpintek > Semana XX).

    Returns:
        Metadata tras el movimiento: {id, name, parents}.
    """
    actual = servicio.files().get(
        fileId=folder_id,
        fields="parents",
        supportsAllDrives=True,
    ).execute()
    parents_previos = ",".join(actual.get("parents", []))

    return servicio.files().update(
        fileId=folder_id,
        addParents=destino_id,
        removeParents=parents_previos,
        fields="id, name, parents",
        supportsAllDrives=True,
    ).execute()


def subir_informe_txt(
    servicio: Any,
    folder_id: str,
    nombre_archivo: str,
    contenido: str,
) -> dict:
    """
    Sube (o sobreescribe) un archivo .txt en la carpeta de Drive indicada.

    Si ya existe un archivo con el mismo nombre en la carpeta, lo elimina
    primero para evitar duplicados.

    Args:
        servicio:       cliente Drive v3.
        folder_id:      ID de la carpeta destino (la carpeta del proyecto).
        nombre_archivo: nombre del archivo, ej. "informe_EU-21822_Sabine.txt".
        contenido:      texto a guardar (UTF-8).

    Returns:
        Metadata del archivo creado: {id, name, webViewLink}.
    """
    # Eliminar versión anterior si existe
    existentes = servicio.files().list(
        q=(
            f"'{folder_id}' in parents "
            f"and name = '{nombre_archivo}' "
            f"and trashed = false"
        ),
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute().get("files", [])
    for f in existentes:
        servicio.files().delete(
            fileId=f["id"], supportsAllDrives=True
        ).execute()

    media = MediaIoBaseUpload(
        io.BytesIO(contenido.encode("utf-8")),
        mimetype="text/plain",
        resumable=False,
    )
    return servicio.files().create(
        body={"name": nombre_archivo, "parents": [folder_id]},
        media_body=media,
        fields="id, name, webViewLink",
        supportsAllDrives=True,
    ).execute()


def aplicar_prefijo_estado(
    servicio: Any,
    folder_id: str,
    nombre_actual: str,
    estado: str,
    reglas: dict,
) -> dict:
    """
    Renombra una carpeta de proyecto añadiendo el prefijo de estado
    definido en reglas.yaml → nomenclatura.prefijos_estado.

    Si la carpeta ya tenía un prefijo de estado previo, éste se sustituye.

    Args:
        servicio: cliente Drive v3.
        folder_id: ID de la carpeta de proyecto.
        nombre_actual: nombre completo actual de la carpeta (con o sin prefijo).
        estado: una de {'bloqueado', 'advertencias', 'aprobado'}.
        reglas: dict de reglas cargado por reglas_loader.

    Returns:
        Metadata tras el rename.

    Raises:
        ValueError: si `estado` no es válido o falta en los prefijos del YAML.
    """
    if estado not in ESTADOS_VALIDOS:
        raise ValueError(
            f"estado inválido: {estado!r}. Debe ser uno de {sorted(ESTADOS_VALIDOS)}"
        )

    prefijos = reglas["nomenclatura"]["prefijos_estado"]
    if estado not in prefijos:
        raise ValueError(
            f"reglas.yaml → nomenclatura.prefijos_estado no define '{estado}'"
        )

    nombre_limpio = _RE_PREFIJO.sub("", nombre_actual)
    nuevo_nombre = f"{prefijos[estado]}{nombre_limpio}"
    return renombrar_carpeta(servicio, folder_id, nuevo_nombre)
