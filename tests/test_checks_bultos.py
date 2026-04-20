"""tests/test_checks_bultos.py — Tests de C-50 a C-56."""

from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import Pieza, OTData
from core.reglas_loader import cargar_reglas
from core.extractor_etiquetas_ean import FilaEAN
from checks.checks_bultos import (
    check_num_bultos,
    check_piezas_asignadas,
    check_piezas_sin_duplicados,
    check_formato_id_bulto,
    check_peso_total,
    check_envio_estructura,
    check_codigo_destino_caja,
)


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


def _fila(id_pieza="M1-P1", id_bulto="CUB-EU-21822-1-3", peso_kg=5.0):
    return FilaEAN(id_bulto=id_bulto, numero_bulto=1, total_bultos=3,
                   id_pieza=id_pieza, peso_kg=peso_kg)


def _pieza(id="M1-P1", ancho=400, alto=798):
    return Pieza(id, ancho, alto, "PLY", "LAM", "Pale", "P")


def _ot(peso_total_kg=50.0, num_tiradores=0, obs_cnc=None, obs_prod=None):
    ot = OTData("EU-21822", "Test", "Semana 18", 10, peso_total_kg, num_tiradores)
    ot.observaciones_cnc = obs_cnc or []
    ot.observaciones_produccion = obs_prod or []
    return ot


# ---------------------------------------------------------------------------
# C-50
# ---------------------------------------------------------------------------

class TestC50:

    def test_pass_coincide(self):
        filas = [_fila(id_bulto="CUB-EU-21822-1-2"), _fila(id_pieza="M1-P2", id_bulto="CUB-EU-21822-2-2")]
        r = check_num_bultos(filas, n_bultos_pdf=2)
        assert r.resultado == "PASS"

    def test_fail_no_coincide(self):
        filas = [_fila(id_bulto="CUB-EU-21822-1-2"), _fila(id_pieza="M1-P2", id_bulto="CUB-EU-21822-2-2")]
        r = check_num_bultos(filas, n_bultos_pdf=3)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_pdf(self):
        filas = [_fila()]
        r = check_num_bultos(filas, n_bultos_pdf=None)
        assert r.resultado == "SKIP"

    def test_id_check(self):
        r = check_num_bultos([], n_bultos_pdf=None)
        assert r.id == "C-50"
        assert r.grupo == "Logistica"


# ---------------------------------------------------------------------------
# C-51
# ---------------------------------------------------------------------------

class TestC51:

    def test_pass_todas_asignadas(self):
        piezas = [_pieza("M1-P1"), _pieza("M1-P2")]
        filas = [_fila("M1-P1"), _fila("M1-P2")]
        r = check_piezas_asignadas(piezas, filas)
        assert r.resultado == "PASS"

    def test_fail_pieza_sin_bulto(self):
        piezas = [_pieza("M1-P1"), _pieza("M1-P2")]
        filas = [_fila("M1-P1")]
        r = check_piezas_asignadas(piezas, filas)
        assert r.resultado == "FAIL"
        assert "M1-P2" in r.detalle
        assert r.bloquea

    def test_pass_sin_piezas(self):
        r = check_piezas_asignadas([], [])
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-52
# ---------------------------------------------------------------------------

class TestC52:

    def test_pass_sin_duplicados(self):
        filas = [_fila("M1-P1", "CUB-EU-21822-1-2"), _fila("M1-P2", "CUB-EU-21822-2-2")]
        r = check_piezas_sin_duplicados(filas)
        assert r.resultado == "PASS"

    def test_fail_pieza_en_dos_bultos(self):
        filas = [
            _fila("M1-P1", "CUB-EU-21822-1-2"),
            _fila("M1-P1", "CUB-EU-21822-2-2"),
        ]
        r = check_piezas_sin_duplicados(filas)
        assert r.resultado == "FAIL"
        assert "M1-P1" in r.detalle

    def test_pass_lista_vacia(self):
        r = check_piezas_sin_duplicados([])
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-53
# ---------------------------------------------------------------------------

