"""
app.py — Verificador de Ficheros de Corte · CUBRO Design SL
Vista: Verificar proyecto individual
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

import config
from core.modelos import CheckResult, InformeFinal
from core.reglas_loader import cargar_reglas, cargar_reglas_cnc
from drive.cliente import obtener_servicio_drive
from drive.navegador import listar_semanas, listar_proyectos
from drive.gestor import aplicar_prefijo_estado
from engine import verificar_proyecto
from notion_writer import NotionWriter

_ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Recursos cacheados
# ---------------------------------------------------------------------------

@st.cache_resource
def get_reglas():
    return cargar_reglas(_ROOT / "reglas.yaml")

@st.cache_resource
def get_reglas_cnc():
    return cargar_reglas_cnc(_ROOT / "reglas_cnc.yaml")

@st.cache_resource
def get_servicio():
    return obtener_servicio_drive()

@st.cache_resource
def get_notion_writer() -> NotionWriter | None:
    """None si el token no está configurado (Notion es opcional)."""
    try:
        return NotionWriter(config.notion_token(), config.NOTION_DB_ID)
    except RuntimeError:
        return None

# ---------------------------------------------------------------------------
# Paleta visual
# ---------------------------------------------------------------------------

_COLOR = {
    "BLOQUEADO":    "#e53935",
    "ADVERTENCIAS": "#fb8c00",
    "APROBADO":     "#43a047",
    "PENDIENTE":    "#757575",
    "PASS": "#43a047",
    "WARN": "#fb8c00",
    "FAIL": "#e53935",
    "SKIP": "#9e9e9e",
}
_ICONO = {
    "BLOQUEADO":    "🔴",
    "ADVERTENCIAS": "🟠",
    "APROBADO":     "🟢",
    "PENDIENTE":    "⚪",
    "PASS": "✅",
    "WARN": "⚠️",
    "FAIL": "❌",
    "SKIP": "⏭️",
}
_ESTADO_A_CLAVE = {
    "BLOQUEADO": "bloqueado",
    "ADVERTENCIAS": "advertencias",
    "APROBADO": "aprobado",
}

# ---------------------------------------------------------------------------
# Helpers UI
# ---------------------------------------------------------------------------

def _chip(texto: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;'
        f'padding:2px 10px;border-radius:12px;font-size:0.85em;'
        f'font-weight:600;white-space:nowrap;">{texto}</span>'
    )

def _url_drive(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"

def _subir_informe_drive(informe: InformeFinal, proyecto: dict) -> None:
    """Sube el informe .txt a 1-Informacion (o raíz si no existe) en Drive."""
    from drive.gestor import subir_informe_txt
    from drive.navegador import _buscar_subcarpeta_por_nombre
    from drive.descargador import _SUBCARPETA_ARCHIVOS
    nombre_proyecto = proyecto["nombre_limpio"]
    nombre_archivo = f"informe_{nombre_proyecto}.txt"
    txt = _informe_a_texto(informe, nombre_proyecto)
    try:
        sub = _buscar_subcarpeta_por_nombre(
            get_servicio(), proyecto["id"], _SUBCARPETA_ARCHIVOS
        )
        carpeta_id = sub["id"] if sub else proyecto["id"]
        subir_informe_txt(get_servicio(), carpeta_id, nombre_archivo, txt)
        st.toast(f"Informe guardado en Drive: {nombre_archivo}", icon="📄")
    except Exception as exc:
        st.toast(f"No se pudo guardar en Drive: {exc}", icon="⚠️")


def _log_notion(informe: InformeFinal) -> None:
    """Registra el informe en Notion; falla silenciosamente si Notion no está configurado."""
    writer = get_notion_writer()
    if writer is None:
        return
    try:
        url = writer.escribir_verificacion(informe)
        st.toast(f"Notion: {informe.estado_global} registrado", icon="📋")
    except Exception as exc:
        st.toast(f"Notion no disponible: {exc}", icon="⚠️")


_RE_ID_PROYECTO = re.compile(r"((?:EU|SP)-?\d{5}(?:-INC)?)", re.IGNORECASE)

def _extraer_id_proyecto(nombre_limpio: str) -> str:
    """Extrae el ID de proyecto del nombre de carpeta.

    Busca el patrón EU-XXXXX / SP-XXXXX donde sea que aparezca,
    para tolerar prefijos como 'S5_EU-21247_...' o 'EU-21247_...'.
    Si no hay match devuelve el primer segmento como fallback.
    """
    m = _RE_ID_PROYECTO.search(nombre_limpio)
    return m.group(1).upper() if m else nombre_limpio.split("_")[0]

# ---------------------------------------------------------------------------
# Modales de confirmación (requiere Streamlit ≥ 1.31)
# ---------------------------------------------------------------------------

@st.dialog("Confirmar acción en Drive")
def _modal_aplicar_estado(folder_id: str, nombre_actual: str, nombre_limpio: str,
                           estado_label: str):
    prefijos = get_reglas()["nomenclatura"]["prefijos_estado"]
    estado_clave = _ESTADO_A_CLAVE[estado_label]
    nuevo_nombre = f"{prefijos[estado_clave]}{nombre_limpio}"

    st.markdown(
        f"La carpeta será renombrada a:\n\n"
        f"**`{nuevo_nombre}`**"
    )
    st.warning(
        "Esta acción es visible para todo el equipo y modifica Google Drive.",
        icon="⚠️",
    )
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Confirmar", type="primary", use_container_width=True):
            with st.spinner("Aplicando…"):
                try:
                    aplicar_prefijo_estado(
                        get_servicio(), folder_id, nombre_actual,
                        estado_clave, get_reglas(),
                    )
                    st.session_state._accion_ok = (
                        f"Carpeta renombrada a «{nuevo_nombre}»"
                    )
                    st.session_state.proyecto["estado"] = estado_label
                    st.session_state.proyecto["name"] = nuevo_nombre
                except Exception as exc:
                    st.session_state._accion_error = str(exc)
            st.rerun()
    with col2:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()


@st.dialog("Mover a Carpintek")
def _modal_mover_carpintek(folder_id: str, nombre_limpio: str):
    st.markdown(
        f"¿Mover **{nombre_limpio}** a la carpeta Carpintek?\n\n"
        "Esta acción elimina la carpeta de la zona de cuarentena."
    )
    st.error("Acción irreversible — asegúrate de que el informe es APROBADO.", icon="🔒")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Mover", type="primary", use_container_width=True):
            with st.spinner("Moviendo…"):
                try:
                    from drive.gestor import mover_carpeta
                    destino_id = config.drive_carpintek_id()
                    mover_carpeta(get_servicio(), folder_id, destino_id)
                    st.session_state._accion_ok = (
                        f"«{nombre_limpio}» movido a Carpintek."
                    )
                    st.session_state.proyecto = None
                    st.session_state.informe = None
                except Exception as exc:
                    st.session_state._accion_error = str(exc)
            st.rerun()
    with col2:
        if st.button("Cancelar", use_container_width=True):
            st.rerun()

# ---------------------------------------------------------------------------
# Sidebar — navegación Drive
# ---------------------------------------------------------------------------

def _sidebar() -> dict | None:
    """Dibuja la navegación. Devuelve el proyecto seleccionado o None."""
    config.render_sidebar_nav()

    responsable = st.sidebar.radio(
        "Responsable",
        config.RESPONSABLES,
        index=config.RESPONSABLES.index(
            st.session_state.get("responsable") or config.RESPONSABLES[0]
        ),
        key="radio_responsable",
    )
    if responsable != st.session_state.get("responsable"):
        st.session_state.responsable = responsable
        st.session_state.semana = None
        st.session_state.proyecto = None
        st.session_state.informe = None

    st.sidebar.markdown("---")

    with st.sidebar:
        with st.spinner(""):
            semanas = listar_semanas(get_servicio(), responsable)

    if not semanas:
        st.sidebar.info("Sin semanas disponibles.")
        return None

    semana_idx = st.sidebar.selectbox(
        "Semana",
        range(len(semanas)),
        format_func=lambda i: semanas[i]["name"],
        index=0,
        key=f"sel_semana_{responsable}",
    )
    semana_sel = semanas[semana_idx]
    if (st.session_state.get("semana") or {}).get("id") != semana_sel["id"]:
        st.session_state.semana = semana_sel
        st.session_state.proyecto = None
        st.session_state.informe = None

    st.sidebar.markdown("---")

    with st.sidebar:
        with st.spinner(""):
            proyectos = listar_proyectos(get_servicio(), semana_sel["id"])

    if not proyectos:
        st.sidebar.info("Sin proyectos en esta semana.")
        return None

    def _etiqueta(p: dict) -> str:
        return f"{_ICONO[p['estado']]} {p['nombre_limpio']}"

    idx_actual = 0
    proyecto_actual = st.session_state.get("proyecto")
    if proyecto_actual:
        ids = [p["id"] for p in proyectos]
        if proyecto_actual["id"] in ids:
            idx_actual = ids.index(proyecto_actual["id"])

    proyecto_idx = st.sidebar.radio(
        "Proyecto",
        range(len(proyectos)),
        format_func=lambda i: _etiqueta(proyectos[i]),
        index=idx_actual,
        key=f"sel_proyecto_{semana_sel['id']}",
    )
    proyecto_sel = proyectos[proyecto_idx]
    if (st.session_state.get("proyecto") or {}).get("id") != proyecto_sel["id"]:
        st.session_state.proyecto = proyecto_sel
        st.session_state.informe = None

    return proyecto_sel

# ---------------------------------------------------------------------------
# Informe completo
# ---------------------------------------------------------------------------

def _mostrar_informe(informe: InformeFinal, nombre_proyecto: str = "") -> None:
    estado = informe.estado_global
    color = _COLOR[estado]

    # Banner estado global
    st.markdown(
        f'<div style="background:{color};color:#fff;padding:14px 20px;'
        f'border-radius:8px;margin-bottom:12px;">'
        f'<span style="font-size:1.6em;font-weight:700;">'
        f'{_ICONO[estado]} {estado}</span>'
        f'<span style="margin-left:20px;opacity:.9;">'
        f'{informe.id_proyecto} · {informe.cliente or "(sin OT)"} · {informe.semana}'
        f'</span></div>',
        unsafe_allow_html=True,
    )

    # Contadores
    totales: dict[str, int] = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    for c in informe.checks:
        totales[c.resultado] = totales.get(c.resultado, 0) + 1

    # Tarjetas clicables — filtro por tipo
    st.session_state.setdefault("filtro_tipo", None)

    _TARJETAS = [
        ("PASS", "✅", _COLOR["PASS"]),
        ("WARN", "⚠️",  _COLOR["WARN"]),
        ("FAIL", "❌",  _COLOR["FAIL"]),
        ("SKIP", "⏭️",  _COLOR["SKIP"]),
    ]
    cols = st.columns(4)
    for col, (tipo, icono, color) in zip(cols, _TARJETAS):
        activo = st.session_state.filtro_tipo == tipo
        bg     = color if activo else f"{color}1a"
        txt    = "#fff" if activo else color
        borde  = f"{'3px' if activo else '2px'} solid {color}"
        sombra = f"0 4px 14px {color}55" if activo else "none"
        with col:
            st.markdown(
                f'<div style="background:{bg};border:{borde};border-radius:12px;'
                f'padding:18px 10px 8px;text-align:center;box-shadow:{sombra};'
                f'margin-bottom:2px;">'
                f'<div style="font-size:2.2em;font-weight:800;color:{txt};line-height:1;">'
                f'{totales[tipo]}</div>'
                f'<div style="font-size:0.85em;font-weight:600;color:{txt};'
                f'opacity:0.9;margin-top:4px;">{icono} {tipo}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            btn_txt = "✕ quitar filtro" if activo else "ver solo estos"
            if st.button(btn_txt, key=f"filtro_{tipo}", use_container_width=True):
                st.session_state.filtro_tipo = None if activo else tipo
                st.rerun()

    filtro_activo = st.session_state.filtro_tipo
    resultados_visibles = {filtro_activo} if filtro_activo else {"PASS", "WARN", "FAIL", "SKIP"}

    st.markdown("---")

    # Grupos
    grupos: dict[str, list[CheckResult]] = {}
    for c in informe.checks:
        grupos.setdefault(c.grupo, []).append(c)

    for grupo, checks in grupos.items():
        n_total = len(checks)
        n_fail = sum(1 for c in checks if c.resultado == "FAIL")
        n_warn = sum(1 for c in checks if c.resultado == "WARN")
        n_pass = sum(1 for c in checks if c.resultado == "PASS")

        checks_filtrados = [c for c in checks if c.resultado in resultados_visibles]
        if not checks_filtrados:
            continue

        # Etiqueta de grupo
        if n_fail:
            label = f"❌ {grupo}  ({n_fail} error{'es' if n_fail > 1 else ''})"
        elif n_warn:
            label = f"⚠️ {grupo}  ({n_warn} aviso{'s' if n_warn > 1 else ''})"
        else:
            label = f"✅ {grupo}"

        # Barra de progreso del grupo
        pct = n_pass / n_total if n_total else 0
        barra_color = "#e53935" if n_fail else ("#fb8c00" if n_warn else "#43a047")

        with st.expander(label, expanded=bool(n_fail or n_warn)):
            # Mini barra
            st.markdown(
                f'<div style="background:#eee;border-radius:4px;height:6px;margin-bottom:10px;">'
                f'<div style="background:{barra_color};width:{pct*100:.0f}%;'
                f'height:6px;border-radius:4px;"></div></div>',
                unsafe_allow_html=True,
            )
            for c in checks_filtrados:
                bloquea_icon = " 🔒" if c.resultado == "FAIL" and c.bloquea else ""
                st.markdown(
                    f"{_ICONO[c.resultado]} &nbsp;**{c.id}** — {c.desc}{bloquea_icon}",
                    unsafe_allow_html=True,
                )
                if c.detalle and c.resultado != "PASS":
                    st.caption(c.detalle)

    # Descarga TXT
    st.markdown("---")
    nombre_archivo = f"informe_{nombre_proyecto or informe.id_proyecto}.txt"
    txt = _informe_a_texto(informe, nombre_proyecto)
    st.download_button(
        "⬇ Descargar informe (.txt)",
        data=txt.encode("utf-8"),
        file_name=nombre_archivo,
        mime="text/plain",
    )


def _informe_a_texto(informe: InformeFinal, nombre_proyecto: str = "") -> str:
    lines = [
        f"PROYECTO: {nombre_proyecto or informe.id_proyecto}",
        f"Semana de corte: {informe.semana}",
        f"Responsable: {informe.responsable}",
        f"Estado global: {informe.estado_global}",
        "=" * 60,
    ]
    for c in informe.checks:
        bloquea = " [BLOQUEA]" if c.resultado == "FAIL" and c.bloquea else ""
        lines.append(f"{c.id}  {c.resultado}{bloquea}  {c.desc}")
        if c.detalle and c.resultado != "PASS":
            lines.append(f"    → {c.detalle}")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Panel de acción
# ---------------------------------------------------------------------------

def _panel_accion(proyecto: dict, informe: InformeFinal) -> None:
    st.markdown("---")
    st.subheader("Acciones")

    estado_informe = informe.estado_global
    folder_id = proyecto["id"]
    nombre_limpio = proyecto["nombre_limpio"]
    nombre_actual = proyecto["name"]

    col_drive, col_info = st.columns([3, 2])

    with col_drive:
        st.markdown("**Aplicar resultado en Drive**")

        # Avisar si ya está aplicado
        estado_drive = proyecto.get("estado", "PENDIENTE")
        if estado_drive == estado_informe:
            st.success(
                f"La carpeta ya tiene el estado [{estado_informe}].",
                icon="✓",
            )
        else:
            _color_btn = _COLOR[estado_informe]
            st.markdown(
                f'<p style="color:{_color_btn};font-weight:600;">'
                f'{_ICONO[estado_informe]} Resultado: {estado_informe}</p>',
                unsafe_allow_html=True,
            )
            if st.button(
                f"Aplicar [{estado_informe}] en Drive",
                type="primary",
                use_container_width=True,
            ):
                _modal_aplicar_estado(
                    folder_id, nombre_actual, nombre_limpio, estado_informe
                )

    with col_info:
        st.markdown("**Otras acciones**")
        st.link_button(
            "🔗 Abrir carpeta en Drive",
            url=_url_drive(folder_id),
            use_container_width=True,
        )
        if estado_informe == "APROBADO":
            if st.button(
                "📦 Mover a Carpintek →",
                use_container_width=True,
                type="secondary",
            ):
                _modal_mover_carpintek(folder_id, nombre_limpio)

    # Feedback de acciones completadas
    if st.session_state.pop("_accion_ok", None):
        st.success(st.session_state.get("_accion_ok_msg", "Acción completada."), icon="✓")
    if msg := st.session_state.pop("_accion_error", None):
        st.error(f"Error: {msg}")

# ---------------------------------------------------------------------------
# Vista principal: Verificar
# ---------------------------------------------------------------------------

def page_verificar() -> None:
    for key in ("responsable", "semana", "proyecto", "informe"):
        st.session_state.setdefault(key, None)

    # Feedback de acciones (puede venir de un rerun tras modal)
    if msg := st.session_state.pop("_accion_ok", None):
        st.success(msg, icon="✓")
    if msg := st.session_state.pop("_accion_error", None):
        st.error(f"Error: {msg}")

    proyecto = _sidebar()

    if not proyecto:
        st.info("Selecciona un proyecto en el panel izquierdo.")
        return

    estado_actual = proyecto.get("estado", "PENDIENTE")
    id_proyecto = _extraer_id_proyecto(proyecto["nombre_limpio"])

    semana_name = st.session_state.semana["name"] if st.session_state.semana else "—"
    resp = st.session_state.responsable or "—"

    st.markdown(f"## {_ICONO[estado_actual]} {proyecto['nombre_limpio']}")
    st.caption(
        f"Estado en Drive: **{estado_actual}** · {semana_name} · {resp} · "
        f"[Abrir en Drive]({_url_drive(proyecto['id'])})"
    )

    st.markdown("---")

    _, col_btn = st.columns([3, 1])
    if col_btn.button("🔍 Verificar proyecto", type="primary", use_container_width=True):
        st.session_state.informe = None
        with st.spinner(f"Descargando y verificando {proyecto['nombre_limpio']}…"):
            try:
                informe = verificar_proyecto(
                    folder_id=proyecto["id"],
                    id_proyecto=id_proyecto,
                    responsable=resp,
                    semana=semana_name,
                    servicio=get_servicio(),
                    reglas=get_reglas(),
                    reglas_cnc=get_reglas_cnc(),
                )
                st.session_state.informe = informe
                _log_notion(informe)
                _subir_informe_drive(informe, proyecto)
            except Exception as exc:
                st.error(f"Error durante la verificación: {exc}")
                st.exception(exc)

    informe: InformeFinal | None = st.session_state.informe
    nombre_proyecto = proyecto["nombre_limpio"]
    if informe:
        _mostrar_informe(informe, nombre_proyecto)
        _panel_accion(proyecto, informe)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Verificador · CUBRO",
        page_icon="🪚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    config.apply_sidebar_width()
    page_verificar()


if __name__ == "__main__":
    main()
