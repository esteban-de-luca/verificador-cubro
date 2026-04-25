"""tests/test_checks_inventario.py — Tests de C-00 a C-04."""

from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import Pieza, DXFDoc, OTData
from core.reglas_loader import cargar_reglas
from checks.checks_inventario import (
    check_documentos_presentes,
    check_id_consistente,
    check_nomenclatura,
    check_num_dxf_vs_ot,
    check_pdfs_nesting_vs_materiales,
)


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


def _pieza(id="M1-P1", material="PLY", gama="LAM", acabado="Pale"):
    return Pieza(id, 400, 798, material, gama, acabado, "P")


def _dxf(nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf", material="PLY", gama="LAM", acabado="Pale", num=1):
    return DXFDoc(nombre, num, material, gama, acabado, layers={"CONTROL", "0_ANOTACIONES"})


_UNSET = object()

def _ot(tableros=None, n_piezas=1, num_tableros_total=_UNSET, materiales_sin_cantidad=None):
    if tableros is None:
        tableros = {"PLY_LAM_Pale": 2}
    if num_tableros_total is _UNSET:
        num_tableros_total = sum(tableros.values()) if tableros else None
    return OTData("EU-21822", "Test", "Semana 18", n_piezas, 50.0, 0,
                  tableros=tableros,
                  materiales_sin_cantidad=materiales_sin_cantidad or [],
                  num_tableros_total=num_tableros_total)


# ---------------------------------------------------------------------------
# C-00
# ---------------------------------------------------------------------------

class TestC00:

    def test_pass_con_todos_presentes(self, reglas):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv", "EAN LOGISTIC_EU-21822.csv"]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "PASS"

    def test_fail_falta_despiece(self, reglas):
        nombres = ["ETIQUETAS_EU-21822.csv", "EAN LOGISTIC_EU-21822.csv"]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_fail_falta_ean(self, reglas):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv"]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "FAIL"
        assert "EAN" in r.detalle

    def test_id_check_correcto(self, reglas):
        r = check_documentos_presentes([], reglas)
        assert r.id == "C-00"
        assert r.grupo == "Inventario"

    def test_pass_con_archivos_extra(self, reglas):
        nombres = [
            "DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
            "EAN LOGISTIC_EU-21822.csv", "OT_EU-21822.pdf", "ALBARÁN_EU-21822.pdf",
        ]
        assert check_documentos_presentes(nombres, reglas).resultado == "PASS"


# ---------------------------------------------------------------------------
# C-01
# ---------------------------------------------------------------------------

class TestC01:

    def test_pass_todos_mismo_id(self):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv", "OT_EU21822.pdf"]
        r = check_id_consistente(nombres, "EU-21822")
        assert r.resultado == "PASS"

    def test_fail_id_diferente_en_archivo(self):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_SP-21493.csv"]
        r = check_id_consistente(nombres, "EU-21822")
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_si_sin_archivos(self):
        r = check_id_consistente([], "EU-21822")
        assert r.resultado == "PASS"  # sin archivos → sin errores

    def test_id_con_inc_se_tolera(self):
        nombres = ["DESPIECE_EU-21822-INC.xlsx"]
        r = check_id_consistente(nombres, "EU-21822-INC")
        assert r.resultado == "PASS"


# ---------------------------------------------------------------------------
# C-02
# ---------------------------------------------------------------------------

class TestC02:

    def test_pass_todos_reconocidos(self, reglas):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
                   "EAN LOGISTIC_EU-21822.csv", "OT_EU-21822.pdf"]
        r = check_nomenclatura(nombres, reglas)
        assert r.resultado == "PASS"

    def test_warn_archivo_desconocido(self, reglas):
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
                   "EAN LOGISTIC_EU-21822.csv", "archivo_raro_sin_patron.xlsx"]
        r = check_nomenclatura(nombres, reglas)
        assert r.resultado == "WARN"
        assert not r.bloquea

    def test_no_bloquea(self, reglas):
        r = check_nomenclatura(["random.docx"], reglas)
        assert not r.bloquea


# ---------------------------------------------------------------------------
# C-03
# ---------------------------------------------------------------------------

