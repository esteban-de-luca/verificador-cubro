"""tests/test_notion_writer.py — Tests de NotionWriter con Notion mockeado."""

from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch
import datetime
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import CheckResult, InformeFinal
from checks._helpers import _pass, _fail, _warn, _skip
from notion_writer import NotionWriter, _PROPS, _MAX_RICH_TEXT


# ---------------------------------------------------------------------------
# Fixtures de InformeFinal
# ---------------------------------------------------------------------------

def _check(id="C-00", resultado="PASS", bloquea=True, grupo="Inventario", detalle=""):
    return CheckResult(
        id=id,
        desc=f"Descripción {id}",
        resultado=resultado,
        bloquea=bloquea,
        grupo=grupo,
        detalle=detalle,
    )


def _informe(estado="APROBADO") -> InformeFinal:
    inf = InformeFinal(
        id_proyecto="EU-21822",
        cliente="Sabine Jennes",
        responsable="Esteban",
        semana="Semana 18",
    )
    if estado == "APROBADO":
        inf.checks = [_check("C-00", "PASS"), _check("C-01", "PASS"),
                      _check("C-02", "SKIP", bloquea=False, grupo="Inventario")]
    elif estado == "ADVERTENCIAS":
        inf.checks = [_check("C-00", "PASS"),
                      _check("C-16", "WARN", bloquea=False, grupo="Material",
                             detalle="acabado 'Raro' no validado")]
    elif estado == "BLOQUEADO":
        inf.checks = [_check("C-15", "FAIL", bloquea=True, grupo="Material",
                             detalle="PLY+LAC inválido"),
                      _check("C-00", "PASS")]
    return inf


def _writer_con_mock(buscar_resultado=None) -> tuple[NotionWriter, MagicMock]:
    """Devuelve (writer, mock_client) con Client patcheado."""
    writer = NotionWriter.__new__(NotionWriter)
    mock_client = MagicMock()
    mock_client.databases.query.return_value = {
        "results": [buscar_resultado] if buscar_resultado else []
    }
    mock_client.pages.create.return_value = {
        "id": "nueva-page-id",
        "url": "https://notion.so/nueva-page-id",
    }
    mock_client.pages.update.return_value = {
        "id": "existente-page-id",
        "url": "https://notion.so/existente-page-id",
    }
    writer._client = mock_client
    writer._db_id = "test-db-id"
    return writer, mock_client


# ---------------------------------------------------------------------------
# Tests de crear / actualizar
# ---------------------------------------------------------------------------

class TestEscribirVerificacion:

    def test_crea_pagina_cuando_no_existe(self):
        writer, mock_client = _writer_con_mock(buscar_resultado=None)
        url = writer.escribir_verificacion(_informe("APROBADO"))
        mock_client.pages.create.assert_called_once()
        mock_client.pages.update.assert_not_called()
        assert url == "https://notion.so/nueva-page-id"

    def test_actualiza_pagina_cuando_existe(self):
        existente = {"id": "existente-page-id", "url": "https://notion.so/existente-page-id"}
        writer, mock_client = _writer_con_mock(buscar_resultado=existente)
        url = writer.escribir_verificacion(_informe("BLOQUEADO"))
        mock_client.pages.update.assert_called_once()
        mock_client.pages.create.assert_not_called()
        assert url == "https://notion.so/existente-page-id"

    def test_busqueda_usa_id_proyecto(self):
        writer, mock_client = _writer_con_mock()
        writer.escribir_verificacion(_informe())
        llamada = mock_client.databases.query.call_args
        filtro = llamada.kwargs["filter"] if llamada.kwargs else llamada[1]["filter"]
        assert filtro["rich_text"]["equals"] == "EU-21822"

    def test_error_notion_se_propaga(self):
        from notion_client import APIResponseError
        writer, mock_client = _writer_con_mock()
        mock_client.pages.create.side_effect = APIResponseError(
            "validation_error", 400, "error", MagicMock(), ""
        )
        with pytest.raises(APIResponseError):
            writer.escribir_verificacion(_informe())

    def test_buscar_falla_silenciosamente_y_crea(self):
        from notion_client import APIResponseError
        writer, mock_client = _writer_con_mock()
        mock_client.databases.query.side_effect = APIResponseError(
            "validation_error", 400, "error", MagicMock(), ""
        )
        # No debe lanzar excepción — crea como nuevo
        url = writer.escribir_verificacion(_informe())
        mock_client.pages.create.assert_called_once()
        assert url == "https://notion.so/nueva-page-id"


