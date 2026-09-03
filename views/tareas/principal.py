from __future__ import annotations

import pandas as pd
import streamlit as st

from models.tareas_modulo.contexto import construir_contexto_tareas
from utils.rendimiento import medir_tiempo, mostrar_info_dataframe
from utils.tareas.carga import cargar_fuentes_tareas, invalidar_cache_tareas
from utils.tareas.formatos import preparar_tabla_operativa_visual, resaltar_carro
from utils.tareas.graficos import grafico_avance_despacho, grafico_sectorizaciones
from views.tareas.estadisticas import render_estadisticas_tareas
from utils.tareas.estilo_pantalla import (
    aplicar_estilo_pantalla,
    perfil_visual,
    selector_modo_visual,
)



def _fmt_entero(valor: object) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _detalle_control_finalizado(contexto: dict[str, object]) -> str:
    resumen = contexto["resumen"]
    control = contexto.get("control_dia_anterior", {})

    base = (
        f"Hoy {_fmt_entero(resumen['CarrosFinalizadosHoy'])} · "
        f"Ayer {_fmt_entero(resumen['CarrosFinalizadosAyer'])}"
    )

    if not control or not control.get("disponible"):
        return base + "<br>Control histórico sin datos"

    fecha = control.get("fecha")
    fecha_visible = (
        pd.Timestamp(fecha).strftime("%d/%m")
        if fecha is not None and pd.notna(fecha)
        else "Último cierre"
    )
    etiqueta_fecha = (
        "Ayer"
        if control.get("es_dia_calendario_anterior")
        else fecha_visible
    )

    return (
        base
        + "<br>"
        + f"📦 {etiqueta_fecha}: "
        + f"{_fmt_entero(control.get('unidades', 0))} unidades cerradas"
    )


def _render_kpis(contexto: dict[str, object]) -> None:
    resumen = contexto["resumen"]
    pendiente_pick = contexto["pendiente_pick"]

    tarjetas = [
        (
            "📦 Pedidos pendientes",
            _fmt_entero(contexto["pedidos_pendientes"]),
            f"{_fmt_entero(contexto['unidades_pendientes'])} unidades",
        ),
        (
            "📥 Pendiente de pickear",
            _fmt_entero(pendiente_pick["Preparaciones"]),
            f"{_fmt_entero(pendiente_pick['Unidades'])} unidades",
        ),
        (
            "🛒 Carros en curso",
            _fmt_entero(resumen["CarrosEnCurso"]),
            f"{_fmt_entero(contexto['unidades_carros_curso'])} unidades",
        ),
        (
            "✅ Carros finalizados",
            _fmt_entero(resumen["CarrosFinalizados"]),
            _detalle_control_finalizado(contexto),
        ),
    ]

    html = '<div class="tareas-kpi-grid">'
    for etiqueta, valor, detalle in tarjetas:
        html += (
            '<div class="tareas-kpi-card">'
            f'<div class="tareas-kpi-label">{etiqueta}</div>'
            f'<div class="tareas-kpi-value">{valor}</div>'
            f'<div class="tareas-kpi-detail">{detalle}</div>'
            '</div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_indicadores(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    col_despachos, col_criticos, col_sectores = st.columns(
        [1.05, 1.3, 1.05], vertical_alignment="top"
    )

    with col_despachos:
        with st.container(border=True):
            st.markdown("#### 🚛 Avance de despachos")
            sin_iniciar = contexto["despachos_sin_iniciar"]
            if sin_iniciar:
                st.caption(
                    f"Sin iniciar ({len(sin_iniciar)}): " + " · ".join(sin_iniciar)
                )

            avance = contexto["avance_despachos"]
            if avance.empty:
                st.info("No hay despachos activos con avance parcial.")
            else:
                cantidad_columnas = 3 if perfil == "tv" else 2
                columnas = st.columns(cantidad_columnas)
                for indice, (_, fila) in enumerate(avance.iterrows()):
                    with columnas[indice % cantidad_columnas]:
                        grafico_avance_despacho(fila, perfil=perfil)

    with col_criticos:
        with st.container(border=True):
            st.markdown("#### 🚨 Carros que cierran despachos")
            criticos = contexto["carros_criticos"].copy()
            if criticos.empty:
                st.success("No hay carros críticos en este momento.")
            else:
                if "Unidades" in criticos.columns:
                    criticos["Unidades"] = pd.to_numeric(
                        criticos["Unidades"], errors="coerce"
                    ).fillna(0).astype(int)
                st.dataframe(
                    criticos,
                    width="stretch",
                    hide_index=True,
                    height=430,
                )

    with col_sectores:
        with st.container(border=True):
            st.markdown("#### 📦 Sectores en preparación")
            grafico_sectorizaciones(
                contexto["familias_operativas"],
                perfil=perfil,
            )


