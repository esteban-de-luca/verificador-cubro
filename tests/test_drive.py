"""
tests/test_drive.py

Tests del módulo drive/ con Google Drive API mockeada.
Ningún test toca Drive real — se valida únicamente la lógica del módulo.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from drive import navegador, descargador, gestor
from drive.navegador import _extraer_estado, _RE_SEMANA


# ===========================================================================
# Helpers: fábrica de servicio Drive mock
# ===========================================================================

def _hacer_servicio_mock(archivos_list_responses: list[dict] | None = None,
                        get_response: dict | None = None) -> MagicMock:
    """
    Construye un mock del objeto servicio Drive con la forma:
        servicio.files().list(...).execute() -> respuesta
        servicio.files().update(...).execute() -> respuesta
        servicio.files().get(...).execute() -> respuesta
        servicio.files().get_media(...) -> request (consumida por downloader)
    """
    servicio = MagicMock()
    files_ns = servicio.files.return_value

    # list().execute()
    list_iter = iter(archivos_list_responses or [])

    def _list_execute(*args, **kwargs):
        return next(list_iter, {"files": []})

    files_ns.list.return_value.execute.side_effect = _list_execute

    # get().execute()
    files_ns.get.return_value.execute.return_value = get_response or {"parents": []}

    # update().execute()
    files_ns.update.return_value.execute.return_value = {"id": "X", "name": "renamed"}

    return servicio


# ===========================================================================
# _extraer_estado
# ===========================================================================

class TestExtraerEstado:

    def test_pendiente_sin_prefijo(self):
        """PASS: nombre sin prefijo → PENDIENTE."""
        assert _extraer_estado("EU-21822_Sabine_Jennes") == "PENDIENTE"

    def test_aprobado_con_ok(self):
        """PASS: prefijo [OK] → OK."""
        assert _extraer_estado("[OK] EU-21822_Sabine_Jennes") == "OK"

    def test_bloqueado(self):
        """PASS: prefijo [BLOQUEADO] → BLOQUEADO."""
        assert _extraer_estado("[BLOQUEADO] SP-21493_Belen_Duenas") == "BLOQUEADO"

    def test_advertencias(self):
        """PASS: prefijo [ADVERTENCIAS] → ADVERTENCIAS."""
        assert _extraer_estado("[ADVERTENCIAS] EU-22005") == "ADVERTENCIAS"

    def test_prefijo_desconocido_es_pendiente(self):
        """FAIL semántico: prefijo [FOO] no reconocido → PENDIENTE."""
        assert _extraer_estado("[FOO] EU-99999") == "PENDIENTE"


# ===========================================================================
# Regex de semana
# ===========================================================================

class TestRegexSemana:

    def test_semana_18_parsea(self):
        assert _RE_SEMANA.match("Semana 18").group(1) == "18"

    def test_semana_con_cero_inicial(self):
        assert _RE_SEMANA.match("Semana 08").group(1) == "8"

    def test_no_semana_no_hace_match(self):
        assert _RE_SEMANA.match("Otra cosa") is None


# ===========================================================================
# listar_responsables
# ===========================================================================

class TestListarResponsables:

    def test_devuelve_solo_los_de_config(self):
        """PASS: filtra las subcarpetas contra config.RESPONSABLES y preserva orden."""
        respuesta = {"files": [
            {"id": "1", "name": "Marina", "parents": ["root"]},
            {"id": "2", "name": "Carpeta_rara", "parents": ["root"]},
            {"id": "3", "name": "Esteban", "parents": ["root"]},
            {"id": "4", "name": "Lucia", "parents": ["root"]},
        ]}
        servicio = _hacer_servicio_mock([respuesta])
        with patch("config.drive_cuarentena_id", return_value="root"):
            resultado = navegador.listar_responsables(servicio)
        nombres = [r["name"] for r in resultado]
        # Orden definido por config.RESPONSABLES: Esteban, Javier, Lucia, Isabel, Marina
        assert nombres == ["Esteban", "Lucia", "Marina"]

    def test_devuelve_vacio_si_no_hay_subcarpetas(self):
        """FAIL semántico: sin carpetas válidas → lista vacía."""
        servicio = _hacer_servicio_mock([{"files": []}])
        with patch("config.drive_cuarentena_id", return_value="root"):
            assert navegador.listar_responsables(servicio) == []


# ===========================================================================
# listar_semanas
# ===========================================================================

class TestListarSemanas:

    def test_orden_descendente_por_numero(self):
        """PASS: semanas ordenadas de mayor a menor número."""
        respuesta_resp = {"files": [{"id": "est", "name": "Esteban", "parents": ["root"]}]}
        respuesta_semanas = {"files": [
            {"id": "s18", "name": "Semana 18", "parents": ["est"]},
            {"id": "s08", "name": "Semana 08", "parents": ["est"]},
            {"id": "s19", "name": "Semana 19", "parents": ["est"]},
            {"id": "otro", "name": "No es semana", "parents": ["est"]},
        ]}
        servicio = _hacer_servicio_mock([respuesta_resp, respuesta_semanas])
        with patch("config.drive_cuarentena_id", return_value="root"):
            semanas = navegador.listar_semanas(servicio, "Esteban")
        assert [s["numero"] for s in semanas] == [19, 18, 8]

    def test_responsable_inexistente_devuelve_vacio(self):
        """FAIL: responsable que no existe en Drive → lista vacía, no exception."""
        servicio = _hacer_servicio_mock([{"files": []}])
        with patch("config.drive_cuarentena_id", return_value="root"):
            assert navegador.listar_semanas(servicio, "Fantasma") == []


# ===========================================================================
# listar_proyectos
# ===========================================================================

class TestListarProyectos:

    def test_extrae_estado_y_ordena(self):
        """PASS: proyectos ordenados alfabéticamente por nombre_limpio, estado extraído."""
        respuesta = {"files": [
            {"id": "p1", "name": "[BLOQUEADO] SP-21493_Belen_Duenas", "parents": ["s18"]},
            {"id": "p2", "name": "EU-22005_Moritz", "parents": ["s18"]},
            {"id": "p3", "name": "[OK] EU-21822_Sabine_Jennes", "parents": ["s18"]},
        ]}
        servicio = _hacer_servicio_mock([respuesta])
        proyectos = navegador.listar_proyectos(servicio, "s18")
        assert [p["nombre_limpio"] for p in proyectos] == [
            "EU-21822_Sabine_Jennes",
            "EU-22005_Moritz",
            "SP-21493_Belen_Duenas",
        ]
        estados = {p["nombre_limpio"]: p["estado"] for p in proyectos}
        assert estados["EU-21822_Sabine_Jennes"] == "OK"
        assert estados["EU-22005_Moritz"] == "PENDIENTE"
        assert estados["SP-21493_Belen_Duenas"] == "BLOQUEADO"


# ===========================================================================
# Paginación
# ===========================================================================

class TestPaginacion:

    def test_recorre_varias_paginas(self):
        """PASS: nextPageToken se sigue hasta agotar páginas."""
        pag1 = {
            "files": [{"id": "a", "name": "Esteban", "parents": ["root"]}],
            "nextPageToken": "tok2",
        }
        pag2 = {
            "files": [{"id": "b", "name": "Marina", "parents": ["root"]}],
        }
        servicio = _hacer_servicio_mock([pag1, pag2])
        with patch("config.drive_cuarentena_id", return_value="root"):
            resultado = navegador.listar_responsables(servicio)
        nombres = [r["name"] for r in resultado]
        assert "Esteban" in nombres and "Marina" in nombres


# ===========================================================================
# Descargador
# ===========================================================================

class TestDescargador:

    def test_descargar_carpeta_devuelve_bytesio_por_nombre(self):
        """PASS: cada archivo de la carpeta se descarga a un BytesIO."""
        lista = {"files": [
            {"id": "f1", "name": "DESPIECE_EU-21822.xlsx", "mimeType": "app/xlsx", "size": 100},
            {"id": "f2", "name": "ETIQUETAS_EU-21822.csv", "mimeType": "text/csv", "size": 50},
        ]}
        servicio = _hacer_servicio_mock([lista])

        # Parchear MediaIoBaseDownload para evitar llamadas HTTP reales.
        def _fake_downloader_factory(buffer, _request):
            buffer.write(b"contenido-mock")
            downloader = MagicMock()
            downloader.next_chunk.return_value = (MagicMock(), True)
            return downloader

        with patch("drive.descargador.MediaIoBaseDownload", side_effect=_fake_downloader_factory), \
             patch("drive.navegador._buscar_subcarpeta_por_nombre", return_value=None):
            resultado = descargador.descargar_carpeta(servicio, "folder123")

        assert set(resultado.keys()) == {
            "DESPIECE_EU-21822.xlsx",
            "ETIQUETAS_EU-21822.csv",
        }
        for buffer in resultado.values():
            assert isinstance(buffer, io.BytesIO)
            assert buffer.tell() == 0  # reseteado al inicio
            assert buffer.read() == b"contenido-mock"

    def test_carpeta_vacia_devuelve_dict_vacio(self):
        """FAIL semántico: sin archivos → dict vacío, no excepción."""
        servicio = _hacer_servicio_mock([{"files": []}])
        with patch("drive.navegador._buscar_subcarpeta_por_nombre", return_value=None):
            assert descargador.descargar_carpeta(servicio, "folder_vacio") == {}


# ===========================================================================
# Gestor: renombrar / mover / prefijo
# ===========================================================================

class TestGestor:

    def test_renombrar_carpeta_llama_api_correctamente(self):
        servicio = _hacer_servicio_mock()
        gestor.renombrar_carpeta(servicio, "f1", "nuevo_nombre")
        call_kwargs = servicio.files().update.call_args.kwargs
        assert call_kwargs["fileId"] == "f1"
        assert call_kwargs["body"] == {"name": "nuevo_nombre"}
        assert call_kwargs["supportsAllDrives"] is True

    def test_mover_carpeta_elimina_parents_previos(self):
        """PASS: se llama update con addParents + removeParents correctos."""
        servicio = _hacer_servicio_mock(get_response={"parents": ["old1", "old2"]})
        gestor.mover_carpeta(servicio, "f1", "nuevo_parent")
        call_kwargs = servicio.files().update.call_args.kwargs
        assert call_kwargs["addParents"] == "nuevo_parent"
        assert call_kwargs["removeParents"] == "old1,old2"

    def test_aplicar_prefijo_estado_aprobado(self):
        """PASS: añade [OK] al nombre limpio."""
        reglas = {"nomenclatura": {"prefijos_estado": {
            "bloqueado": "[BLOQUEADO] ",
            "advertencias": "[ADVERTENCIAS] ",
            "aprobado": "[OK] ",
        }}}
        servicio = _hacer_servicio_mock()
        gestor.aplicar_prefijo_estado(
            servicio, "f1", "EU-21822_Sabine_Jennes", "aprobado", reglas
        )
        body = servicio.files().update.call_args.kwargs["body"]
        assert body["name"] == "[OK] EU-21822_Sabine_Jennes"

    def test_aplicar_prefijo_reemplaza_prefijo_previo(self):
        """PASS: si ya había [BLOQUEADO], se reemplaza por [OK]."""
        reglas = {"nomenclatura": {"prefijos_estado": {
            "bloqueado": "[BLOQUEADO] ",
            "advertencias": "[ADVERTENCIAS] ",
            "aprobado": "[OK] ",
        }}}
        servicio = _hacer_servicio_mock()
        gestor.aplicar_prefijo_estado(
            servicio, "f1", "[BLOQUEADO] SP-21493_Belen", "aprobado", reglas
        )
        body = servicio.files().update.call_args.kwargs["body"]
        assert body["name"] == "[OK] SP-21493_Belen"

    def test_estado_invalido_lanza_error(self):
        """FAIL: estado desconocido → ValueError."""
        reglas = {"nomenclatura": {"prefijos_estado": {"aprobado": "[OK] "}}}
        servicio = _hacer_servicio_mock()
        with pytest.raises(ValueError, match="estado inválido"):
            gestor.aplicar_prefijo_estado(
                servicio, "f1", "EU-X", "verde_fluor", reglas
            )

    def test_prefijo_ausente_en_yaml_lanza_error(self):
        """FAIL: el YAML no tiene el prefijo para el estado dado → ValueError."""
        reglas = {"nomenclatura": {"prefijos_estado": {"aprobado": "[OK] "}}}
        servicio = _hacer_servicio_mock()
        with pytest.raises(ValueError, match="no define"):
            gestor.aplicar_prefijo_estado(
                servicio, "f1", "EU-X", "bloqueado", reglas
            )
