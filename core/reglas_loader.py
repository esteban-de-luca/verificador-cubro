"""
core/reglas_loader.py

Único punto de acceso a los archivos YAML de reglas de negocio.
Lee, valida campos obligatorios y devuelve las reglas como dict.

El motor (engine.py) llama a estas funciones UNA sola vez al inicio
de cada verificación. Todos los checks reciben las reglas como parámetro.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constantes de validación
# ---------------------------------------------------------------------------

_SECCIONES_OBLIGATORIAS_REGLAS = [
    "materiales",
    "acabados",
    "cazoletas_metod",
    "puerta_alto_sufijo_estandar",
    "baldas_dimensiones",
    "layers",
    "desbaste_tirador",
    "tiradores_con_geometria_dxf",
    "tipologias",
    "logistica",
    "nomenclatura",
]

_SUBSECCIONES_LAYERS = [
    "prohibidos_control",
    "sin_geometria_operativa",
    "rhino_internos",
    "obligatorios",
    "obligatorios_lam_lin",
    "desuso",
    "corte_perimetral",
    "tirador_handcut",
    "ventilacion",
    "colgador_hornacina",
    "tensores",
    "cajones_drill",
    "bisagras_metod",
    "bisagras_pax",
]

_SUBSECCIONES_TIPOLOGIAS = [
    "sufijo_a_tipologia",
    "apertura_obligatoria",
    "apertura_si_tirador",
    "apertura_nunca",
    "tipologias_sin_mecanizado",
    "mecanizado_esperado",
]

_SUBSECCIONES_LOGISTICA = [
    "tolerancia_peso_porcentaje",
    "estructura_umbral_mm",
]

_SUBSECCIONES_NOMENCLATURA = [
    "patrones",
    "prefijos_estado",
]

_CAMPOS_OBLIGATORIOS_CNC = ["excepciones"]

_CAMPOS_PATRON_CNC = ["patron", "tipo", "justifica_check"]


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def cargar_reglas(ruta: str | Path = "reglas.yaml") -> dict[str, Any]:
    """
    Lee reglas.yaml, valida estructura obligatoria y lo devuelve como dict.

    Args:
        ruta: ruta al archivo reglas.yaml (relativa o absoluta).

    Returns:
        dict con el contenido completo de reglas.yaml.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si faltan secciones obligatorias o la estructura es inválida.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"reglas.yaml no encontrado en: {ruta.resolve()}")

    with ruta.open(encoding="utf-8") as f:
        datos = yaml.safe_load(f)

    if not isinstance(datos, dict):
        raise ValueError("reglas.yaml debe ser un mapping YAML en el nivel raíz")

    _validar_secciones(datos, _SECCIONES_OBLIGATORIAS_REGLAS, "reglas.yaml")
    _validar_secciones(datos["layers"], _SUBSECCIONES_LAYERS, "reglas.yaml → layers")
    _validar_secciones(datos["tipologias"], _SUBSECCIONES_TIPOLOGIAS, "reglas.yaml → tipologias")
    _validar_secciones(datos["logistica"], _SUBSECCIONES_LOGISTICA, "reglas.yaml → logistica")
    _validar_secciones(datos["nomenclatura"], _SUBSECCIONES_NOMENCLATURA, "reglas.yaml → nomenclatura")
    _validar_materiales(datos["materiales"])
    _validar_cazoletas(datos["cazoletas_metod"])
    _validar_baldas(datos["baldas_dimensiones"])

    return datos


def cargar_reglas_cnc(ruta: str | Path = "reglas_cnc.yaml") -> dict[str, Any]:
    """
    Lee reglas_cnc.yaml, valida estructura y devuelve como dict.

    Args:
        ruta: ruta al archivo reglas_cnc.yaml (relativa o absoluta).

    Returns:
        dict con el contenido completo de reglas_cnc.yaml.

    Raises:
        FileNotFoundError: si el archivo no existe.
        ValueError: si la estructura es inválida.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"reglas_cnc.yaml no encontrado en: {ruta.resolve()}")

    with ruta.open(encoding="utf-8") as f:
        datos = yaml.safe_load(f)

    if not isinstance(datos, dict):
        raise ValueError("reglas_cnc.yaml debe ser un mapping YAML en el nivel raíz")

    _validar_secciones(datos, _CAMPOS_OBLIGATORIOS_CNC, "reglas_cnc.yaml")

    if not isinstance(datos["excepciones"], list):
        raise ValueError("reglas_cnc.yaml → excepciones debe ser una lista")

    for i, excepcion in enumerate(datos["excepciones"]):
        _validar_secciones(
            excepcion,
            _CAMPOS_PATRON_CNC,
            f"reglas_cnc.yaml → excepciones[{i}]",
        )

    return datos


# ---------------------------------------------------------------------------
# Helpers de validación (privados)
# ---------------------------------------------------------------------------

def _validar_secciones(
    datos: dict,
    campos_requeridos: list[str],
    contexto: str,
) -> None:
    faltantes = [c for c in campos_requeridos if c not in datos]
    if faltantes:
        raise ValueError(
            f"{contexto}: faltan campos obligatorios: {faltantes}"
        )


def _validar_materiales(materiales: Any) -> None:
    if not isinstance(materiales, dict):
        raise ValueError("reglas.yaml → materiales debe ser un mapping")
    for tablero, config in materiales.items():
        if "gamas_validas" not in config:
            raise ValueError(
                f"reglas.yaml → materiales.{tablero}: falta 'gamas_validas'"
            )
        if not isinstance(config["gamas_validas"], list) or not config["gamas_validas"]:
            raise ValueError(
                f"reglas.yaml → materiales.{tablero}.gamas_validas debe ser lista no vacía"
            )


def _validar_cazoletas(cazoletas: Any) -> None:
    if not isinstance(cazoletas, list) or not cazoletas:
        raise ValueError("reglas.yaml → cazoletas_metod debe ser una lista no vacía")
    for i, entrada in enumerate(cazoletas):
        for campo in ("alto_max", "cazoletas", "nota"):
            if campo not in entrada:
                raise ValueError(
                    f"reglas.yaml → cazoletas_metod[{i}]: falta campo '{campo}'"
                )


def _validar_baldas(baldas: Any) -> None:
    if not isinstance(baldas, list) or not baldas:
        raise ValueError("reglas.yaml → baldas_dimensiones debe ser una lista no vacía")
    for i, balda in enumerate(baldas):
        for campo in ("ancho", "alto", "herrajes"):
            if campo not in balda:
                raise ValueError(
                    f"reglas.yaml → baldas_dimensiones[{i}]: falta campo '{campo}'"
                )
