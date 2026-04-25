"""
tests/test_extractores.py

Tests de los extractores con datos sintéticos en memoria.
No se requieren ficheros reales de proyecto — todo se construye aquí.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import ezdxf
import openpyxl
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.modelos import CheckResult, Pieza, Bulto, OTData, DXFDoc, InformeFinal
from core.extractor_despiece import leer_despiece, _inferir_tipologia, _normalizar
from core.extractor_etiquetas_ean import leer_etiquetas, leer_ean
from core.extractor_ot import leer_ot


# ===========================================================================
# Helpers de construcción de fixtures en memoria
# ===========================================================================

def _xlsx_en_memoria(filas: list[list]) -> io.BytesIO:
    """Crea un XLSX en memoria con las filas dadas (primera fila = cabecera)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for fila in filas:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _csv_en_memoria(texto: str, encoding: str = "utf-8") -> io.BytesIO:
    buf = io.BytesIO(texto.encode(encoding))
    buf.seek(0)
    return buf


def _dxf_bytesio(layers_con_geometria: list[str], layers_vacios: list[str] | None = None) -> io.BytesIO:
    """
    Crea un DXF válido con ezdxf: una LINE por cada layer con geometría
    y un TEXT de anotación con ID de pieza en 0_ANOTACIONES.
    Devuelve BytesIO codificado en CP1252 (como Rhino).
    """
    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()

    for layer in layers_con_geometria:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line((0, 0), (100, 0), dxfattribs={"layer": layer})

    for layer in (layers_vacios or []):
        if layer not in doc.layers:
            doc.layers.add(layer)

    # Anotación de pieza en el layer estándar
    if "0_ANOTACIONES" not in doc.layers:
        doc.layers.add("0_ANOTACIONES")
    msp.add_text(
        "598x798 / M2-P1",
        dxfattribs={"layer": "0_ANOTACIONES", "height": 5},
    )

    # ezdxf escribe en texto (no binario para DXF ASCII)
    stream = io.StringIO()
    doc.write(stream)
    contenido = stream.getvalue()

    buf = io.BytesIO(contenido.encode("cp1252", errors="replace"))
    buf.seek(0)
    return buf


# ===========================================================================
# Tests de modelos
# ===========================================================================

class TestCheckResult:

    def test_pass_valido(self):
        """PASS: CheckResult con resultado PASS se construye sin error."""
        cr = CheckResult("C-00", "Test", "PASS", "ok", False, "Inventario")
        assert cr.resultado == "PASS"
        assert not cr.es_error_critico
        assert not cr.es_advertencia

    def test_fail_bloqueante(self):
        """PASS: FAIL con bloquea=True → es_error_critico=True."""
        cr = CheckResult("C-15", "Material", "FAIL", "PLY+LAC", True, "Material")
        assert cr.es_error_critico

    def test_fail_no_bloqueante(self):
        """PASS: FAIL con bloquea=False NO es error crítico."""
        cr = CheckResult("C-16", "Acabado", "FAIL", "x", False, "Material")
        assert not cr.es_error_critico

    def test_warn_es_advertencia(self):
        """PASS: WARN → es_advertencia=True."""
        cr = CheckResult("C-43", "Layer desuso", "WARN", "x", False, "DXF")
        assert cr.es_advertencia

    def test_resultado_invalido_lanza_error(self):
        """FAIL: resultado desconocido → ValueError."""
        with pytest.raises(ValueError, match="resultado inválido"):
            CheckResult("C-00", "x", "QUIZAS", "x", False, "Inventario")

    def test_grupo_invalido_lanza_error(self):
        """FAIL: grupo desconocido → ValueError."""
        with pytest.raises(ValueError, match="grupo inválido"):
            CheckResult("C-00", "x", "PASS", "x", False, "Inventado")


