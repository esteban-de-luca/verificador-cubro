"""tests/test_checks_dxf.py — Tests de C-30 a C-44."""

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
    check_distancia_bisagras,
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

    def test_pass_sin_layer_control(self, reglas):
        dxfs = [_dxf(layers={"0_ANOTACIONES", "13-BISELAR-EM5-Z0_8",
                              "10_12-CUTEXT-EM5-Z18"}, layers_geo=set())]
        r = check_layer_control(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_layer_control_presente(self, reglas):
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

    def test_pass_tablero_solo_rodapie(self, reglas):
        # Tablero solo de rodapié usa CORTAR_RODAPIE como corte perimetral
        dxfs = [_dxf(gama="LAM", acabado="Pale",
                     layers={"10_12-CORTAR_RODAPIE", "13-BISELAR-EM5-Z0_8"})]
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

    def test_pass_rejilla_presente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES", "8-REJILLA"})]
        ot = _ot(num_ventilacion=2)
        r = check_ventilacion_rejilla(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_rejilla_ausente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
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


# ---------------------------------------------------------------------------
# C-44
# ---------------------------------------------------------------------------

def _circulo(layer: str, x: float, y: float, r: float = 17.5) -> dict:
    return {"layer": layer, "x": x, "y": y, "r": r}


def _dxf_con_circulos(circulos: list[dict]) -> "DXFDoc":
    """DXFDoc mínimo con la lista de círculos indicada."""
    return DXFDoc(
        nombre="TEST_MDF_LACA_BLANCO_T1.dxf", tablero_num=1,
        material="MDF", gama="LAC", acabado="Blanco",
        circulos=circulos,
    )


L7 = "7-POCKET-EM5-Z14"
L6M = "6-POCKET-EM5-Z14"
L6P = "6A-POCKET-EM5-Z14_PAX"


class TestC44:

    # --- SKIP ---
    def test_skip_sin_dxfs(self, reglas):
        r = check_distancia_bisagras([], reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_circulos_pocket(self, reglas):
        # DXF sin ningún 7-POCKET
        dxfs = [_dxf_con_circulos([])]
        r = check_distancia_bisagras(dxfs, reglas)
        assert r.resultado == "SKIP"

    # --- METOD vertical: paso 50mm ---
    def test_pass_metod_vertical_2bisagras(self, reglas):
        # Puerta vertical: X constante, bisagras separadas 700mm (14×50)
        # Companion offset en Y (dY=22.5 > dX=9.5) → orientación V
        circs = [
            _circulo(L7,  -31.0, -6354.5),
            _circulo(L7,  -31.0, -5654.5),
            _circulo(L6M, -40.5, -6377.0, r=4.0),  # companion: dX=9.5, dY=22.5
            _circulo(L6M, -40.5, -5677.0, r=4.0),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "PASS"

    def test_fail_metod_vertical_distancia_no_multiplo(self, reglas):
        # Bisagras separadas 518mm — no es múltiplo de 50
        circs = [
            _circulo(L7,  1195.0, -6690.5),
            _circulo(L7,  1195.0, -6172.5),
            _circulo(L7,  1195.0, -5654.5),
            _circulo(L6M, 1185.5, -6713.0, r=4.0),
            _circulo(L6M, 1185.5, -6195.0, r=4.0),
            _circulo(L6M, 1185.5, -5677.0, r=4.0),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "518" in r.detalle

    def test_pass_metod_vertical_3bisagras_550(self, reglas):
        # 3 bisagras separadas 550mm (11×50) cada una
        circs = [
            _circulo(L7,  -31.0, -6754.5),
            _circulo(L7,  -31.0, -6204.5),
            _circulo(L7,  -31.0, -5654.5),
            _circulo(L6M, -40.5, -6777.0, r=4.0),
            _circulo(L6M, -40.5, -6227.0, r=4.0),
            _circulo(L6M, -40.5, -5677.0, r=4.0),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "PASS"

    # --- METOD horizontal: paso 50mm ---
    def test_pass_metod_horizontal_650mm(self, reglas):
        # Puerta horizontal: Y constante, bisagras separadas 650mm (13×50)
        # Companion offset en X (dX=22.5 > dY=9.5) → orientación H
        circs = [
            _circulo(L7,  -706.5, -31.0),
            _circulo(L7,   -56.5, -31.0),
            _circulo(L6M, -729.0, -40.5, r=4.0),  # companion: dX=22.5, dY=9.5
            _circulo(L6M,  -79.0, -40.5, r=4.0),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "PASS"

    # --- PAX horizontal: paso 32mm ---
    def test_pass_pax_horizontal_exacto(self, reglas):
        # Bisagras PAX separadas 928mm (29×32) y 192mm (6×32)
        circs = [
            _circulo(L7,  186.5, -1093.7),
            _circulo(L7, 1114.5, -1093.7),
            _circulo(L7, 1306.5, -1093.7),
            _circulo(L6P, 164.0, -1084.6, r=2.5),
            _circulo(L6P, 209.0, -1084.6, r=2.5),
            _circulo(L6P,1092.0, -1084.6, r=2.5),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "PASS"

    def test_fail_pax_horizontal_3mm_desviacion(self, reglas):
        # Bisagra PAX desplazada 3mm: 195mm en vez de 192mm (6×32)
        circs = [
            _circulo(L7,  4506.3, -1093.7),
            _circulo(L7,  5434.3, -1093.7),
            _circulo(L7,  5629.3, -1093.7),  # ← 3mm fuera de posición
            _circulo(L6P, 4483.8, -1084.6, r=2.5),
            _circulo(L6P, 4528.8, -1084.6, r=2.5),
            _circulo(L6P, 5411.8, -1084.6, r=2.5),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "FAIL"
        assert "195" in r.detalle or "925" in r.detalle

    def test_id_check(self, reglas):
        r = check_distancia_bisagras([], reglas)
        assert r.id == "C-44"

    def test_pass_dos_puertas_mismo_y_nesting(self, reglas):
        # Regresión T2: 2 puertas METOD horizontales en el mismo Y.
        # La distancia inter-puerta (939mm) no es múltiplo de 50 pero NO es
        # un error — es el hueco de nesting entre piezas distintas.
        # Intra-puerta: 700mm = 14×50 ✓ en cada puerta.
        circs = [
            # Puerta A
            _circulo(L7, -7165.42, -2891.0),
            _circulo(L7, -6465.42, -2891.0),
            # Puerta B
            _circulo(L7, -5526.42, -2891.0),
            _circulo(L7, -4826.42, -2891.0),
            # Companions (6-POCKET) — uno por cada 7-POCKET
            _circulo(L6M, -7187.92, -2881.5, r=4.0),
            _circulo(L6M, -7142.92, -2881.5, r=4.0),
            _circulo(L6M, -6487.92, -2881.5, r=4.0),
            _circulo(L6M, -6442.92, -2881.5, r=4.0),
            _circulo(L6M, -5548.92, -2881.5, r=4.0),
            _circulo(L6M, -5503.92, -2881.5, r=4.0),
            _circulo(L6M, -4848.92, -2881.5, r=4.0),
            _circulo(L6M, -4803.92, -2881.5, r=4.0),
        ]
        r = check_distancia_bisagras([_dxf_con_circulos(circs)], reglas)
        assert r.resultado == "PASS", r.detalle