# ---------------------------------------------------------------------------
# Tests de propiedades construidas
# ---------------------------------------------------------------------------

class TestConstruirPropiedades:

    def test_titulo_incluye_id_y_cliente(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe("APROBADO"))
        titulo = props[_PROPS["nombre"]]["title"][0]["text"]["content"]
        assert "EU-21822" in titulo
        assert "Sabine Jennes" in titulo

    def test_titulo_sin_cliente(self):
        inf = _informe("APROBADO")
        inf.cliente = ""
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(inf)
        titulo = props[_PROPS["nombre"]]["title"][0]["text"]["content"]
        assert "EU-21822" in titulo

    def test_estado_select_correcto(self):
        for estado in ("APROBADO", "ADVERTENCIAS", "BLOQUEADO"):
            writer, _ = _writer_con_mock()
            props = writer._construir_propiedades(_informe(estado))
            assert props[_PROPS["estado"]]["select"]["name"] == estado

    def test_contadores_correctos_aprobado(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe("APROBADO"))
        assert props[_PROPS["n_errores"]]["number"] == 0
        assert props[_PROPS["n_avisos"]]["number"] == 0
        assert props[_PROPS["n_pass"]]["number"] == 2
        assert props[_PROPS["n_skip"]]["number"] == 1

    def test_contadores_correctos_bloqueado(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe("BLOQUEADO"))
        assert props[_PROPS["n_errores"]]["number"] == 1
        assert props[_PROPS["n_avisos"]]["number"] == 0

    def test_fecha_es_hoy(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe())
        fecha_str = props[_PROPS["fecha"]]["date"]["start"]
        assert fecha_str == datetime.date.today().isoformat()

    def test_responsable_select(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe())
        assert props[_PROPS["responsable"]]["select"]["name"] == "Esteban"

    def test_texto_largo_truncado(self):
        inf = _informe("BLOQUEADO")
        # Crear muchos errores con detalle largo
        inf.checks = [
            _check(f"C-{i:02d}", "FAIL", bloquea=True, grupo="Material",
                   detalle="x" * 300)
            for i in range(10)
        ]
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(inf)
        detalle = props[_PROPS["detalle_errores"]]["rich_text"][0]["text"]["content"]
        assert len(detalle) <= _MAX_RICH_TEXT

    def test_notas_vacias_si_sin_c63(self):
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(_informe("APROBADO"))
        notas = props[_PROPS["notas"]]["rich_text"][0]["text"]["content"]
        assert notas == ""

    def test_notas_incluyen_c63_warn(self):
        inf = _informe("ADVERTENCIAS")
        inf.checks.append(
            _check("C-63", "WARN", bloquea=False, grupo="Texto CNC",
                   detalle="«texto raro»")
        )
        writer, _ = _writer_con_mock()
        props = writer._construir_propiedades(inf)
        notas = props[_PROPS["notas"]]["rich_text"][0]["text"]["content"]
        assert "«texto raro»" in notas


# ---------------------------------------------------------------------------
# Tests de helpers de extracción
# ---------------------------------------------------------------------------

class TestExtraccion:

    def test_detalle_max_10_errores(self):
        inf = _informe("APROBADO")
        inf.checks = [
            _check(f"C-{i:02d}", "FAIL", bloquea=True, grupo="Material")
            for i in range(15)
        ]
        writer, _ = _writer_con_mock()
        detalle = writer._extraer_detalle_errores(inf)
        # Debe incluir exactamente 10 checks (cada uno genera ≥1 línea)
        ids_en_detalle = [f"C-{i:02d}" for i in range(10)]
        ids_fuera = [f"C-{i:02d}" for i in range(10, 15)]
        for id_ in ids_en_detalle:
            assert id_ in detalle
        for id_ in ids_fuera:
            assert id_ not in detalle

    def test_detalle_incluye_descripcion_y_detalle(self):
        inf = _informe("APROBADO")
        inf.checks = [
            _check("C-15", "FAIL", bloquea=True, grupo="Material",
                   detalle="PLY+LAC inválido")
        ]
        writer, _ = _writer_con_mock()
        detalle = writer._extraer_detalle_errores(inf)
        assert "C-15" in detalle
        assert "PLY+LAC inválido" in detalle
