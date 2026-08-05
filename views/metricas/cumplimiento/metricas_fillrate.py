from __future__ import annotations

from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from models.cumplimiento.indicadores_fillrate import calcular_fill_rate, resumir_fill_rate
from utils.metricas.metricas_helpers import formatear_entero, limitar_previsualizacion


def _opciones(tabla: pd.DataFrame, columna: str) -> list[str]:
    if columna not in tabla.columns:
        return []
    return sorted(tabla[columna].fillna("").astype(str).str.strip().loc[lambda s: s.ne("")].unique().tolist())


def _donut(titulo: str, pedidas: float, controladas: float, key: str) -> None:
    porcentaje = controladas / pedidas * 100 if pedidas > 0 else 0.0
    faltantes = max(pedidas - controladas, 0.0)
    figura = go.Figure(go.Pie(
        labels=["Controladas", "Faltantes"],
        values=[controladas, faltantes],
        hole=0.68,
        textinfo="none",
        hovertemplate="%{label}: %{value:,.0f}<extra></extra>",
    ))
    figura.add_annotation(
        text=f"<b>{porcentaje:.1f}%</b><br><span style='font-size:11px'>Fill Rate</span>",
        x=.5, y=.5, showarrow=False,
    )
    figura.update_layout(
        title=dict(text=titulo, x=.5), template="plotly_dark", height=270,
        margin=dict(l=5, r=5, t=48, b=5), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(figura, width="stretch", config={"displaylogo": False}, key=key)
    st.caption(f"{controladas:,.0f} de {pedidas:,.0f} unidades")


def render(contexto: dict) -> None:
    base = contexto.get("df_fillrate_pedidos", pd.DataFrame()).copy()
    if base.empty:
        st.warning("No hay pedidos disponibles para calcular Fill Rate.")
        return

    st.markdown("### 📦 Fill Rate operativo")
    st.caption(
        "Fill Rate por cohorte mensual: unidades pedidas por pedidos creados "
        "en el mes versus unidades controladas hasta el cierre de ese mismo "
        "mes. Los controles efectuados después quedan como recuperación "
        "posterior y no modifican retroactivamente el indicador."
    )
    st.info(
        "El universo incluye pedidos abiertos, pendientes y recientes. Para "
        "cada pedido se fija como corte el último día de su mes de creación: "
        "lo controlado en el mes siguiente permanece como faltante del mes "
        "original y se muestra como recuperación posterior."
    )

    fechas = pd.to_datetime(
        base.get("FechaReferenciaFillRate", base.get("FechaHoraCreacion")),
        errors="coerce",
    )
    fecha_min = fechas.dropna().min().date() if fechas.notna().any() else pd.Timestamp.today().date()
    fecha_max = fechas.dropna().max().date() if fechas.notna().any() else fecha_min

    with st.form("form_filtros_fillrate", border=True):
        c1, c2, c3, c4 = st.columns([1.3, 1.1, 1.2, 1.8], vertical_alignment="bottom")
        rango = c1.date_input(
            "Período de creación", value=(fecha_min, fecha_max),
            min_value=fecha_min, max_value=fecha_max, format="DD/MM/YYYY",
        )
        circuitos = c2.multiselect("Circuito", _opciones(base, "TipoCircuito"), placeholder="Todos")
        grupos = c3.multiselect("Grupo de entrega", _opciones(base, "GrupoEntrega"), placeholder="Todos")
        busqueda = c4.text_input("Pedido o cliente", placeholder="Buscar...")
        aplicar, borrar, _ = st.columns([1, 1, 5])
        btn_aplicar = aplicar.form_submit_button("✅ Aplicar filtros", type="primary", width="stretch")
        btn_borrar = borrar.form_submit_button("🧹 Borrar filtros", width="stretch")

    defaults = {
        "fillrate_fecha_desde": fecha_min,
        "fillrate_fecha_hasta": fecha_max,
        "fillrate_circuitos": [], "fillrate_grupos": [], "fillrate_busqueda": "",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)
    if btn_borrar:
        for k, v in defaults.items(): st.session_state[k] = v
        st.rerun()
    if btn_aplicar:
        valores = list(rango) if isinstance(rango, (tuple, list)) else [rango, rango]
        if len(valores) == 1: valores = [valores[0], valores[0]]
        st.session_state["fillrate_fecha_desde"] = valores[0]
        st.session_state["fillrate_fecha_hasta"] = valores[-1]
        st.session_state["fillrate_circuitos"] = circuitos
        st.session_state["fillrate_grupos"] = grupos
        st.session_state["fillrate_busqueda"] = busqueda
        st.rerun()

    visible = base.copy()
    fecha_ref = pd.to_datetime(
        visible.get("FechaReferenciaFillRate", visible.get("FechaHoraCreacion")),
        errors="coerce",
    )
    visible = visible.loc[
        fecha_ref.dt.date.between(
            st.session_state["fillrate_fecha_desde"], st.session_state["fillrate_fecha_hasta"]
        )
    ].copy()
    if st.session_state["fillrate_circuitos"]:
        visible = visible.loc[visible["TipoCircuito"].isin(st.session_state["fillrate_circuitos"])].copy()
    if st.session_state["fillrate_grupos"]:
        visible = visible.loc[visible["GrupoEntrega"].isin(st.session_state["fillrate_grupos"])].copy()
    texto = str(st.session_state["fillrate_busqueda"] or "").strip()
    if texto:
        mascara = pd.Series(False, index=visible.index)
        for col in ["Pedido", "ClienteFinal", "ClienteCodigo"]:
            if col in visible: mascara |= visible[col].fillna("").astype(str).str.contains(texto, case=False, na=False)
        visible = visible.loc[mascara].copy()

    visible, diag = calcular_fill_rate(visible)
    if visible.empty:
        st.warning("No hay datos para los filtros aplicados.")
        return

    pedidas = diag["unidades_pedidas"]; controladas = diag["unidades_controladas"]
    faltantes = diag["unidades_faltantes"]; pct = diag["fill_rate_pct"]
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Fill Rate al cierre", f"{pct:.1f}%")
    k2.metric("Unidades pedidas", formatear_entero(pedidas))
    k3.metric("Controladas en el mes", formatear_entero(controladas))
    k4.metric("Pendientes al cierre", formatear_entero(faltantes), delta_color="inverse")
    k5.metric("Pedidos evaluados", formatear_entero(diag["pedidos_evaluados"]))

    r1, r2 = st.columns(2)
    r1.metric(
        "Unidades recuperadas después",
        formatear_entero(diag.get("unidades_controladas_posteriores", 0)),
        help="Unidades de la cohorte que se controlaron en un mes posterior.",
    )
    r2.metric(
        "Pedidos completados después",
        formatear_entero(diag.get("pedidos_completados_posteriormente", 0)),
        help="Pedidos incompletos al cierre de su mes que luego terminaron de controlarse.",
    )

    st.markdown("#### Fill Rate por circuito")
    cols = st.columns(5)
    circuitos_principales = ["ZONA", "EXPRESO", "RETIRA", "DIARIO", "CON TURNO"]
    etiquetas_circuito = {"CON TURNO": "EASY / CON TURNO"}
    for col, circuito in zip(cols, circuitos_principales):
        with col:
            serie_circuito = visible.get(
                "TipoCircuito", pd.Series("", index=visible.index)
            ).fillna("").astype(str).str.upper()
            bloque = visible.loc[serie_circuito.eq(circuito)]
            resumen = resumir_fill_rate(bloque, ["TipoCircuito"])
            if resumen.empty:
                st.info(f"{etiquetas_circuito.get(circuito, circuito)}: sin datos")
            else:
                fila = resumen.iloc[0]
                _donut(etiquetas_circuito.get(circuito, circuito), float(fila["UnidadesPedidas"]), float(fila["UnidadesControladas"]), f"fillrate_{circuito}")

    visible["Mes"] = pd.to_datetime(
        visible.get("FechaReferenciaFillRate", visible.get("FechaHoraCreacion")),
        errors="coerce",
    ).dt.to_period("M").dt.to_timestamp()
    mensual = resumir_fill_rate(visible.dropna(subset=["Mes"]), ["Mes"])
    circuito = resumir_fill_rate(visible, ["TipoCircuito"])
    g1, g2 = st.columns(2)
    with g1:
        if not mensual.empty:
            fig = px.line(mensual, x="Mes", y="FillRatePct", markers=True, title="Evolución mensual", labels={"FillRatePct": "% Fill Rate"})
            fig.update_yaxes(range=[0, 105]); fig.update_layout(template="plotly_dark", height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
    with g2:
        if not circuito.empty:
            fig = px.bar(circuito, x="TipoCircuito", y="FillRatePct", text="FillRatePct", title="Cumplimiento por circuito")
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside"); fig.update_yaxes(range=[0,105]); fig.update_layout(template="plotly_dark", height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

    clientes = resumir_fill_rate(visible, ["ClienteFinal"])
    if (
        not clientes.empty
        and "UnidadesPedidas" in clientes.columns
    ):
        clientes = (
            clientes.loc[clientes["UnidadesPedidas"].gt(0)]
            .sort_values(
                ["FillRatePct", "UnidadesFaltantes"],
                ascending=[True, False],
            )
            .head(15)
        )
    else:
        clientes = pd.DataFrame()

    if not clientes.empty:
        fig = px.bar(clientes.sort_values("FillRatePct", ascending=False), x="FillRatePct", y="ClienteFinal", orientation="h", text="FillRatePct", title="Clientes con menor Fill Rate")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside"); fig.update_xaxes(range=[0,105]); fig.update_layout(template="plotly_dark", height=480, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

    st.markdown("#### Detalle de Fill Rate por pedido")
    columnas = [c for c in [
        "Pedido", "ClienteFinal", "EstadoPedido", "EstadoPreparacion",
        "TipoCircuito", "GrupoEntrega", "FechaHoraCreacion",
        "FechaHoraInicioPreparacion", "FechaHoraFinControl",
        "FechaCorteFillRate", "EstadoCierreFillRate",
        "UnidadesPedidas", "UnidadesControladasFillRate",
        "UnidadesControladasPosteriores", "UnidadesFaltantesFillRate",
        "FechaPrimerControlPosteriorCierre", "FillRatePedidoPct",
    ] if c in visible]
    detalle = visible[columnas].sort_values(["UnidadesFaltantesFillRate", "FillRatePedidoPct"], ascending=[False, True])
    st.dataframe(limitar_previsualizacion(detalle, 3000), width="stretch", hide_index=True)

    salida = BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        detalle.to_excel(writer, index=False, sheet_name="Fill Rate Pedidos")
        mensual.to_excel(writer, index=False, sheet_name="Evolucion Mensual")
        circuito.to_excel(writer, index=False, sheet_name="Por Circuito")
        clientes.to_excel(writer, index=False, sheet_name="Clientes Criticos")
    st.download_button("📥 Descargar análisis Fill Rate", salida.getvalue(), "Fill_Rate_Operativo.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

    sin_denominador = int(diag.get("pedidos_sin_unidades_pedidas", 0))
    if sin_denominador:
        st.warning(
            f"{sin_denominador} pedidos del reporte no tienen unidades pedidas "
            "identificables y no ingresan al Fill Rate."
        )
