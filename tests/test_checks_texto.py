"""tests/test_checks_texto.py — Tests de C-60 a C-63."""

from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import DXFDoc, OTData, Pieza
from core.reglas_loader import cargar_reglas_cnc
from checks.checks_texto import (
    check_retales_en_ot,
    check_sin_mecanizar_en_ot,
    check_observaciones_reconocidas,
    check_observaciones_no_reconocidas,
)


@pytest.fixture(scope="session")
def reglas_cnc():
    return cargar_reglas_cnc(ROOT / "reglas_cnc.yaml")


def _ot(obs_cnc=None, obs_prod=None):
    ot = OTData("EU-21822", "Test", "Semana 18", 10, 50.0, 0)
    ot.observaciones_cnc = obs_cnc or []
    ot.observaciones_produccion = obs_prod or []
    return ot


def _dxf(layers=None):
    return DXFDoc(
        nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf",
        tablero_num=1, material="PLY", gama="LAM", acabado="Pale",
        layers=layers or {"CONTROL", "0_ANOTACIONES"},
    )


def _pieza(id="M1-P1", tipologia="P", mecanizado="cazta."):
    p = Pieza(id, 400, 798, "PLY", "LAM", "Pale", tipologia)
    p.mecanizado = mecanizado
    return p


# ---------------------------------------------------------------------------
# C-60
# ---------------------------------------------------------------------------

class TestC60:

    def test_pass_sin_layer_retal(self, reglas_cnc):
        dxfs = [_dxf(layers={"CONTROL", "0_ANOTACIONES"})]
        ot = _ot()
        r = check_retales_en_ot(ot, dxfs, reglas_cnc)
        assert r.resultado == "PASS"

    def test_fail_layer_retal_sin_mencion_ot(self, reglas_cnc):
        dxfs = [_dxf(layers={"CONTROL", "RETAL UTILIZADO"})]
        ot = _ot(obs_cnc=[])
        r = check_retales_en_ot(ot, dxfs, reglas_cnc)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_pass_layer_retal_con_mencion_ot(self, reglas_cnc):
        dxfs = [_dxf(layers={"CONTROL", "RETAL UTILIZADO"})]
        ot = _ot(obs_cnc=["retal utilizado de PLY-LAM-Pale"])
        r = check_retales_en_ot(ot, dxfs, reglas_cnc)
        assert r.resultado == "PASS"

    def test_id_check(self, reglas_cnc):
        r = check_retales_en_ot(_ot(), [], reglas_cnc)
        assert r.id == "C-60"
        assert r.grupo == "Texto CNC"


# ---------------------------------------------------------------------------
# C-61
# ---------------------------------------------------------------------------

class TestC61:

    def test_pass_puertas_con_mecanizado(self, reglas_cnc):
        piezas = [_pieza(mecanizado="cazta.")]
        ot = _ot()
        r = check_sin_mecanizar_en_ot(piezas, ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_skip_puerta_sin_mec_sin_mencion(self, reglas_cnc):
        # Si hay puerta sin mecanizar y la OT no lo menciona → SKIP (revisar OT)
        piezas = [_pieza(mecanizado="   ")]
        ot = _ot(obs_cnc=[])
        r = check_sin_mecanizar_en_ot(piezas, ot, reglas_cnc)
        assert r.resultado == "SKIP"
        assert not r.bloquea

    def test_pass_puerta_sin_mec_con_mencion(self, reglas_cnc):
        piezas = [_pieza(mecanizado="")]
        ot = _ot(obs_cnc=["piezas sin mecanizar"])
        r = check_sin_mecanizar_en_ot(piezas, ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_pass_sin_puertas(self, reglas_cnc):
        piezas = [_pieza(tipologia="E", mecanizado="")]
        ot = _ot()
        r = check_sin_mecanizar_en_ot(piezas, ot, reglas_cnc)
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-62
# ---------------------------------------------------------------------------

class TestC62:

    def test_pass_sin_observaciones(self, reglas_cnc):
        ot = _ot(obs_cnc=[])
        r = check_observaciones_reconocidas(ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_pass_observacion_reconocida(self, reglas_cnc):
        ot = _ot(obs_cnc=["retal de PLY-LAM-Pale"])
        r = check_observaciones_reconocidas(ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_skip_observacion_no_reconocida(self, reglas_cnc):
        ot = _ot(obs_cnc=["texto completamente desconocido xyzabc"])
        r = check_observaciones_reconocidas(ot, reglas_cnc)
        assert r.resultado == "SKIP"
        assert not r.bloquea

    def test_id_check(self, reglas_cnc):
        r = check_observaciones_reconocidas(_ot(), reglas_cnc)
        assert r.id == "C-62"


# ---------------------------------------------------------------------------
# C-63
# ---------------------------------------------------------------------------

class TestC63:

    def test_pass_sin_observaciones(self, reglas_cnc):
        ot = _ot(obs_cnc=[])
        r = check_observaciones_no_reconocidas(ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_pass_todas_reconocidas(self, reglas_cnc):
        ot = _ot(obs_cnc=["retal de PLY-LAM-Pale"])
        r = check_observaciones_no_reconocidas(ot, reglas_cnc)
        assert r.resultado == "PASS"

    def test_skip_hay_no_reconocidas(self, reglas_cnc):
        ot = _ot(obs_cnc=["texto xyzabc completamente desconocido"])
        r = check_observaciones_no_reconocidas(ot, reglas_cnc)
        assert r.resultado == "SKIP"
        assert not r.bloquea
        assert "xyzabc" in r.detalle

    def test_nunca_fail(self, reglas_cnc):
        ot = _ot(obs_cnc=["obs desconocida 1", "obs desconocida 2"])
        r = check_observaciones_no_reconocidas(ot, reglas_cnc)
        assert r.resultado != "FAIL"

    def test_id_check(self, reglas_cnc):
        r = check_observaciones_no_reconocidas(_ot(), reglas_cnc)
        assert r.id == "C-63"
