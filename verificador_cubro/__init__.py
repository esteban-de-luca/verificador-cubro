"""
verificador_cubro — el motor de reglas del Verificador como librería.

Lo usa el dashboard (`cubro-dashboard`, paso «Observaciones y paquete» de «Generar fichero de
corte») para verificar el paquete que acaba de generar su motor ANTES de descargarlo, con los
mismos checks y las mismas reglas que la app de Streamlit. No toca Drive, Notion ni el log de
verificaciones: recibe los ficheros en memoria y devuelve el informe.

    from verificador_cubro import verificar_archivos
    informe = verificar_archivos({"DESPIECE_EU-1_Cliente.csv": b"...", ...}, "EU-1")
    informe["estado"]  # OK | ADVERTENCIAS | BLOQUEADO (el mismo que la app)

Las reglas viajan dentro del paquete instalado (`reglas.yaml`, `reglas_cnc.yaml`); en una copia
del repo se leen de la raíz, que es donde las edita el equipo.
"""

from __future__ import annotations

import io
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

__all__ = ["verificar_archivos", "ruta_regla", "VERSION"]

_AQUI = Path(__file__).resolve().parent

try:
    VERSION = metadata.version("verificador-cubro")
except metadata.PackageNotFoundError:  # copia del repo sin instalar
    VERSION = "repo"


def ruta_regla(nombre: str) -> Path:
    """Dónde está `reglas.yaml` / `reglas_cnc.yaml`: dentro del paquete instalado o en la raíz del repo."""
    for candidata in (_AQUI / nombre, _AQUI.parent / nombre):
        if candidata.is_file():
            return candidata
    raise FileNotFoundError(f"No se encuentra {nombre} ni en {_AQUI} ni en {_AQUI.parent}")


def verificar_archivos(
    archivos: Mapping[str, bytes],
    id_proyecto: str,
    *,
    csv_hubspot_existe: bool | None = None,
) -> dict[str, Any]:
    """Verifica un fichero de corte completo (los ficheros de su carpeta, por nombre).

    `csv_hubspot_existe` (C-84): por defecto, si entre los ficheros está `{id_proyecto}.csv`.

    Devuelve un dict serializable a JSON:
    `{"version", "id_proyecto", "cliente", "estado", "checks": [...], "errores_extraccion": [...]}`,
    con cada check como `{"id", "desc", "resultado", "detalle", "bloquea", "grupo"}` en el orden
    en que los ejecuta la app. `estado` es `InformeFinal.estado_global`.
    """
    from core.extractor_extraccion import cargar_naming_default
    from core.modelos import InformeFinal
    from core.reglas_loader import cargar_reglas, cargar_reglas_cnc
    from engine import _clasificar, _ejecutar_checks, _extraer

    reglas = cargar_reglas(ruta_regla("reglas.yaml"))
    reglas_cnc = cargar_reglas_cnc(ruta_regla("reglas_cnc.yaml"))
    if csv_hubspot_existe is None:
        csv_hubspot_existe = f"{id_proyecto}.csv" in archivos

    en_memoria = {nombre: io.BytesIO(datos) for nombre, datos in archivos.items()}
    datos = _extraer(en_memoria, _clasificar(list(en_memoria), reglas), reglas)
    datos.naming = cargar_naming_default()
    checks = _ejecutar_checks(datos, id_proyecto, reglas, reglas_cnc, csv_hubspot_existe)
    informe = InformeFinal(
        id_proyecto=id_proyecto,
        cliente=datos.ot.cliente if datos.ot else "",
        responsable="",
        semana="",
        checks=checks,
    )
    return {
        "version": VERSION,
        "id_proyecto": id_proyecto,
        "cliente": informe.cliente,
        "estado": informe.estado_global,
        "checks": [
            {
                "id": c.id,
                "desc": c.desc,
                "resultado": str(getattr(c.resultado, "value", c.resultado)),
                "detalle": str(c.detalle or ""),
                "bloquea": bool(c.bloquea),
                "grupo": str(c.grupo),
            }
            for c in checks
        ],
        "errores_extraccion": list(datos.errores_extraccion),
    }