class TestInformeFinal:

    def _informe(self, checks: list[CheckResult]) -> InformeFinal:
        inf = InformeFinal("EU-99999", "Test", "Esteban", "Semana 18")
        inf.checks = checks
        return inf

    def test_aprobado_sin_errores(self):
        cr = CheckResult("C-00", "x", "PASS", "ok", False, "Inventario")
        assert self._informe([cr]).estado_global == "APROBADO"

    def test_bloqueado_con_fail_bloqueante(self):
        cr = CheckResult("C-15", "x", "FAIL", "error", True, "Material")
        assert self._informe([cr]).estado_global == "BLOQUEADO"

    def test_advertencias_solo_warn(self):
        cr = CheckResult("C-43", "x", "WARN", "aviso", False, "DXF")
        assert self._informe([cr]).estado_global == "ADVERTENCIAS"

    def test_bloqueado_tiene_prioridad_sobre_warn(self):
        cr_fail = CheckResult("C-15", "x", "FAIL", "error", True, "Material")
        cr_warn = CheckResult("C-43", "x", "WARN", "aviso", False, "DXF")
        assert self._informe([cr_fail, cr_warn]).estado_global == "BLOQUEADO"


class TestPieza:

    def test_tiene_tirador_true(self):
        p = Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P", tirador="Round")
        assert p.tiene_tirador

    def test_tiene_tirador_false(self):
        p = Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P")
        assert not p.tiene_tirador

    def test_clave_material(self):
        p = Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P")
        assert p.clave_material == "PLY_LAM_Pale"

    def test_apertura_i_valida(self):
        p = Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P", apertura="I")
        assert p.tiene_apertura

    def test_apertura_vacia_no_valida(self):
        p = Pieza("M1-P1", 400, 798, "PLY", "LAM", "Pale", "P", apertura="")
        assert not p.tiene_apertura


# ===========================================================================
# Tests de extractor_despiece
# ===========================================================================

class TestInferirTipologia:

    @pytest.mark.parametrize("id_pieza,mec,esperado", [
        ("E1", "", "E"),
        ("E12", "", "E"),
        ("B3", "", "B"),
        ("R1", "", "R"),
        ("R1", "vent.", "RV"),
        ("H2", "", "H"),
        ("M2-P1", "", "P"),
        ("M4-C2", "", "C"),
        ("M4-PL1", "", "L"),
        ("M1-T1", "", "T"),
    ])
    def test_inferencia_correcta(self, id_pieza, mec, esperado):
        """PASS: tipología inferida correctamente para patrones estándar."""
        assert _inferir_tipologia(id_pieza, mec) == esperado


class TestLeerDespiece:

    def _xlsx_basico(self) -> io.BytesIO:
        return _xlsx_en_memoria([
            ["ID", "Ancho", "Alto", "Material", "Gama", "Acabado",
             "Mecanizado", "Tirador", "Posición tirador", "Color tirador", "Apertura"],
            ["M1-P1", 400, 798, "PLY", "LAM", "Pale",  "cazta.", "Round", "3", "Cerezo", "D"],
            ["M1-C1", 400, 200, "PLY", "LAM", "Pale",  "torn.",  "Round", "2", "Cerezo", ""],
            ["E1",    600, 200, "MDF", "LAC", "Blanco", "",       "",      "",  "",        ""],
            ["R1",    100, 80,  "PLY", "LAM", "Pale",  "",       "",      "",  "",        ""],
        ])

    def test_lee_piezas_correctamente(self):
        """PASS: devuelve lista de Pieza con los campos del XLSX."""
        piezas = leer_despiece(self._xlsx_basico())
        assert len(piezas) == 4
        p0 = piezas[0]
        assert p0.id == "M1-P1"
        assert p0.ancho == 400
        assert p0.alto == 798
        assert p0.material == "PLY"
        assert p0.gama == "LAM"
        assert p0.acabado == "Pale"
        assert p0.tirador == "Round"
        assert p0.apertura == "D"

    def test_tipologia_inferida_si_falta_columna(self):
        """PASS: sin columna Tipología se infiere correctamente."""
        piezas = leer_despiece(self._xlsx_basico())
        tipos = {p.id: p.tipologia for p in piezas}
        assert tipos["M1-P1"] == "P"
        assert tipos["M1-C1"] == "C"
        assert tipos["E1"] == "E"
        assert tipos["R1"] == "R"

    def test_filas_sin_id_se_ignoran(self):
        """PASS: filas sin ID (vacías o de total) no se incluyen."""
        buf = _xlsx_en_memoria([
            ["ID", "Ancho", "Alto", "Material", "Gama", "Acabado"],
            ["M1-P1", 400, 798, "PLY", "LAM", "Pale"],
            ["",      "",   "",  "",    "",    ""],
            ["Total", "",   "",  "",    "",    ""],
        ])
        piezas = leer_despiece(buf)
        assert len(piezas) == 1

    def test_cabecera_con_tildes_funciona(self):
        """PASS: columna 'Posición' con tilde se normaliza correctamente."""
        buf = _xlsx_en_memoria([
            ["ID", "Ancho", "Alto", "Material", "Gama", "Acabado", "Posición tirador"],
            ["M1-P1", 400, 798, "PLY", "LAM", "Pale", "3"],
        ])
        piezas = leer_despiece(buf)
        assert piezas[0].posicion_tirador == "3"

    def test_sin_columnas_obligatorias_lanza_error(self):
        """FAIL: XLSX sin columna 'ID' → ValueError."""
        buf = _xlsx_en_memoria([
            ["Referencia_Falsa", "Dimensión"],
            ["M1-P1", 400],
        ])
        with pytest.raises(ValueError, match="columnas obligatorias"):
            leer_despiece(buf)

    def test_xlsx_vacio_lanza_error(self):
        """FAIL: XLSX sin filas → ValueError."""
        buf = _xlsx_en_memoria([])
        with pytest.raises(ValueError, match="vacío"):
            leer_despiece(buf)

    def test_desde_path(self, tmp_path):
        """PASS: acepta Path además de BytesIO."""
        buf = self._xlsx_basico()
        ruta = tmp_path / "DESPIECE_EU-test.xlsx"
        ruta.write_bytes(buf.read())
        piezas = leer_despiece(ruta)
        assert len(piezas) == 4


