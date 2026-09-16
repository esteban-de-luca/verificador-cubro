"""tests/test_retales.py — Consumo vs. generación de retales en las OBSERVACIONES CNC.

La distinción es la que sostiene la exculpación del '# Tableros 0' en C-04: un
patrón laxo que casara con 'Retales generados …' daría por bueno cualquier 0,
porque casi todas las OT generan retales.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.retales import retales_consumidos, retales_generados


# Bloque OBSERVACIONES CNC literal de la OT de SP-23508 (Laura Arribas).
OBS_SP23508 = [
    "La pieza P1 se debe cortar de retal R841",
    "Retales generados 1x de LIN Vapour R865, 1x de LAC Blanco R866, "
    "1x de WOO Nogal R867",
]


class TestRetalesConsumidos:

    def test_detecta_consumo_con_pieza_y_codigo(self):
        c = retales_consumidos(OBS_SP23508)
        assert len(c) == 1
        assert c[0].codigos == ("R841",)
        assert "P1" in c[0].ids_candidatos

    def test_ignora_la_linea_de_retales_generados(self):
        """El caso que blinda §5.3 del briefing: si esta línea colara como
        consumo, cualquier 0 quedaría exculpado."""
        assert retales_consumidos([OBS_SP23508[1]]) == []

    def test_ignora_generados_aunque_la_linea_hable_de_cortar(self):
        """Ante una línea con los dos sentidos se elige no exculpar."""
        obs = ["Retales generados al cortar de retal R900"]
        assert retales_consumidos(obs) == []

    def test_variantes_del_verbo_de_consumo(self):
        for texto in (
            "La pieza P1 se debe cortar de retal R841",
            "P1 se corta del retal R841",
            "Retal utilizado de MDF LACA Crema R841",
            "Retal de PLY LAM Pale",
        ):
            assert retales_consumidos([texto]), texto

    def test_observacion_ajena_no_es_consumo(self):
        obs = ["Cantear R1 por el canto largo", "M1-P1: 3 herrajes ocultos"]
        assert retales_consumidos(obs) == []

    def test_consumo_sin_codigo_se_detecta_igual(self):
        c = retales_consumidos(["La pieza P1 se corta de retal"])
        assert len(c) == 1
        assert c[0].codigos == ()
        assert c[0].codigos_texto == "(sin código)"

    def test_los_ids_previos_al_retal_son_candidatos_a_pieza(self):
        """El código del retal va detrás de la palabra 'retal'; lo de delante
        son IDs de pieza, aunque compartan forma (R2 rodapié vs R841 retal)."""
        c = retales_consumidos(["La pieza R2 se debe cortar de retal R841"])
        assert c[0].codigos == ("R841",)
        assert "R2" in c[0].ids_candidatos

    def test_sin_observaciones(self):
        assert retales_consumidos([]) == []


class TestRetalesGenerados:

    def test_extrae_los_codigos_generados(self):
        assert retales_generados(OBS_SP23508) == ["R865", "R866", "R867"]

    def test_el_consumo_no_cuenta_como_generacion(self):
        assert retales_generados([OBS_SP23508[0]]) == []
