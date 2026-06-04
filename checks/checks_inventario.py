"""
checks/checks_inventario.py — C-00 a C-04: Inventario y nomenclatura de archivos.

Parámetros de entrada:
    nombres_archivos: list[str]  — todos los nombres de archivo en la carpeta del proyecto
    piezas: list[Pieza]          — del DESPIECE (para C-04)
    dxfs: list[DXFDoc]           — DXFs parseados (para C-03)
    ot: OTData                   — OT parseada (para C-03)
    id_proyecto: str             — ID esperado del proyecto (para C-01)
    reglas: dict                 — cargado por reglas_loader (para C-00, C-02)
"""

from __future__ import annotations

import fnmatch
import re

from core.modelos import CheckResult, DXFDoc, ExtraccionData, OTData, Pieza
from checks._helpers import (
    _pass, _fail, _warn, _skip, _resultado, _norm_id, _id_coincide_proyecto,
    _RE_INC_SUFIJO,
)

_GRUPO = "Inventario"

# ---------------------------------------------------------------------------
# C-00: Documentos obligatorios presentes
# ---------------------------------------------------------------------------

def check_documentos_presentes(nombres_archivos: list[str], reglas: dict) -> CheckResult:
    """
    C-00: DESPIECE, ETIQUETAS, EAN LOGISTIC y EXTRACCION deben estar presentes.
    Bloquea: Sí.
    """
    patrones = reglas["nomenclatura"]["patrones"]
    ean_patrones = [patrones["ean"]] + ([patrones["ean_alt"]] if "ean_alt" in patrones else [])
    obligatorios = {
        "DESPIECE": [patrones["despiece"]],
        "ETIQUETAS": [patrones["etiquetas"]],
        "EAN LOGISTIC": ean_patrones,
        "EXTRACCION": [patrones.get("extraccion", "EXTRACCION_*")],
    }
    faltantes = []
    for nombre_doc, lista_patrones in obligatorios.items():
        encontrado = any(
            fnmatch.fnmatch(n.upper(), p.upper())
            for n in nombres_archivos
            for p in lista_patrones
        )
        if not encontrado:
            faltantes.append(nombre_doc)

    if faltantes:
        archivos_encontrados = ", ".join(nombres_archivos) if nombres_archivos else "(ninguno)"
        detalle = (
            f"Faltan: {'; '.join(faltantes)}. "
            f"Archivos en carpeta: {archivos_encontrados}"
        )
        return _fail("C-00", "Documentos obligatorios presentes", detalle, True, _GRUPO)

    return _resultado("C-00", "Documentos obligatorios presentes", faltantes, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-01: ID de proyecto consistente en todos los archivos
# ---------------------------------------------------------------------------

# Formatos de ID aceptados:
#   - EU/SP + 5 dígitos (con o sin guion), opcional sufijo -INC / _INC[N]
#   - 4 dígitos sin prefijo, siempre seguido de '_' (proyectos tipo "4302_cliente_…")
# Lookbehind y lookahead evitan matchear dentro de números más largos (ej. EU22780
# no genera un match de '2278'; un nombre con 5 dígitos numéricos no se confunde
# con un ID de 4).
_RE_ID_ARCHIVO = re.compile(
    r"(?<![A-Za-z0-9])((?:EU|SP)-?\d{5}(?:[-_]INC\d*)?|\d{4}(?=_))",
    re.IGNORECASE,
)


def _ids_internos(
    ot: OTData | None,
    extraccion: ExtraccionData | None,
    filas_ean: list | None,
) -> list[tuple[str, str]]:
    """IDs de proyecto declarados DENTRO del contenido de los documentos.

    Devuelve [(fuente, id_crudo)] — el ID tal como aparece dentro de la OT,
    el EXTRACCION y el EAN (este último embebido en el ID de bulto). Orden:
    OT, EXTRACCION, EAN (la OT es la fuente preferida para el ID a mostrar).
    """
    internos: list[tuple[str, str]] = []
    if ot is not None and getattr(ot, "id_proyecto", ""):
        internos.append(("OT", ot.id_proyecto))
    if extraccion is not None and getattr(extraccion, "id_proyecto", ""):
        internos.append(("EXTRACCION", extraccion.id_proyecto))
    if filas_ean:
        for f in filas_ean:
            m = _RE_ID_ARCHIVO.search(getattr(f, "id_bulto", "") or "")
            if m:
                internos.append(("EAN", m.group(1)))
                break  # un bulto representativo basta
    return internos


def _id_real_segun_contenido(
    internos: list[tuple[str, str]],
    id_norm: str,
) -> tuple[str, list[str]] | None:
    """Detecta el caso 'la carpeta/nombres dicen una incidencia, pero el
    contenido dice otra'.

    Si TODOS los documentos cuyo contenido comparte la base del proyecto
    esperado declaran, de forma unánime, un ID con DISTINTA incidencia, lo
    devuelve como (id_a_mostrar, [fuentes]). Si no hay unanimidad o el
    contenido coincide con lo esperado, devuelve None (no se afirma nada).
    """
    base_esperado = _RE_INC_SUFIJO.sub("", id_norm)
    base_internos = [
        (fuente, _norm_id(raw), raw)
        for fuente, raw in internos
        if _RE_INC_SUFIJO.sub("", _norm_id(raw)) == base_esperado
    ]
    if not base_internos:
        return None
    norms = {norm for _, norm, _ in base_internos}
    if len(norms) != 1:
        return None  # los documentos internos no se ponen de acuerdo
    (norm_real,) = norms
    if norm_real == id_norm:
        return None  # el contenido coincide con lo esperado
    # ID a mostrar: el primer crudo (OT preferida); normaliza '_INC' → '-INC'.
    raw_real = base_internos[0][2].replace("_INC", "-INC")
    fuentes = sorted({fuente for fuente, _, _ in base_internos})
    return raw_real, fuentes


def check_id_consistente(
    nombres_archivos: list[str],
    id_proyecto: str,
    ot: OTData | None = None,
    extraccion: ExtraccionData | None = None,
    filas_ean: list | None = None,
) -> CheckResult:
    """
    C-01: Todos los archivos que contienen un ID de proyecto usan el mismo.

    En proyectos de incidencia (sufijo -INC), algunos archivos —típicamente el
    EAN LOGISTIC— se nombran con el ID base del producto original (sin -INC),
    porque la logística/EAN se hereda del proyecto base. Ese ID base se acepta
    como consistente con el ID de la incidencia (p. ej. 'SP-20594' en un
    proyecto 'SP-20594-INC').

    Además de los NOMBRES de archivo, compara la incidencia con el ID declarado
    DENTRO de los documentos (OT, EXTRACCION, EAN). Cuando el contenido apunta
    unánimemente a otra incidencia que la esperada, el problema no es el archivo
    señalado sino el ID del proyecto: en ese caso indica cuál es la incidencia
    real y qué renombrar, en vez de listar discrepancias de nombre.
    Bloquea: Sí.
    """
    id_norm = _norm_id(id_proyecto)
    DESC = "ID proyecto consistente en todos los archivos"

    # ¿El contenido interno revela que la incidencia real es otra?
    real = _id_real_segun_contenido(_ids_internos(ot, extraccion, filas_ean), id_norm)
    if real is not None:
        raw_real, fuentes = real
        norm_real = _norm_id(raw_real)
        mal_nombrados = []
        for nombre in nombres_archivos:
            if any(_norm_id(m.group(1)) != norm_real
                   for m in _RE_ID_ARCHIVO.finditer(nombre)):
                mal_nombrados.append(nombre)
        detalle = (
            f"El contenido de los documentos declara el proyecto como "
            f"'{raw_real}' (según {', '.join(fuentes)}), pero la carpeta/ID "
            f"esperado es '{id_proyecto}'. El proyecto es realmente {raw_real}: "
            f"corrige el ID de la carpeta"
            + (f" y el nombre de: {', '.join(mal_nombrados)}" if mal_nombrados else "")
            + " para que todo use la misma incidencia."
        )
        return _fail("C-01", DESC, detalle, True, _GRUPO)

    # Comportamiento estándar: consistencia por nombre de archivo.
    errores = []
    for nombre in nombres_archivos:
        for m in _RE_ID_ARCHIVO.finditer(nombre):
            if not _id_coincide_proyecto(_norm_id(m.group(1)), id_norm):
                errores.append(f"{nombre}: ID encontrado '{m.group(1)}' ≠ '{id_proyecto}'")
    return _resultado("C-01", DESC, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-02: Nomenclatura sigue el patrón definido
# ---------------------------------------------------------------------------

def check_nomenclatura(nombres_archivos: list[str], reglas: dict) -> CheckResult:
    """
    C-02: Cada archivo debe coincidir con al menos un patrón conocido.

    Los archivos no reconocidos generan SKIP (informativo, no bloquea ni
    alerta) — la lista de patrones cubre los archivos del fichero de corte
    estándar, y otros archivos auxiliares (planos, alzados, dossiers de
    diseño, anotaciones internas) son válidos pero no entran en el check.
    """
    DESC = "Nomenclatura sigue el patrón definido"
    patrones = reglas["nomenclatura"]["patrones"]
    todos_patrones = list(patrones.values())

    no_reconocidos = []
    for nombre in nombres_archivos:
        reconocido = any(
            fnmatch.fnmatch(nombre.upper(), p.upper()) for p in todos_patrones
        )
        if not reconocido:
            no_reconocidos.append(nombre)

    if not no_reconocidos:
        return _pass("C-02", DESC, False, _GRUPO)

    n = len(no_reconocidos)
    detalle = "; ".join(no_reconocidos[:5])
    if n > 5:
        detalle += f" (y {n - 5} más)"
    return _skip("C-02", DESC, detalle, _GRUPO)


# ---------------------------------------------------------------------------
# C-03: Nº de DXFs == nº tableros declarados en OT
# ---------------------------------------------------------------------------

def check_num_dxf_vs_ot(dxfs: list[DXFDoc], ot: OTData) -> CheckResult:
    """
    C-03: Número de DXFs tableros (_T[N].dxf) == nº tableros declarados en OT.

    FAIL si:
      - falta '# Tableros' de algún material en INFORMACION DE CORTE
      - falta 'Cantidad de tableros' en la cabecera INFORMACION DE ENVIO
      - el nº de DXFs no coincide con los tableros declarados
    Bloquea: Sí.
    """
    errores: list[str] = []

    if ot.materiales_sin_cantidad:
        errores.append(
            "Falta '# Tableros' en INFORMACION DE CORTE para: "
            + ", ".join(ot.materiales_sin_cantidad)
        )

    if ot.num_tableros_total is None and not ot.tableros:
        errores.append(
            "Falta 'Cantidad de tableros' en cabecera INFORMACION DE ENVIO "
            "y '# Tableros' en INFORMACION DE CORTE"
        )
    elif ot.num_tableros_total is None:
        errores.append("Falta 'Cantidad de tableros' en cabecera INFORMACION DE ENVIO")

    if errores:
        return _fail("C-03", "Nº DXFs == nº tableros OT",
                     " | ".join(errores), True, _GRUPO)

    # Referencia para comparar con DXFs: total de cabecera si existe, si no suma por material.
    total_ot = ot.num_tableros_total if ot.num_tableros_total is not None else sum(ot.tableros.values())
    # Excluir DXFs cortados de retal — no son tableros nuevos, sino reutilización de sobrante.
    n_dxf = sum(
        1 for d in dxfs
        if not any("retal" in l.lower() and "utilizado" in l.lower() for l in d.layers)
    )
    if n_dxf == total_ot:
        return _pass("C-03", "Nº DXFs == nº tableros OT", True, _GRUPO)
    return _fail(
        "C-03", "Nº DXFs == nº tableros OT",
        f"DXFs presentes: {n_dxf} | OT declara: {total_ot}",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-04: Nº PDFs nesting == combinaciones únicas material+gama+acabado
# ---------------------------------------------------------------------------

# Formatos de PDF nesting aceptados:
#   - EU/SP/C[1-5] + dígitos (con o sin guion) en cualquier posición
#   - 4 dígitos sin prefijo SOLO al inicio del nombre y seguidos de '_'
#     (evita falsos positivos con dimensiones u otros números embebidos).
_RE_NESTING_PDF = re.compile(
    r"(?:(?:EU|SP|C[1-5])-?\d+|^\d{4}_).*?(PLY|MDF).*?\.pdf$",
    re.IGNORECASE,
)


def check_pdfs_nesting_vs_materiales(
    nombres_archivos: list[str],
    piezas: list[Pieza],
    ot: OTData | None = None,
) -> CheckResult:
    """
    C-04: Debe haber un PDF de nesting por cada combinación única
    material+gama+acabado presente en el DESPIECE.

    Cuando la OT declara 'Cantidad de tableros: 0' significa que el proyecto
    se corta de retal (típico en incidencias P1/P2 con una sola pieza), no
    hay nesting que generar y el check SKIPea.

    Bloquea: Sí.
    """
    desc = "PDFs nesting == combinaciones material DESPIECE"
    if not piezas:
        return _skip("C-04", desc, "DESPIECE sin piezas", _GRUPO)
    if ot is not None and ot.num_tableros_total == 0:
        return _skip(
            "C-04", desc,
            "OT declara 0 tableros (proyecto cortado de retal)",
            _GRUPO,
        )

    combos_esperados = {p.clave_material for p in piezas}
    n_pdfs_nesting = sum(
        1 for n in nombres_archivos
        if n.lower().endswith(".pdf") and _RE_NESTING_PDF.search(n)
    )
    n_esperado = len(combos_esperados)

    if n_pdfs_nesting == n_esperado:
        return _pass("C-04", desc, True, _GRUPO)

    return _fail(
        "C-04", desc,
        f"PDFs nesting detectados: {n_pdfs_nesting} | Combinaciones DESPIECE: {n_esperado} "
        f"({', '.join(sorted(combos_esperados))})",
        True, _GRUPO,
    )
