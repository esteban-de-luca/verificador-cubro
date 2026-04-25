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

from core.modelos import CheckResult, DXFDoc, OTData, Pieza
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO = "Inventario"

# ---------------------------------------------------------------------------
# C-00: Documentos obligatorios presentes
# ---------------------------------------------------------------------------

def check_documentos_presentes(nombres_archivos: list[str], reglas: dict) -> CheckResult:
    """
    C-00: DESPIECE, ETIQUETAS y EAN LOGISTIC deben estar presentes.
    Bloquea: Sí.
    """
    patrones = reglas["nomenclatura"]["patrones"]
    ean_patrones = [patrones["ean"]] + ([patrones["ean_alt"]] if "ean_alt" in patrones else [])
    obligatorios = {
        "DESPIECE": [patrones["despiece"]],
        "ETIQUETAS": [patrones["etiquetas"]],
        "EAN LOGISTIC": ean_patrones,
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

_RE_ID_ARCHIVO = re.compile(r"(?<![A-Za-z])((?:EU|SP)-?\d{5}(?:-INC)?)", re.IGNORECASE)


def check_id_consistente(nombres_archivos: list[str], id_proyecto: str) -> CheckResult:
    """
    C-01: Todos los archivos que contienen un ID de proyecto usan el mismo.
    Bloquea: Sí.
    """
    id_norm = id_proyecto.upper().replace("-", "")
    errores = []
    for nombre in nombres_archivos:
        for m in _RE_ID_ARCHIVO.finditer(nombre):
            id_en_archivo = m.group(1).upper().replace("-", "")
            if id_en_archivo != id_norm:
                errores.append(f"{nombre}: ID encontrado '{m.group(1)}' ≠ '{id_proyecto}'")
    return _resultado("C-01", "ID proyecto consistente en todos los archivos", errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-02: Nomenclatura sigue el patrón definido
# ---------------------------------------------------------------------------

def check_nomenclatura(nombres_archivos: list[str], reglas: dict) -> CheckResult:
    """
    C-02: Cada archivo debe coincidir con al menos un patrón conocido.
    Los archivos no reconocidos generan WARN (no bloquea).
    """
    patrones = reglas["nomenclatura"]["patrones"]
    todos_patrones = list(patrones.values())

    no_reconocidos = []
    for nombre in nombres_archivos:
        reconocido = any(
            fnmatch.fnmatch(nombre.upper(), p.upper()) for p in todos_patrones
        )
        if not reconocido:
            no_reconocidos.append(nombre)

    return _resultado(
        "C-02", "Nomenclatura sigue el patrón definido",
        no_reconocidos, False, _GRUPO, tipo_fail="WARN",
    )


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

_RE_NESTING_PDF = re.compile(
    r"(?:EU|SP)-?\d+.*?(PLY|MDF).*?\.pdf$", re.IGNORECASE
)


def check_pdfs_nesting_vs_materiales(
    nombres_archivos: list[str], piezas: list[Pieza]
) -> CheckResult:
    """
    C-04: Debe haber un PDF de nesting por cada combinación única
    material+gama+acabado presente en el DESPIECE.
    Bloquea: Sí.
    """
    if not piezas:
        return _skip("C-04", "PDFs nesting == combinaciones material DESPIECE",
                     "DESPIECE sin piezas", _GRUPO)

    combos_esperados = {p.clave_material for p in piezas}
    n_pdfs_nesting = sum(
        1 for n in nombres_archivos
        if n.lower().endswith(".pdf") and _RE_NESTING_PDF.search(n)
    )
    n_esperado = len(combos_esperados)

    if n_pdfs_nesting == n_esperado:
        return _pass("C-04", "PDFs nesting == combinaciones material DESPIECE", True, _GRUPO)

    return _fail(
        "C-04", "PDFs nesting == combinaciones material DESPIECE",
        f"PDFs nesting detectados: {n_pdfs_nesting} | Combinaciones DESPIECE: {n_esperado} "
        f"({', '.join(sorted(combos_esperados))})",
        True, _GRUPO,
    )