class TestC53:

    def test_pass_formato_correcto(self):
        filas = [_fila(id_bulto="CUB-EU-21822-1-3")]
        r = check_formato_id_bulto(filas, "EU-21822")
        assert r.resultado == "PASS"

    def test_pass_formato_sin_guion_en_id(self):
        filas = [_fila(id_bulto="CUB-EU21822-1-3")]
        r = check_formato_id_bulto(filas, "EU-21822")
        assert r.resultado == "PASS"

    def test_fail_formato_invalido(self):
        filas = [_fila(id_bulto="BULTO-1")]
        r = check_formato_id_bulto(filas, "EU-21822")
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_fail_id_proyecto_distinto(self):
        filas = [_fila(id_bulto="CUB-SP-21493-1-2")]
        r = check_formato_id_bulto(filas, "EU-21822")
        assert r.resultado == "FAIL"

    def test_pass_inc_en_id(self):
        filas = [_fila(id_bulto="CUB-EU-21822-INC-1-2")]
        r = check_formato_id_bulto(filas, "EU-21822-INC")
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-54
# ---------------------------------------------------------------------------

class TestC54:

    def test_pass_dentro_tolerancia(self, reglas):
        filas = [_fila(peso_kg=50.0)]
        ot = _ot(peso_total_kg=50.0)
        r = check_peso_total(filas, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_fuera_tolerancia(self, reglas):
        filas = [_fila(peso_kg=60.0)]
        ot = _ot(peso_total_kg=50.0)
        r = check_peso_total(filas, ot, reglas)
        assert r.resultado == "FAIL"
        assert not r.bloquea

    def test_skip_ot_sin_peso(self, reglas):
        filas = [_fila(peso_kg=5.0)]
        ot = _ot(peso_total_kg=0)
        r = check_peso_total(filas, ot, reglas)
        assert r.resultado == "SKIP"

    def test_skip_ean_sin_pesos(self, reglas):
        filas = [_fila(peso_kg=0.0)]
        ot = _ot(peso_total_kg=50.0)
        r = check_peso_total(filas, ot, reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-55
# ---------------------------------------------------------------------------

class TestC55:

    def test_pass_piezas_pequenas(self, reglas):
        piezas = [_pieza(ancho=400, alto=700)]
        ot = _ot()
        r = check_envio_estructura(piezas, ot, reglas)
        assert r.resultado == "PASS"

    def test_fail_pieza_grande_sin_estructura(self, reglas):
        piezas = [_pieza(ancho=400, alto=900)]  # 900 > 780 umbral
        ot = _ot()  # sin mención de estructura
        r = check_envio_estructura(piezas, ot, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_pass_pieza_grande_con_estructura_declarada(self, reglas):
        piezas = [_pieza(ancho=400, alto=900)]
        ot = _ot(obs_cnc=["Envío en estructura"])
        r = check_envio_estructura(piezas, ot, reglas)
        assert r.resultado == "PASS"

    def test_skip_sin_piezas(self, reglas):
        r = check_envio_estructura([], _ot(), reglas)
        assert r.resultado == "SKIP"


# ---------------------------------------------------------------------------
# C-56
# ---------------------------------------------------------------------------

class TestC56:

    def test_pass_codigo_correcto(self):
        r = check_codigo_destino_caja("CUB-EU-21822", "EU-21822")
        assert r.resultado == "PASS"

    def test_fail_codigo_incorrecto(self):
        r = check_codigo_destino_caja("CUB-SP-21493", "EU-21822")
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_pdf(self):
        r = check_codigo_destino_caja(None, "EU-21822")
        assert r.resultado == "SKIP"

    def test_pass_case_insensitive(self):
        r = check_codigo_destino_caja("cub-eu-21822", "EU-21822")
        assert r.resultado == "PASS"
