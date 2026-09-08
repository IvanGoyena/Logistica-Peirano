from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from models.tareas_modulo.estadisticas_tareas import (
    construir_base_estadisticas,
    construir_eventos_hibridos,
    estado_calidad,
    resumen_usuarios,
    construir_score_productividad,
    construir_campeonato_productividad,
)
from utils.tareas.carga import cargar_fuentes_tareas
from utils.estilo_graficos import aplicar_formato_visual_plotly


# Usuarios que no deben participar de esta vista estadística.
# Se normaliza el texto para que diferencias de mayúsculas/minúsculas
# o espacios no vuelvan a incorporarlos.
USUARIOS_EXCLUIDOS_ESTADISTICAS = {
    "GASTON ALEJANDRO KIRICZUK",
    "IVAN GOYENA",
    "LUCAS VEGA",
    "JUAN MANUEL ESPINDOLA",
}


def _normalizar_usuario(valor) -> str:
    return " ".join(str(valor).strip().upper().split())


def _excluir_usuarios(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "Usuario" not in df.columns:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    x = df.copy()
    normalizados = x["Usuario"].fillna("").map(_normalizar_usuario)
    return x.loc[~normalizados.isin(USUARIOS_EXCLUIDOS_ESTADISTICAS)].copy()


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
    tabla.insert(0, "#", pd.Series(range(1, len(tabla) + 1), dtype="string"))
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
    carga = cargar_fuentes_tareas(incluir_estadisticas=True)
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

    # Regla global de esta vista: estos usuarios no participan de KPIs,
    # rankings, gráficos, filtros ni radiografía.
    pick = _excluir_usuarios(pick)
    control = _excluir_usuarios(control)

    fechas = pd.concat([
        pick.get("FechaEvento", pd.Series(dtype="datetime64[ns]")),
        control.get("FechaEvento", pd.Series(dtype="datetime64[ns]")),
    ]).dropna()
    if fechas.empty:
        st.info("El histórico no contiene eventos de Picking o Control con fecha válida.")
        return


    st.markdown(
        """
        <style>
        .tareas-kpi-grid {
            display: grid !important;
            grid-template-columns: repeat(6, minmax(0, 1fr)) !important;
            gap: 10px !important;
            width: 100% !important;
            align-items: stretch !important;
            margin-bottom: 10px !important;
        }
        .tareas-kpi-card {
            min-width: 0 !important;
            min-height: 112px !important;
            padding: 11px 13px !important;
            border-radius: 10px !important;
        }
        .tareas-kpi-label {
            font-size: 0.86rem !important;
            line-height: 1.15 !important;
            margin-bottom: 7px !important;
        }
        .tareas-kpi-value {
            font-size: 1.9rem !important;
            line-height: 1.05 !important;
            margin-bottom: 8px !important;
        }
        .tareas-kpi-detail {
            font-size: 0.75rem !important;
            line-height: 1.2 !important;
        }
        @media (max-width: 1100px) {
            .tareas-kpi-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

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

    # KPI gerencial de Control:
    # contamos preparaciones/carros únicos controlados, no ControlContenedorId.
    # Priorizamos IdPreparacion si está disponible; "Id" queda como respaldo
    # porque el modelo híbrido puede normalizar allí el identificador de preparación.
    if control_f is None or control_f.empty:
        carros_controlados = 0
    elif "IdPreparacion" in control_f.columns:
        carros_controlados = int(
            control_f["IdPreparacion"]
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )
    elif "Id" in control_f.columns:
        carros_controlados = int(
            control_f["Id"]
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )
    else:
        carros_controlados = 0

    # Promedio solicitado: primer KPI / segundo KPI.
    # Picking = Unidades pickeadas / Pickeos
    # Control = Unidades controladas / Pickeos control
    promedio_lineas_pick = (
        kp["unidades"] / kp["pickeos"]
        if kp["pickeos"] else 0
    )
    promedio_lineas_control = (
        kc["unidades"] / kc["pickeos"]
        if kc["pickeos"] else 0
    )

    st.markdown("#### 🏆 KPIs Picking")
    _render_kpi_cards([
        ("Unidades pickeadas", _fmt(kp["unidades"]), "Volumen procesado en Picking"),
        ("Pickeos", _fmt(kp["pickeos"]), "Líneas de pickeo registradas"),
        ("Tareas", _fmt(kp["eventos"]), "CuantasTareas consolidado / proxy en vivo"),
        ("SKUs", _fmt(kp["skus"]), "Artículos únicos trabajados"),
        ("Usuarios activos", _fmt(kp["usuarios"]), "Operarios con actividad"),
        ("Promedio líneas", f"{promedio_lineas_pick:.2f}", "Unidades / pickeos"),
    ])

    st.markdown("#### 📦 KPIs Control")
    _render_kpi_cards([
        ("Unidades controladas", _fmt(kc["unidades"]), "Volumen procesado en Control"),
        ("Pickeos control", _fmt(kc["pickeos"]), "Líneas controladas"),
        ("Carros controlados", _fmt(carros_controlados), "Preparaciones / carros únicos controlados"),
        ("SKUs", _fmt(kc["skus"]), "Artículos únicos controlados"),
        ("Usuarios activos", _fmt(kc["usuarios"]), "Operarios con actividad"),
        ("Promedio líneas", f"{promedio_lineas_control:.2f}", "Unidades / pickeos control"),
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


    # ======================================================
    # SCORE + CAMPEONATO DE PRODUCTIVIDAD PICKING
    # ======================================================
    st.divider()
    st.markdown("### 🏆 Score y Campeonato de Productividad Picking")
    st.caption(
        "Cada tarea cerrada genera un Score de 0–120 y suma puntos al campeonato. "
        "Score = eficiencia de la tarea · Puntos = mérito acumulado. "
        "Referencias mensuales estables · Jornada productiva 06:00–17:00."
    )

    tareas_camp, diario_camp, mensual_camp, refs_camp = construir_campeonato_productividad(
        fuentes.get("preparacion_analitico"),
        fuentes.get("volumetria"),
        fuentes.get("ubicaciones"),
        fecha_referencia=hasta,
        usuarios_excluidos=USUARIOS_EXCLUIDOS_ESTADISTICAS,
    )

    # ------------------------------------------------------
    # RANKING DEL DÍA / PERÍODO SELECCIONADO
    # ------------------------------------------------------
    if tareas_camp.empty:
        st.info("Todavía no hay tareas cerradas del Analítico para calcular puntos en este mes.")
    else:
        dias_sel = tareas_camp.loc[
            (tareas_camp["Fecha"].dt.date >= desde)
            & (tareas_camp["Fecha"].dt.date <= hasta)
        ].copy()
        if usuario != "Todos":
            dias_sel = dias_sel.loc[dias_sel["Usuario"].eq(usuario)].copy()

        st.markdown("#### 📅 Ranking del período seleccionado")
        if dias_sel.empty:
            st.info(
                "Hay actividad en vivo, pero todavía no hay tareas cerradas/consolidadas "
                "en el Analítico para este período. Los puntos se incorporan cuando la tarea cierra."
            )
        else:
            ranking_periodo = (
                dias_sel.groupby("Usuario", as_index=False)
                .agg(
                    Puntos=("PuntosTarea", "sum"),
                    Score=("ScoreTarea", "mean"),
                    Tareas=("TareaId", "nunique"),
                    Horas=("Horas", "sum"),
                    Unidades=("Unidades", "sum"),
                    Lineas=("Lineas", "sum"),
                )
                .sort_values(["Puntos", "Score"], ascending=False)
                .reset_index(drop=True)
            )
            ranking_periodo.insert(0, "#", range(1, len(ranking_periodo) + 1))
            ranking_periodo["Puntos"] = ranking_periodo["Puntos"].round(1)
            ranking_periodo["Score"] = ranking_periodo["Score"].round(1)
            ranking_periodo["Horas"] = ranking_periodo["Horas"].round(2)

            rp1, rp2 = st.columns([1.55, .85], vertical_alignment="top")
            with rp1:
                st.dataframe(ranking_periodo, hide_index=True, width="stretch", height=330)
            with rp2:
                graf = ranking_periodo.sort_values("Puntos", ascending=True)
                fig = px.bar(
                    graf, x="Puntos", y="Usuario", orientation="h",
                    text="Puntos", title="Puntos del período",
                )
                fig = aplicar_formato_visual_plotly(fig, altura=330)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        # --------------------------------------------------
        # RANKING MENSUAL
        # --------------------------------------------------
        mes_nombre = pd.Timestamp(hasta).strftime("%m/%Y")
        st.markdown(f"#### 🏆 Ranking mensual · {mes_nombre}")

        tabla_mes = mensual_camp.copy()
        if usuario != "Todos":
            tabla_mes = tabla_mes.loc[tabla_mes["Usuario"].eq(usuario)].copy()
        tabla_mes = tabla_mes.rename(columns={
            "PosicionMes": "#",
            "ScorePromedio": "Score prom.",
            "PuntosMes": "Puntos",
            "DiasActivos": "Días",
            "Oro": "🥇",
            "Plata": "🥈",
            "Bronce": "🥉",
        })
        cols_mes = ["#", "Usuario", "Puntos", "Score prom.", "Días", "Tareas", "Horas", "Unidades", "Líneas", "🥇", "🥈", "🥉"]
        tabla_mes = tabla_mes.rename(columns={"Lineas": "Líneas"})
        tabla_mes = tabla_mes[[c for c in cols_mes if c in tabla_mes.columns]]

        rm1, rm2 = st.columns([1.55, .85], vertical_alignment="top")
        with rm1:
            st.dataframe(tabla_mes, hide_index=True, width="stretch", height=390)
        with rm2:
            graf_mes = mensual_camp.sort_values("PuntosMes", ascending=True)
            fig = px.bar(
                graf_mes, x="PuntosMes", y="Usuario", orientation="h",
                text="PuntosMes", title="Campeonato mensual",
            )
            fig = aplicar_formato_visual_plotly(fig, altura=390)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        # --------------------------------------------------
        # EVOLUCIÓN DIARIA DEL MES
        # --------------------------------------------------
        st.markdown("#### 📈 Evolución diaria")
        evo = diario_camp.copy()
        if usuario != "Todos":
            evo = evo.loc[evo["Usuario"].eq(usuario)].copy()
        if not evo.empty:
            e1, e2 = st.columns(2, vertical_alignment="top")
            with e1:
                fig = px.line(
                    evo, x="FechaDia", y="Score", color="Usuario",
                    markers=True, title="Score diario",
                )
                fig = aplicar_formato_visual_plotly(fig, altura=360)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
            with e2:
                # Acumulado real de puntos a medida que avanza el mes.
                acum = evo.sort_values(["Usuario", "FechaDia"]).copy()
                acum["Puntos acumulados"] = acum.groupby("Usuario")["Puntos"].cumsum()
                fig = px.line(
                    acum, x="FechaDia", y="Puntos acumulados", color="Usuario",
                    markers=True, title="Puntos acumulados del mes",
                )
                fig = aplicar_formato_visual_plotly(fig, altura=360)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        # --------------------------------------------------
        # DESGLOSE POR USUARIO + TAREAS QUE SUMARON PUNTOS
        # --------------------------------------------------
        st.markdown("#### 🔎 Puntos tarea por tarea")
        opciones_camp = mensual_camp["Usuario"].tolist()
        if usuario != "Todos" and usuario in opciones_camp:
            indice_default = opciones_camp.index(usuario)
        else:
            indice_default = 0

        elegido_camp = st.selectbox(
            "Operario para analizar",
            opciones_camp,
            index=indice_default,
            key="est_campeonato_usuario_v2",
        )
        tareas_u = tareas_camp.loc[tareas_camp["Usuario"].eq(elegido_camp)].copy()
        tareas_u = tareas_u.loc[
            (tareas_u["Fecha"].dt.date >= desde)
            & (tareas_u["Fecha"].dt.date <= hasta)
        ].copy()

        if tareas_u.empty:
            st.info("Ese operario no tiene tareas cerradas dentro del período seleccionado.")
        else:
            resumen_u = mensual_camp.loc[mensual_camp["Usuario"].eq(elegido_camp)].iloc[0]
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Puntos mes", f"{resumen_u['PuntosMes']:.1f}")
            k2.metric("Score promedio", f"{resumen_u['ScorePromedio']:.1f}")
            k3.metric("Tareas mes", int(resumen_u["Tareas"]))
            k4.metric("Posición mes", f"#{int(resumen_u['PosicionMes'])}")

            detalle_t = tareas_u.copy()
            detalle_t["Fecha"] = detalle_t["Fecha"].dt.strftime("%d/%m/%Y")
            detalle_t["Minutos"] = detalle_t["MinutosOperativos"].round(1)
            detalle_t["Score"] = detalle_t["ScoreTarea"].round(1)
            detalle_t["Puntos"] = detalle_t["PuntosTarea"].round(2)
            detalle_t["Recorrido"] = detalle_t["RecorridoEqM"].round(1)
            detalle_t["m³"] = detalle_t["M3"].round(3)
            detalle_t["Kg"] = detalle_t["Kg"].round(1)
            detalle_t = detalle_t[[
                "Fecha", "TareaId", "Unidades", "Lineas", "SKUs",
                "Minutos", "m³", "Kg", "Recorrido", "Score", "Puntos",
            ]].rename(columns={"Lineas": "Líneas"})
            st.dataframe(detalle_t, hide_index=True, width="stretch", height=390)

            # Desglose visual de la tarea seleccionada.
            tarea_opts = tareas_u["TareaId"].astype(str).tolist()
            tarea_sel = st.selectbox(
                "Ver composición de una tarea",
                tarea_opts,
                key="est_score_tarea_v2",
            )
            ft = tareas_u.loc[tareas_u["TareaId"].astype(str).eq(str(tarea_sel))].iloc[0]
            desglose_t = pd.DataFrame({
                "Componente": ["Unidades/h", "Tareas/h", "Líneas/h", "Volumen/h", "Kg/h", "Recorrido/h"],
                "Puntos": [ft["PtsUnid"], ft["PtsTareas"], ft["PtsLineas"], ft["PtsM3"], ft["PtsKg"], ft["PtsRecorrido"]],
            })
            desglose_t["Puntos"] = desglose_t["Puntos"].round(1)
            d1, d2 = st.columns([.8, 1.7], vertical_alignment="top")
            with d1:
                st.metric("Score tarea", f"{ft['ScoreTarea']:.1f}")
                st.metric("Puntos tarea", f"{ft['PuntosTarea']:.2f}")
                st.metric("Minutos operativos", f"{ft['MinutosOperativos']:.1f}")
            with d2:
                fig = px.bar(
                    desglose_t, x="Puntos", y="Componente", orientation="h",
                    text="Puntos", title=f"Composición · Tarea {tarea_sel}",
                )
                fig.update_xaxes(range=[0, 120])
                fig = aplicar_formato_visual_plotly(fig, altura=330)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        st.caption(
            "Los puntos se generan únicamente con tareas cerradas/consolidadas del Analítico. "
            "Una tarea abierta sigue visible en Picking, pero entra al campeonato al cerrarse. "
            "Puntos tarea = Score tarea / 10, por lo que cada tarea puede aportar hasta 12 puntos."
        )


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
