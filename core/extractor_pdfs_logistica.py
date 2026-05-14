"""
core/extractor_pdfs_logistica.py — Extrae datos de PDFs logísticos.

PDFs soportados:
  - BULTOS_*.pdf : etiquetas de paquetería con "Bulto N de TOTAL"
  - DESTINO CAJA_*.pdf : etiqueta de destino con código CUB-{ID_PROYECTO}
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import pdfplumber


_RE_BULTO_TOTAL = re.compile(r"Bulto\s+\d+\s+de\s+(\d+)", re.IGNORECASE)
# Acepta '_INC' o '-INC' como separador y opcionalmente sufijo numérico
# (INC, INC2, INC3, ...). El código impreso bajo el barcode suele usar '_'
# como separador (p.ej. 'CUB-SP-20848_INC2-1-1').
_RE_CODIGO_CUB = re.compile(r"CUB-((?:EU|SP)-\d{5}(?:[-_]INC\d*)?)", re.IGNORECASE)
# Fallback: el ID sin prefijo CUB- (texto grande de cabecera del PDF, siempre
# con guiones).
_RE_ID_PROYECTO = re.compile(r"\b((?:EU|SP)-\d{5}(?:-INC\d*)?)\b", re.IGNORECASE)


def _texto_pdf(origen: BinaryIO | Path | str) -> str:
    if isinstance(origen, (str, Path)):
        ctx = pdfplumber.open(str(origen))
    else:
        ctx = pdfplumber.open(origen)
    partes: list[str] = []
    with ctx as pdf:
        for pagina in pdf.pages:
            t = pagina.extract_text(x_tolerance=2)
            if t:
                partes.append(t)
    return "\n\n".join(partes)


def leer_n_bultos(origen: BinaryIO | Path | str) -> int | None:
    """
    Extrae el número total de bultos del PDF BULTOS_.
    Busca el patrón 'Bulto N de TOTAL' y devuelve TOTAL.
    Devuelve None si no encuentra el patrón.
    """
    texto = _texto_pdf(origen)
    m = _RE_BULTO_TOTAL.search(texto)
    return int(m.group(1)) if m else None


def leer_codigo_destino(origen: BinaryIO | Path | str) -> str | None:
    """
    Extrae el código de destino del PDF DESTINO CAJA_.
    Intenta primero 'CUB-EU-XXXXX'/'CUB-SP-XXXXX' como texto explícito.
    Fallback: el texto del barcode (CUB-XXXXX) está embebido en la imagen
    y no es extraíble; se construye desde el ID de proyecto visible en cabecera.

    El código se devuelve en forma canónica con guiones — los '_' que pueda
    contener el texto extraído (p.ej. 'CUB-SP-20848_INC2') se normalizan a '-'.
    """
    texto = _texto_pdf(origen)
    m = _RE_CODIGO_CUB.search(texto)
    if m:
        return f"CUB-{m.group(1).upper().replace('_', '-')}"
    m2 = _RE_ID_PROYECTO.search(texto)
    if m2:
        return f"CUB-{m2.group(1).upper().replace('_', '-')}"
    return None
