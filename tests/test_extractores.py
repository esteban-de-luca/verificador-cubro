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
        # Sueltos clásicos
        ("E1", "", "E"),
        ("E12", "", "E"),
        ("B3", "", "B"),
        ("R1", "", "R"),
        ("R1", "vent.", "RV"),
        ("H2", "", "H"),
        # Sueltos nuevos
        ("T1", "", "T"),
        ("T15", "", "T"),
        ("PL1", "", "L"),
        ("PL3", "", "L"),
        ("FE1", "", "FE"),
        ("FE2", "", "FE"),
        ("F1", "", "F"),
        ("F8", "", "F"),
        ("P1", "", "P"),    # Puerta suelta — se valida como P
        ("P8", "", "P"),
        # Prefijo M{n}- (Mueble METOD)
        ("M2-P1", "", "P"),
        ("M4-C2", "", "C"),
        ("M4-PL1", "", "L"),
        ("M3-L1", "", "L"),
        ("M1-T1", "", "T"),
        ("M1-TBE1", "", "TBE"),
        # Prefijo P{n}- (Armario PAX)
        ("P1-P1", "", "X"),     # Puerta PAX
        ("P3-P2", "", "X"),
        ("P1-T1", "", "T"),     # Tapeta PAX
        ("P3-T1", "", "T"),
        ("P1-PL1", "", "L"),    # Panel lateral PAX
        ("P2-L1", "", "L"),
        # Fallback: IDs no reconocidos → cadena vacía
        ("XYZ123", "", ""),
        ("A1", "", ""),
        ("M1-Q1", "", ""),      # sufijo desconocido
        ("M1-X1", "", ""),      # M{n}-X{n} no existe en CUBRO
        ("P1-X1", "", ""),      # sufijo X tras P{n}- tampoco
    ])
    def test_inferencia_correcta(self, id_pieza, mec, esperado):
        """PASS: tipología inferida correctamente para todos los patrones."""
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

    def test_layers_vacios_no_se_incluyen(self):
        """PASS: layers declarados en la tabla LAYER del DXF pero sin
        entidades quedan fuera de doc.layers (solo se cuentan los usados)."""
        from core.extractor_dxf import leer_dxf
        buf = self._bytesio_dxf(["CONTROL"], ["LAYER_VACIO"])
        doc = leer_dxf(buf, nombre="EU21822_X_PLY_LAMINADO_PALE_T1.dxf")
        assert "LAYER_VACIO" not in doc.layers
        assert "LAYER_VACIO" not in doc.layers_con_geometria
        assert "CONTROL" in doc.layers

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