# ===========================================================================
# Tests de extractor_etiquetas_ean
# ===========================================================================

class TestLeerEtiquetas:

    def _csv_etiquetas(self, sep: str = ";") -> io.BytesIO:
        contenido = sep.join(["ID", "Ancho", "Alto", "Material", "Gama", "Acabado"]) + "\n"
        contenido += sep.join(["M1-P1", "400", "798", "PLY", "LAM", "Pale"]) + "\n"
        contenido += sep.join(["M1-C1", "400", "200", "PLY", "LAM", "Pale"]) + "\n"
        contenido += sep.join(["E1",    "600", "200", "MDF", "LAC", "Blanco"]) + "\n"
        return _csv_en_memoria(contenido)

    def test_lee_filas_correctamente(self):
        """PASS: devuelve una FilaEtiqueta por fila válida."""
        etiquetas = leer_etiquetas(self._csv_etiquetas())
        assert len(etiquetas) == 3
        assert etiquetas[0].id == "M1-P1"
        assert etiquetas[0].ancho == 400
        assert etiquetas[0].acabado == "Pale"

    def test_separador_coma_funciona(self):
        """PASS: CSV con coma como separador."""
        etiquetas = leer_etiquetas(self._csv_etiquetas(sep=","))
        assert len(etiquetas) == 3

    def test_encoding_utf8_bom(self):
        """PASS: CSV con BOM UTF-8."""
        contenido = "ID;Ancho;Alto;Material;Gama;Acabado\nM1-P1;400;798;PLY;LAM;Pale\n"
        buf = io.BytesIO(contenido.encode("utf-8-sig"))
        buf.seek(0)
        etiquetas = leer_etiquetas(buf)
        assert etiquetas[0].id == "M1-P1"

    def test_csv_vacio_lanza_error(self):
        """FAIL: CSV vacío → ValueError."""
        with pytest.raises(ValueError, match="vacío"):
            leer_etiquetas(_csv_en_memoria(""))

    def test_filas_sin_id_se_ignoran(self):
        """PASS: filas con ID vacío no se incluyen."""
        contenido = "ID;Ancho;Alto\nM1-P1;400;798\n;200;100\n"
        etiquetas = leer_etiquetas(_csv_en_memoria(contenido))
        assert len(etiquetas) == 1


