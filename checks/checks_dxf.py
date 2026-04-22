"""
checks/checks_dxf.py — C-30 a C-43: Validación de layers en ficheros DXF.

Los checks operan sobre la lista completa de DXFDoc y, cuando aplica,
también reciben las piezas del DESPIECE y/o datos de la OT.
"""

from __future__ import annotations

from core.modelos import CheckResult, DXFDoc, OTData, Pieza
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO = "DXF"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _todas_layers(dxfs: list[DXFDoc]) -> set[str]:
    """Unión de todos los layers de todos los DXFs."""
    return set().union(*(d.layers for d in dxfs))


def _todas_layers_geo(dxfs: list[DXFDoc]) -> set[str]:
    """Unión de todos los layers CON geometría de todos los DXFs."""
    return set().union(*(d.layers_con_geometria for d in dxfs))


def _sum_conteo(dxfs: list[DXFDoc], layer: str) -> int:
    """Suma de entidades de un layer en todos los DXFs."""
    return sum(d.conteos_layer.get(layer, 0) for d in dxfs)


def _si_no_dxfs(id_check: str, desc: str, dxfs: list[DXFDoc]) -> CheckResult | None:
    if not dxfs:
        return _skip(id_check, desc, "Sin DXFs disponibles", _GRUPO)
    return None


# ---------------------------------------------------------------------------
# C-30: Layer CONTROL ausente en todos los DXFs
# ---------------------------------------------------------------------------

