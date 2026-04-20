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
_RE_CODIGO_CUB = re.compile(r"CUB-((?:EU|SP)-\d{5}(?:-INC)?)", re.IGNORECASE)


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
    Busca 'CUB-EU-XXXXX' o 'CUB-SP-XXXXX' en el texto.
    Devuelve None si el PDF no contiene el código en formato texto.
    """
    texto = _texto_pdf(origen)
    m = _RE_CODIGO_CUB.search(texto)
    return f"CUB-{m.group(1).upper()}" if m else None
