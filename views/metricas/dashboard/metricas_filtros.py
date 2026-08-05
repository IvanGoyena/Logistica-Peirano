from __future__ import annotations

import pandas as pd
import streamlit as st

from models.metricas.metricas_dashboard import aplicar_filtros, metricas_periodo


def render(contexto: dict) -> dict:
    tareas = contexto["df_tareas"]
    detalle = contexto["df_detalle"]
    fecha_minima = pd.to_datetime(tareas["Fecha"], errors="coerce").min()
    fecha_maxima = pd.to_datetime(tareas["Fecha"], errors="coerce").max()

    st.markdown("### 🔎 Filtros")
    with st.container(border=True):
        f1, f2, f3, f4, f5 = st.columns([1.30, 1.10, 1.15, 1.10, 1.10])
        rango = f1.date_input(
            "Período",
            value=(fecha_minima.date(), fecha_maxima.date()),
            min_value=fecha_minima.date(),
            max_value=fecha_maxima.date(),
            key="metricas_periodo",
        )
        familias = f2.multiselect(
            "Familia",
            sorted(tareas["FamiliaPrincipal"].fillna("").astype(str).loc[lambda s: s.str.strip().ne("")].unique()),
            placeholder="Todas",
            key="metricas_familias",
        )
        sectores = f3.multiselect(
            "Sectorización",
            sorted(tareas["SectorizacionPrincipal"].fillna("").astype(str).loc[lambda s: s.str.strip().ne("")].unique()),
            placeholder="Todas",
            key="metricas_sectorizaciones",
        )
        usuarios = f4.multiselect(
            "Usuario",
            sorted(tareas["Usuario"].fillna("").astype(str).loc[lambda s: s.str.strip().ne("")].unique()),
            placeholder="Todos",
            key="metricas_usuarios",
        )
        tipos = f5.multiselect(
            "Tipo",
            sorted(tareas["Tipo"].fillna("").astype(str).loc[lambda s: s.str.strip().ne("")].unique()),
            placeholder="Todos",
            key="metricas_tipos",
        )

    if len(rango) == 2:
        desde, hasta = rango
    else:
        desde, hasta = fecha_minima.date(), fecha_maxima.date()

    procesos = sorted(tareas["Proceso"].dropna().astype(str).unique().tolist())
    tareas_filtradas, detalle_filtrado = aplicar_filtros(
        tareas, detalle, desde, hasta, procesos, familias, sectores, usuarios, tipos
    )
    if tareas_filtradas.empty:
        st.warning("No existen datos para la combinación de filtros seleccionada.")
        st.stop()

    dias = (pd.Timestamp(hasta) - pd.Timestamp(desde)).days + 1
    anterior_hasta = pd.Timestamp(desde) - pd.Timedelta(days=1)
    anterior_desde = anterior_hasta - pd.Timedelta(days=dias - 1)
    tareas_anteriores, _ = aplicar_filtros(
        tareas, detalle, anterior_desde.date(), anterior_hasta.date(),
        procesos, familias, sectores, usuarios, tipos
    )
    tareas_evolucion, detalle_evolucion = aplicar_filtros(
        tareas, detalle, fecha_minima.date(), fecha_maxima.date(),
        procesos, familias, sectores, usuarios, tipos
    )

    return {
        **contexto,
        "fecha_minima": fecha_minima,
        "fecha_maxima": fecha_maxima,
        "fecha_desde": desde,
        "fecha_hasta": hasta,
        "filtro_familias": familias,
        "filtro_sectorizaciones": sectores,
        "filtro_usuarios": usuarios,
        "filtro_tipos": tipos,
        "tareas_filtradas": tareas_filtradas,
        "detalle_filtrado": detalle_filtrado,
        "tareas_evolucion": tareas_evolucion,
        "detalle_evolucion": detalle_evolucion,
        "actual": metricas_periodo(tareas_filtradas),
        "anterior": metricas_periodo(tareas_anteriores),
    }
