"""
core/extractor_etiquetas_ean.py — Lee los CSVs ETIQUETAS y EAN LOGISTIC.

ETIQUETAS: una fila por pieza → ID, dimensiones, material/gama/acabado.
EAN LOGISTIC: una fila por asignación pieza↔bulto → ID bulto, peso, pieza.

Ambos archivos se leen desde BytesIO (sin escritura a disco).
Encodings habituales: UTF-8 con BOM o Latin-1. Se detectan automáticamente.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


# ---------------------------------------------------------------------------
# Estructuras de datos de salida (más simples que Pieza completa)
# ---------------------------------------------------------------------------

# Normaliza nombres de gama del CSV al código interno (igual que extractor_dxf)
_GAMA_NORM: dict[str, str] = {
    "LAMINADO": "LAM",
    "LINOLEO": "LIN",
    "LINÓLEO": "LIN",
    "LACA": "LAC",
    "WOOD": "WOO",
}


@dataclass
class FilaEtiqueta:
    """Una fila del CSV ETIQUETAS."""
    id: str
    ancho: int     # mm
    alto: int      # mm
    material: str
    gama: str
    acabado: str


@dataclass
class FilaEAN:
    """Una fila del CSV EAN LOGISTIC."""
    id_bulto: str     # "CUB-EU-21822-1-5"
    numero_bulto: int
    total_bultos: int
    id_pieza: str
    peso_kg: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")


def _decodificar(raw: bytes) -> str:
    """Intenta decodificar bytes con varios encodings."""
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def _abrir_como_texto(origen: BinaryIO | Path | str) -> str:
    """Lee bytes de origen y devuelve texto decodificado."""
    if isinstance(origen, (str, Path)):
        return Path(origen).read_bytes().pipe(_decodificar) if False else \
               _decodificar(Path(origen).read_bytes())
    raw = origen.read()
    if isinstance(raw, str):
        return raw
    return _decodificar(raw)


def _normalizar_cabecera(texto: str) -> str:
    tabla = str.maketrans("áéíóúàèìòùñ", "aeiouaeioun")
    return texto.strip().lower().translate(tabla)


def _detectar_separador(primera_linea: str) -> str:
    """Detecta ; o , como separador según cuál aparece más."""
    return ";" if primera_linea.count(";") >= primera_linea.count(",") else ","


def _leer_csv(texto: str) -> tuple[list[str], list[dict[str, str]]]:
    """
    Parsea CSV con detección automática de separador.
    Devuelve (cabeceras_normalizadas, filas_como_dict).
    """
    lineas = texto.splitlines()
    if not lineas:
        return [], []
    sep = _detectar_separador(lineas[0])
    reader = csv.DictReader(io.StringIO(texto), delimiter=sep)
    cabeceras = [_normalizar_cabecera(k) for k in (reader.fieldnames or [])]
    filas: list[dict[str, str]] = []
    for fila_raw in reader:
        fila_norm = {
            _normalizar_cabecera(k): (v.strip() if v else "")
            for k, v in fila_raw.items()
            if k is not None
        }
        filas.append(fila_norm)
    return cabeceras, filas


def _int_o(valor: str, defecto: int = 0) -> int:
    try:
        return int(float(valor.replace(",", ".")))
    except (ValueError, AttributeError):
        return defecto


def _float_o(valor: str, defecto: float = 0.0) -> float:
    try:
        # Eliminar unidades ("2.596 kg" → "2.596") y normalizar separador decimal
        limpio = valor.strip().split()[0].replace(",", ".")
        return float(limpio)
    except (ValueError, AttributeError, IndexError):
        return defecto


# ---------------------------------------------------------------------------
# Mapa de alias para ETIQUETAS
# ---------------------------------------------------------------------------

_ALIAS_ETQ: dict[str, str] = {
    "id": "id", "referencia": "id", "pieza": "id", "id pieza": "id",
    "ancho": "ancho", "anchura": "ancho",
    "alto": "alto", "altura": "alto",
    "material": "material",
    "gama": "gama",
    "acabado": "acabado", "finish": "acabado",
}

# Alias para EAN LOGISTIC
_ALIAS_EAN: dict[str, str] = {
    "id bulto": "id_bulto", "id_bulto": "id_bulto",
    "bulto": "id_bulto", "ean": "id_bulto", "codigo bulto": "id_bulto",
    "numero bulto": "numero_bulto", "num bulto": "numero_bulto",
    "num_bulto": "numero_bulto", "n bulto": "numero_bulto",
    "n. bulto": "numero_bulto",
    "total bultos": "total_bultos", "total": "total_bultos",
    "id pieza": "id_pieza", "id_pieza": "id_pieza",
    "pieza": "id_pieza", "referencia": "id_pieza",
    "peso": "peso_kg", "peso kg": "peso_kg", "peso_kg": "peso_kg",
    "peso (kg)": "peso_kg", "peso_pieza": "peso_kg", "weight": "peso_kg",
}


def _resolver_campo(cabecera_norm: str, alias: dict[str, str]) -> str | None:
    return alias.get(cabecera_norm)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def leer_etiquetas(origen: BinaryIO | Path | str) -> list[FilaEtiqueta]:
    """
    Lee el CSV ETIQUETAS y devuelve una fila por pieza.

    Raises:
        ValueError: si faltan columnas obligatorias (id, ancho, alto).
    """
    texto = _abrir_como_texto(origen)
    _, filas = _leer_csv(texto)
    if not filas:
        raise ValueError("ETIQUETAS: CSV vacío")

    resultado: list[FilaEtiqueta] = []
    for fila in filas:
        datos: dict[str, str] = {}
        for key, val in fila.items():
            campo = _resolver_campo(key, _ALIAS_ETQ)
            if campo and campo not in datos:
                datos[campo] = val

        id_pieza = datos.get("id", "")
        if not id_pieza:
            continue

        resultado.append(FilaEtiqueta(
            id=id_pieza,
            ancho=_int_o(datos.get("ancho", "0")),
            alto=_int_o(datos.get("alto", "0")),
            material=datos.get("material", "").upper(),
            gama=_GAMA_NORM.get(datos.get("gama", "").upper(), datos.get("gama", "").upper()),
            acabado=datos.get("acabado", ""),
        ))

    campos_requeridos = {"id", "ancho", "alto"}
    # Verificamos con la primera fila exitosa
    if resultado and not all(
        getattr(resultado[0], c, None) is not None for c in ("id", "ancho", "alto")
    ):
        raise ValueError(
            f"ETIQUETAS: columnas obligatorias no encontradas: {campos_requeridos}"
        )
    return resultado


def leer_ean(origen: BinaryIO | Path | str) -> list[FilaEAN]:
    """
    Lee el CSV EAN LOGISTIC.

    Cada fila relaciona una pieza con un bulto. Un bulto puede tener
    múltiples piezas (una fila por pieza por bulto).

    Raises:
        ValueError: si faltan columnas obligatorias (id_bulto, id_pieza).
    """
    texto = _abrir_como_texto(origen)
    _, filas = _leer_csv(texto)
    if not filas:
        raise ValueError(
            "EAN LOGISTIC: no se encontraron filas válidas (CSV vacío o sin datos)"
        )

    resultado: list[FilaEAN] = []
    for fila in filas:
        datos: dict[str, str] = {}
        for key, val in fila.items():
            campo = _resolver_campo(key, _ALIAS_EAN)
            if campo and campo not in datos:
                datos[campo] = val

        id_bulto = datos.get("id_bulto", "")
        id_pieza_raw = datos.get("id_pieza", "")
        if not id_bulto or not id_pieza_raw:
            continue

        # Extraer número y total del id_bulto: CUB-EU-21822-1-5 → num=1, total=5
        m = re.search(r"-(\d+)-(\d+)$", id_bulto)
        numero = int(m.group(1)) if m else _int_o(datos.get("numero_bulto", "0"))
        total = int(m.group(2)) if m else _int_o(datos.get("total_bultos", "0"))
        peso = _float_o(datos.get("peso_kg", "0"))

        # ID_PIEZA puede contener varias piezas separadas por "/" (ej. "M5-T2 / M5-T1")
        ids_piezas = [p.strip() for p in re.split(r"\s*/\s*", id_pieza_raw) if p.strip()]
        for id_pieza in ids_piezas:
            resultado.append(FilaEAN(
                id_bulto=id_bulto,
                numero_bulto=numero,
                total_bultos=total,
                id_pieza=id_pieza,
                peso_kg=peso,
            ))

    if not resultado:
        raise ValueError(
            "EAN LOGISTIC: no se encontraron filas válidas (revisa columnas id_bulto e id_pieza)"
        )
    return resultado
