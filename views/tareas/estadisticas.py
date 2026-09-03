from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from models.tareas_modulo.estadisticas_tareas import (
    construir_base_estadisticas,
    construir_eventos_hibridos,
    estado_calidad,
    resumen_usuarios,
)
from utils.tareas.carga import cargar_fuentes_tareas
from utils.estilo_graficos import aplicar_formato_visual_plotly


def _fmt(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")



def _render_kpi_cards(items: list[tuple[str, str, str]]) -> None:
    """Renderiza KPIs sin saltos/indentación que Markdown pueda tratar como código."""
    cards = []
    for label, value, detail in items:
        cards.append(
            f'<div class="tareas-kpi-card">'
            f'<div class="tareas-kpi-label">{label}</div>'
            f'<div class="tareas-kpi-value">{value}</div>'
            f'<div class="tareas-kpi-detail">{detail}</div>'
            f'</div>'
        )
    html = '<div class="tareas-kpi-grid">' + ''.join(cards) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


def _col_unidades(df: pd.DataFrame) -> str:
    return "UnidadesProceso" if "UnidadesProceso" in df.columns else "Unidades"


def _filtrar(eventos: pd.DataFrame, desde, hasta, usuario, despacho, sector):
    x = eventos.copy()
    x = x.loc[(x["FechaEvento"].dt.date >= desde) & (x["FechaEvento"].dt.date <= hasta)]
    if usuario != "Todos": x = x.loc[x["Usuario"].eq(usuario)]
    if despacho != "Todos" and "DespachoDescripcion" in x: x = x.loc[x["DespachoDescripcion"].eq(despacho)]
    if sector != "Todos" and "Sectorizacion" in x: x = x.loc[x["Sectorizacion"].fillna("").astype(str).eq(sector)]
    return x


def _opciones_combinadas(pick: pd.DataFrame, control: pd.DataFrame, columna: str) -> list[str]:
    valores: set[str] = set()
    for df in (pick, control):
        if not df.empty and columna in df.columns:
            valores.update(df[columna].dropna().astype(str).str.strip().loc[lambda x: x.ne("")].tolist())
    return ["Todos"] + sorted(valores)


def _tabla_ranking(eventos: pd.DataFrame, proceso: str) -> pd.DataFrame:
    ranking = resumen_usuarios(eventos)
    if ranking.empty:
        return ranking

    tabla = ranking.copy()
    tabla.insert(0, "#", range(1, len(tabla) + 1))
    if proceso == "Control":
        tabla = tabla.rename(columns={"Tareas": "Controles", "Unid/Tarea": "Unid/Control"})

    # Fila TOTAL para validar rápidamente el proceso contra sus KPI.
    col_eventos = "Controles" if proceso == "Control" else "Tareas"
    col_ratio = "Unid/Control" if proceso == "Control" else "Unid/Tarea"
    total_eventos = int(pd.to_numeric(eventos.get("EventosMetric", 0), errors="coerce").fillna(0).sum())
    total_unidades = float(pd.to_numeric(eventos.get("UnidadesProceso", 0), errors="coerce").fillna(0).sum())
    total = {
        "#": "",
        "Usuario": "TOTAL",
        col_eventos: total_eventos,
        "Preparaciones": int(eventos["Id"].nunique()) if "Id" in eventos else 0,
        "Unidades": int(total_unidades),
        "SKUs": int(eventos["CodigoArticulo"].nunique()) if "CodigoArticulo" in eventos else 0,
        col_ratio: round(total_unidades / total_eventos, 1) if total_eventos else 0.0,
        "Participacion": 100.0 if total_unidades else 0.0,
    }
    if "Pickeos" in tabla.columns:
        total["Pickeos"] = int(pd.to_numeric(eventos.get("PickeosMetric", 0), errors="coerce").fillna(0).sum())
    tabla = pd.concat([tabla, pd.DataFrame([total])], ignore_index=True)
    tabla["Participacion"] = tabla["Participacion"].map(lambda v: f"{float(v):.1f}%")
    return tabla


def _grafico_participacion(eventos: pd.DataFrame, titulo: str) -> None:
    if eventos is None or eventos.empty:
        st.info(f"Sin actividad para calcular participación de {titulo}.")
        return

    col_u = _col_unidades(eventos)
    participacion = (
        eventos.groupby("Usuario", as_index=False)[col_u]
        .sum()
        .rename(columns={col_u: "Unidades"})
        .sort_values("Unidades", ascending=False)
    )
    participacion["Unidades"] = pd.to_numeric(participacion["Unidades"], errors="coerce").fillna(0)
    participacion = participacion.loc[participacion["Unidades"].gt(0)]
    if participacion.empty:
        st.info(f"Sin unidades para calcular participación de {titulo}.")
        return

    fig = px.pie(participacion, names="Usuario", values="Unidades", hole=.42)
    fig = aplicar_formato_visual_plotly(fig, altura=390)
    fig.update_layout(legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_estadisticas_tareas() -> None:
    carga = cargar_fuentes_tareas()
    fuentes = carga["fuentes"]
    crudo = fuentes.get("preparaciones_historico", pd.DataFrame())
    if crudo is None or crudo.empty:
        st.warning("No encontré archivos 'Filtrar Preparacion*' dentro de Data_WMS.")
        st.caption("La vista queda lista: al publicar el reporte en esa carpeta se alimentará automáticamente.")
        return

    base = construir_base_estadisticas(crudo, fuentes.get("articulos"))
    pick, control = construir_eventos_hibridos(
        base,
        fuentes.get("preparacion_analitico"),
        fuentes.get("control_historico"),
        fuentes.get("articulos"),
    )

    fechas = pd.concat([
        pick.get("FechaEvento", pd.Series(dtype="datetime64[ns]")),
        control.get("FechaEvento", pd.Series(dtype="datetime64[ns]")),
    ]).dropna()
    if fechas.empty:
        st.info("El histórico no contiene eventos de Picking o Control con fecha válida.")
        return

    st.subheader("📊 Estadísticas de Operación")
    st.caption("Modelo híbrido: analíticos DIGIP para datos consolidados + Filtrar Preparación para el delta en vivo.")
    st.caption(f"Histórico disponible: {fechas.min().date().strftime('%d/%m/%Y')} a {fechas.max().date().strftime('%d/%m/%Y')}. Por defecto se abre el último día disponible.")

    c1, c2, c3, c4 = st.columns([1.15, 1.15, 1.6, 1.5])
    with c1:
        fecha_ultima = fechas.max().date()
        desde = st.date_input("Desde", value=fecha_ultima, key="est_desde_v3")
    with c2:
        hasta = st.date_input("Hasta", value=fecha_ultima, key="est_hasta_v3")

    usuarios = _opciones_combinadas(pick, control, "Usuario")
    despachos = _opciones_combinadas(pick, control, "DespachoDescripcion")
    sectores = _opciones_combinadas(pick, control, "Sectorizacion")
    with c3:
        usuario = st.selectbox("Usuario", usuarios, key="est_usuario_v3")
    with c4:
        despacho = st.selectbox("Despacho", despachos, key="est_despacho_v3")
    sector = st.selectbox("Sectorización", sectores, key="est_sector_v3")

    pick_f = _filtrar(pick, desde, hasta, usuario, despacho, sector)
    control_f = _filtrar(control, desde, hasta, usuario, despacho, sector)
    combinado = pd.concat([pick_f, control_f], ignore_index=True, sort=False)

    if combinado.empty:
        st.info("No hay registros para los filtros seleccionados.")
        return

    estado_p, detalle_p = estado_calidad(pick, desde, hasta)
    estado_c, detalle_c = estado_calidad(control, desde, hasta)
    st.caption(f"Picking: {estado_p} — {detalle_p} · Control: {estado_c} — {detalle_c}")

    def _kpis_proceso(df: pd.DataFrame) -> dict[str, int]:
        if df is None or df.empty:
            return {"unidades": 0, "eventos": 0, "pickeos": 0, "preparaciones": 0, "skus": 0, "usuarios": 0}
        return {
            "unidades": int(pd.to_numeric(df.get(_col_unidades(df), 0), errors="coerce").fillna(0).sum()),
            "eventos": int(pd.to_numeric(df.get("EventosMetric", 0), errors="coerce").fillna(0).sum()),
            "pickeos": int(pd.to_numeric(df.get("PickeosMetric", 0), errors="coerce").fillna(0).sum()),
            "preparaciones": int(df["Id"].nunique()) if "Id" in df else 0,
            "skus": int(df["CodigoArticulo"].replace("", pd.NA).dropna().nunique()) if "CodigoArticulo" in df else 0,
            "usuarios": int(df["Usuario"].nunique()) if "Usuario" in df else 0,
        }

    kp = _kpis_proceso(pick_f)
    kc = _kpis_proceso(control_f)

    st.markdown("#### 🏆 KPIs Picking")
    _render_kpi_cards([
        ("Unidades pickeadas", _fmt(kp["unidades"]), "Volumen procesado en Picking"),
        ("Pickeos", _fmt(kp["pickeos"]), "Líneas de pickeo registradas"),
        ("Tareas", _fmt(kp["eventos"]), "CuantasTareas consolidado / proxy en vivo"),
        ("SKUs", _fmt(kp["skus"]), "Artículos únicos trabajados"),
        ("Usuarios activos", _fmt(kp["usuarios"]), "Operarios con actividad"),
    ])

    st.markdown("#### 📦 KPIs Control")
    _render_kpi_cards([
        ("Unidades controladas", _fmt(kc["unidades"]), "Volumen procesado en Control"),
        ("Pickeos control", _fmt(kc["pickeos"]), "Líneas controladas"),
        ("Controles", _fmt(kc["eventos"]), "ControlContenedor detectados"),
        ("SKUs", _fmt(kc["skus"]), "Artículos únicos controlados"),
        ("Usuarios activos", _fmt(kc["usuarios"]), "Operarios con actividad"),
    ])

    # PICKING: tabla + participación del proceso
    st.markdown("### 🏆 Picking")
    col_tabla_pick, col_grafico_pick = st.columns([1.55, .85], vertical_alignment="top")
    with col_tabla_pick:
        tabla_pick = _tabla_ranking(pick_f, "Picking")
        if tabla_pick.empty:
            st.info("Sin actividad de Picking para los filtros seleccionados.")
        else:
            st.dataframe(tabla_pick, hide_index=True, width="stretch", height=390)
    with col_grafico_pick:
        st.markdown("#### 📊 Participación Picking")
        _grafico_participacion(pick_f, "Picking")

    st.divider()

    # CONTROL: tabla + participación del proceso
    st.markdown("### 📦 Control")
    col_tabla_control, col_grafico_control = st.columns([1.55, .85], vertical_alignment="top")
    with col_tabla_control:
        tabla_control = _tabla_ranking(control_f, "Control")
        if tabla_control.empty:
            st.info("Sin actividad de Control para los filtros seleccionados.")
        else:
            st.dataframe(tabla_control, hide_index=True, width="stretch", height=390)
    with col_grafico_control:
        st.markdown("#### 📊 Participación Control")
        _grafico_participacion(control_f, "Control")

    st.caption("Picking y Control se muestran como procesos independientes. Se excluyen los pedidos cuyo código comienza con TR o RM.")

    st.markdown("### 👤 Radiografía de usuario")
    opciones = sorted(combinado["Usuario"].dropna().astype(str).unique().tolist())
    elegido = st.selectbox("Seleccionar operario", opciones, key="est_detalle_usuario_v3")
    u = combinado.loc[combinado["Usuario"].eq(elegido)].copy()

    a, b = st.columns(2)
    with a:
        col_u = _col_unidades(u)
        por_hora = u.groupby("Hora", as_index=False)[col_u].sum().rename(columns={col_u: "Unidades"})
        fig = px.bar(por_hora, x="Hora", y="Unidades", title="Actividad por hora")
        fig = aplicar_formato_visual_plotly(fig, altura=330)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with b:
        if "Sectorizacion" in u.columns and u["Sectorizacion"].notna().any():
            col_u = _col_unidades(u)
            fam = (
                u.groupby("Sectorizacion", as_index=False)[col_u]
                .sum()
                .rename(columns={col_u: "Unidades"})
                .sort_values("Unidades", ascending=False)
            )
            fig = px.bar(fam, x="Unidades", y="Sectorizacion", orientation="h", title="Unidades por sectorización")
            fig = aplicar_formato_visual_plotly(fig, altura=330)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        else:
            st.info("Sin sectorización disponible para este usuario.")

    st.markdown("### 🔎 Detalle de preparaciones")
    cols = [c for c in [
        "Proceso", "FechaEvento", "Id", "PedidoCodigos", "DespachoDescripcion",
        "CodigoArticulo", "Articulo", "UnidadesProceso", "Unidades", "Contenedor", "Sectorizacion", "Familia"
    ] if c in u.columns]
    detalle = u[cols].sort_values("FechaEvento", ascending=False).copy()
    st.dataframe(detalle, hide_index=True, width="stretch", height=500)
