"""
config.py — Configuración central del Verificador

Lee credenciales e IDs desde:
  1. Streamlit Secrets (producción en Streamlit Cloud)
  2. Variables de entorno (desarrollo local / CI)
  3. Archivo .streamlit/secrets.toml (desarrollo local con Streamlit)

Nada sensible se hardcodea: todos los secrets vienen de fuera del repo.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st


def apply_sidebar_width() -> None:
    """Fija el ancho del sidebar (23.1rem) y oculta el nav automático de Streamlit."""
    st.markdown(
        """<style>
        [data-testid='stSidebar'] { min-width: 23.1rem; max-width: 23.1rem; }
        [data-testid='stSidebarNav'] { display: none; }
        </style>""",
        unsafe_allow_html=True,
    )


def render_sidebar_nav() -> None:
    """Dibuja el encabezado del sidebar con logo arriba y links de navegación debajo."""
    from pathlib import Path
    logo = Path(__file__).parent / "logo_cubro.png"
    st.sidebar.image(str(logo))
    st.sidebar.page_link("app.py", label="🔍 Verificador de Fichero")
    st.sidebar.page_link("pages/2_Cola_Global.py", label="📋 Ficheros pendientes")
    st.sidebar.markdown("---")


# ---------------------------------------------------------------------------
# Constantes NO sensibles (pueden vivir en el repo)
# ---------------------------------------------------------------------------

#: Miembros del equipo con carpeta propia en la zona de cuarentena.
RESPONSABLES: list[str] = ["Esteban", "Javier", "Lucia", "Isabel", "Marina"]

#: ID fijo de la base de datos de Notion "Log Verificaciones Ficheros de Corte".
NOTION_DB_ID: str = "344f687d-1343-80c0-9b63-000b2d119814"

#: Scopes OAuth requeridos por la Service Account para operar sobre Drive.
DRIVE_SCOPES: list[str] = ["https://www.googleapis.com/auth/drive"]


# ---------------------------------------------------------------------------
# Helpers internos de acceso a secrets
# ---------------------------------------------------------------------------

def _leer_streamlit_secrets() -> dict[str, Any] | None:
    """Devuelve st.secrets si Streamlit está disponible y tiene secrets cargados."""
    try:
        import streamlit as st  # import tardío: streamlit es opcional en tests
        _ = st.secrets  # fuerza carga
        return st.secrets
    except Exception:
        return None


def _get_secret(seccion: str, clave: str, env_var: str | None = None) -> str | None:
    """
    Busca un secret en este orden:
      1. Streamlit Secrets [seccion][clave]
      2. Variable de entorno env_var (si se proporciona)
    Devuelve None si no se encuentra en ningún sitio.
    """
    secrets = _leer_streamlit_secrets()
    if secrets is not None:
        try:
            return secrets[seccion][clave]
        except (KeyError, TypeError):
            pass
    if env_var:
        return os.environ.get(env_var)
    return None


# ---------------------------------------------------------------------------
# IDs de carpetas Drive
# ---------------------------------------------------------------------------

def drive_cuarentena_id() -> str:
    """ID de la carpeta raíz 'Pre Produccion – Verificacion'."""
    valor = _get_secret("drive", "DRIVE_CUARENTENA_ID", "DRIVE_CUARENTENA_ID")
    if not valor:
        raise RuntimeError(
            "DRIVE_CUARENTENA_ID no configurado en Streamlit Secrets ni en entorno"
        )
    return valor


def drive_carpintek_id() -> str:
    """ID de la carpeta Carpintek > 10. Next."""
    valor = _get_secret("drive", "DRIVE_CARPINTEK_ID", "DRIVE_CARPINTEK_ID")
    if not valor:
        raise RuntimeError(
            "DRIVE_CARPINTEK_ID no configurado en Streamlit Secrets ni en entorno"
        )
    return valor


# ---------------------------------------------------------------------------
# Credenciales Google Service Account
# ---------------------------------------------------------------------------

def google_credentials_info() -> dict[str, Any]:
    """
    Devuelve el diccionario de credenciales de la Service Account.

    Orden de búsqueda:
      1. Streamlit Secrets [google][credentials] (puede ser dict o string JSON)
      2. Variable de entorno GOOGLE_CREDENTIALS_JSON (string JSON)
      3. Archivo apuntado por GOOGLE_APPLICATION_CREDENTIALS (ruta a JSON)
    """
    secrets = _leer_streamlit_secrets()
    if secrets is not None:
        try:
            cred = secrets["google"]["credentials"]
            if isinstance(cred, str):
                return json.loads(cred)
            return dict(cred)
        except (KeyError, TypeError):
            pass

    cred_env = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if cred_env:
        return json.loads(cred_env)

    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and Path(cred_path).exists():
        return json.loads(Path(cred_path).read_text(encoding="utf-8"))

    raise RuntimeError(
        "Credenciales Google no encontradas. Configurar [google].credentials en "
        "Streamlit Secrets o GOOGLE_CREDENTIALS_JSON/GOOGLE_APPLICATION_CREDENTIALS."
    )


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

def notion_token() -> str:
    valor = _get_secret("notion", "NOTION_TOKEN", "NOTION_TOKEN")
    if not valor:
        raise RuntimeError(
            "NOTION_TOKEN no configurado en Streamlit Secrets ni en entorno"
        )
    return valor
