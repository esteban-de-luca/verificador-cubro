"""tests/test_sheets_writer.py — Tests de sheets_writer con la API mockeada.

Verifican el CONTRATO con el dashboard: 14 columnas en orden fijo, RAW,
timestamp ISO 8601, estado en minúsculas, conteos enteros y listas unidas
con '\\n'.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import CheckResult, InformeFinal
import sheets_writer
from sheets_writer import (
    COLUMNAS,
    append_verificacion,
    construir_fila,
    _derivar_estado,
)


# ---------------------------------------------------------------------------
# Fixtures
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


def _informe(estado="OK") -> InformeFinal:
    inf = InformeFinal(
        id_proyecto="EU-21822",
        cliente="Sabine Jennes",
        responsable="Esteban",
        semana="Semana 18",
    )
    if estado == "OK":
        inf.checks = [
            _check("C-00", "PASS"),
            _check("C-01", "PASS"),
            _check("C-02", "SKIP", bloquea=False),
        ]
    elif estado == "ADVERTENCIAS":
        inf.checks = [
            _check("C-00", "PASS"),
            _check("C-16", "WARN", bloquea=False, grupo="Material",
                   detalle="acabado 'Raro' no validado"),
        ]
    elif estado == "BLOQUEADO":
        inf.checks = [
            _check("C-15", "FAIL", bloquea=True, grupo="Material",
                   detalle="PLY+LAC inválido"),
            _check("C-00", "PASS"),
            _check("C-16", "WARN", bloquea=False, grupo="Material"),
        ]
    return inf


_AHORA = datetime(2026, 6, 24, 9, 30, 15, tzinfo=timezone.utc)


def _fila(estado="OK", link_informe="", ahora=_AHORA) -> dict:
    """Devuelve la fila como dict {columna: valor} para asserts legibles."""
    valores = construir_fila(_informe(estado), link_informe=link_informe, ahora=ahora)
    assert len(valores) == len(COLUMNAS) == 14
    return dict(zip(COLUMNAS, valores))


# ---------------------------------------------------------------------------
# construir_fila — formato de columnas
# ---------------------------------------------------------------------------

class TestConstruirFila:

    def test_14_columnas_en_orden(self):
        valores = construir_fila(_informe("OK"), ahora=_AHORA)
        assert len(valores) == 14
        assert COLUMNAS == [
            "timestamp", "id_proyecto", "estado", "responsable",
            "semana_produccion", "fecha_analisis", "cliente", "n_fail",
            "n_warn", "n_pass", "errores_criticos", "advertencias",
            "aspectos_relevantes", "link_informe",
        ]

    def test_timestamp_iso_8601_segundos(self):
        f = _fila("OK")
        assert f["timestamp"] == "2026-06-24T09:30:15+00:00"

    def test_fecha_analisis_iso(self):
        f = _fila("OK")
        assert f["fecha_analisis"] == "2026-06-24"

    def test_estado_minusculas_aprobado(self):
        assert _fila("OK")["estado"] == "aprobado"

    def test_estado_minusculas_advertencias(self):
        assert _fila("ADVERTENCIAS")["estado"] == "advertencias"

    def test_estado_minusculas_bloqueado(self):
        assert _fila("BLOQUEADO")["estado"] == "bloqueado"

    def test_id_proyecto(self):
        assert _fila("OK")["id_proyecto"] == "EU-21822"

    def test_responsable_cliente_semana(self):
        f = _fila("OK")
        assert f["responsable"] == "Esteban"
        assert f["cliente"] == "Sabine Jennes"
        assert f["semana_produccion"] == "Semana 18"

    def test_conteos_son_enteros(self):
        f = _fila("BLOQUEADO")
        for col in ("n_fail", "n_warn", "n_pass"):
            assert isinstance(f[col], int)

    def test_conteos_aprobado(self):
        f = _fila("OK")
        assert (f["n_fail"], f["n_warn"], f["n_pass"]) == (0, 0, 2)

    def test_conteos_bloqueado(self):
        f = _fila("BLOQUEADO")
        # 1 error crítico, 1 aviso, 1 PASS
        assert (f["n_fail"], f["n_warn"], f["n_pass"]) == (1, 1, 1)

    def test_errores_criticos_texto(self):
        f = _fila("BLOQUEADO")
        assert "C-15" in f["errores_criticos"]
        assert "PLY+LAC inválido" in f["errores_criticos"]
        # Sin errores → ""
        assert _fila("OK")["errores_criticos"] == ""

    def test_advertencias_texto(self):
        f = _fila("ADVERTENCIAS")
        assert "C-16" in f["advertencias"]
        assert _fila("OK")["advertencias"] == ""

    def test_listas_se_unen_con_salto_de_linea(self):
        inf = _informe("BLOQUEADO")
        inf.checks = [
            _check("C-10", "FAIL", bloquea=True, grupo="Material"),
            _check("C-11", "FAIL", bloquea=True, grupo="Material"),
        ]
        valores = construir_fila(inf, ahora=_AHORA)
        col_err = dict(zip(COLUMNAS, valores))["errores_criticos"]
        assert col_err.count("\n") == 1
        assert col_err.split("\n")[0].startswith("C-10")
        assert col_err.split("\n")[1].startswith("C-11")

    def test_aspectos_relevantes_desde_c63(self):
        inf = _informe("ADVERTENCIAS")
        inf.checks.append(
            _check("C-63", "WARN", bloquea=False, grupo="Texto CNC",
                   detalle="«texto raro»")
        )
        f = dict(zip(COLUMNAS, construir_fila(inf, ahora=_AHORA)))
        assert "«texto raro»" in f["aspectos_relevantes"]

    def test_aspectos_relevantes_vacios_por_defecto(self):
        assert _fila("OK")["aspectos_relevantes"] == ""

    def test_link_informe(self):
        f = _fila("OK", link_informe="https://drive.google.com/x")
        assert f["link_informe"] == "https://drive.google.com/x"
        assert _fila("OK")["link_informe"] == ""

    def test_campos_vacios_son_string_vacio(self):
        inf = InformeFinal(id_proyecto="", cliente="", responsable="", semana="")
        f = dict(zip(COLUMNAS, construir_fila(inf, ahora=_AHORA)))
        for col in ("id_proyecto", "cliente", "responsable",
                    "semana_produccion", "link_informe"):
            assert f[col] == ""


class TestDerivarEstado:

    def test_bloqueado_tiene_prioridad(self):
        assert _derivar_estado(2, 5) == "bloqueado"

    def test_advertencias_si_no_hay_fail(self):
        assert _derivar_estado(0, 3) == "advertencias"

    def test_aprobado_si_todo_limpio(self):
        assert _derivar_estado(0, 0) == "aprobado"


# ---------------------------------------------------------------------------
# append_verificacion — llamada a la API
# ---------------------------------------------------------------------------

def _servicio_mock(append_resultados=None):
    """Servicio Sheets mockeado. append_resultados: lista para side_effect."""
    servicio = MagicMock()
    append_exec = (
        servicio.spreadsheets.return_value
        .values.return_value
        .append.return_value
        .execute
    )
    if append_resultados is not None:
        append_exec.side_effect = append_resultados
    else:
        append_exec.return_value = {"updates": {"updatedRows": 1}}
    return servicio


def _kwargs_append(servicio) -> dict:
    return servicio.spreadsheets.return_value.values.return_value.append.call_args.kwargs


class TestAppendVerificacion:

    def test_usa_value_input_option_raw(self):
        servicio = _servicio_mock()
        append_verificacion(_informe("OK"), servicio=servicio,
                            sheet_id="SID", tab="Log", ahora=_AHORA)
        kw = _kwargs_append(servicio)
        assert kw["valueInputOption"] == "RAW"
        assert kw["insertDataOption"] == "INSERT_ROWS"

    def test_usa_sheet_id_y_rango_correctos(self):
        servicio = _servicio_mock()
        append_verificacion(_informe("OK"), servicio=servicio,
                            sheet_id="SID-123", tab="Log", ahora=_AHORA)
        kw = _kwargs_append(servicio)
        assert kw["spreadsheetId"] == "SID-123"
        assert kw["range"] == "'Log'!A:N"

    def test_pestaña_con_comillas_se_escapa(self):
        servicio = _servicio_mock()
        append_verificacion(_informe("OK"), servicio=servicio,
                            sheet_id="SID", tab="Hoja'X", ahora=_AHORA)
        assert _kwargs_append(servicio)["range"] == "'Hoja''X'!A:N"

    def test_envia_una_fila_de_14_columnas(self):
        servicio = _servicio_mock()
        append_verificacion(_informe("BLOQUEADO"), servicio=servicio,
                            sheet_id="SID", tab="Log", ahora=_AHORA)
        body = _kwargs_append(servicio)["body"]
        assert len(body["values"]) == 1
        assert len(body["values"][0]) == 14
        assert body["values"][0][2] == "bloqueado"  # columna estado

    def test_fallback_a_primera_hoja_si_pestaña_no_existe(self):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 400
        err = HttpError(
            resp, b'{"error":{"message":"Unable to parse range: Log!A:N"}}'
        )
        servicio = _servicio_mock(
            append_resultados=[err, {"updates": {"updatedRows": 1}}]
        )
        # metadata de la primera hoja
        servicio.spreadsheets.return_value.get.return_value.execute.return_value = {
            "sheets": [
                {"properties": {"title": "_Log_Verificacion_Ficheros", "index": 0}}
            ]
        }
        append_verificacion(_informe("OK"), servicio=servicio,
                            sheet_id="SID", tab="Log", ahora=_AHORA)

        # Se llamó append dos veces: primero "Log", luego la primera hoja real.
        append = servicio.spreadsheets.return_value.values.return_value.append
        rangos = [c.kwargs["range"] for c in append.call_args_list]
        assert rangos == ["'Log'!A:N", "'_Log_Verificacion_Ficheros'!A:N"]

    def test_error_no_de_rango_se_propaga(self):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 403
        err = HttpError(resp, b'{"error":{"message":"permission denied"}}')
        servicio = _servicio_mock(append_resultados=[err])
        with pytest.raises(HttpError):
            append_verificacion(_informe("OK"), servicio=servicio,
                                sheet_id="SID", tab="Log", ahora=_AHORA)

    def test_usa_config_por_defecto(self, monkeypatch):
        servicio = _servicio_mock()
        monkeypatch.setattr(sheets_writer.config, "log_verif_sheet_id",
                            lambda: "DEFAULT-SID")
        monkeypatch.setattr(sheets_writer.config, "log_verif_tab",
                            lambda: "Log")
        append_verificacion(_informe("OK"), servicio=servicio, ahora=_AHORA)
        assert _kwargs_append(servicio)["spreadsheetId"] == "DEFAULT-SID"
