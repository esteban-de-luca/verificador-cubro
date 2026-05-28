"""tests/test_checks_externos.py — Tests del grupo Externo (C-84+)."""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from checks.checks_externos import check_csv_hubspot


class TestC84:

    def test_pass_csv_existe(self):
        r = check_csv_hubspot("EU-21822", csv_existe=True)
        assert r.resultado == "PASS"
        assert r.bloquea
        assert r.id == "C-84"
        assert r.grupo == "Externo"

    def test_fail_csv_no_existe(self):
        r = check_csv_hubspot("EU-21822", csv_existe=False)
        assert r.resultado == "FAIL"
        assert r.bloquea
        assert "EU-21822.csv" in r.detalle

    def test_skip_drive_no_accesible(self):
        r = check_csv_hubspot("EU-21822", csv_existe=None)
        assert r.resultado == "SKIP"
        assert not r.bloquea
        assert "no accesible" in r.detalle.lower()

    def test_fail_id_4_digitos(self):
        """Proyectos 4302 también validan {ID}.csv."""
        r = check_csv_hubspot("4302", csv_existe=False)
        assert r.resultado == "FAIL"
        assert "4302.csv" in r.detalle

    def test_pass_id_inc(self):
        """Proyectos -INC: el archivo esperado es '{ID-INC}.csv'."""
        r = check_csv_hubspot("SP-20848-INC2", csv_existe=True)
        assert r.resultado == "PASS"
