"""
checks/checks_extraccion.py — C-70 a C-80: cruces del CSV EXTRACCION
contra OT y DESPIECE.

El EXTRACCION es un tercer testigo independiente. Si discrepa con OT o
DESPIECE no sabemos cuál es correcto, así que la mayoría de checks
bloquean producción (FAIL). Excepciones (WARN o SKIP):
  - C-70 (cabecera fija OT)        → WARN
  - C-73 (metros canto, tolerable) → WARN
  - C-75 (prioridad INC)           → WARN
  - C-80 (baldas con herrajes)     → WARN

Parámetros comunes:
    extr:    ExtraccionData
    ot:      OTData (puede ser instancia vacía si no se extrajo)
    piezas:  list[Pieza] del DESPIECE
    reglas:  dict cargado por cargar_reglas()  (sección 'extraccion')
    naming:  dict {cod_tab_lower: (gama_largo, acabado_largo)} cargado al inicio
"""

from __future__ import annotations

from core.modelos import CheckResult, ExtraccionData, OTData, Pieza
from core.extractor_extraccion import cod_tab_a_clave_canonica
from checks._helpers import _pass, _fail, _warn, _skip, _resultado

_GRUPO = "Extraccion"


# ---------------------------------------------------------------------------
# C-70: cabecera fija (Nº OT, semana, fechas) EXTRACCION ↔ OT
# ---------------------------------------------------------------------------

def check_cabecera_ot(extr: ExtraccionData, ot: OTData) -> CheckResult:
    """C-70: WARN. Compara los campos fijos de cabecera entre EXTRACCION y OT.

    Si un campo está vacío en uno de los documentos la comparación se omite
    (lo reporta C-00/extracción defectuosa).
    """
    desc = "Cabecera (Nº OT, semana, fechas) EXTRACCION ↔ OT"
    errores: list[str] = []

    if extr.numero_ot and ot.numero_ot and extr.numero_ot != ot.numero_ot:
        errores.append(f"Nº OT: EXTRACCION '{extr.numero_ot}' ≠ OT '{ot.numero_ot}'")

    # Semana: en OT viene como "Semana 22"; en EXTRACCION solo "22".
    sem_e = extr.semana.strip()
    sem_o = "".join(ch for ch in ot.semana if ch.isdigit())
    if sem_e and sem_o and sem_e != sem_o:
        errores.append(f"Semana: EXTRACCION '{sem_e}' ≠ OT '{sem_o}'")

    if extr.fecha_entrada and ot.fecha_entrada and extr.fecha_entrada != ot.fecha_entrada:
        errores.append(
            f"Fecha entrada: EXTRACCION '{extr.fecha_entrada}' ≠ OT '{ot.fecha_entrada}'"
        )
    if extr.fecha_salida and ot.fecha_salida and extr.fecha_salida != ot.fecha_salida:
        errores.append(
            f"Fecha salida: EXTRACCION '{extr.fecha_salida}' ≠ OT '{ot.fecha_salida}'"
        )

    return _resultado("C-70", desc, errores, False, _GRUPO, tipo_fail="WARN")


# ---------------------------------------------------------------------------
# C-71: recuentos críticos (piezas, tiradores, ventilación, tensores)
# ---------------------------------------------------------------------------

