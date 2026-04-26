"""
engine.py — Orquestador principal de verificación.

Flujo:
  1. Descarga todos los archivos de la carpeta del proyecto en memoria.
  2. Clasifica los archivos por tipo (usando los patrones de reglas.yaml).
  3. Extrae datos con los extractores de core/.
  4. Ejecuta los 42 checks en orden (C-00..C-63).
  5. Devuelve InformeFinal con todos los CheckResult.

Las reglas se cargan UNA vez en la app y se pasan como parámetros.
"""

from __future__ import annotations

import fnmatch
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from core.modelos import CheckResult, InformeFinal, OTData, Pieza
from core.extractor_despiece import leer_despiece
from core.extractor_etiquetas_ean import FilaEAN, FilaEtiqueta, leer_ean, leer_etiquetas
from core.extractor_dxf import DXFDoc, leer_todos_dxf
from core.extractor_ot import leer_ot
from core.extractor_pdfs_logistica import leer_n_bultos, leer_codigo_destino

from checks.checks_inventario import (
    check_documentos_presentes,
    check_id_consistente,
    check_nomenclatura,
    check_num_dxf_vs_ot,
    check_pdfs_nesting_vs_materiales,
)
from checks.checks_piezas import (
    check_num_piezas,
    check_ids_despiece_en_etiquetas,
    check_ids_despiece_en_ot,
    check_dimensiones,
    check_material_consistente,
    check_material_tablero,
    check_acabados,
    check_sufijo_tipologia,
    check_apertura_puertas,
    check_apertura_pax,
    check_pax_mecanizado,
    check_sin_apertura_cajones,
    check_tirador_completo,
    check_posicion_sin_tirador,
    check_cazoletas,
    check_baldas_dimensiones,
    check_cajones_dimensiones,
    check_mec_torn_en_ancho_especial,
    check_mecanizado_rodapies,
    check_tirador_en_sin_mecanizado,
    check_alto_puerta_sufijo,
    check_tipologia_inferible,
)
from checks.checks_dxf import (
    check_layer_control,
    check_layer_0_sin_geometria,
    check_layers_rhino_ausentes,
    check_layer_anotaciones,
    check_layer_biselar_lam_lin,
    check_corte_perimetral,
    check_layer_desbaste_tirador,
    check_handcut_vs_tiradores,
    check_cajones_drill,
    check_bisagras_pocket,
    check_ventilacion_rejilla,
    check_mecanismo_hornacina,
    check_tirantes,
    check_layers_desuso,
    check_distancia_bisagras,
)
from checks.checks_bultos import (
    check_num_bultos,
    check_piezas_asignadas,
    check_piezas_sin_duplicados,
    check_formato_id_bulto,
    check_peso_total,
    check_envio_estructura,
    check_codigo_destino_caja,
)
from checks.checks_texto import (
    check_retales_en_ot,
    check_sin_mecanizar_en_ot,
    check_observaciones_reconocidas,
    check_observaciones_no_reconocidas,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Datos extraídos del proyecto (contenedor para pasar a los checks)
# ---------------------------------------------------------------------------

@dataclass
class DatosProyecto:
    """Todos los datos extraídos de los archivos del proyecto."""

    nombres: list[str] = field(default_factory=list)
    piezas: list[Pieza] = field(default_factory=list)
    filas_etiqueta: list[FilaEtiqueta] = field(default_factory=list)
    filas_ean: list[FilaEAN] = field(default_factory=list)
    ot: OTData | None = None
    dxfs: list[DXFDoc] = field(default_factory=list)
    n_bultos_pdf: int | None = None      # None → SKIP C-50
    codigo_destino: str | None = None    # None → SKIP C-56
    errores_extraccion: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Clasificación de archivos
# ---------------------------------------------------------------------------

def _match(nombre: str, patron: str) -> bool:
    return fnmatch.fnmatch(nombre.upper(), patron.upper())


def _es_nesting_pdf(nombre: str) -> bool:
    n = nombre.upper()
    return n.endswith(".PDF") and any(m in n for m in ("_PLY_", "_MDF_"))


def _clasificar(nombres: list[str], reglas: dict) -> dict[str, list[str]]:
    p = reglas["nomenclatura"]["patrones"]
    grupos: dict[str, list[str]] = {
        t: [] for t in ["despiece", "etiquetas", "ean", "ot", "dxf",
                         "albaran", "bultos", "destino_caja", "pdfs_nesting", "otros"]
    }
    for nombre in nombres:
        if _match(nombre, p["despiece"]):
            grupos["despiece"].append(nombre)
        elif _match(nombre, p["etiquetas"]):
            grupos["etiquetas"].append(nombre)
        elif _match(nombre, p["ean"]) or _match(nombre, p.get("ean_alt", "EAN_LOGISTIC_*")):
            grupos["ean"].append(nombre)
        elif _match(nombre, p["ot"]):
            grupos["ot"].append(nombre)
        elif nombre.lower().endswith(".dxf"):
            grupos["dxf"].append(nombre)
        elif _match(nombre, p.get("albaran", "ALBARAN_*")) or \
             _match(nombre, p.get("albaran_alt", "ALBARÁN_*")):
            grupos["albaran"].append(nombre)
        elif _match(nombre, p.get("bultos", "BULTOS_*")):
            grupos["bultos"].append(nombre)
        elif _match(nombre, p.get("destino_caja", "DESTINO CAJA_*")):
            grupos["destino_caja"].append(nombre)
        elif _es_nesting_pdf(nombre):
            grupos["pdfs_nesting"].append(nombre)
        elif nombre.lower().endswith(".pdf"):
            grupos["otros"].append(nombre)
        else:
            grupos["otros"].append(nombre)
    return grupos


# ---------------------------------------------------------------------------
# Extracción de datos (tolerante a errores)
# ---------------------------------------------------------------------------

def _extraer(
    archivos: dict[str, io.BytesIO],
    clasificados: dict[str, list[str]],
) -> DatosProyecto:
    datos = DatosProyecto(nombres=list(archivos.keys()))
    err = datos.errores_extraccion

    for nombre in clasificados["despiece"]:
        try:
            archivos[nombre].seek(0)
            datos.piezas = leer_despiece(archivos[nombre])
        except Exception as exc:
            err.append(f"DESPIECE '{nombre}': {exc}")

    for nombre in clasificados["etiquetas"]:
        try:
            archivos[nombre].seek(0)
            datos.filas_etiqueta = leer_etiquetas(archivos[nombre])
        except Exception as exc:
            err.append(f"ETIQUETAS '{nombre}': {exc}")

    for nombre in clasificados["ean"]:
        try:
            archivos[nombre].seek(0)
            datos.filas_ean = leer_ean(archivos[nombre])
        except Exception as exc:
            err.append(f"EAN '{nombre}': {exc}")

    for nombre in clasificados["ot"]:
        try:
            archivos[nombre].seek(0)
            datos.ot = leer_ot(archivos[nombre])
        except Exception as exc:
            err.append(f"OT '{nombre}': {exc}")

    for nombre in clasificados["bultos"]:
        try:
            archivos[nombre].seek(0)
            n = leer_n_bultos(archivos[nombre])
            if n is not None:
                datos.n_bultos_pdf = n
        except Exception as exc:
            err.append(f"BULTOS '{nombre}': {exc}")

    for nombre in clasificados["destino_caja"]:
        try:
            archivos[nombre].seek(0)
            codigo = leer_codigo_destino(archivos[nombre])
            if codigo is not None:
                datos.codigo_destino = codigo
        except Exception as exc:
            err.append(f"DESTINO CAJA '{nombre}': {exc}")

    dxf_buffers = {n: archivos[n] for n in clasificados["dxf"] if n in archivos}
    if dxf_buffers:
        try:
            todos_dxf = leer_todos_dxf(dxf_buffers)
            # Excluir DXFs sin número de tablero (_T1, _T2…): son exports
            # combinados ("TODOS LOS TABLEROS") que duplican entidades y
            # provocan doble conteo en checks de HANDCUT, DRILL, etc.
            datos.dxfs = [d for d in todos_dxf if d.tablero_num > 0]
            if not datos.dxfs and todos_dxf:
                # Si ninguno tiene sufijo _TN (proyecto con un solo tablero sin
                # numerar), usar todos para no perder información.
                datos.dxfs = todos_dxf
        except Exception as exc:
            err.append(f"DXFs: {exc}")

    return datos


# ---------------------------------------------------------------------------
# Ejecución de checks
# ---------------------------------------------------------------------------

def _ot_vacia(id_proyecto: str) -> OTData:
    return OTData(id_proyecto, "", "", 0, 0.0, 0)


def _ejecutar_checks(
    datos: DatosProyecto,
    id_proyecto: str,
    reglas: dict,
    reglas_cnc: dict,
) -> list[CheckResult]:
    resultados: list[CheckResult] = []
    ot = datos.ot or _ot_vacia(id_proyecto)

    # Inventario (C-00..C-04)
    resultados.append(check_documentos_presentes(datos.nombres, reglas))
    resultados.append(check_id_consistente(datos.nombres, id_proyecto))
    resultados.append(check_nomenclatura(datos.nombres, reglas))
    resultados.append(check_num_dxf_vs_ot(datos.dxfs, ot))
    resultados.append(check_pdfs_nesting_vs_materiales(datos.nombres, datos.piezas))

    # Piezas (C-10..C-17, C-20..C-29)
    resultados.append(check_num_piezas(datos.piezas, datos.filas_etiqueta, ot))
    resultados.append(check_ids_despiece_en_etiquetas(datos.piezas, datos.filas_etiqueta))
    resultados.append(check_ids_despiece_en_ot(datos.piezas, ot))
    resultados.append(check_dimensiones(datos.piezas, datos.filas_etiqueta))
    resultados.append(check_material_consistente(datos.piezas, datos.filas_etiqueta))
    resultados.append(check_material_tablero(datos.piezas, reglas))
    resultados.append(check_acabados(datos.piezas, reglas))
    resultados.append(check_sufijo_tipologia(datos.piezas, reglas))
    resultados.append(check_apertura_puertas(datos.piezas, reglas))
    resultados.append(check_apertura_pax(datos.piezas, reglas))
    resultados.append(check_pax_mecanizado(datos.piezas))
    resultados.append(check_sin_apertura_cajones(datos.piezas, reglas))
    resultados.append(check_tirador_completo(datos.piezas))
    resultados.append(check_posicion_sin_tirador(datos.piezas))
    resultados.append(check_cazoletas(datos.piezas, reglas))
    resultados.append(check_baldas_dimensiones(datos.piezas, reglas))
    resultados.append(check_cajones_dimensiones(datos.piezas, reglas))
    resultados.append(check_mec_torn_en_ancho_especial(datos.piezas))
    resultados.append(check_mecanizado_rodapies(datos.piezas, reglas))
    resultados.append(check_tirador_en_sin_mecanizado(datos.piezas, reglas))
    resultados.append(check_alto_puerta_sufijo(datos.piezas, reglas))
    resultados.append(check_tipologia_inferible(datos.piezas))

    # DXF (C-30..C-43)
    resultados.append(check_layer_control(datos.dxfs, reglas))
    resultados.append(check_layer_0_sin_geometria(datos.dxfs, reglas))
    resultados.append(check_layers_rhino_ausentes(datos.dxfs, reglas))
    resultados.append(check_layer_anotaciones(datos.dxfs, reglas))
    resultados.append(check_layer_biselar_lam_lin(datos.dxfs, reglas))
    resultados.append(check_corte_perimetral(datos.dxfs, reglas))
    resultados.append(check_layer_desbaste_tirador(datos.dxfs, datos.piezas, reglas))
    resultados.append(check_handcut_vs_tiradores(datos.dxfs, ot, reglas))
    resultados.append(check_cajones_drill(datos.dxfs, datos.piezas, reglas))
    resultados.append(check_bisagras_pocket(datos.dxfs, datos.piezas, reglas))
    resultados.append(check_ventilacion_rejilla(datos.dxfs, ot, reglas))
    resultados.append(check_mecanismo_hornacina(datos.dxfs, ot, reglas))
    resultados.append(check_tirantes(datos.dxfs, ot, reglas))
    resultados.append(check_layers_desuso(datos.dxfs, reglas))
    resultados.append(check_distancia_bisagras(datos.dxfs, reglas))

    # Bultos (C-50..C-56)
    resultados.append(check_num_bultos(datos.filas_ean, datos.n_bultos_pdf))
    resultados.append(check_piezas_asignadas(datos.piezas, datos.filas_ean))
    resultados.append(check_piezas_sin_duplicados(datos.filas_ean))
    resultados.append(check_formato_id_bulto(datos.filas_ean, id_proyecto))
    resultados.append(check_peso_total(datos.filas_ean, ot, reglas))
    resultados.append(check_envio_estructura(datos.piezas, ot, reglas))
    resultados.append(check_codigo_destino_caja(datos.codigo_destino, id_proyecto))

    # Texto CNC (C-60..C-63)
    resultados.append(check_retales_en_ot(ot, datos.dxfs, reglas_cnc))
    resultados.append(check_sin_mecanizar_en_ot(datos.piezas, ot, reglas_cnc))
    resultados.append(check_observaciones_reconocidas(ot, reglas_cnc))
    resultados.append(check_observaciones_no_reconocidas(ot, reglas_cnc))

    return resultados


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def verificar_proyecto(
    folder_id: str,
    id_proyecto: str,
    responsable: str,
    semana: str,
    servicio: Any,
    reglas: dict,
    reglas_cnc: dict,
) -> InformeFinal:
    """
    Descarga, extrae y verifica todos los archivos del proyecto en Drive.

    Args:
        folder_id:   ID de la carpeta Drive del proyecto.
        id_proyecto: Ej. "EU-21822".
        responsable: Nombre del responsable (para el informe).
        semana:      Ej. "Semana 18" (para el informe).
        servicio:    Cliente Drive v3 autenticado.
        reglas:      Dict cargado por cargar_reglas().
        reglas_cnc:  Dict cargado por cargar_reglas_cnc().

    Returns:
        InformeFinal con todos los CheckResult y el estado global.
    """
    from drive.descargador import descargar_carpeta

    log.info("Descargando archivos de %s (%s)…", id_proyecto, folder_id)
    archivos = descargar_carpeta(servicio, folder_id)
    log.info("%d archivos descargados", len(archivos))

    clasificados = _clasificar(list(archivos.keys()), reglas)
    log.info(
        "Clasificados: despiece=%d etiquetas=%d ean=%d ot=%d dxf=%d pdfs=%d",
        len(clasificados["despiece"]), len(clasificados["etiquetas"]),
        len(clasificados["ean"]), len(clasificados["ot"]),
        len(clasificados["dxf"]), len(clasificados["pdfs_nesting"]),
    )

    datos = _extraer(archivos, clasificados)
    for err in datos.errores_extraccion:
        log.warning("Extracción: %s", err)

    cliente = datos.ot.cliente if datos.ot else ""
    checks = _ejecutar_checks(datos, id_proyecto, reglas, reglas_cnc)

    return InformeFinal(
        id_proyecto=id_proyecto,
        cliente=cliente,
        responsable=responsable,
        semana=semana,
        checks=checks,
    )
