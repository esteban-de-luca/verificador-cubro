"""
checks/checks_externos.py — C-84+: Validaciones contra carpetas Drive externas.

Estos checks miran archivos que viven fuera de la carpeta del proyecto.
El engine pre-resuelve la existencia (con Drive API) y le pasa al check
solo un bool / None para mantenerlos puros y testeables sin mockear Drive.
"""

from __future__ import annotations

from core.modelos import CheckResult
from checks._helpers import _pass, _fail, _skip

_GRUPO = "Externo"


# ---------------------------------------------------------------------------
# C-84: CSV de exportación a HubSpot existe en carpeta de Drive
# ---------------------------------------------------------------------------

def check_csv_hubspot(
    id_proyecto: str,
    csv_existe: bool | None,
) -> CheckResult:
    """
    C-84: En la carpeta DRIVE_HUBSPOT_EXPORT_ID debe existir un CSV
    nombrado exactamente '{ID_PROYECTO}.csv'.

    Args:
        id_proyecto: Ej. 'EU-21822', 'SP-20848-INC2', '4302'.
        csv_existe: True si el archivo existe; False si no; None si la
            carpeta no pudo consultarse (Drive caído, sin permisos, etc.).

    Bloquea: Sí.
    """
    ID = "C-84"
    DESC = "CSV exportación HubSpot existe en Drive"

    if csv_existe is None:
        return _skip(
            ID, DESC,
            "Carpeta HubSpot no accesible (Drive sin respuesta o sin permisos)",
            _GRUPO,
        )

    if csv_existe:
        return _pass(ID, DESC, True, _GRUPO)

    return _fail(
        ID, DESC,
        f"No existe '{id_proyecto}.csv' en la carpeta de exportación HubSpot",
        True, _GRUPO,
    )
