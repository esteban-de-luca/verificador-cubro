"""tests/test_checks_piezas.py — Tests de C-10 a C-29."""

from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import Pieza, OTData
from core.extractor_etiquetas_ean import FilaEtiqueta
from core.reglas_loader import cargar_reglas
from checks.checks_piezas import (
    check_num_piezas, check_ids_despiece_en_etiquetas, check_ids_despiece_en_ot,
    check_dimensiones, check_material_consistente, check_material_tablero,
    check_acabados, check_sufijo_tipologia, check_apertura_puertas,
    check_apertura_pax_con_tirador, check_sin_apertura_cajones,
    check_tirador_completo, check_posicion_sin_tirador, check_cazoletas,
    check_baldas_dimensiones, check_mecanizado_rodapies,
    check_tirador_en_sin_mecanizado, check_alto_puerta_sufijo,
)


@pytest.fixture(scope="session")
def r():
    return cargar_reglas(ROOT / "reglas.yaml")


# Helpers de construcción rápida
def _p(id="M1-P1", ancho=400, alto=798, mat="PLY", gama="LAM", acabado="Pale",
       tip="P", mec="cazta.", tirador="", pos="", color="", apertura="D"):
    return Pieza(id, ancho, alto, mat, gama, acabado, tip, mec, tirador, pos, color, apertura)


def _e(id="M1-P1", ancho=400, alto=798, mat="PLY", gama="LAM", acabado="Pale"):
    return FilaEtiqueta(id, ancho, alto, mat, gama, acabado)


def _ot(n=1, ids=None, peso=100.0):
    return OTData("EU-21822", "Test", "Semana 18", n, peso, 0, ids_piezas=ids or [])


# ===========================================================================
# C-10
# ===========================================================================
class TestC10:
    def test_pass_coinciden(self, r):
        piezas = [_p("M1-P1"), _p("M1-C1")]
        etq = [_e("M1-P1"), _e("M1-C1")]
        assert check_num_piezas(piezas, etq, _ot(2)).resultado == "PASS"

    def test_fail_despiece_mas_que_etiquetas(self, r):
        piezas = [_p("M1-P1"), _p("M1-C1")]
        etq = [_e("M1-P1")]
        res = check_num_piezas(piezas, etq, _ot(0))
        assert res.resultado == "FAIL" and res.bloquea

    def test_fail_despiece_difiere_ot(self, r):
        piezas = [_p("M1-P1")]
        etq = [_e("M1-P1")]
        res = check_num_piezas(piezas, etq, _ot(99))
        assert res.resultado == "FAIL"

    def test_ot_cero_no_compara_con_ot(self, r):
        piezas = [_p("M1-P1")]
        etq = [_e("M1-P1")]
        assert check_num_piezas(piezas, etq, _ot(0)).resultado == "PASS"


# ===========================================================================
# C-11
# ===========================================================================
class TestC11:
    def test_pass_todos_presentes(self):
        piezas = [_p("M1-P1"), _p("E1")]
        etq = [_e("M1-P1"), _e("E1")]
        assert check_ids_despiece_en_etiquetas(piezas, etq).resultado == "PASS"

    def test_fail_falta_en_etiquetas(self):
        piezas = [_p("M1-P1"), _p("M1-C1")]
        etq = [_e("M1-P1")]
        res = check_ids_despiece_en_etiquetas(piezas, etq)
        assert res.resultado == "FAIL"
        assert "M1-C1" in res.detalle


# ===========================================================================
# C-12
# ===========================================================================
class TestC12:
    def test_skip_sin_ids_en_ot(self):
        res = check_ids_despiece_en_ot([_p()], _ot(ids=[]))
        assert res.resultado == "SKIP"

    def test_pass_ids_en_ot(self):
        res = check_ids_despiece_en_ot([_p("M1-P1")], _ot(ids=["M1-P1"]))
        assert res.resultado == "PASS"

    def test_fail_falta_id_en_ot(self):
        res = check_ids_despiece_en_ot([_p("M1-P1"), _p("M1-C1")], _ot(ids=["M1-P1"]))
        assert res.resultado == "FAIL"
        assert "M1-C1" in res.detalle


