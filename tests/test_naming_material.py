"""tests/test_naming_material.py — Vocabulario material+gama+acabado en nombres."""

from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.naming_material import (
    GAMA_ALIAS,
    GAMA_DISPLAY,
    clave_comparable,
    norm_acabado,
    parsear_material,
)


class TestParsearMaterial:

    @pytest.mark.parametrize("nombre,esperado", [
        # Formato con underscores y gama en palabra completa.
        ("EU21822_Sabine_Jennes_PLY_LAMINADO_PALE_T1.dxf", ("PLY", "LAM", "Pale")),
        # Formato con espacios y guión en el ID.
        ("EU-21247_Daphne Zindili_MDF LACA MARGA_T1.dxf", ("MDF", "LAC", "Marga")),
        # Gama en código interno.
        ("EU21822_Sabine_PLY_LAM_PALE.pdf", ("PLY", "LAM", "Pale")),
        # PDF de nesting real, sin sufijo de tablero.
        ("EU21868INC_Philip_Gregoire_MDF_WOOD_ROBLE.pdf", ("MDF", "WOO", "Roble")),
        # ID numérico de 4 dígitos.
        ("4302_baptiste_ducloux_MDF_LACA_PINO.pdf", ("MDF", "LAC", "Pino")),
        # Acabado de dos palabras.
        ("EU123_x_PLY_LINOLEO_SMOKEY_BLUE.pdf", ("PLY", "LIN", "Smokey Blue")),
        # Linóleo con acento en la gama.
        ("EU123_x_PLY_LINÓLEO_OLIVE.dxf", ("PLY", "LIN", "Olive")),
    ])
    def test_parsea(self, nombre, esperado):
        assert parsear_material(nombre) == esperado

    @pytest.mark.parametrize("nombre", [
        "DESPIECE_EU-21822.xlsx",      # no es dxf ni pdf
        "OT_EU-21822.pdf",             # sin material en el nombre
        "EU21822_Sabine_MDF.pdf",      # material sin gama ni acabado
        "EU21822_Sabine_MDF_LACA.pdf", # gama sin acabado
    ])
    def test_no_parsea(self, nombre):
        assert parsear_material(nombre) is None

    def test_laminado_no_se_consume_como_lam(self):
        """La alternancia va de más larga a más corta: 'LAMINADO' no debe
        matchear como 'LAM' dejando 'INADO' dentro del acabado."""
        assert parsear_material("EU1_x_PLY_LAMINADO_PALE.dxf") == ("PLY", "LAM", "Pale")


class TestNormAcabado:

    @pytest.mark.parametrize("a,b", [
        ("Cadaqués", "CADAQUES"),        # el nombre de archivo pierde el acento
        ("Rosa-baby", "ROSA BABY"),      # guión vs espacio
        ("Smokey-Blue", "SMOKEY_BLUE"),  # guión vs underscore
        ("Roble", "ROBLE"),              # solo mayúsculas
        ("Marble-Green", "marblegreen"), # sin separador
    ])
    def test_equivalentes(self, a, b):
        assert norm_acabado(a) == norm_acabado(b)

    def test_distintos_no_colisionan(self):
        assert norm_acabado("Crema") != norm_acabado("Cerezo")
        assert norm_acabado("Pino") != norm_acabado("Pine")


class TestClaveComparable:

    def test_cruza_despiece_con_nombre_de_archivo(self):
        """La clave del DESPIECE y la del nombre de archivo deben coincidir."""
        del_despiece = clave_comparable("MDF", "WOO", "Roble")
        del_archivo = clave_comparable(
            *parsear_material("EU21868INC_Philip_MDF_WOOD_ROBLE.pdf")
        )
        assert del_despiece == del_archivo

    def test_distingue_gama(self):
        assert clave_comparable("MDF", "LAC", "Blanco") != clave_comparable(
            "PLY", "LAM", "Blanco")


class TestAlias:

    def test_display_es_inverso_de_alias(self):
        """GAMA_DISPLAY debe invertir GAMA_ALIAS para cada código interno, así
        la etiqueta que se muestra al taller vuelve al nombre de Drive."""
        for codigo, palabra in GAMA_DISPLAY.items():
            assert GAMA_ALIAS[palabra] == codigo
