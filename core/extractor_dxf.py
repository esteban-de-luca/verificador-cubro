"""
core/extractor_dxf.py — Lee ficheros DXF de nesting (encoding CP1252).

Rhinoceros exporta los DXFs en Windows-1252 (CP1252 / ANSI_1252).
El extractor:
  1. Decodifica los bytes con CP1252.
  2. Parsea la sección ENTITIES directamente del texto raw (sin depender
     del sistema de owner-handles de ezdxf, que falla cuando los DXFs
     tienen el campo 330/owner incorrecto).
  3. Usa ezdxf únicamente para los metadatos del fichero (nombre, versión).
  4. Extrae layers, conteos de entidades y IDs de piezas de anotaciones.

La función principal devuelve un DXFDoc por archivo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from core.modelos import DXFDoc


#: Encoding que Rhinoceros usa al exportar DXF.
DXF_ENCODING = "cp1252"

#: Regex para extraer el número de tablero del nombre de archivo (*_T1.dxf).
_RE_TABLERO_NUM = re.compile(r"_T(\d+)\.dxf$", re.IGNORECASE)

#: Regex para el nombre completo del DXF de nesting.
#: Soporta dos formatos:
#:   Antiguo (underscores): EU21822_Sabine_Jennes_PLY_LAMINADO_PALE_T1.dxf
#:   Nuevo (espacios, guión en ID): EU-21247_Daphne Zindili_MDF LACA MARGA_T1.dxf
#: Se ancla en el keyword de material (PLY/MDF) para ser robusto al formato del prefijo.
_RE_NOMBRE_DXF = re.compile(
    r"(PLY|MDF)"
    r"[ _](LAMINADO|LINOLEO|LINÓLEO|LACA|WOOD)"
    r"[ _](.+?)"
    r"(?:_T\d+)?\.dxf$",
    re.IGNORECASE,
)

#: Mapa gama en nombre de archivo → código interno.
_GAMA_ALIAS: dict[str, str] = {
    "LAMINADO": "LAM",
    "LINOLEO": "LIN",
    "LINÓLEO": "LIN",
    "LACA": "LAC",
    "WOOD": "WOO",
}

#: Tipos de entidades que cuentan como "geometría operativa".
_TIPOS_GEOMETRIA = frozenset({
    "LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC",
    "ELLIPSE", "SPLINE", "HATCH", "SOLID", "3DFACE",
})


# ---------------------------------------------------------------------------
# Parsing del nombre de archivo
# ---------------------------------------------------------------------------

def _parsear_nombre(nombre: str) -> tuple[str, str, str, int]:
    """
    Extrae (material, gama, acabado, num_tablero) del nombre del DXF.

    Si el nombre no sigue el patrón exacto, devuelve valores vacíos
    y num_tablero = 0 para que los checks detecten el problema.
    """
    m_num = _RE_TABLERO_NUM.search(nombre)
    num = int(m_num.group(1)) if m_num else 0

    m_nombre = _RE_NOMBRE_DXF.search(nombre)
    if not m_nombre:
        return "", "", "", num

    material = m_nombre.group(1).upper()
    gama_raw = m_nombre.group(2).upper()
    acabado = m_nombre.group(3).replace("_", " ").title()
    gama = _GAMA_ALIAS.get(gama_raw, gama_raw)
    return material, gama, acabado, num


# ---------------------------------------------------------------------------
# Parser raw de la sección ENTITIES
# ---------------------------------------------------------------------------

def _parsear_entities_raw(contenido: str) -> list[dict]:
    """
    Extrae todas las entidades de la sección ENTITIES parseando el texto DXF
    directamente, sin pasar por el sistema de owner-handles de ezdxf.

    Esto es necesario porque Rhinoceros genera DXFs con el campo 330 (owner)
    incorrecto, por lo que ezdxf no asigna las entidades al modelspace y
    doc.modelspace() devuelve 0 entidades.

    Devuelve una lista de dicts con al menos 'tipo' (str) y 'layer' (str).
    Para TEXT/MTEXT también incluye 'texto' (str).
    """
    lineas = contenido.splitlines()
    n = len(lineas)

    # Localizar inicio y fin de la sección ENTITIES
    inicio = fin = -1
    i = 0
    while i < n - 3:
        if (lineas[i].strip() == "0" and lineas[i + 1].strip() == "SECTION"
                and lineas[i + 2].strip() == "2" and lineas[i + 3].strip() == "ENTITIES"):
            inicio = i + 4
            break
        i += 1
    if inicio == -1:
        return []

    i = inicio
    while i < n - 1:
        if lineas[i].strip() == "0" and lineas[i + 1].strip() == "ENDSEC":
            fin = i
            break
        i += 1
    if fin == -1:
        fin = n

    # Recorrer la sección par a par (código, valor)
    entidades: list[dict] = []
    ent_actual: dict | None = None
    i = inicio
    while i < fin - 1:
        codigo_str = lineas[i].strip()
        valor = lineas[i + 1].strip()
        i += 2
        try:
            codigo = int(codigo_str)
        except ValueError:
            continue

        if codigo == 0:
            if ent_actual is not None:
                entidades.append(ent_actual)
            # VERTEX y SEQEND son subentidades de POLYLINE; las ignoramos
            if valor in ("VERTEX", "SEQEND", "ENDSEC"):
                ent_actual = None
            else:
                ent_actual = {"tipo": valor, "layer": "0", "texto": "",
                              "x": None, "y": None, "r": None}
        elif ent_actual is not None:
            if codigo == 8:    # layer
                ent_actual["layer"] = valor
            elif codigo == 1:  # texto primario (TEXT / MTEXT)
                ent_actual["texto"] = valor
            elif codigo == 10:  # coordenada X (CIRCLE, ARC…)
                try:
                    ent_actual["x"] = float(valor)
                except ValueError:
                    pass
            elif codigo == 20:  # coordenada Y
                try:
                    ent_actual["y"] = float(valor)
                except ValueError:
                    pass
            elif codigo == 40:  # radio (CIRCLE) o primera magnitud
                try:
                    ent_actual["r"] = float(valor)
                except ValueError:
                    pass

    if ent_actual is not None:
        entidades.append(ent_actual)

    return entidades


# ---------------------------------------------------------------------------
# Extracción de layers y conteos
# ---------------------------------------------------------------------------

def _extraer_layers_y_conteos(
    entidades: list[dict],
) -> tuple[set[str], set[str], dict[str, int]]:
    """
    A partir de la lista de entidades raw devuelve:
      - layers: layers con al menos una entidad
      - layers_con_geometria: layers con al menos una entidad de geometría operativa
      - conteos_layer: {layer: nº entidades de geometría}
    """
    layers: set[str] = set()
    layers_con_geometria: set[str] = set()
    conteos_layer: dict[str, int] = {}

    for ent in entidades:
        tipo = ent["tipo"]
        layer = ent["layer"]
        layers.add(layer)
        if tipo in _TIPOS_GEOMETRIA:
            layers_con_geometria.add(layer)
            conteos_layer[layer] = conteos_layer.get(layer, 0) + 1

    return layers, layers_con_geometria, conteos_layer


def _extraer_circulos(entidades: list[dict]) -> list[dict]:
    """
    Devuelve los círculos con coordenadas válidas para checks geométricos (C-44).
    Cada entrada: {'layer': str, 'x': float, 'y': float, 'r': float}.
    """
    return [
        {"layer": e["layer"], "x": e["x"], "y": e["y"], "r": e["r"]}
        for e in entidades
        if e["tipo"] == "CIRCLE"
        and e.get("x") is not None
        and e.get("y") is not None
        and e.get("r") is not None
    ]


def _extraer_ids_piezas(entidades: list[dict]) -> list[str]:
    """
    Extrae IDs de piezas del layer 0_ANOTACIONES.
    En los DXFs de CUBRO las anotaciones son entidades TEXT o MTEXT con
    el formato: 'dimensiones / ID_PIEZA' (ej. '598x798 / M6-P1').
    """
    patron = re.compile(
        r"(?:^|[/\s])\s*"         # separador o inicio
        r"((?:M\d+-[A-Za-z]+\d+)" # M2-P1, M4-PL1, M1-T1
        r"|(?:[ERBH]\d+))",        # E1, R2, B3, H1
        re.IGNORECASE,
    )
    ids: list[str] = []
    for ent in entidades:
        if ent["tipo"] not in ("TEXT", "MTEXT"):
            continue
        if ent["layer"].upper() not in ("0_ANOTACIONES", "ANOTACIONES"):
            continue
        for m in patron.finditer(ent["texto"]):
            ids.append(m.group(1).upper())
    return ids


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def leer_dxf(origen: BinaryIO | Path | str, nombre: str | None = None) -> DXFDoc:
    """
    Lee un archivo DXF y devuelve un DXFDoc.

    Args:
        origen: BytesIO desde Drive, Path o str con ruta de archivo.
        nombre: nombre del archivo (para extraer material/tablero del nombre).
                Si origen es Path, se infiere automáticamente.

    Returns:
        DXFDoc con layers, conteos y IDs de piezas.
    """
    if isinstance(origen, (str, Path)):
        origen = Path(origen)
        if nombre is None:
            nombre = origen.name
        raw = origen.read_bytes()
    else:
        raw = origen.read()

    nombre = nombre or "desconocido.dxf"
    contenido = raw.decode(DXF_ENCODING, errors="replace")

    material, gama, acabado, num = _parsear_nombre(nombre)
    entidades = _parsear_entities_raw(contenido)
    layers, layers_con_geometria, conteos_layer = _extraer_layers_y_conteos(entidades)
    ids_piezas = _extraer_ids_piezas(entidades)
    circulos = _extraer_circulos(entidades)

    return DXFDoc(
        nombre=nombre,
        tablero_num=num,
        material=material,
        gama=gama,
        acabado=acabado,
        layers=layers,
        layers_con_geometria=layers_con_geometria,
        conteos_layer=conteos_layer,
        ids_piezas=ids_piezas,
        circulos=circulos,
    )


def leer_todos_dxf(
    origenes: dict[str, BinaryIO] | list[Path | str],
) -> list[DXFDoc]:
    """
    Lee múltiples DXFs y devuelve la lista de DXFDoc ordenada por tablero_num.

    Args:
        origenes: dict {nombre: BytesIO} (desde drive/descargador) o
                  lista de Paths/strings (para tests locales).
    """
    docs: list[DXFDoc] = []
    if isinstance(origenes, dict):
        for nombre, bytesio in origenes.items():
            if nombre.lower().endswith(".dxf"):
                docs.append(leer_dxf(bytesio, nombre=nombre))
    else:
        for ruta in origenes:
            docs.append(leer_dxf(ruta))

    docs.sort(key=lambda d: (d.nombre, d.tablero_num))
    return docs
