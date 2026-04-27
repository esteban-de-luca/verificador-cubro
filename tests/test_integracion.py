"""
tests/test_integracion.py — Tests de integración del pipeline completo.

Verifican que engine._clasificar, _extraer y _ejecutar_checks producen
resultados correctos usando fixtures en memoria (sin Drive real).
"""

from __future__ import annotations
import io
import sys
from pathlib import Path

import ezdxf
import openpyxl
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.reglas_loader import cargar_reglas, cargar_reglas_cnc
from core.modelos import InformeFinal
from engine import (
    DatosProyecto,
    _clasificar,
    _extraer,
    _ejecutar_checks,
)


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


@pytest.fixture(scope="session")
def reglas_cnc():
    return cargar_reglas_cnc(ROOT / "reglas_cnc.yaml")


# ---------------------------------------------------------------------------
# Generadores de fixtures en memoria
# ---------------------------------------------------------------------------

def _xlsx_despiece(piezas: list[dict]) -> io.BytesIO:
    """
    Crea un DESPIECE XLSX mínimo con las piezas dadas.
    Cada dict: {id, ancho, alto, material, gama, acabado, mecanizado, tirador?, apertura?}
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["ID", "Ancho", "Alto", "Material", "Gama", "Acabado",
               "Mecanizado", "Tirador", "Posicion Tirador", "Color Tirador", "Apertura"])
    for p in piezas:
        ws.append([
            p["id"], p["ancho"], p["alto"],
            p.get("material", "PLY"), p.get("gama", "LAM"), p.get("acabado", "Pale"),
            p.get("mecanizado", ""), p.get("tirador", ""),
            p.get("posicion_tirador", ""), p.get("color_tirador", ""),
            p.get("apertura", ""),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _csv_etiquetas(piezas: list[dict]) -> io.BytesIO:
    """CSV ETIQUETAS con columnas id;ancho;alto;material;gama;acabado."""
    lines = ["id;ancho;alto;material;gama;acabado"]
    for p in piezas:
        lines.append(
            f"{p['id']};{p['ancho']};{p['alto']};"
            f"{p.get('material','PLY')};{p.get('gama','LAM')};{p.get('acabado','Pale')}"
        )
    return io.BytesIO("\n".join(lines).encode("utf-8"))


def _csv_ean(piezas: list[dict], id_proyecto: str = "EU-99999") -> io.BytesIO:
    """CSV EAN LOGISTIC: todas las piezas en un único bulto."""
    n = len(piezas)
    bulto_id = f"CUB-{id_proyecto}-1-1"
    lines = ["id bulto;id pieza;peso"]
    for p in piezas:
        lines.append(f"{bulto_id};{p['id']};5.0")
    return io.BytesIO("\n".join(lines).encode("utf-8"))


def _dxf_valido(
    nombre: str = "EU99999_Test_PLY_LAMINADO_PALE_T1.dxf",
    layers_extra: set[str] | None = None,
) -> io.BytesIO:
    """DXF mínimo válido con layers CONTROL y 0_ANOTACIONES."""
    doc = ezdxf.new()
    msp = doc.modelspace()

    capas_base = {"CONTROL", "0_ANOTACIONES", "13-BISELAR-EM5-Z0_8",
                  "10_12-CUTEXT-EM5-Z18"}
    if layers_extra:
        capas_base |= layers_extra

    for capa in capas_base:
        doc.layers.add(capa)
        msp.add_line((0, 0), (100, 100), dxfattribs={"layer": capa})

    sio = io.StringIO()
    doc.write(sio)
    buf = io.BytesIO(sio.getvalue().encode("cp1252", errors="replace"))
    buf.seek(0)
    return buf


# Piezas de referencia
_PIEZAS_VALIDAS = [
    {"id": "M1-P1", "ancho": 400, "alto": 798,
     "material": "PLY", "gama": "LAM", "acabado": "Pale",
     "mecanizado": "cazta.", "apertura": "I"},
    {"id": "M1-C1", "ancho": 400, "alto": 198,
     "material": "PLY", "gama": "LAM", "acabado": "Pale",
     "mecanizado": "torn."},
]


# ---------------------------------------------------------------------------
# Tests de _clasificar
# ---------------------------------------------------------------------------

class TestClasificar:

    def test_despiece_xlsx(self, reglas):
        c = _clasificar(["DESPIECE_EU-21822.xlsx"], reglas)
        assert "DESPIECE_EU-21822.xlsx" in c["despiece"]

    def test_etiquetas_csv(self, reglas):
        c = _clasificar(["ETIQUETAS_EU-21822.csv"], reglas)
        assert "ETIQUETAS_EU-21822.csv" in c["etiquetas"]

    def test_ean_con_espacio(self, reglas):
        c = _clasificar(["EAN LOGISTIC_EU-21822.csv"], reglas)
        assert "EAN LOGISTIC_EU-21822.csv" in c["ean"]

    def test_ot_pdf(self, reglas):
        c = _clasificar(["OT_EU-21822.pdf"], reglas)
        assert "OT_EU-21822.pdf" in c["ot"]

    def test_dxf_tablero(self, reglas):
        c = _clasificar(["EU21822_X_PLY_LAMINADO_PALE_T1.dxf"], reglas)
        assert "EU21822_X_PLY_LAMINADO_PALE_T1.dxf" in c["dxf"]

    def test_nesting_pdf_ply(self, reglas):
        c = _clasificar(["EU21822_Sabine_PLY_LAMINADO_PALE.pdf"], reglas)
        assert "EU21822_Sabine_PLY_LAMINADO_PALE.pdf" in c["pdfs_nesting"]

    def test_nesting_pdf_mdf(self, reglas):
        c = _clasificar(["EU21822_Sabine_MDF_LACA_Blanco.pdf"], reglas)
        assert "EU21822_Sabine_MDF_LACA_Blanco.pdf" in c["pdfs_nesting"]

    def test_albaran(self, reglas):
        c = _clasificar(["ALBARAN_EU-21822.pdf", "ALBARÁN_EU-21822.pdf"], reglas)
        assert "ALBARAN_EU-21822.pdf" in c["albaran"]
        assert "ALBARÁN_EU-21822.pdf" in c["albaran"]

    def test_archivo_no_reconocido(self, reglas):
        c = _clasificar(["documento_random.docx"], reglas)
        assert "documento_random.docx" in c["otros"]

    def test_case_insensitive(self, reglas):
        c = _clasificar(["despiece_eu-21822.xlsx"], reglas)
        assert "despiece_eu-21822.xlsx" in c["despiece"]

    def test_conjunto_tipico(self, reglas):
        nombres = [
            "DESPIECE_EU-21822.xlsx",
            "ETIQUETAS_EU-21822.csv",
            "EAN LOGISTIC_EU-21822.csv",
            "OT_EU-21822.pdf",
            "EU21822_X_PLY_LAMINADO_PALE_T1.dxf",
            "EU21822_X_PLY_LAMINADO_PALE_T2.dxf",
            "EU21822_Sabine_PLY_LAMINADO_PALE.pdf",
        ]
        c = _clasificar(nombres, reglas)
        assert len(c["despiece"]) == 1
        assert len(c["etiquetas"]) == 1
        assert len(c["ean"]) == 1
        assert len(c["ot"]) == 1
        assert len(c["dxf"]) == 2
        assert len(c["pdfs_nesting"]) == 1


# ---------------------------------------------------------------------------
# Tests de _extraer
# ---------------------------------------------------------------------------

class TestExtraer:

    def _archivos_validos(self) -> tuple[dict[str, io.BytesIO], dict]:
        dxf_buf = _dxf_valido()
        archivos = {
            "DESPIECE_EU-99999.xlsx":     _xlsx_despiece(_PIEZAS_VALIDAS),
            "ETIQUETAS_EU-99999.csv":     _csv_etiquetas(_PIEZAS_VALIDAS),
            "EAN LOGISTIC_EU-99999.csv":  _csv_ean(_PIEZAS_VALIDAS),
            "EU99999_Test_PLY_LAMINADO_PALE_T1.dxf": dxf_buf,
        }
        from engine import _clasificar
        from core.reglas_loader import cargar_reglas
        r = cargar_reglas(ROOT / "reglas.yaml")
        clasificados = _clasificar(list(archivos.keys()), r)
        return archivos, clasificados

    def test_extrae_piezas(self):
        archivos, clasificados = self._archivos_validos()
        datos = _extraer(archivos, clasificados)
        assert len(datos.piezas) == 2
        assert datos.piezas[0].id == "M1-P1"

    def test_extrae_etiquetas(self):
        archivos, clasificados = self._archivos_validos()
        datos = _extraer(archivos, clasificados)
        assert len(datos.filas_etiqueta) == 2

    def test_extrae_ean(self):
        archivos, clasificados = self._archivos_validos()
        datos = _extraer(archivos, clasificados)
        assert len(datos.filas_ean) == 2
        assert datos.filas_ean[0].id_bulto == "CUB-EU-99999-1-1"

    def test_extrae_dxfs(self):
        archivos, clasificados = self._archivos_validos()
        datos = _extraer(archivos, clasificados)
        assert len(datos.dxfs) == 1
        assert "CONTROL" in datos.dxfs[0].layers

    def test_sin_despiece_piezas_vacias(self, reglas):
        archivos = {"ETIQUETAS_EU-99999.csv": _csv_etiquetas(_PIEZAS_VALIDAS)}
        clasificados = _clasificar(list(archivos.keys()), reglas)
        datos = _extraer(archivos, clasificados)
        assert datos.piezas == []

    def test_error_extraccion_registrado(self, reglas):
        archivos = {"DESPIECE_EU-99999.xlsx": io.BytesIO(b"no es xlsx")}
        clasificados = _clasificar(list(archivos.keys()), reglas)
        datos = _extraer(archivos, clasificados)
        assert datos.piezas == []
        assert any("DESPIECE" in e for e in datos.errores_extraccion)

    def test_otros_extractores_no_se_ven_afectados_por_fallo_despiece(self, reglas):
        archivos = {
            "DESPIECE_EU-99999.xlsx":    io.BytesIO(b"corrupto"),
            "ETIQUETAS_EU-99999.csv":    _csv_etiquetas(_PIEZAS_VALIDAS),
            "EAN LOGISTIC_EU-99999.csv": _csv_ean(_PIEZAS_VALIDAS),
        }
        clasificados = _clasificar(list(archivos.keys()), reglas)
        datos = _extraer(archivos, clasificados)
        assert datos.filas_etiqueta  # etiquetas sí se extrajeron
        assert datos.filas_ean       # EAN sí se extrajeron
        assert datos.piezas == []   # DESPIECE falló


# ---------------------------------------------------------------------------
# Tests de _ejecutar_checks (pipeline completo)
# ---------------------------------------------------------------------------

class TestEjecutarChecks:

    def _datos_validos(self, reglas) -> DatosProyecto:
        """DatosProyecto con data mínima pero coherente."""
        from core.modelos import Pieza, OTData
        from core.extractor_etiquetas_ean import FilaEtiqueta, FilaEAN

        piezas = [
            Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P",
                  mecanizado="cazta.", apertura="I"),
            Pieza("M1-C1", 400, 198, "PLY", "LAM", "Pale", "C",
                  mecanizado="torn."),
        ]
        etiquetas = [
            FilaEtiqueta("M1-P1", 400, 798, "PLY", "LAM", "Pale"),
            FilaEtiqueta("M1-C1", 400, 198, "PLY", "LAM", "Pale"),
        ]
        ean = [
            FilaEAN("CUB-EU-99999-1-1", 1, 1, "M1-P1", 5.0),
            FilaEAN("CUB-EU-99999-1-1", 1, 1, "M1-C1", 3.0),
        ]
        ot = OTData("EU-99999", "Test Cliente", "Semana 1",
                    num_piezas=2, peso_total_kg=8.0, num_tiradores=0,
                    tableros={"PLY_LAM_Pale": 1})

        from core.modelos import DXFDoc
        dxf = DXFDoc(
            nombre="EU99999_Test_PLY_LAMINADO_PALE_T1.dxf",
            tablero_num=1, material="PLY", gama="LAM", acabado="Pale",
            layers={"CONTROL", "0_ANOTACIONES", "13-BISELAR-EM5-Z0_8",
                    "10_12-CUTEXT-EM5-Z18"},
            layers_con_geometria={"CONTROL"},
        )

        nombres = [
            "DESPIECE_EU-99999.xlsx", "ETIQUETAS_EU-99999.csv",
            "EAN LOGISTIC_EU-99999.csv", "OT_EU-99999.pdf",
            "EU99999_Test_PLY_LAMINADO_PALE_T1.dxf",
            "EU99999_Sabine_PLY_LAMINADO_PALE.pdf",
        ]
        return DatosProyecto(
            nombres=nombres,
            piezas=piezas,
            filas_etiqueta=etiquetas,
            filas_ean=ean,
            ot=ot,
            dxfs=[dxf],
        )

    def test_checks_producen_lista_no_vacia(self, reglas, reglas_cnc):
        datos = self._datos_validos(reglas)
        resultados = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        assert len(resultados) > 0

    def test_checks_cubren_todos_los_grupos(self, reglas, reglas_cnc):
        datos = self._datos_validos(reglas)
        resultados = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        grupos = {c.grupo for c in resultados}
        assert "Inventario" in grupos
        assert "Piezas" in grupos
        assert "DXF" in grupos
        assert "Logistica" in grupos
        assert "Texto CNC" in grupos

    def test_todos_los_checks_tienen_id(self, reglas, reglas_cnc):
        datos = self._datos_validos(reglas)
        resultados = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        for c in resultados:
            assert c.id, f"Check sin ID: {c}"
            assert c.id.startswith("C-"), f"ID inesperado: {c.id}"

    def test_resultados_son_solo_estados_validos(self, reglas, reglas_cnc):
        datos = self._datos_validos(reglas)
        resultados = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        estados_validos = {"PASS", "FAIL", "WARN", "SKIP"}
        for c in resultados:
            assert c.resultado in estados_validos, f"{c.id}: resultado '{c.resultado}'"


# ---------------------------------------------------------------------------
# Tests de estado global (InformeFinal.estado_global)
# ---------------------------------------------------------------------------

class TestEstadoGlobal:

    def _informe_con(self, checks: list) -> InformeFinal:
        inf = InformeFinal("EU-99999", "Test", "Esteban", "Semana 1")
        inf.checks = checks
        return inf

    def _pass(self, id="C-00"):
        from checks._helpers import _pass
        return _pass(id, "desc", True, "Inventario")

    def _fail_bloquea(self, id="C-15"):
        from checks._helpers import _fail
        return _fail(id, "desc", "detalle error", True, "Material")

    def _fail_no_bloquea(self, id="C-16"):
        from checks._helpers import _fail
        return _fail(id, "desc", "detalle", False, "Material")

    def _warn(self, id="C-43"):
        from checks._helpers import _warn
        return _warn(id, "desc", "detalle", "DXF")

    def test_aprobado_sin_errores(self):
        inf = self._informe_con([self._pass("C-00"), self._pass("C-01")])
        assert inf.estado_global == "OK"

    def test_bloqueado_con_fail_bloqueante(self):
        inf = self._informe_con([self._fail_bloquea(), self._pass()])
        assert inf.estado_global == "BLOQUEADO"
        assert inf.bloquea

    def test_advertencias_solo_warn(self):
        inf = self._informe_con([self._warn(), self._pass()])
        assert inf.estado_global == "ADVERTENCIAS"
        assert not inf.bloquea

    def test_advertencias_fail_no_bloqueante(self):
        inf = self._informe_con([self._fail_no_bloquea(), self._pass()])
        # FAIL sin bloquea no es error_critico → no es BLOQUEADO
        # Pero sí es FAIL → ¿es advertencia? No: es_advertencia solo para WARN.
        # El informe tendrá FAIL pero no bloquea → estado = ADVERTENCIAS no, sino...
        # Mirando la lógica: errores_criticos = FAIL+bloquea; advertencias = WARN
        # FAIL sin bloquea no entra en ninguno → OK si no hay WARNs
        assert inf.estado_global == "OK"  # FAIL sin bloquea = no bloquea y no es WARN

    def test_bloqueado_gana_sobre_warn(self):
        inf = self._informe_con([self._fail_bloquea(), self._warn()])
        assert inf.estado_global == "BLOQUEADO"

    def test_lista_errores_criticos(self):
        inf = self._informe_con([self._fail_bloquea("C-15"), self._pass()])
        assert len(inf.errores_criticos) == 1
        assert inf.errores_criticos[0].id == "C-15"

    def test_lista_advertencias(self):
        inf = self._informe_con([self._warn("C-43"), self._pass()])
        assert len(inf.advertencias) == 1
        assert inf.advertencias[0].id == "C-43"


# ---------------------------------------------------------------------------
# Test de integración end-to-end: engine sin Drive
# ---------------------------------------------------------------------------

class TestPipelineEndToEnd:

    def _armar_archivos(self, piezas: list[dict], reglas) -> tuple[dict, dict]:
        dxf_buf = _dxf_valido()
        archivos = {
            "DESPIECE_EU-99999.xlsx":     _xlsx_despiece(piezas),
            "ETIQUETAS_EU-99999.csv":     _csv_etiquetas(piezas),
            "EAN LOGISTIC_EU-99999.csv":  _csv_ean(piezas),
            "EU99999_Test_PLY_LAMINADO_PALE_T1.dxf": dxf_buf,
            "EU99999_Test_PLY_LAMINADO_PALE.pdf": io.BytesIO(b"%PDF fake"),
        }
        clasificados = _clasificar(list(archivos.keys()), reglas)
        return archivos, clasificados

    def test_pipeline_piezas_ply_lam_no_bloquea(self, reglas, reglas_cnc):
        archivos, clasificados = self._armar_archivos(_PIEZAS_VALIDAS, reglas)
        datos = _extraer(archivos, clasificados)
        checks = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        inf = InformeFinal("EU-99999", "", "Esteban", "Semana 1", checks=checks)
        # PLY+LAM+Pale válido → C-15, C-16 PASS
        c15 = next(c for c in checks if c.id == "C-15")
        c16 = next(c for c in checks if c.id == "C-16")
        assert c15.resultado == "PASS"
        assert c16.resultado == "PASS"

    def test_pipeline_material_invalido_falla_c15(self, reglas, reglas_cnc):
        piezas_invalidas = [
            {**_PIEZAS_VALIDAS[0], "material": "PLY", "gama": "LAC",
             "acabado": "Blanco"},  # PLY+LAC → inválido
        ]
        archivos, clasificados = self._armar_archivos(piezas_invalidas, reglas)
        datos = _extraer(archivos, clasificados)
        checks = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        c15 = next(c for c in checks if c.id == "C-15")
        assert c15.resultado == "FAIL"
        assert c15.bloquea

    def test_pipeline_puerta_sin_apertura_falla_c20(self, reglas, reglas_cnc):
        piezas = [
            {"id": "M1-P1", "ancho": 400, "alto": 798,
             "material": "PLY", "gama": "LAM", "acabado": "Pale",
             "mecanizado": "cazta.", "apertura": ""},  # sin apertura
        ]
        archivos, clasificados = self._armar_archivos(piezas, reglas)
        datos = _extraer(archivos, clasificados)
        checks = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        c20 = next(c for c in checks if c.id == "C-20")
        assert c20.resultado == "FAIL"

    def test_pipeline_ids_inconsistentes_fallan_c11(self, reglas, reglas_cnc):
        piezas_despiece = [_PIEZAS_VALIDAS[0]]
        piezas_etiquetas_distintas = [
            {**_PIEZAS_VALIDAS[0], "id": "M1-P99"},  # ID diferente
        ]
        dxf_buf = _dxf_valido()
        archivos = {
            "DESPIECE_EU-99999.xlsx":     _xlsx_despiece(piezas_despiece),
            "ETIQUETAS_EU-99999.csv":     _csv_etiquetas(piezas_etiquetas_distintas),
            "EAN LOGISTIC_EU-99999.csv":  _csv_ean(piezas_despiece),
            "EU99999_Test_PLY_LAMINADO_PALE_T1.dxf": dxf_buf,
        }
        clasificados = _clasificar(list(archivos.keys()), reglas)
        datos = _extraer(archivos, clasificados)
        checks = _ejecutar_checks(datos, "EU-99999", reglas, reglas_cnc)
        c11 = next(c for c in checks if c.id == "C-11")
        assert c11.resultado == "FAIL"
