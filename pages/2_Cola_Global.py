"""
pages/2_Cola_Global.py — Verificación en lote de proyectos PENDIENTE.

Escanea la semana más reciente de cada responsable, muestra todos los proyectos
PENDIENTE, permite seleccionarlos y los verifica secuencialmente con barra de
progreso en tiempo real. Al terminar, muestra tabla resumen y permite aplicar
el estado resultante en Drive con un solo clic.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import config
from core.modelos import InformeFinal
from drive.navegador import listar_semanas, listar_proyectos
from drive.gestor import aplicar_prefijo_estado
from engine import verificar_proyecto

# Reutilizamos los recursos cacheados de app.py  (misma instancia gracias a
# @st.cache_resource — Streamlit comparte el caché entre páginas)
_ROOT = Path(__file__).parent.parent
from app import get_reglas, get_reglas_cnc, get_servicio, _COLOR, _ICONO, _ESTADO_A_CLAVE
from app import _extraer_id_proyecto, _url_drive, _informe_a_texto

# ---------------------------------------------------------------------------
# Estado de sesión específico de esta página
# ---------------------------------------------------------------------------

def _init_state() -> None:
    st.session_state.setdefault("cola_seleccion", set())   # set[folder_id]
    st.session_state.setdefault("cola_resultados", [])     # list[dict]
    st.session_state.setdefault("cola_scope", {})          # {responsable: semana_dict}


# ---------------------------------------------------------------------------
# Carga de proyectos disponibles
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def _cargar_proyectos_pendientes(_servicio_ref) -> list[dict]:
    """
    Devuelve todos los proyectos PENDIENTE de la semana más reciente de cada
    responsable. TTL de 2 minutos para no martillear la API de Drive.
    """
    proyectos: list[dict] = []
    for responsable in config.RESPONSABLES:
        semanas = listar_semanas(_servicio_ref, responsable)
        if not semanas:
            continue
        semana = semanas[0]  # La más reciente
        for p in listar_proyectos(_servicio_ref, semana["id"]):
            proyectos.append({
                **p,
                "responsable": responsable,
                "semana_name": semana["name"],
                "semana_id": semana["id"],
                "id_proyecto": _extraer_id_proyecto(p["nombre_limpio"]),
            })
    return proyectos


# ---------------------------------------------------------------------------
# Tabla de selección
# ---------------------------------------------------------------------------

def _tabla_seleccion(proyectos: list[dict]) -> list[dict]:
    """Muestra la tabla de proyectos con checkboxes. Devuelve los seleccionados."""
    pendientes = [p for p in proyectos if p["estado"] == "PENDIENTE"]
    ya_verificados = [p for p in proyectos if p["estado"] != "PENDIENTE"]

    if not pendientes and not ya_verificados:
        st.info("No hay proyectos disponibles.")
        return []

    seleccionados: list[dict] = []

    # Cabecera
    hdr = st.columns([0.5, 3, 1.5, 1.5, 1])
    hdr[0].markdown("**✓**")
    hdr[1].markdown("**Proyecto**")
    hdr[2].markdown("**Responsable**")
    hdr[3].markdown("**Semana**")
    hdr[4].markdown("**Estado**")
    st.markdown('<hr style="margin:4px 0;">', unsafe_allow_html=True)

    # Filas pendientes (seleccionables)
    if pendientes:
        for p in pendientes:
            col_chk, col_nom, col_resp, col_sem, col_est = st.columns([0.5, 3, 1.5, 1.5, 1])
            checked = col_chk.checkbox(
                "",
                value=p["id"] in st.session_state.cola_seleccion,
                key=f"chk_{p['id']}",
                label_visibility="collapsed",
            )
            if checked:
                st.session_state.cola_seleccion.add(p["id"])
                seleccionados.append(p)
            else:
                st.session_state.cola_seleccion.discard(p["id"])

            col_nom.markdown(f"[{p['nombre_limpio']}]({_url_drive(p['id'])})")
            col_resp.markdown(p["responsable"])
            col_sem.markdown(p["semana_name"])
            col_est.markdown(
                f'<span style="color:{_COLOR["PENDIENTE"]};font-weight:600;">⚪ PENDIENTE</span>',
                unsafe_allow_html=True,
            )

    # Filas ya verificadas (no seleccionables, informativas)
    if ya_verificados:
        with st.expander(f"Ya verificados ({len(ya_verificados)})", expanded=False):
            for p in ya_verificados:
                c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1])
                c1.markdown(f"[{p['nombre_limpio']}]({_url_drive(p['id'])})")
                c2.markdown(p["responsable"])
                c3.markdown(p["semana_name"])
                color = _COLOR.get(p["estado"], _COLOR["PENDIENTE"])
                icono = _ICONO.get(p["estado"], "⚪")
                c4.markdown(
                    f'<span style="color:{color};font-weight:600;">{icono} {p["estado"]}</span>',
                    unsafe_allow_html=True,
                )

    return seleccionados


# ---------------------------------------------------------------------------
# Verificación secuencial con progreso
# ---------------------------------------------------------------------------

def _verificar_cola(seleccionados: list[dict]) -> None:
    """Verifica los proyectos seleccionados mostrando progreso en tiempo real."""
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
# Tabla de resultados de la cola
# ---------------------------------------------------------------------------

def _mostrar_resultados_cola(resultados: list[dict]) -> None:
    st.markdown("### Resultados de la cola")

    # Resumen
    conteo: dict[str, int] = {"BLOQUEADO": 0, "ADVERTENCIAS": 0, "APROBADO": 0, "ERROR": 0}
    for r in resultados:
        if r["error"]:
            conteo["ERROR"] += 1
        else:
            conteo[r["informe"].estado_global] += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔴 BLOQUEADOS", conteo["BLOQUEADO"])
    c2.metric("🟠 ADVERTENCIAS", conteo["ADVERTENCIAS"])
    c3.metric("🟢 APROBADOS", conteo["APROBADO"])
    c4.metric("💥 Errores", conteo["ERROR"])

    st.markdown("---")

    for r in resultados:
        proyecto = r["proyecto"]
        nombre = proyecto["nombre_limpio"]

        if r["error"]:
            with st.expander(f"💥 {nombre}", expanded=True):
                st.error(r["error"])
            continue

        informe: InformeFinal = r["informe"]
        estado = informe.estado_global
        color = _COLOR[estado]
        icono = _ICONO[estado]

        n_fail = len(informe.errores_criticos)
        n_warn = len(informe.advertencias)
        resumen_txt = (
            f"{n_fail} error{'es' if n_fail!=1 else ''}, "
            f"{n_warn} aviso{'s' if n_warn!=1 else ''}"
            if (n_fail or n_warn) else "Sin errores ni avisos"
        )

        with st.expander(
            f"{icono} {nombre}  —  {resumen_txt}",
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

                # Errores bloqueantes
                if informe.errores_criticos:
                    st.markdown("**Errores bloqueantes:**")
                    for c in informe.errores_criticos:
                        st.markdown(f"- ❌ **{c.id}** {c.desc}")
                        if c.detalle:
                            st.caption(f"  → {c.detalle}")

                # Advertencias
                if informe.advertencias:
                    st.markdown("**Advertencias:**")
                    for c in informe.advertencias:
                        st.markdown(f"- ⚠️ **{c.id}** {c.desc}")
                        if c.detalle:
                            st.caption(f"  → {c.detalle}")

            with col_acc:
                st.markdown("**Acciones**")
                estado_drive = proyecto.get("estado", "PENDIENTE")
                estado_clave = _ESTADO_A_CLAVE.get(estado, "bloqueado")

                if estado_drive == estado:
                    st.success(f"Ya aplicado en Drive", icon="✓")
                else:
                    if st.button(
                        f"Aplicar [{estado}]",
                        key=f"btn_estado_{proyecto['id']}",
                        type="primary" if estado == "APROBADO" else "secondary",
                        use_container_width=True,
                    ):
                        with st.spinner("Aplicando en Drive…"):
                            try:
                                aplicar_prefijo_estado(
                                    get_servicio(),
                                    proyecto["id"],
                                    proyecto["name"],
                                    estado_clave,
                                    get_reglas(),
                                )
                                # Actualizar estado local
                                r["proyecto"]["estado"] = estado
                                st.toast(f"✓ {nombre}: [{estado}] aplicado")
                                # Limpiar cache de proyectos
                                _cargar_proyectos_pendientes.clear()
                            except Exception as exc:
                                st.error(str(exc))
                        st.rerun()

                st.link_button(
                    "🔗 Abrir en Drive",
                    url=_url_drive(proyecto["id"]),
                    use_container_width=True,
                )

                # Descarga TXT
                nombre_proyecto = proyecto["nombre_limpio"]
                txt = _informe_a_texto(informe, nombre_proyecto)
                st.download_button(
                    "⬇ Informe .txt",
                    data=txt.encode("utf-8"),
                    file_name=f"informe_{nombre_proyecto}.txt",
                    mime="text/plain",
                    key=f"dl_{proyecto['id']}",
                    use_container_width=True,
                )

    # Botón limpiar
    st.markdown("---")
    if st.button("🗑 Limpiar resultados", type="secondary"):
        st.session_state.cola_resultados = []
        st.rerun()


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Cola Global · Verificador CUBRO",
        page_icon="🪚",
        layout="wide",
    )

    _init_state()

    st.title("🗂 Cola Global de Verificación")
    st.caption(
        "Muestra los proyectos PENDIENTE de la semana más reciente de cada responsable. "
        "Selecciona los que quieras verificar y pulsa el botón."
    )

    # Si hay resultados de una verificación anterior, mostrarlos primero
    if st.session_state.cola_resultados:
        _mostrar_resultados_cola(st.session_state.cola_resultados)
        st.markdown("---")
        st.markdown("### Nueva verificación")

    # Cargar proyectos
    with st.spinner("Escaneando semanas recientes…"):
        try:
            todos = _cargar_proyectos_pendientes(get_servicio())
        except Exception as exc:
            st.error(f"Error al conectar con Drive: {exc}")
            return

    n_pendientes = sum(1 for p in todos if p["estado"] == "PENDIENTE")

    col_hdr, col_btn = st.columns([4, 1])
    col_hdr.markdown(
        f"**{n_pendientes} proyecto{'s' if n_pendientes!=1 else ''} PENDIENTE "
        f"de {len(config.RESPONSABLES)} responsables** (semanas más recientes)"
    )
    if col_btn.button("🔄 Actualizar lista", use_container_width=True):
        _cargar_proyectos_pendientes.clear()
        st.rerun()

    st.markdown("---")

    if not todos:
        st.success("¡No hay proyectos pendientes! Todo verificado.")
        return

    seleccionados = _tabla_seleccion(todos)

    st.markdown("---")

    n_sel = len(seleccionados)
    col_sel, col_all, col_none = st.columns([3, 1, 1])
    col_sel.markdown(f"**{n_sel} seleccionado{'s' if n_sel != 1 else ''}**")

    with col_all:
        if st.button("Seleccionar todos", use_container_width=True):
            pendientes_ids = {p["id"] for p in todos if p["estado"] == "PENDIENTE"}
            st.session_state.cola_seleccion = pendientes_ids
            st.rerun()

    with col_none:
        if st.button("Deseleccionar", use_container_width=True):
            st.session_state.cola_seleccion.clear()
            st.rerun()

    if seleccionados:
        st.markdown("---")
        if st.button(
            f"🚀 Verificar {n_sel} proyecto{'s' if n_sel != 1 else ''}",
            type="primary",
            use_container_width=True,
        ):
            _verificar_cola(seleccionados)


if __name__ == "__main__":
    main()
