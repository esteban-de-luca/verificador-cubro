"""
checks/_helpers.py — Helpers internos compartidos por todos los módulos de checks.

No usar fuera del paquete checks/.
"""

from __future__ import annotations

import re

from core.modelos import CheckResult

# Sufijo de incidencia (INC, INC2, …) sobre un ID ya normalizado (sin guiones).
_RE_INC_SUFIJO = re.compile(r"INC\d*$")


def _norm_id(id_proyecto: str) -> str:
    """Normaliza un ID de proyecto: mayúsculas, sin guiones ni guiones bajos."""
    return id_proyecto.upper().replace("-", "").replace("_", "")


def _id_coincide_proyecto(id_encontrado_norm: str, id_proyecto_norm: str) -> bool:
    """
    True si un ID ya normalizado corresponde al proyecto `id_proyecto_norm`.

    En proyectos de incidencia (sufijo INC) se acepta además el ID base del
    producto original (sin INC), porque la logística/EAN —nombre del EAN
    LOGISTIC, IDs de bulto, etc.— se hereda del producto base
    (p. ej. 'SP20594' es válido en el proyecto 'SP20594INC').
    """
    if id_encontrado_norm == id_proyecto_norm:
        return True
    id_base = _RE_INC_SUFIJO.sub("", id_proyecto_norm)
    return id_base != id_proyecto_norm and id_encontrado_norm == id_base


def _es_incidencia(id_proyecto: str) -> bool:
    """True si el ID corresponde a una incidencia (sufijo -INC, -INC2, …)."""
    return "-INC" in id_proyecto.upper().replace("_", "-")


def _pass(id: str, desc: str, bloquea: bool, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "PASS", "Correcto", bloquea, grupo)


def _fail(id: str, desc: str, detalle: str, bloquea: bool, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "FAIL", detalle, bloquea, grupo)


def _warn(id: str, desc: str, detalle: str, grupo: str,
          bloquea: bool = False) -> CheckResult:
    return CheckResult(id, desc, "WARN", detalle, bloquea, grupo)


def _skip(id: str, desc: str, motivo: str, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "SKIP", motivo, False, grupo)


def _resultado(
    id: str,
    desc: str,
    errores: list[str],
    bloquea: bool,
    grupo: str,
    tipo_fail: str = "FAIL",
) -> CheckResult:
    """
    Devuelve PASS si errores está vacía, FAIL/WARN con los primeros 5 errores si no.
    """
    if not errores:
        return _pass(id, desc, bloquea, grupo)
    n = len(errores)
    detalle = "; ".join(errores[:5])
    if n > 5:
        detalle += f" (y {n - 5} más)"
    if tipo_fail == "WARN":
        return _warn(id, desc, detalle, grupo, bloquea)
    return _fail(id, desc, detalle, bloquea, grupo)