def check_recuentos_criticos(extr: ExtraccionData, ot: OTData) -> CheckResult:
    """C-71: FAIL bloqueante. Estos son los datos que ven CNC y embalaje."""
    desc = "Recuentos críticos (piezas, tiradores, ventilación, tensores) ↔ OT"
    errores: list[str] = []

    if ot.num_piezas and extr.piezas and extr.piezas != ot.num_piezas:
        errores.append(f"Piezas: EXTRACCION {extr.piezas} ≠ OT {ot.num_piezas}")
    if ot.num_tiradores and extr.tiradores and extr.tiradores != ot.num_tiradores:
        errores.append(f"Tiradores: EXTRACCION {extr.tiradores} ≠ OT {ot.num_tiradores}")
    if extr.rejillas_ventilacion != ot.num_ventilacion:
        errores.append(
            f"Rejillas ventilación: EXTRACCION {extr.rejillas_ventilacion} ≠ OT {ot.num_ventilacion}"
        )
    # Tensores: 0 EXTR ↔ False OT; ≥1 EXTR ↔ True OT. None OT → no comparable.
    if ot.tiene_tensores is not None:
        tiene_ext = extr.tensores >= 1
        if tiene_ext != ot.tiene_tensores:
            errores.append(
                f"Tensores: EXTRACCION {extr.tensores} "
                f"({'tiene' if tiene_ext else 'no tiene'}) ≠ OT "
                f"({'tiene' if ot.tiene_tensores else 'no tiene'})"
            )

    return _resultado("C-71", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-72: logística — palets + tipos de envío activos (mono o multi-envío)
# ---------------------------------------------------------------------------

_TIPOS_ENVIO = ("caja_grande", "caja_pequena",
                "estructura_grande", "estructura_pequena")


def _normalizar_modelo(texto: str) -> str:
    """lower + strip + sin tildes; 'Caja pequeña' ≡ 'caja pequena'."""
    if not texto:
        return ""
    s = texto.strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"),
                 ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        s = s.replace(a, b)
    return s


def _parsear_modelos_envio_ot(modelo_envio: str) -> set[str]:
    """Divide 'Modelo de envío' OT por '+' (multi-envío) y normaliza."""
    if not modelo_envio:
        return set()
    return {p for p in (_normalizar_modelo(x) for x in modelo_envio.split("+")) if p}


def _es_paqueteria(modelo_envio: str) -> bool:
    """True si el modelo de envío es exclusivamente 'Paqueteria' (con o sin
    tilde, case-insensitive). Indica envío por mensajería estándar — sin
    palets y sin caja/estructura.
    """
    return _parsear_modelos_envio_ot(modelo_envio) == {"paqueteria"}


def check_logistica_envio(
    extr: ExtraccionData, ot: OTData, reglas: dict,
) -> CheckResult:
    """C-72: FAIL bloqueante.

    - 'Cantidad de palets' EXTRACCION == OT.
    - El conjunto de tipos de envío activos (caja/estructura grande/pequeña)
      en EXTRACCION coincide con 'Modelo de envío' de la OT. La OT puede
      declarar uno o varios modelos combinados con '+', p. ej.
      'Caja grande + Estructura pequena' — en ese caso EXTRACCION debe
      tener exactamente esos N tipos a ≥1 y el resto a 0.
    - Caso especial 'Paqueteria': típico en incidencias P1 o proyectos
      pequeños cortados de retal. EXTRACCION debe tener TODOS los tipos
      a 0 y palets a 0 (el bulto va por mensajería estándar).
    """
    desc = "Logística (palets + tipos de envío) coherente con OT"
    errores: list[str] = []

    if ot.num_palets is not None and extr.palets != ot.num_palets:
        errores.append(f"Palets: EXTRACCION {extr.palets} ≠ OT {ot.num_palets}")

    cfg = (reglas or {}).get("extraccion", {}).get("tipos_envio", {}) or {}
    activos = [n for n in _TIPOS_ENVIO if getattr(extr, n) >= 1]

    if _es_paqueteria(ot.modelo_envio):
        if activos:
            extr_legible = " + ".join(cfg.get(n, n) for n in activos)
            errores.append(
                f"Modelo de envío: OT 'Paqueteria' incompatible con "
                f"EXTRACCION '{extr_legible}' (todos los tipos deben ser 0)"
            )
    elif not activos:
        errores.append("Tipo de envío: ningún tipo está activo (todos a 0)")
    elif ot.modelo_envio:
        modelos_extr_norm = {_normalizar_modelo(cfg.get(n, "")) for n in activos}
        modelos_extr_norm.discard("")
        modelos_ot_norm = _parsear_modelos_envio_ot(ot.modelo_envio)
        if modelos_extr_norm != modelos_ot_norm:
            extr_legible = " + ".join(cfg.get(n, n) for n in activos)
            errores.append(
                f"Modelo de envío: EXTRACCION '{extr_legible}' ≠ OT '{ot.modelo_envio}'"
            )

    return _resultado("C-72", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-73: metros de canto (con tolerancia)
# ---------------------------------------------------------------------------

def check_metros_canto(
    extr: ExtraccionData, ot: OTData, reglas: dict,
) -> CheckResult:
    """C-73: WARN. Tolerancia absoluta en metros sobre la OT.

    En proyectos multi-material el sistema redondea cada material al entero
    superior por separado y luego se suma, lo que acumula error de redondeo;
    una tolerancia absoluta de ±4 mt absorbe ese acumulado.
    """
    desc = "Metros de canto EXTRACCION ≈ OT (tolerancia absoluta)"
    cfg = (reglas or {}).get("extraccion", {}) or {}
    tol_mt = float(cfg.get("tolerancia_metros_canto_mt", 4.0))

    if not ot.metros_canto:
        return _skip("C-73", desc, "OT no declara metros lineales de corte", _GRUPO)
    if not extr.metros_canto:
        return _skip("C-73", desc, "EXTRACCION no declara metros de canto", _GRUPO)

    diff = abs(extr.metros_canto - ot.metros_canto)
    if diff > tol_mt:
        return _warn(
            "C-73", desc,
            f"EXTRACCION {extr.metros_canto} mt vs OT {ot.metros_canto} mt "
            f"(diferencia {diff:.2f} mt > tolerancia ±{tol_mt:g} mt)",
            _GRUPO,
        )
    return _pass("C-73", desc, False, _GRUPO)


# ---------------------------------------------------------------------------
# C-74: tableros codificados <COD>_tab ↔ tabla CORTE OT
# ---------------------------------------------------------------------------

def check_tableros_codificados(
    extr: ExtraccionData,
    ot: OTData,
    naming: dict[str, tuple[str, str]],
) -> CheckResult:
    """C-74: FAIL bloqueante.

    Decodifica cada clave <COD>_tab de EXTRACCION (vía naming_extraccion.csv) a
    su clave canónica 'MATERIAL_GAMA_Acabado' y la compara con OT.tableros.

    Las claves con cantidad 0 se ignoran en ambos lados: indican "no hay
    tableros nuevos de esta combinación" — típico en incidencias cortadas
    de retal donde la OT declara '# Tableros: 0'. Si ambos lados quedan
    vacíos tras filtrar, el check se salta (SKIP).
    """
    desc = "Tableros <COD>_tab decodificados ↔ tabla CORTE OT"

    if not extr.tableros_codificados:
        return _skip("C-74", desc, "EXTRACCION no declara claves <COD>_tab", _GRUPO)
    if not ot.tableros:
        return _skip("C-74", desc, "OT no declara tabla INFORMACION DE CORTE", _GRUPO)

    errores: list[str] = []
    # Mapas indexados por clave normalizada (lower) → (clave_original, cantidad).
    # La normalización evita falsos FAIL por casing irregular en acabados con
    # guión (p.ej. OT "Rosa-Baby" vs naming "Rosa-baby").
    cods_decodificados: dict[str, tuple[str, int]] = {}
    for cod_tab, cantidad in extr.tableros_codificados.items():
        if cantidad == 0:
            continue
        clave_canonica = cod_tab_a_clave_canonica(cod_tab, naming)
        if clave_canonica is None:
            errores.append(f"Código '{cod_tab}' no se reconoce en naming_extraccion.csv")
            continue
        k = clave_canonica.lower()
        prev = cods_decodificados.get(k)
        cods_decodificados[k] = (clave_canonica, (prev[1] if prev else 0) + cantidad)

    ot_tableros: dict[str, tuple[str, int]] = {}
    for clave, cantidad in ot.tableros.items():
        if cantidad <= 0:
            continue
        ot_tableros[clave.lower()] = (clave, cantidad)

    if not cods_decodificados and not ot_tableros:
        return _skip(
            "C-74", desc,
            "Proyecto sin tableros nuevos (probablemente cortado de retal)",
            _GRUPO,
        )

    # Lado EXTRACCION → OT: cada combinación del EXTRACCION debe estar en OT
    for k, (clave, cantidad) in cods_decodificados.items():
        en_ot = ot_tableros.get(k)
        if en_ot is None:
            errores.append(
                f"OT no declara la combinación '{clave}' (EXTRACCION dice {cantidad})"
            )
        elif en_ot[1] != cantidad:
            errores.append(
                f"Combinación '{clave}': EXTRACCION {cantidad} ≠ OT {en_ot[1]}"
            )

    # Lado OT → EXTRACCION
    for k, (clave, cantidad) in ot_tableros.items():
        if k not in cods_decodificados:
            errores.append(
                f"EXTRACCION no declara la combinación '{clave}' (OT dice {cantidad})"
            )

    return _resultado("C-74", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-75: prioridad INC válida solo en proyectos -INC
# ---------------------------------------------------------------------------

def check_prioridad_inc(extr: ExtraccionData, reglas: dict) -> CheckResult:
    """C-75: WARN. Solo se rellena en proyectos -INC con valor de la lista."""
    desc = "Prioridad INC rellenada solo en -INC con valor válido"
    cfg = (reglas or {}).get("extraccion", {}) or {}
    validas = set(cfg.get("prioridades_inc_validas", []))

    id_norm = extr.id_proyecto.upper().replace("_", "-")
    es_inc = "-INC" in id_norm
    valor = extr.prioridad_inc.strip()

    if es_inc:
        if not valor:
            return _warn(
                "C-75", desc,
                f"{extr.id_proyecto} es -INC pero 'Prioridad de INC' está vacía",
                _GRUPO,
            )
        if validas and valor not in validas:
            return _warn(
                "C-75", desc,
                f"{extr.id_proyecto}: prioridad '{valor}' no válida "
                f"(esperado uno de {sorted(validas)})",
                _GRUPO,
            )
        return _pass("C-75", desc, False, _GRUPO)

    # No-INC: el valor debe estar vacío
    if valor:
        return _warn(
            "C-75", desc,
            f"{extr.id_proyecto} no es -INC pero tiene 'Prioridad de INC' = '{valor}'",
            _GRUPO,
        )
    return _pass("C-75", desc, False, _GRUPO)


# ---------------------------------------------------------------------------
# C-76: tabla EXTRACCION ↔ DESPIECE — nº filas + conjunto IDs
# ---------------------------------------------------------------------------

def check_tabla_ids_vs_despiece(
    extr: ExtraccionData, piezas: list[Pieza],
) -> CheckResult:
    """C-76: FAIL bloqueante. Mismo nº de piezas y mismos IDs en ambos."""
    desc = "Tabla EXTRACCION: nº filas + conjunto IDs ↔ DESPIECE"
    if not extr.piezas_tabla:
        return _fail(
            "C-76", desc,
            "EXTRACCION no tiene filas en la tabla de piezas",
            True, _GRUPO,
        )
    if not piezas:
        return _skip("C-76", desc, "DESPIECE vacío", _GRUPO)

    ids_extr = {f.id_pieza for f in extr.piezas_tabla}
    ids_desp = {p.id for p in piezas}

    errores: list[str] = []
    if len(extr.piezas_tabla) != len(piezas):
        errores.append(
            f"Nº filas: EXTRACCION {len(extr.piezas_tabla)} ≠ DESPIECE {len(piezas)}"
        )
    en_extr_no_desp = sorted(ids_extr - ids_desp)
    if en_extr_no_desp:
        errores.append(f"IDs en EXTRACCION no presentes en DESPIECE: {en_extr_no_desp}")
    en_desp_no_extr = sorted(ids_desp - ids_extr)
    if en_desp_no_extr:
        errores.append(f"IDs en DESPIECE no presentes en EXTRACCION: {en_desp_no_extr}")

    return _resultado("C-76", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-77: tabla EXTRACCION ↔ DESPIECE — dimensiones + material/gama/acabado
# ---------------------------------------------------------------------------

def check_tabla_dimensiones_material(
    extr: ExtraccionData, piezas: list[Pieza],
) -> CheckResult:
    """C-77: FAIL bloqueante. Por cada ID común a ambos: Ancho, Alto,
    Material, Gama, Acabado deben coincidir."""
    desc = "Tabla EXTRACCION: dimensiones + material/gama/acabado ↔ DESPIECE"
    if not extr.piezas_tabla or not piezas:
        return _skip("C-77", desc, "EXTRACCION o DESPIECE vacío", _GRUPO)

    por_id = {p.id: p for p in piezas}
    errores: list[str] = []
    for fila in extr.piezas_tabla:
        p = por_id.get(fila.id_pieza)
        if p is None:
            continue  # IDs huérfanos los reporta C-76
        difs: list[str] = []
        if fila.ancho != p.ancho:
            difs.append(f"ancho {fila.ancho}≠{p.ancho}")
        if fila.alto != p.alto:
            difs.append(f"alto {fila.alto}≠{p.alto}")
        if fila.material and fila.material != p.material:
            difs.append(f"material {fila.material}≠{p.material}")
        if fila.gama and fila.gama != p.gama:
            difs.append(f"gama {fila.gama}≠{p.gama}")
        if fila.acabado and fila.acabado.lower() != p.acabado.lower():
            difs.append(f"acabado '{fila.acabado}'≠'{p.acabado}'")
        if difs:
            errores.append(f"{fila.id_pieza}: {', '.join(difs)}")

    return _resultado("C-77", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-78: tabla EXTRACCION ↔ DESPIECE — tipología + mecanizado
# ---------------------------------------------------------------------------

def check_tabla_tipologia_mecanizado(
    extr: ExtraccionData, piezas: list[Pieza],
) -> CheckResult:
    """C-78: FAIL bloqueante. Tipología y mecanizado por ID."""
    desc = "Tabla EXTRACCION: tipología + mecanizado ↔ DESPIECE"
    if not extr.piezas_tabla or not piezas:
        return _skip("C-78", desc, "EXTRACCION o DESPIECE vacío", _GRUPO)

    por_id = {p.id: p for p in piezas}
    errores: list[str] = []
    for fila in extr.piezas_tabla:
        p = por_id.get(fila.id_pieza)
        if p is None:
            continue
        difs: list[str] = []
        # Tipología: si está rellena en ambos lados, comparamos
        if fila.tipologia and p.tipologia and fila.tipologia != p.tipologia:
            difs.append(f"tipología {fila.tipologia}≠{p.tipologia}")
        if fila.mecanizado.strip() != p.mecanizado.strip():
            difs.append(f"mecanizado '{fila.mecanizado}'≠'{p.mecanizado}'")
        if difs:
            errores.append(f"{fila.id_pieza}: {', '.join(difs)}")

    return _resultado("C-78", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-79: tabla EXTRACCION ↔ DESPIECE — tirador completo
# ---------------------------------------------------------------------------

def check_tabla_tirador(
    extr: ExtraccionData, piezas: list[Pieza],
) -> CheckResult:
    """C-79: FAIL bloqueante. Tirador, posición, apertura y color tirador."""
    desc = "Tabla EXTRACCION: tirador/posición/apertura/color ↔ DESPIECE"
    if not extr.piezas_tabla or not piezas:
        return _skip("C-79", desc, "EXTRACCION o DESPIECE vacío", _GRUPO)

    por_id = {p.id: p for p in piezas}
    errores: list[str] = []
    for fila in extr.piezas_tabla:
        p = por_id.get(fila.id_pieza)
        if p is None:
            continue
        difs: list[str] = []
        if fila.tirador.strip().lower() != p.tirador.strip().lower():
            difs.append(f"tirador '{fila.tirador}'≠'{p.tirador}'")
        if fila.posicion_tirador.strip() != p.posicion_tirador.strip():
            difs.append(f"posición '{fila.posicion_tirador}'≠'{p.posicion_tirador}'")
        if fila.apertura.strip().upper() != p.apertura.strip().upper():
            difs.append(f"apertura '{fila.apertura}'≠'{p.apertura}'")
        if fila.color_tirador.strip().lower() != p.color_tirador.strip().lower():
            difs.append(f"color tirador '{fila.color_tirador}'≠'{p.color_tirador}'")
        if difs:
            errores.append(f"{fila.id_pieza}: {', '.join(difs)}")

    return _resultado("C-79", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-80: baldas con herrajes ocultos ↔ DESPIECE tipología B
# ---------------------------------------------------------------------------

def check_baldas_herrajes(
    extr: ExtraccionData,
    piezas: list[Pieza],
    reglas: dict,
) -> CheckResult:
    """C-80: WARN. Las cantidades de baldas con 2/3 herrajes ocultos en
    EXTRACCION deben cuadrar con los conteos por dimensiones del DESPIECE."""
    desc = "Baldas con herrajes (EXTRACCION) ↔ DESPIECE tipología B"
    cfg = (reglas or {}).get("extraccion", {}) or {}
    dims_2h_raw = cfg.get("baldas_2h_dims", []) or []
    dims_3h_raw = cfg.get("baldas_3h_dims", []) or []

    # Aceptar ambas orientaciones (200×600 ≡ 600×200)
    def _pares(seq: list[dict]) -> set[tuple[int, int]]:
        pares: set[tuple[int, int]] = set()
        for d in seq:
            a, h = int(d["ancho"]), int(d["alto"])
            pares.add((a, h))
            pares.add((h, a))
        return pares

    dims_2h = _pares(dims_2h_raw)
    dims_3h = _pares(dims_3h_raw)

    baldas = [p for p in piezas if p.tipologia == "B"]
    n_2h_desp = sum(1 for p in baldas if (p.ancho, p.alto) in dims_2h)
    n_3h_desp = sum(1 for p in baldas if (p.ancho, p.alto) in dims_3h)

    errores: list[str] = []
    if extr.baldas_2h != n_2h_desp:
        errores.append(
            f"Baldas 2 herrajes: EXTRACCION {extr.baldas_2h} ≠ DESPIECE {n_2h_desp}"
        )
    if extr.baldas_3h != n_3h_desp:
        errores.append(
            f"Baldas 3 herrajes: EXTRACCION {extr.baldas_3h} ≠ DESPIECE {n_3h_desp}"
        )

    return _resultado("C-80", desc, errores, False, _GRUPO, tipo_fail="WARN")


# ---------------------------------------------------------------------------
# C-81: Altillos EXTRACCION ↔ OT — total + desglose por dimensión
# ---------------------------------------------------------------------------

def check_altillos(extr: ExtraccionData, ot: OTData) -> CheckResult:
    """C-81: FAIL bloqueante.

    Compara los altillos declarados en EXTRACCION con el bloque ALTILLOS
    de la OT en dos dimensiones:
      1) Total agregado:  extr.altillos_total  ↔  Σ ot.altillos_dims.values()
      2) Desglose por dimensión: extr.altillos_dims[dim]  ↔  ot.altillos_dims[dim]

    Si ambos lados están a 0 (proyecto sin altillos) el check pasa.
    """
    desc = "Altillos EXTRACCION ↔ OT (total + desglose por dimensión)"

    total_ext = extr.altillos_total
    total_ot = sum(ot.altillos_dims.values())

    if total_ext == 0 and total_ot == 0:
        return _pass("C-81", desc, True, _GRUPO)

    errores: list[str] = []
    if total_ext != total_ot:
        errores.append(f"Total: EXTRACCION {total_ext} ≠ OT {total_ot}")

    dims_todas = set(extr.altillos_dims.keys()) | set(ot.altillos_dims.keys())
    for dim in sorted(dims_todas):
        ext_n = extr.altillos_dims.get(dim, 0)
        ot_n = ot.altillos_dims.get(dim, 0)
        if ext_n != ot_n:
            errores.append(f"Dimensión {dim}: EXTRACCION {ext_n} ≠ OT {ot_n}")

    return _resultado("C-81", desc, errores, True, _GRUPO)


# ---------------------------------------------------------------------------
# C-82: nº de hornacinas EXTRACCION ↔ OT
# ---------------------------------------------------------------------------

def check_hornacinas(extr: ExtraccionData, ot: OTData) -> CheckResult:
    """C-82: FAIL bloqueante.

    Compara la cantidad declarada en EXTRACCION ('Hornacinas,N') con la
    cantidad declarada en la OT ('Cantidad de hornacinas:N uds'). En
    proyectos sin hornacinas la OT no incluye esa línea y num_hornacinas
    se queda a 0 — debe coincidir con extr.hornacinas = 0.
    """
    desc = "Nº de hornacinas EXTRACCION ↔ OT"
    if extr.hornacinas == ot.num_hornacinas:
        return _pass("C-82", desc, True, _GRUPO)
    return _fail(
        "C-82", desc,
        f"Hornacinas: EXTRACCION {extr.hornacinas} ≠ OT {ot.num_hornacinas}",
        True, _GRUPO,
    )


# ---------------------------------------------------------------------------
# C-83: presencia de mueble de nevera EXTRACCION ↔ OT
# ---------------------------------------------------------------------------

def check_mueble_nevera(extr: ExtraccionData, ot: OTData) -> CheckResult:
    """C-83: FAIL bloqueante.

    La OT no declara cantidad — solo aparece la línea "Mueble de nevera
    75x60x220 cm" cuando hay al menos uno. Por eso la comparación es
    binaria: extr.mueble_nevera ≥ 1 ↔ ot.tiene_mueble_nevera.
    """
    desc = "Mueble de nevera EXTRACCION ↔ OT"
    tiene_ext = extr.mueble_nevera >= 1
    if tiene_ext == ot.tiene_mueble_nevera:
        return _pass("C-83", desc, True, _GRUPO)
    return _fail(
        "C-83", desc,
        f"Mueble de nevera: EXTRACCION {extr.mueble_nevera} "
        f"({'tiene' if tiene_ext else 'no tiene'}) ≠ OT "
        f"({'tiene' if ot.tiene_mueble_nevera else 'no tiene'})",
        True, _GRUPO,
    )
