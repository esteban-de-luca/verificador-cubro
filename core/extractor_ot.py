"""
core/extractor_ot.py — Lee el PDF de la Orden de Trabajo con pdfplumber.

La OT es el documento maestro del taller. Este extractor busca:
  - ID de proyecto y nombre de cliente
  - Nº total de piezas (Packing List)
  - Nº de tableros por material (para check C-03)
  - Peso total en kg
  - Nº de tiradores declarados
  - Semana de producción
  - Observaciones CNC (sección independiente)
  - Observaciones de producción

El texto de los PDFs de OT no tiene estructura fija de tabla con coordenadas
estables — se usa búsqueda por regex sobre el texto extraído plana.

Nota de extracción: x_tolerance=2 en pdfplumber recupera los espacios entre
palabras que Rhino/Word omite en el PDF (gap real ≈2.8pt, vs ≤0 intrapalabra).
Las páginas se unen con \\n\\n para que los saltos de página actúen como
separadores de sección y los regexes de sección no se desborden.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import pdfplumber

from core.modelos import OTData


# ---------------------------------------------------------------------------
# Regexes de extracción
# ---------------------------------------------------------------------------

_RE_ID_PROYECTO = re.compile(
    r"\b((?:EU|SP)-\d{5}(?:-INC)?)\b", re.IGNORECASE
)
_RE_CLIENTE = re.compile(
    r"(?:cliente|client|customer)[:\s]+([A-Za-záéíóúàèìòùñüÁÉÍÓÚÑ ,.-]+?)(?:\n|$)",
    re.IGNORECASE,
)
_RE_SEMANA = re.compile(
    r"(Semana\s+\d+)", re.IGNORECASE
)
_RE_NUM_PIEZAS = re.compile(
    r"(?:cantidad\s+de\s+piezas|total\s+piezas|n[uú]mero\s+de\s+piezas|piezas\s+totales)[:\s]+(\d+)",
    re.IGNORECASE,
)
# "Peso estimado total: 167,4 kg"  o  "Peso total: 120 kg"
_RE_PESO = re.compile(
    r"peso\s+(?:estimado\s+)?(?:total|bruto)[:\s]+([\d,. ]+)\s*kg",
    re.IGNORECASE,
)
# "# Tiradores 13"  o  "Tiradores: 13"
_RE_TIRADORES = re.compile(
    r"(?:#\s*tiradores?|tiradores?)[:\s]+(\d+)", re.IGNORECASE
)
# Fila "Tiradores  Superline" (sin #) — captura modelo/s del tirador
_RE_MODELO_TIRADOR = re.compile(
    r"^Tiradores\s+([A-Za-z][^\n]*)$",
    re.IGNORECASE | re.MULTILINE,
)
# Tabla INFORMACION DE CORTE — formato multi-columna:
#   Tablero base  MDF  PLY
#   Gama          Laca Laminado
#   Acabado       Marga Sable
#   # Tableros    2    1
_RE_CORTE_TABLA = re.compile(
    r"Tablero\s+base\s+(.*?)\n"
    r"Gama\s+(.*?)\n"
    r"Acabado\s+(.*?)\n"
    r"#\s*Tableros\s*([^\n]*)",
    re.IGNORECASE,
)
# "Cantidad de tableros: 3" (cabecera INFORMACION DE ENVIO). Acepta vacío.
_RE_TABLEROS_TOTAL = re.compile(
    r"cantidad\s+de\s+tableros[:\s]*([^\n]*)", re.IGNORECASE
)
# Filas del Packing List: "EU-21247 M5-T2 120 800 ..."  o  "EU-21247 P1-P1 ..."  o  "EU-21247 R2 ..."  o  "EU-21742 H1-TAP ..."
_RE_PL_FILA = re.compile(
    r"(?:EU|SP)-\d{5}(?:-INC)?\s+"                        # ID proyecto al inicio de fila
    r"([A-Za-z]+\d+-[A-Za-z]+\d*|[A-Za-z]+\d+)",          # ID pieza: M9-PL1, P1-P1, H1-TAP, R2, E1…
    re.IGNORECASE
)
# "Rejillas de ventilación: 2 uds."
_RE_VENTILACION = re.compile(
    r"rejillas?\s+de\s+ventilaci[oó]n[:\s]+(\d+)", re.IGNORECASE
)
# "Colgador de hornacina: No"  /  "Colgador de hornacina: 2"  /  (legacy "Sí")
_RE_HORNACINA = re.compile(
    r"colgador\s+de\s+hornacina[:\s]+(s[ií]|no|\d+)", re.IGNORECASE
)
# "Tensores: No"  /  "Sí"
_RE_TENSORES = re.compile(
    r"tensores[:\s]+(s[ií]|no)", re.IGNORECASE
)
# Sección de Observaciones CNC — se detiene en la siguiente cabecera de sección
# o en línea en blanco. Cabeceras conocidas: OBSERVACIONES DE PRODUCCIÓN, PACKING LIST.
_RE_SEC_CNC = re.compile(
    r"(?:observaciones?\s+cnc|cnc\s+observations?)[:\s]*\n"
    r"(.*?)"
    r"(?=\nobservaciones?\s+(?:de\s+)?producci[oó]n|\npacking\s+list|\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_RE_SEC_PRODUCCION = re.compile(
    r"(?:observaciones?\s+(?:de\s+)?producci[oó]n|production\s+notes?)[:\s]*\n"
    r"(.*?)"
    r"(?=\npacking\s+list|\n\s*\n|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_GAMA_NOMBRE_A_CODIGO: dict[str, str] = {
    "laca": "LAC",
    "laminado": "LAM",
    "linoleo": "LIN",
    "linóleo": "LIN",
    "wood": "WOO",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extraer_texto(bytesio_o_path: BinaryIO | Path | str) -> str:
    """Extrae todo el texto del PDF concatenando todas las páginas."""
    if isinstance(bytesio_o_path, (str, Path)):
        ctx = pdfplumber.open(str(bytesio_o_path))
    else:
        ctx = pdfplumber.open(bytesio_o_path)

    partes: list[str] = []
    with ctx as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text(x_tolerance=2)
            if texto:
                partes.append(texto)
    return "\n\n".join(partes)


def _float_limpio(texto: str) -> float:
    """Convierte '1.234,56' o '1234.56' a float."""
    s = texto.strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _limpiar_observaciones(bloque: str) -> list[str]:
    """Divide un bloque de texto en líneas no vacías."""
    return [
        linea.strip()
        for linea in bloque.strip().splitlines()
        if linea.strip()
    ]


def _parsear_tabla_corte(texto: str) -> tuple[dict[str, int], list[str]]:
    """
    Parsea la tabla INFORMACION DE CORTE.

    Returns:
        (tableros, materiales_sin_cantidad) donde:
        - tableros: {MAT_GAM_Acabado: n_tableros} — solo columnas con cantidad declarada
        - materiales_sin_cantidad: claves de columnas cuyo '# Tableros' está vacío
          o no es un número (se detectan pero no se cuentan).
        Si la tabla no coincide, devuelve ({}, []).
    """
    m = _RE_CORTE_TABLA.search(texto)
    if not m:
        return {}, []

    materiales = m.group(1).upper().split()
    gamas_raw = m.group(2).lower().split()
    acabados_tokens = m.group(3).split()
    nums_raw = m.group(4).split()

    gamas = [_GAMA_NOMBRE_A_CODIGO.get(g, g.upper()) for g in gamas_raw]

    n_cols = min(len(materiales), len(gamas), len(acabados_tokens))
    if n_cols == 0:
        return {}, []

    tableros: dict[str, int] = {}
    sin_cantidad: list[str] = []
    for i in range(n_cols):
        clave = f"{materiales[i]}_{gamas[i]}_{acabados_tokens[i].title()}"
        num_tok = nums_raw[i] if i < len(nums_raw) else ""
        if num_tok.isdigit():
            tableros[clave] = tableros.get(clave, 0) + int(num_tok)
        else:
            if clave not in sin_cantidad:
                sin_cantidad.append(clave)
    return tableros, sin_cantidad


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def leer_ot(origen: BinaryIO | Path | str) -> OTData:
    """
    Lee el PDF de la Orden de Trabajo y extrae los datos estructurados.

    Args:
        origen: BytesIO desde Drive, Path o str con ruta del archivo OT.

    Returns:
        OTData con todos los campos extraídos. Los campos no encontrados
        tienen valores por defecto (0, "", []) para que los checks puedan
        detectar su ausencia sin lanzar excepciones.
    """
    texto = _extraer_texto(origen)

    # ID de proyecto
    m_id = _RE_ID_PROYECTO.search(texto)
    id_proyecto = m_id.group(1).upper() if m_id else ""

    # Cliente
    m_cliente = _RE_CLIENTE.search(texto)
    cliente = m_cliente.group(1).strip() if m_cliente else ""

    # Semana
    m_semana = _RE_SEMANA.search(texto)
    semana = m_semana.group(1).strip() if m_semana else ""

    # Nº piezas
    m_piezas = _RE_NUM_PIEZAS.search(texto)
    num_piezas = int(m_piezas.group(1)) if m_piezas else 0

    # Peso total — "Peso estimado total: 167,4 kg"
    m_peso = _RE_PESO.search(texto)
    peso_total = _float_limpio(m_peso.group(1)) if m_peso else 0.0

    # Tiradores — "# Tiradores 13"
    m_tir = _RE_TIRADORES.search(texto)

    # Modelos de tirador — fila "Tiradores  Superline" (sin #)
    modelos_tiradores: list[str] = list(dict.fromkeys(
        tok.strip().title()
        for m in _RE_MODELO_TIRADOR.finditer(texto)
        for tok in m.group(1).split()
        if tok.strip() and tok.strip() != "-"
    ))
    num_tiradores = int(m_tir.group(1)) if m_tir else 0

    # Tableros por material (tabla INFORMACION DE CORTE)
    tableros, materiales_sin_cantidad = _parsear_tabla_corte(texto)

    # Cantidad total de tableros en cabecera "INFORMACION DE ENVIO"
    m_tot = _RE_TABLEROS_TOTAL.search(texto)
    if m_tot:
        tok_tot = m_tot.group(1).strip().split()
        num_tableros_total: int | None = (
            int(tok_tot[0]) if tok_tot and tok_tot[0].isdigit() else None
        )
    else:
        num_tableros_total = None

    # Ventilación — "Rejillas de ventilación: 2 uds."
    m_vent = _RE_VENTILACION.search(texto)
    num_ventilacion = int(m_vent.group(1)) if m_vent else 0

    # Hornacina — "Colgador de hornacina: No" / "Colgador de hornacina: 2" / legacy "Sí"
    m_hor = _RE_HORNACINA.search(texto)
    if m_hor:
        val = m_hor.group(1).lower()
        if val == "no":
            colgadores_hornacina: int | None = 0
        elif val.startswith("s"):
            colgadores_hornacina = 1  # legacy "Sí" — cantidad desconocida, asumimos ≥1
        else:
            colgadores_hornacina = int(val)
    else:
        colgadores_hornacina = None

    # Tensores — "Tensores: No/Sí"
    m_ten = _RE_TENSORES.search(texto)
    if m_ten:
        tiene_tensores: bool | None = m_ten.group(1).lower().startswith("s")
    else:
        tiene_tensores = None

    # Observaciones CNC
    m_cnc = _RE_SEC_CNC.search(texto)
    obs_cnc = _limpiar_observaciones(m_cnc.group(1)) if m_cnc else []

    # Observaciones producción
    m_prod = _RE_SEC_PRODUCCION.search(texto)
    obs_prod = _limpiar_observaciones(m_prod.group(1)) if m_prod else []

    # IDs de piezas del Packing List (filas "EU-XXXXX  ID_PIEZA  ancho alto ...")
    ids_piezas = [m.group(1).upper() for m in _RE_PL_FILA.finditer(texto)]

    return OTData(
        id_proyecto=id_proyecto,
        cliente=cliente,
        semana=semana,
        num_piezas=num_piezas,
        peso_total_kg=peso_total,
        num_tiradores=num_tiradores,
        tableros=tableros,
        materiales_sin_cantidad=materiales_sin_cantidad,
        num_tableros_total=num_tableros_total,
        num_ventilacion=num_ventilacion,
        colgadores_hornacina=colgadores_hornacina,
        tiene_tensores=tiene_tensores,
        observaciones_cnc=obs_cnc,
        observaciones_produccion=obs_prod,
        ids_piezas=ids_piezas,
        modelos_tiradores=modelos_tiradores,
    )
