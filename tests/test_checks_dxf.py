"""tests/test_checks_dxf.py — Tests de C-30 a C-43."""

from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import DXFDoc, OTData, Pieza
from core.reglas_loader import cargar_reglas
from checks.checks_dxf import (
    check_layer_control,
    check_layer_0_sin_geometria,
    check_layers_rhino_ausentes,
    check_layer_anotaciones,
    check_layer_biselar_lam_lin,
    check_corte_perimetral,
    check_layer_desbaste_tirador,
    check_handcut_vs_tiradores,
    check_cajones_drill,
    check_bisagras_pocket,
    check_ventilacion_rejilla,
    check_mecanismo_hornacina,
    check_tirantes,
    check_layers_desuso,
)


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


def _dxf(
    nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf",
    material="PLY", gama="LAM", acabado="Pale", num=1,
    layers=None, layers_geo=None, conteos=None,
):
    if layers is None:
        layers = {"CONTROL", "0_ANOTACIONES", "13-BISELAR-EM5-Z0_8",
                  "10_12-CUTEXT-EM5-Z18"}
    if layers_geo is None:
        layers_geo = {"CONTROL"}
    return DXFDoc(
        nombre=nombre, tablero_num=num, material=material,
        gama=gama, acabado=acabado,
        layers=layers,
        layers_con_geometria=layers_geo,
        conteos_layer=conteos or {},
    )


def _pieza(id="M1-P1", material="PLY", gama="LAM", acabado="Pale",
           mecanizado="cazta.", tirador="", color_tirador=""):
    p = Pieza(id, 400, 798, material, gama, acabado, "P")
    p.mecanizado = mecanizado
    p.tirador = tirador
    p.color_tirador = color_tirador
    return p


def _ot(num_tiradores=0, num_ventilacion=0, colgadores_hornacina=None, tiene_tensores=None,
        modelos_tiradores=None):
    ot = OTData("EU-21822", "Test", "Semana 18", 10, 50.0, num_tiradores)
    ot.num_ventilacion = num_ventilacion
    ot.colgadores_hornacina = colgadores_hornacina
    ot.tiene_tensores = tiene_tensores
    ot.modelos_tiradores = modelos_tiradores or []
    return ot


# ---------------------------------------------------------------------------
# C-30
# ---------------------------------------------------------------------------

