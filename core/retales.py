"""
core/retales.py — Retales citados en las Observaciones CNC de la OT.

En el mismo bloque OBSERVACIONES CNC conviven los dos sentidos del retal, y
significan cosas opuestas para producción:

    consumo:     "La pieza P1 se debe cortar de retal R841"
                 → esa pieza sale de un sobrante de stock: necesita plano de
                   nesting pero NO consume tablero nuevo ('# Tableros 0' en la
                   OT es correcto).

    generación:  "Retales generados 1x de LIN Vapour R865, 1x de LAC Blanco R866"
                 → el proyecto DEJA sobrantes al cortar sus tableros. No
                   justifica ningún 0: casi todas las OT generan retales.

Un patrón laxo tipo /retal\\w*\\s+(R\\d+)/ casaría con las dos y daría por bueno
cualquier '# Tableros 0'. Por eso son dos extractores separados y con nombre,
y una línea que mencione generación nunca se lee como consumo.

Lo usa checks/checks_inventario.py (C-04) para decidir si un material con 0
tableros declarados tiene derecho a tener PDF de nesting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Verbo/locución de CONSUMO de retal. Tres formas en circulación:
#:   1. "se debe cortar de retal R841" / "se corta del retal"  — verbo explícito
#:   2. "retal utilizado de MDF LACA Blanco"                   — tipo RETAL_UTILIZADO
#:   3. "retal de PLY LAM Pale"                                — tipo RETAL
#: Las dos últimas son el vocabulario que reglas_cnc.yaml ya reconoce como
#: mención de retal para C-60; C-04 usa el mismo para no discrepar de C-60
#: sobre qué es una mención de retal.
_RE_CONSUMO = re.compile(
    r"cort\w*\s+(?:de|del)\s+(?:un\s+)?retal(?:es)?\b"
    r"|retal(?:es)?\s+utilizad[oa]s?\b"
    r"|retal(?:es)?\s+de\b",
    re.IGNORECASE,
)

#: Locución de GENERACIÓN. Se busca en toda la línea, no solo al principio: una
#: línea que hable de retales generados no se lee como consumo aunque también
#: encaje con _RE_CONSUMO. Al no exculpar, el sentido del error se mantiene.
_RE_GENERACION = re.compile(r"\bretal(?:es)?\s+generad[oa]s?\b", re.IGNORECASE)

#: Primera aparición de la palabra 'retal' en la línea: los códigos R### que
#: vengan detrás son retales; los IDs que vengan antes ("La pieza P1 se debe
#: cortar de…") son piezas.
_RE_PALABRA_RETAL = re.compile(r"\bretal(?:es)?\b", re.IGNORECASE)

#: Código de retal: R seguido de dígitos ("R841").
_RE_CODIGO_RETAL = re.compile(r"\bR(\d+)\b", re.IGNORECASE)

#: Token con forma de ID de pieza: "P1", "R2", "M2-P1", "H1-TAP". Mismo
#: vocabulario que el Packing List de la OT (_RE_PL_FILA en extractor_ot).
#: Son candidatos: quien los use debe cruzarlos contra los IDs del DESPIECE.
_RE_ID_PIEZA = re.compile(r"\b([A-Za-z]+\d+-[A-Za-z]+\d*|[A-Za-z]+\d+)\b")


@dataclass(frozen=True)
class RetalConsumido:
    """Una observación CNC que declara cortar una pieza de un retal existente."""

    texto: str                        # línea original, para el mensaje del check
    codigos: tuple[str, ...]          # ("R841",) — vacío si la OT no lo cita
    ids_candidatos: tuple[str, ...]   # tokens con forma de ID de pieza en la línea

    @property
    def codigos_texto(self) -> str:
        """Códigos citados, o '(sin código)' si la observación no da ninguno."""
        return ", ".join(self.codigos) if self.codigos else "(sin código)"


def retales_consumidos(observaciones: list[str]) -> list[RetalConsumido]:
    """Observaciones CNC que declaran CONSUMO de un retal de stock.

    Devuelve una entrada por línea de consumo. `ids_candidatos` son tokens con
    forma de ID de pieza y no se filtran aquí: el DESPIECE es quien decide
    cuáles son piezas reales del proyecto.
    """
    consumos: list[RetalConsumido] = []
    for obs in observaciones:
        if _RE_GENERACION.search(obs):
            continue
        if not _RE_CONSUMO.search(obs):
            continue
        m_retal = _RE_PALABRA_RETAL.search(obs)
        cola = obs[m_retal.end():] if m_retal else ""
        codigos = tuple(
            dict.fromkeys(f"R{m.group(1)}" for m in _RE_CODIGO_RETAL.finditer(cola))
        )
        ids = tuple(
            dict.fromkeys(m.group(1).upper() for m in _RE_ID_PIEZA.finditer(obs))
        )
        consumos.append(RetalConsumido(texto=obs.strip(), codigos=codigos,
                                       ids_candidatos=ids))
    return consumos


def retales_generados(observaciones: list[str]) -> list[str]:
    """Códigos de los retales que el proyecto DEJA al cortar sus tableros.

    Existe para que la distinción consumo/generación sea explícita y testeable:
    ningún código devuelto aquí justifica un '# Tableros 0'.
    """
    codigos: list[str] = []
    for obs in observaciones:
        if not _RE_GENERACION.search(obs):
            continue
        codigos.extend(f"R{m.group(1)}" for m in _RE_CODIGO_RETAL.finditer(obs))
    return list(dict.fromkeys(codigos))
