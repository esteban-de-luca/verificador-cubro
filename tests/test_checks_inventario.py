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
        nombres = [
            "DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
            "EAN LOGISTIC_EU-21822.csv", "EXTRACCION_EU-21822.csv",
        ]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "PASS"

    def test_fail_falta_despiece(self, reglas):
        nombres = [
            "ETIQUETAS_EU-21822.csv", "EAN LOGISTIC_EU-21822.csv",
            "EXTRACCION_EU-21822.csv",
        ]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea

    def test_fail_falta_ean(self, reglas):
        nombres = [
            "DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
            "EXTRACCION_EU-21822.csv",
        ]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "FAIL"
        assert "EAN" in r.detalle

    def test_fail_falta_extraccion(self, reglas):
        nombres = [
            "DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
            "EAN LOGISTIC_EU-21822.csv",
        ]
        r = check_documentos_presentes(nombres, reglas)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "EXTRACCION" in r.detalle

    def test_id_check_correcto(self, reglas):
        r = check_documentos_presentes([], reglas)
        assert r.id == "C-00"
        assert r.grupo == "Inventario"

    def test_pass_con_archivos_extra(self, reglas):
        nombres = [
            "DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
            "EAN LOGISTIC_EU-21822.csv", "EXTRACCION_EU-21822.csv",
            "OT_EU-21822.pdf", "ALBARÁN_EU-21822.pdf",
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

    def test_inc_underscore_equivale_a_guion(self):
        # Caso real: SP-17124-INC en carpeta y OT/DESPIECE, pero EAN usa "_INC"
        # en vez de "-INC". Debe considerarse el mismo ID.
        nombres = [
            "DESPIECE_SP-17124-INC.xlsx",
            "OT_SP-17124-INC.pdf",
            "EAN LOGISTIC_SP-17124_INC.csv",
        ]
        r = check_id_consistente(nombres, "SP-17124-INC")
        assert r.resultado == "PASS"

    def test_ean_logistic_usa_id_base_en_incidencia(self):
        # Caso real SP-20594-INC: el EAN LOGISTIC se nombra con el ID base del
        # producto original (SP-20594, sin -INC) porque la logística/EAN se
        # hereda del proyecto base. Debe considerarse consistente.
        nombres = [
            "DESPIECE_SP-20594-INC_Sandra_Lopez.xlsx",
            "OT_SP-20594-INC_Sandra_Lopez.pdf",
            "EXTRACCION_SP-20594-INC_Sandra_Lopez.csv",
            "ETIQUETAS_SP-20594-INC_Sandra_Lopez.csv",
            "EAN LOGISTIC_SP-20594_Sandra Lopez.csv",
        ]
        r = check_id_consistente(nombres, "SP-20594-INC")
        assert r.resultado == "PASS"

    def test_incidencia_no_tolera_id_base_de_otro_proyecto(self):
        # La tolerancia al ID base aplica solo al base del PROPIO proyecto;
        # el base de otro proyecto (SP-21493) sigue siendo inconsistente.
        nombres = [
            "DESPIECE_SP-20594-INC.xlsx",
            "EAN LOGISTIC_SP-21493.csv",
        ]
        r = check_id_consistente(nombres, "SP-20594-INC")
        assert r.resultado == "FAIL"
        assert "SP-21493" in r.detalle

    def test_proyecto_base_no_tolera_sufijo_inc_extra(self):
        # A la inversa: un proyecto base (sin -INC) no debe aceptar un archivo
        # con sufijo -INC como si fuera el mismo ID.
        nombres = [
            "DESPIECE_SP-20594.xlsx",
            "EAN LOGISTIC_SP-20594-INC.csv",
        ]
        r = check_id_consistente(nombres, "SP-20594")
        assert r.resultado == "FAIL"

    # --- ID numérico de 4 dígitos (proyectos tipo "4302") ---
    def test_pass_id_4_digitos(self):
        nombres = [
            "DESPIECE_4302_baptiste_ducloux.xlsx",
            "ETIQUETAS_4302_baptiste_ducloux.csv",
            "4302_baptiste_ducloux_MDF_LACA_PINO.pdf",
        ]
        r = check_id_consistente(nombres, "4302")
        assert r.resultado == "PASS"

    def test_fail_id_4_digitos_inconsistente(self):
        nombres = [
            "DESPIECE_4302_baptiste.xlsx",
            "ETIQUETAS_5500_otro.csv",
        ]
        r = check_id_consistente(nombres, "4302")
        assert r.resultado == "FAIL"
        assert "5500" in r.detalle

    def test_pass_id_4_digitos_no_confunde_con_5_digitos(self):
        # Una pieza con dimensión '12345' o un ID de 5 dígitos no debe
        # interpretarse como ID de 4 dígitos.
        nombres = [
            "DESPIECE_4302_baptiste.xlsx",
            "EU-12345_otro.pdf",  # ID EU correcto, no debería matchear 1234
        ]
        r = check_id_consistente(nombres, "4302")
        # Solo el EU-12345 sería detectado y diferiría → FAIL
        # (pero el match de 4 dígitos no debería disparar falso positivo)
        assert r.resultado == "FAIL"
        assert "EU-12345" in r.detalle or "EU12345" in r.detalle

    # --- Incidencia real según el contenido interno de los documentos ---
    def test_contenido_revela_incidencia_real(self):
        # Caso real SP-19751: carpeta y nombres de DESPIECE/OT dicen 'INC', pero
        # el contenido de la OT y del EAN declara 'INC2'. El check debe indicar
        # que la incidencia real es INC2 y qué renombrar, sin acusar al EAN.
        from core.modelos import OTData
        from core.extractor_etiquetas_ean import FilaEAN
        nombres = [
            "DESPIECE_SP19751INC_Nora.xlsx",
            "OT_SP19751INC_Nora.pdf",
            "EAN LOGISTIC_SP-19751_INC2_Nora.csv",
        ]
        ot = OTData("SP-19751-INC2", "", "", 0, 0.0, 0)
        ean = [FilaEAN("CUB-SP-19751_INC2-1-1", 1, 1, "T1 / T2 / T3", 3.894)]
        r = check_id_consistente(nombres, "SP-19751-INC", ot=ot, filas_ean=ean)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "SP-19751-INC2" in r.detalle
        assert "realmente" in r.detalle.lower()
        # Señala los archivos mal nombrados (DESPIECE/OT), no el EAN
        assert "DESPIECE_SP19751INC_Nora.xlsx" in r.detalle
        assert "OT_SP19751INC_Nora.pdf" in r.detalle
        assert "EAN LOGISTIC_SP-19751_INC2_Nora.csv" not in r.detalle

    def test_no_directiva_si_contenido_coincide_con_esperado(self):
        # Si el contenido interno coincide con el ID esperado, no se afirma nada
        # y el check pasa (nombres también consistentes).
        from core.modelos import OTData
        nombres = ["DESPIECE_SP-19751-INC.xlsx", "OT_SP-19751-INC.pdf"]
        ot = OTData("SP-19751-INC", "", "", 0, 0.0, 0)
        r = check_id_consistente(nombres, "SP-19751-INC", ot=ot)
        assert r.resultado == "PASS"

    def test_no_directiva_si_contenido_no_es_unanime(self):
        # Si los documentos internos discrepan entre sí (OT=INC2, EXTRACCION=INC),
        # no se afirma una incidencia real; se cae al chequeo por nombre.
        from core.modelos import OTData, ExtraccionData
        nombres = ["DESPIECE_SP-19751-INC.xlsx", "OT_SP-19751-INC.pdf"]
        ot = OTData("SP-19751-INC2", "", "", 0, 0.0, 0)
        extr = ExtraccionData(id_proyecto="SP-19751-INC")
        r = check_id_consistente(nombres, "SP-19751-INC", ot=ot, extraccion=extr)
        # Nombres coinciden con lo esperado → PASS (sin directiva)
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

    def test_skip_archivo_desconocido(self, reglas):
        # Archivos no reconocidos → SKIP (informativo, no alerta)
        nombres = ["DESPIECE_EU-21822.xlsx", "ETIQUETAS_EU-21822.csv",
                   "EAN LOGISTIC_EU-21822.csv", "archivo_raro_sin_patron.xlsx"]
        r = check_nomenclatura(nombres, reglas)
        assert r.resultado == "SKIP"
        assert not r.bloquea
        assert "archivo_raro_sin_patron.xlsx" in r.detalle

    def test_no_bloquea(self, reglas):
        r = check_nomenclatura(["random.docx"], reglas)
        assert not r.bloquea

    def test_pass_dossier_variantes(self, reglas):
        # Cualquier nombre que contenga "DOSSIER" se acepta — cubre todos los
        # idiomas y prefijos: CUBRO_Technical_Project_Dossier_*, CUBRO_Dossier_*,
        # Dossier_técnico_de_proyecto_* (sin prefijo CUBRO_), etc.
        nombres = [
            "CUBRO_Technical_Project_Dossier_EU-21822.pdf",
            "CUBRO_Dossier_de_proyecto_EU-21822.pdf",
            "CUBRO_Dossier_technique_du_projet_EU-21822.pdf",
            "Dossier_técnico_de_proyecto_SP-22429_Paula_Boixet_v2.pdf",
            "DOSSIER_EU-21822.pdf",
        ]
        r = check_nomenclatura(nombres, reglas)
        assert r.resultado == "PASS"

    def test_pass_planos_y_alzados(self, reglas):
        # Planos / Alzados (singular y plural, mayúsculas/minúsculas)
        nombres = [
            "Planos_proyecto_SP-22429.pdf",
            "PLANOS_EU-21822.pdf",
            "Alzados_proyecto_SP-22429.pdf",
            "Plano_distribucion.pdf",
            "Alzado_cocina.pdf",
        ]
        r = check_nomenclatura(nombres, reglas)
        assert r.resultado == "PASS"


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

    def test_pass_proyecto_integramente_de_retal(self):
        """C1-23637 real: la OT declara 0 tableros por material (todas las
        piezas se cortan de retal) y todos los DXFs llevan capa RETAL
        UTILIZADO → 0 == 0, no debe fallar."""
        dxfs = [
            DXFDoc("C123637_X_PLY_LAM_Agave_T1.dxf", 1, "PLY", "LAM", "Agave",
                   layers={"CUTEXT", "RETAL UTILIZADO"}),
            DXFDoc("C123637_X_PLY_LAM_Blanco_T1.dxf", 1, "PLY", "LAM", "Blanco",
                   layers={"CUTEXT", "RETAL UTILIZADO"}),
        ]
        ot = _ot(tableros={"PLY_LAM_Agave": 0, "PLY_LAM_Blanco": 0},
                 num_tableros_total=0)
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

    def test_skip_proyecto_de_retal(self):
        """SP-20742-INC real: OT declara 0 tableros (la pieza se corta de
        retal), DESPIECE tiene 1 combinación material, pero no debe existir
        ningún PDF de nesting → SKIP."""
        piezas = [_pieza(material="MDF", gama="LAC", acabado="Crema")]
        nombres = ["DESPIECE_SP-20742-INC.xlsx", "OT_SP-20742-INC.pdf"]
        ot = _ot(tableros={}, num_tableros_total=0)
        r = check_pdfs_nesting_vs_materiales(nombres, piezas, ot)
        assert r.resultado == "SKIP"
        assert "retal" in r.detalle.lower()

    def test_pass_con_ot_normal(self):
        """OT con tableros >0 sigue exigiendo PDF por combinación."""
        piezas = [_pieza(material="PLY", gama="LAM", acabado="Pale")]
        nombres = ["EU21822_Sabine_PLY_LAM_PALE.pdf"]
        ot = _ot()  # num_tableros_total = 2
        r = check_pdfs_nesting_vs_materiales(nombres, piezas, ot)
        assert r.resultado == "PASS"

    def test_fail_con_ot_normal_falta_pdf(self):
        """OT con tableros >0 y falta el PDF de nesting → FAIL (no es retal)."""
        piezas = [_pieza(material="MDF", gama="LAC", acabado="Crema")]
        nombres = ["DESPIECE_SP-20742-INC.xlsx"]
        ot = _ot(tableros={"MDF_LAC_Crema": 1}, num_tableros_total=1)
        r = check_pdfs_nesting_vs_materiales(nombres, piezas, ot)
        assert r.resultado == "FAIL"

    # --- Proyectos con ID numérico de 4 dígitos (caso 4302) ---
    def test_pass_id_4_digitos(self):
        """Proyecto 4302 con un PDF nesting MDF → PASS."""
        piezas = [_pieza(material="MDF", gama="LAC", acabado="Pino")]
        nombres = [
            "DESPIECE_4302_baptiste_ducloux.xlsx",
            "4302_baptiste_ducloux_MDF_LACA_PINO.pdf",
        ]
        r = check_pdfs_nesting_vs_materiales(nombres, piezas)
        assert r.resultado == "PASS"

    def test_despiece_pdf_no_se_cuenta_como_nesting(self):
        """Un DESPIECE no debe contar como nesting aunque contenga MDF en el
        nombre y un ID de 4 dígitos."""
        piezas = [_pieza(material="MDF", gama="LAC", acabado="Pino")]
        nombres = [
            "DESPIECE_4302_baptiste_MDF_LACA_PINO.pdf",
            "4302_baptiste_MDF_LACA_PINO.pdf",
        ]
        # Solo el segundo PDF (sin prefijo DESPIECE) debe contar
        r = check_pdfs_nesting_vs_materiales(nombres, piezas)
        assert r.resultado == "PASS"