class TestLeerEAN:

    def _csv_ean(self) -> io.BytesIO:
        contenido = (
            "ID Bulto;ID Pieza;Peso\n"
            "CUB-EU-21822-1-3;M1-P1;12.5\n"
            "CUB-EU-21822-1-3;M1-C1;8.0\n"
            "CUB-EU-21822-2-3;E1;15.0\n"
            "CUB-EU-21822-3-3;R1;5.0\n"
        )
        return _csv_en_memoria(contenido)

    def test_lee_filas_correctamente(self):
        """PASS: devuelve una FilaEAN por pieza asignada."""
        filas = leer_ean(self._csv_ean())
        assert len(filas) == 4

    def test_extrae_numero_y_total_del_id_bulto(self):
        """PASS: número y total se extraen del ID bulto (CUB-X-N-TOTAL)."""
        filas = leer_ean(self._csv_ean())
        assert filas[0].numero_bulto == 1
        assert filas[0].total_bultos == 3
        assert filas[2].numero_bulto == 2

    def test_ids_piezas_correctos(self):
        """PASS: id_pieza extraído correctamente por fila."""
        filas = leer_ean(self._csv_ean())
        ids = [f.id_pieza for f in filas]
        assert ids == ["M1-P1", "M1-C1", "E1", "R1"]

    def test_filas_sin_bulto_o_pieza_se_ignoran(self):
        """PASS: filas con id_bulto o id_pieza vacío no se incluyen."""
        contenido = (
            "ID Bulto;ID Pieza;Peso\n"
            "CUB-EU-21822-1-2;M1-P1;12.5\n"
            ";M1-C1;8.0\n"
            "CUB-EU-21822-2-2;;5.0\n"
        )
        filas = leer_ean(_csv_en_memoria(contenido))
        assert len(filas) == 1

    def test_sin_filas_validas_lanza_error(self):
        """FAIL: CSV con solo cabecera → ValueError."""
        with pytest.raises(ValueError, match="no se encontraron filas válidas"):
            leer_ean(_csv_en_memoria("ID Bulto;ID Pieza;Peso\n"))


# ===========================================================================
# Tests de extractor_dxf
# ===========================================================================

