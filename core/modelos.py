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
    tipologia: str                 # "P" | "C" | "X" | "E" | "R" | "RV" | "T" | "L" | "B" | "H"
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
    tableros: dict[str, int] = field(default_factory=dict)      # {clave_material: n_tableros}
    observaciones_cnc: list[str] = field(default_factory=list)  # Observaciones CNC
    observaciones_produccion: list[str] = field(default_factory=list)  # Obs. producción
    # Campos opcionales — se rellenan si el extractor los detecta
    ids_piezas: list[str] = field(default_factory=list)  # IDs individuales del Packing List (C-12)
    num_ventilacion: int = 0          # Nº rejillas ventilación declaradas (C-40)
    tiene_hornacina: bool | None = None   # OT declara colgador de hornacina (C-41)
    tiene_tensores: bool | None = None    # OT declara tensores (C-42)


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

    @property
    def clave_material(self) -> str:
        return f"{self.material}_{self.gama}_{self.acabado}"


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
        APROBADO    si todos los checks son PASS o SKIP.
        """
        if self.errores_criticos:
            return "BLOQUEADO"
        if self.advertencias:
            return "ADVERTENCIAS"
        return "APROBADO"

    @property
    def bloquea(self) -> bool:
        return self.estado_global == "BLOQUEADO"
