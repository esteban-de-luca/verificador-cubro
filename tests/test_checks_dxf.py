"""tests/test_checks_dxf.py — Tests de C-30 a C-45."""

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
    check_nesting_laca,
    check_geometria_prohibida,
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
        modelos_tiradores=None, tiradores_por_modelo=None):
    ot = OTData("EU-21822", "Test", "Semana 18", 10, 50.0, num_tiradores)
    ot.num_ventilacion = num_ventilacion
    ot.colgadores_hornacina = colgadores_hornacina
    ot.tiene_tensores = tiene_tensores
    ot.modelos_tiradores = modelos_tiradores or []
    if tiradores_por_modelo is not None:
        ot.tiradores_por_modelo = tiradores_por_modelo
    elif modelos_tiradores and len(modelos_tiradores) == 1:
        # Caso simple: un solo modelo concentra todo num_tiradores
        ot.tiradores_por_modelo = {modelos_tiradores[0]: num_tiradores}
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
        ot = _ot(num_tiradores=6, modelos_tiradores=["Pill", "Superline"],
                 tiradores_por_modelo={"Pill": 4, "Superline": 2})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    def test_pass_round_bar_con_handcut(self, reglas):
        """Round + Bar: solo los Round cuentan; cuenta coincide → PASS."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 4})]
        ot = _ot(num_tiradores=6, modelos_tiradores=["Round", "Bar"],
                 tiradores_por_modelo={"Round": 4, "Bar": 2})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_pass_plantea_round_solo_round_genera_handcut(self, reglas):
        """Bug real SP-21613: Plantea(9) + Round(4) → HANDCUT debe ser 4 (solo Round)."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 4})]
        ot = _ot(num_tiradores=13, modelos_tiradores=["Plantea", "Round"],
                 tiradores_por_modelo={"Plantea": 9, "Round": 4})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_plantea_round_handcut_no_coincide(self, reglas):
        """Plantea(9) + Round(4) pero solo 2 HANDCUT → FAIL con detalle correcto."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 2})]
        ot = _ot(num_tiradores=13, modelos_tiradores=["Plantea", "Round"],
                 tiradores_por_modelo={"Plantea": 9, "Round": 4})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"
        assert "2" in r.detalle and "4" in r.detalle
        assert "13" not in r.detalle  # ya no compara contra el total

    def test_skip_fallback_sin_emparejado_modelos_mixtos(self, reglas):
        """Si el extractor no pudo emparejar y hay mezcla con/sin geometría → SKIP."""
        dxfs = [_dxf(conteos={"9_11-HANDCUT-EM5-Z18": 4})]
        ot = _ot(num_tiradores=13, modelos_tiradores=["Plantea", "Round"],
                 tiradores_por_modelo={})  # vacío explícito
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"

    # --- Modelos compuestos 'Round/Square' (varias piezas con tiradores
    # distintos en la misma columna del cuadro INFORMACION DE CORTE) ---

    def test_pass_modelo_compuesto_round_square(self, reglas):
        """Bug real SP-21613 Apto 1: Square(5) + Round/Square(19) → 24 HANDCUT esperados."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 24})]
        ot = _ot(num_tiradores=24, modelos_tiradores=["Square", "Round/Square"],
                 tiradores_por_modelo={"Square": 5, "Round/Square": 19})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_modelo_compuesto_no_coincide(self, reglas):
        """Square(5) + Round/Square(19) pero solo 20 HANDCUT en DXF → FAIL."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 20})]
        ot = _ot(num_tiradores=24, modelos_tiradores=["Square", "Round/Square"],
                 tiradores_por_modelo={"Square": 5, "Round/Square": 19})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "FAIL"
        assert "20" in r.detalle and "24" in r.detalle

    def test_skip_modelo_compuesto_mixto_ambiguo(self, reglas):
        """'Round/Plantea': Round genera HANDCUT pero Plantea no → SKIP por ambigüedad."""
        layer = "9_11-HANDCUT-EM5-Z18"
        dxfs = [_dxf(conteos={layer: 5})]
        ot = _ot(num_tiradores=10, modelos_tiradores=["Round/Plantea"],
                 tiradores_por_modelo={"Round/Plantea": 10})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"
        assert "ambig" in r.detalle.lower()

    def test_skip_modelo_compuesto_sin_geometria(self, reglas):
        """'Bar/Superline': ningún sub-modelo genera HANDCUT → SKIP."""
        dxfs = [_dxf(conteos={})]
        ot = _ot(num_tiradores=4, modelos_tiradores=["Bar/Superline"],
                 tiradores_por_modelo={"Bar/Superline": 4})
        r = check_handcut_vs_tiradores(dxfs, ot, reglas)
        assert r.resultado == "SKIP"

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

    def test_pass_sin_rejilla_y_ot_cero(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        r = check_ventilacion_rejilla(dxfs, _ot(num_ventilacion=0), reglas)
        assert r.resultado == "PASS"

    def test_fail_rejilla_ausente(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        ot = _ot(num_ventilacion=3)
        r = check_ventilacion_rejilla(dxfs, ot, reglas)
        assert r.resultado == "FAIL"

    def test_fail_layer_sin_declaracion_ot(self, reglas):
        dxfs = [_dxf(layers={"CONTROL", "8-REJILLA"})]
        r = check_ventilacion_rejilla(dxfs, _ot(num_ventilacion=0), reglas)
        assert r.resultado == "FAIL"

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


def _bbox(xmin, xmax, ymin, ymax, layer="10_12-CUTEXT-EM5-Z18") -> dict:
    """Bounding box de pieza (contorno CUTEXT o CONTORNO LACA)."""
    return {"layer": layer, "xmin": xmin, "xmax": xmax,
            "ymin": ymin, "ymax": ymax}


def _bbox_envolvente(circulos: list[dict], margen: float = 100) -> dict:
    """Bbox que envuelve todos los círculos con `margen` mm de margen extra."""
    xs = [c["x"] for c in circulos]
    ys = [c["y"] for c in circulos]
    return _bbox(min(xs) - margen, max(xs) + margen,
                 min(ys) - margen, max(ys) + margen)


def _dxf_con_circulos(circulos: list[dict],
                      piezas_contorno: list[dict] | None = None) -> "DXFDoc":
    """DXFDoc mínimo. Si piezas_contorno=None, genera un único bbox envolvente
    de todos los círculos (con 100 mm de margen) para que cada cazoleta tenga
    pieza asignada."""
    if piezas_contorno is None:
        piezas_contorno = [_bbox_envolvente(circulos)] if circulos else []
    return DXFDoc(
        nombre="TEST_MDF_LACA_BLANCO_T1.dxf", tablero_num=1,
        material="MDF", gama="LAC", acabado="Blanco",
        circulos=circulos,
        piezas_contorno=piezas_contorno,
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
        # 518mm no es múltiplo de 50 → desfase +18mm respecto a 10×50=500
        assert "+18" in r.detalle
        assert "METOD" in r.detalle

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
        # 195mm vs 6×32=192 → desfase +3mm
        assert "+3" in r.detalle
        assert "PAX" in r.detalle

    def test_id_check(self, reglas):
        r = check_distancia_bisagras([], reglas)
        assert r.id == "C-44"

    def test_pass_dos_puertas_mismo_y_nesting(self, reglas):
        # Regresión T2: 2 puertas METOD horizontales en el mismo Y.
        # Cada puerta tiene su propio contorno; el hueco inter-puerta (939mm)
        # nunca se mide porque las cazoletas se agrupan POR PIEZA.
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
        contornos = [
            _bbox(-7250, -6380, -2950, -2830),  # Puerta A
            _bbox(-5610, -4740, -2950, -2830),  # Puerta B
        ]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle

    # --- PAX altillo (pieza < 700mm): cazoleta a 68mm exactos del borde ---
    def test_pass_pax_altillo_cazoletas_a_68mm(self, reglas):
        # Altillo PAX 476mm horizontal: cazoletas a 68mm de cada borde.
        # Distancia entre cazoletas = 476 - 68 - 68 = 340mm (NO múltiplo de 32),
        # pero la regla altillo solo exige los 68mm desde el borde.
        circs = [
            _circulo(L7, 2443.0, -27733.2),  # 68mm de xmin=2375
            _circulo(L7, 2783.0, -27733.2),  # 68mm de xmax=2851
            # Companions PAX (offset dX≈22.5, dY≈9.1 → orient H)
            _circulo(L6P, 2465.5, -27724.1, r=2.5),
            _circulo(L6P, 2420.5, -27724.1, r=2.5),
            _circulo(L6P, 2805.5, -27724.1, r=2.5),
            _circulo(L6P, 2760.5, -27724.1, r=2.5),
        ]
        contornos = [_bbox(2375, 2851, -27756, -27510)]  # 476×246mm
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle

    def test_fail_pax_altillo_cazoleta_no_a_68mm(self, reglas):
        # Altillo PAX 476mm con una cazoleta a 60mm del borde (no 68).
        circs = [
            _circulo(L7, 2435.0, -27733.2),  # 60mm de xmin=2375 → ✗
            _circulo(L7, 2783.0, -27733.2),  # 68mm de xmax=2851 ✓
            _circulo(L6P, 2457.5, -27724.1, r=2.5),
            _circulo(L6P, 2412.5, -27724.1, r=2.5),
            _circulo(L6P, 2805.5, -27724.1, r=2.5),
            _circulo(L6P, 2760.5, -27724.1, r=2.5),
        ]
        contornos = [_bbox(2375, 2851, -27756, -27510)]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "FAIL"
        assert r.bloquea
        # cazoleta a 60mm del borde (esperado 68) → desfase -8mm
        assert "68" in r.detalle and "-8" in r.detalle

    def test_pass_pax_altillo_contorno_laca(self, reglas):
        # Altillo PAX en una pieza con contorno layer "10_12-CONTORNO LACA"
        # (no estándar: e.g. acabado Agave). Misma regla aplica.
        circs = [
            _circulo(L7, 2443.0, -27733.2),
            _circulo(L7, 2783.0, -27733.2),
            _circulo(L6P, 2465.5, -27724.1, r=2.5),
            _circulo(L6P, 2420.5, -27724.1, r=2.5),
            _circulo(L6P, 2805.5, -27724.1, r=2.5),
            _circulo(L6P, 2760.5, -27724.1, r=2.5),
        ]
        contornos = [_bbox(2375, 2851, -27756, -27510,
                           layer="10_12-CONTORNO LACA")]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle

    def test_pass_convivencia_altillo_y_puerta_grande(self, reglas):
        # Caso real EU-21742: convivencia de pieza grande PAX (cazoletas a
        # múltiplos de 32) y altillo PAX (cazoletas a 68mm del borde) en
        # el mismo tablero, alineados en el mismo Y.
        circs = [
            # Pieza grande (X=10..2360, 2350mm wide): 3 cazoletas
            _circulo(L7, 1117.0, -27733.2),
            _circulo(L7, 1309.0, -27733.2),  # 192 = 6×32
            _circulo(L7, 2237.0, -27733.2),  # 928 = 29×32
            # Altillo (X=2375..2851, 476mm wide): 2 cazoletas
            _circulo(L7, 2443.0, -27733.2),  # 68mm del borde xmin=2375
            _circulo(L7, 2783.0, -27733.2),  # 68mm del borde xmax=2851
            # Companions PAX (orient H) — dummies suficientes para clasificar
            _circulo(L6P, 1094.5, -27724.1, r=2.5),
            _circulo(L6P, 1139.5, -27724.1, r=2.5),
            _circulo(L6P, 1286.5, -27724.1, r=2.5),
            _circulo(L6P, 1331.5, -27724.1, r=2.5),
            _circulo(L6P, 2214.5, -27724.1, r=2.5),
            _circulo(L6P, 2259.5, -27724.1, r=2.5),
            _circulo(L6P, 2420.5, -27724.1, r=2.5),
            _circulo(L6P, 2465.5, -27724.1, r=2.5),
            _circulo(L6P, 2760.5, -27724.1, r=2.5),
            _circulo(L6P, 2805.5, -27724.1, r=2.5),
        ]
        contornos = [
            _bbox(10, 2360, -27756, -27510),    # pieza grande
            _bbox(2375, 2851, -27756, -27510),  # altillo
        ]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle

    def test_fail_pieza_con_una_sola_bisagra(self, reglas):
        # Una pieza con UNA sola cazoleta es siempre FAIL (toda puerta
        # debe tener ≥ 2 bisagras).
        circs = [
            _circulo(L7, 1117.0, -27733.2),
            _circulo(L6P, 1094.5, -27724.1, r=2.5),
            _circulo(L6P, 1139.5, -27724.1, r=2.5),
        ]
        contornos = [_bbox(1000, 2000, -27800, -27500)]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "1 bisagra" in r.detalle.lower() or "solo 1" in r.detalle.lower()

    def test_fail_bisagra_sin_pieza_asignada(self, reglas):
        # Cazoleta fuera del contorno → FAIL.
        circs = [
            _circulo(L7, 9999.0, -27733.2),  # fuera del bbox
            _circulo(L6P, 9976.5, -27724.1, r=2.5),
            _circulo(L6P, 10021.5, -27724.1, r=2.5),
        ]
        contornos = [_bbox(0, 2000, -27800, -27500)]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "FAIL"
        assert "sin pieza asignada" in r.detalle

    # --- Excepciones: configuraciones de puerta con herrajes custom ---
    def test_pass_excepcion_puerta_4_bisagras_798x256(self, reglas):
        # Caso real EU-21119 T2: puerta 798×256 con 4 bisagras dispuestas en
        # parrilla 2×2 (700mm en X, 220mm en Y). 2 cazoletas tienen companions
        # en otra layer (3-DRILL). Configuración custom validada por diseño.
        # La excepción declarada en reglas.yaml debe hacer PASS.
        circs = [
            # 4 cazoletas (r=17.5) en parrilla 2x2
            _circulo(L7, 2184.5, -3618.0),
            _circulo(L7, 2884.5, -3618.0),
            _circulo(L7, 2184.5, -3398.0),
            _circulo(L7, 2884.5, -3398.0),
            # Solo las 2 cazoletas inferiores tienen companions METOD reales
            _circulo(L6M, 2162.0, -3608.5, r=4.0),
            _circulo(L6M, 2207.0, -3608.5, r=4.0),
            _circulo(L6M, 2862.0, -3608.5, r=4.0),
            _circulo(L6M, 2907.0, -3608.5, r=4.0),
        ]
        contornos = [_bbox(2135.5, 2933.5, -3641.5, -3385.5)]  # 798×256
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle

    def test_fail_pieza_misma_dim_pero_otro_n_cazoletas(self, reglas):
        # Pieza 798×256 con SOLO 2 cazoletas (no 4) → la excepción NO aplica
        # (n_cazoletas debe coincidir exactamente). La validación normal
        # detecta que las 2 cazoletas no son múltiplo de 50 entre ellas.
        circs = [
            _circulo(L7, 2184.5, -3618.0),
            _circulo(L7, 2233.0, -3618.0),  # distancia 48.5mm — NO múltiplo
            _circulo(L6M, 2162.0, -3608.5, r=4.0),
            _circulo(L6M, 2207.0, -3608.5, r=4.0),
            _circulo(L6M, 2210.5, -3608.5, r=4.0),
            _circulo(L6M, 2255.5, -3608.5, r=4.0),
        ]
        contornos = [_bbox(2135.5, 2933.5, -3641.5, -3385.5)]
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "FAIL"
        # La excepción no aplica porque solo hay 2 cazoletas, no 4

    def test_pass_excepcion_dimensiones_rotadas(self, reglas):
        # La excepción casa en cualquier orientación: 256×798 también.
        circs = [
            _circulo(L7, 3618.0, -2184.5),
            _circulo(L7, 3618.0, -2884.5),
            _circulo(L7, 3398.0, -2184.5),
            _circulo(L7, 3398.0, -2884.5),
            _circulo(L6M, 3608.5, -2162.0, r=4.0),
            _circulo(L6M, 3608.5, -2207.0, r=4.0),
            _circulo(L6M, 3608.5, -2862.0, r=4.0),
            _circulo(L6M, 3608.5, -2907.0, r=4.0),
        ]
        contornos = [_bbox(3385.5, 3641.5, -2933.5, -2135.5)]  # 256×798
        r = check_distancia_bisagras(
            [_dxf_con_circulos(circs, piezas_contorno=contornos)], reglas
        )
        assert r.resultado == "PASS", r.detalle


# ---------------------------------------------------------------------------
# C-45: disposición piezas LAC en nesting (pegadas vs separadas 15 mm)
# ---------------------------------------------------------------------------

L_LACA = "10_12-CONTORNO LACA"
L_CUTEXT = "10_12-CUTEXT-EM5-Z18"


def _dxf_lac(acabado: str, contornos: list[dict],
             nombre: str | None = None) -> "DXFDoc":
    """DXFDoc LAC con contornos arbitrarios — para tests de C-45."""
    return DXFDoc(
        nombre=nombre or f"EU-99999_X_MDF_LACA_{acabado.upper()}_T1.dxf",
        tablero_num=1,
        material="MDF", gama="LAC", acabado=acabado,
        piezas_contorno=contornos,
    )


def _piezas_en_fila(n: int, gap: float, ancho: float = 398, alto: float = 596,
                    layer: str = L_LACA, x0: float = 0, y0: float = 0) -> list[dict]:
    """Genera n bboxes en una fila horizontal con `gap` mm entre piezas."""
    out = []
    x = x0
    for _ in range(n):
        out.append(_bbox(x, x + ancho, y0, y0 + alto, layer=layer))
        x += ancho + gap
    return out


class TestC45:

    # --- Ejemplo 1: LAC Marga único, separadas 15 mm → FAIL ---
    def test_solo_marga_separadas_15_falla(self, reglas):
        dxf = _dxf_lac("Marga", _piezas_en_fila(3, gap=15))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "FAIL"
        assert "15" in r.detalle and "Marga" in r.detalle

    # --- Ejemplo 2: LAC Marga único, pegadas → PASS ---
    def test_solo_marga_pegadas_pasa(self, reglas):
        dxf = _dxf_lac("Marga", _piezas_en_fila(4, gap=0))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "PASS"

    # --- Ejemplo 3: LAC Roto único, separadas 15 mm → PASS ---
    def test_solo_roto_separadas_15_pasa(self, reglas):
        dxf = _dxf_lac("Roto", _piezas_en_fila(5, gap=15, layer=L_CUTEXT))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "PASS"

    # --- Ejemplo 4: LAC Roto único, separadas 12 mm → FAIL ---
    def test_solo_roto_separadas_12_falla(self, reglas):
        dxf = _dxf_lac("Roto", _piezas_en_fila(5, gap=12, layer=L_CUTEXT))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "FAIL"
        assert "15" in r.detalle  # gap esperado

    # --- LAC Seda único, separadas 26 mm (> 15) → PASS ---
    # Caso EU-20868: el régimen estándar acepta cualquier gap ≥ 15 mm.
    def test_solo_seda_separadas_mas_de_15_pasa(self, reglas):
        dxf = _dxf_lac("Seda", _piezas_en_fila(3, gap=26, layer=L_CUTEXT))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "PASS"

    # --- LAC Seda único, separadas 17.9 mm en X → PASS (gap > 15) ---
    def test_solo_seda_gap_ligeramente_mayor_a_15_pasa(self, reglas):
        dxf = _dxf_lac("Seda", _piezas_en_fila(4, gap=17.9, layer=L_CUTEXT))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "PASS"

    # --- Ejemplo 5: LAC Roto único, pegadas → FAIL ---
    def test_solo_roto_pegadas_falla(self, reglas):
        dxf = _dxf_lac("Roto", _piezas_en_fila(5, gap=0, layer=L_CUTEXT))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "FAIL"

    # --- Ejemplo 6: Roto + Marga, DXF Roto separado 15 → FAIL ---
    def test_mixto_dxf_roto_separado_15_falla(self, reglas):
        # En proyecto contaminado, también el DXF de Roto usa CONTORNO LACA
        dxf_roto = _dxf_lac("Roto", _piezas_en_fila(4, gap=15))
        dxf_marga = _dxf_lac("Marga", _piezas_en_fila(2, gap=0))
        r = check_nesting_laca([dxf_roto, dxf_marga], reglas)
        assert r.resultado == "FAIL"
        # El error menciona Marga como motivo de la regla aplicada al Roto
        assert "Roto" in r.detalle and "Marga" in r.detalle

    # --- Ejemplo 7: Roto + Marga, DXF Roto pegado → PASS ---
    def test_mixto_dxf_roto_pegado_pasa(self, reglas):
        dxf_roto = _dxf_lac("Roto", _piezas_en_fila(4, gap=0))
        dxf_marga = _dxf_lac("Marga", _piezas_en_fila(3, gap=0))
        r = check_nesting_laca([dxf_roto, dxf_marga], reglas)
        assert r.resultado == "PASS"

    # --- Ejemplo 8: Roto + Marga, DXF Marga pegado → PASS ---
    def test_mixto_dxf_marga_pegado_pasa(self, reglas):
        dxf_roto = _dxf_lac("Roto", _piezas_en_fila(2, gap=0))
        dxf_marga = _dxf_lac("Marga", _piezas_en_fila(4, gap=0))
        r = check_nesting_laca([dxf_roto, dxf_marga], reglas)
        assert r.resultado == "PASS"

    # --- Ejemplo 9: Blanco + Crema + Seda, separadas 8 → FAIL ---
    def test_todos_estandar_gap_incorrecto_falla(self, reglas):
        dxfs = [
            _dxf_lac("Blanco", _piezas_en_fila(3, gap=8, layer=L_CUTEXT)),
            _dxf_lac("Crema",  _piezas_en_fila(2, gap=15, layer=L_CUTEXT)),
            _dxf_lac("Seda",   _piezas_en_fila(2, gap=15, layer=L_CUTEXT)),
        ]
        r = check_nesting_laca(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert "Blanco" in r.detalle

    # --- Ejemplo 10: Marga + Roto + Blanco, gap 0.3 (ruido) → PASS ---
    def test_ruido_floating_point_dentro_de_eps_pasa(self, reglas):
        # Régimen pegado, gap 0.3 mm → dentro de EPS=0.5
        dxfs = [
            _dxf_lac("Marga",  _piezas_en_fila(2, gap=0)),
            _dxf_lac("Roto",   _piezas_en_fila(2, gap=0.3)),
            _dxf_lac("Blanco", _piezas_en_fila(3, gap=0.3)),
        ]
        r = check_nesting_laca(dxfs, reglas)
        assert r.resultado == "PASS"

    # --- Edge cases ---

    def test_skip_sin_dxfs(self, reglas):
        r = check_nesting_laca([], reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_dxfs_lac(self, reglas):
        # Solo gama LAM → C-45 no aplica
        dxf = DXFDoc(
            nombre="EU-99999_X_PLY_LAMINADO_PALE_T1.dxf", tablero_num=1,
            material="PLY", gama="LAM", acabado="Pale",
            piezas_contorno=_piezas_en_fila(3, gap=15, layer=L_CUTEXT),
        )
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "SKIP"

    def test_skip_dxf_lac_con_una_sola_pieza(self, reglas):
        dxf = _dxf_lac("Noche", _piezas_en_fila(1, gap=0))
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "SKIP"

    # --- Caso real EU-18071: 3 piezas Marga separadas 15 mm → FAIL ---
    def test_caso_real_eu18071(self, reglas):
        contornos = [
            _bbox(7.5, 405.5, -603.5, -7.5, layer=L_LACA),     # 398×596
            _bbox(420.5, 818.5, -603.5, -7.5, layer=L_LACA),   # 398×596 — gap 15 vs anterior
            _bbox(833.5, 981.5, -605.5, -7.5, layer=L_LACA),   # 148×598 — gap 15 vs anterior
        ]
        dxf = _dxf_lac("Marga", contornos,
                       nombre="EU-18071_INC_X_MDF LACA MARGA_T1.dxf")
        r = check_nesting_laca([dxf], reglas)
        assert r.resultado == "FAIL"
        assert "15" in r.detalle


# ---------------------------------------------------------------------------
# C-46: Tipos de geometría prohibidos (SPLINE)
# ---------------------------------------------------------------------------

def _dxf_con_tipos(conteos_tipo_por_layer, nombre="EU-22780_X_PLY_LAMINADO_FES_T1.dxf"):
    """DXF mínimo con un mapeo {layer: {tipo: n}} para C-46."""
    layers = set(conteos_tipo_por_layer.keys())
    return DXFDoc(
        nombre=nombre, tablero_num=1, material="PLY", gama="LAM", acabado="Fes",
        layers=layers,
        layers_con_geometria=layers,
        conteos_layer={},
        conteos_tipo_por_layer=conteos_tipo_por_layer,
    )


class TestC46:

    def test_pass_sin_splines(self, reglas):
        dxfs = [_dxf_con_tipos({
            "10_12-CUTEXT-EM5-Z18": {"LWPOLYLINE": 12, "CIRCLE": 6},
            "0_ANOTACIONES": {"TEXT": 50, "MTEXT": 3},
        })]
        r = check_geometria_prohibida(dxfs, reglas)
        assert r.resultado == "PASS"

    def test_fail_con_splines(self, reglas):
        dxfs = [_dxf_con_tipos({
            "0_ANOTACIONES": {"SPLINE": 1584, "POLYLINE": 1},
            "10_12-CUTEXT-EM5-Z18": {"SPLINE": 4, "POLYLINE": 1},
            "4-DES1_IN-EM5-Z3_7_ROBLE": {"CIRCLE": 3},
        })]
        r = check_geometria_prohibida(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "SPLINE" in r.detalle
        # El layer con más splines debe aparecer destacado en el detalle
        assert "0_ANOTACIONES" in r.detalle

    def test_fail_reporta_total_por_tablero(self, reglas):
        # 2 tableros: uno limpio, otro con splines → solo el segundo en el detalle
        dxfs = [
            _dxf_con_tipos(
                {"10_12-CUTEXT-EM5-Z18": {"LWPOLYLINE": 5}},
                nombre="EU-22780_X_PLY_LAMINADO_FES_T1.dxf",
            ),
            _dxf_con_tipos(
                {"7-POCKET-EM5-Z14": {"SPLINE": 10}},
                nombre="EU-22780_X_PLY_LAMINADO_FES_T2.dxf",
            ),
        ]
        r = check_geometria_prohibida(dxfs, reglas)
        assert r.resultado == "FAIL"
        assert "T2.dxf" in r.detalle
        assert "T1.dxf" not in r.detalle

    def test_skip_sin_dxfs(self, reglas):
        r = check_geometria_prohibida([], reglas)
        assert r.resultado == "SKIP"

    def test_skip_sin_lista_prohibidos(self):
        # reglas sin la sección tipos_geometria → SKIP (no PASS silencioso)
        dxfs = [_dxf_con_tipos({"X": {"SPLINE": 1}})]
        r = check_geometria_prohibida(dxfs, {})
        assert r.resultado == "SKIP"

    def test_id_check(self, reglas):
        r = check_geometria_prohibida([], reglas)
        assert r.id == "C-46"
        assert r.grupo == "DXF"