def check_layer_control(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-30: Layer CONTROL no debe aparecer en ningún DXF. Bloquea: Sí.

    El layer CONTROL es un artefacto interno de Rhinoceros que indica un
    fallo en el proceso de exportación. Su presencia invalida el fichero.
    """
    s = _si_no_dxfs("C-30", "Layer CONTROL ausente en todos los DXFs", dxfs)
    if s:
        return s
    prohibidos: list[str] = reglas["layers"]["prohibidos_control"]
    errores = []
    for dxf in dxfs:
        for layer in prohibidos:
            if layer in dxf.layers:
                errores.append(f"{dxf.nombre}: layer '{layer}' presente (no debe existir)")
    return _resultado("C-30", "Layer CONTROL ausente en todos los DXFs",
                      errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-31: Layer "0" sin geometría operativa
# ---------------------------------------------------------------------------

def check_layer_0_sin_geometria(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-31: El layer '0' no debe tener geometría operativa. Bloquea: Sí."""
    s = _si_no_dxfs("C-31", "Layer '0' sin geometría operativa", dxfs)
    if s:
        return s
    layers_prohibidos: list[str] = reglas["layers"]["sin_geometria_operativa"]
    errores = []
    for dxf in dxfs:
        for layer in layers_prohibidos:
            if layer in dxf.layers_con_geometria:
                errores.append(f"{dxf.nombre}: layer '{layer}' tiene geometría operativa")
    return _resultado("C-31", "Layer '0' sin geometría operativa", errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-32: Layers internos de Rhino ausentes en DXFs exportados
# ---------------------------------------------------------------------------

def check_layers_rhino_ausentes(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-32: Layers de Rhino (HORNACINAS, FAKTUM, etc.) no deben aparecer. Bloquea: Sí."""
    s = _si_no_dxfs("C-32", "Layers internos Rhino ausentes", dxfs)
    if s:
        return s
    rhino_internos: list[str] = reglas["layers"]["rhino_internos"]
    todas = _todas_layers(dxfs)
    encontrados = [lay for lay in rhino_internos if lay in todas]
    return _resultado("C-32", "Layers internos Rhino ausentes en DXFs",
                      [f"Layer Rhino detectado: '{l}'" for l in encontrados], True, _GRUPO)


# ---------------------------------------------------------------------------
# C-33: Layer 0_ANOTACIONES presente en todos los DXFs
# ---------------------------------------------------------------------------

def check_layer_anotaciones(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-33: 0_ANOTACIONES presente en cada DXF. Bloquea: Sí."""
    s = _si_no_dxfs("C-33", "Layer 0_ANOTACIONES en todos los DXFs", dxfs)
    if s:
        return s
    obligatorios: list[str] = reglas["layers"]["obligatorios"]
    errores = []
    for dxf in dxfs:
        for layer in obligatorios:
            if layer not in dxf.layers:
                errores.append(f"{dxf.nombre}: falta layer '{layer}'")
    return _resultado("C-33", "Layer 0_ANOTACIONES en todos los DXFs", errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-34: Layer 13-BISELAR presente en tableros LAM y LIN
# ---------------------------------------------------------------------------

def check_layer_biselar_lam_lin(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-34: Layer 13-BISELAR-EM5-Z0_8 en cada DXF de gama LAM o LIN. Bloquea: Sí."""
    s = _si_no_dxfs("C-34", "Layer biselar en tableros LAM/LIN", dxfs)
    if s:
        return s
    layers_biselar: list[str] = reglas["layers"]["obligatorios_lam_lin"]
    errores = []
    for dxf in dxfs:
        if dxf.gama not in ("LAM", "LIN"):
            continue
        for layer in layers_biselar:
            if layer not in dxf.layers:
                errores.append(
                    f"{dxf.nombre} (gama {dxf.gama}): falta layer '{layer}'"
                )
    return _resultado("C-34", "Layer biselar en tableros LAM/LIN", errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-35: Layer de corte perimetral correcto según gama y acabado
# ---------------------------------------------------------------------------

def check_corte_perimetral(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """
    C-35: Cada DXF tiene el layer de corte perimetral correcto.

    Regla a nivel de proyecto:
    - Si TODOS los acabados LAC del proyecto son estándar (Roto/Crema/Blanco/Seda)
      → cada LAC usa 10_12-CUTEXT-EM5-Z18
    - Si CUALQUIER acabado LAC del proyecto es no estándar (Agave, Marga, Noche…)
      → TODOS los LAC del proyecto usan 10_12-CONTORNO LACA (incluso Roto/Seda)
    - LAM/LIN/WOO → siempre 10_12-CUTEXT-EM5-Z18
    Bloquea: Sí.
    """
    s = _si_no_dxfs("C-35", "Layer corte perimetral correcto por gama/acabado", dxfs)
    if s:
        return s
    cp = reglas["layers"]["corte_perimetral"]
    layer_estandar = cp["estandar"]
    layer_laca_no_std = cp["laca_no_estandar"]
    lac_std = {a.lower() for a in cp.get("lac_acabados_estandar", [])}

    proyecto_tiene_lac_no_std = any(
        dxf.gama == "LAC" and dxf.acabado.lower() not in lac_std
        for dxf in dxfs
    )

    errores = []
    for dxf in dxfs:
        if dxf.gama == "LAC":
            layer_esperado = layer_laca_no_std if proyecto_tiene_lac_no_std else layer_estandar
        else:
            layer_esperado = layer_estandar

        if layer_esperado not in dxf.layers:
            errores.append(
                f"{dxf.nombre} ({dxf.gama} {dxf.acabado}): "
                f"falta layer corte '{layer_esperado}'"
            )
    return _resultado("C-35", "Layer corte perimetral correcto por gama/acabado",
                      errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-36: Layer desbaste tirador coherente con color tirador del DESPIECE
# ---------------------------------------------------------------------------

def check_layer_desbaste_tirador(
    dxfs: list[DXFDoc], piezas: list[Pieza], reglas: dict
) -> CheckResult:
    """
    C-36: Para cada color de tirador en el DESPIECE, el layer de desbaste
    correspondiente debe estar presente en al menos un DXF. Bloquea: Sí.
    """
    s = _si_no_dxfs("C-36", "Layer desbaste tirador coherente con color tirador", dxfs)
    if s:
        return s

    desbaste: dict[str, str] = reglas["desbaste_tirador"]
    todas = _todas_layers(dxfs)
    layer_default = desbaste.get("_DEFAULT", "")
    modelos_con_geometria = {
        m.upper() for m in reglas.get("tiradores_con_geometria_dxf", [])
    }

    errores = []
    colores_vistos: set[str] = set()
    for p in piezas:
        if not p.tiene_tirador or not p.color_tirador:
            continue
        if p.tirador.upper() not in modelos_con_geometria:
            continue  # modelo sin geometría en nesting → no deja layer
        color = p.color_tirador.upper()
        if color in colores_vistos:
            continue
        colores_vistos.add(color)

        # Prioridad: color exacto > _LIN si gama LIN > _DEFAULT
        layer_esperado = (
            desbaste.get(color)
            or (desbaste.get("_LIN") if p.gama == "LIN" else None)
            or layer_default
        )
        if layer_esperado and layer_esperado not in todas:
            errores.append(
                f"Color tirador '{color}': layer '{layer_esperado}' no encontrado en DXFs"
            )
    return _resultado("C-36", "Layer desbaste tirador coherente con color tirador",
                      errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-37: Recuento HANDCUT == nº tiradores declarados en OT
# ---------------------------------------------------------------------------

def check_handcut_vs_tiradores(
    dxfs: list[DXFDoc], ot: OTData, reglas: dict
) -> CheckResult:
    """C-37: Si hay tiradores que generan geometría (Round/Square/Pill), el layer
    HANDCUT debe estar presente en los DXFs. Tiradores sin geometría (Superline,
    Bar, Knob…) no generan HANDCUT → SKIP. Bloquea: Sí."""
    s = _si_no_dxfs("C-37", "Recuento HANDCUT == tiradores OT", dxfs)
    if s:
        return s
    if ot.num_tiradores == 0:
        return _skip("C-37", "Recuento HANDCUT == tiradores OT",
                     "OT sin tiradores declarados", _GRUPO)

    modelos_con_handcut: set[str] = {
        m for m in ot.modelos_tiradores
        if m.title() in reglas.get("tiradores_con_geometria_dxf", [])
    }

    if not modelos_con_handcut:
        modelos_str = ", ".join(ot.modelos_tiradores) if ot.modelos_tiradores else "desconocido"
        return _skip(
            "C-37", "Recuento HANDCUT == tiradores OT",
            f"Tirador '{modelos_str}' no genera HANDCUT en DXF", _GRUPO,
        )

    layer_handcut: str = reglas["layers"]["tirador_handcut"]
    n_handcut = _sum_conteo(dxfs, layer_handcut)

    if n_handcut == ot.num_tiradores:
        return _pass("C-37", "Recuento HANDCUT == tiradores OT", True, _GRUPO)
    return _fail(
        "C-37", "Recuento HANDCUT == tiradores OT",
        f"DXF: {n_handcut} entidades HANDCUT | OT: {ot.num_tiradores} tiradores",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-38: Piezas con torn. tienen layers 3-DRILL-* en DXFs
# ---------------------------------------------------------------------------

def check_cajones_drill(
    dxfs: list[DXFDoc], piezas: list[Pieza], reglas: dict
) -> CheckResult:
    """C-38: Si hay cajones con torn., los layers DRILL deben existir en DXFs. Bloquea: Sí."""
    s = _si_no_dxfs("C-38", "Cajones con torn. tienen layers DRILL en DXFs", dxfs)
    if s:
        return s

    cajones_con_torn = [p for p in piezas if "torn" in p.mecanizado.lower()]
    if not cajones_con_torn:
        return _skip("C-38", "Cajones con torn. tienen layers DRILL en DXFs",
                     "Sin piezas con torn.", _GRUPO)

    drill_layers: list[str] = reglas["layers"]["cajones_drill"]
    todas = _todas_layers(dxfs)
    presentes = [l for l in drill_layers if l in todas]

    if presentes:
        return _pass("C-38", "Cajones con torn. tienen layers DRILL en DXFs", True, _GRUPO)
    return _fail(
        "C-38", "Cajones con torn. tienen layers DRILL en DXFs",
        f"Hay {len(cajones_con_torn)} cajones con torn. pero ningún layer DRILL "
        f"({', '.join(drill_layers)}) en DXFs",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-39: Piezas con cazta. tienen layers POCKET en DXFs
# ---------------------------------------------------------------------------

def check_bisagras_pocket(
    dxfs: list[DXFDoc], piezas: list[Pieza], reglas: dict
) -> CheckResult:
    """C-39: Si hay piezas con cazta., layers 6/7-POCKET deben existir en DXFs. Bloquea: Sí."""
    s = _si_no_dxfs("C-39", "Piezas con cazta. tienen layers POCKET en DXFs", dxfs)
    if s:
        return s

    piezas_cazta = [p for p in piezas if "cazta" in p.mecanizado.lower()]
    if not piezas_cazta:
        return _skip("C-39", "Piezas con cazta. tienen layers POCKET en DXFs",
                     "Sin piezas con cazta.", _GRUPO)

    pocket_layers: list[str] = reglas["layers"]["bisagras_metod"] + reglas["layers"]["bisagras_pax"]
    todas = _todas_layers(dxfs)
    presentes = [l for l in pocket_layers if l in todas]

    if presentes:
        return _pass("C-39", "Piezas con cazta. tienen layers POCKET en DXFs", True, _GRUPO)
    return _fail(
        "C-39", "Piezas con cazta. tienen layers POCKET en DXFs",
        f"Hay {len(piezas_cazta)} piezas con cazta. pero sin layer POCKET en DXFs",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-40: Recuento layer REJILLA == ventilación declarada en OT
# ---------------------------------------------------------------------------

def check_ventilacion_rejilla(
    dxfs: list[DXFDoc], ot: OTData, reglas: dict
) -> CheckResult:
    """
    C-40: Layer 8-REJILLA presente en DXFs ↔ OT declara ventilación.
    Check de presencia/ausencia — el nº de entidades del layer no es comparable
    al nº de piezas físicas (cada rejilla genera múltiples entidades de geometría).
    Bloquea: Sí.
    """
    s = _si_no_dxfs("C-40", "Recuento REJILLA == ventilación OT", dxfs)
    if s:
        return s
    if ot.num_ventilacion == 0:
        return _skip("C-40", "Recuento REJILLA == ventilación OT",
                     "OT sin ventilación declarada", _GRUPO)

    layer_vent: str = reglas["layers"]["ventilacion"]
    hay_rejilla = any(layer_vent in dxf.layers for dxf in dxfs)
    ot_declara = ot.num_ventilacion > 0

    if hay_rejilla and ot_declara:
        return _pass("C-40", "Recuento REJILLA == ventilación OT", True, _GRUPO)
    if not hay_rejilla and ot_declara:
        return _fail(
            "C-40", "Recuento REJILLA == ventilación OT",
            f"OT declara {ot.num_ventilacion} rejilla(s) pero layer '{layer_vent}' ausente en DXFs",
            True, _GRUPO,
        )
    # hay_rejilla=True, ot_declara=False — no puede ocurrir aquí (skip arriba)
    return _pass("C-40", "Recuento REJILLA == ventilación OT", True, _GRUPO)


# ---------------------------------------------------------------------------
# C-41: Layer MECANISMO_HORNACINA coherente con OT
# ---------------------------------------------------------------------------

def check_mecanismo_hornacina(
    dxfs: list[DXFDoc], ot: OTData, reglas: dict
) -> CheckResult:
    """C-41: Layer MECANISMO_HORNACINA presente ↔ OT declara colgadores. Bloquea: Sí.

    Reglas:
      - Layer presente en DXFs → OT debe declarar "Colgador de hornacina: N" con N≥1.
      - Layer ausente en DXFs → OT debe declarar "Colgador de hornacina: No" (N=0).
      - OT sin el campo → SKIP.
    """
    s = _si_no_dxfs("C-41", "Layer hornacina coherente con OT", dxfs)
    if s:
        return s
    if ot.colgadores_hornacina is None:
        return _skip("C-41", "Layer hornacina coherente con OT",
                     "OT sin dato de colgador de hornacina", _GRUPO)

    layer_hor: str = reglas["layers"]["colgador_hornacina"]
    todas = _todas_layers(dxfs)
    tiene_layer = layer_hor in todas
    n = ot.colgadores_hornacina

    if tiene_layer and n == 0:
        return _fail("C-41", "Layer hornacina coherente con OT",
                     f"Layer '{layer_hor}' en DXFs pero OT declara 'No' (0 colgadores). "
                     f"La OT debería indicar 'Colgador de hornacina: N' con N≥1",
                     True, _GRUPO)
    if not tiene_layer and n >= 1:
        return _fail("C-41", "Layer hornacina coherente con OT",
                     f"OT declara {n} colgador(es) pero falta layer '{layer_hor}' en DXFs",
                     True, _GRUPO)
    return _pass("C-41", "Layer hornacina coherente con OT", True, _GRUPO)


# ---------------------------------------------------------------------------
# C-42: Layers TIRANTE coherentes con OT
# ---------------------------------------------------------------------------

def check_tirantes(dxfs: list[DXFDoc], ot: OTData, reglas: dict) -> CheckResult:
    """C-42: Layers TIRANTE presentes ↔ OT declara tensores. Bloquea: Sí."""
    s = _si_no_dxfs("C-42", "Layers TIRANTE coherentes con OT", dxfs)
    if s:
        return s
    if ot.tiene_tensores is None:
        return _skip("C-42", "Layers TIRANTE coherentes con OT",
                     "OT sin dato de tensores", _GRUPO)

    tirante_layers: list[str] = reglas["layers"]["tensores"]
    todas = _todas_layers(dxfs)
    layers_presentes = [l for l in tirante_layers if l in todas]

    if ot.tiene_tensores and not layers_presentes:
        return _fail("C-42", "Layers TIRANTE coherentes con OT",
                     "OT declara tensores pero no hay layers TIRANTE en DXFs",
                     True, _GRUPO)
    if not ot.tiene_tensores and layers_presentes:
        return _fail("C-42", "Layers TIRANTE coherentes con OT",
                     f"Layers TIRANTE en DXFs pero OT no declara tensores: "
                     f"{layers_presentes}",
                     True, _GRUPO)
    return _pass("C-42", "Layers TIRANTE coherentes con OT", True, _GRUPO)


# ---------------------------------------------------------------------------
# C-43: Layers en desuso detectados
# ---------------------------------------------------------------------------

def check_layers_desuso(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-43: Layers en desuso presentes → advertencia para revisión. Bloquea: No."""
    s = _si_no_dxfs("C-43", "Layers en desuso ausentes", dxfs)
    if s:
        return s
    desuso: list[str] = reglas["layers"]["desuso"]
    todas = _todas_layers(dxfs)
    encontrados = [l for l in desuso if l in todas]
    return _resultado("C-43", "Layers en desuso ausentes",
                      [f"Layer en desuso detectado: '{l}'" for l in encontrados],
                      False, _GRUPO, tipo_fail="WARN")


# ---------------------------------------------------------------------------
# C-44: Distancia entre bisagras múltiplo exacto del paso (METOD=50mm, PAX=32mm)
# ---------------------------------------------------------------------------

import math as _math


def _bisagra_nearest(cx: float, cy: float, pool: list[dict]) -> tuple[dict | None, float]:
    """Devuelve (círculo_más_cercano, distancia) del pool dado."""
    if not pool:
        return None, float("inf")
    best = min(pool, key=lambda c: _math.hypot(c["x"] - cx, c["y"] - cy))
    return best, _math.hypot(best["x"] - cx, best["y"] - cy)


def check_distancia_bisagras(dxfs: list[DXFDoc], reglas: dict) -> CheckResult:
    """C-44: Distancia entre bisagras debe ser múltiplo exacto del paso.

    METOD (6-POCKET companion) → paso 50 mm.
    PAX   (6A-POCKET companion) → paso 32 mm.
    Tolerancia: cero — el residuo dist % paso debe ser exactamente 0.
    Bloquea: Sí.
    """
    ID = "C-44"
    DESC = "Distancia entre bisagras múltiplo exacto de paso"

    s = _si_no_dxfs(ID, DESC, dxfs)
    if s:
        return s

    cfg = reglas["bisagra_distancia"]
    layer_7p: str = cfg["layer_7pocket"]
    layer_6m: str = cfg["layer_6pocket_metod"]
    layer_6p: str = cfg["layer_6pocket_pax"]
    paso_metod: int = int(cfg["paso_metod"])
    paso_pax: int = int(cfg["paso_pax"])
    tol_grupo: float = 5.0  # mm — tolerancia para agrupar círculos en la misma puerta

    errores: list[str] = []
    algun_tablero_con_bisagras = False

    for dxf in dxfs:
        c7  = [c for c in dxf.circulos if c["layer"] == layer_7p]
        c6m = [c for c in dxf.circulos if c["layer"] == layer_6m]
        c6p = [c for c in dxf.circulos if c["layer"] == layer_6p]

        if not c7 or (not c6m and not c6p):
            continue  # sin bisagras en este tablero
        algun_tablero_con_bisagras = True

        # --- Clasificar cada 7-POCKET: tipo (METOD/PAX) y orientación (V/H) ---
        clasificados: list[dict] = []
        for c in c7:
            _, d_m = _bisagra_nearest(c["x"], c["y"], c6m)
            comp_p, d_p = _bisagra_nearest(c["x"], c["y"], c6p)
            es_metod = d_m <= d_p
            paso = paso_metod if es_metod else paso_pax
            tipo = "METOD" if es_metod else "PAX"
            comp, _ = _bisagra_nearest(c["x"], c["y"], c6m if es_metod else c6p)
            if comp is None:
                continue
            dx = abs(comp["x"] - c["x"])
            dy = abs(comp["y"] - c["y"])
            # El companion se desplaza a lo largo de la columna de bisagras:
            # |dY| > |dX| → columna en Y → puerta VERTICAL → agrupar por X
            # |dX| > |dY| → columna en X → puerta HORIZONTAL → agrupar por Y
            orient = "V" if dy >= dx else "H"
            clasificados.append({**c, "tipo": tipo, "paso": paso, "orient": orient})

        # --- Agrupar por puerta (coordenada constante) ---
        grupos: dict[tuple, list[dict]] = {}
        for item in clasificados:
            coord_key = item["x"] if item["orient"] == "V" else item["y"]
            found = next(
                (k for k in grupos
                 if k[0] == item["orient"]
                 and k[1] == item["tipo"]
                 and abs(k[2] - coord_key) < tol_grupo),
                None,
            )
            if found is None:
                found = (item["orient"], item["tipo"], coord_key)
                grupos[found] = []
            grupos[found].append(item)

        # --- Verificar distancias con tolerancia cero ---
        for (orient, tipo, coord_key), items in grupos.items():
            paso = items[0]["paso"]
            vals = sorted(i["y"] for i in items) if orient == "V" \
                else sorted(i["x"] for i in items)

            if len(vals) < 2:
                continue

            eje = "X" if orient == "V" else "Y"

            # Agrupar en cadenas de puerta: un gap no-múltiplo de paso puede
            # ser (a) un límite de nesting entre puertas distintas o (b) un
            # error real de posición. Distinguir:
            #   • Gap no-múltiplo entre dos cadenas de ≥2 círculos → límite
            #     de nesting (puertas contiguas en el tablero): ignorar.
            #   • Gap no-múltiplo conectado a una cadena de 1 círculo → bisagra
            #     huérfana o fuera de posición → error real.
            cadenas: list[list[float]] = []
            puentes: list[tuple[float, int]] = []  # (dist, left_idx)
            cadena_actual: list[float] = [vals[0]]
            for k in range(len(vals) - 1):
                dist = round(abs(vals[k + 1] - vals[k]), 4)
                if dist % paso == 0.0:
                    cadena_actual.append(vals[k + 1])
                else:
                    cadenas.append(cadena_actual)
                    puentes.append((dist, len(cadenas) - 1))
                    cadena_actual = [vals[k + 1]]
            cadenas.append(cadena_actual)

            for dist, left_idx in puentes:
                right_idx = left_idx + 1
                # Solo es error si alguna de las dos cadenas adyacentes
                # tiene un único círculo (no es una puerta válida de ≥2 bisagras)
                if len(cadenas[left_idx]) < 2 or len(cadenas[right_idx]) < 2:
                    nearest_n = round(dist / paso)
                    desv = dist - nearest_n * paso
                    errores.append(
                        f"{dxf.nombre} — bisagra {tipo} "
                        f"({'vertical' if orient == 'V' else 'horizontal'}, "
                        f"{eje}≈{coord_key:.0f}): "
                        f"distancia {dist}mm no es múltiplo de {paso}mm "
                        f"(más cercano {nearest_n}×{paso}={nearest_n * paso}mm, "
                        f"desv. {desv:+.1f}mm)"
                    )

    if not algun_tablero_con_bisagras:
        return _skip(ID, DESC, "Sin circles 7-POCKET con companion en los DXFs", _GRUPO)
    return _resultado(ID, DESC, errores, True, _GRUPO)
