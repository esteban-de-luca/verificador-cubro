"""
core/extractor_despiece.py — Lee el DESPIECE (XLSX) desde BytesIO.

El DESPIECE es la fuente de verdad de todas las piezas del proyecto.
Acepta tanto BytesIO (desde Drive) como Path (para tests locales).
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO

import openpyxl

from core.modelos import Pieza


# ---------------------------------------------------------------------------
# Mapeo de nombres de columna normalizados → nombres internos
# El XLSX puede usar variantes de mayúsculas/minúsculas y tildes.
# ---------------------------------------------------------------------------

_ALIAS_COLUMNAS: dict[str, str] = {
    # ID de pieza
    "id": "id",
    "referencia": "id",
    "pieza": "id",
    "id pieza": "id",
    # Dimensiones
    "ancho": "ancho",
    "anchura": "ancho",
    "alto": "alto",
    "altura": "alto",
    # Material
    "material": "material",
    # Gama
    "gama": "gama",
    # Acabado
    "acabado": "acabado",
    "finish": "acabado",
    # Tipología
    "tipologia": "tipologia",
    "tipología": "tipologia",
    "tipo": "tipologia",
    # Mecanizado
    "mecanizado": "mecanizado",
    "mec": "mecanizado",
    "mecanizados": "mecanizado",
    # Tirador
    "tirador": "tirador",
    "modelo tirador": "tirador",
    "handle": "tirador",
    # Posición tirador
    "posicion tirador": "posicion_tirador",
    "posición tirador": "posicion_tirador",
    "posicion de tirador": "posicion_tirador",
    "posición de tirador": "posicion_tirador",
    "pos tirador": "posicion_tirador",
    "pos. tirador": "posicion_tirador",
    "posicion": "posicion_tirador",
    "posición": "posicion_tirador",
    # Color tirador
    "color tirador": "color_tirador",
    "color": "color_tirador",
    "acabado tirador": "color_tirador",
    # Apertura
    "apertura": "apertura",
    "apertura i/d": "apertura",
    "opening": "apertura",
}


def _normalizar(texto: str) -> str:
    """Convierte a minúsculas, quita tildes y espacios extra."""
    tabla = str.maketrans("áéíóúàèìòùäëïöüâêîôûñ", "aeiouaeiouaeiouaeioun")
    return texto.strip().lower().translate(tabla)


def _mapear_columnas(fila_cabecera: list) -> dict[int, str]:
    """
    Devuelve {índice_columna: nombre_campo_interno} para cada celda
    de la fila de cabecera que se reconoce.
    """
    mapa: dict[int, str] = {}
    for idx, celda in enumerate(fila_cabecera):
        if celda is None:
            continue
        clave = _normalizar(str(celda))
        if clave in _ALIAS_COLUMNAS:
            campo = _ALIAS_COLUMNAS[clave]
            if campo not in mapa.values():  # primera ocurrencia gana
                mapa[idx] = campo
    return mapa


def _inferir_tipologia(id_pieza: str, mecanizado: str) -> str:
    """
    Infiere la tipología a partir del sufijo del ID y del mecanizado.

    Patrones reconocidos (ver matriz en docstring del módulo):
      Sueltos:       E{n}, B{n}, H{n}, R{n}, T{n}, PL{n}, FE{n}, F{n}, P{n}
      Prefijo M{n}-: P, C, PL, L, T, TBE  (Mueble METOD)
      Prefijo P{n}-: P (=X), T, PL, L     (Armario PAX)

    Devuelve cadena vacía '' si el ID no encaja en ningún patrón conocido.
    El check C-33 reporta esos IDs como SKIP para revisión manual.
    """
    # IDs sueltos (sin prefijo). Orden: regexes más específicos primero
    # para evitar ambigüedad con los más cortos (PL vs P, FE vs F).
    if re.match(r"^E\d+$", id_pieza, re.IGNORECASE):
        return "E"
    if re.match(r"^B\d+$", id_pieza, re.IGNORECASE):
        return "B"
    if re.match(r"^H\d+$", id_pieza, re.IGNORECASE):
        return "H"
    if re.match(r"^R\d+$", id_pieza, re.IGNORECASE):
        return "RV" if "vent" in mecanizado.lower() else "R"
    if re.match(r"^T\d+$", id_pieza, re.IGNORECASE):
        return "T"
    if re.match(r"^PL\d+$", id_pieza, re.IGNORECASE):
        return "L"
    if re.match(r"^FE\d+$", id_pieza, re.IGNORECASE):
        return "FE"
    if re.match(r"^F\d+$", id_pieza, re.IGNORECASE):
        return "F"
    if re.match(r"^P\d+$", id_pieza, re.IGNORECASE):
        return "P"  # Puerta suelta — se valida con todas las reglas P

    # IDs con prefijo M{n}- (Mueble METOD)
    m_metod = re.match(r"^M\d+-([A-Za-z]+)\d*$", id_pieza)
    if m_metod:
        sufijo = m_metod.group(1).upper()
        if sufijo == "P":
            return "P"
        if sufijo == "C":
            return "C"
        if sufijo in ("PL", "L"):
            return "L"
        if sufijo == "T":
            return "T"
        if sufijo == "TBE":
            return "TBE"
        # Nota: M{n}-X{n} no existe en CUBRO (PAX usa prefijo P{n}-).

    # IDs con prefijo P{n}- (Armario PAX)
    m_pax = re.match(r"^P\d+-([A-Za-z]+)\d*$", id_pieza)
    if m_pax:
        sufijo = m_pax.group(1).upper()
        if sufijo == "P":
            return "X"  # Puerta PAX
        if sufijo == "T":
            return "T"
        if sufijo in ("PL", "L"):
            return "L"

    return ""  # Sin patrón reconocido — C-33 lo reporta como SKIP


#: Palabras que indican filas de totales/subtotales — se ignoran como piezas.
_IDS_RESUMEN = frozenset({"total", "subtotal", "totales", "suma", "total piezas"})


def _celda_str(valor: object) -> str:
    """Convierte el valor de celda a string limpio; None → ''."""
    if valor is None:
        return ""
    return str(valor).strip()


def _celda_int(valor: object) -> int:
    """Convierte el valor de celda a entero; '' o None → 0."""
    s = _celda_str(valor)
    if not s:
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def leer_despiece(origen: BinaryIO | Path | str) -> list[Pieza]:
    """
    Lee el archivo DESPIECE (XLSX) y devuelve la lista de piezas.

    Args:
        origen: BytesIO desde Drive, Path o str con ruta de archivo.

    Returns:
        Lista de Pieza ordenada por ID tal y como aparece en el XLSX.
        Las filas sin ID o completamente vacías se ignoran.

    Raises:
        ValueError: si el archivo no tiene columnas reconocibles (ID, Ancho, Alto).
    """
    if isinstance(origen, (str, Path)):
        origen = Path(origen).open("rb")

    wb = openpyxl.load_workbook(origen, data_only=True)
    ws = wb.active

    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise ValueError("DESPIECE vacío: no hay filas")

    # Buscar la fila de cabecera (la primera que tenga ≥3 celdas no nulas)
    cabecera_idx = 0
    for i, fila in enumerate(filas):
        celdas_con_valor = [c for c in fila if c is not None and str(c).strip()]
        if len(celdas_con_valor) >= 3:
            cabecera_idx = i
            break

    mapa = _mapear_columnas(list(filas[cabecera_idx]))
    campos_necesarios = {"id", "ancho", "alto"}
    campos_encontrados = set(mapa.values())
    if not campos_necesarios.issubset(campos_encontrados):
        faltantes = campos_necesarios - campos_encontrados
        raise ValueError(
            f"DESPIECE: columnas obligatorias no encontradas: {faltantes}. "
            f"Cabecera detectada: {[filas[cabecera_idx][i] for i in mapa]}"
        )

    piezas: list[Pieza] = []
    for fila in filas[cabecera_idx + 1:]:
        datos = {campo: _celda_str(fila[idx]) for idx, campo in mapa.items()}
        id_pieza = datos.get("id", "")
        if not id_pieza or id_pieza.lower() in _IDS_RESUMEN:
            continue  # fila vacía, de total o sin ID → ignorar

        mecanizado = datos.get("mecanizado", "")
        tipologia = datos.get("tipologia", "") or _inferir_tipologia(id_pieza, mecanizado)

        piezas.append(Pieza(
            id=id_pieza,
            ancho=_celda_int(datos.get("ancho", 0)),
            alto=_celda_int(datos.get("alto", 0)),
            material=datos.get("material", "").upper(),
            gama=datos.get("gama", "").upper(),
            acabado=datos.get("acabado", ""),
            tipologia=tipologia.upper(),
            mecanizado=mecanizado,
            tirador=datos.get("tirador", ""),
            posicion_tirador=datos.get("posicion_tirador", ""),
            color_tirador=datos.get("color_tirador", ""),
            apertura=datos.get("apertura", "").upper(),
        ))

    return piezas