class TestLeerDXFContornosPieza:
    """Tests del parser de polilíneas para extraer contornos de pieza (C-44)."""

    def _dxf_con_polilineas(self, polilineas: list[tuple[str, str, list[tuple[float, float]]]]) -> io.BytesIO:
        """
        Construye un DXF con las polilíneas dadas.

        Args:
            polilineas: lista de (tipo, layer, vertices) donde
                        tipo ∈ {"polyline", "lwpolyline"}.
        """
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        for tipo, layer, vertices in polilineas:
            if layer not in doc.layers:
                doc.layers.add(layer)
            if tipo == "polyline":
                msp.add_polyline2d(vertices, dxfattribs={"layer": layer})
            elif tipo == "lwpolyline":
                msp.add_lwpolyline(vertices, dxfattribs={"layer": layer})
            else:
                raise ValueError(f"tipo desconocido: {tipo}")
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)
        return buf

    def test_polyline_cutext_extrae_bbox(self):
        """PASS: POLYLINE2D en layer CUTEXT → bbox correcto en piezas_contorno."""
        from core.extractor_dxf import leer_dxf
        buf = self._dxf_con_polilineas([
            ("polyline", "10_12-CUTEXT-EM5-Z18",
             [(10.0, -27510.0), (2360.0, -27510.0),
              (2360.0, -27756.0), (10.0, -27756.0)]),
        ])
        doc = leer_dxf(buf, nombre="EU21742_X_MDF_WOOD_ROBLE_T11.dxf")
        assert len(doc.piezas_contorno) == 1
        c = doc.piezas_contorno[0]
        assert c["layer"] == "10_12-CUTEXT-EM5-Z18"
        assert c["xmin"] == pytest.approx(10.0)
        assert c["xmax"] == pytest.approx(2360.0)
        assert c["ymin"] == pytest.approx(-27756.0)
        assert c["ymax"] == pytest.approx(-27510.0)

    def test_lwpolyline_contorno_laca_extrae_bbox(self):
        """PASS: LWPOLYLINE en layer CONTORNO LACA → bbox correcto."""
        from core.extractor_dxf import leer_dxf
        buf = self._dxf_con_polilineas([
            ("lwpolyline", "10_12-CONTORNO LACA",
             [(2375.0, -27510.0), (2851.0, -27510.0),
              (2851.0, -27756.0), (2375.0, -27756.0)]),
        ])
        doc = leer_dxf(buf, nombre="EU21742_X_MDF_LACA_AGAVE_T1.dxf")
        assert len(doc.piezas_contorno) == 1
        c = doc.piezas_contorno[0]
        assert c["layer"] == "10_12-CONTORNO LACA"
        assert c["xmin"] == pytest.approx(2375.0)
        assert c["xmax"] == pytest.approx(2851.0)

    def test_polilineas_de_otras_layers_se_ignoran(self):
        """PASS: polilíneas en layers no-contorno NO entran en piezas_contorno."""
        from core.extractor_dxf import leer_dxf
        buf = self._dxf_con_polilineas([
            ("polyline", "9_11-HANDCUT-EM5-Z18",
             [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)]),
        ])
        doc = leer_dxf(buf, nombre="EU21742_X_MDF_WOOD_ROBLE_T1.dxf")
        assert doc.piezas_contorno == []

    def test_dxf_sin_polilineas_devuelve_lista_vacia(self):
        """PASS: DXF sin polilíneas → piezas_contorno vacía."""
        from core.extractor_dxf import leer_dxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        msp.add_circle((100, 100), radius=10,
                       dxfattribs={"layer": "7-POCKET-EM5-Z14"})
        if "7-POCKET-EM5-Z14" not in doc.layers:
            doc.layers.add("7-POCKET-EM5-Z14")
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)

        from core.extractor_dxf import leer_dxf as leer_dxf_fn
        d = leer_dxf_fn(buf, nombre="EU21742_X_PLY_LAMINADO_PALE_T1.dxf")
        assert d.piezas_contorno == []

    def test_multiples_contornos_en_un_dxf(self):
        """PASS: 2 piezas en el mismo tablero → 2 bboxes en piezas_contorno."""
        from core.extractor_dxf import leer_dxf
        buf = self._dxf_con_polilineas([
            ("polyline", "10_12-CUTEXT-EM5-Z18",
             [(10.0, -27510.0), (2360.0, -27510.0),
              (2360.0, -27756.0), (10.0, -27756.0)]),
            ("lwpolyline", "10_12-CUTEXT-EM5-Z18",
             [(2375.0, -27510.0), (2851.0, -27510.0),
              (2851.0, -27756.0), (2375.0, -27756.0)]),
        ])
        doc = leer_dxf(buf, nombre="EU21742_X_MDF_WOOD_ROBLE_T11.dxf")
        assert len(doc.piezas_contorno) == 2
        # ordenamos para no depender de orden de inserción
        anchuras = sorted(c["xmax"] - c["xmin"] for c in doc.piezas_contorno)
        assert anchuras[0] == pytest.approx(476.0)
        assert anchuras[1] == pytest.approx(2350.0)

    def test_circulo_extrusion_negativa_aplica_arbitrary_axis(self):
        """PASS: CIRCLE con extrusion=(0,0,-1) → coordenada X invertida (X→-X)
        en el sistema WCS. CUBRO usa esto para piezas de la cara trasera."""
        from core.extractor_dxf import leer_dxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        if "7-POCKET-EM5-Z14" not in doc.layers:
            doc.layers.add("7-POCKET-EM5-Z14")
        # Cazoleta dibujada en OCS a X=869.5 con extrusion Z=-1
        # → posición física en WCS: X = -869.5
        msp.add_circle(
            (869.5, -9377.0), radius=17.5,
            dxfattribs={"layer": "7-POCKET-EM5-Z14", "extrusion": (0, 0, -1)},
        )
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)

        d = leer_dxf(buf, nombre="EU21119_X_MDF_WOOD_CEREZO_T1.dxf")
        assert len(d.circulos) == 1
        # El círculo se extrae con X invertida (Arbitrary Axis Algorithm)
        assert d.circulos[0]["x"] == pytest.approx(-869.5)
        assert d.circulos[0]["y"] == pytest.approx(-9377.0)

    def test_polilinea_extrusion_negativa_aplica_arbitrary_axis(self):
        """PASS: POLYLINE/LWPOLYLINE con extrusion Z=-1 → vértices X invertidos
        antes de calcular bbox. Permite asociar cazoletas de cara trasera al
        contorno de su pieza."""
        from core.extractor_dxf import leer_dxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        if "10_12-CUTEXT-EM5-Z18" not in doc.layers:
            doc.layers.add("10_12-CUTEXT-EM5-Z18")
        # CUTEXT en OCS con extrusion Z=-1: X 820.5..1618.5 → WCS X -1618.5..-820.5
        msp.add_lwpolyline(
            [(820.5, -9400.5), (1618.5, -9400.5),
             (1618.5, -9202.5), (820.5, -9202.5)],
            dxfattribs={"layer": "10_12-CUTEXT-EM5-Z18", "extrusion": (0, 0, -1)},
        )
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)

        d = leer_dxf(buf, nombre="EU21119_X_MDF_WOOD_CEREZO_T1.dxf")
        assert len(d.piezas_contorno) == 1
        c = d.piezas_contorno[0]
        # X de OCS [820.5, 1618.5] → WCS [-1618.5, -820.5]
        assert c["xmin"] == pytest.approx(-1618.5)
        assert c["xmax"] == pytest.approx(-820.5)
        assert c["ymin"] == pytest.approx(-9400.5)
        assert c["ymax"] == pytest.approx(-9202.5)

    def test_cazoleta_y_cutext_z_negativo_se_asocian_correctamente(self):
        """Regresión EU-21119: cazoleta con Z=-1 dentro de CUTEXT con Z=-1
        debe asociarse a esa pieza tras la transformación WCS. Antes del fix,
        las cazoletas Z=-1 se filtraban y se reportaban falsos positivos
        de tipo 'pieza con 1 sola bisagra'."""
        from core.extractor_dxf import leer_dxf
        from core.reglas_loader import cargar_reglas
        from checks.checks_dxf import check_distancia_bisagras

        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        for layer in ("7-POCKET-EM5-Z14", "6-POCKET-EM5-Z14",
                      "10_12-CUTEXT-EM5-Z18"):
            if layer not in doc.layers:
                doc.layers.add(layer)
        # Pieza 798×198mm en cara trasera (extrusion Z=-1).
        # 2 bisagras METOD: una a 49 mm de xmin (X=869.5) y otra a 149 mm de
        # xmax (X=1469.5). Distancia 600 mm = 12×50 ✓.
        ext_neg = {"extrusion": (0, 0, -1)}
        msp.add_lwpolyline(
            [(820.5, -9400.5), (1618.5, -9400.5),
             (1618.5, -9202.5), (820.5, -9202.5)],
            dxfattribs={"layer": "10_12-CUTEXT-EM5-Z18", **ext_neg},
        )
        # Cazoletas (radio 17.5) y companions METOD (radio 4.0)
        for cx in (869.5, 1469.5):
            msp.add_circle((cx, -9377.0), radius=17.5,
                           dxfattribs={"layer": "7-POCKET-EM5-Z14", **ext_neg})
            for off in (-22.5, 22.5):
                msp.add_circle((cx + off, -9367.5), radius=4.0,
                               dxfattribs={"layer": "6-POCKET-EM5-Z14", **ext_neg})
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)

        d = leer_dxf(buf, nombre="EU21119_X_MDF_WOOD_CEREZO_T1.dxf")
        # Tras transformación WCS, todo está en X negativo pero coherente:
        # las 2 cazoletas caen dentro del CUTEXT.
        reglas = cargar_reglas(ROOT / "reglas.yaml")
        r = check_distancia_bisagras([d], reglas)
        assert r.resultado == "PASS", r.detalle

    def test_circulos_y_polilineas_coexisten(self):
        """PASS: extractor procesa círculos y polilíneas en el mismo DXF
        sin que uno corrompa al otro (regresión: el parser maneja la
        transición POLYLINE→VERTEX→SEQEND→CIRCLE correctamente)."""
        from core.extractor_dxf import leer_dxf
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()
        for layer in ("10_12-CUTEXT-EM5-Z18", "7-POCKET-EM5-Z14"):
            if layer not in doc.layers:
                doc.layers.add(layer)
        msp.add_polyline2d(
            [(0.0, 0.0), (1000.0, 0.0), (1000.0, 500.0), (0.0, 500.0)],
            dxfattribs={"layer": "10_12-CUTEXT-EM5-Z18"},
        )
        msp.add_circle((250.0, 250.0), radius=17.5,
                       dxfattribs={"layer": "7-POCKET-EM5-Z14"})
        msp.add_circle((750.0, 250.0), radius=17.5,
                       dxfattribs={"layer": "7-POCKET-EM5-Z14"})
        stream = io.StringIO()
        doc.write(stream)
        buf = io.BytesIO(stream.getvalue().encode("cp1252", errors="replace"))
        buf.seek(0)

        d = leer_dxf(buf, nombre="EU21742_X_MDF_WOOD_ROBLE_T1.dxf")
        assert len(d.piezas_contorno) == 1
        assert len(d.circulos) == 2
        assert d.piezas_contorno[0]["xmax"] == pytest.approx(1000.0)
        assert {(c["x"], c["y"]) for c in d.circulos} == {(250.0, 250.0), (750.0, 250.0)}


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
        """PASS: tabla INFORMACION DE CORTE columnar parseada correctamente."""
        texto = (
            "EU-21822\n"
            "INFORMACION DE CORTE\n"
            "Tablero base PLY MDF\n"
            "Gama Laminado Laca\n"
            "Acabado Pale Blanco\n"
            "# Tableros 3 2\n"
        )
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

    def test_observaciones_cnc_descarta_cabeceras_pagina(self):
        """OBSERVACIONES CNC vacía + salto de página: la cabecera repetida
        (ID, cliente, ORDEN DE TRABAJO) se descarta y no contamina obs_cnc."""
        texto = (
            "EU-21731\n"
            "Solenn Nunes\n"
            "ORDEN DE TRABAJO\n"
            "OBSERVACIONES CNC\n"
            "EU-21731\n"
            "Solenn Nunes\n"
            "ORDEN DE TRABAJO\n"
            "PACKING LIST\n"
        )
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.observaciones_cnc == []

    def test_campos_vacios_si_pdf_no_tiene_datos(self):
        """FAIL semántico: PDF sin info → valores por defecto, no excepción."""
        texto = "Texto sin estructura reconocible"
        with patch("core.extractor_ot.pdfplumber.open", return_value=self._pdf_mock(texto)):
            ot = leer_ot(io.BytesIO(b"x"))
        assert ot.id_proyecto == ""
        assert ot.num_piezas == 0
        assert ot.tableros == {}
        assert ot.observaciones_cnc == []
