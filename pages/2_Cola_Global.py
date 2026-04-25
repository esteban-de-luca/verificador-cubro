"""
pages/2_Cola_Global.py — Verificación en lote de proyectos no aprobados.

Escanea TODAS las semanas de cada responsable y muestra todos los proyectos
que no estén en estado OK (PENDIENTE, ADVERTENCIAS, BLOQUEADO), agrupados
por responsable en expanders. Permite seleccionarlos (individual o por grupo)
y verificarlos secuencialmente con barra de progreso. Al terminar, los
resultados ocupan la zona principal ordenados por severidad.
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


def _chk_key(folder_id: str) -> str:
    return f"chk_{folder_id}"


def _set_seleccion(ids_a_marcar: set[str], pendientes_ids: set[str]) -> None:
    """
    Sincroniza la selección con el estado de los widgets checkbox.

    `ids_a_marcar` es el conjunto de IDs que deben quedar marcados.
    `pendientes_ids` es el universo de IDs que tienen checkbox renderizado
    (necesario para desmarcar los que NO estén en `ids_a_marcar`).
    """
    st.session_state.cola_seleccion = set(ids_a_marcar)
    for pid in pendientes_ids:
        st.session_state[_chk_key(pid)] = (pid in ids_a_marcar)


# ---------------------------------------------------------------------------
# Carga de proyectos no aprobados
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def _cargar_proyectos_no_aprobados(_servicio_ref) -> list[dict]:
    """
    Recorre TODAS las semanas de cada responsable y devuelve los proyectos
    que no estén en estado OK. Estados incluidos: PENDIENTE, ADVERTENCIAS,
    BLOQUEADO.
    """
    proyectos: list[dict] = []
    for responsable in config.RESPONSABLES:
        for semana in listar_semanas(_servicio_ref, responsable):
            for p in listar_proyectos(_servicio_ref, semana["id"]):
                if p["estado"] == "OK":
                    continue
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
# Callback de sincronización checkbox → cola_seleccion
# ---------------------------------------------------------------------------

def _on_check_change(pid: str) -> None:
    if st.session_state.get(_chk_key(pid), False):
        st.session_state.cola_seleccion.add(pid)
    else:
        st.session_state.cola_seleccion.discard(pid)


# ---------------------------------------------------------------------------
# ZONA 1 — Cola agrupada por responsable
# ---------------------------------------------------------------------------

_ORDEN_ESTADOS = ("PENDIENTE", "ADVERTENCIAS", "BLOQUEADO")


def _resumen_estados(proyectos: list[dict]) -> str:
    conteo: dict[str, int] = {}
    for p in proyectos:
        conteo[p["estado"]] = conteo.get(p["estado"], 0) + 1
    partes = []
    for est in _ORDEN_ESTADOS:
        if est in conteo:
            partes.append(f"{conteo[est]} {est}")
    return "  ·  ".join(partes)


def _render_grupo_responsable(responsable: str, proyectos: list[dict]) -> None:
    """Expander con los proyectos no aprobados de un responsable."""
    n = len(proyectos)
    seleccionados_grupo = sum(
        1 for p in proyectos if p["id"] in st.session_state.cola_seleccion
    )
    label = (
        f"{responsable}  ·  {n} proyecto{'s' if n != 1 else ''}  —  "
        f"{_resumen_estados(proyectos)}"
    )
    if seleccionados_grupo:
        label += f"  ·  ☑ {seleccionados_grupo}"

    with st.expander(label, expanded=True):
        # Botones de selección por grupo
        col_sel, col_des = st.columns([1, 1])
        with col_sel:
            if st.button(
                f"Seleccionar todo de {responsable}",
                key=f"sel_grupo_{responsable}",
                use_container_width=True,
            ):
                ids_grupo = {p["id"] for p in proyectos}
                nueva = st.session_state.cola_seleccion | ids_grupo
                # Sincroniza solo los chk de este grupo a True
                for pid in ids_grupo:
                    st.session_state[_chk_key(pid)] = True
                st.session_state.cola_seleccion = nueva
                st.rerun()
        with col_des:
            if st.button(
                f"Deseleccionar grupo",
                key=f"des_grupo_{responsable}",
                use_container_width=True,
                disabled=(seleccionados_grupo == 0),
            ):
                ids_grupo = {p["id"] for p in proyectos}
                for pid in ids_grupo:
                    st.session_state[_chk_key(pid)] = False
                st.session_state.cola_seleccion -= ids_grupo
                st.rerun()

        # Cabecera de columnas
        h = st.columns([0.35, 1.1, 3, 0.9, 1.2, 0.7])
        h[0].markdown("&nbsp;", unsafe_allow_html=True)
        h[1].markdown("**ID**")
        h[2].markdown("**Nombre**")
        h[3].markdown("**Semana**")
        h[4].markdown("**Estado**")
        h[5].markdown("**Drive**")

        for p in proyectos:
            col_chk, col_id, col_nom, col_sem, col_est, col_link = st.columns(
                [0.35, 1.1, 3, 0.9, 1.2, 0.7]
            )

            chk_key = _chk_key(p["id"])
            # Inicializa el widget state SOLO la primera vez (no en cada rerun
            # — si no, sobrescribiríamos las acciones del usuario)
            if chk_key not in st.session_state:
                st.session_state[chk_key] = p["id"] in st.session_state.cola_seleccion

            col_chk.checkbox(
                "",
                key=chk_key,
                on_change=_on_check_change,
                args=(p["id"],),
                label_visibility="collapsed",
            )
            col_id.markdown(f"`{p['id_proyecto']}`")
            col_nom.markdown(p["nombre_limpio"])
            col_sem.markdown(p["semana_name"])

            color = _COLOR.get(p["estado"], _COLOR["PENDIENTE"])
            icono = _ICONO.get(p["estado"], "⚪")
            col_est.markdown(
                f'<span style="color:{color};font-weight:600;">{icono} {p["estado"]}</span>',
                unsafe_allow_html=True,
            )
            col_link.markdown(f"[↗ Drive]({_url_drive(p['id'])})")


def _render_zona_cola(todos: list[dict]) -> bool:
    """Devuelve True si el usuario ha pulsado Verificar."""
    n_total = len(todos)
    todos_ids = {p["id"] for p in todos}
    n_responsables = len({p["responsable"] for p in todos})
    n_sel = sum(1 for p in todos if p["id"] in st.session_state.cola_seleccion)

    # ── Cabecera ───────────────────────────────────────────────────────────
    col_info, col_refresh = st.columns([4, 1])
    col_info.markdown(
        f"### {n_total} proyecto{'s' if n_total != 1 else ''} no aprobado"
        f"{'s' if n_total != 1 else ''}  ·  "
        f"{n_responsables} responsable{'s' if n_responsables != 1 else ''}"
    )
    if col_refresh.button("↺ Actualizar", use_container_width=True, key="btn_refresh"):
        _cargar_proyectos_no_aprobados.clear()
        st.rerun()

    # ── Controles globales + botón Verificar ───────────────────────────────
    col_all, col_none, col_cnt, col_go = st.columns([1, 1, 1.4, 2.2])
    with col_all:
        if st.button("Todos", use_container_width=True, key="btn_todos",
                     disabled=(n_total == 0)):
            _set_seleccion(todos_ids, todos_ids)
            st.rerun()
    with col_none:
        if st.button("Ninguno", use_container_width=True, key="btn_ninguno",
                     disabled=(n_sel == 0)):
            _set_seleccion(set(), todos_ids)
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

    if not todos:
        st.success("¡No hay proyectos por verificar! Todo aprobado.")
        return False

    # ── Agrupar por responsable y renderizar ───────────────────────────────
    por_responsable: dict[str, list[dict]] = {}
    for p in todos:
        por_responsable.setdefault(p["responsable"], []).append(p)

    # Dentro de cada grupo, ordena por semana descendente y luego por nombre
    for ps in por_responsable.values():
        ps.sort(key=lambda p: (-p["semana_numero"], p["nombre_limpio"].lower()))

    for responsable in config.RESPONSABLES:
        ps = por_responsable.get(responsable)
        if not ps:
            continue
        _render_grupo_responsable(responsable, ps)

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

    # Limpia selección y los chk_* widgets para que la próxima carga arranque
    # con todos desmarcados.
    ids_verificados = {p["id"] for p in seleccionados}
    for pid in ids_verificados:
        st.session_state.pop(_chk_key(pid), None)
    st.session_state.cola_seleccion.clear()
    st.rerun()


# ---------------------------------------------------------------------------
# ZONA 2 — Resultados
# ---------------------------------------------------------------------------

_SEVERIDAD = {"BLOQUEADO": 0, "ADVERTENCIAS": 1, "APROBADO": 2}


def _orden_severidad(r: dict) -> int:
    if r["error"]:
        return -1
    return _SEVERIDAD.get(r["informe"].estado_global, 99)


def _aplicar_estado_a_drive(r: dict, estado: str) -> None:
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
                            _cargar_proyectos_no_aprobados.clear()
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
                _cargar_proyectos_no_aprobados.clear()
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

    if st.session_state.cola_resultados:
        _render_zona_resultados(st.session_state.cola_resultados)
        st.markdown("---")
        with st.expander("➕ Verificar más proyectos", expanded=False):
            try:
                todos = _cargar_proyectos_no_aprobados(get_servicio())
            except Exception as exc:
                st.error(f"Error al conectar con Drive: {exc}")
                return
            if _render_zona_cola(todos):
                seleccionados = [
                    p for p in todos
                    if p["id"] in st.session_state.cola_seleccion
                ]
                if seleccionados:
                    _verificar_cola(seleccionados)
        return

    st.caption(
        "Todos los proyectos no aprobados (PENDIENTE, ADVERTENCIAS, BLOQUEADO) "
        "agrupados por responsable. Selecciónalos y pulsa Verificar."
    )

    with st.spinner("Escaneando todas las semanas…"):
        try:
            todos = _cargar_proyectos_no_aprobados(get_servicio())
        except Exception as exc:
            st.error(f"Error al conectar con Drive: {exc}")
            return

    if _render_zona_cola(todos):
        seleccionados = [
            p for p in todos
            if p["id"] in st.session_state.cola_seleccion
        ]
        if seleccionados:
            _verificar_cola(seleccionados)


if __name__ == "__main__":
    main()
