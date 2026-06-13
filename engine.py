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

from core.modelos import CheckResult, ExtraccionData, InformeFinal, OTData, Pieza
from core.extractor_despiece import leer_despiece
from core.extractor_etiquetas_ean import FilaEAN, FilaEtiqueta, leer_ean, leer_etiquetas
from core.extractor_dxf import DXFDoc, leer_todos_dxf
from core.extractor_extraccion import cargar_naming_default, leer_extraccion
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
    check_nesting_laca,
    check_geometria_prohibida,
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
from checks.checks_extraccion import (
    check_cabecera_ot,
    check_recuentos_criticos,
    check_logistica_envio,
    check_metros_canto,
    check_tableros_codificados,
    check_prioridad_inc,
    check_tabla_ids_vs_despiece,
    check_tabla_dimensiones_material,
    check_tabla_tipologia_mecanizado,
    check_tabla_tirador,
    check_baldas_herrajes,
    check_altillos,
    check_hornacinas,
    check_mueble_nevera,
)
from checks.checks_externos import check_csv_hubspot

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
    extraccion: ExtraccionData | None = None  # None → C-70..C-80 hacen SKIP, C-00 hace FAIL
    naming: dict[str, tuple[str, str]] = field(default_factory=dict)  # naming_extraccion.csv cargado
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
                         "albaran", "bultos", "destino_caja", "extraccion",
                         "pdfs_nesting", "otros"]
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
        elif _match(nombre, p.get("extraccion", "EXTRACCION_*")):
            grupos["extraccion"].append(nombre)
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
    reglas: dict,
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

    for nombre in clasificados.get("extraccion", []):
        try:
            archivos[nombre].seek(0)
            datos.extraccion = leer_extraccion(archivos[nombre], reglas)
        except Exception as exc:
            err.append(f"EXTRACCION '{nombre}': {exc}")

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
    csv_hubspot_existe: bool | None = None,
) -> list[CheckResult]:
    resultados: list[CheckResult] = []
    ot = datos.ot or _ot_vacia(id_proyecto)

    # Inventario (C-00..C-04)
    resultados.append(check_documentos_presentes(datos.nombres, reglas))
    resultados.append(check_id_consistente(
        datos.nombres, id_proyecto, ot, datos.extraccion, datos.filas_ean))
    resultados.append(check_nomenclatura(datos.nombres, reglas))
    resultados.append(check_num_dxf_vs_ot(datos.dxfs, ot))
    resultados.append(check_pdfs_nesting_vs_materiales(datos.nombres, datos.piezas, ot))

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
    resultados.append(check_nesting_laca(datos.dxfs, reglas))
    resultados.append(check_geometria_prohibida(datos.dxfs, reglas))

    # Bultos (C-50..C-56)
    resultados.append(check_num_bultos(datos.filas_ean, datos.n_bultos_pdf))
    resultados.append(check_piezas_asignadas(datos.piezas, datos.filas_ean))
    resultados.append(check_piezas_sin_duplicados(datos.filas_ean))
    resultados.append(check_formato_id_bulto(datos.filas_ean, id_proyecto))
    resultados.append(check_peso_total(datos.filas_ean, ot, reglas))
    resultados.append(check_envio_estructura(datos.piezas, datos.extraccion, reglas))
    resultados.append(check_codigo_destino_caja(datos.codigo_destino, id_proyecto))

    # Texto CNC (C-60..C-63)
    resultados.append(check_retales_en_ot(ot, datos.dxfs, reglas_cnc))
    resultados.append(check_sin_mecanizar_en_ot(datos.piezas, ot, reglas_cnc))
    resultados.append(check_observaciones_reconocidas(ot, reglas_cnc))
    resultados.append(check_observaciones_no_reconocidas(ot, reglas_cnc))

    # EXTRACCION (C-70..C-80): tercer testigo independiente
    if datos.extraccion is None:
        motivo = "EXTRACCION ausente (C-00 reporta el fallo)"
        for cid, desc in (
            ("C-70", "Cabecera (Nº OT, semana, fechas) EXTRACCION ↔ OT"),
            ("C-71", "Recuentos críticos (piezas, tiradores, ventilación, tensores) ↔ OT"),
            ("C-72", "Logística (palets + tipo de envío) coherente con OT"),
            ("C-73", "Metros de canto EXTRACCION ≈ OT (con tolerancia)"),
            ("C-74", "Tableros <COD>_tab decodificados ↔ tabla CORTE OT"),
            ("C-75", "Prioridad INC rellenada solo en -INC con valor válido"),
            ("C-76", "Tabla EXTRACCION: nº filas + conjunto IDs ↔ DESPIECE"),
            ("C-77", "Tabla EXTRACCION: dimensiones + material/gama/acabado ↔ DESPIECE"),
            ("C-78", "Tabla EXTRACCION: tipología + mecanizado ↔ DESPIECE"),
            ("C-79", "Tabla EXTRACCION: tirador/posición/apertura/color ↔ DESPIECE"),
            ("C-80", "Baldas con herrajes (EXTRACCION) ↔ DESPIECE tipología B"),
            ("C-81", "Altillos EXTRACCION ↔ OT (total + desglose por dimensión)"),
            ("C-82", "Nº de hornacinas EXTRACCION ↔ OT"),
            ("C-83", "Mueble de nevera EXTRACCION ↔ OT"),
        ):
            resultados.append(CheckResult(cid, desc, "SKIP", motivo, False, "Extraccion"))
    else:
        resultados.append(check_cabecera_ot(datos.extraccion, ot))
        resultados.append(check_recuentos_criticos(datos.extraccion, ot))
        resultados.append(check_logistica_envio(datos.extraccion, ot, reglas))
        resultados.append(check_metros_canto(datos.extraccion, ot, reglas))
        resultados.append(check_tableros_codificados(datos.extraccion, ot, datos.naming))
        resultados.append(check_prioridad_inc(datos.extraccion, reglas, id_proyecto))
        resultados.append(check_tabla_ids_vs_despiece(datos.extraccion, datos.piezas))
        resultados.append(check_tabla_dimensiones_material(datos.extraccion, datos.piezas))
        resultados.append(check_tabla_tipologia_mecanizado(datos.extraccion, datos.piezas))
        resultados.append(check_tabla_tirador(datos.extraccion, datos.piezas))
        resultados.append(check_baldas_herrajes(datos.extraccion, datos.piezas, reglas))
        resultados.append(check_altillos(datos.extraccion, ot))
        resultados.append(check_hornacinas(datos.extraccion, ot))
        resultados.append(check_mueble_nevera(datos.extraccion, ot))

    # Externos (C-84+)
    resultados.append(check_csv_hubspot(id_proyecto, csv_hubspot_existe))

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
    from drive.navegador import archivo_existe_en_carpeta
    import config

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

    datos = _extraer(archivos, clasificados, reglas)
    datos.naming = cargar_naming_default()
    for err in datos.errores_extraccion:
        log.warning("Extracción: %s", err)

    # C-84: ¿existe el CSV de exportación a HubSpot? Resolver acá (no en
    # los checks) para que las pruebas no tengan que mockear Drive.
    try:
        csv_hubspot_existe = archivo_existe_en_carpeta(
            servicio, config.DRIVE_HUBSPOT_EXPORT_ID, f"{id_proyecto}.csv"
        )
    except Exception as exc:
        log.warning("C-84: no se pudo consultar carpeta HubSpot: %s", exc)
        csv_hubspot_existe = None

    cliente = datos.ot.cliente if datos.ot else ""
    checks = _ejecutar_checks(
        datos, id_proyecto, reglas, reglas_cnc, csv_hubspot_existe
    )

    return InformeFinal(
        id_proyecto=id_proyecto,
        cliente=cliente,
        responsable=responsable,
        semana=semana,
        checks=checks,
    )
