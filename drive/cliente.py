"""
drive/cliente.py — Autenticación Google Drive con Service Account.

Punto único de construcción del objeto `servicio` de la Drive API v3.
El servicio se cachea en memoria durante toda la sesión (las credenciales
JWT se refrescan automáticamente por google-auth cuando expiran).
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

import httplib2
from google.oauth2 import service_account
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

import config


#: Timeout (segundos) para cada operación HTTP a Drive. Evita que un
#: cuelgue puntual del socket (cold start, glitch de red) bloquee la app
#: indefinidamente — junto con num_retries=2 en cada .execute(), una
#: lentitud transitoria se reintenta en vez de tirar la página.
_DRIVE_HTTP_TIMEOUT = 30


#: Lock global para serializar requests HTTP a la Drive API.
#:
#: httplib2 (transporte por defecto de google-api-python-client) NO es
#: thread-safe: reusa un único socket SSL por host y dos hilos llamando
#: SSL_read en paralelo revientan OpenSSL con un segfault (CRYPTO_malloc).
#:
#: En Streamlit Cloud esto se dispara cuando dos cache misses concurrentes
#: (p.ej. _listar_semanas_cached + _listar_proyectos_cached) atacan el
#: mismo servicio cacheado a la vez. Serializar las llamadas en el cliente
#: es la solución estándar mientras no migremos a un transporte
#: thread-safe (httpx).
_drive_http_lock = threading.Lock()


class _LockedHttp:
    """Envoltorio thread-safe sobre el http object usado por googleapiclient.

    Serializa `.request()` con un lock global; el resto de accesos a
    atributos se delegan al inner (lectura) o se aplican sobre el inner
    (escritura) para mantener la compatibilidad con googleapiclient, que
    a veces consulta/modifica flags del transporte.
    """

    def __init__(self, inner: Any) -> None:
        object.__setattr__(self, "_inner", inner)

    def request(self, *args, **kwargs):
        with _drive_http_lock:
            return self._inner.request(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_inner":
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)


@lru_cache(maxsize=1)
def obtener_credenciales() -> service_account.Credentials:
    """Credenciales de la Service Account (cacheadas, thread-safe para refresh)."""
    info = config.google_credentials_info()
    return service_account.Credentials.from_service_account_info(
        info, scopes=config.DRIVE_SCOPES
    )


@lru_cache(maxsize=1)
def obtener_servicio_drive() -> Any:
    """
    Construye y devuelve un objeto servicio Drive v3 autenticado con la
    Service Account configurada en Streamlit Secrets / entorno.

    El resultado se cachea: todas las llamadas subsiguientes reutilizan
    el mismo servicio. Los tokens OAuth se refrescan internamente. Todas
    las requests HTTP están serializadas con un lock para evitar el
    segfault de httplib2 bajo concurrencia (ver _drive_http_lock).

    Returns:
        googleapiclient.discovery.Resource ya listo para operar.

    Raises:
        RuntimeError: si las credenciales no están configuradas.
    """
    http = AuthorizedHttp(
        obtener_credenciales(),
        http=httplib2.Http(timeout=_DRIVE_HTTP_TIMEOUT),
    )
    return build("drive", "v3", http=_LockedHttp(http), cache_discovery=False)


def resetear_servicio_cache() -> None:
    """Invalida el servicio cacheado (usar en tests o tras rotar credenciales)."""
    obtener_servicio_drive.cache_clear()
