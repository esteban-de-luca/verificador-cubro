"""
drive/cliente.py — Autenticación Google Drive con Service Account.

Punto único de construcción del objeto `servicio` de la Drive API v3.
El servicio se cachea en memoria durante toda la sesión (las credenciales
JWT se refrescan automáticamente por google-auth cuando expiran).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config


@lru_cache(maxsize=1)
def obtener_servicio_drive() -> Any:
    """
    Construye y devuelve un objeto servicio Drive v3 autenticado con la
    Service Account configurada en Streamlit Secrets / entorno.

    El resultado se cachea: todas las llamadas subsiguientes reutilizan
    el mismo servicio. Los tokens OAuth se refrescan internamente.

    Returns:
        googleapiclient.discovery.Resource ya listo para operar.

    Raises:
        RuntimeError: si las credenciales no están configuradas.
    """
    info = config.google_credentials_info()
    credenciales = service_account.Credentials.from_service_account_info(
        info, scopes=config.DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


def resetear_servicio_cache() -> None:
    """Invalida el servicio cacheado (usar en tests o tras rotar credenciales)."""
    obtener_servicio_drive.cache_clear()