# ===========================================================================
# C-13
# ===========================================================================
class TestC13:
    def test_pass_dimensiones_iguales(self):
        piezas = [_p("M1-P1", 400, 798)]
        etq = [_e("M1-P1", 400, 798)]
        assert check_dimensiones(piezas, etq).resultado == "PASS"

    def test_fail_ancho_diferente(self):
        piezas = [_p("M1-P1", 400, 798)]
        etq = [_e("M1-P1", 500, 798)]
        res = check_dimensiones(piezas, etq)
        assert res.resultado == "FAIL" and res.bloquea
        assert "M1-P1" in res.detalle

    def test_falta_etiqueta_no_se_cuenta_aqui(self):
        # pieza sin etiqueta → C-11 lo detecta, C-13 no genera error adicional
        piezas = [_p("M1-P1"), _p("M1-C1")]
        etq = [_e("M1-P1", 400, 798)]
        assert check_dimensiones(piezas, etq).resultado == "PASS"


# ===========================================================================
# C-14
# ===========================================================================
class TestC14:
    def test_pass_material_igual(self):
        piezas = [_p("M1-P1", mat="PLY", gama="LAM", acabado="Pale")]
        etq = [_e("M1-P1", mat="PLY", gama="LAM", acabado="Pale")]
        assert check_material_consistente(piezas, etq).resultado == "PASS"

    def test_fail_gama_diferente(self):
        piezas = [_p("M1-P1", mat="PLY", gama="LAM", acabado="Pale")]
        etq = [_e("M1-P1", mat="PLY", gama="LIN", acabado="Pale")]
        res = check_material_consistente(piezas, etq)
        assert res.resultado == "FAIL"

    def test_fail_acabado_diferente(self):
        piezas = [_p("M1-P1", mat="PLY", gama="LAM", acabado="Pale")]
        etq = [_e("M1-P1", mat="PLY", gama="LAM", acabado="Noir")]
        res = check_material_consistente(piezas, etq)
        assert res.resultado == "FAIL"


# ===========================================================================
# C-15
# ===========================================================================
class TestC15:
    def test_pass_ply_lam(self, r):
        piezas = [_p(mat="PLY", gama="LAM")]
        assert check_material_tablero(piezas, r).resultado == "PASS"

    def test_fail_ply_lac(self, r):
        piezas = [_p(mat="PLY", gama="LAC")]
        res = check_material_tablero(piezas, r)
        assert res.resultado == "FAIL" and res.bloquea
        assert "PLY" in res.detalle and "LAC" in res.detalle

    def test_fail_mdf_lam(self, r):
        piezas = [_p(mat="MDF", gama="LAM")]
        assert check_material_tablero(piezas, r).resultado == "FAIL"

    def test_pass_mdf_lac(self, r):
        piezas = [_p(mat="MDF", gama="LAC", acabado="Blanco")]
        assert check_material_tablero(piezas, r).resultado == "PASS"

    def test_material_desconocido_es_error(self, r):
        piezas = [_p(mat="MADERA_MAGICA", gama="LAM")]
        assert check_material_tablero(piezas, r).resultado == "FAIL"


# ===========================================================================
# C-16
# ===========================================================================
class TestC16:
    def test_pass_acabado_valido(self, r):
        piezas = [_p(mat="PLY", gama="LAM", acabado="Pale")]
        assert check_acabados(piezas, r).resultado == "PASS"

    def test_fail_acabado_no_en_lista(self, r):
        piezas = [_p(mat="PLY", gama="LAM", acabado="AcabadoInventado")]
        res = check_acabados(piezas, r)
        assert res.resultado == "FAIL"
        assert not res.bloquea  # C-16 no bloquea

    def test_pass_lac_blanco(self, r):
        piezas = [Pieza("M1-P1", 400, 798, "MDF", "LAC", "Blanco", "P")]
        assert check_acabados(piezas, r).resultado == "PASS"


# ===========================================================================
# C-17
# ===========================================================================
class TestC17:
    def test_pass_m2_p1_es_tipo_p(self, r):
        piezas = [Pieza("M2-P1", 400, 798, "PLY", "LAM", "Pale", "P")]
        assert check_sufijo_tipologia(piezas, r).resultado == "PASS"

    def test_pass_m2_c1_es_tipo_c(self, r):
        piezas = [Pieza("M2-C1", 400, 200, "PLY", "LAM", "Pale", "C")]
        assert check_sufijo_tipologia(piezas, r).resultado == "PASS"

    def test_fail_sufijo_p_con_tipo_c(self, r):
        piezas = [Pieza("M2-P1", 400, 798, "PLY", "LAM", "Pale", "C")]
        res = check_sufijo_tipologia(piezas, r)
        assert res.resultado == "FAIL" and res.bloquea

    def test_pass_e1_sin_sufijo_de_mueble(self, r):
        piezas = [Pieza("E1", 600, 200, "MDF", "LAC", "Blanco", "E")]
        assert check_sufijo_tipologia(piezas, r).resultado == "PASS"

    def test_pass_pl1_tipo_l(self, r):
        # M4-PL1: sufijo PL, primera letra P → válidas [P, X, L]
        piezas = [Pieza("M4-PL1", 400, 2000, "PLY", "LAM", "Pale", "L")]
        assert check_sufijo_tipologia(piezas, r).resultado == "PASS"


