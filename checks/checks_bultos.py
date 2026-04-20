"""
checks/checks_bultos.py — C-50 a C-56: Logística y bultos.

Inputs:
    filas_ean: list[FilaEAN]  — del CSV EAN LOGISTIC
    piezas: list[Pieza]       — del DESPIECE
    ot: OTData                — OT parseada
    reglas: dict              — cargado por reglas_loader
    n_bultos_pdf: int | None  — de PDF BULTOS/ALBARÁN (None → SKIP comparación PDF)
    codigo_destino: str | None — de PDF DESTINO CAJA (None → SKIP C-56)
"""

from __future__ import annotations

import re

from core.modelos import CheckResult, OTData, Pieza
from core.extractor_etiquetas_ean import FilaEAN
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO = "Logistica"

# Regex para validar formato de ID de bulto: CUB-{ID_PROYECTO}-{N}-{TOTAL}
_RE_ID_BULTO = re.compile(
    r"^CUB-(?:EU|SP)-?\d{5}(?:-INC)?-\d+-\d+$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# C-50: Nº total de bultos igual en EAN LOGISTIC y PDFs (BULTOS / ALBARÁN)
# ---------------------------------------------------------------------------

def check_num_bultos(
    filas_ean: list[FilaEAN],
    n_bultos_pdf: int | None = None,
) -> CheckResult:
    """
    C-50: Nº de bultos únicos en EAN LOGISTIC == nº de bultos en PDF BULTOS/ALBARÁN.
    SKIP si n_bultos_pdf no está disponible.
    Bloquea: Sí.
    """
    ids_unicos = {f.id_bulto for f in filas_ean}
    n_ean = len(ids_unicos)

    if n_bultos_pdf is None:
        return _skip(
            "C-50", "Nº bultos igual en EAN y PDFs",
            f"PDF BULTOS/ALBARÁN no disponible (EAN: {n_ean} bultos)", _GRUPO,
        )
    if n_ean == n_bultos_pdf:
        return _pass("C-50", "Nº bultos igual en EAN y PDFs", True, _GRUPO)
    return _fail(
        "C-50", "Nº bultos igual en EAN y PDFs",
        f"EAN LOGISTIC: {n_ean} | PDF: {n_bultos_pdf}",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-51: Todas las piezas del DESPIECE asignadas a algún bulto
# ---------------------------------------------------------------------------

def check_piezas_asignadas(
    piezas: list[Pieza], filas_ean: list[FilaEAN]
) -> CheckResult:
    """C-51: Cada ID del DESPIECE aparece al menos una vez en EAN LOGISTIC. Bloquea: Sí."""
    ids_en_ean = {f.id_pieza for f in filas_ean}
    sin_bulto = [p.id for p in piezas if p.id not in ids_en_ean]
    return _resultado("C-51", "Todas las piezas asignadas a un bulto",
                      [f"Sin bulto: {pid}" for pid in sin_bulto], True, _GRUPO)


# ---------------------------------------------------------------------------
# C-52: Sin piezas duplicadas asignadas a más de un bulto
# ---------------------------------------------------------------------------

def check_piezas_sin_duplicados(filas_ean: list[FilaEAN]) -> CheckResult:
    """C-52: Cada pieza asignada a exactamente un bulto. Bloquea: Sí."""
    conteo: dict[str, list[str]] = {}
    for f in filas_ean:
        conteo.setdefault(f.id_pieza, []).append(f.id_bulto)

    errores = [
        f"{pid}: asignado a {len(bultos)} bultos ({', '.join(bultos)})"
        for pid, bultos in conteo.items()
        if len(bultos) > 1
    ]
    return _resultado("C-52", "Sin piezas duplicadas en varios bultos", errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-53: Formato de ID de bulto correcto: CUB-{ID_PROYECTO}-{N}-{TOTAL}
# ---------------------------------------------------------------------------

def check_formato_id_bulto(filas_ean: list[FilaEAN], id_proyecto: str) -> CheckResult:
    """C-53: Todos los IDs de bulto siguen el formato CUB-{ID}-{N}-{TOTAL}. Bloquea: Sí."""
    id_norm = id_proyecto.upper().replace("-", "")
    errores = []
    for f in filas_ean:
        if not _RE_ID_BULTO.match(f.id_bulto):
            errores.append(f"ID inválido: '{f.id_bulto}'")
        else:
            # Verificar que el ID del proyecto en el bulto coincide
            partes = f.id_bulto.upper().split("-")
            # CUB-EU-21822-1-5 → partes = ['CUB','EU','21822','1','5']
            # CUB-EU21822-1-5  → partes = ['CUB','EU21822','1','5'] (sin guión en ID)
            id_en_bulto = "".join(p for p in partes[1:-2] if p.isalnum())
            if id_norm and id_en_bulto and id_en_bulto != id_norm:
                errores.append(
                    f"Bulto '{f.id_bulto}': proyecto '{id_en_bulto}' ≠ '{id_norm}'"
                )
    # Deduplica errores
    return _resultado("C-53", "Formato ID bulto correcto", list(dict.fromkeys(errores)),
                      True, _GRUPO)


# ---------------------------------------------------------------------------
# C-54: Peso total: suma EAN == peso OT (tolerancia configurable)
# ---------------------------------------------------------------------------

def check_peso_total(
    filas_ean: list[FilaEAN], ot: OTData, reglas: dict
) -> CheckResult:
    """
    C-54: Suma de pesos del EAN LOGISTIC == peso total de la OT,
    dentro de la tolerancia definida en logistica.tolerancia_peso_porcentaje.
    Bloquea: No.
    """
    if ot.peso_total_kg == 0:
        return _skip("C-54", "Peso total EAN == OT (tolerancia máx.)",
                     "OT sin peso declarado", _GRUPO)

    tolerancia_pct: float = reglas["logistica"]["tolerancia_peso_porcentaje"]
    # PESO_PIEZA en el EAN es el peso total del bulto, repetido para cada pieza del bulto.
    # Se suma una sola vez por id_bulto único para no duplicar.
    peso_ean = sum({f.id_bulto: f.peso_kg for f in filas_ean}.values())

    if peso_ean == 0:
        return _skip("C-54", "Peso total EAN == OT (tolerancia máx.)",
                     "EAN LOGISTIC sin pesos declarados", _GRUPO)

    desviacion_pct = abs(peso_ean - ot.peso_total_kg) / ot.peso_total_kg * 100
    if desviacion_pct <= tolerancia_pct:
        return _pass("C-54", "Peso total EAN == OT (tolerancia máx.)", False, _GRUPO)
    return _fail(
        "C-54", "Peso total EAN == OT (tolerancia máx.)",
        f"EAN: {peso_ean:.2f} kg | OT: {ot.peso_total_kg:.2f} kg "
        f"(desviación: {desviacion_pct:.1f}% > {tolerancia_pct}%)",
        False, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-55: Modelo de envío coherente con dimensiones máximas de piezas
# ---------------------------------------------------------------------------

def check_envio_estructura(
    piezas: list[Pieza], ot: OTData, reglas: dict
) -> CheckResult:
    """
    C-55: Si alguna pieza supera el umbral de dimensión para paquetería estándar,
    el envío debe ser en estructura (indicado en OT).
    Bloquea: Sí.
    """
    if not piezas:
        return _skip("C-55", "Modelo envío coherente con dimensiones", "Sin piezas", _GRUPO)

    umbral_mm: int = reglas["logistica"]["estructura_umbral_mm"]
    max_dim = max(max(p.ancho, p.alto) for p in piezas)

    necesita_estructura = max_dim > umbral_mm
    declara_estructura = any(
        "estructura" in obs.lower() for obs in ot.observaciones_cnc + ot.observaciones_produccion
    )

    if necesita_estructura and not declara_estructura:
        return _fail(
            "C-55", "Modelo envío coherente con dimensiones",
            f"Pieza de {max_dim}mm > umbral {umbral_mm}mm pero OT no declara envío en estructura",
            True, _GRUPO,
        )
    return _pass("C-55", "Modelo envío coherente con dimensiones", True, _GRUPO)


# ---------------------------------------------------------------------------
# C-56: Código DESTINO CAJA es CUB-{ID_PROYECTO} sin números adicionales
# ---------------------------------------------------------------------------

def check_codigo_destino_caja(
    codigo_destino: str | None, id_proyecto: str
) -> CheckResult:
    """
    C-56: El código del PDF DESTINO CAJA es exactamente CUB-{ID_PROYECTO}.
    SKIP si el PDF no está disponible.
    Bloquea: Sí.
    """
    if codigo_destino is None:
        return _skip("C-56", "Código DESTINO CAJA correcto",
                     "PDF DESTINO CAJA no disponible", _GRUPO)

    esperado = f"CUB-{id_proyecto.upper()}"
    codigo_norm = codigo_destino.strip().upper()
    if codigo_norm == esperado:
        return _pass("C-56", "Código DESTINO CAJA correcto", True, _GRUPO)
    return _fail(
        "C-56", "Código DESTINO CAJA correcto",
        f"Encontrado: '{codigo_norm}' | Esperado: '{esperado}'",
        True, _GRUPO,
    )
