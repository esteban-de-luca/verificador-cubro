"""
checks/checks_texto.py — C-60 a C-63: Observaciones CNC (Capa 2, texto OT).

Los patrones del catálogo usan {variable} como placeholder. La coincidencia
se implementa convirtiendo {variable} → (.+) y aplicando regex.

Recibe reglas_cnc (no reglas) como parámetro — conforme a la arquitectura.
"""

from __future__ import annotations

import re

from core.modelos import CheckResult, DXFDoc, OTData, Pieza
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO = "Texto CNC"


# ---------------------------------------------------------------------------
# Matching de patrones CNC
# ---------------------------------------------------------------------------

def _patron_a_regex(patron: str) -> re.Pattern:
    """
    Convierte un patrón de catálogo CNC a regex.
    '{variable}' → '(.+?)' · El resto se escapa con re.escape.
    """
    partes = re.split(r"\{[^}]+\}", patron)
    regex = ".+?".join(re.escape(p) for p in partes)
    return re.compile(regex, re.IGNORECASE)


def _coincide_algun_patron(obs: str, patrones_compilados: list[re.Pattern]) -> bool:
    return any(p.search(obs) for p in patrones_compilados)


def _compilar_patrones(reglas_cnc: dict) -> list[re.Pattern]:
    return [_patron_a_regex(exc["patron"]) for exc in reglas_cnc["excepciones"]]


def _patrones_por_check(reglas_cnc: dict, id_check: str) -> list[re.Pattern]:
    """Devuelve solo los patrones que justifican un check concreto."""
    return [
        _patron_a_regex(exc["patron"])
        for exc in reglas_cnc["excepciones"]
        if exc["justifica_check"] == id_check
    ]


# ---------------------------------------------------------------------------
# C-60: Retales mencionados en OT si hay layer RETAL UTILIZADO en DXFs
# ---------------------------------------------------------------------------

def check_retales_en_ot(
    ot: OTData, dxfs: list[DXFDoc], reglas_cnc: dict
) -> CheckResult:
    """
    C-60: Si algún DXF tiene el layer RETAL UTILIZADO, la OT debe mencionar
    'retal utilizado' o 'retal de' en sus observaciones CNC.
    Bloquea: Sí.
    """
    # Detectar si algún DXF tiene layer de retal utilizado
    todas_layers = set().union(*(d.layers for d in dxfs)) if dxfs else set()
    hay_retal_layer = any(
        "retal" in lay.lower() and "utilizado" in lay.lower()
        for lay in todas_layers
    )
    if not hay_retal_layer:
        return _pass("C-60", "Retales en OT si hay layer RETAL UTILIZADO", True, _GRUPO)

    patrones = _patrones_por_check(reglas_cnc, "C-60")
    obs_cnc = ot.observaciones_cnc
    if not obs_cnc:
        return _fail(
            "C-60", "Retales en OT si hay layer RETAL UTILIZADO",
            "DXF tiene RETAL UTILIZADO pero OT sin observaciones CNC de retal",
            True, _GRUPO,
        )
    hay_mención = any(_coincide_algun_patron(obs, patrones) for obs in obs_cnc)
    if hay_mención:
        return _pass("C-60", "Retales en OT si hay layer RETAL UTILIZADO", True, _GRUPO)
    return _fail(
        "C-60", "Retales en OT si hay layer RETAL UTILIZADO",
        "Layer RETAL UTILIZADO en DXF pero no se menciona en observaciones CNC de la OT",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-61: Piezas sin mecanizar mencionadas en OT si hay P con mecanizado vacío
# ---------------------------------------------------------------------------

def check_sin_mecanizar_en_ot(
    piezas: list[Pieza], ot: OTData, reglas_cnc: dict
) -> CheckResult:
    """
    C-61: Si hay puertas P con campo mecanizado vacío (sin mecanizar),
    la OT debe incluir la observación 'sin mecanizar'.
    Bloquea: Sí.
    """
    puertas_sin_mec = [
        p.id for p in piezas
        if p.tipologia == "P" and not p.mecanizado.strip()
    ]
    if not puertas_sin_mec:
        return _pass("C-61", "Piezas sin mecanizar mencionadas en OT", True, _GRUPO)

    patrones = _patrones_por_check(reglas_cnc, "C-61")
    obs_cnc = ot.observaciones_cnc
    hay_mención = any(_coincide_algun_patron(obs, patrones) for obs in obs_cnc)
    if hay_mención:
        return _pass("C-61", "Piezas sin mecanizar mencionadas en OT", True, _GRUPO)
    return _skip(
        "C-61", "Piezas sin mecanizar mencionadas en OT",
        f"Revisar OT: puertas sin mecanizar {puertas_sin_mec} no mencionadas",
        _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-62: Cada observación CNC reconocida por al menos un patrón del catálogo
# ---------------------------------------------------------------------------

def check_observaciones_reconocidas(ot: OTData, reglas_cnc: dict) -> CheckResult:
    """
    C-62: Cada línea de observaciones CNC de la OT debe coincidir con
    al menos un patrón del catálogo reglas_cnc.yaml.
    Bloquea: No.
    """
    if not ot.observaciones_cnc:
        return _pass("C-62", "Observaciones CNC reconocidas por catálogo", False, _GRUPO)

    todos_patrones = _compilar_patrones(reglas_cnc)
    no_reconocidas = [
        obs for obs in ot.observaciones_cnc
        if not _coincide_algun_patron(obs, todos_patrones)
    ]
    if not no_reconocidas:
        return _pass("C-62", "Observaciones CNC reconocidas por catálogo", False, _GRUPO)
    detalle = "; ".join(f"No reconocida: '{obs}'" for obs in no_reconocidas)
    return _skip("C-62", "Observaciones CNC reconocidas por catálogo", detalle, _GRUPO)


# ---------------------------------------------------------------------------
# C-63: Observaciones no reconocidas marcadas para revisión humana
# ---------------------------------------------------------------------------

def check_observaciones_no_reconocidas(ot: OTData, reglas_cnc: dict) -> CheckResult:
    """
    C-63: Las observaciones CNC no reconocidas se marcan para revisión
    con su texto íntegro (se escriben en Notion campo 'Notas').
    Bloquea: No. Siempre PASS o WARN (nunca FAIL).
    """
    if not ot.observaciones_cnc:
        return _pass("C-63", "Observaciones no reconocidas marcadas para revisión",
                     False, _GRUPO)

    todos_patrones = _compilar_patrones(reglas_cnc)
    no_reconocidas = [
        obs for obs in ot.observaciones_cnc
        if not _coincide_algun_patron(obs, todos_patrones)
    ]
    if not no_reconocidas:
        return _pass("C-63", "Observaciones no reconocidas marcadas para revisión",
                     False, _GRUPO)
    detalle = " | ".join(f"«{obs}»" for obs in no_reconocidas)
    return _skip(
        "C-63", "Observaciones no reconocidas marcadas para revisión",
        f"Requieren revisión humana: {detalle}", _GRUPO,
    )
