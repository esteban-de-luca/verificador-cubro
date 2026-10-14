"""Capas de corte del MDF (Esteban y Carpintek, 14/10/2026): el MDF que se corta de tablero (Wood y
Laca estándar) va en 10_12-CUTEXT-MDF-EM5-Z18 y sus rodapiés en 10_12-CORTAR_RODAPIE_MDF, obligatorio
desde la semana 45 (Ventas) y el 14/10/2026 (Tickets y PAX); antes valen las dos."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.extractor_ot import _RE_FECHA_FICHERO  # noqa: E402
from core.modelos import DXFDoc, OTData  # noqa: E402
from core.reglas_loader import cargar_reglas  # noqa: E402
from checks.checks_dxf import capas_mdf_obligatorias, check_corte_perimetral, check_nesting_laca  # noqa: E402

CUTEXT = "10_12-CUTEXT-EM5-Z18"
CUTEXT_MDF = "10_12-CUTEXT-MDF-EM5-Z18"
RODAPIE = "10_12-CORTAR_RODAPIE"
RODAPIE_MDF = "10_12-CORTAR_RODAPIE_MDF"
LACA = "10_12-CONTORNO LACA"


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


def _ot(id_proyecto="EU-1", entrada="", fecha=""):
    return OTData(id_proyecto=id_proyecto, cliente="", semana="", num_piezas=0, peso_total_kg=0, num_tiradores=0,
                  fecha_entrada=entrada, fecha_fichero=fecha)


def _dxf(material, gama, acabado, layers):
    return DXFDoc(nombre=f"X_{material}_{gama}_{acabado}_T1.dxf", tablero_num=1, material=material, gama=gama,
                  acabado=acabado, layers=set(layers))


VENTAS_S45 = _ot("EU-1", entrada="02/11/2026", fecha="20/10/2026")
VENTAS_S44 = _ot("EU-1", entrada="26/10/2026", fecha="20/10/2026")
INC_HOY = _ot("EU-1-INC", fecha="14/10/2026")
PAX_AYER = _ot("5191", fecha="13/10/2026")


def test_desde_cuando(reglas):
    assert capas_mdf_obligatorias(VENTAS_S45, reglas) is True
    assert capas_mdf_obligatorias(VENTAS_S44, reglas) is False
    assert capas_mdf_obligatorias(INC_HOY, reglas) is True
    assert capas_mdf_obligatorias(_ot("EU-1-INC2", fecha="15/10/2026"), reglas) is True
    assert capas_mdf_obligatorias(PAX_AYER, reglas) is False
    assert capas_mdf_obligatorias(_ot("5191", fecha="14/10/2026"), reglas) is True
    # Sin datos con los que decidir (OT ilegible, complemento sin semana…): valen las dos.
    assert capas_mdf_obligatorias(None, reglas) is None
    assert capas_mdf_obligatorias(_ot("C1-1", fecha="20/10/2026"), reglas) is None
    assert capas_mdf_obligatorias(_ot("EU-1-INC"), reglas) is None


def test_la_fecha_del_fichero_se_lee_de_la_ot():
    texto = ("Taller Carpintek Fecha máxima de salida\nNº de OT 4999\nResponsable Esteban 30/10/2026\n"
             "Fecha 13/10/2026\nFecha entrada a corte: 19/10/2026")
    assert _RE_FECHA_FICHERO.search(texto).group(1) == "13/10/2026"
    assert _RE_FECHA_FICHERO.search("Fecha entrada a corte: 19/10/2026") is None


@pytest.mark.parametrize("ot", [VENTAS_S45, INC_HOY])
def test_desde_el_arranque_el_mdf_va_en_sus_capas(reglas, ot):
    ok = [_dxf("MDF", "WOO", "Roble", {CUTEXT_MDF}), _dxf("MDF", "WOO", "Roble", {RODAPIE_MDF}),
          _dxf("MDF", "LAC", "Roto", {CUTEXT_MDF}), _dxf("PLY", "LAM", "Pale", {CUTEXT, RODAPIE})]
    assert check_corte_perimetral(ok, reglas, ot).resultado == "PASS"
    r = check_corte_perimetral([_dxf("MDF", "WOO", "Roble", {CUTEXT})], reglas, ot)
    assert r.resultado == "FAIL" and CUTEXT_MDF in r.detalle
    # Los pasantes de hornacina en la capa de siempre también cuentan: ninguna geometría en CUTEXT.
    r = check_corte_perimetral([_dxf("MDF", "LAC", "Roto", {CUTEXT_MDF, CUTEXT})], reglas, ot)
    assert r.resultado == "FAIL"


@pytest.mark.parametrize("ot", [VENTAS_S44, PAX_AYER, None])
def test_antes_del_arranque_valen_las_dos(reglas, ot):
    dxfs = [_dxf("MDF", "WOO", "Roble", {CUTEXT}), _dxf("MDF", "WOO", "Nogal", {CUTEXT_MDF}),
            _dxf("MDF", "LAC", "Roto", {CUTEXT}), _dxf("MDF", "WOO", "Roble", {RODAPIE_MDF})]
    assert check_corte_perimetral(dxfs, reglas, ot).resultado == "PASS"
    assert check_corte_perimetral([_dxf("MDF", "WOO", "Roble", {"0_ANOTACIONES"})], reglas, ot).resultado == "FAIL"


def test_el_contrachapado_nunca_va_en_las_capas_del_mdf(reglas):
    for ot in (VENTAS_S44, VENTAS_S45):
        r = check_corte_perimetral([_dxf("PLY", "LAM", "Pale", {CUTEXT_MDF})], reglas, ot)
        assert r.resultado == "FAIL" and "contrachapado" in r.detalle


def test_la_laca_de_alvic_sigue_en_contorno_laca(reglas):
    # Con pasantes de hornacina en la capa de MDF: no molestan.
    dxfs = [_dxf("MDF", "LAC", "Agave", {LACA, CUTEXT_MDF}), _dxf("MDF", "LAC", "Roto", {LACA})]
    assert check_corte_perimetral(dxfs, reglas, VENTAS_S45).resultado == "PASS"
    assert check_corte_perimetral([_dxf("MDF", "LAC", "Agave", {CUTEXT_MDF})], reglas, VENTAS_S45).resultado == "FAIL"


def test_c45_lee_la_laca_de_tablero_en_la_capa_de_mdf(reglas):
    def fila(gap):
        return [{"layer": CUTEXT_MDF, "xmin": x, "xmax": x + 398, "ymin": 0, "ymax": 596}
                for x in (0, 398 + gap, 2 * (398 + gap))]

    dxf = DXFDoc(nombre="X_MDF_LACA_ROTO_T1.dxf", tablero_num=1, material="MDF", gama="LAC", acabado="Roto",
                 piezas_contorno=fila(15))
    assert check_nesting_laca([dxf], reglas).resultado == "PASS"
    dxf.piezas_contorno = fila(5)
    assert check_nesting_laca([dxf], reglas).resultado == "FAIL"
