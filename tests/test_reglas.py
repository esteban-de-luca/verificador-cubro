"""
tests/test_reglas.py

Valida la integridad estructural de reglas.yaml y reglas_cnc.yaml.
Ejecutar: pytest tests/test_reglas.py -v

Cada test tiene al menos un caso PASS y un caso FAIL.
"""

from __future__ import annotations

import copy
import textwrap
from pathlib import Path

import pytest
import yaml

# Raíz del proyecto = directorio padre de tests/
ROOT = Path(__file__).parent.parent
REGLAS_PATH = ROOT / "reglas.yaml"
REGLAS_CNC_PATH = ROOT / "reglas_cnc.yaml"

# Importar desde core/ (ajustar sys.path si no hay package instalado)
import sys
sys.path.insert(0, str(ROOT))
from core.reglas_loader import cargar_reglas, cargar_reglas_cnc


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(REGLAS_PATH)


@pytest.fixture(scope="session")
def reglas_cnc():
    return cargar_reglas_cnc(REGLAS_CNC_PATH)


# ===========================================================================
# Tests de carga básica
# ===========================================================================

class TestCargaBasica:

    def test_reglas_yaml_carga_sin_error(self):
        """PASS: el archivo existe y tiene estructura válida."""
        datos = cargar_reglas(REGLAS_PATH)
        assert isinstance(datos, dict)

    def test_reglas_cnc_yaml_carga_sin_error(self):
        """PASS: el archivo existe y tiene estructura válida."""
        datos = cargar_reglas_cnc(REGLAS_CNC_PATH)
        assert isinstance(datos, dict)

    def test_archivo_inexistente_lanza_error(self, tmp_path):
        """FAIL: archivo que no existe → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            cargar_reglas(tmp_path / "no_existe.yaml")

    def test_yaml_raiz_no_dict_lanza_error(self, tmp_path):
        """FAIL: YAML cuya raíz es una lista → ValueError."""
        yaml_invalido = tmp_path / "reglas_invalido.yaml"
        yaml_invalido.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ValueError, match="mapping YAML"):
            cargar_reglas(yaml_invalido)


# ===========================================================================
# Tests de secciones obligatorias
# ===========================================================================

class TestSeccionesObligatorias:

    _SECCIONES = [
        "materiales", "acabados", "cazoletas_metod",
        "puerta_alturas_estandar", "baldas_dimensiones",
        "layers", "desbaste_tirador", "tiradores_con_geometria_dxf",
        "tipologias", "logistica", "nomenclatura",
    ]

    @pytest.mark.parametrize("seccion", _SECCIONES)
    def test_seccion_presente(self, reglas, seccion):
        """PASS: cada sección obligatoria existe en reglas.yaml."""
        assert seccion in reglas, f"Falta sección: {seccion}"

    @pytest.mark.parametrize("seccion", _SECCIONES)
    def test_seccion_ausente_lanza_error(self, tmp_path, seccion):
        """FAIL: quitar una sección obligatoria → ValueError."""
        datos = yaml.safe_load(REGLAS_PATH.read_text(encoding="utf-8"))
        del datos[seccion]
        yaml_roto = tmp_path / "reglas_roto.yaml"
        yaml_roto.write_text(yaml.dump(datos, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError):
            cargar_reglas(yaml_roto)


# ===========================================================================
# Tests de materiales (C-15)
# ===========================================================================

class TestMateriales:

    def test_ply_gamas_validas_son_lam_y_lin(self, reglas):
        """PASS: PLY acepta LAM y LIN."""
        gamas = reglas["materiales"]["PLY"]["gamas_validas"]
        assert set(gamas) == {"LAM", "LIN"}

    def test_mdf_gamas_validas_son_lac_y_woo(self, reglas):
        """PASS: MDF acepta LAC y WOO."""
        gamas = reglas["materiales"]["MDF"]["gamas_validas"]
        assert set(gamas) == {"LAC", "WOO"}

    def test_ply_no_acepta_lac(self, reglas):
        """FAIL semántico: LAC no debe estar en gamas_validas de PLY."""
        gamas = reglas["materiales"]["PLY"]["gamas_validas"]
        assert "LAC" not in gamas

    def test_mdf_no_acepta_lam(self, reglas):
        """FAIL semántico: LAM no debe estar en gamas_validas de MDF."""
        gamas = reglas["materiales"]["MDF"]["gamas_validas"]
        assert "LAM" not in gamas

    def test_espesores_definidos(self, reglas):
        """PASS: todos los tableros tienen espesores_mm definidos."""
        for tablero, config in reglas["materiales"].items():
            assert "espesores_mm" in config, f"{tablero} sin espesores_mm"
            assert isinstance(config["espesores_mm"], dict)

    def test_materiales_sin_gamas_validas_lanza_error(self, tmp_path):
        """FAIL: material sin gamas_validas → ValueError."""
        datos = yaml.safe_load(REGLAS_PATH.read_text(encoding="utf-8"))
        del datos["materiales"]["PLY"]["gamas_validas"]
        yaml_roto = tmp_path / "reglas_roto.yaml"
        yaml_roto.write_text(yaml.dump(datos, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError, match="gamas_validas"):
            cargar_reglas(yaml_roto)


# ===========================================================================
# Tests de acabados (C-16)
# ===========================================================================

class TestAcabados:

    def test_cuatro_gamas_definidas(self, reglas):
        """PASS: LAC, WOO, LAM y LIN tienen acabados."""
        for gama in ("LAC", "WOO", "LAM", "LIN"):
            assert gama in reglas["acabados"], f"Gama {gama} sin acabados"
            assert len(reglas["acabados"][gama]) > 0

    def test_lac_incluye_blanco(self, reglas):
        """PASS: Blanco es acabado LAC conocido."""
        assert "Blanco" in reglas["acabados"]["LAC"]

    def test_woo_incluye_cerezo(self, reglas):
        """PASS: Cerezo es acabado WOO conocido."""
        assert "Cerezo" in reglas["acabados"]["WOO"]

    def test_lam_incluye_pale(self, reglas):
        """PASS: Pale es acabado LAM conocido (EU-21822)."""
        assert "Pale" in reglas["acabados"]["LAM"]

    def test_acabado_inexistente_no_en_lista(self, reglas):
        """FAIL semántico: un acabado inventado no debe aparecer en ninguna gama."""
        for gama, lista in reglas["acabados"].items():
            assert "AcabadoFalso_XYZ" not in lista, f"Acabado falso en {gama}"

    def test_no_hay_duplicados_en_gama(self, reglas):
        """PASS: no hay acabados duplicados dentro de una misma gama."""
        for gama, lista in reglas["acabados"].items():
            assert len(lista) == len(set(lista)), f"Duplicados en acabados.{gama}"


# ===========================================================================
# Tests de cazoletas METOD (C-25)
# ===========================================================================

class TestCazoletas:

    def test_lista_no_vacia(self, reglas):
        """PASS: hay al menos una entrada en cazoletas_metod."""
        assert len(reglas["cazoletas_metod"]) > 0

    def test_campos_obligatorios_presentes(self, reglas):
        """PASS: cada entrada tiene alto_max, cazoletas y nota."""
        for entrada in reglas["cazoletas_metod"]:
            for campo in ("alto_max", "cazoletas", "nota"):
                assert campo in entrada

    def test_orden_creciente_alto_max(self, reglas):
        """PASS: los alto_max están en orden estrictamente creciente."""
        valores = [e["alto_max"] for e in reglas["cazoletas_metod"]]
        assert valores == sorted(valores)

    def test_ultimo_registro_cubre_altura_extrema(self, reglas):
        """PASS: el último registro cubre alturas muy grandes (≥ 2200)."""
        ultimo = reglas["cazoletas_metod"][-1]
        assert ultimo["alto_max"] >= 2200

    def test_puerta_600_tiene_2_cazoletas(self, reglas):
        """PASS: puerta de 600mm → 2 bisagras."""
        for entrada in reglas["cazoletas_metod"]:
            if entrada["alto_max"] >= 600:
                assert entrada["cazoletas"] == 2
                break

    def test_cazoleta_sin_campo_lanza_error(self, tmp_path):
        """FAIL: entrada sin 'alto_max' → ValueError."""
        datos = yaml.safe_load(REGLAS_PATH.read_text(encoding="utf-8"))
        del datos["cazoletas_metod"][0]["alto_max"]
        yaml_roto = tmp_path / "reglas_roto.yaml"
        yaml_roto.write_text(yaml.dump(datos, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError, match="alto_max"):
            cargar_reglas(yaml_roto)

    def test_alturas_estandar_puerta_contienen_798(self, reglas):
        """PASS: la lista de alturas estándar de puerta incluye los valores clave (798, 598, 998)."""
        alturas = reglas["puerta_alturas_estandar"]
        assert isinstance(alturas, list)
        assert 798 in alturas
        assert 598 in alturas
        assert 998 in alturas


# ===========================================================================
# Tests de baldas (C-26)
# ===========================================================================

class TestBaldas:

    def test_tres_dimensiones_estandar(self, reglas):
        """PASS: hay exactamente 3 dimensiones estándar de balda."""
        assert len(reglas["baldas_dimensiones"]) == 3

    def test_campos_obligatorios_presentes(self, reglas):
        """PASS: cada balda tiene ancho, alto y herrajes."""
        for balda in reglas["baldas_dimensiones"]:
            for campo in ("ancho", "alto", "herrajes"):
                assert campo in balda

    def test_balda_600_existe(self, reglas):
        """PASS: balda con dimensión 600 (como alto) está definida."""
        altos = [b["alto"] for b in reglas["baldas_dimensiones"]]
        assert 600 in altos

    def test_balda_sin_campo_lanza_error(self, tmp_path):
        """FAIL: balda sin 'herrajes' → ValueError."""
        datos = yaml.safe_load(REGLAS_PATH.read_text(encoding="utf-8"))
        del datos["baldas_dimensiones"][0]["herrajes"]
        yaml_roto = tmp_path / "reglas_roto.yaml"
        yaml_roto.write_text(yaml.dump(datos, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError, match="herrajes"):
            cargar_reglas(yaml_roto)


# ===========================================================================
# Tests de layers DXF (C-30 a C-43)
# ===========================================================================

class TestLayers:

    def test_layer_control_en_criticos(self, reglas):
        """PASS: CONTROL está en layers.criticos (C-30)."""
        assert "CONTROL" in reglas["layers"]["criticos"]

    def test_0_anotaciones_en_obligatorios(self, reglas):
        """PASS: 0_ANOTACIONES está en layers.obligatorios (C-33)."""
        assert "0_ANOTACIONES" in reglas["layers"]["obligatorios"]

    def test_13_biselar_en_lam_lin(self, reglas):
        """PASS: layer de biselado LAM/LIN presente (C-34)."""
        assert "13-BISELAR-EM5-Z0_8" in reglas["layers"]["obligatorios_lam_lin"]

    def test_layers_desuso_es_lista(self, reglas):
        """PASS: layers.desuso es una lista."""
        assert isinstance(reglas["layers"]["desuso"], list)

    def test_tirador_handcut_es_string(self, reglas):
        """PASS: tirador_handcut es un string no vacío."""
        handcut = reglas["layers"]["tirador_handcut"]
        assert isinstance(handcut, str) and len(handcut) > 0

    def test_cajones_drill_no_vacio(self, reglas):
        """PASS: hay al menos un layer de drill para cajones (C-38)."""
        assert len(reglas["layers"]["cajones_drill"]) > 0

    def test_bisagras_metod_no_vacio(self, reglas):
        """PASS: hay layers de pocket para bisagras METOD (C-39)."""
        assert len(reglas["layers"]["bisagras_metod"]) > 0

    def test_layer_inexistente_no_en_criticos(self, reglas):
        """FAIL semántico: layer inventado no en criticos."""
        assert "LAYER_FALSO_XYZ" not in reglas["layers"]["criticos"]

    def test_corte_perimetral_tiene_estandar(self, reglas):
        """PASS: corte_perimetral.estandar definido (C-35)."""
        assert "estandar" in reglas["layers"]["corte_perimetral"]

    def test_lac_acabados_estandar_incluye_blanco(self, reglas):
        """PASS: Blanco usa CUTEXT, no CONTORNO LACA."""
        lista = reglas["layers"]["corte_perimetral"]["lac_acabados_estandar"]
        assert "Blanco" in lista


# ===========================================================================
# Tests de desbaste tirador (C-36)
# ===========================================================================

class TestDesbasteTirador:

    def test_cerezo_tiene_layer(self, reglas):
        """PASS: CEREZO tiene layer de desbaste definido."""
        assert "CEREZO" in reglas["desbaste_tirador"]

    def test_default_existe(self, reglas):
        """PASS: _DEFAULT siempre existe como fallback."""
        assert "_DEFAULT" in reglas["desbaste_tirador"]

    def test_lin_especial_existe(self, reglas):
        """PASS: _LIN tiene layer propio (linóleo usa soft)."""
        assert "_LIN" in reglas["desbaste_tirador"]

    def test_todos_los_valores_son_strings(self, reglas):
        """PASS: todos los layers de desbaste son strings no vacíos."""
        for color, layer in reglas["desbaste_tirador"].items():
            assert isinstance(layer, str) and len(layer) > 0, \
                f"desbaste_tirador.{color} no es string válido"

    def test_color_inexistente_no_en_desbaste(self, reglas):
        """FAIL semántico: color inventado no debe tener layer."""
        assert "VERDE_FLUORESCENTE" not in reglas["desbaste_tirador"]

    def test_tiradores_con_geometria_dxf_es_lista(self, reglas):
        """PASS: tiradores_con_geometria_dxf es lista con al menos Round."""
        lista = reglas["tiradores_con_geometria_dxf"]
        assert isinstance(lista, list)
        assert "Round" in lista


# ===========================================================================
# Tests de tipologías (C-17, C-20–C-22, C-27, C-28)
# ===========================================================================

class TestTipologias:

    def test_apertura_obligatoria_incluye_p(self, reglas):
        """PASS: puertas P siempre llevan apertura (C-20)."""
        assert "P" in reglas["tipologias"]["apertura_obligatoria"]

    def test_apertura_nunca_incluye_c(self, reglas):
        """PASS: cajones C nunca llevan apertura (C-22)."""
        assert "C" in reglas["tipologias"]["apertura_nunca"]

    def test_tipologias_sin_mecanizado_incluye_t_y_r(self, reglas):
        """PASS: T y R no deben llevar tirador (C-28)."""
        lista = reglas["tipologias"]["tipologias_sin_mecanizado"]
        assert "T" in lista
        assert "R" in lista

    def test_mecanizado_esperado_puerta_es_cazta(self, reglas):
        """PASS: puerta P espera cazoletas (C-27)."""
        assert reglas["tipologias"]["mecanizado_esperado"]["P"] == "cazta."

    def test_mecanizado_esperado_cajon_es_torn(self, reglas):
        """PASS: cajón C espera tornillos (C-27)."""
        assert reglas["tipologias"]["mecanizado_esperado"]["C"] == "torn."

    def test_apertura_obligatoria_no_incluye_c(self, reglas):
        """FAIL semántico: C no debe tener apertura obligatoria."""
        assert "C" not in reglas["tipologias"]["apertura_obligatoria"]

    def test_sufijo_a_tipologia_tiene_clave_p(self, reglas):
        """PASS: la clave P está en sufijo_a_tipologia (C-17)."""
        assert "P" in reglas["tipologias"]["sufijo_a_tipologia"]


# ===========================================================================
# Tests de logística (C-54, C-55)
# ===========================================================================

class TestLogistica:

    def test_tolerancia_peso_es_float(self, reglas):
        """PASS: tolerancia_peso_porcentaje es un número positivo."""
        tol = reglas["logistica"]["tolerancia_peso_porcentaje"]
        assert isinstance(tol, (int, float)) and tol > 0

    def test_tolerancia_peso_es_2_por_ciento(self, reglas):
        """PASS: valor por defecto es 2.0% según arquitectura."""
        assert reglas["logistica"]["tolerancia_peso_porcentaje"] == 2.0

    def test_umbral_estructura_es_780(self, reglas):
        """PASS: umbral de estructura definido en 780mm."""
        assert reglas["logistica"]["estructura_umbral_mm"] == 780

    def test_tolerancia_negativa_rechazada_semanticamente(self, reglas):
        """FAIL semántico: la tolerancia nunca debe ser negativa."""
        assert reglas["logistica"]["tolerancia_peso_porcentaje"] >= 0


# ===========================================================================
# Tests de nomenclatura (C-00, C-02)
# ===========================================================================

class TestNomenclatura:

    def test_patron_despiece_definido(self, reglas):
        """PASS: patrón para identificar archivo DESPIECE existe."""
        assert "despiece" in reglas["nomenclatura"]["patrones"]

    def test_patron_ean_definido(self, reglas):
        """PASS: patrón para EAN LOGISTIC existe."""
        assert "ean" in reglas["nomenclatura"]["patrones"]

    def test_prefijo_bloqueado_definido(self, reglas):
        """PASS: prefijo de estado BLOQUEADO definido."""
        assert "bloqueado" in reglas["nomenclatura"]["prefijos_estado"]

    def test_prefijo_aprobado_empieza_con_ok(self, reglas):
        """PASS: prefijo aprobado contiene [OK]."""
        prefijo = reglas["nomenclatura"]["prefijos_estado"]["aprobado"]
        assert "[OK]" in prefijo

    def test_prefijo_bloqueado_contiene_bloqueado(self, reglas):
        """PASS: prefijo bloqueado contiene la palabra BLOQUEADO."""
        prefijo = reglas["nomenclatura"]["prefijos_estado"]["bloqueado"]
        assert "BLOQUEADO" in prefijo

    def test_patron_dxf_tablero_definido(self, reglas):
        """PASS: patrón para DXF de tablero existe."""
        assert "dxf_tablero" in reglas["nomenclatura"]["patrones"]


# ===========================================================================
# Tests de reglas_cnc.yaml
# ===========================================================================

class TestReglasCNC:

    def test_excepciones_es_lista(self, reglas_cnc):
        """PASS: excepciones es una lista."""
        assert isinstance(reglas_cnc["excepciones"], list)

    def test_al_menos_una_excepcion(self, reglas_cnc):
        """PASS: hay al menos un patrón CNC definido."""
        assert len(reglas_cnc["excepciones"]) > 0

    def test_cada_excepcion_tiene_patron_tipo_justifica(self, reglas_cnc):
        """PASS: cada excepción tiene los tres campos obligatorios."""
        for i, exc in enumerate(reglas_cnc["excepciones"]):
            for campo in ("patron", "tipo", "justifica_check"):
                assert campo in exc, f"excepciones[{i}] falta campo '{campo}'"

    def test_patron_retal_presente(self, reglas_cnc):
        """PASS: patrón RETAL está definido (C-60)."""
        tipos = {e["tipo"] for e in reglas_cnc["excepciones"]}
        assert "RETAL" in tipos

    def test_patron_sin_mecanizado_presente(self, reglas_cnc):
        """PASS: patrón SIN_MECANIZADO está definido (C-61)."""
        tipos = {e["tipo"] for e in reglas_cnc["excepciones"]}
        assert "SIN_MECANIZADO" in tipos

    def test_patron_envio_estructura_presente(self, reglas_cnc):
        """PASS: patrón ENVIO_ESTRUCTURA está definido (C-55)."""
        tipos = {e["tipo"] for e in reglas_cnc["excepciones"]}
        assert "ENVIO_ESTRUCTURA" in tipos

    def test_tipo_inventado_no_presente(self, reglas_cnc):
        """FAIL semántico: tipo inventado no debe existir."""
        tipos = {e["tipo"] for e in reglas_cnc["excepciones"]}
        assert "TIPO_FALSO_XYZ" not in tipos

    def test_excepcion_sin_campo_lanza_error(self, tmp_path):
        """FAIL: excepción sin 'tipo' → ValueError."""
        datos = yaml.safe_load(REGLAS_CNC_PATH.read_text(encoding="utf-8"))
        del datos["excepciones"][0]["tipo"]
        yaml_roto = tmp_path / "cnc_roto.yaml"
        yaml_roto.write_text(yaml.dump(datos, allow_unicode=True), encoding="utf-8")
        with pytest.raises(ValueError):
            cargar_reglas_cnc(yaml_roto)

    def test_todos_los_patrones_son_strings(self, reglas_cnc):
        """PASS: todos los campos 'patron' son strings no vacíos."""
        for exc in reglas_cnc["excepciones"]:
            assert isinstance(exc["patron"], str) and len(exc["patron"]) > 0

    def test_justifica_check_es_string_o_lista(self, reglas_cnc):
        """PASS: justifica_check es string tipo C-XX o lista vacía."""
        for exc in reglas_cnc["excepciones"]:
            jc = exc["justifica_check"]
            assert isinstance(jc, (str, list)), \
                f"justifica_check de tipo incorrecto: {type(jc)}"


# ===========================================================================
# Tests de consistencia cruzada entre secciones
# ===========================================================================

class TestConsistenciaCruzada:

    def test_gamas_en_materiales_coinciden_con_acabados(self, reglas):
        """PASS: toda gama válida en materiales tiene acabados definidos."""
        todas_gamas = set()
        for config in reglas["materiales"].values():
            todas_gamas.update(config["gamas_validas"])
        for gama in todas_gamas:
            assert gama in reglas["acabados"], \
                f"Gama '{gama}' en materiales pero sin acabados definidos"

    def test_apertura_obligatoria_y_nunca_no_solapan(self, reglas):
        """PASS: las listas apertura_obligatoria y apertura_nunca son disjuntas."""
        obligatoria = set(reglas["tipologias"]["apertura_obligatoria"])
        nunca = set(reglas["tipologias"]["apertura_nunca"])
        solapamiento = obligatoria & nunca
        assert not solapamiento, \
            f"Tipologías en apertura_obligatoria Y apertura_nunca: {solapamiento}"

    def test_mecanizado_esperado_tipologias_sin_mecanizado_no_solapan(self, reglas):
        """PASS: tipologías con mecanizado esperado no están en sin_mecanizado."""
        con_mec = set(reglas["tipologias"]["mecanizado_esperado"].keys())
        sin_mec = set(reglas["tipologias"]["tipologias_sin_mecanizado"])
        solapamiento = con_mec & sin_mec
        assert not solapamiento, \
            f"Tipologías con Y sin mecanizado al mismo tiempo: {solapamiento}"