class TestLeerDXF:

    def _bytesio_dxf(self, layers_geo: list[str], layers_vacios: list[str] | None = None) -> io.BytesIO:
        return _dxf_bytesio(layers_geo, layers_vacios)

    def test_layers_con_geometria_detectados(self):
        """PASS: layers con LINE están en layers_con_geometria."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL", "0_ANOTACIONES"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf")
        assert "CONTROL" in doc.layers_con_geometria

    def test_layers_vacios_en_layers_no_en_con_geometria(self):
        """PASS: layers sin entidades no están en layers_con_geometria."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL"], ["LAYER_VACIO"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf")
        assert "LAYER_VACIO" in doc.layers
        assert "LAYER_VACIO" not in doc.layers_con_geometria

    def test_extrae_material_del_nombre(self):
        """PASS: PLY/MDF extraídos del nombre del archivo."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL"])
        doc = leer_dxf(buf, nombre="EU21822_Sabine_Jennes_PLY_LAMINADO_PALE_T1.dxf")
        assert doc.material == "PLY"
        assert doc.gama == "LAM"

    def test_extrae_numero_tablero_del_nombre(self):
        """PASS: _T3.dxf → tablero_num=3."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T3.dxf")
        assert doc.tablero_num == 3

    def test_extrae_id_pieza_de_anotacion(self):
        """PASS: texto '598x798 / M2-P1' en 0_ANOTACIONES → 'M2-P1' en ids_piezas."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL", "0_ANOTACIONES"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf")
        assert "M2-P1" in doc.ids_piezas

    def test_nombre_sin_patron_deja_material_vacio(self):
        """FAIL semántico: nombre sin patrón → material/gama vacíos, detectable por checks."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL"])
        doc = leer_dxf(buf, nombre="archivo_sin_patron.dxf")
        assert doc.material == ""
        assert doc.tablero_num == 0

    def test_conteos_layer_correcto(self):
        """PASS: conteos_layer reporta nº de entidades por layer."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL", "0_ANOTACIONES"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf")
        assert "CONTROL" in doc.conteos_layer
        assert doc.conteos_layer["CONTROL"] >= 1

    def test_leer_todos_dxf_ordena_por_nombre_y_tablero(self):
        """PASS: lista ordenada coherentemente."""
        from core.extractor_dxf import leer_todos_dxf
        buf1 = self._bytesio_dxf(["CONTROL"])
        buf2 = self._bytesio_dxf(["CONTROL"])
        resultado = leer_todos_dxf({
            "EU21822_X_PLY_LAMINADO_PALE_T2.dxf": buf1,
            "EU21822_X_PLY_LAMINADO_PALE_T1.dxf": buf2,
        })
        assert resultado[0].nombre.endswith("T1.dxf")
        assert resultado[1].nombre.endswith("T2.dxf")

    def test_ignora_no_dxf_en_dict(self):
        """PASS: archivos que no son .dxf se ignoran en leer_todos_dxf."""
        from core.extractor_dxf import leer_todos_dxf
        buf_dxf = self._bytesio_dxf(["CONTROL"])
        resultado = leer_todos_dxf({
            "EU21822_X_PLY_LAMINADO_PALE_T1.dxf": buf_dxf,
            "DESPIECE_EU21822.xlsx": io.BytesIO(b"no dxf"),
        })
        assert len(resultado) == 1


# ===========================================================================
# Tests de extractor_ot
# ===========================================================================

class TestLeerOT:

    def _pdf_mock(self, texto: str):
        """Mock de pdfplumber que devuelve texto fijo."""
        pagina = MagicMock()
        pagina.extract_text.return_value = texto
        pdf = MagicMock()
        pdf.pages = [pagina]
        pdf.__enter__ = lambda s: s
        pdf.__exit__ = MagicMock(return_value=False)
        return pdf

    def test_extrae_id_proyecto(self):
        """PASS: EU-21822 extraído del texto."""
        texto = "Proyecto: EU-21822  Cliente: Sabine Jennes\nSemana 18"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"irrelevante"))
        assert ot.id_proyecto == "EU-21822"

    def test_extrae_sp_con_inc(self):
        """PASS: SP-21493-INC también se reconoce como ID de proyecto."""
        texto = "Proyecto: SP-21493-INC  Cliente: Belen Duenas"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"irrelevante"))
        assert ot.id_proyecto == "SP-21493-INC"

    def test_extrae_num_piezas(self):
        """PASS: 'Total piezas: 24' extraído."""
        texto = "EU-21822\nTotal piezas: 24\nPeso total: 125,4 kg"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.num_piezas == 24

    def test_extrae_peso_total(self):
        """PASS: 'Peso total: 125,4 kg' → 125.4."""
        texto = "EU-21822\nPeso total: 125,4 kg"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.peso_total_kg == pytest.approx(125.4, abs=0.01)

    def test_extrae_semana(self):
        """PASS: 'Semana 18' extraído."""
        texto = "EU-21822\nSemana 18\nTotal piezas: 10"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert "18" in ot.semana

    def test_extrae_tiradores(self):
        """PASS: 'Tiradores: 8' extraído."""
        texto = "EU-21822\nTiradores: 8"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.num_tiradores == 8

    def test_extrae_tiradores_multi_material(self):
        """PASS: '# Tiradores 8 6 12' (una columna por material) → suma 26."""
        texto = "EU-22467\n# Tiradores 8 6 12\n"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.num_tiradores == 26

    def test_extrae_tableros(self):
        """PASS: línea 'PLY LAM Pale: 3' → tableros['PLY_LAM_Pale']=3."""
        texto = "EU-21822\nPLY LAM Pale: 3\nMDF LAC Blanco: 2"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.tableros.get("PLY_LAM_Pale") == 3
        assert ot.tableros.get("MDF_LAC_Blanco") == 2

    def test_extrae_observaciones_cnc(self):
        """PASS: bloque bajo 'Observaciones CNC' capturado por líneas."""
        texto = (
            "EU-21822\n"
            "Observaciones CNC:\n"
            "retal de PLY LAM Pale\n"
            "sin mecanizar\n\n"
            "Observaciones producción:\nnada\n"
        )
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert "retal de PLY LAM Pale" in ot.observaciones_cnc
        assert "sin mecanizar" in ot.observaciones_cnc

    def test_campos_vacios_si_pdf_no_tiene_datos(self):
        """FAIL semántico: PDF sin info → valores por defecto, no excepción."""
        texto = "Texto sin estructura reconocible"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.id_proyecto == ""
        assert ot.num_piezas == 0
        assert ot.tableros == {}
        assert ot.observaciones_cnc == []