class TestC03:

    def test_pass_dxf_coincide_con_ot(self):
        dxfs = [_dxf(num=1), _dxf(num=2)]
        ot = _ot(tableros={"PLY_LAM_Pale": 2})
        r = check_num_dxf_vs_ot(dxfs, ot)
        assert r.resultado == "PASS"
        assert r.bloquea

    def test_fail_mas_dxf_que_ot(self):
        dxfs = [_dxf(num=1), _dxf(num=2), _dxf(num=3)]
        ot = _ot(tableros={"PLY_LAM_Pale": 2})
        r = check_num_dxf_vs_ot(dxfs, ot)
        assert r.resultado == "FAIL"
        assert "3" in r.detalle and "2" in r.detalle

    def test_fail_menos_dxf_que_ot(self):
        dxfs = [_dxf(num=1)]
        ot = _ot(tableros={"PLY_LAM_Pale": 2, "MDF_LAC_Blanco": 1})
        r = check_num_dxf_vs_ot(dxfs, ot)
        assert r.resultado == "FAIL"

    def test_fail_ot_sin_tableros(self):
        # OT vacía (sin cabecera ni tabla) → FAIL por dato obligatorio faltante
        r = check_num_dxf_vs_ot([_dxf()], _ot(tableros={}))
        assert r.resultado == "FAIL"
        assert "Cantidad de tableros" in r.detalle

    def test_fail_material_sin_cantidad(self):
        ot = _ot(tableros={}, num_tableros_total=3,
                 materiales_sin_cantidad=["MDF_WOO_Roble"])
        r = check_num_dxf_vs_ot([_dxf()], ot)
        assert r.resultado == "FAIL"
        assert "MDF_WOO_Roble" in r.detalle

    def test_fail_falta_total_cabecera(self):
        ot = _ot(tableros={"PLY_LAM_Pale": 2}, num_tableros_total=None)
        r = check_num_dxf_vs_ot([_dxf(num=1), _dxf(num=2)], ot)
        assert r.resultado == "FAIL"
        assert "cabecera" in r.detalle.lower()

    def test_pass_varios_materiales(self):
        dxfs = [_dxf(num=i) for i in range(1, 6)]
        ot = _ot(tableros={"PLY_LAM_Pale": 3, "MDF_LAC_Blanco": 2})
        assert check_num_dxf_vs_ot(dxfs, ot).resultado == "PASS"

    def test_pass_dxf_de_retal_no_cuenta(self):
        # OT declara 5 tableros; hay 6 DXFs pero uno se corta de retal → no cuenta
        dxfs = [_dxf(num=i) for i in range(1, 6)]
        dxf_retal = DXFDoc("EU-22467_X_PLY_LAM_Pale_T2.dxf", 2, "PLY", "LAM", "Pale",
                           layers={"CONTROL", "RETAL UTILIZADO"})
        dxfs.append(dxf_retal)
        ot = _ot(tableros={"PLY_LAM_Pale": 3, "MDF_LAC_Blanco": 2})
        assert check_num_dxf_vs_ot(dxfs, ot).resultado == "PASS"


# ---------------------------------------------------------------------------
# C-04
# ---------------------------------------------------------------------------

class TestC04:

    def test_pass_pdf_por_combo(self):
        piezas = [_pieza(material="PLY", gama="LAM", acabado="Pale")]
        nombres = ["DESPIECE_EU-21822.xlsx", "EU21822_Sabine_Jennes_PLY_LAM_PALE.pdf"]
        r = check_pdfs_nesting_vs_materiales(nombres, piezas)
        assert r.resultado == "PASS"

    def test_fail_falta_pdf_para_combo(self):
        piezas = [
            _pieza(material="PLY", gama="LAM", acabado="Pale"),
            Pieza("M2-P1", 400, 798, "MDF", "LAC", "Blanco", "P"),
        ]
        # Solo hay PDF para PLY, falta el de MDF
        nombres = ["EU21822_Sabine_PLY_LAM_PALE.pdf"]
        r = check_pdfs_nesting_vs_materiales(nombres, piezas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_skip_sin_piezas(self):
        r = check_pdfs_nesting_vs_materiales([], [])
        assert r.resultado == "SKIP"

    def test_pass_sin_pdfs_si_no_hay_piezas(self):
        r = check_pdfs_nesting_vs_materiales(["OT_EU-21822.pdf"], [])
        assert r.resultado == "SKIP"
