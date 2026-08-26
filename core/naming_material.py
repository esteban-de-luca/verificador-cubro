"""
core/naming_material.py — Material+gama+acabado en nombres de archivo.

Los archivos de nesting de un proyecto llevan en el nombre el tablero del que
salen: 'EU21868INC_Philip_Gregoire_MDF_WOOD_ROBLE.pdf'. Tanto los DXF (uno por
tablero) como los PDF de nesting siguen ese patrón, así que el vocabulario vive
aquí y lo comparten:

  - core/extractor_dxf.py     — parsea material/gama/acabado de cada DXF
  - checks/checks_inventario.py — C-04, cruza los PDF de nesting con el DESPIECE
  - checks/checks_dxf.py      — reconstruye la etiqueta legible del tablero
"""

from __future__ import annotations

import re
import unicodedata

#: Mapa gama tal como aparece en el nombre de archivo → código interno.
GAMA_ALIAS: dict[str, str] = {
    "LAMINADO": "LAM",
    "LINOLEO": "LIN",
    "LINÓLEO": "LIN",
    "LACA": "LAC",
    "WOOD": "WOO",
}

#: Inverso de GAMA_ALIAS: código interno → palabra del nombre de archivo. Sirve
#: para mostrar el tablero al equipo igual que aparece en Drive ("MDF WOOD
#: ROBLE"). 'LINOLEO' es la grafía sin acento, la que usan los nombres.
GAMA_DISPLAY: dict[str, str] = {"LAM": "LAMINADO", "LIN": "LINOLEO",
                                "LAC": "LACA", "WOO": "WOOD"}

#: Patrón material+gama+acabado dentro de un nombre de archivo. Se ancla en el
#: keyword de material (PLY/MDF) para ser robusto al formato del prefijo, y
#: acepta los dos separadores en uso:
#:   underscores: EU21822_Sabine_Jennes_PLY_LAMINADO_PALE_T1.dxf
#:   espacios:    EU-21247_Daphne Zindili_MDF LACA MARGA_T1.dxf
#: El sufijo _TN es opcional: los DXF van por tablero, los PDF de nesting no
#: siempre.
#: La gama admite la palabra completa ('LAMINADO') y el código interno ('LAM'),
#: porque ambas grafías circulan en los nombres. Las alternativas van de más
#: larga a más corta para que 'LAMINADO' no se consuma como 'LAM'.
_RE_MATERIAL = re.compile(
    r"(PLY|MDF)"
    r"[ _](LAMINADO|LINÓLEO|LINOLEO|LACA|WOOD|LAM|LIN|LAC|WOO)"
    r"[ _](.+?)"
    r"(?:[ _]T\d+)?\.(?:dxf|pdf)$",
    re.IGNORECASE,
)


def parsear_material(nombre: str) -> tuple[str, str, str] | None:
    """(material, gama, acabado) del nombre de archivo, o None si no encaja."""
    m = _RE_MATERIAL.search(nombre)
    if m is None:
        return None
    gama_raw = m.group(2).upper()
    return (
        m.group(1).upper(),
        GAMA_ALIAS.get(gama_raw, gama_raw),
        m.group(3).replace("_", " ").title(),
    )


def norm_acabado(acabado: str) -> str:
    """Forma canónica de un acabado, para comparar entre fuentes distintas.

    Un nombre de archivo puede perder los acentos ('CADAQUES' por 'Cadaqués') y
    usar cualquier separador ('ROSA_BABY', 'ROSA-BABY', 'Rosa baby'), mientras
    el DESPIECE escribe la forma de catálogo. La comparación ignora acentos,
    mayúsculas y separadores para que esas variantes no cuenten como acabados
    distintos.
    """
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", acabado)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[\s_-]+", "", sin_acentos).casefold()


def clave_comparable(material: str, gama: str, acabado: str) -> str:
    """Clave material+gama+acabado normalizada para cruzar entre fuentes.

    Equivalente a Pieza.clave_material pero tolerante a las variantes de
    grafía del acabado descritas en norm_acabado().
    """
    return f"{material.upper()}_{gama.upper()}_{norm_acabado(acabado)}"