# ===========================================================================
# C-20
# ===========================================================================
class TestC20:
    def test_pass_puerta_con_apertura(self, r):
        piezas = [_p("M1-P1", tip="P", apertura="D")]
        assert check_apertura_puertas(piezas, r).resultado == "PASS"

    def test_fail_puerta_sin_apertura(self, r):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        apertura="")]
        res = check_apertura_puertas(piezas, r)
        assert res.resultado == "FAIL" and res.bloquea

    def test_cajon_no_requiere_apertura(self, r):
        piezas = [Pieza("M1-C1", 400, 200, "PLY", "LAM", "Pale", "C",
                        mecanizado="torn.", apertura="")]
        assert check_apertura_puertas(piezas, r).resultado == "PASS"


# ===========================================================================
# C-21
# ===========================================================================
class TestC21:
    def test_pass_pax_con_tirador_y_apertura(self, r):
        piezas = [Pieza("M1-X1", 400, 798, "PLY", "LAM", "Pale", "X",
                        mecanizado="cazta.", tirador="Round", posicion_tirador="3",
                        color_tirador="Cerezo", apertura="D")]
        assert check_apertura_pax_con_tirador(piezas, r).resultado == "PASS"

    def test_fail_pax_tirador_sin_apertura(self, r):
        piezas = [Pieza("M1-X1", 400, 798, "PLY", "LAM", "Pale", "X",
                        mecanizado="cazta.", tirador="Round", posicion_tirador="3",
                        color_tirador="Cerezo", apertura="")]
        res = check_apertura_pax_con_tirador(piezas, r)
        assert res.resultado == "FAIL"

    def test_pass_pax_sin_tirador_sin_apertura(self, r):
        piezas = [Pieza("M1-X1", 400, 798, "PLY", "LAM", "Pale", "X",
                        mecanizado="cazta.", apertura="")]
        assert check_apertura_pax_con_tirador(piezas, r).resultado == "PASS"


# ===========================================================================
# C-22
# ===========================================================================
class TestC22:
    def test_pass_cajon_sin_apertura(self, r):
        piezas = [Pieza("M1-C1", 400, 200, "PLY", "LAM", "Pale", "C",
                        mecanizado="torn.", apertura="")]
        assert check_sin_apertura_cajones(piezas, r).resultado == "PASS"

    def test_fail_cajon_con_apertura(self, r):
        piezas = [Pieza("M1-C1", 400, 200, "PLY", "LAM", "Pale", "C",
                        mecanizado="torn.", apertura="D")]
        res = check_sin_apertura_cajones(piezas, r)
        assert res.resultado == "FAIL" and res.bloquea


# ===========================================================================
# C-23
# ===========================================================================
class TestC23:
    def test_pass_tirador_completo(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="Round", posicion_tirador="3", color_tirador="Cerezo",
                        apertura="D")]
        assert check_tirador_completo(piezas).resultado == "PASS"

    def test_fail_falta_posicion(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="Round", posicion_tirador="", color_tirador="Cerezo",
                        apertura="D")]
        res = check_tirador_completo(piezas)
        assert res.resultado == "FAIL" and res.bloquea
        assert "posición" in res.detalle

    def test_fail_falta_color(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="Round", posicion_tirador="3", color_tirador="",
                        apertura="D")]
        assert check_tirador_completo(piezas).resultado == "FAIL"

    def test_pass_sin_tirador_no_aplica(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        mecanizado="cazta.", apertura="D")]
        assert check_tirador_completo(piezas).resultado == "PASS"


# ===========================================================================
# C-24
# ===========================================================================
class TestC24:
    def test_pass_posicion_con_tirador(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="Round", posicion_tirador="3", color_tirador="Cerezo")]
        assert check_posicion_sin_tirador(piezas).resultado == "PASS"

    def test_fail_posicion_sin_tirador(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="", posicion_tirador="3", color_tirador="")]
        res = check_posicion_sin_tirador(piezas)
        assert res.resultado == "FAIL" and res.bloquea

    def test_pass_ni_posicion_ni_tirador(self):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="", posicion_tirador="")]
        assert check_posicion_sin_tirador(piezas).resultado == "PASS"


