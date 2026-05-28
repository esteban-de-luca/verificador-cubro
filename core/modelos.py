"""
core/modelos.py — Estructuras de datos del motor de verificación.

Todas las funciones de check reciben instancias de estos dataclasses, nunca
dicts crudos. Esto hace los checks autodocumentados y seguros de tipo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Resultado de un checkpoint
# ---------------------------------------------------------------------------

#: Valores válidos para CheckResult.resultado.
RESULTADOS_VALIDOS = frozenset({"PASS", "FAIL", "WARN", "SKIP"})

#: Grupos válidos para CheckResult.grupo.
GRUPOS_VALIDOS = frozenset({
    "Inventario", "Piezas", "Material",
    "Mecanizados", "Tiradores", "DXF", "Logistica", "Texto CNC",
    "Extraccion", "Externo",
})


@dataclass
class CheckResult:
    """Resultado de un checkpoint individual."""

    id: str          # Ej. "C-36"
    desc: str        # Descripción legible del check
    resultado: str   # PASS | FAIL | WARN | SKIP
    detalle: str     # Texto con el motivo del resultado
    bloquea: bool    # True → bloquea entrada a producción si FAIL
    grupo: str       # Categoría para agrupar en el informe

    def __post_init__(self) -> None:
        if self.resultado not in RESULTADOS_VALIDOS:
            raise ValueError(
                f"CheckResult.resultado inválido: {self.resultado!r}. "
                f"Debe ser uno de {sorted(RESULTADOS_VALIDOS)}"
            )
        if self.grupo not in GRUPOS_VALIDOS:
            raise ValueError(
                f"CheckResult.grupo inválido: {self.grupo!r}. "
                f"Debe ser uno de {sorted(GRUPOS_VALIDOS)}"
            )

    @property
    def es_error_critico(self) -> bool:
        """True si el check falló Y bloquea la entrada a producción."""
        return self.resultado == "FAIL" and self.bloquea

    @property
    def es_advertencia(self) -> bool:
        return self.resultado == "WARN"


# ---------------------------------------------------------------------------
# Pieza (fila del DESPIECE)
# ---------------------------------------------------------------------------

@dataclass
class Pieza:
    """Una pieza del DESPIECE: la fuente de verdad para todos los checks."""

    id: str                        # "M2-P1", "E1", "R1", etc.
    ancho: int                     # mm
    alto: int                      # mm
    material: str                  # "PLY" | "MDF"
    gama: str                      # "LAM" | "LIN" | "LAC" | "WOO"
    acabado: str                   # "Pale", "Blanco", etc.
    tipologia: str                 # "P" | "C" | "X" | "E" | "R" | "RV" | "T" | "L" | "B" | "H" | "TBE" | "FE" | "F" | "" (no inferible)
    mecanizado: str = ""           # "cazta." | "torn." | "vent." | "" etc.
    tirador: str = ""              # "Round" | "Bar" | "Knob" | ""
    posicion_tirador: str = ""     # "1"–"5" | ""
    color_tirador: str = ""        # "Cerezo" | "Inox" | ""
    apertura: str = ""             # "I" | "D" | ""

    @property
    def tiene_tirador(self) -> bool:
        return bool(self.tirador.strip())

    @property
    def tiene_apertura(self) -> bool:
        return self.apertura.strip() in ("I", "D")

    @property
    def clave_material(self) -> str:
        """Clave compuesta para PDFs de nesting: MATERIAL_GAMA_ACABADO."""
        return f"{self.material}_{self.gama}_{self.acabado}"


# ---------------------------------------------------------------------------
# Bulto (fila de EAN LOGISTIC)
# ---------------------------------------------------------------------------

@dataclass
class Bulto:
    """Un bulto del EAN LOGISTIC."""

    id_bulto: str        # "CUB-EU-21822-1-5"
    numero: int          # N (el enésimo bulto de este proyecto)
    total: int           # Total de bultos del proyecto
    peso_kg: float       # Peso declarado en kg
    piezas: list[str] = field(default_factory=list)  # IDs de piezas asignadas


# ---------------------------------------------------------------------------
# Datos de la Orden de Trabajo
# ---------------------------------------------------------------------------

@dataclass
class OTData:
    """Información extraída del PDF de la Orden de Trabajo."""

    id_proyecto: str                            # "EU-21822"
    cliente: str                                # "Sabine Jennes"
    semana: str                                 # "Semana 18"
    num_piezas: int                             # Total piezas en Packing List OT
    peso_total_kg: float                        # Peso bruto total
    num_tiradores: int                          # Total tiradores declarados
    tableros: dict[str, int] = field(default_factory=dict)      # {clave_material: n_tableros} — solo columnas con cantidad declarada
    materiales_sin_cantidad: list[str] = field(default_factory=list)  # claves de materiales en INFORMACION DE CORTE sin '# Tableros' (C-03)
    num_tableros_total: int | None = None                        # "Cantidad de tableros: N" en cabecera — None si falta (C-03)
    observaciones_cnc: list[str] = field(default_factory=list)  # Observaciones CNC
    observaciones_produccion: list[str] = field(default_factory=list)  # Obs. producción
    # Campos opcionales — se rellenan si el extractor los detecta
    ids_piezas: list[str] = field(default_factory=list)  # IDs individuales del Packing List (C-12)
    num_ventilacion: int = 0          # Nº rejillas ventilación declaradas (C-40)
    colgadores_hornacina: int | None = None   # OT declara cantidad de colgadores de hornacina: 0="No", N≥1=cantidad, None=ausente (C-41)
    tiene_tensores: bool | None = None    # OT declara tensores (C-42)
    modelos_tiradores: list[str] = field(default_factory=list)  # Modelos de tirador: ["Round"], ["Superline", "Pill"]…
    tiradores_por_modelo: dict[str, int] = field(default_factory=dict)  # {"Plantea": 9, "Round": 4} — empareja modelo con su recuento (C-37)
    # Campos usados por los checks de cruce con EXTRACCION (C-70..C-73, C-80)
    numero_ot: str = ""                  # "Nº de OT 5074" → "5074"
    fecha_entrada: str = ""              # "Fecha entrada a corte: 25/05/2026" → "25/05/2026"
    fecha_salida: str = ""               # "Fecha salida de taller: 05/06/2026" → "05/06/2026"
    num_palets: int | None = None        # "Cantidad de palets: 1 ud." → 1; None si ausente
    modelo_envio: str = ""               # "Modelo de envío: Caja grande" → "Caja grande"
    metros_canto: float = 0.0            # "Mts lineales de corte: 62,32 mt" → 62.32
    # Otros elementos del bloque "Otros elementos:" (C-81, C-82, C-83)
    altillos_dims: dict[str, int] = field(default_factory=dict)  # {"997x480x580": 4, "497x480x580": 2}
    num_hornacinas: int = 0              # "Cantidad de hornacinas:4 uds" → 4; 0 si no aparece
    tiene_mueble_nevera: bool = False    # "Mueble de nevera 75x60x220 cm" presente → True


# ---------------------------------------------------------------------------
# Documento DXF (un archivo = un tablero)
# ---------------------------------------------------------------------------

@dataclass
class DXFDoc:
    """Datos extraídos de un fichero DXF de nesting."""

    nombre: str                  # nombre del archivo, ej. "EU21822_..._T1.dxf"
    tablero_num: int             # número extraído del nombre (*_T1.dxf → 1)
    material: str                # "PLY" | "MDF" — inferido del nombre del archivo
    gama: str                    # "LAM" | "LIN" | "LAC" | "WOO"
    acabado: str                 # "Pale", "Blanco", etc.

    #: Todos los layers presentes (con o sin geometría).
    layers: set[str] = field(default_factory=set)

    #: Layers que contienen al menos una entidad gráfica.
    layers_con_geometria: set[str] = field(default_factory=set)

    #: Nº de entidades por layer (para checks de recuento como C-37).
    conteos_layer: dict[str, int] = field(default_factory=dict)

    #: IDs de piezas detectados en anotaciones (texto en 0_ANOTACIONES).
    ids_piezas: list[str] = field(default_factory=list)

    #: Círculos con coordenadas extraídas para checks geométricos (C-44).
    #: Cada dict: {'layer': str, 'x': float, 'y': float, 'r': float}.
    circulos: list[dict] = field(default_factory=list)

    #: Bounding boxes de las piezas individuales nesteadas en el tablero,
    #: extraídas de las layers de contorno (CUTEXT / CONTORNO LACA). Usado
    #: por C-44 para asociar cada cazoleta a la pieza que la contiene.
    #: Cada dict: {'layer': str, 'xmin': float, 'xmax': float,
    #:             'ymin': float, 'ymax': float}.
    piezas_contorno: list[dict] = field(default_factory=list)

    #: Conteo de entidades por (layer, tipo). Estructura: {layer: {tipo: n}}.
    #: Usado por C-46 para detectar tipos de geometría prohibidos (p.ej. SPLINE).
    conteos_tipo_por_layer: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def clave_material(self) -> str:
        return f"{self.material}_{self.gama}_{self.acabado}"


# ---------------------------------------------------------------------------
# EXTRACCION CSV — Tercer testigo (Checks C-70..C-80)
# ---------------------------------------------------------------------------

@dataclass
class FilaExtraccion:
    """Una fila de la Sección B (tabla de piezas) del CSV EXTRACCION."""

    id_proyecto: str               # "EU-22376"
    cliente: str                   # "Bürgerverein"
    id_pieza: str                  # "M1-P1", "R1", "E1", etc.
    tipologia: str                 # "P" | "C" | "X" | "E" | "R" | "RV" | "T" | "L" | "B" | "H" | ""
    ancho: int                     # mm
    alto: int                      # mm
    material: str                  # "PLY" | "MDF" | ""
    gama: str                      # "LAM" | "LIN" | "LAC" | "WOO" | ""  (HPL→LAM ya normalizado)
    acabado: str                   # "Pale", "Zafiro", "Rosa-baby"…
    mecanizado: str = ""           # "cazta." | "torn." | "vent." | ""
    tirador: str = ""              # "Round" | "Bar" | "Knob" | ""
    posicion_tirador: str = ""     # "1"–"5" | ""
    apertura: str = ""             # "I" | "D" | ""
    color_tirador: str = ""        # "Zafiro" | "Inox" | ""
    cnc: str = ""                  # Observación CNC por pieza (vacío por defecto)
    ac2: str = ""                  # Observación AC2 por pieza
    embalaje: str = ""             # Observación embalaje por pieza


@dataclass
class ExtraccionData:
    """Contenido completo del CSV EXTRACCION_<ID>_<Cliente>.csv.

    Sección A (cabecera de proyecto): datos agregados.
    Sección B (tabla de piezas): una FilaExtraccion por pieza.

    Todos los campos numéricos usan 0 / 0.0 / "" como valor por defecto cuando
    el campo está ausente, para que los checks puedan detectarlo sin excepciones.
    """

    # --- Sección A: cabecera ---
    id_proyecto: str = ""
    cliente: str = ""
    numero_ot: str = ""                    # nº OT como string (preserva ceros a la izquierda)
    semana: str = ""                       # "22"
    fecha_entrada: str = ""                # "25/05/2026"
    fecha_salida: str = ""                 # "05/06/2026"
    piezas: int = 0                        # Cantidad de piezas
    tiradores: int = 0                     # Tiradores Integrados
    metros_canto: float = 0.0              # Metros de canto
    tensores: int = 0                      # Cantidad de tensores
    rejillas_ventilacion: int = 0          # Rejillas ventilacion
    hornacinas: int = 0                    # Hornacinas
    palets: int = 0                        # Cantidad de palets
    mueble_nevera: int = 0                 # Mueble de nevera 75x60x220 cm
    baldas_2h: int = 0                     # Baldas con 2 herrajes ocultos
    baldas_3h: int = 0                     # Baldas con 3 herrajes ocultos
    # Altillos: fila especial "Altillos,N,DIM1,Q1,DIM2,Q2,..." en el CSV.
    # altillos_total es el agregado declarado (primer valor tras la clave).
    # altillos_dims desglosa por dimensión (key: "997x480x580", value: cantidad).
    altillos_total: int = 0
    altillos_dims: dict[str, int] = field(default_factory=dict)
    # Tipos de envío (uno solo debe ser ≥1; los otros 0)
    caja_grande: int = 0
    caja_pequena: int = 0
    estructura_grande: int = 0
    estructura_pequena: int = 0
    # Prioridad solo aplicable a proyectos -INC
    prioridad_inc: str = ""                # "P1" | "P2" | ""
    # Tableros por combinación: {<COD>_tab: cantidad}
    # Ej. {"LAC_Zaf_tab": 2, "HPL_Pal_tab": 1}
    tableros_codificados: dict[str, int] = field(default_factory=dict)
    # Claves de cabecera que no se reconocieron (se reportan como WARN)
    claves_desconocidas: list[str] = field(default_factory=list)

    # --- Sección B: tabla de piezas ---
    piezas_tabla: list[FilaExtraccion] = field(default_factory=list)

    @property
    def tipo_envio_activo(self) -> str:
        """
        Devuelve el nombre canónico del tipo de envío con cantidad ≥1.

        Returns:
            "caja_grande" | "caja_pequena" | "estructura_grande" | "estructura_pequena"
            o "" si ninguno está activo o más de uno lo está (caso anómalo).
        """
        activos = [
            nombre for nombre, valor in (
                ("caja_grande", self.caja_grande),
                ("caja_pequena", self.caja_pequena),
                ("estructura_grande", self.estructura_grande),
                ("estructura_pequena", self.estructura_pequena),
            ) if valor >= 1
        ]
        return activos[0] if len(activos) == 1 else ""


# ---------------------------------------------------------------------------
# Resultado global de la verificación
# ---------------------------------------------------------------------------

@dataclass
class InformeFinal:
    """Resultado completo de verificar un fichero de corte."""

    id_proyecto: str
    cliente: str
    responsable: str
    semana: str

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def errores_criticos(self) -> list[CheckResult]:
        return [c for c in self.checks if c.es_error_critico]

    @property
    def advertencias(self) -> list[CheckResult]:
        return [c for c in self.checks if c.es_advertencia]

    @property
    def estado_global(self) -> str:
        """
        BLOQUEADO   si hay al menos 1 check FAIL con bloquea=True.
        ADVERTENCIAS si hay WARNs pero ningún FAIL bloqueante.
        OK          si todos los checks son PASS o SKIP.
        """
        if self.errores_criticos:
            return "BLOQUEADO"
        if self.advertencias:
            return "ADVERTENCIAS"
        return "OK"

    @property
    def bloquea(self) -> bool:
        return self.estado_global == "BLOQUEADO"
