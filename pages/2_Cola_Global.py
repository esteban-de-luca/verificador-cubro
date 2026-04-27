"""
pages/2_Cola_Global.py — Verificación en lote de proyectos no aprobados.

Carga las semanas y proyectos en PARALELO (ThreadPoolExecutor) y los renderiza
PROGRESIVAMENTE: cada responsable aparece en la UI en cuanto termina su carga,
en lugar de esperar a que estén todos. Cache manual en session_state (TTL 120 s)
para que las recargas siguientes sean instantáneas.

Muestra todos los proyectos que no estén en estado OK (PENDIENTE, ADVERTENCIAS,
BLOQUEADO) agrupados por responsable en expanders.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import streamlit as st
from googleapiclient.discovery import build

import config
from core.modelos import InformeFinal
from drive.cliente import obtener_credenciales
from drive.navegador import listar_semanas, listar_proyectos
from drive.gestor import aplicar_prefijo_estado
from engine import verificar_proyecto

_ROOT = Path(__file__).parent.parent
from app import get_reglas, get_reglas_cnc, get_servicio, _COLOR, _ICONO, _ESTADO_A_CLAVE
from app import _extraer_id_proyecto, _url_drive, _informe_a_texto


# ---------------------------------------------------------------------------
# Estado de sesión y cache manual
# ---------------------------------------------------------------------------

_CACHE_TTL = 120  # segundos


def _init_state() -> None:
    st.session_state.setdefault("cola_seleccion", set())   # set[folder_id]
    st.session_state.setdefault("cola_resultados", [])     # list[dict]
    st.session_state.setdefault("cola_scope", {})


def _chk_key(folder_id: str) -> str:
    return f"chk_{folder_id}"


def _set_seleccion(ids_a_marcar: set[str], universo_ids: set[str]) -> None:
    """Sincroniza selección y widgets checkbox."""
    st.session_state.cola_seleccion = set(ids_a_marcar)
    for pid in universo_ids:
        st.session_state[_chk_key(pid)] = (pid in ids_a_marcar)


def _cache_valid() -> bool:
    return (
        "cola_data" in st.session_state
        and time.time() - st.session_state.get("cola_data_ts", 0) < _CACHE_TTL
    )


def _cache_set(proyectos: list[dict]) -> None:
    st.session_state["cola_data"] = proyectos
    st.session_state["cola_data_ts"] = time.time()


def _cache_invalidate() -> None:
    st.session_state.pop("cola_data", None)
    st.session_state.pop("cola_data_ts", None)


# ---------------------------------------------------------------------------
# Servicio Drive thread-local (googleapiclient.Resource no es thread-safe)
# ---------------------------------------------------------------------------

_tls = threading.local()


def _thread_service() -> Any:
    """Devuelve el servicio Drive del hilo actual, construyéndolo si no existe."""
    srv = getattr(_tls, "srv", None)
    if srv is None:
        srv = build("drive", "v3", credentials=obtener_credenciales(), cache_discovery=False)
        _tls.srv = srv
    return srv


# ---------------------------------------------------------------------------
# Callback checkbox → selección
# ---------------------------------------------------------------------------

def _on_check_change(pid: str) -> None:
    if st.session_state.get(_chk_key(pid), False):
        st.session_state.cola_seleccion.add(pid)
    else:
        st.session_state.cola_seleccion.discard(pid)


# ---------------------------------------------------------------------------
# Render de un grupo (responsable)
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
        col_sel, col_des = st.columns([1, 1])
        with col_sel:
            if st.button(
                f"Seleccionar todo de {responsable}",
                key=f"sel_grupo_{responsable}",
                use_container_width=True,
            ):
                ids_grupo = {p["id"] for p in proyectos}
                for pid in ids_grupo:
                    st.session_state[_chk_key(pid)] = True
                st.session_state.cola_seleccion |= ids_grupo
                st.rerun()
        with col_des:
            if st.button(
                "Deseleccionar grupo",
                key=f"des_grupo_{responsable}",
                use_container_width=True,
                disabled=(seleccionados_grupo == 0),
            ):
                ids_grupo = {p["id"] for p in proyectos}
                for pid in ids_grupo:
                    st.session_state[_chk_key(pid)] = False
                st.session_state.cola_seleccion -= ids_grupo
                st.rerun()

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


# ---------------------------------------------------------------------------
# Render de cabecera + controles globales
# ---------------------------------------------------------------------------

def _render_header(n_total: int, n_responsables: int) -> None:
    col_info, col_refresh = st.columns([4, 1])
    col_info.markdown(
        f"### {n_total} proyecto{'s' if n_total != 1 else ''} no aprobado"
        f"{'s' if n_total != 1 else ''}  ·  "
        f"{n_responsables} responsable{'s' if n_responsables != 1 else ''}"
    )
    if col_refresh.button("↺ Actualizar", use_container_width=True, key="btn_refresh"):
        _cache_invalidate()
        st.rerun()


def _render_controles(todos: list[dict]) -> bool:
    """Devuelve True si se ha pulsado Verificar."""
    todos_ids = {p["id"] for p in todos}
    n_sel = sum(1 for p in todos if p["id"] in st.session_state.cola_seleccion)
    n_total = len(todos)

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
        return st.button(
            f"▶ Verificar {n_sel} proyecto{'s' if n_sel != 1 else ''}",
            type="primary",
            disabled=(n_sel == 0),
            use_container_width=True,
            key="btn_verificar",
        )


# ---------------------------------------------------------------------------
# Render síncrono (cache hit)
# ---------------------------------------------------------------------------

def _render_zona_cola(todos: list[dict]) -> tuple[bool, Any]:
    n_total = len(todos)
    n_responsables = len({p["responsable"] for p in todos})

    _render_header(n_total, n_responsables)
    verify_clicked = _render_controles(todos)
    st.markdown("---")
    progress_ph = st.empty()

    if not todos:
        st.success("¡No hay proyectos por verificar! Todo aprobado.")
        return False, progress_ph

    por_responsable: dict[str, list[dict]] = {}
    for p in todos:
        por_responsable.setdefault(p["responsable"], []).append(p)
    for ps in por_responsable.values():
        ps.sort(key=lambda p: (-p["semana_numero"], p["nombre_limpio"].lower()))

    for responsable in config.RESPONSABLES:
        ps = por_responsable.get(responsable)
        if ps:
            _render_grupo_responsable(responsable, ps)

    return verify_clicked, progress_ph


# ---------------------------------------------------------------------------
# Render progresivo (cache miss) — paralelo + streaming
# ---------------------------------------------------------------------------

def _proyecto_dict(p: dict, responsable: str, semana: dict) -> dict:
    return {
        **p,
        "responsable": responsable,
        "semana_name": semana["name"],
        "semana_id": semana["id"],
        "semana_numero": semana["numero"],
        "id_proyecto": _extraer_id_proyecto(p["nombre_limpio"]),
    }


def _stream_cargar_y_renderizar() -> tuple[list[dict], bool]:
    """
    Paraleliza la carga de Drive y renderiza cada responsable en cuanto
    termina su parte. Devuelve (proyectos_total, verify_clicked).
    """
    # Pre-asigna placeholders en orden de render
    header_ph = st.empty()
    controls_ph = st.empty()
    sep_ph = st.empty()
    sep_ph.markdown("---")
    progress_ph = st.empty()

    resp_phs: dict[str, Any] = {}
    for r in config.RESPONSABLES:
        ph = st.empty()
        ph.markdown(f"_⏳ **{r}** — esperando…_")
        resp_phs[r] = ph

    header_ph.markdown("### ⏳ Cargando estructura de semanas…")

    # ── Fase 1: listar_semanas en paralelo (5 calls) ───────────────────────
    semanas_por_resp: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=5) as exe:
        futs = {
            exe.submit(lambda r=r: listar_semanas(_thread_service(), r)): r
            for r in config.RESPONSABLES
        }
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                semanas_por_resp[r] = fut.result()
            except Exception as exc:
                semanas_por_resp[r] = []
                resp_phs[r].error(f"Error en {r}: {exc}")

    # Si un responsable no tiene semanas, vacía su placeholder ya
    for r in config.RESPONSABLES:
        if not semanas_por_resp.get(r):
            resp_phs[r].empty()

    # ── Fase 2: listar_proyectos en paralelo (todas las semanas) ───────────
    tasks = [(r, sem) for r, sems in semanas_por_resp.items() for sem in sems]
    proyectos_por_resp: dict[str, list[dict]] = {r: [] for r in config.RESPONSABLES}
    pendientes_por_resp = {r: len(sems) for r, sems in semanas_por_resp.items()}

    n_tasks = len(tasks)
    completados = 0

    if n_tasks > 0:
        header_ph.markdown(f"### ⏳ Cargando proyectos…  (0/{n_tasks} semanas)")

        with ThreadPoolExecutor(max_workers=10) as exe:
            futs2 = {
                exe.submit(
                    lambda sid=sem["id"]: listar_proyectos(_thread_service(), sid)
                ): (r, sem)
                for r, sem in tasks
            }
            for fut in as_completed(futs2):
                r, sem = futs2[fut]
                try:
                    raw = fut.result()
                except Exception as exc:
                    raw = []
                    st.toast(f"Error en {r}/{sem['name']}: {exc}", icon="⚠️")

                for p in raw:
                    if p["estado"] == "OK":
                        continue
                    proyectos_por_resp[r].append(_proyecto_dict(p, r, sem))

                pendientes_por_resp[r] -= 1
                completados += 1

                header_ph.markdown(
                    f"### ⏳ Cargando proyectos…  "
                    f"({completados}/{n_tasks} semanas)"
                )

                # Si este responsable está completo, lo renderizamos ya
                if pendientes_por_resp[r] == 0:
                    ps = proyectos_por_resp[r]
                    ps.sort(key=lambda p: (-p["semana_numero"], p["nombre_limpio"].lower()))
                    if ps:
                        with resp_phs[r].container():
                            _render_grupo_responsable(r, ps)
                    else:
                        resp_phs[r].empty()

    # ── Consolidación ──────────────────────────────────────────────────────
    proyectos_total: list[dict] = []
    for r in config.RESPONSABLES:
        proyectos_total.extend(proyectos_por_resp[r])

    n_total = len(proyectos_total)
    n_resp = sum(1 for ps in proyectos_por_resp.values() if ps)

    # Render final de cabecera y controles
    with header_ph.container():
        _render_header(n_total, n_resp)

    with controls_ph.container():
        verify_clicked = _render_controles(proyectos_total)

    if n_total == 0:
        st.success("¡No hay proyectos por verificar! Todo aprobado.")

    return proyectos_total, verify_clicked, progress_ph


# ---------------------------------------------------------------------------
# Verificación secuencial
# ---------------------------------------------------------------------------

def _verificar_cola(seleccionados: list[dict], progress_ph: Any) -> None:
    n = len(seleccionados)
    st.session_state.cola_resultados = []

    with progress_ph.container():
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

    ids_verificados = {p["id"] for p in seleccionados}
    for pid in ids_verificados:
        st.session_state.pop(_chk_key(pid), None)
    st.session_state.cola_seleccion.clear()
    _cache_invalidate()
    st.rerun()


# ---------------------------------------------------------------------------
# ZONA 2 — Resultados
# ---------------------------------------------------------------------------

_SEVERIDAD = {"BLOQUEADO": 0, "ADVERTENCIAS": 1, "OK": 2}


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
                    type="primary" if estado == "OK" else "secondary",
                    use_container_width=True,
                ):
                    with st.spinner("Aplicando en Drive…"):
                        try:
                            _aplicar_estado_a_drive(r, estado)
                            st.toast(f"✓ {nombre}: [{estado}] aplicado")
                            _cache_invalidate()
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
    conteo = {"BLOQUEADO": 0, "ADVERTENCIAS": 0, "OK": 0, "ERROR": 0}
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
    c3.metric("🟢 Aprobados", conteo["OK"])
    c4.metric("💥 Errores", conteo["ERROR"])

    aprobados_pendientes = [
        r for r in resultados
        if not r["error"]
        and r["informe"].estado_global == "OK"
        and r["proyecto"].get("estado") != "OK"
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
                            _aplicar_estado_a_drive(r, "OK")
                        except Exception as exc:
                            fallos.append(f"{r['proyecto']['nombre_limpio']}: {exc}")
                _cache_invalidate()
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

def _do_zona_cola() -> None:
    """Resuelve cache hit/miss y dispara verificación si procede."""
    if _cache_valid():
        todos = st.session_state["cola_data"]
        verify_clicked, progress_ph = _render_zona_cola(todos)
    else:
        try:
            todos, verify_clicked, progress_ph = _stream_cargar_y_renderizar()
        except Exception as exc:
            st.error(f"Error al conectar con Drive: {exc}")
            return
        _cache_set(todos)

    if verify_clicked:
        seleccionados = [
            p for p in todos if p["id"] in st.session_state.cola_seleccion
        ]
        if seleccionados:
            _verificar_cola(seleccionados, progress_ph)


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
            _do_zona_cola()
        return

    st.caption(
        "Todos los proyectos no aprobados (PENDIENTE, ADVERTENCIAS, BLOQUEADO) "
        "agrupados por responsable. Selecciónalos y pulsa Verificar."
    )

    _do_zona_cola()


if __name__ == "__main__":
    main()