def _render_tabla(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    tabla = preparar_tabla_operativa_visual(contexto["tabla_operativa"])
    st.markdown("### 📋 Operación en curso")
    st.caption(f"{len(tabla)} registros activos")

    if tabla.empty:
        st.info("No hay tareas operativas para mostrar.")
        return

    st.dataframe(
        tabla.style.format({"Unidades": "{:.0f}", "SKUs": "{:.0f}"}).apply(
            resaltar_carro, axis=1
        ),
        width="stretch",
        hide_index=True,
        height={"pc": 560, "monitor": 620, "tv": 790}[perfil],
    )


@st.fragment(run_every="5m")
def _render_fragmento_operativo(perfil: str) -> None:
    carga = cargar_fuentes_tareas()
    fuentes = carga["fuentes"]

    faltantes = [
        nombre
        for nombre, clave in [
            ("Informe Tareas", "tareas"),
            ("Pedidos DIGIP", "pedidos"),
            ("Detalle Pendientes", "detalle"),
            ("Maestro Clientes", "clientes"),
            ("Maestro Artículo", "articulos"),
            ("Maestro Volumetría", "volumetria"),
        ]
        if fuentes[clave] is None or fuentes[clave].empty
    ]

    if faltantes:
        st.error("No se puede construir el tablero. Faltan: " + ", ".join(faltantes))
        return

    if carga["actualizacion_completa"]:
        st.caption(
            f"✅ Datos actualizados: {carga['hora_actualizacion']} · "
            "actualización automática cada 5 minutos"
        )
    else:
        st.caption(
            f"⚠️ Último intento: {carga['hora_actualizacion']} · "
            "se conserva información válida anterior"
        )

    if carga["mensajes"]:
        with st.expander("⚠️ Detalle de actualización", expanded=False):
            for mensaje in carga["mensajes"]:
                st.caption(f"• {mensaje}")

    with medir_tiempo("Construir contexto operativo"):
        contexto = construir_contexto_tareas(
            fuentes["tareas"],
            fuentes["pedidos"],
            fuentes["detalle"],
            fuentes["clientes"],
            fuentes["articulos"],
            fuentes["volumetria"],
            fuentes.get("control_historico"),
        )

    mostrar_info_dataframe("Tabla pedidos", contexto["tabla_pedidos"])
    mostrar_info_dataframe("Tabla tareas", contexto["tabla_tareas"])
    mostrar_info_dataframe("Tabla operativa", contexto["tabla_operativa"])

    _render_kpis(contexto)
    _render_indicadores(contexto, perfil=perfil)
    _render_tabla(contexto, perfil=perfil)


def render_tareas() -> None:
    with st.sidebar:
        st.markdown("### Visualización")
        modo = selector_modo_visual()
        st.toggle("Diagnóstico de rendimiento", key="debug_rendimiento")

    perfil = perfil_visual(modo)
    aplicar_estilo_pantalla(modo)

    encabezado, acciones = st.columns([5, 1], vertical_alignment="center")
    with encabezado:
        st.title("📋 Centro de Control Operativo")
        st.caption("Seguimiento en vivo de pedidos, carros, despachos y sectores")
    with acciones:
        if st.button("🔄 Actualizar ahora", width="stretch"):
            invalidar_cache_tareas()
            construir_contexto_tareas.clear()
            st.rerun()

    tab_operacion, tab_estadisticas = st.tabs(["⚡ Operación en vivo", "📊 Estadísticas"])
    with tab_operacion:
        _render_fragmento_operativo(perfil)
    with tab_estadisticas:
        render_estadisticas_tareas()
