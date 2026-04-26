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

#: Layers que delimitan el contorno de una pieza individual en el nesting.
#: Usado por C-44 (distancia bisagras) para asociar cada cazoleta a su pieza.
#: - 10_12-CUTEXT-EM5-Z18 → estándar (PLY/MDF)
#: - 10_12-CONTORNO LACA  → MDF LAC con acabados no estándar (Agave, etc.)
LAYERS_CONTORNO_PIEZA = frozenset({
    "10_12-CUTEXT-EM5-Z18",
    "10_12-CONTORNO LACA",
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
    Para POLYLINE/LWPOLYLINE incluye 'vertices' (list[tuple[float, float]]).
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
    #
    # Tres estados simultáneos:
    #   cur  → entidad simple actualmente abierta (CIRCLE, TEXT, LWPOLYLINE…)
    #   poly → POLYLINE compuesto con vértices via VERTEX (cerrado por SEQEND)
    #   vert → VERTEX en curso dentro de poly
    # LWPOLYLINE es una entidad simple "auto-contenida": acumula sus vértices
    # como múltiples pares (10, 20) dentro del mismo bloque.
    entidades: list[dict] = []
    cur: dict | None = None
    poly: dict | None = None
    vert: dict | None = None
    lw_x: float | None = None  # X pendiente de LWPOLYLINE esperando su Y

    def _nuevo_simple(tipo: str) -> dict:
        return {"tipo": tipo, "layer": "0", "texto": "",
                "x": None, "y": None, "r": None, "vertices": [],
                "extrusion_z": 1.0}

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
            # Cerrar lo que estuviera abierto
            if vert is not None:
                if vert["x"] is not None and vert["y"] is not None and poly is not None:
                    poly["vertices"].append((vert["x"], vert["y"]))
                vert = None
            elif cur is not None and poly is None:
                entidades.append(cur)
                cur = None

            # Abrir nueva entidad según su tipo
            if valor == "POLYLINE":
                if poly is not None:  # POLYLINE no cerrado: forzar cierre
                    entidades.append(poly)
                poly = _nuevo_simple("POLYLINE")
                cur = None
                lw_x = None
            elif valor == "VERTEX":
                if poly is not None:
                    vert = {"x": None, "y": None}
                # VERTEX huérfano fuera de POLYLINE: ignorar
            elif valor == "SEQEND":
                if poly is not None:
                    entidades.append(poly)
                    poly = None
            elif valor == "ENDSEC":
                if poly is not None:
                    entidades.append(poly)
                    poly = None
                if cur is not None:
                    entidades.append(cur)
                    cur = None
                break
            elif valor == "LWPOLYLINE":
                if poly is not None:
                    entidades.append(poly)
                    poly = None
                cur = _nuevo_simple("LWPOLYLINE")
                lw_x = None
            else:
                if poly is not None:  # SEQEND faltante: cerrar y seguir
                    entidades.append(poly)
                    poly = None
                cur = _nuevo_simple(valor)
                lw_x = None
        else:
            # Group code dentro de una entidad
            if vert is not None:
                if codigo == 10:
                    try: vert["x"] = float(valor)
                    except ValueError: pass
                elif codigo == 20:
                    try: vert["y"] = float(valor)
                    except ValueError: pass
            elif poly is not None:
                if codigo == 8:
                    poly["layer"] = valor
                elif codigo == 230:  # Z de la dirección de extrusión
                    try: poly["extrusion_z"] = float(valor)
                    except ValueError: pass
                # codes 66/70: flags, ignoramos
            elif cur is not None:
                if codigo == 8:
                    cur["layer"] = valor
                elif codigo == 1:
                    cur["texto"] = valor
                elif codigo == 10:
                    if cur["tipo"] == "LWPOLYLINE":
                        try: lw_x = float(valor)
                        except ValueError: lw_x = None
                    else:
                        try: cur["x"] = float(valor)
                        except ValueError: pass
                elif codigo == 20:
                    if cur["tipo"] == "LWPOLYLINE":
                        if lw_x is not None:
                            try:
                                cur["vertices"].append((lw_x, float(valor)))
                            except ValueError:
                                pass
                            lw_x = None
                    else:
                        try: cur["y"] = float(valor)
                        except ValueError: pass
                elif codigo == 40:
                    try: cur["r"] = float(valor)
                    except ValueError: pass
                elif codigo == 230:  # Z de la dirección de extrusión
                    # 230=-1.0 → entidad reflejada (típicamente representación
                    # de cara trasera para mecanizado a doble cara). El check
                    # C-44 ignora estos duplicados.
                    try: cur["extrusion_z"] = float(valor)
                    except ValueError: pass

    # Cierre final por seguridad (DXFs sin ENDSEC explícito)
    if vert is not None and poly is not None:
        if vert["x"] is not None and vert["y"] is not None:
            poly["vertices"].append((vert["x"], vert["y"]))
    if poly is not None:
        entidades.append(poly)
    elif cur is not None:
        entidades.append(cur)

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


def _aplicar_extrusion_wcs(x: float, y: float, extrusion_z: float) -> tuple[float, float]:
    """
    Convierte coordenadas OCS (Object Coord System) a WCS (World Coord System)
    aplicando el Arbitrary Axis Algorithm del DXF.

    Cuando una entidad 2D tiene dirección de extrusión Z = -1 (group code 230),
    su sistema local está espejado respecto al WCS y la transformación es
    X → -X, Y → Y. CUBRO usa esto para representar piezas de la cara trasera
    en el mismo nesting (no son duplicados — son piezas reales en otra parte
    del tablero).
    """
    if extrusion_z < 0:
        return -x, y
    return x, y


def _extraer_circulos(entidades: list[dict]) -> list[dict]:
    """
    Devuelve los círculos con coordenadas válidas para checks geométricos (C-44).
    Cada entrada: {'layer': str, 'x': float, 'y': float, 'r': float}.

    Las coordenadas se convierten al sistema WCS aplicando el Arbitrary Axis
    Algorithm: si extrusion_z = -1, X se invierte (X → -X). Esto hace que las
    cazoletas de piezas en la "cara trasera" del nesting aparezcan en su
    posición física correcta y se asocien al CUTEXT de su pieza.
    """
    out: list[dict] = []
    for e in entidades:
        if e["tipo"] != "CIRCLE":
            continue
        if e.get("x") is None or e.get("y") is None or e.get("r") is None:
            continue
        x, y = _aplicar_extrusion_wcs(e["x"], e["y"], e.get("extrusion_z", 1.0))
        out.append({"layer": e["layer"], "x": x, "y": y, "r": e["r"]})
    return out


def _extraer_contornos_pieza(
    entidades: list[dict],
    layers_contorno: frozenset[str] = LAYERS_CONTORNO_PIEZA,
) -> list[dict]:
    """
    Extrae bounding boxes de las polilíneas que delimitan piezas individuales.

    Cada pieza nesteada en el tablero está rodeada por una POLYLINE o
    LWPOLYLINE en una de las layers de contorno. Para C-44 solo necesitamos
    el rectángulo envolvente (xmin, xmax, ymin, ymax) — las piezas son
    rectangulares y la cazoleta debe caer dentro de ese rectángulo para
    pertenecer a la pieza.

    Si la polilínea tiene extrusion_z = -1 (cara trasera), se aplica la
    transformación X → -X a los vértices antes de calcular el bbox.

    Cada entrada devuelta: {'layer', 'xmin', 'xmax', 'ymin', 'ymax'}.
    """
    contornos: list[dict] = []
    for e in entidades:
        if e["tipo"] not in ("POLYLINE", "LWPOLYLINE"):
            continue
        if e["layer"] not in layers_contorno:
            continue
        vertices = e.get("vertices") or []
        if not vertices:
            continue
        ez = e.get("extrusion_z", 1.0)
        vertices_wcs = [_aplicar_extrusion_wcs(vx, vy, ez) for vx, vy in vertices]
        xs = [v[0] for v in vertices_wcs]
        ys = [v[1] for v in vertices_wcs]
        contornos.append({
            "layer": e["layer"],
            "xmin": min(xs),
            "xmax": max(xs),
            "ymin": min(ys),
            "ymax": max(ys),
        })
    return contornos


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
    piezas_contorno = _extraer_contornos_pieza(entidades)

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
        piezas_contorno=piezas_contorno,
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
