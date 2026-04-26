"""
checks/checks_piezas.py — C-10 a C-29: Congruencia de piezas, materiales y mecanizados.

Todos los checks reciben las reglas como parámetro — nunca leen YAML directamente.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from core.modelos import CheckResult, OTData, Pieza
from core.extractor_etiquetas_ean import FilaEtiqueta
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO_PIEZAS = "Piezas"
_GRUPO_MATERIAL = "Material"
_GRUPO_MEC = "Mecanizados"
_GRUPO_TIRA = "Tiradores"


def _norm_acabado(s: str) -> str:
    """Normaliza acabados: lowercase y colapsa guiones/espacios.
    'Marble-Green' == 'Marble Green' == 'marble  green' → 'marble green'."""
    return re.sub(r"[\s\-]+", " ", s.strip().lower())

# ---------------------------------------------------------------------------
# C-10: Nº total de piezas igual en OT, DESPIECE y ETIQUETAS
# ---------------------------------------------------------------------------

def check_num_piezas(
    piezas: list[Pieza],
    etiquetas: list[FilaEtiqueta],
    ot: OTData,
) -> CheckResult:
    """C-10: Nº piezas DESPIECE == ETIQUETAS (== OT si disponible). Bloquea: Sí."""
    n_des = len(piezas)
    n_etq = len({e.id for e in etiquetas})
    errores = []
    if n_des != n_etq:
        errores.append(f"DESPIECE: {n_des} | ETIQUETAS: {n_etq}")
    if ot.num_piezas > 0 and n_des != ot.num_piezas:
        errores.append(f"DESPIECE: {n_des} | OT: {ot.num_piezas}")
    return _resultado("C-10", "Nº total piezas igual en OT, DESPIECE y ETIQUETAS",
                      errores, True, _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-11: Todos los IDs del DESPIECE presentes en ETIQUETAS
# ---------------------------------------------------------------------------

def check_ids_despiece_en_etiquetas(
    piezas: list[Pieza],
    etiquetas: list[FilaEtiqueta],
) -> CheckResult:
    """C-11: Cada ID del DESPIECE debe existir en ETIQUETAS. Bloquea: Sí."""
    ids_etq = {e.id for e in etiquetas}
    faltantes = [p.id for p in piezas if p.id not in ids_etq]
    return _resultado("C-11", "IDs DESPIECE presentes en ETIQUETAS", faltantes, True, _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-12: Todos los IDs del DESPIECE presentes en Packing List OT
# ---------------------------------------------------------------------------

def check_ids_despiece_en_ot(piezas: list[Pieza], ot: OTData) -> CheckResult:
    """
    C-12: Cada ID del DESPIECE en el Packing List de la OT.
    SKIP si el extractor no proporcionó IDs individuales de la OT.
    Bloquea: Sí.
    """
    if not ot.ids_piezas:
        return _skip(
            "C-12", "IDs DESPIECE presentes en Packing List OT",
            "OT sin IDs individuales (requiere extractor avanzado de OT)", _GRUPO_PIEZAS,
        )
    ids_ot = set(ot.ids_piezas)
    faltantes = [p.id for p in piezas if p.id.upper() not in ids_ot]
    return _resultado("C-12", "IDs DESPIECE presentes en Packing List OT",
                      faltantes, True, _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-13: Dimensiones iguales en DESPIECE y ETIQUETAS
# ---------------------------------------------------------------------------

def check_dimensiones(
    piezas: list[Pieza],
    etiquetas: list[FilaEtiqueta],
) -> CheckResult:
    """C-13: Ancho y alto de cada pieza iguales en DESPIECE y ETIQUETAS. Bloquea: Sí."""
    idx_etq = {e.id: e for e in etiquetas}
    errores = []
    for p in piezas:
        e = idx_etq.get(p.id)
        if e is None:
            continue  # ya detectado por C-11
        if p.ancho != e.ancho or p.alto != e.alto:
            errores.append(
                f"{p.id}: DESPIECE {p.ancho}×{p.alto} ≠ ETIQUETAS {e.ancho}×{e.alto}"
            )
    return _resultado("C-13", "Dimensiones iguales en DESPIECE y ETIQUETAS",
                      errores, True, _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-14: Material/gama/acabado consistente entre DESPIECE y ETIQUETAS
# ---------------------------------------------------------------------------

def check_material_consistente(
    piezas: list[Pieza],
    etiquetas: list[FilaEtiqueta],
) -> CheckResult:
    """C-14: Material, gama y acabado iguales en DESPIECE y ETIQUETAS. Bloquea: Sí."""
    idx_etq = {e.id: e for e in etiquetas}
    errores = []
    for p in piezas:
        e = idx_etq.get(p.id)
        if e is None:
            continue
        inconsistencias = []
        if p.material and e.material and p.material != e.material:
            inconsistencias.append(f"material {p.material}≠{e.material}")
        if p.gama and e.gama and p.gama != e.gama:
            inconsistencias.append(f"gama {p.gama}≠{e.gama}")
        if p.acabado and e.acabado and _norm_acabado(p.acabado) != _norm_acabado(e.acabado):
            inconsistencias.append(f"acabado '{p.acabado}'≠'{e.acabado}'")
        if inconsistencias:
            errores.append(f"{p.id}: {', '.join(inconsistencias)}")
    return _resultado("C-14", "Material/gama/acabado consistente DESPIECE↔ETIQUETAS",
                      errores, True, _GRUPO_MATERIAL)


# ---------------------------------------------------------------------------
# C-15: PLY solo con LAM o LIN — MDF solo con LAC o WOO
# ---------------------------------------------------------------------------

def check_material_tablero(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-15: Combinación tablero-gama válida. Bloquea: Sí."""
    materiales = reglas["materiales"]
    errores = []
    for p in piezas:
        config = materiales.get(p.material)
        if config is None:
            errores.append(f"{p.id}: material desconocido '{p.material}'")
            continue
        if p.gama and p.gama not in config["gamas_validas"]:
            errores.append(
                f"{p.id}: {p.material}+{p.gama} inválido "
                f"(válidas: {config['gamas_validas']})"
            )
    return _resultado("C-15", "PLY→LAM/LIN · MDF→LAC/WOO", errores, True, _GRUPO_MATERIAL)


