"""
pages/2_Cola_Global.py — Verificación en lote de proyectos PENDIENTE.

Escanea la semana más reciente de cada responsable, agrupa los proyectos
PENDIENTE por responsable, permite seleccionarlos (individual o por grupo) y
los verifica secuencialmente con barra de progreso. Al terminar, los resultados
ocupan la zona principal ordenados por severidad y permiten aplicar el estado
en Drive con un solo clic (incluida acción bulk para todos los APROBADOS).
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import config
from core.modelos import InformeFinal
from drive.navegador import listar_semanas, listar_proyectos
from drive.gestor import aplicar_prefijo_estado
from engine import verificar_proyecto

_ROOT = Path(__file__).parent.parent
from app import get_reglas, get_reglas_cnc, get_servicio, _COLOR, _ICONO, _ESTADO_A_CLAVE
from app import _extraer_id_proyecto, _url_drive, _informe_a_texto


# ---------------------------------------------------------------------------
# Estado de sesión
# ---------------------------------------------------------------------------

def _init_state() -> None:
    st.session_state.setdefault("cola_seleccion", set())   # set[folder_id]
    st.session_state.setdefault("cola_resultados", [])     # list[dict]
    st.session_state.setdefault("cola_scope", {})


# ---------------------------------------------------------------------------
# Carga de proyectos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def _cargar_proyectos_pendientes(_servicio_ref) -> list[dict]:
    """Proyectos de la semana más reciente de cada responsable."""
    proyectos: list[dict] = []
    for responsable in config.RESPONSABLES:
        semanas = listar_semanas(_servicio_ref, responsable)
        if not semanas:
            continue
        semana = semanas[0]
        for p in listar_proyectos(_servicio_ref, semana["id"]):
            proyectos.append({
                **p,
                "responsable": responsable,
                "semana_name": semana["name"],
                "semana_id": semana["id"],
                "semana_numero": semana["numero"],
                "id_proyecto": _extraer_id_proyecto(p["nombre_limpio"]),
            })
    return proyectos


# ---------------------------------------------------------------------------
# ZONA 1 — Cola de selección agrupada por responsable
# ---------------------------------------------------------------------------

def _render_grupo_responsable(responsable: str, proyectos: list[dict], atrasado: bool) -> None:
    """Renderiza una tarjeta con los pendientes de un responsable."""
    semana_lbl = proyectos[0]["semana_name"]
    warn = " · ⚠ semana atrasada" if atrasado else ""

    with st.container(border=True):
        col_h1, col_h2 = st.columns([4, 1.3])
        col_h1.markdown(
            f"**{responsable}**  ·  {len(proyectos)} pendiente"
            f"{'s' if len(proyectos) != 1 else ''}  ·  {semana_lbl}{warn}"
        )
        if col_h2.button(
            f"Seleccionar todo de {responsable}",
            key=f"sel_grupo_{responsable}",
            use_container_width=True,
        ):
            for p in proyectos:
                st.session_state.cola_seleccion.add(p["id"])
            st.rerun()

        for p in proyectos:
            col_chk, col_id, col_nom, col_link = st.columns([0.35, 1.1, 3, 0.7])
            checked = col_chk.checkbox(
                "",
                value=p["id"] in st.session_state.cola_seleccion,
                key=f"chk_{p['id']}",
                label_visibility="collapsed",
            )
            if checked:
                st.session_state.cola_seleccion.add(p["id"])
            else:
                st.session_state.cola_seleccion.discard(p["id"])
            col_id.markdown(f"`{p['id_proyecto']}`")
            col_nom.markdown(p["nombre_limpio"])
            col_link.markdown(f"[↗ Drive]({_url_drive(p['id'])})")


def _render_ya_verificados(ya_verificados: list[dict]) -> None:
    conteo: dict[str, int] = {}
    for p in ya_verificados:
        conteo[p["estado"]] = conteo.get(p["estado"], 0) + 1
    partes = []
    for est in ("OK", "ADVERTENCIAS", "BLOQUEADO"):
        if est in conteo:
            partes.append(f"{_ICONO.get(est, '')} {conteo[est]} {est}")
    resumen = "  ·  ".join(partes) if partes else ""

    with st.expander(
        f"Ver {len(ya_verificados)} ya verificados esta semana  —  {resumen}",
        expanded=False,
    ):
        for p in ya_verificados:
            c1, c2, c3, c4 = st.columns([1, 3, 1.5, 1.2])
            c1.markdown(f"`{_extraer_id_proyecto(p['nombre_limpio'])}`")
            c2.markdown(f"[{p['nombre_limpio']}]({_url_drive(p['id'])})")
            c3.markdown(f"{p['responsable']} · {p['semana_name']}")
            color = _COLOR.get(p["estado"], _COLOR["PENDIENTE"])
            icono = _ICONO.get(p["estado"], "⚪")
            c4.markdown(
                f'<span style="color:{color};font-weight:600;">{icono} {p["estado"]}</span>',
                unsafe_allow_html=True,
            )


def _render_zona_cola(todos: list[dict]) -> bool:
    """
    Renderiza cabecera, controles y tarjetas por responsable.
    Devuelve True si el usuario ha pulsado el botón de Verificar.
    """
    pendientes = [p for p in todos if p["estado"] == "PENDIENTE"]
    ya_verificados = [p for p in todos if p["estado"] != "PENDIENTE"]

    n_pendientes = len(pendientes)
    n_responsables = len({p["responsable"] for p in pendientes})
    seleccion = st.session_state.cola_seleccion
    n_sel = sum(1 for p in pendientes if p["id"] in seleccion)

    # ── Cabecera con métricas y refresco ────────────────────────────────────
    col_info, col_refresh = st.columns([4, 1])
    col_info.markdown(
        f"### {n_pendientes} pendiente{'s' if n_pendientes != 1 else ''}  ·  "
        f"{n_responsables} responsable{'s' if n_responsables != 1 else ''}"
    )
    if col_refresh.button("↺ Actualizar", use_container_width=True, key="btn_refresh"):
        _cargar_proyectos_pendientes.clear()
        st.rerun()

    # ── Controles de selección + botón Verificar ───────────────────────────
    col_all, col_none, col_cnt, col_go = st.columns([1, 1, 1.4, 2.2])
    with col_all:
        if st.button("Todos", use_container_width=True, key="btn_todos",
                     disabled=(n_pendientes == 0)):
            st.session_state.cola_seleccion = {p["id"] for p in pendientes}
            st.rerun()
    with col_none:
        if st.button("Ninguno", use_container_width=True, key="btn_ninguno",
                     disabled=(n_sel == 0)):
            st.session_state.cola_seleccion.clear()
            st.rerun()
    with col_cnt:
        st.markdown(
            f"<div style='padding-top:6px;'><b>{n_sel}</b> "
            f"seleccionado{'s' if n_sel != 1 else ''}</div>",
            unsafe_allow_html=True,
        )
    with col_go:
        verify_clicked = st.button(
            f"▶ Verificar {n_sel} proyecto{'s' if n_sel != 1 else ''}",
            type="primary",
            disabled=(n_sel == 0),
            use_container_width=True,
            key="btn_verificar",
        )

    st.markdown("---")

    if not pendientes and not ya_verificados:
        st.success("¡No hay proyectos pendientes! Todo verificado.")
        return False

    if not pendientes:
        st.success("¡No hay pendientes esta semana! Todo verificado.")

    # ── Tarjetas por responsable ───────────────────────────────────────────
    por_responsable: dict[str, list[dict]] = {}
    for p in pendientes:
        por_responsable.setdefault(p["responsable"], []).append(p)

    max_semana = max((p["semana_numero"] for p in todos), default=0)

    # Respeta el orden de config.RESPONSABLES
    for responsable in config.RESPONSABLES:
        ps = por_responsable.get(responsable)
        if not ps:
            continue
        atrasado = ps[0]["semana_numero"] < max_semana
        _render_grupo_responsable(responsable, ps, atrasado)

    # ── Ya verificados (colapsado) ─────────────────────────────────────────
    if ya_verificados:
        _render_ya_verificados(ya_verificados)

    return verify_clicked


# ---------------------------------------------------------------------------
# Verificación secuencial con progreso
# ---------------------------------------------------------------------------

def _verificar_cola(seleccionados: list[dict]) -> None:
    n = len(seleccionados)
    st.session_state.cola_resultados = []

    st.markdown(f"### Verificando {n} proyecto{'s' if n > 1 else ''}…")
    barra = st.progress(0, text="Iniciando…")
    contenedor_estado = st.empty()

    for i, proyecto in enumerate(seleccionados):
        nombre = proyecto["nombre_limpio"]
        barra.progress(i / n, text=f"({i+1}/{n}) {nombre}")
        contenedor_estado.info(f"⏳ Descargando y analizando **{nombre}**…")

        try:
            informe = verificar_proyecto(
                folder_id=proyecto["id"],
                id_proyecto=proyecto["id_proyecto"],
                responsable=proyecto["responsable"],
                semana=proyecto["semana_name"],
                servicio=get_servicio(),
                reglas=get_reglas(),
                reglas_cnc=get_reglas_cnc(),
            )
            st.session_state.cola_resultados.append({
                "proyecto": proyecto,
                "informe": informe,
                "error": None,
            })
        except Exception as exc:
            st.session_state.cola_resultados.append({
                "proyecto": proyecto,
                "informe": None,
                "error": str(exc),
            })

    barra.progress(1.0, text="✓ Completado")
    contenedor_estado.empty()
    st.session_state.cola_seleccion.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# ZONA 2 — Resultados
# ---------------------------------------------------------------------------

_SEVERIDAD = {"BLOQUEADO": 0, "ADVERTENCIAS": 1, "APROBADO": 2}


def _orden_severidad(r: dict) -> int:
    if r["error"]:
        return -1  # errores de sistema arriba del todo
    return _SEVERIDAD.get(r["informe"].estado_global, 99)


def _aplicar_estado_a_drive(r: dict, estado: str) -> None:
    """Aplica el prefijo de estado en Drive y actualiza el dict local."""
    proyecto = r["proyecto"]
    estado_clave = _ESTADO_A_CLAVE.get(estado, "bloqueado")
    aplicar_prefijo_estado(
        get_servicio(),
        proyecto["id"],
        proyecto["name"],
        estado_clave,
        get_reglas(),
    )
    r["proyecto"]["estado"] = estado


def _render_resultado(r: dict) -> None:
    proyecto = r["proyecto"]
    nombre = proyecto["nombre_limpio"]

    if r["error"]:
        with st.expander(f"💥 ERROR  ·  {nombre}", expanded=True):
            st.error(r["error"])
        return

    informe: InformeFinal = r["informe"]
    estado = informe.estado_global
    color = _COLOR[estado]
    icono = _ICONO[estado]

    n_fail = len(informe.errores_criticos)
    n_warn = len(informe.advertencias)
    if n_fail or n_warn:
        resumen_txt = (
            f"{n_fail} error{'es' if n_fail != 1 else ''}, "
            f"{n_warn} aviso{'s' if n_warn != 1 else ''}"
        )
    else:
        resumen_txt = "Sin errores ni avisos"

    with st.expander(
        f"{icono} {estado}  ·  {proyecto['id_proyecto']}  ·  {nombre}  —  {resumen_txt}",
        expanded=(estado == "BLOQUEADO"),
    ):
        col_info, col_acc = st.columns([3, 2])

        with col_info:
            st.markdown(
                f'<span style="background:{color};color:#fff;padding:3px 12px;'
                f'border-radius:10px;font-weight:700;">{estado}</span>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"{informe.id_proyecto} · {informe.cliente or '(sin OT)'} · "
                f"{informe.semana} · {informe.responsable}"
            )

            if informe.errores_criticos:
                st.markdown("**Errores bloqueantes:**")
                for c in informe.errores_criticos:
                    st.markdown(f"- ❌ **{c.id}** {c.desc}")
                    if c.detalle:
                        st.caption(f"  → {c.detalle}")

            if informe.advertencias:
                st.markdown("**Advertencias:**")
                for c in informe.advertencias:
                    st.markdown(f"- ⚠️ **{c.id}** {c.desc}")
                    if c.detalle:
                        st.caption(f"  → {c.detalle}")

        with col_acc:
            st.markdown("**Acciones**")
            estado_drive = proyecto.get("estado", "PENDIENTE")

            if estado_drive == estado:
                st.success("Ya aplicado en Drive", icon="✓")
            elif estado != "BLOQUEADO":
                if st.button(
                    f"Aplicar [{estado}]",
                    key=f"btn_estado_{proyecto['id']}",
                    type="primary" if estado == "APROBADO" else "secondary",
                    use_container_width=True,
                ):
                    with st.spinner("Aplicando en Drive…"):
                        try:
                            _aplicar_estado_a_drive(r, estado)
                            st.toast(f"✓ {nombre}: [{estado}] aplicado")
                            _cargar_proyectos_pendientes.clear()
                        except Exception as exc:
                            st.error(str(exc))
                    st.rerun()
            else:
                st.info("Revisa el detalle antes de aplicar.")

            st.link_button(
                "🔗 Abrir en Drive",
                url=_url_drive(proyecto["id"]),
                use_container_width=True,
            )

            txt = _informe_a_texto(informe, nombre)
            st.download_button(
                "⬇ Informe .txt",
                data=txt.encode("utf-8"),
                file_name=f"informe_{nombre}.txt",
                mime="text/plain",
                key=f"dl_{proyecto['id']}",
                use_container_width=True,
            )


def _render_zona_resultados(resultados: list[dict]) -> None:
    conteo = {"BLOQUEADO": 0, "ADVERTENCIAS": 0, "APROBADO": 0, "ERROR": 0}
    for r in resultados:
        if r["error"]:
            conteo["ERROR"] += 1
        else:
            conteo[r["informe"].estado_global] += 1

    n_total = len(resultados)
    st.markdown(f"### ✅ Resultados de verificación  ·  {n_total} proyecto"
                f"{'s' if n_total != 1 else ''}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 Bloqueados", conteo["BLOQUEADO"])
    c2.metric("🟠 Advertencias", conteo["ADVERTENCIAS"])
    c3.metric("🟢 Aprobados", conteo["APROBADO"])
    c4.metric("💥 Errores", conteo["ERROR"])

    # Bulk apply approved
    aprobados_pendientes = [
        r for r in resultados
        if not r["error"]
        and r["informe"].estado_global == "APROBADO"
        and r["proyecto"].get("estado") != "APROBADO"
    ]
    col_bulk, col_clean = st.columns([3, 1])
    with col_bulk:
        if aprobados_pendientes:
            if st.button(
                f"✓ Aplicar todos los aprobados ({len(aprobados_pendientes)})",
                type="primary",
                use_container_width=True,
                key="btn_bulk_aprobados",
            ):
                fallos: list[str] = []
                with st.spinner("Aplicando estado en Drive…"):
                    for r in aprobados_pendientes:
                        try:
                            _aplicar_estado_a_drive(r, "APROBADO")
                        except Exception as exc:
                            fallos.append(f"{r['proyecto']['nombre_limpio']}: {exc}")
                _cargar_proyectos_pendientes.clear()
                if fallos:
                    for f in fallos:
                        st.error(f)
                else:
                    st.toast(f"✓ {len(aprobados_pendientes)} aprobados aplicados")
                st.rerun()
    with col_clean:
        if st.button("🗑 Limpiar resultados", use_container_width=True, key="btn_limpiar_res"):
            st.session_state.cola_resultados = []
            st.rerun()

    st.markdown("---")

    # Ordenados por severidad
    for r in sorted(resultados, key=_orden_severidad):
        _render_resultado(r)


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Ficheros pendientes · Verificador CUBRO",
        page_icon="📋",
        layout="wide",
    )
    config.apply_sidebar_width()
    config.render_sidebar_nav()

    _init_state()

    st.title("📋 Ficheros pendientes")

    # ── Si hay resultados, ocupan la zona principal ────────────────────────
    if st.session_state.cola_resultados:
        _render_zona_resultados(st.session_state.cola_resultados)
        st.markdown("---")
        with st.expander("➕ Verificar más proyectos", expanded=False):
            try:
                todos = _cargar_proyectos_pendientes(get_servicio())
            except Exception as exc:
                st.error(f"Error al conectar con Drive: {exc}")
                return
            if _render_zona_cola(todos):
                seleccionados = [
                    p for p in todos
                    if p["id"] in st.session_state.cola_seleccion
                    and p["estado"] == "PENDIENTE"
                ]
                if seleccionados:
                    _verificar_cola(seleccionados)
        return

    # ── Cola normal ────────────────────────────────────────────────────────
    st.caption(
        "Proyectos PENDIENTE de la semana más reciente de cada responsable. "
        "Selecciónalos individualmente o por grupo y pulsa Verificar."
    )

    with st.spinner("Escaneando semanas recientes…"):
        try:
            todos = _cargar_proyectos_pendientes(get_servicio())
        except Exception as exc:
            st.error(f"Error al conectar con Drive: {exc}")
            return

    if _render_zona_cola(todos):
        seleccionados = [
            p for p in todos
            if p["id"] in st.session_state.cola_seleccion
            and p["estado"] == "PENDIENTE"
        ]
        if seleccionados:
            _verificar_cola(seleccionados)


if __name__ == "__main__":
    main()
