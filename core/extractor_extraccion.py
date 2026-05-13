"""
core/extractor_extraccion.py — Lee el CSV EXTRACCION_<ID>_<Cliente>.csv.

El CSV tiene dos secciones:
  Sección A — pares clave,valor con datos agregados del proyecto.
  Sección B — tabla con una fila por pieza (cabecera: 'ID Proyecto,...').

La frontera entre secciones se detecta por la aparición de una fila cuya
primera celda se normaliza a 'id proyecto'.

Particularidades del documento:
  - La gama 'Laminado' se codifica como HPL (no LAM como en el resto del
    sistema). El extractor traduce HPL→LAM al rellenar FilaExtraccion para que
    los checks de cruce con DESPIECE funcionen sin transformaciones extra.
  - Las claves de cabecera tipo <COD>_tab (ej. 'LAC_Zaf_tab') indican nº de
    tableros por combinación gama+acabado. Se almacenan en
    `tableros_codificados` preservando el case original para que el check C-74
    pueda decodificarlas con la tabla canónica (core/naming_extraccion.csv).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import BinaryIO

from core.modelos import ExtraccionData, FilaExtraccion


# ---------------------------------------------------------------------------
# Normalización de gama y material (solo aplica al EXTRACCION)
# ---------------------------------------------------------------------------

#: Mapea cualquier variante de gama presente en EXTRACCION a su código interno.
#: 'HPL' es la codificación propia del EXTRACCION para Laminado.
_GAMA_NORM: dict[str, str] = {
    "LAMINADO": "LAM",
    "LINOLEO":  "LIN",
    "LINÓLEO":  "LIN",
    "LACA":     "LAC",
    "WOOD":     "WOO",
    "HPL":      "LAM",
    # idempotente para casos ya normalizados
    "LAM":      "LAM",
    "LIN":      "LIN",
    "LAC":      "LAC",
    "WOO":      "WOO",
}

#: Tablero base inferido a partir de la gama (cuando el campo Material está vacío).
_GAMA_A_MATERIAL: dict[str, str] = {
    "LAM": "PLY",
    "LIN": "PLY",
    "LAC": "MDF",
    "WOO": "MDF",
}


# ---------------------------------------------------------------------------
# Helpers de bajo nivel (encoding, normalización, parsing numérico)
# ---------------------------------------------------------------------------

_ENCODINGS = ("utf-8-sig", "utf-8", "latin-1", "cp1252")

_TILDES = str.maketrans(
    "áéíóúàèìòùñÁÉÍÓÚÀÈÌÒÙÑ",
    "aeiouaeiounAEIOUAEIOUN",
)


def _decodificar(raw: bytes) -> str:
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def _abrir_como_texto(origen: BinaryIO | Path | str) -> str:
    if isinstance(origen, (str, Path)):
        return _decodificar(Path(origen).read_bytes())
    raw = origen.read()
    if isinstance(raw, str):
        return raw
    return _decodificar(raw)


def _normalizar_clave(texto: str) -> str:
    """Minúsculas, sin tildes, sin espacios sobrantes — para lookup en alias."""
    return texto.strip().lower().translate(_TILDES)


def _detectar_separador(primera_linea: str) -> str:
    return ";" if primera_linea.count(";") >= primera_linea.count(",") else ","


def _int_o(valor: str, defecto: int = 0) -> int:
    try:
        return int(float(valor.strip().replace(",", ".")))
    except (ValueError, AttributeError):
        return defecto


def _float_o(valor: str, defecto: float = 0.0) -> float:
    try:
        # "63 mt" → "63" → 63.0;  "62,32" → 62.32
        return float(valor.strip().split()[0].replace(",", "."))
    except (ValueError, AttributeError, IndexError):
        return defecto


# ---------------------------------------------------------------------------
# Detección de secciones y de claves especiales
# ---------------------------------------------------------------------------

def _es_clave_tableros(clave_orig: str) -> bool:
    """True si la clave tiene formato <PREFIJO>_..._tab (Sección A).

    Ejemplos: LAC_Zaf_tab, HPL_Pal_tab, WOO_Cer_M_tab.
    """
    s = clave_orig.strip()
    return s.lower().endswith("_tab") and "_" in s[:-4]


def _es_cabecera_tabla(fila: list[str]) -> bool:
    """True si la primera celda de la fila se normaliza a 'id proyecto'."""
    if not fila:
        return False
    return _normalizar_clave(fila[0]) == "id proyecto"


# ---------------------------------------------------------------------------
# Alias para las columnas de la tabla de piezas (Sección B)
# ---------------------------------------------------------------------------

_ALIAS_TABLA: dict[str, str] = {
    "id proyecto":          "id_proyecto",
    "nombre cliente":       "cliente",
    "cliente":              "cliente",
    "pieza":                "id_pieza",
    "id pieza":             "id_pieza",
    "tipologia":            "tipologia",
    "ancho":                "ancho",
    "alto":                 "alto",
    "material":             "material",
    "gama":                 "gama",
    "acabado":              "acabado",
    "mecanizado":           "mecanizado",
    "tirador":              "tirador",
    "posicion de tirador":  "posicion_tirador",
    "posicion tirador":     "posicion_tirador",
    "apertura":             "apertura",
    "color tirador":        "color_tirador",
    "cnc":                  "cnc",
    "ac2":                  "ac2",
    "embalaje":             "embalaje",
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def leer_extraccion(
    origen: BinaryIO | Path | str,
    reglas: dict,
) -> ExtraccionData:
    """Lee el CSV EXTRACCION y devuelve un ExtraccionData completo.

    Args:
        origen:  BytesIO, Path o str con la ruta al CSV.
        reglas:  dict cargado por cargar_reglas() — usa reglas['extraccion']
                 ['alias_cabecera'] para mapear las claves de la Sección A.

    Returns:
        ExtraccionData con cabecera (Sección A) y tabla de piezas (Sección B).

    Raises:
        ValueError: si el CSV está vacío o no contiene la cabecera 'ID Proyecto'.
    """
    texto = _abrir_como_texto(origen)
    lineas = texto.splitlines()
    if not lineas:
        raise ValueError("EXTRACCION: CSV vacío")

    sep = _detectar_separador(lineas[0])
    reader = csv.reader(io.StringIO(texto), delimiter=sep)

    cfg = (reglas or {}).get("extraccion", {}) or {}
    alias_cab = {
        _normalizar_clave(k): v
        for k, v in (cfg.get("alias_cabecera", {}) or {}).items()
    }

    data = ExtraccionData()
    en_seccion_a = True
    cabecera_tabla: list[str] | None = None

    for fila in reader:
        if not fila or not any(c.strip() for c in fila):
            continue  # fila vacía → ignorar

        if en_seccion_a:
            if _es_cabecera_tabla(fila):
                en_seccion_a = False
                cabecera_tabla = [_normalizar_clave(c) for c in fila]
                continue

            clave_orig = fila[0].strip()
            valor = fila[1].strip() if len(fila) >= 2 else ""

            # Claves <COD>_tab: van aparte, preservando el case original para
            # que el check C-74 las decodifique con la tabla canónica.
            if _es_clave_tableros(clave_orig):
                if valor:
                    data.tableros_codificados[clave_orig] = _int_o(valor)
                continue

            campo = alias_cab.get(_normalizar_clave(clave_orig))
            if campo is None:
                if clave_orig:
                    data.claves_desconocidas.append(clave_orig)
                continue

            _asignar_campo(data, campo, valor)

        else:
            if cabecera_tabla is None:
                continue  # defensivo (no debería ocurrir)
            fila_pieza = _construir_fila_pieza(fila, cabecera_tabla)
            if fila_pieza is not None:
                data.piezas_tabla.append(fila_pieza)

    if cabecera_tabla is None:
        raise ValueError(
            "EXTRACCION: no se encontró la cabecera de la tabla de piezas "
            "(se esperaba una fila comenzando por 'ID Proyecto')"
        )

    # Si la Sección A no traía id_proyecto/cliente, los recuperamos de la
    # primera fila de la tabla (donde se repiten por pieza).
    if not data.id_proyecto and data.piezas_tabla:
        data.id_proyecto = data.piezas_tabla[0].id_proyecto
    if not data.cliente and data.piezas_tabla:
        data.cliente = data.piezas_tabla[0].cliente

    return data


# ---------------------------------------------------------------------------
# Asignación de campos de la Sección A
# ---------------------------------------------------------------------------

def _asignar_campo(data: ExtraccionData, campo: str, valor: str) -> None:
    """Asigna `valor` al atributo `campo` de `data`, con conversión adecuada."""
    if campo == "altillos_seccion":
        return  # etiqueta de sección sin valor útil
    if campo == "metros_canto":
        data.metros_canto = _float_o(valor)
        return
    if campo in (
        "numero_ot", "semana", "fecha_entrada", "fecha_salida", "prioridad_inc",
    ):
        setattr(data, campo, valor)
        return
    if campo in (
        "piezas", "tiradores", "tensores", "rejillas_ventilacion",
        "hornacinas", "palets", "mueble_nevera", "baldas_2h", "baldas_3h",
        "caja_grande", "caja_pequena", "estructura_grande", "estructura_pequena",
    ):
        setattr(data, campo, _int_o(valor))
        return
    # Campos no soportados se ignoran silenciosamente


# ---------------------------------------------------------------------------
# Construcción de FilaExtraccion (Sección B)
# ---------------------------------------------------------------------------

def _construir_fila_pieza(
    fila: list[str],
    cabecera_norm: list[str],
) -> FilaExtraccion | None:
    """Construye una FilaExtraccion. Devuelve None si la fila no tiene id_pieza."""
    datos: dict[str, str] = {}
    for idx, clave_norm in enumerate(cabecera_norm):
        if idx >= len(fila):
            break
        campo = _ALIAS_TABLA.get(clave_norm)
        if campo and campo not in datos:
            datos[campo] = fila[idx].strip()

    id_pieza = datos.get("id_pieza", "")
    if not id_pieza:
        return None

    gama_raw = datos.get("gama", "").upper()
    gama = _GAMA_NORM.get(gama_raw, gama_raw)

    material_raw = datos.get("material", "").upper()
    # Si la fila declara HPL como material (uso ocasional), lo traducimos a PLY
    if material_raw == "HPL":
        material_raw = "PLY"
    # Si no hay material declarado pero hay gama, lo inferimos
    if not material_raw and gama:
        material_raw = _GAMA_A_MATERIAL.get(gama, "")

    return FilaExtraccion(
        id_proyecto=datos.get("id_proyecto", ""),
        cliente=datos.get("cliente", ""),
        id_pieza=id_pieza,
        tipologia=datos.get("tipologia", "").upper(),
        ancho=_int_o(datos.get("ancho", "0")),
        alto=_int_o(datos.get("alto", "0")),
        material=material_raw,
        gama=gama,
        acabado=datos.get("acabado", ""),
        mecanizado=datos.get("mecanizado", ""),
        tirador=datos.get("tirador", ""),
        posicion_tirador=datos.get("posicion_tirador", ""),
        apertura=datos.get("apertura", "").upper(),
        color_tirador=datos.get("color_tirador", ""),
        cnc=datos.get("cnc", ""),
        ac2=datos.get("ac2", ""),
        embalaje=datos.get("embalaje", ""),
    )


# ---------------------------------------------------------------------------
# Carga del CSV de mapeo Gama+Acabado → <COD>_tab (usado por el check C-74)
# ---------------------------------------------------------------------------

def cargar_naming_default() -> dict[str, tuple[str, str]]:
    """Carga el CSV de naming desde su ubicación canónica (junto a este módulo).

    Útil para que la app y los tests no tengan que conocer la ruta exacta.
    Devuelve {} silenciosamente si el archivo no existe — los checks que lo
    necesiten harán SKIP.
    """
    ruta = Path(__file__).parent / "naming_extraccion.csv"
    if not ruta.exists():
        return {}
    return cargar_naming(ruta)


def cargar_naming(ruta: str | Path) -> dict[str, tuple[str, str]]:
    """Devuelve {cod_tab_lower: (gama_largo, acabado_largo)} desde el CSV de mapeo.

    La clave se normaliza a minúsculas para absorber inconsistencias internas
    del documento fuente (p. ej. 'LAC_bla_tab' vs 'LAC_Bla_tab').

    Args:
        ruta: ruta al CSV con columnas 'Gama,Acabado,Nombre interno'.

    Raises:
        FileNotFoundError: si el CSV no existe.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(f"naming_extraccion.csv no encontrado en: {ruta}")
    texto = _decodificar(ruta.read_bytes())
    reader = csv.DictReader(io.StringIO(texto))
    mapa: dict[str, tuple[str, str]] = {}
    for fila in reader:
        gama = (fila.get("Gama") or "").strip()
        acab = (fila.get("Acabado") or "").strip()
        cod = (fila.get("Nombre interno") or "").strip()
        if gama and acab and cod:
            mapa[cod.lower()] = (gama, acab)
    return mapa


def cod_tab_a_clave_canonica(
    cod_tab: str,
    naming: dict[str, tuple[str, str]],
) -> str | None:
    """Decodifica '<COD>_tab' a la clave canónica 'MATERIAL_GAMA_Acabado'.

    Args:
        cod_tab: clave tal y como aparece en el EXTRACCION (ej. 'LAC_Zaf_tab').
        naming:  dict devuelto por cargar_naming().

    Returns:
        Clave canónica 'MDF_LAC_Zafiro' o None si el código no se reconoce.
    """
    entrada = naming.get(cod_tab.lower())
    if entrada is None:
        return None
    gama_largo, acabado = entrada
    gama_corta = _GAMA_NORM.get(gama_largo.upper(), gama_largo.upper())
    material = _GAMA_A_MATERIAL.get(gama_corta, "")
    if not material:
        return None
    return f"{material}_{gama_corta}_{acabado}"
