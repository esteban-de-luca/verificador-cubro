"""tests/test_checks_extraccion.py — Tests de C-70 a C-80.

Cada bloque cubre PASS / FAIL (o WARN) / SKIP del check correspondiente.
Los fixtures construyen los modelos mínimos necesarios; ningún test toca
ficheros reales.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import ExtraccionData, FilaExtraccion, OTData, Pieza
from core.extractor_extraccion import cargar_naming_default
from core.reglas_loader import cargar_reglas
from checks.checks_extraccion import (
    check_cabecera_ot,
    check_recuentos_criticos,
    check_logistica_envio,
    check_metros_canto,
    check_tableros_codificados,
    check_prioridad_inc,
    check_tabla_ids_vs_despiece,
    check_tabla_dimensiones_material,
    check_tabla_tipologia_mecanizado,
    check_tabla_tirador,
    check_baldas_herrajes,
    check_altillos,
    check_hornacinas,
    check_mueble_nevera,
)


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


@pytest.fixture(scope="session")
def naming():
    return cargar_naming_default()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _ot(**overrides) -> OTData:
    base = dict(
        id_proyecto="EU-22376", cliente="Bürgerverein", semana="Semana 22",
        num_piezas=3, peso_total_kg=50.0, num_tiradores=2,
        tableros={"MDF_LAC_Zafiro": 2},
        num_tableros_total=2,
        num_ventilacion=1,
        tiene_tensores=False,
        numero_ot="5074",
        fecha_entrada="25/05/2026", fecha_salida="05/06/2026",
        num_palets=1, modelo_envio="Caja grande", metros_canto=62.32,
    )
    base.update(overrides)
    return OTData(**base)


def _extr(**overrides) -> ExtraccionData:
    base = dict(
        id_proyecto="EU-22376", cliente="Bürgerverein",
        numero_ot="5074", semana="22",
        fecha_entrada="25/05/2026", fecha_salida="05/06/2026",
        piezas=3, tiradores=2, metros_canto=63.0,
        tensores=0, rejillas_ventilacion=1, hornacinas=0, palets=1,
        baldas_2h=0, baldas_3h=0,
        caja_grande=1, caja_pequena=0,
        estructura_grande=0, estructura_pequena=0,
        prioridad_inc="",
        tableros_codificados={"LAC_Zaf_tab": 2},
    )
    base.update(overrides)
    d = ExtraccionData(**base)
    return d


def _fila(id_pieza, ancho=120, alto=800, **extras) -> FilaExtraccion:
    base = dict(
        id_proyecto="EU-22376", cliente="Bürgerverein", id_pieza=id_pieza,
        tipologia="T", ancho=ancho, alto=alto,
        material="MDF", gama="LAC", acabado="Zafiro",
    )
    base.update(extras)
    return FilaExtraccion(**base)


def _pieza(id, ancho=120, alto=800, **extras) -> Pieza:
    base = dict(
        id=id, ancho=ancho, alto=alto,
        material="MDF", gama="LAC", acabado="Zafiro",
        tipologia="T",
    )
    base.update(extras)
    return Pieza(**base)


# ---------------------------------------------------------------------------
# C-70: cabecera fija EXTRACCION ↔ OT
# ---------------------------------------------------------------------------

class TestC70:

    def test_pass_todo_coincide(self):
        r = check_cabecera_ot(_extr(), _ot())
        assert r.resultado == "PASS"

    def test_warn_num_ot_distinto(self):
        r = check_cabecera_ot(_extr(numero_ot="9999"), _ot())
        assert r.resultado == "WARN"
        assert "Nº OT" in r.detalle

    def test_warn_semana_distinta(self):
        r = check_cabecera_ot(_extr(semana="21"), _ot())
        assert r.resultado == "WARN"
        assert "Semana" in r.detalle

    def test_warn_fecha_entrada(self):
        r = check_cabecera_ot(_extr(fecha_entrada="20/05/2026"), _ot())
        assert r.resultado == "WARN"

    def test_no_bloquea(self):
        r = check_cabecera_ot(_extr(numero_ot="9999"), _ot())
        assert not r.bloquea


# ---------------------------------------------------------------------------
# C-71: recuentos críticos (FAIL)
# ---------------------------------------------------------------------------

class TestC71:

    def test_pass_todo_coincide(self):
        r = check_recuentos_criticos(_extr(), _ot())
        assert r.resultado == "PASS"
        assert r.bloquea

    def test_fail_piezas_distinto(self):
        r = check_recuentos_criticos(_extr(piezas=4), _ot())
        assert r.resultado == "FAIL"
        assert "Piezas" in r.detalle

    def test_fail_tiradores_distinto(self):
        r = check_recuentos_criticos(_extr(tiradores=5), _ot())
        assert r.resultado == "FAIL"

    def test_fail_ventilacion_distinta(self):
        r = check_recuentos_criticos(_extr(rejillas_ventilacion=0), _ot())
        assert r.resultado == "FAIL"
        assert "ventilación" in r.detalle or "ventilacion" in r.detalle.lower()

    def test_fail_tensores_discrepancia(self):
        """OT dice False (sin tensores), EXTRACCION dice 3 (≥1)."""
        r = check_recuentos_criticos(_extr(tensores=3), _ot(tiene_tensores=False))
        assert r.resultado == "FAIL"

    def test_pass_tensores_ambos_si(self):
        r = check_recuentos_criticos(_extr(tensores=4), _ot(tiene_tensores=True))
        assert r.resultado == "PASS"

    def test_pass_si_ot_sin_tensores_info(self):
        """OT con tiene_tensores=None → no comparable."""
        r = check_recuentos_criticos(_extr(tensores=3), _ot(tiene_tensores=None))
        # Los demás campos siguen coincidiendo
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-72: logística (FAIL)
# ---------------------------------------------------------------------------

class TestC72:

    def test_pass_caja_grande_y_palets_coinciden(self, reglas):
        r = check_logistica_envio(_extr(), _ot(), reglas)
        assert r.resultado == "PASS"

    def test_fail_palets_distinto(self, reglas):
        r = check_logistica_envio(_extr(palets=2), _ot(num_palets=1), reglas)
        assert r.resultado == "FAIL"

    def test_fail_ningun_tipo_envio(self, reglas):
        r = check_logistica_envio(_extr(caja_grande=0), _ot(), reglas)
        assert r.resultado == "FAIL"
        assert "ningún tipo" in r.detalle.lower() or "ningun tipo" in r.detalle.lower()

    def test_fail_extr_multi_pero_ot_mono(self, reglas):
        """EXTRACCION tiene 2 tipos activos pero OT solo declara uno → FAIL."""
        r = check_logistica_envio(_extr(caja_pequena=1), _ot(), reglas)
        assert r.resultado == "FAIL"
        assert "modelo de envío" in r.detalle.lower()

    def test_fail_modelo_envio_no_coincide(self, reglas):
        r = check_logistica_envio(
            _extr(caja_grande=0, estructura_grande=1),
            _ot(modelo_envio="Caja grande"),
            reglas,
        )
        assert r.resultado == "FAIL"

    def test_pass_estructura_pequena(self, reglas):
        r = check_logistica_envio(
            _extr(caja_grande=0, estructura_pequena=1),
            _ot(modelo_envio="Estructura pequeña"),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_multi_envio_caja_y_estructura(self, reglas):
        """SP-22687 real: OT 'Caja grande + Estructura pequena', EXTRACCION
        con caja_grande=1 y estructura_pequena=1 → PASS."""
        r = check_logistica_envio(
            _extr(caja_grande=1, estructura_pequena=1, palets=2),
            _ot(modelo_envio="Caja grande + Estructura pequena", num_palets=2),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_multi_envio_tildes_y_espacios(self, reglas):
        """OT con 'pequeña' (con tilde) y espacios irregulares ≡ 'pequena'."""
        r = check_logistica_envio(
            _extr(caja_grande=1, estructura_pequena=1, palets=2),
            _ot(modelo_envio="Caja grande  +  Estructura pequeña", num_palets=2),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_fail_multi_envio_extr_falta_un_tipo(self, reglas):
        """OT declara dos modelos pero EXTRACCION sólo activa uno → FAIL."""
        r = check_logistica_envio(
            _extr(caja_grande=1, estructura_pequena=0, palets=2),
            _ot(modelo_envio="Caja grande + Estructura pequena", num_palets=2),
            reglas,
        )
        assert r.resultado == "FAIL"
        assert "modelo de envío" in r.detalle.lower()

    def test_fail_multi_envio_extr_tiene_tipo_extra(self, reglas):
        """EXTRACCION tiene un tipo extra que OT no declara → FAIL."""
        r = check_logistica_envio(
            _extr(caja_grande=1, estructura_pequena=1,
                  estructura_grande=1, palets=2),
            _ot(modelo_envio="Caja grande + Estructura pequena", num_palets=2),
            reglas,
        )
        assert r.resultado == "FAIL"

    def test_pass_extr_multi_pero_ot_sin_modelo(self, reglas):
        """Si OT no declara modelo_envio no se compara, solo se exige ≥1 activo."""
        r = check_logistica_envio(
            _extr(caja_grande=1, estructura_pequena=1),
            _ot(modelo_envio=""),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_paqueteria_todo_a_cero(self, reglas):
        """SP-21888-INC real: OT 'Paqueteria', EXTRACCION con todos los tipos
        a 0 y palets a 0 → PASS (envío por mensajería estándar)."""
        r = check_logistica_envio(
            _extr(caja_grande=0, caja_pequena=0,
                  estructura_grande=0, estructura_pequena=0, palets=0),
            _ot(modelo_envio="Paqueteria", num_palets=0),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_paqueteria_con_tilde(self, reglas):
        """'Paquetería' con tilde debe equivaler a 'Paqueteria'."""
        r = check_logistica_envio(
            _extr(caja_grande=0, palets=0),
            _ot(modelo_envio="Paquetería", num_palets=0),
            reglas,
        )
        assert r.resultado == "PASS"

    def test_fail_paqueteria_con_caja_activa(self, reglas):
        """OT 'Paqueteria' pero EXTRACCION activa una caja → FAIL."""
        r = check_logistica_envio(
            _extr(caja_grande=1, palets=0),
            _ot(modelo_envio="Paqueteria", num_palets=0),
            reglas,
        )
        assert r.resultado == "FAIL"
        assert "paqueteria" in r.detalle.lower()

    def test_fail_paqueteria_con_palets(self, reglas):
        """OT 'Paqueteria' con num_palets=0 pero EXTRACCION palets=1 → FAIL
        por el check independiente de palets."""
        r = check_logistica_envio(
            _extr(caja_grande=0, palets=1),
            _ot(modelo_envio="Paqueteria", num_palets=0),
            reglas,
        )
        assert r.resultado == "FAIL"
        assert "palets" in r.detalle.lower()


# ---------------------------------------------------------------------------
# C-73: metros de canto (WARN con tolerancia)
# ---------------------------------------------------------------------------

class TestC73:

    def test_pass_dentro_de_tolerancia(self, reglas):
        # OT: 62.32, EXTRACCION: 63 → diff 0.68 mt ≤ 4 → PASS
        r = check_metros_canto(_extr(metros_canto=63.0), _ot(metros_canto=62.32), reglas)
        assert r.resultado == "PASS"

    def test_warn_fuera_de_tolerancia(self, reglas):
        # OT: 62.32, EXTRACCION: 70 → diff 7.68 mt > 4 → WARN
        r = check_metros_canto(_extr(metros_canto=70.0), _ot(metros_canto=62.32), reglas)
        assert r.resultado == "WARN"

    def test_skip_ot_sin_dato(self, reglas):
        r = check_metros_canto(_extr(), _ot(metros_canto=0.0), reglas)
        assert r.resultado == "SKIP"

    def test_skip_extr_sin_dato(self, reglas):
        r = check_metros_canto(_extr(metros_canto=0.0), _ot(), reglas)
        assert r.resultado == "SKIP"

    def test_pass_multimaterial_acumulado(self, reglas):
        """EU-22427 real: OT=97.01, EXTR=98 → diff 0.99 mt ≤ 4 → PASS."""
        r = check_metros_canto(
            _extr(metros_canto=98.0), _ot(metros_canto=97.01), reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_en_el_limite(self, reglas):
        """Diff exactamente igual a la tolerancia (±4 mt) → PASS."""
        r = check_metros_canto(
            _extr(metros_canto=104.0), _ot(metros_canto=100.0), reglas,
        )
        assert r.resultado == "PASS"

    def test_warn_justo_fuera_de_tolerancia(self, reglas):
        """Diff 4.01 mt > 4 → WARN."""
        r = check_metros_canto(
            _extr(metros_canto=104.01), _ot(metros_canto=100.0), reglas,
        )
        assert r.resultado == "WARN"
        assert "tolerancia" in r.detalle.lower()
        assert "mt" in r.detalle

    def test_warn_proyecto_grande_5mt(self, reglas):
        """OT=500 mt, EXTR=505 → diff 5 mt > 4 → WARN.
        Antes con tolerancia 2% esto pasaba (1%); ahora con ±4 mt absoluta no."""
        r = check_metros_canto(
            _extr(metros_canto=505.0), _ot(metros_canto=500.0), reglas,
        )
        assert r.resultado == "WARN"

    def test_pass_diff_por_debajo(self, reglas):
        """EXTRACCION puede ser menor que OT también (diff abs)."""
        r = check_metros_canto(
            _extr(metros_canto=58.32), _ot(metros_canto=62.32), reglas,
        )
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-74: tableros codificados ↔ OT
# ---------------------------------------------------------------------------

class TestC74:

    def test_pass_combinacion_unica_coincide(self, naming):
        r = check_tableros_codificados(_extr(), _ot(), naming)
        assert r.resultado == "PASS"

    def test_fail_cantidad_distinta(self, naming):
        r = check_tableros_codificados(
            _extr(tableros_codificados={"LAC_Zaf_tab": 3}),
            _ot(),  # ot tiene MDF_LAC_Zafiro: 2
            naming,
        )
        assert r.resultado == "FAIL"

    def test_fail_combinacion_no_en_ot(self, naming):
        r = check_tableros_codificados(
            _extr(tableros_codificados={"HPL_Pal_tab": 2}),
            _ot(),
            naming,
        )
        assert r.resultado == "FAIL"
        assert "no declara" in r.detalle.lower()

    def test_fail_combinacion_solo_en_ot(self, naming):
        # OT tiene MDF_LAC_Zafiro=2 y PLY_LAM_Pale=1; EXTRACCION solo LAC_Zaf=2
        r = check_tableros_codificados(
            _extr(),
            _ot(tableros={"MDF_LAC_Zafiro": 2, "PLY_LAM_Pale": 1}),
            naming,
        )
        assert r.resultado == "FAIL"
        assert "PLY_LAM_Pale" in r.detalle

    def test_fail_codigo_no_reconocido(self, naming):
        r = check_tableros_codificados(
            _extr(tableros_codificados={"XXX_Yyy_tab": 2}),
            _ot(),
            naming,
        )
        assert r.resultado == "FAIL"
        assert "no se reconoce" in r.detalle.lower()

    def test_fail_sin_codigos_pero_ot_con_tableros(self, naming):
        """EXTRACCION no declara ninguna clave <COD>_tab pero la OT sí declara
        tableros → FAIL: la EXTRACCION debe declarar siempre los materiales."""
        r = check_tableros_codificados(_extr(tableros_codificados={}), _ot(), naming)
        assert r.resultado == "FAIL"
        assert "no declara" in r.detalle.lower()

    def test_fail_sin_codigos_aunque_ot_declare_cero(self, naming):
        """Caso EU-21993-INC3 (retal): OT declara la combinación con # Tableros 0
        y la EXTRACCION no declara ninguna clave <COD>_tab → FAIL.
        El retal solo se exime si la EXTRACCION declara la clave con 0."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={}),
            _ot(tableros={"PLY_LIN_Pistacho": 0}),
            naming,
        )
        assert r.resultado == "FAIL"
        assert "PLY_LIN_Pistacho" in r.detalle

    def test_skip_sin_codigos_y_ot_sin_tabla(self, naming):
        """Ni EXTRACCION ni OT declaran tableros → no hay nada que comparar → SKIP."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={}), _ot(tableros={}), naming
        )
        assert r.resultado == "SKIP"

    def test_skip_ot_sin_tabla(self, naming):
        r = check_tableros_codificados(_extr(), _ot(tableros={}), naming)
        assert r.resultado == "SKIP"

    def test_pass_multimaterial(self, naming):
        """OT y EXTRACCION declaran 2 combinaciones; ambas cuadran."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"LAC_Zaf_tab": 2, "HPL_Pal_tab": 1}),
            _ot(tableros={"MDF_LAC_Zafiro": 2, "PLY_LAM_Pale": 1}),
            naming,
        )
        assert r.resultado == "PASS"

    def test_skip_proyecto_de_retal(self, naming):
        """SP-21888-INC real: EXTRACCION declara HPL_Sab_tab:0 y OT declara
        la combinación con # Tableros:0 (cortado de retal) → SKIP."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"HPL_Pal_tab": 0}),
            _ot(tableros={"PLY_LAM_Pale": 0}),
            naming,
        )
        assert r.resultado == "SKIP"

    def test_pass_cantidad_cero_ignorada_en_extr(self, naming):
        """EXTRACCION declara una clave con 0 y otra con cantidad real;
        la de 0 se ignora y la real cuadra con OT → PASS."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"LAC_Zaf_tab": 2, "HPL_Pal_tab": 0}),
            _ot(tableros={"MDF_LAC_Zafiro": 2}),
            naming,
        )
        assert r.resultado == "PASS"

    def test_pass_cantidad_cero_en_ambos_lados(self, naming):
        """EXTRACCION y OT tienen una entrada con 0 (ignorada) + las reales
        que cuadran → PASS."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"LAC_Zaf_tab": 2, "HPL_Pal_tab": 0}),
            _ot(tableros={"MDF_LAC_Zafiro": 2, "PLY_LAM_Pale": 0}),
            naming,
        )
        assert r.resultado == "PASS"

    def test_fail_extr_cero_pero_ot_real(self, naming):
        """Si EXTRACCION declara una combinación con 0 pero OT declara la
        misma con cantidad real, EXTRACCION falta → FAIL."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"HPL_Pal_tab": 0}),
            _ot(tableros={"PLY_LAM_Pale": 2}),
            naming,
        )
        assert r.resultado == "FAIL"
        assert "EXTRACCION no declara" in r.detalle

    def test_pass_case_insensitive(self, naming):
        """Defensa en profundidad: si la OT viniera con casing irregular
        ('Rosa-Baby' vs naming 'Rosa-baby'), la comparación case-insensitive
        evita el falso FAIL."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"HPL_Rsa_tab": 1}),
            _ot(tableros={"PLY_LAM_Rosa-Baby": 1}),
            naming,
        )
        assert r.resultado == "PASS"

    def test_pass_normaliza_acentos(self, naming):
        """naming declara 'Cadaqués' (con tilde); la OT a veces se escribe
        'Cadaques' sin tilde. La comparación debe ignorar acentos."""
        r = check_tableros_codificados(
            _extr(tableros_codificados={"HPL_Cad_tab": 1}),
            _ot(tableros={"PLY_LAM_Cadaques": 1}),
            naming,
        )
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-75: prioridad INC
# ---------------------------------------------------------------------------

class TestC75:

    def test_pass_no_inc_y_vacio(self, reglas):
        r = check_prioridad_inc(_extr(), reglas)
        assert r.resultado == "PASS"

    def test_warn_no_inc_con_valor(self, reglas):
        r = check_prioridad_inc(_extr(prioridad_inc="P1"), reglas)
        assert r.resultado == "WARN"

    def test_pass_inc_con_p1(self, reglas):
        r = check_prioridad_inc(
            _extr(id_proyecto="EU-22376-INC", prioridad_inc="P1"), reglas,
        )
        assert r.resultado == "PASS"

    def test_pass_inc_con_p2(self, reglas):
        r = check_prioridad_inc(
            _extr(id_proyecto="EU-22376-INC", prioridad_inc="P2"), reglas,
        )
        assert r.resultado == "PASS"

    def test_warn_inc_sin_valor(self, reglas):
        r = check_prioridad_inc(
            _extr(id_proyecto="EU-22376-INC", prioridad_inc=""), reglas,
        )
        assert r.resultado == "WARN"
        assert "vacía" in r.detalle.lower() or "vacia" in r.detalle.lower()

    def test_warn_inc_valor_invalido(self, reglas):
        r = check_prioridad_inc(
            _extr(id_proyecto="EU-22376-INC", prioridad_inc="P3"), reglas,
        )
        assert r.resultado == "WARN"


# ---------------------------------------------------------------------------
# C-76: tabla EXTRACCION ↔ DESPIECE — IDs
# ---------------------------------------------------------------------------

class TestC76:

    def test_pass_mismos_ids(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1"), _fila("M2-P1"), _fila("R1")]
        piezas = [_pieza("M1-T1"), _pieza("M2-P1"), _pieza("R1")]
        r = check_tabla_ids_vs_despiece(extr, piezas)
        assert r.resultado == "PASS"

    def test_fail_id_huerfano_en_extr(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1"), _fila("FANTASMA")]
        piezas = [_pieza("M1-T1")]
        r = check_tabla_ids_vs_despiece(extr, piezas)
        assert r.resultado == "FAIL"
        assert "FANTASMA" in r.detalle

    def test_fail_id_solo_en_despiece(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1")]
        piezas = [_pieza("M1-T1"), _pieza("M2-P1")]
        r = check_tabla_ids_vs_despiece(extr, piezas)
        assert r.resultado == "FAIL"
        assert "M2-P1" in r.detalle

    def test_fail_extraccion_vacia(self):
        extr = _extr()
        extr.piezas_tabla = []
        r = check_tabla_ids_vs_despiece(extr, [_pieza("M1-T1")])
        assert r.resultado == "FAIL"


# ---------------------------------------------------------------------------
# C-77: dimensiones + material
# ---------------------------------------------------------------------------

class TestC77:

    def test_pass_todo_coincide(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1", ancho=120, alto=800)]
        piezas = [_pieza("M1-T1", ancho=120, alto=800)]
        r = check_tabla_dimensiones_material(extr, piezas)
        assert r.resultado == "PASS"

    def test_fail_ancho_distinto(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1", ancho=150)]
        piezas = [_pieza("M1-T1", ancho=120)]
        r = check_tabla_dimensiones_material(extr, piezas)
        assert r.resultado == "FAIL"
        assert "ancho" in r.detalle.lower()

    def test_fail_acabado_distinto(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1", acabado="Negro")]
        piezas = [_pieza("M1-T1", acabado="Zafiro")]
        r = check_tabla_dimensiones_material(extr, piezas)
        assert r.resultado == "FAIL"

    def test_pass_acabado_case_insensitive(self):
        """'ZAFIRO' (mayúscula) y 'Zafiro' deben compararse iguales."""
        extr = _extr()
        extr.piezas_tabla = [_fila("M1-T1", acabado="ZAFIRO")]
        piezas = [_pieza("M1-T1", acabado="Zafiro")]
        r = check_tabla_dimensiones_material(extr, piezas)
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-78: tipología + mecanizado
# ---------------------------------------------------------------------------

class TestC78:

    def test_pass_coincide(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M2-P1", tipologia="P", mecanizado="cazta.")]
        piezas = [_pieza("M2-P1", tipologia="P", mecanizado="cazta.")]
        r = check_tabla_tipologia_mecanizado(extr, piezas)
        assert r.resultado == "PASS"

    def test_fail_tipologia_distinta(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M2-P1", tipologia="C")]
        piezas = [_pieza("M2-P1", tipologia="P")]
        r = check_tabla_tipologia_mecanizado(extr, piezas)
        assert r.resultado == "FAIL"

    def test_fail_mecanizado_distinto(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M2-P1", tipologia="P", mecanizado="torn.")]
        piezas = [_pieza("M2-P1", tipologia="P", mecanizado="cazta.")]
        r = check_tabla_tipologia_mecanizado(extr, piezas)
        assert r.resultado == "FAIL"


# ---------------------------------------------------------------------------
# C-79: tirador completo
# ---------------------------------------------------------------------------

class TestC79:

    def test_pass_coincide(self):
        extr = _extr()
        extr.piezas_tabla = [_fila(
            "M2-P1", tirador="Round", posicion_tirador="2",
            apertura="I", color_tirador="Zafiro",
        )]
        piezas = [_pieza(
            "M2-P1", tirador="Round", posicion_tirador="2",
            apertura="I", color_tirador="Zafiro",
        )]
        r = check_tabla_tirador(extr, piezas)
        assert r.resultado == "PASS"

    def test_fail_apertura_distinta(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M2-P1", apertura="I")]
        piezas = [_pieza("M2-P1", apertura="D")]
        r = check_tabla_tirador(extr, piezas)
        assert r.resultado == "FAIL"

    def test_pass_color_case_insensitive(self):
        extr = _extr()
        extr.piezas_tabla = [_fila("M2-P1", color_tirador="ZAFIRO")]
        piezas = [_pieza("M2-P1", color_tirador="Zafiro")]
        r = check_tabla_tirador(extr, piezas)
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-80: baldas con herrajes
# ---------------------------------------------------------------------------

class TestC80:

    def test_pass_sin_baldas(self, reglas):
        r = check_baldas_herrajes(_extr(baldas_2h=0, baldas_3h=0), [], reglas)
        assert r.resultado == "PASS"

    def test_pass_2h_coincide(self, reglas):
        baldas = [_pieza("B1", ancho=200, alto=600, tipologia="B")]
        r = check_baldas_herrajes(_extr(baldas_2h=1), baldas, reglas)
        assert r.resultado == "PASS"

    def test_pass_orientacion_invertida(self, reglas):
        """200×600 ≡ 600×200 (orientación libre)."""
        baldas = [_pieza("B1", ancho=600, alto=200, tipologia="B")]
        r = check_baldas_herrajes(_extr(baldas_2h=1), baldas, reglas)
        assert r.resultado == "PASS"

    def test_warn_recuento_2h_distinto(self, reglas):
        baldas = [_pieza("B1", ancho=200, alto=600, tipologia="B")]
        r = check_baldas_herrajes(_extr(baldas_2h=2), baldas, reglas)
        assert r.resultado == "WARN"
        assert "2 herrajes" in r.detalle

    def test_pass_3h_coincide(self, reglas):
        baldas = [_pieza("B1", ancho=200, alto=1200, tipologia="B")]
        r = check_baldas_herrajes(_extr(baldas_3h=1), baldas, reglas)
        assert r.resultado == "PASS"

    def test_pieza_b_fuera_de_dims_no_cuenta(self, reglas):
        """Una balda B con dimensión no estándar no cuenta para 2h ni 3h."""
        baldas = [_pieza("B1", ancho=400, alto=500, tipologia="B")]
        r = check_baldas_herrajes(_extr(baldas_2h=0, baldas_3h=0), baldas, reglas)
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-81: altillos (FAIL bloqueante)
# ---------------------------------------------------------------------------

class TestC81:

    def test_pass_ambos_sin_altillos(self):
        r = check_altillos(_extr(), _ot())
        assert r.resultado == "PASS"
        assert r.bloquea

    def test_pass_desglose_coincide(self):
        extr = _extr(altillos_total=6, altillos_dims={"997x480x580": 4, "497x480x580": 2})
        ot = _ot(altillos_dims={"997x480x580": 4, "497x480x580": 2})
        r = check_altillos(extr, ot)
        assert r.resultado == "PASS"

    def test_fail_total_distinto(self):
        """OT dice x3 cuando EXTRACCION dice x4 — caso descrito por Esteban."""
        extr = _extr(altillos_total=6, altillos_dims={"997x480x580": 4, "497x480x580": 2})
        ot = _ot(altillos_dims={"997x480x580": 3, "497x480x580": 2})
        r = check_altillos(extr, ot)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "Total" in r.detalle
        assert "997x480x580" in r.detalle

    def test_fail_dimension_faltante_en_ot(self):
        """EXTRACCION declara una dimensión que la OT no tiene."""
        extr = _extr(altillos_total=4, altillos_dims={"997x480x580": 2, "747x480x580": 2})
        ot = _ot(altillos_dims={"997x480x580": 2})
        r = check_altillos(extr, ot)
        assert r.resultado == "FAIL"
        assert "747x480x580" in r.detalle

    def test_fail_extraccion_sin_altillos_pero_ot_si(self):
        """EXTRACCION dice 0 altillos, OT trae bloque con altillos."""
        ot = _ot(altillos_dims={"997x480x580": 1})
        r = check_altillos(_extr(), ot)
        assert r.resultado == "FAIL"

    def test_fail_extraccion_con_altillos_pero_ot_no(self):
        """EXTRACCION declara altillos, OT no los menciona."""
        extr = _extr(altillos_total=2, altillos_dims={"497x480x580": 2})
        r = check_altillos(extr, _ot())
        assert r.resultado == "FAIL"


# ---------------------------------------------------------------------------
# C-82: hornacinas (FAIL bloqueante)
# ---------------------------------------------------------------------------

class TestC82:

    def test_pass_ambos_cero(self):
        r = check_hornacinas(_extr(), _ot())
        assert r.resultado == "PASS"
        assert r.bloquea

    def test_pass_coincide(self):
        r = check_hornacinas(_extr(hornacinas=4), _ot(num_hornacinas=4))
        assert r.resultado == "PASS"

    def test_fail_distinto(self):
        r = check_hornacinas(_extr(hornacinas=4), _ot(num_hornacinas=3))
        assert r.resultado == "FAIL"
        assert "Hornacinas" in r.detalle
        assert "4" in r.detalle and "3" in r.detalle

    def test_fail_extraccion_si_ot_no(self):
        r = check_hornacinas(_extr(hornacinas=2), _ot())
        assert r.resultado == "FAIL"


# ---------------------------------------------------------------------------
# C-83: mueble de nevera (FAIL bloqueante)
# ---------------------------------------------------------------------------

class TestC83:

    def test_pass_ambos_sin_nevera(self):
        r = check_mueble_nevera(_extr(), _ot())
        assert r.resultado == "PASS"
        assert r.bloquea

    def test_pass_ambos_con_nevera(self):
        r = check_mueble_nevera(_extr(mueble_nevera=1), _ot(tiene_mueble_nevera=True))
        assert r.resultado == "PASS"

    def test_pass_extraccion_2_ot_si(self):
        """OT solo declara presencia (binaria); EXTRACCION con 2 también pasa."""
        r = check_mueble_nevera(_extr(mueble_nevera=2), _ot(tiene_mueble_nevera=True))
        assert r.resultado == "PASS"

    def test_fail_extraccion_si_ot_no(self):
        r = check_mueble_nevera(_extr(mueble_nevera=1), _ot())
        assert r.resultado == "FAIL"
        assert "Mueble de nevera" in r.detalle

    def test_fail_extraccion_no_ot_si(self):
        r = check_mueble_nevera(_extr(), _ot(tiene_mueble_nevera=True))
        assert r.resultado == "FAIL"
