"""
Genera el PDF "Listado de Checks — Verificador de Ficheros de Corte"
CUBRO Design SL · Arquitectura v3.0 · Abril 2026
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ---------------------------------------------------------------------------
# Paleta de colores CUBRO
# ---------------------------------------------------------------------------
CUBRO_DARK   = colors.HexColor("#1A1A2E")
CUBRO_BLUE   = colors.HexColor("#16213E")
CUBRO_ACCENT = colors.HexColor("#0F3460")
CUBRO_TEAL   = colors.HexColor("#00B4D8")
PASS_GREEN   = colors.HexColor("#D4EDDA")
WARN_YELLOW  = colors.HexColor("#FFF3CD")
ROW_LIGHT    = colors.HexColor("#F8F9FA")
ROW_WHITE    = colors.white
HEADER_BG    = colors.HexColor("#0F3460")
HEADER_FG    = colors.white

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "CubroTitle",
    parent=styles["Title"],
    fontSize=20,
    textColor=CUBRO_DARK,
    spaceAfter=4,
    fontName="Helvetica-Bold",
    alignment=TA_CENTER,
)
subtitle_style = ParagraphStyle(
    "CubroSubtitle",
    parent=styles["Normal"],
    fontSize=10,
    textColor=colors.HexColor("#555555"),
    spaceAfter=2,
    alignment=TA_CENTER,
)
group_style = ParagraphStyle(
    "GroupHeading",
    parent=styles["Heading2"],
    fontSize=12,
    textColor=CUBRO_ACCENT,
    spaceBefore=14,
    spaceAfter=4,
    fontName="Helvetica-Bold",
)
cell_style = ParagraphStyle(
    "Cell",
    parent=styles["Normal"],
    fontSize=8,
    leading=11,
    fontName="Helvetica",
)
cell_bold = ParagraphStyle(
    "CellBold",
    parent=cell_style,
    fontName="Helvetica-Bold",
)
summary_style = ParagraphStyle(
    "Summary",
    parent=styles["Normal"],
    fontSize=9,
    leading=13,
    fontName="Helvetica",
    textColor=CUBRO_DARK,
)

# ---------------------------------------------------------------------------
# Datos de checks
# ---------------------------------------------------------------------------
GROUPS = [
    {
        "title": "GRUPO 1 — Inventario (C-00 a C-04)",
        "checks": [
            ("C-00", "Documentos obligatorios presentes",
             "DESPIECE, ETIQUETAS y EAN LOGISTIC están presentes", "Sí"),
            ("C-01", "ID de proyecto consistente en todos los archivos",
             "Todos los IDs de proyecto en los archivos coinciden con el esperado", "Sí"),
            ("C-02", "Nomenclatura de archivos correcta",
             "Todos los archivos coinciden con patrones conocidos (WARN si no)", "No"),
            ("C-03", "Nº DXFs == nº tableros declarados en OT",
             "Nº de DXFs tableros = suma de tableros en OT", "Sí"),
            ("C-04", "PDFs nesting == combinaciones material DESPIECE",
             "Un PDF por cada combinación única material+gama+acabado", "Sí"),
        ],
    },
    {
        "title": "GRUPO 2 — Piezas: validaciones generales (C-10 a C-17)",
        "checks": [
            ("C-10", "Nº total piezas igual en OT, DESPIECE y ETIQUETAS",
             "El nº de piezas coincide en los tres documentos", "Sí"),
            ("C-11", "Todos los IDs del DESPIECE presentes en ETIQUETAS",
             "Cada ID del DESPIECE existe en ETIQUETAS", "Sí"),
            ("C-12", "Todos los IDs del DESPIECE presentes en packing list OT",
             "Cada ID del DESPIECE existe en la OT", "Sí"),
            ("C-13", "Dimensiones iguales en DESPIECE y ETIQUETAS",
             "Ancho y alto de cada pieza coinciden exactamente", "Sí"),
            ("C-14", "Material/gama/acabado consistente DESPIECE-ETIQUETAS",
             "Material, gama y acabado iguales en ambos documentos", "Sí"),
            ("C-15", "PLY->LAM/LIN  ·  MDF->LAC/WOO",
             "PLY solo con LAM o LIN; MDF solo con LAC o WOO", "Sí"),
            ("C-16", "Acabados pertenecen a la lista validada de su gama",
             "El acabado de cada pieza está en la lista de su gama (WARN si no)", "No"),
            ("C-17", "Sufijo ID coherente con tipología DESPIECE",
             "El sufijo del ID (P, C, T…) es coherente con la tipología declarada", "Sí"),
        ],
    },
    {
        "title": "GRUPO 3 — Piezas: mecanizados y aperturas (C-20 a C-29)",
        "checks": [
            ("C-20", "Puertas P siempre con apertura I/D",
             "Toda puerta tipo P tiene apertura (Izq. o Der.) definida", "Sí"),
            ("C-21", "Puertas X con tirador tienen apertura I/D",
             "Puerta X con tirador debe tener apertura definida", "Sí"),
            ("C-22", "Cajones C sin apertura I/D",
             "Ningún cajón tipo C tiene apertura asignada", "Sí"),
            ("C-23", "Pieza con tirador tiene modelo + posición + color",
             "Si hay tirador: modelo, posición y color definidos (los tres)", "Sí"),
            ("C-24", "Sin posición de tirador sin tirador asignado",
             "Si hay posición de tirador -> tirador asignado", "Sí"),
            ("C-25", "Nº cazoletas correcto según altura de puerta",
             "Puertas P/X con cazoletas tienen el nº correcto según tabla de alturas", "Sí"),
            ("C-26", "Baldas con mecanizado tienen dimensiones estándar",
             "Baldas B con mecanizado tienen dimensiones en la tabla estándar del YAML", "Sí"),
            ("C-27", "Rodapiés R sin mecanizado (RV solo vent.)",
             "Rodapié R sin mecanizado; RV solo con 'vent.' (WARN si no)", "No"),
            ("C-28", "Tipologías sin mecanizado no llevan tirador",
             "Tipologías T/L/B/E/R/TBE sin tirador (WARN si lo tienen)", "No"),
            ("C-29", "Alto de puerta P acaba en 98",
             "El alto de puerta P debería acabar en 98 (WARN si no — posible recrecida)", "No"),
        ],
    },
    {
        "title": "GRUPO 4 — Layers DXF (C-30 a C-43)",
        "checks": [
            ("C-30", "Layer CONTROL ausente en todos los DXFs",
             "El layer 'CONTROL' no aparece en ningún DXF", "Sí"),
            ("C-31", "Layer '0' sin geometría operativa",
             "Layer '0' presente pero sin geometría operativa", "Sí"),
            ("C-32", "Layers internos de Rhino ausentes en DXFs",
             "HORNACINAS, FAKTUM, GODMORGON, METOD, PAX no presentes", "Sí"),
            ("C-33", "Layer 0_ANOTACIONES en todos los DXFs",
             "Layer '0_ANOTACIONES' presente en cada DXF", "Sí"),
            ("C-34", "Layer biselar en tableros LAM/LIN",
             "Layer '13-BISELAR-EM5-Z0_8' presente en DXFs de gama LAM o LIN", "Sí"),
            ("C-35", "Layer corte perimetral correcto por gama/acabado",
             "Layer correcto: CUTEXT para estándar, CONTORNO LACA para LAC no estándar", "Sí"),
            ("C-36", "Layer desbaste tirador coherente con color",
             "Para cada color de tirador en DESPIECE, existe su layer desbaste en DXFs", "Sí"),
            ("C-37", "Recuento HANDCUT == tiradores OT",
             "Suma entidades '9_11-HANDCUT-EM5-Z18' = nº tiradores declarados en OT", "Sí"),
            ("C-38", "Cajones con torn. tienen layers DRILL en DXFs",
             "Si hay cajones con 'torn.', existe algún layer 3-DRILL-*", "Sí"),
            ("C-39", "Piezas con cazta. tienen layers POCKET en DXFs",
             "Si hay piezas con 'cazta.', existe algún layer 6/7-POCKET", "Sí"),
            ("C-40", "Recuento REJILLA == ventilación OT",
             "Layer '8-REJILLA' presente <-> OT declara ventilación", "Sí"),
            ("C-41", "Layer hornacina coherente con OT",
             "Layer 'MECANISMO_HORNACINA_Z12' presente <-> OT declara hornacina", "Sí"),
            ("C-42", "Layers TIRANTE coherentes con OT",
             "Layers TIRANTE presentes <-> OT declara tensores", "Sí"),
            ("C-43", "Layers en desuso ausentes",
             "Los layers obsoletos del YAML no aparecen en ningún DXF (WARN si aparecen)", "No"),
        ],
    },
    {
        "title": "GRUPO 5 — Logística / bultos (C-50 a C-56)",
        "checks": [
            ("C-50", "Nº bultos igual en EAN y PDFs",
             "Nº bultos únicos en EAN LOGISTIC == nº en PDF BULTOS/ALBARÁN", "Sí"),
            ("C-51", "Todas las piezas asignadas a un bulto",
             "Cada pieza del DESPIECE aparece en EAN LOGISTIC", "Sí"),
            ("C-52", "Sin piezas duplicadas en varios bultos",
             "Cada pieza asignada a exactamente un bulto", "Sí"),
            ("C-53", "Formato ID bulto correcto",
             "IDs de bulto siguen el formato CUB-{ID_PROYECTO}-{N}-{TOTAL}", "Sí"),
            ("C-54", "Peso total EAN == OT (tolerancia máx. 2%)",
             "Suma pesos EAN = peso OT ± 2% (WARN si no)", "No"),
            ("C-55", "Modelo de envío coherente con dimensiones",
             "Si alguna pieza > 2480 mm -> OT declara 'estructura' en observaciones", "Sí"),
            ("C-56", "Código DESTINO CAJA correcto",
             "Código en PDF DESTINO CAJA = exactamente CUB-{ID_PROYECTO}", "Sí"),
        ],
    },
    {
        "title": "GRUPO 6 — Texto CNC / observaciones OT (C-60 a C-63)",
        "checks": [
            ("C-60", "Retales declarados en OT si hay layer retal",
             "Si DXF tiene layer RETAL UTILIZADO -> OT menciona 'retal de' o 'retal utilizado'", "Sí"),
            ("C-61", "Piezas sin mecanizar mencionadas en OT",
             "Si hay puertas P sin mecanizado -> OT incluye 'sin mecanizar' (WARN si no)", "No"),
            ("C-62", "Observaciones CNC reconocidas por catálogo",
             "Cada observación CNC de la OT coincide con un patrón de reglas_cnc.yaml (WARN si no)", "No"),
            ("C-63", "Observaciones no reconocidas marcadas para revisión",
             "Las no reconocidas se marcan WARN con texto íntegro para revisión humana en Notion", "No"),
        ],
    },
]

# ---------------------------------------------------------------------------
# Construcción del documento
# ---------------------------------------------------------------------------
COL_WIDTHS = [18*mm, 52*mm, 82*mm, 14*mm]
PAGE_W, PAGE_H = A4
MARGIN = 18*mm

output_path = "Listado_Checks_Verificador_CUBRO.pdf"

doc = SimpleDocTemplate(
    output_path,
    pagesize=A4,
    leftMargin=MARGIN, rightMargin=MARGIN,
    topMargin=MARGIN, bottomMargin=MARGIN,
    title="Listado de Checks — Verificador de Ficheros de Corte",
    author="CUBRO Design SL",
)

story = []

# — Cabecera
story.append(Spacer(1, 4*mm))
story.append(Paragraph("Verificador de Ficheros de Corte", title_style))
story.append(Paragraph("Listado completo de Checks · CUBRO Design SL · Arquitectura v3.0 · Abril 2026", subtitle_style))
story.append(Spacer(1, 2*mm))
story.append(HRFlowable(width="100%", thickness=2, color=CUBRO_TEAL))
story.append(Spacer(1, 5*mm))

def make_table(checks):
    header = [
        Paragraph("<b>ID</b>", ParagraphStyle("H", parent=cell_style, textColor=HEADER_FG, fontName="Helvetica-Bold")),
        Paragraph("<b>Qué verifica</b>", ParagraphStyle("H", parent=cell_style, textColor=HEADER_FG, fontName="Helvetica-Bold")),
        Paragraph("<b>Condición de PASS</b>", ParagraphStyle("H", parent=cell_style, textColor=HEADER_FG, fontName="Helvetica-Bold")),
        Paragraph("<b>Bloquea</b>", ParagraphStyle("H", parent=cell_style, textColor=HEADER_FG, fontName="Helvetica-Bold", alignment=TA_CENTER)),
    ]
    data = [header]
    for i, (cid, desc, cond, bloquea) in enumerate(checks):
        bg = ROW_LIGHT if i % 2 == 0 else ROW_WHITE
        bloquea_cell = Paragraph(
            f"<b>{bloquea}</b>",
            ParagraphStyle(
                "Bloquea",
                parent=cell_style,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#B22222") if bloquea == "Sí" else colors.HexColor("#7B6000"),
                fontName="Helvetica-Bold",
            ),
        )
        row = [
            Paragraph(f"<b>{cid}</b>", cell_bold),
            Paragraph(desc, cell_style),
            Paragraph(cond, cell_style),
            bloquea_cell,
        ]
        data.append(row)

    t = Table(data, colWidths=COL_WIDTHS, repeatRows=1)
    row_count = len(data)
    t.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR",  (0, 0), (-1, 0), HEADER_FG),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        # Body
        ("FONTSIZE",   (0, 1), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        # Alternating rows
        *[("BACKGROUND", (0, i), (-1, i), ROW_LIGHT if i % 2 == 1 else ROW_WHITE)
          for i in range(1, row_count)],
        # Grid
        ("GRID",       (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("LINEBELOW",  (0, 0), (-1, 0), 1.5, CUBRO_TEAL),
    ]))
    return t

for group in GROUPS:
    story.append(Paragraph(group["title"], group_style))
    story.append(make_table(group["checks"]))
    story.append(Spacer(1, 4*mm))

# — Resumen final
story.append(HRFlowable(width="100%", thickness=1, color=CUBRO_TEAL))
story.append(Spacer(1, 3*mm))
story.append(Paragraph(
    "<b>Resumen:</b>  42 checks en total  ·  28 bloqueantes (FAIL)  ·  14 de advertencia (WARN/SKIP)<br/>"
    "Números no usados (reservados): C-05–C-09 · C-18–C-19 · C-44–C-49 · C-57–C-59<br/>"
    "Fuente de reglas configurables: <i>reglas.yaml</i> y <i>reglas_cnc.yaml</i>",
    summary_style,
))

doc.build(story)
print(f"PDF generado: {output_path}")
