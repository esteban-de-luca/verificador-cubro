"""
checks/_helpers.py — Helpers internos compartidos por todos los módulos de checks.

No usar fuera del paquete checks/.
"""

from __future__ import annotations

from core.modelos import CheckResult


def _pass(id: str, desc: str, bloquea: bool, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "PASS", "Correcto", bloquea, grupo)


def _fail(id: str, desc: str, detalle: str, bloquea: bool, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "FAIL", detalle, bloquea, grupo)


def _warn(id: str, desc: str, detalle: str, grupo: str) -> CheckResult:
    return CheckResult(id, desc, "WARN", detalle, False, grupo)


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
        return _warn(id, desc, detalle, grupo)
    return _fail(id, desc, detalle, bloquea, grupo)