class TestC30:

    def test_pass_control_con_geometria(self, reglas):
        dxfs = [_dxf(layers_geo={"CONTROL"})]
        r = check_layer_control(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_control_sin_geometria(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"}, layers_geo=set())]
        r = check_layer_control(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_dxfs(self, reglas):
        r = check_layer_control([], reglas)
        assert r.resultado == "SKIP"

    def test_id_check(self, reglas):
        r = check_layer_control([], reglas)
        assert r.id == "C-30"
        assert r.grupo == "DXF"


# ---------------------------------------------------------------------------
# C-31
# ---------------------------------------------------------------------------

class TestC31:

    def test_pass_layer_0_sin_geometria(self, reglas):
        dxfs = [_dxf(layers_geo={"CONTROL"})]  # "0" not in layers_geo
        r = check_layer_0_sin_geometria(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_layer_0_con_geometria(self, reglas):
        dxfs = [_dxf(layers_geo={"CONTROL", "0"})]
        r = check_layer_0_sin_geometria(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_dxfs(self, reglas):
        r = check_layer_0_sin_geometria([], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-32
# ---------------------------------------------------------------------------

class TestC32:

    def test_pass_sin_layers_rhino(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        r = check_layers_rhino_ausentes(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_layer_rhino_presente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES", "HORNACINAS"})]
        r = check_layers_rhino_ausentes(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert "HORNACINAS" in r.detalle

    def test_fail_faktum(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "FAKTUM"})]
        r = check_layers_rhino_ausentes(dxfs, reglas)
        assert r.resultado == "FAIL"

    def test_skip_sin_dxfs(self, reglas):
        r = check_layers_rhino_ausentes([], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-33
# ---------------------------------------------------------------------------

class TestC33:

    def test_pass_anotaciones_presente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        r = check_layer_anotaciones(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_falta_anotaciones(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        r = check_layer_anotaciones(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_dxfs(self, reglas):
        r = check_layer_anotaciones([], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-34
# ---------------------------------------------------------------------------

class TestC34:

    def test_pass_lam_con_biselar(self, reglas):
        dxfs = [_dxf(gama="LAM", layers={"CONTROL", "0_ANOTACIONES",
                                           "13-BISELAR-EM5-Z0_8"})]
        r = check_layer_biselar_lam_lin(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_lam_sin_biselar(self, reglas):
        dxfs = [_dxf(gama="LAM", layers={"CONTROL", "0_ANOTACIONES"})]
        r = check_layer_biselar_lam_lin(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_pass_lac_no_necesita_biselar(self, reglas):
        dxfs = [_dxf(gama="LAC", layers={"CONTROL", "0_ANOTACIONES",
                                           "10_12-CONTORNO LACA"})]
        r = check_layer_biselar_lam_lin(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_pass_lin_con_biselar(self, reglas):
        dxfs = [_dxf(gama="LIN", layers={"CONTROL", "0_ANOTACIONES",
                                           "13-BISELAR-EM5-Z0_8"})]
        r = check_layer_biselar_lam_lin(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_skip_sin_dxfs(self, reglas):
        r = check_layer_biselar_lam_lin([], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-35
# ---------------------------------------------------------------------------

class TestC35:

    def test_pass_lam_estandar(self, reglas):
        dxfs = [_dxf(gama="LAM", acabado="Pale",
                     layers={"10_12-CUTEXT-EM5-Z18", "CONTROL"})]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_pass_lac_estandar_roto(self, reglas):
        # Roto is in lac_acabados_estandar
        dxfs = [_dxf(gama="LAC", acabado="Roto",
                     layers={"10_12-CUTEXT-EM5-Z18", "CONTROL"})]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_pass_lac_no_estandar_usa_contorno(self, reglas):
        dxfs = [_dxf(gama="LAC", acabado="Azul",
                     layers={"10_12-CONTORNO LACA", "CONTROL"})]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_lac_no_estandar_tiene_cutext(self, reglas):
        dxfs = [_dxf(gama="LAC", acabado="Azul",
                     layers={"10_12-CUTEXT-EM5-Z18", "CONTROL"})]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "FAIL"

    def test_skip_sin_dxfs(self, reglas):
        r = check_corte_perimetral([], reglas)
        assert r.resultado == "SKIP"

    def test_pass_lac_estandar_roto_con_no_estandar_en_proyecto(self, reglas):
        # Proyecto con Agave (no estándar) + Roto: ambos deben usar CONTORNO LACA
        dxfs = [
            _dxf(gama="LAC", acabado="Agave", layers={"10_12-CONTORNO LACA"}),
            _dxf(gama="LAC", acabado="Roto",  layers={"10_12-CONTORNO LACA"}),
        ]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_lac_estandar_roto_usa_cutext_cuando_hay_no_estandar(self, reglas):
        # Roto usa CUTEXT pero el proyecto tiene Agave (no estándar) → FAIL
        dxfs = [
            _dxf(gama="LAC", acabado="Agave", layers={"10_12-CONTORNO LACA"}),
            _dxf(gama="LAC", acabado="Roto",  layers={"10_12-CUTEXT-EM5-Z18"}),
        ]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "FAIL"

    def test_pass_mix_lac_solo_estandares(self, reglas):
        # Roto + Seda, ambos estándar → CUTEXT para los dos
        dxfs = [
            _dxf(gama="LAC", acabado="Roto", layers={"10_12-CUTEXT-EM5-Z18"}),
            _dxf(gama="LAC", acabado="Seda", layers={"10_12-CUTEXT-EM5-Z18"}),
        ]
        r = check_corte_perimetral(dxfs, reglas)
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-36
# ---------------------------------------------------------------------------

class TestC36:

    def test_pass_sin_tiradores(self, reglas):
        dxfs = [_dxf()]
        piezas = [_pieza(tirador="")]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_pass_color_con_layer_correcto(self, reglas):
        layer_roble = "4-DES1_IN-EM5-Z3_7_ROBLE"
        dxfs = [_dxf(layers={"CONTROL", layer_roble})]
        piezas = [_pieza(tirador="Round", color_tirador="Roble")]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_fail_color_sin_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        piezas = [_pieza(tirador="Round", color_tirador="Roble")]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "FAIL"

    def test_skip_sin_dxfs(self, reglas):
        r = check_layer_desbaste_tirador([], [], reglas)
        assert r.resultado == "SKIP"

    def test_pass_tirador_sin_geometria_ignorado(self, reglas):
        # Superline no genera geometría → no se verifica su color
        dxfs = [_dxf(layers={"CONTROL"})]
        piezas = [_pieza(tirador="Superline", color_tirador="Brass")]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_pass_mismo_color_geometria_y_no_geometria(self, reglas):
        # Superline+Roble no envenena colores_vistos; Round+Roble sí se verifica
        layer_roble = "4-DES1_IN-EM5-Z3_7_ROBLE"
        dxfs = [_dxf(layers={"CONTROL", layer_roble})]
        piezas = [
            _pieza(tirador="Superline", color_tirador="Roble"),
            _pieza(tirador="Round",     color_tirador="Roble"),
        ]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_fail_geometria_y_no_geometria_layer_ausente(self, reglas):
        # Round+Roble debe verificarse aunque Superline+Roble venga antes
        dxfs = [_dxf(layers={"CONTROL"})]
        piezas = [
            _pieza(tirador="Superline", color_tirador="Roble"),
            _pieza(tirador="Round",     color_tirador="Roble"),
        ]
        r = check_layer_desbaste_tirador(dxfs, piezas, reglas)
        assert r.resultado == "FAIL"


# ---------------------------------------------------------------------------
# C-37
# ---------------------------------------------------------------------------

class TestC37:

    # --- Tiradores CON geometría (Round / Square / Pill) ---

    def test_pass_round_handcut_coincide(self, reglas):
        """Round → requiere HANDCUT; cuenta coincide → PASS."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 5})]
        ot = _ot(num_tiradores=5, modelos_tiradores=["Round"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_round_handcut_no_coincide(self, reglas):
        """Round → requiere HANDCUT; cuenta no coincide → FAIL."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 3})]
        ot = _ot(num_tiradores=5, modelos_tiradores=["Round"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"
        assert "3" in r.detalle and "5" in r.detalle

    def test_fail_square_sin_handcut(self, reglas):
        """Square → requiere HANDCUT; layer ausente → FAIL."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=4, modelos_tiradores=["Square"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    def test_fail_pill_sin_handcut(self, reglas):
        """Pill → requiere HANDCUT; layer ausente → FAIL."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=2, modelos_tiradores=["Pill"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    # --- Tiradores SIN geometría (Superline / Bar / Knob…) ---

    def test_skip_superline_sin_handcut(self, reglas):
        """Superline no genera HANDCUT → SKIP aunque no haya layer."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=4, modelos_tiradores=["Superline"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"
        assert "Superline" in r.detalle

    def test_skip_bar_sin_handcut(self, reglas):
        """Bar no genera HANDCUT → SKIP."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=3, modelos_tiradores=["Bar"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"

    def test_skip_bar_superline_sin_handcut(self, reglas):
        """Bar + Superline: ninguno genera HANDCUT → SKIP."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=5, modelos_tiradores=["Bar", "Superline"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"

    # --- Mezcla: al menos uno con geometría ---

    def test_fail_pill_superline_sin_handcut(self, reglas):
        """Pill + Superline: Pill requiere HANDCUT; si no hay → FAIL."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=6, modelos_tiradores=["Pill", "Superline"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    def test_pass_round_bar_con_handcut(self, reglas):
        """Round + Bar: Round requiere HANDCUT; cuenta coincide → PASS."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 4})]
        ot = _ot(num_tiradores=4, modelos_tiradores=["Round", "Bar"])
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    # --- Casos base ---

    def test_skip_ot_sin_tiradores(self, reglas):
        """Sin tiradores en OT → SKIP."""
        dxfs = [_dxf()]
        ot = _ot(num_tiradores=0)
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        """Sin DXFs → SKIP."""
        r = check_handcut_vs_tiradores([], _ot(num_tiradores=3, modelos_tiradores=["Round"]), reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-38
# ---------------------------------------------------------------------------

class TestC38:

    def test_pass_cajones_con_drill(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "3-DRILL-EM5-Z12"})]
        piezas = [_pieza(mecanizado="torn.")]
        r = check_cajones_drill(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_fail_cajones_sin_drill(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        piezas = [_pieza(mecanizado="torn.")]
        r = check_cajones_drill(dxfs, piezas, reglas)
        assert r.resultado == "FAIL"

    def test_skip_sin_piezas_torn(self, reglas):
        dxfs = [_dxf()]
        piezas = [_pieza(mecanizado="cazta.")]
        r = check_cajones_drill(dxfs, piezas, reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        r = check_cajones_drill([], [], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-39
# ---------------------------------------------------------------------------

class TestC39:

    def test_pass_bisagras_con_pocket(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "6-POCKET-EM5-Z14"})]
        piezas = [_pieza(mecanizado="cazta.")]
        r = check_bisagras_pocket(dxfs, piezas, reglas)
        assert r.resultado == "PASS"

    def test_fail_bisagras_sin_pocket(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        piezas = [_pieza(mecanizado="cazta.")]
        r = check_bisagras_pocket(dxfs, piezas, reglas)
        assert r.resultado == "FAIL"

    def test_skip_sin_piezas_cazta(self, reglas):
        dxfs = [_dxf()]
        piezas = [_pieza(mecanizado="torn.")]
        r = check_bisagras_pocket(dxfs, piezas, reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        r = check_bisagras_pocket([], [], reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-40
# ---------------------------------------------------------------------------

class TestC40:

    def test_pass_rejilla_coincide(self, reglas):
        dxfs = [_dxf(conteos={"8-REJILLA": 2})]
        ot = _ot(num_ventilacion=2)
        r = check_ventilacion_rejilla(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_rejilla_no_coincide(self, reglas):
        dxfs = [_dxf(conteos={"8-REJILLA": 1})]
        ot = _ot(num_ventilacion=3)
        r = check_ventilacion_rejilla(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    def test_skip_ot_sin_ventilacion(self, reglas):
        r = check_ventilacion_rejilla([_dxf()], _ot(num_ventilacion=0), reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        r = check_ventilacion_rejilla([], _ot(num_ventilacion=2), reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-41
# ---------------------------------------------------------------------------

class TestC41:

    def test_pass_ot_hornacina_y_layer_presente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "MECANISMO_HORNACINA_Z12"})]
        r = check_mecanismo_hornacina(dxfs, _ot(colgadores_hornacina=2), reglas)
        assert r.resultado == "PASS"

    def test_pass_ot_sin_hornacina_y_sin_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        r = check_mecanismo_hornacina(dxfs, _ot(colgadores_hornacina=0), reglas)
        assert r.resultado == "PASS"

    def test_fail_ot_hornacina_sin_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        r = check_mecanismo_hornacina(dxfs, _ot(colgadores_hornacina=1), reglas)
        assert r.resultado == "FAIL"

    def test_fail_layer_sin_hornacina_en_ot(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "MECANISMO_HORNACINA_Z12"})]
        r = check_mecanismo_hornacina(dxfs, _ot(colgadores_hornacina=0), reglas)
        assert r.resultado == "FAIL"

    def test_skip_ot_sin_dato(self, reglas):
        r = check_mecanismo_hornacina([_dxf()], _ot(colgadores_hornacina=None), reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        r = check_mecanismo_hornacina([], _ot(colgadores_hornacina=1), reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-42
# ---------------------------------------------------------------------------

class TestC42:

    def test_pass_tensores_con_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "TIRANTE-POCKET-EM5-Z12"})]
        r = check_tirantes(dxfs, _ot(tiene_tensores=True), reglas)
        assert r.resultado == "PASS"

    def test_pass_sin_tensores_sin_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        r = check_tirantes(dxfs, _ot(tiene_tensores=False), reglas)
        assert r.resultado == "PASS"

    def test_fail_tensores_sin_layer(self, reglas):
        dxfs = [_dxf(layers={"CONTROL"})]
        r = check_tirantes(dxfs, _ot(tiene_tensores=True), reglas)
        assert r.resultado == "FAIL"

    def test_fail_layer_sin_tensores_en_ot(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "TIRANTE-POCKET-EM5-Z12"})]
        r = check_tirantes(dxfs, _ot(tiene_tensores=False), reglas)
        assert r.resultado == "FAIL"

    def test_skip_ot_sin_dato(self, reglas):
        r = check_tirantes([_dxf()], _ot(tiene_tensores=None), reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs(self, reglas):
        r = check_tirantes([], _ot(tiene_tensores=True), reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-43
# ---------------------------------------------------------------------------

class TestC43:

    def test_pass_sin_layers_desuso(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        r = check_layers_desuso(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_warn_layer_desuso_presente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "7-POCKET-EM5-Z14_CANGREJO"})]
        r = check_layers_desuso(dxfs, reglas)
        assert r.resultado == "WARN"
        assert not r.bloquea

    def test_skip_sin_dxfs(self, reglas):
        r = check_layers_desuso([], reglas)
        assert r.resultado == "SKIP"

    def test_id_check(self, reglas):
        r = check_layers_desuso([], reglas)
        assert r.id == "C-43"
