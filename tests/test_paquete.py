"""verificador_cubro: el motor de reglas como librería (lo usa el dashboard antes de descargar)."""

import json

from verificador_cubro import ruta_regla, verificar_archivos


def test_las_reglas_se_encuentran_en_la_raiz_del_repo():
    assert ruta_regla("reglas.yaml").name == "reglas.yaml"
    assert ruta_regla("reglas_cnc.yaml").is_file()


def test_una_carpeta_vacia_queda_bloqueada_y_el_informe_es_json():
    informe = verificar_archivos({}, "EU-12345")
    assert informe["estado"] == "BLOQUEADO"
    c00 = next(c for c in informe["checks"] if c["id"] == "C-00")
    assert c00["resultado"] == "FAIL" and c00["bloquea"]
    assert set(informe["checks"][0]) == {"id", "desc", "resultado", "detalle", "bloquea", "grupo"}
    json.dumps(informe)


def test_el_csv_de_hubspot_cuenta_si_esta_entre_los_ficheros():
    sin = verificar_archivos({}, "EU-12345")
    con = verificar_archivos({"EU-12345.csv": b""}, "EU-12345")
    c84 = lambda i: next(c for c in i["checks"] if c["id"] == "C-84")  # noqa: E731
    assert c84(sin)["resultado"] != c84(con)["resultado"]