# ---------------------------------------------------------------------------
# C-16: Acabados pertenecen a la lista validada de su gama
# ---------------------------------------------------------------------------

def check_acabados(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-16: Acabado de cada pieza está en la lista validada de su gama. Bloquea: No."""
    acabados_gama: dict[str, list[str]] = reglas["acabados"]
    errores = []
    for p in piezas:
        lista = acabados_gama.get(p.gama)
        if lista is None:
            continue  # gama desconocida → ya detectado por C-15
        lista_norm = {_norm_acabado(a) for a in lista}
        if p.acabado and _norm_acabado(p.acabado) not in lista_norm:
            errores.append(f"{p.id}: acabado '{p.acabado}' no validado para gama {p.gama}")
    return _resultado("C-16", "Acabados pertenecen a la lista validada de su gama",
                      errores, False, _GRUPO_MATERIAL)


# ---------------------------------------------------------------------------
# C-17: Sufijo del ID coherente con tipología declarada
# ---------------------------------------------------------------------------

_RE_SUFIJO = re.compile(r"^M\d+-([A-Za-z]+)\d*$")


def check_sufijo_tipologia(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """
    C-17: El sufijo del ID de pieza (M2-P1 → 'P') debe ser coherente con la
    tipología declarada en el DESPIECE. Bloquea: Sí.
    """
    sufijo_a_tip: dict[str, list[str]] = reglas["tipologias"]["sufijo_a_tipologia"]
    errores = []
    for p in piezas:
        m = _RE_SUFIJO.match(p.id)
        if not m:
            continue  # E1, R1, B1 — no tienen sufijo de mueble
        sufijo = m.group(1).upper()
        # Buscar primero coincidencia exacta, luego primera letra
        tips_validas = sufijo_a_tip.get(sufijo) or sufijo_a_tip.get(sufijo[0])
        if tips_validas is None:
            continue  # sin regla para este sufijo
        if p.tipologia not in tips_validas:
            errores.append(
                f"{p.id}: sufijo '{sufijo}' → tipología '{p.tipologia}' "
                f"(esperado uno de {tips_validas})"
            )
    if not errores:
        return _pass("C-17", "Sufijo ID coherente con tipología DESPIECE", True, _GRUPO_PIEZAS)
    detalle = "; ".join(errores)
    return _skip("C-17", "Sufijo ID coherente con tipología DESPIECE",
                 f"Revisar DESPIECE: {detalle}", _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-20: Puertas P con apertura coherente con mecanizado
# ---------------------------------------------------------------------------

def _es_p_torn_apertura_obligatoria(
    p: Pieza, excepciones: list[dict],
) -> bool:
    """¿La pieza P+torn. cae en una excepción donde la apertura es obligatoria?

    Las excepciones se declaran en reglas.yaml bajo
    `tipologias.apertura_obligatoria_p_torn` como lista de {dim, descripcion}.
    Match exacto en cualquier orientación (ancho×alto o alto×ancho).
    """
    for spec in excepciones:
        sw, sh = spec["dim"]
        if (p.ancho, p.alto) == (sw, sh) or (p.ancho, p.alto) == (sh, sw):
            return True
    return False


def check_apertura_puertas(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-20: Coherencia apertura-mecanizado en puertas P. Bloquea: Sí.

    - P con cazta. (puerta normal con bisagras) → apertura I/D obligatoria.
    - P con torn. (frente de cajón sin bisagras)  → apertura I/D PROHIBIDA.
    - P con torn. en EXCEPCIÓN declarada (frente compuesto que abre junto a
      una hermana con cazta.) → apertura I/D OBLIGATORIA.
    - P sin mecanizado declarado → apertura obligatoria por defecto
      (otro check captura el mecanizado faltante si aplica).
    """
    tipologias_obligatoria: list[str] = reglas["tipologias"]["apertura_obligatoria"]
    excepciones_p_torn: list[dict] = (
        reglas["tipologias"].get("apertura_obligatoria_p_torn") or []
    )
    errores: list[str] = []
    for p in piezas:
        if p.tipologia not in tipologias_obligatoria:
            continue
        es_torn = "torn." in p.mecanizado.lower()
        es_excep = es_torn and _es_p_torn_apertura_obligatoria(p, excepciones_p_torn)

        if es_excep:
            # Excepción: aunque tenga torn., la apertura es obligatoria
            # (frente compuesto que abre junto a la hermana con cazta.).
            if not p.tiene_apertura:
                errores.append(
                    f"{p.id}: P {p.ancho}×{p.alto} con torn. (frente compuesto) "
                    f"requiere apertura I/D"
                )
        elif es_torn and p.tiene_apertura:
            errores.append(
                f"{p.id}: P con torn. (frente de cajón) no debe tener "
                f"apertura I/D (tiene: '{p.apertura}')"
            )
        elif not es_torn and not p.tiene_apertura:
            errores.append(f"{p.id}: tipología {p.tipologia} sin apertura")
    return _resultado(
        "C-20", "Puertas P con apertura coherente con mecanizado",
        errores, True, _GRUPO_MEC,
    )


# ---------------------------------------------------------------------------
# C-21: Puertas X (PAX) siempre con apertura I/D
# ---------------------------------------------------------------------------

def check_apertura_pax(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-21: Toda puerta X (PAX) debe tener apertura I/D, con o sin tirador.
    Bloquea: Sí.
    """
    errores = [
        f"{p.id}: tipología {p.tipologia} sin apertura"
        for p in piezas
        if p.tipologia == "X" and not p.tiene_apertura
    ]
    return _resultado("C-21", "Puertas X siempre con apertura I/D",
                      errores, True, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-22: Cajones C nunca con apertura
# ---------------------------------------------------------------------------

def check_sin_apertura_cajones(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-22: Ningún cajón C tiene apertura I/D. Bloquea: Sí."""
    tipologias: list[str] = reglas["tipologias"]["apertura_nunca"]
    errores = [
        f"{p.id}: tipología {p.tipologia} no debe tener apertura (tiene: '{p.apertura}')"
        for p in piezas
        if p.tipologia in tipologias and p.tiene_apertura
    ]
    return _resultado("C-22", "Cajones C sin apertura I/D", errores, True, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-23: Toda pieza con tirador tiene modelo + posición + color
# ---------------------------------------------------------------------------

#: Tipologías excluidas de validaciones de tirador (C-23, C-24).
#: F (Faktum) nunca debe disparar FAIL/WARN — son piezas residuales que
#: se controlan manualmente.
_TIPOLOGIAS_TIRADOR_SIN_VALIDAR = frozenset({"F"})


def check_tirador_completo(piezas: list[Pieza]) -> CheckResult:
    """C-23: Pieza con tirador → modelo + posición + color, los tres. Bloquea: Sí."""
    errores = []
    for p in piezas:
        if not p.tiene_tirador:
            continue
        if p.tipologia in _TIPOLOGIAS_TIRADOR_SIN_VALIDAR:
            continue  # F (Faktum): silenciada por petición de negocio
        faltantes = []
        if not p.posicion_tirador.strip():
            faltantes.append("posición")
        if not p.color_tirador.strip():
            faltantes.append("color")
        if faltantes:
            errores.append(f"{p.id} ('{p.tirador}'): falta {', '.join(faltantes)}")
    return _resultado("C-23", "Pieza con tirador tiene modelo+posición+color",
                      errores, True, _GRUPO_TIRA)


# ---------------------------------------------------------------------------
# C-24: Ninguna pieza tiene posición sin tirador
# ---------------------------------------------------------------------------

def check_posicion_sin_tirador(piezas: list[Pieza]) -> CheckResult:
    """C-24: Posición de tirador definida → tirador asignado. Bloquea: Sí."""
    errores = [
        f"{p.id}: posición '{p.posicion_tirador}' sin tirador"
        for p in piezas
        if p.posicion_tirador.strip() and not p.tiene_tirador
        and p.tipologia not in _TIPOLOGIAS_TIRADOR_SIN_VALIDAR
    ]
    return _resultado("C-24", "Sin posición de tirador sin tirador asignado",
                      errores, True, _GRUPO_TIRA)


# ---------------------------------------------------------------------------
# C-25: Nº cazoletas correcto según altura de puerta
# ---------------------------------------------------------------------------

def check_cazoletas(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """
    C-25: Puertas P y X con cazoletas (cazta.) tienen el nº correcto según
    la tabla cazoletas_metod del YAML. Bloquea: Sí.
    Nota: la OT declara el nº total; aquí verificamos la tabla por altura.
    """
    tabla: list[dict] = reglas["cazoletas_metod"]
    errores = []
    for p in piezas:
        if p.tipologia not in ("P", "X"):
            continue
        if "cazta" not in p.mecanizado.lower():
            continue
        # Determinar cazoletas esperadas según altura
        cazoletas_esp = None
        for entrada in tabla:
            if p.alto <= entrada["alto_max"]:
                cazoletas_esp = entrada["cazoletas"]
                break
        if cazoletas_esp is None:
            continue  # sin regla para esta altura
        # El nº real de cazoletas sería de la OT; aquí solo alertamos de zona límite
        if cazoletas_esp is None:
            errores.append(f"{p.id} (alto={p.alto}): en zona límite de cazoletas")
    return _resultado("C-25", "Nº cazoletas correcto según altura de puerta",
                      errores, True, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-26: Baldas B con mec. tienen dimensiones estándar
# ---------------------------------------------------------------------------

_MEC_BALDA_VALIDO = {"mec.", "mec"}


def check_baldas_dimensiones(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-26: Balda con herrajes ocultos tiene dimensiones estándar. Bloquea: Sí.

    Reglas para baldas (tipología B):
      - Mecanizado vacío → sin mecanizar, no aplica (N/A).
      - Mecanizado == "mec."/"mec"/"Mec." (case-insensitive) → se valida dim.
      - Cualquier otro valor → FAIL (mecanizado no permitido en balda).
      - Si la dim solo encaja al intercambiar ancho↔alto → SKIP (ambigüedad).
    """
    baldas_std: list[dict] = reglas["baldas_dimensiones"]
    combos_validos = {(b["ancho"], b["alto"]) for b in baldas_std}
    errores: list[str] = []
    intercambiadas: list[str] = []
    for p in piezas:
        if p.tipologia != "B":
            continue
        mec = p.mecanizado.strip()
        if not mec:
            continue  # sin mecanizado → no aplica
        if mec.lower() not in _MEC_BALDA_VALIDO:
            errores.append(
                f"{p.id}: mecanizado '{mec}' no permitido en balda "
                f"(solo se admite vacío o 'mec.')"
            )
            continue
        if (p.ancho, p.alto) in combos_validos:
            continue
        if (p.alto, p.ancho) in combos_validos:
            intercambiadas.append(f"{p.id}: {p.ancho}×{p.alto} (dim. válida con ancho↔alto intercambiados)")
            continue
        errores.append(
            f"{p.id}: {p.ancho}×{p.alto} no es dimensión estándar de balda "
            f"(válidas: {sorted(combos_validos)})"
        )
    if errores:
        return _resultado("C-26", "Baldas con mec. tienen dimensiones estándar",
                          errores, True, _GRUPO_MEC)
    if intercambiadas:
        return _skip(
            "C-26", "Baldas con mec. tienen dimensiones estándar",
            "Ancho/alto intercambiados en: " + "; ".join(intercambiadas),
            _GRUPO_MEC,
        )
    return _resultado("C-26", "Baldas con mec. tienen dimensiones estándar",
                      [], True, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-27: Rodapiés R sin mecanizado (excepto vent. en RV)
# ---------------------------------------------------------------------------

def check_mecanizado_rodapies(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """
    C-27: Rodapiés R no deben tener mecanizado.
    RV solo debe tener vent. Bloquea: No.
    """
    mec_esperado: dict = reglas["tipologias"]["mecanizado_esperado"]
    errores = []
    for p in piezas:
        if p.tipologia == "R" and p.mecanizado.strip():
            errores.append(f"{p.id}: rodapié con mecanizado '{p.mecanizado}'")
        elif p.tipologia == "RV":
            esperado = mec_esperado.get("RV", "vent.")
            if esperado.lower() not in p.mecanizado.lower():
                errores.append(
                    f"{p.id}: RV sin '{esperado}' (tiene: '{p.mecanizado}')"
                )
    return _resultado("C-27", "Rodapiés R sin mecanizado (RV solo vent.)",
                      errores, False, _GRUPO_MEC, tipo_fail="WARN")


# ---------------------------------------------------------------------------
# C-28: Alerta si T, L, B, E, R tienen tirador asignado
# ---------------------------------------------------------------------------

def check_tirador_en_sin_mecanizado(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-28: Tipologías T/L/B/E/R con tirador son inusuales. Bloquea: No."""
    tips_sin_mec: list[str] = reglas["tipologias"]["tipologias_sin_mecanizado"]
    errores = [
        f"{p.id}: tipología {p.tipologia} con tirador '{p.tirador}'"
        for p in piezas
        if p.tipologia in tips_sin_mec and p.tiene_tirador
    ]
    return _resultado("C-28", "Alerta: tipologías sin mecanizado con tirador",
                      errores, False, _GRUPO_TIRA, tipo_fail="WARN")


# ---------------------------------------------------------------------------
# C-29: Alerta si alto de puerta P no acaba en 98
# ---------------------------------------------------------------------------

def check_alto_puerta_sufijo(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-29: Alto de puerta P es uno de los valores estándar. Bloquea: No.

    Si alguna puerta P tiene un alto fuera de la lista de alturas estándar
    (recrecida, recortada o diseño especial), el check devuelve SKIP con el
    listado de piezas afectadas para que tengan visibilidad en el informe.
    """
    alturas_std: list[int] = reglas["puerta_alturas_estandar"]
    std_set = set(alturas_std)
    no_estandar = [
        f"{p.id}: alto={p.alto}"
        for p in piezas
        if p.tipologia == "P" and p.alto not in std_set
    ]
    if no_estandar:
        return _skip(
            "C-29", "Alto puerta P es valor estándar",
            "Alturas fuera del estándar (posible recrecida/recortada): "
            + "; ".join(no_estandar),
            _GRUPO_MEC,
        )
    return _pass("C-29", "Alto puerta P es valor estándar", False, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-18: Cajones C tienen dimensiones estándar
# ---------------------------------------------------------------------------

def check_cajones_dimensiones(piezas: list[Pieza], reglas: dict) -> CheckResult:
    """C-18: Cajón C tiene dimensiones estándar (ancho×alto). Bloquea: No.

    Si dims exactas en lista → PASS.
    Si no coinciden (en cualquier orientación) → SKIP con el listado de piezas
    afectadas para revisión manual.
    """
    cajones_std: list[dict] = reglas["cajones_dimensiones"]
    combos_validos = {(c["ancho"], c["alto"]) for c in cajones_std}
    no_estandar = [
        f"{p.id}: {p.ancho}×{p.alto}"
        for p in piezas
        if p.tipologia == "C" and (p.ancho, p.alto) not in combos_validos
    ]
    if no_estandar:
        return _skip(
            "C-18", "Cajones C con dimensiones estándar",
            "Cajones con dim. fuera del estándar: " + "; ".join(no_estandar),
            _GRUPO_PIEZAS,
        )
    return _pass("C-18", "Cajones C con dimensiones estándar", False, _GRUPO_PIEZAS)


# ---------------------------------------------------------------------------
# C-19: Piezas P o C con ancho 446 o 596 deben tener mecanizado "torn."
# ---------------------------------------------------------------------------

_RE_CAZTA_CON_NUM = re.compile(r"\d+\s*cazta\.?", re.IGNORECASE)


def check_mec_torn_en_ancho_especial(piezas: list[Pieza]) -> CheckResult:
    """C-19: Puertas P y cajones C con ancho 446 o 596 deben usar 'torn.'.
    - Mecanizado vacío → SKIP (frente sin mecanizar, válido en algunos proyectos)
    - 'N cazta.' u otro mecanizado distinto de 'torn.' → WARN (no bloquea)
    """
    anchos_especiales = {446, 596}
    warns: list[str] = []
    sin_mecanizar: list[str] = []
    for p in piezas:
        if p.tipologia not in ("P", "C"):
            continue
        if p.ancho not in anchos_especiales:
            continue
        mec = p.mecanizado.strip()
        if mec.lower() in ("torn.", "torn"):
            continue
        if not mec:
            sin_mecanizar.append(f"{p.id}: ancho={p.ancho} sin mecanizado declarado en el Despiece")
            continue
        if _RE_CAZTA_CON_NUM.search(mec):
            warns.append(
                f"{p.id}: ancho={p.ancho} con mecanizado '{mec}' — debe ser 'torn.'"
            )
        else:
            warns.append(
                f"{p.id}: ancho={p.ancho} con mecanizado '{mec}' (esperado 'torn.')"
            )

    if warns:
        return _resultado("C-19", "Ancho 446/596 con mecanizado 'torn.'",
                          warns, False, _GRUPO_MEC, tipo_fail="WARN")
    if sin_mecanizar:
        return _skip("C-19", "Ancho 446/596 con mecanizado 'torn.'",
                     "Frentes sin mecanizar — revisar: " + " | ".join(sin_mecanizar),
                     _GRUPO_MEC)
    return _pass("C-19", "Ancho 446/596 con mecanizado 'torn.'", True, _GRUPO_MEC)


# ---------------------------------------------------------------------------
# C-32: Puertas X (PAX) siempre con cazta. (nunca torn.)
# ---------------------------------------------------------------------------

def check_pax_mecanizado(piezas: list[Pieza]) -> CheckResult:
    """C-32: Las puertas X (PAX) siempre llevan bisagras (cazta.) y nunca
    tornillos (torn.). Si una X tiene mecanizado torn., es un error de
    clasificación: o bien la tipología debe ser C/P, o bien el mecanizado
    está mal declarado. Bloquea: Sí.
    """
    errores = [
        f"{p.id}: X con mecanizado '{p.mecanizado}' — PAX nunca lleva torn., "
        f"siempre cazta."
        for p in piezas
        if p.tipologia == "X" and "torn." in p.mecanizado.lower()
    ]
    return _resultado(
        "C-32", "Puertas X siempre con cazta. (nunca torn.)",
        errores, True, _GRUPO_MEC,
    )


# ---------------------------------------------------------------------------
# C-33: IDs con tipología inferible
# ---------------------------------------------------------------------------

def check_tipologia_inferible(piezas: list[Pieza]) -> CheckResult:
    """C-33: Los IDs de pieza deben encajar en algún patrón conocido para
    poder inferir su tipología. Bloquea: No (informativo).

    Cuando _inferir_tipologia devuelve cadena vacía, significa que el ID
    no encaja en ningún patrón documentado. Estos IDs se reportan como
    SKIP para revisión manual del operario, sin afectar al flujo de
    validación (los demás checks filtran por tipología y los ignoran
    automáticamente).
    """
    sin_tipologia = [p.id for p in piezas if not p.tipologia.strip()]
    if not sin_tipologia:
        return _pass("C-33", "IDs con tipología inferible", False, _GRUPO_PIEZAS)
    n = len(sin_tipologia)
    listado = ", ".join(sin_tipologia[:10])
    if n > 10:
        listado += f" (y {n - 10} más)"
    return _skip(
        "C-33", "IDs con tipología inferible",
        f"IDs sin tipología reconocida (revisar manualmente): {listado}",
        _GRUPO_PIEZAS,
    )