# ===========================================================================
# C-25
# ===========================================================================
class TestC25:
    def test_pass_puerta_sin_zona_limite(self, r):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        mecanizado="cazta.", apertura="D")]
        assert check_cazoletas(piezas, r).resultado == "PASS"

    def test_pass_no_puertas(self, r):
        piezas = [Pieza("E1", 600, 200, "MDF", "LAC", "Blanco", "E")]
        assert check_cazoletas(piezas, r).resultado == "PASS"


# ===========================================================================
# C-26
# ===========================================================================
class TestC26:
    def test_pass_balda_600(self, r):
        piezas = [Pieza("B1", 600, 200, "MDF", "LAC", "Blanco", "B",
                        mecanizado="herrajes")]
        assert check_baldas_dimensiones(piezas, r).resultado == "PASS"

    def test_fail_balda_dimensiones_no_estandar(self, r):
        piezas = [Pieza("B1", 750, 300, "MDF", "LAC", "Blanco", "B",
                        mecanizado="herrajes")]
        res = check_baldas_dimensiones(piezas, r)
        assert res.resultado == "FAIL" and res.bloquea

    def test_pass_balda_sin_mecanizado_no_aplica(self, r):
        piezas = [Pieza("B1", 750, 300, "PLY", "LAM", "Pale", "B")]
        assert check_baldas_dimensiones(piezas, r).resultado == "PASS"


# ===========================================================================
# C-27
# ===========================================================================
class TestC27:
    def test_warn_rodapie_con_mecanizado(self, r):
        piezas = [Pieza("R1", 100, 80, "PLY", "LAM", "Pale", "R",
                        mecanizado="cazta.")]
        res = check_mecanizado_rodapies(piezas, r)
        assert res.resultado == "WARN" and not res.bloquea

    def test_pass_rodapie_sin_mecanizado(self, r):
        piezas = [Pieza("R1", 100, 80, "PLY", "LAM", "Pale", "R")]
        assert check_mecanizado_rodapies(piezas, r).resultado == "PASS"

    def test_warn_rv_sin_vent(self, r):
        piezas = [Pieza("R2", 100, 80, "PLY", "LAM", "Pale", "RV",
                        mecanizado="")]
        assert check_mecanizado_rodapies(piezas, r).resultado == "WARN"

    def test_pass_rv_con_vent(self, r):
        piezas = [Pieza("R2", 100, 80, "PLY", "LAM", "Pale", "RV",
                        mecanizado="vent.")]
        assert check_mecanizado_rodapies(piezas, r).resultado == "PASS"


# ===========================================================================
# C-28
# ===========================================================================
class TestC28:
    def test_warn_tapeta_con_tirador(self, r):
        piezas = [Pieza("M1-T1", 100, 600, "PLY", "LAM", "Pale", "T",
                        tirador="Round", posicion_tirador="3", color_tirador="Cerezo")]
        res = check_tirador_en_sin_mecanizado(piezas, r)
        assert res.resultado == "WARN" and not res.bloquea

    def test_pass_tapeta_sin_tirador(self, r):
        piezas = [Pieza("M1-T1", 100, 600, "PLY", "LAM", "Pale", "T")]
        assert check_tirador_en_sin_mecanizado(piezas, r).resultado == "PASS"

    def test_pass_puerta_con_tirador_no_es_warn(self, r):
        # Puerta P no está en tipologias_sin_mecanizado
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        tirador="Round", posicion_tirador="3", color_tirador="Cerezo",
                        apertura="D")]
        assert check_tirador_en_sin_mecanizado(piezas, r).resultado == "PASS"


# ===========================================================================
# C-29
# ===========================================================================
class TestC29:
    def test_pass_alto_acaba_en_98(self, r):
        piezas = [Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                        mecanizado="cazta.", apertura="D")]
        assert check_alto_puerta_sufijo(piezas, r).resultado == "PASS"

    def test_warn_alto_no_acaba_en_98(self, r):
        piezas = [Pieza("M1-P1", 400, 800, "PLY", "LAM", "Pale", "P",
                        mecanizado="cazta.", apertura="D")]
        res = check_alto_puerta_sufijo(piezas, r)
        assert res.resultado == "WARN" and not res.bloquea

    def test_pass_598_acaba_en_98(self, r):
        piezas = [Pieza("M1-P1", 400, 598, "PLY", "LAM", "Pale", "P",
                        mecanizado="cazta.", apertura="D")]
        assert check_alto_puerta_sufijo(piezas, r).resultado == "PASS"

    def test_no_aplica_cajon(self, r):
        piezas = [Pieza("M1-C1", 400, 200, "PLY", "LAM", "Pale", "C",
                        mecanizado="torn.")]
        assert check_alto_puerta_sufijo(piezas, r).resultado == "PASS"
