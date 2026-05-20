"""tests/test_extractor_extraccion.py — Tests del parser EXTRACCION.

Cubre:
  - Sección A (cabecera): mapeo de claves, conversión de tipos, claves <COD>_tab,
    typo legacy 'integradros', alias case-insensitive.
  - Sección B (tabla): detección de cabecera 'ID Proyecto', conversión HPL→LAM,
    inferencia de material a partir de gama, filas vacías ignoradas.
  - Manejo de errores: CSV vacío, falta de cabecera de tabla.
  - cargar_naming() y cod_tab_a_clave_canonica().
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.extractor_extraccion import (
    cargar_naming,
    cargar_naming_default,
    cod_tab_a_clave_canonica,
    leer_extraccion,
)
from core.modelos import ExtraccionData, FilaExtraccion
from core.reglas_loader import cargar_reglas


@pytest.fixture(scope="session")
def reglas():
    return cargar_reglas(ROOT / "reglas.yaml")


def _csv_en_memoria(texto: str, encoding: str = "utf-8") -> io.BytesIO:
    buf = io.BytesIO(texto.encode(encoding))
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# CSV base de prueba — reproduce el proyecto EU-22376 con valores compactos
# ---------------------------------------------------------------------------

CSV_BASE = """Numero OT,5074
Semana,22
Fecha entrada,25/05/2026
Fecha salida,05/06/2026
Altillos
Mueble de nevera 75x60x220 cm,0
Baldas con 2 herrajes ocultos,0
Baldas con 3 herrajes ocultos,0
Hornacinas,0
Caja grande,1
Caja pequeña,0
Estructura grande,0
Estructura pequeña,0
Cantidad de palets,1
LAC_Zaf_tab,2
Cantidad de piezas,3
Metros de canto,63
Cantidad de tensores,0
Rejillas ventilacion,1
Tiradores Integrados,2
Prioridad de INC,
ID Proyecto,Nombre Cliente,Pieza,Tipologia,Ancho,Alto,Material,Gama,Acabado,Mecanizado,Tirador,Posición de tirador,Apertura,Color Tirador,CNC,AC2,Embalaje
EU-22376,Bürgerverein,M1-T1,T,120,800,MDF,LAC,Zafiro,,,,,,,,
EU-22376,Bürgerverein,M1-C1,C,798,398,MDF,LAC,Zafiro,torn.,Round,1,,ZAFIRO,,,
EU-22376,Bürgerverein,M2-P1,P,398,798,MDF,LAC,Zafiro,2 cazta.,Round,2,I,ZAFIRO,,,
"""


# ---------------------------------------------------------------------------
# Sección A: cabecera
# ---------------------------------------------------------------------------

class TestSeccionA:

    def test_campos_cabecera_basicos(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.numero_ot == "5074"
        assert d.semana == "22"
        assert d.fecha_entrada == "25/05/2026"
        assert d.fecha_salida == "05/06/2026"
        assert d.piezas == 3
        assert d.tiradores == 2
        assert d.metros_canto == pytest.approx(63.0)
        assert d.tensores == 0
        assert d.rejillas_ventilacion == 1
        assert d.hornacinas == 0
        assert d.palets == 1
        assert d.caja_grande == 1
        assert d.caja_pequena == 0
        assert d.estructura_grande == 0
        assert d.estructura_pequena == 0
        assert d.baldas_2h == 0
        assert d.baldas_3h == 0
        assert d.mueble_nevera == 0
        assert d.prioridad_inc == ""

    def test_tipo_envio_activo(self, reglas):
        """tipo_envio_activo: 'caja_grande' cuando solo ese es ≥1."""
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.tipo_envio_activo == "caja_grande"

    def test_tipo_envio_ninguno_activo(self, reglas):
        csv = CSV_BASE.replace("Caja grande,1", "Caja grande,0")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.tipo_envio_activo == ""

    def test_tipo_envio_multiple_activo(self, reglas):
        csv = CSV_BASE.replace("Caja pequeña,0", "Caja pequeña,1")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.tipo_envio_activo == ""  # ambiguo → vacío

    def test_clave_tab_extraida_aparte(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.tableros_codificados == {"LAC_Zaf_tab": 2}

    def test_typo_legacy_integradros(self, reglas):
        """El alias acepta el typo histórico 'Tiradores integradros'."""
        csv = CSV_BASE.replace("Tiradores Integrados,2", "Tiradores integradros,5")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.tiradores == 5

    def test_metros_canto_con_decimal(self, reglas):
        csv = CSV_BASE.replace("Metros de canto,63", "Metros de canto,62.32")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.metros_canto == pytest.approx(62.32)

    def test_metros_canto_con_coma(self, reglas):
        csv = CSV_BASE.replace("Metros de canto,63", "Metros de canto,62,32")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        # Nota: la coma en CSV es separador; '62,32' se ve como dos columnas
        # → _int_o('62') → 62.0. Para que la coma decimal funcione, el sistema
        # debe usar ';' como separador o escribir "62.32".
        # Test alternativo: punto decimal funciona correctamente.
        assert d.metros_canto == pytest.approx(62.0)

    def test_metros_canto_con_unidades(self, reglas):
        """'62.32 mt' (con unidad embebida) → 62.32."""
        # Comilla doble alrededor para que CSV no parta por la coma decimal
        csv = CSV_BASE.replace("Metros de canto,63", 'Metros de canto,"62.32 mt"')
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.metros_canto == pytest.approx(62.32)

    def test_alias_normaliza_tildes(self, reglas):
        """'Posición de tirador' (con tilde) se reconoce."""
        # La columna ya lleva tilde en CSV_BASE; aquí cambiamos la línea de
        # cabecera para meter Posicion sin tilde y verificar idempotencia.
        csv = CSV_BASE.replace("Posición de tirador", "Posicion de tirador")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        # Las posiciones se rellenan en filas de piezas
        ids = [f.id_pieza for f in d.piezas_tabla]
        assert "M2-P1" in ids
        for f in d.piezas_tabla:
            if f.id_pieza == "M2-P1":
                assert f.posicion_tirador == "2"

    def test_id_proyecto_recuperado_de_tabla(self, reglas):
        """Si la cabecera no incluye id_proyecto, se recupera de la 1ª fila."""
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.id_proyecto == "EU-22376"
        assert d.cliente == "Bürgerverein"

    def test_claves_desconocidas_se_reportan(self, reglas):
        csv = CSV_BASE.replace(
            "Numero OT,5074\n",
            "Numero OT,5074\nCampo Inexistente Para Test,42\n",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert any("Campo Inexistente" in c for c in d.claves_desconocidas)

    def test_altillos_sin_valor(self, reglas):
        """Fila 'Altillos' sin valores → total=0, dims vacío."""
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.altillos_total == 0
        assert d.altillos_dims == {}

    def test_altillos_con_desglose(self, reglas):
        """Fila 'Altillos,6,997x480x580,4,497x480x580,2' → total + dims."""
        csv = CSV_BASE.replace(
            "Altillos\n",
            "Altillos,6,997x480x580,4,497x480x580,2\n",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.altillos_total == 6
        assert d.altillos_dims == {"997x480x580": 4, "497x480x580": 2}

    def test_altillos_solo_total_sin_desglose(self, reglas):
        """Fila 'Altillos,3' (total agregado, sin desglose por dim)."""
        csv = CSV_BASE.replace("Altillos\n", "Altillos,3\n")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.altillos_total == 3
        assert d.altillos_dims == {}

    def test_altillos_no_va_a_claves_desconocidas(self, reglas):
        """Las dimensiones de altillos no deben aparecer en claves_desconocidas."""
        csv = CSV_BASE.replace(
            "Altillos\n",
            "Altillos,6,997x480x580,4,497x480x580,2\n",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert not any("997x480x580" in c for c in d.claves_desconocidas)
        assert not any("497x480x580" in c for c in d.claves_desconocidas)


# ---------------------------------------------------------------------------
# Multi-material: pares (clave, valor) repetidos en la MISMA fila
# ---------------------------------------------------------------------------
# En proyectos con varias gamas+acabados, el sistema CUBRO repite las claves
# por material en la misma fila del CSV. Ejemplos reales (EU-22427):
#   LAC_Pin_tab,2,LAC_Rot_tab,1
#   Cantidad de piezas,23,Cantidad de piezas,11
#   Metros de canto,61,Metros de canto,37
# El parser debe iterar la fila por pares y acumular los campos numéricos.

CSV_MULTI = """Numero OT,5085
Semana,22
Fecha entrada,25/05/2026
Fecha salida,05/06/2026
Mueble de nevera 75x60x220 cm,0
Caja grande,1
Cantidad de palets,1
LAC_Pin_tab,2,LAC_Rot_tab,1
Cantidad de piezas,23,Cantidad de piezas,11
Metros de canto,61,Metros de canto,37
Cantidad de tensores,0
Rejillas ventilacion,2
Tiradores integradros,20
Prioridad de INC,
ID Proyecto,Nombre Cliente,Pieza,Tipologia,Ancho,Alto,Material,Gama,Acabado,Mecanizado,Tirador,Posición de tirador,Apertura,Color Tirador,CNC,AC2,Embalaje
EU-22427,Konrad Hopf,M1-T1,T,200,800,MDF,LAC,Pino,,,,,,,,
EU-22427,Konrad Hopf,M8-PL1,L,396,800,MDF,LAC,Roto,,,,,,,,
"""


class TestMultiMaterial:

    def test_tableros_codificados_dos_combinaciones(self, reglas):
        """LAC_Pin_tab=2 y LAC_Rot_tab=1 ambos en la misma fila → dict con ambos."""
        d = leer_extraccion(_csv_en_memoria(CSV_MULTI), reglas)
        assert d.tableros_codificados == {"LAC_Pin_tab": 2, "LAC_Rot_tab": 1}

    def test_piezas_se_acumulan(self, reglas):
        """'Cantidad de piezas,23,Cantidad de piezas,11' → 34."""
        d = leer_extraccion(_csv_en_memoria(CSV_MULTI), reglas)
        assert d.piezas == 34

    def test_metros_canto_se_acumulan(self, reglas):
        """'Metros de canto,61,Metros de canto,37' → 98.0."""
        d = leer_extraccion(_csv_en_memoria(CSV_MULTI), reglas)
        assert d.metros_canto == pytest.approx(98.0)

    def test_string_conserva_primera_aparicion(self, reglas):
        """Si el sistema duplica Numero OT, conservamos la primera no vacía."""
        csv = CSV_MULTI.replace(
            "Numero OT,5085", "Numero OT,5085,Numero OT,5085",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.numero_ot == "5085"

    def test_unico_material_sigue_funcionando(self, reglas):
        """Regresión: un solo par en la fila se sigue parseando bien (era el caso de CSV_BASE)."""
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert d.tableros_codificados == {"LAC_Zaf_tab": 2}
        assert d.piezas == 3
        assert d.metros_canto == pytest.approx(63.0)

    def test_tres_materiales_se_acumulan(self, reglas):
        """Hipotético: 3 combinaciones en la misma fila."""
        csv = CSV_MULTI.replace(
            "LAC_Pin_tab,2,LAC_Rot_tab,1",
            "LAC_Pin_tab,2,LAC_Rot_tab,1,HPL_Pal_tab,3",
        ).replace(
            "Cantidad de piezas,23,Cantidad de piezas,11",
            "Cantidad de piezas,23,Cantidad de piezas,11,Cantidad de piezas,8",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        assert d.tableros_codificados == {
            "LAC_Pin_tab": 2, "LAC_Rot_tab": 1, "HPL_Pal_tab": 3,
        }
        assert d.piezas == 42


# ---------------------------------------------------------------------------
# Sección B: tabla de piezas
# ---------------------------------------------------------------------------

class TestSeccionB:

    def test_numero_filas_correcto(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        assert len(d.piezas_tabla) == 3

    def test_fila_sin_tirador(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        f = next(p for p in d.piezas_tabla if p.id_pieza == "M1-T1")
        assert f.tipologia == "T"
        assert f.ancho == 120
        assert f.alto == 800
        assert f.material == "MDF"
        assert f.gama == "LAC"
        assert f.acabado == "Zafiro"
        assert f.tirador == ""

    def test_fila_con_tirador_completo(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE), reglas)
        f = next(p for p in d.piezas_tabla if p.id_pieza == "M2-P1")
        assert f.tirador == "Round"
        assert f.posicion_tirador == "2"
        assert f.apertura == "I"
        assert f.color_tirador == "ZAFIRO"
        assert f.mecanizado == "2 cazta."

    def test_hpl_se_traduce_a_lam(self, reglas):
        """Si la gama llega como HPL (codificación EXTRACCION), pasa a LAM."""
        csv = CSV_BASE.replace(",MDF,LAC,Zafiro", ",PLY,HPL,Pale")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        for f in d.piezas_tabla:
            assert f.gama == "LAM"
            assert f.material == "PLY"

    def test_material_inferido_si_falta(self, reglas):
        """Si Material está vacío pero hay Gama, el material se infiere."""
        # Pieza WOO sin material declarado debería resolver a MDF
        csv = CSV_BASE.replace(",MDF,LAC,Zafiro", ",,WOO,Cerezo")
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        for f in d.piezas_tabla:
            assert f.gama == "WOO"
            assert f.material == "MDF"

    def test_fila_vacia_se_ignora(self, reglas):
        csv = CSV_BASE.replace(
            "EU-22376,Bürgerverein,M1-T1",
            "EU-22376,,,,,,,,,,,,,,,,\nEU-22376,Bürgerverein,M1-T1",
        )
        d = leer_extraccion(_csv_en_memoria(csv), reglas)
        # La fila con id_pieza vacío no se añade
        assert all(p.id_pieza for p in d.piezas_tabla)


# ---------------------------------------------------------------------------
# Manejo de errores
# ---------------------------------------------------------------------------

class TestErrores:

    def test_csv_vacio_levanta_error(self, reglas):
        with pytest.raises(ValueError, match="vacío"):
            leer_extraccion(_csv_en_memoria(""), reglas)

    def test_sin_cabecera_tabla_levanta_error(self, reglas):
        csv = "Numero OT,5074\nSemana,22\n"
        with pytest.raises(ValueError, match="cabecera"):
            leer_extraccion(_csv_en_memoria(csv), reglas)

    def test_acepta_path(self, tmp_path, reglas):
        ruta = tmp_path / "EXTRACCION_test.csv"
        ruta.write_text(CSV_BASE, encoding="utf-8")
        d = leer_extraccion(ruta, reglas)
        assert d.piezas == 3

    def test_acepta_utf8_bom(self, reglas):
        d = leer_extraccion(_csv_en_memoria(CSV_BASE, encoding="utf-8-sig"), reglas)
        assert d.numero_ot == "5074"


# ---------------------------------------------------------------------------
# cargar_naming() y cod_tab_a_clave_canonica()
# ---------------------------------------------------------------------------

class TestNaming:

    def test_cargar_naming_default(self):
        mapa = cargar_naming_default()
        # Al menos las combinaciones más usuales deben estar
        assert "lac_zaf_tab" in mapa
        assert mapa["lac_zaf_tab"] == ("Laca", "Zafiro")
        assert "hpl_pal_tab" in mapa
        assert mapa["hpl_pal_tab"] == ("Laminado", "Pale")

    def test_cargar_naming_case_insensitive(self):
        """LAC_bla_tab (typo del sistema, minúscula) se encuentra como lac_bla_tab."""
        mapa = cargar_naming_default()
        assert "lac_bla_tab" in mapa

    def test_decodifica_lac_a_canonica(self):
        mapa = cargar_naming_default()
        assert cod_tab_a_clave_canonica("LAC_Zaf_tab", mapa) == "MDF_LAC_Zafiro"

    def test_decodifica_hpl_a_lam(self):
        """HPL_Pal_tab → PLY_LAM_Pale (HPL se traduce a LAM)."""
        mapa = cargar_naming_default()
        assert cod_tab_a_clave_canonica("HPL_Pal_tab", mapa) == "PLY_LAM_Pale"

    def test_decodifica_wood_con_sufijo_m(self):
        """WOO_Cer_M_tab → MDF_WOO_Cerezo."""
        mapa = cargar_naming_default()
        assert cod_tab_a_clave_canonica("WOO_Cer_M_tab", mapa) == "MDF_WOO_Cerezo"

    def test_decodifica_codigo_desconocido_devuelve_none(self):
        mapa = cargar_naming_default()
        assert cod_tab_a_clave_canonica("XXX_Yyy_tab", mapa) is None

    def test_cargar_naming_archivo_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            cargar_naming(tmp_path / "no_existe.csv")
