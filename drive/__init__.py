"""
drive — Módulo de integración con Google Drive vía Service Account.

Submódulos:
    cliente      Autenticación y construcción del servicio Drive v3.
    navegador    Listado de carpetas (responsable → semana → proyecto).
    descargador  Descarga de archivos en memoria (io.BytesIO, nunca a disco).
    gestor       Renombrar y mover carpetas.
"""

from drive.cliente import obtener_servicio_drive
from drive.navegador import (
    listar_responsables,
    listar_semanas,
    listar_proyectos,
    listar_archivos,
)
from drive.descargador import descargar_carpeta
from drive.gestor import (
    renombrar_carpeta,
    mover_carpeta,
    aplicar_prefijo_estado,
)

__all__ = [
    "obtener_servicio_drive",
    "listar_responsables",
    "listar_semanas",
    "listar_proyectos",
    "listar_archivos",
    "descargar_carpeta",
    "renombrar_carpeta",
    "mover_carpeta",
    "aplicar_prefijo_estado",
]
