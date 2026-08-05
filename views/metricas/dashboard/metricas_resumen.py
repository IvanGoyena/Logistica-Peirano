from __future__ import annotations

from io import BytesIO

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.estilo_graficos import aplicar_formato_visual_plotly
from models.metricas.metricas_dashboard import construir_insights
from utils.metricas.metricas_helpers import (
    formatear_entero,
    limitar_previsualizacion,
    mostrar_insight,
)

ORDEN_DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]
MESES_CORTOS = {1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic"}

def render(contexto: dict) -> None:
    actual = contexto["actual"]
    anterior = contexto["anterior"]
    detalle_filtrado = contexto["detalle_filtrado"]
    filtro_familias = contexto["filtro_familias"]
    tareas_evolucion = contexto["tareas_evolucion"]
    tareas_filtradas = contexto["tareas_filtradas"]
    fila1_col1, fila1_col2, fila1_col3 = (
        st.columns(
            [
                1.35,
                1,
                1,
            ]
        )
    )

    with fila1_col1:

        st.markdown(
            "#### Evolución mensual"
        )

        metrica_evolucion = st.selectbox(
            "Métrica",
            options=[
                "Unidades",
                "Tareas",
                "Volumen m³",
                "Peso kg",
                "Horas",
            ],
            label_visibility="collapsed",
            key="metrica_evolucion",
        )

        evolucion = (
            tareas_evolucion
            .assign(
                Periodo=lambda tabla: (
                    tabla["Fecha"]
                    .dt.to_period("M")
                    .dt.to_timestamp()
                )
            )
            .groupby(
                [
                    "Periodo",
                    "Proceso",
                ],
                as_index=False,
            )
            .agg(
                Tareas=("ClaveTarea", "nunique"),
                Unidades=(
                    "UnidadesAnalisis",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenTotalM3",
                    "sum",
                ),
                PesoKg=(
                    "PesoTotalKg",
                    "sum",
                ),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
        )

        evolucion["Horas"] = (
            evolucion["Segundos"]
            / 3600
        )

        mapa_metricas = {
            "Unidades": "Unidades",
            "Tareas": "Tareas",
            "Volumen m³": "VolumenM3",
            "Peso kg": "PesoKg",
            "Horas": "Horas",
        }

        columna_metrica = mapa_metricas[
            metrica_evolucion
        ]

        evolucion["Mes"] = (
            evolucion["Periodo"]
            .dt.month
            .map(MESES_CORTOS)
            + " "
            + evolucion["Periodo"]
            .dt.year
            .astype(str)
        )

        fig_evolucion = px.line(
            evolucion,
            x="Mes",
            y=columna_metrica,
            color="Proceso",
            markers=True,
            labels={
                columna_metrica: metrica_evolucion,
                "Mes": "",
                "Proceso": "Proceso",
            },
        )

        fig_evolucion.update_traces(
            line_width=3,
            marker_size=8,
            textposition="top center",
        )

        fig_evolucion.update_layout(
            height=360,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10,
            ),
            legend_title_text="",
            hovermode="x unified",
            xaxis_title="",
            yaxis_title=metrica_evolucion,
        )

        fig_evolucion.update_yaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        aplicar_formato_visual_plotly(fig_evolucion)

        st.plotly_chart(
            fig_evolucion,
            width="stretch",
        )

    with fila1_col2:

        st.markdown(
            "#### Mix de categorías"
        )

        categoria_mix = st.selectbox(
            label="",
            options=["Familia", "Sector"],
            index=1,
            key="categoria_mix",
            label_visibility="collapsed",
        )

        if categoria_mix == "Sector":

            columna_mix = "Sectorizacion"
            valor_sin_categoria = "SIN SECTORIZACIÓN"

        else:

            columna_mix = "FamiliaFinal"
            valor_sin_categoria = "SIN FAMILIA"

        mix_categorias = (
            detalle_filtrado
            .assign(
                CategoriaMix=lambda tabla: (
                    tabla[columna_mix]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        valor_sin_categoria,
                    )
                )
            )
            .groupby(
                "CategoriaMix",
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
        )

        if len(mix_categorias) > 7:

            principales = mix_categorias.head(6)

            otros = pd.DataFrame(
                {
                    "CategoriaMix": ["OTROS"],
                    "UnidadesDetalle": [
                        mix_categorias.iloc[
                            6:
                        ]["UnidadesDetalle"].sum()
                    ],
                }
            )

            mix_categorias = pd.concat(
                [
                    principales,
                    otros,
                ],
                ignore_index=True,
            )

        fig_mix = px.pie(
            mix_categorias,
            names="CategoriaMix",
            values="UnidadesDetalle",
            hole=0.55,
        )

        fig_mix.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Unidades: %{value:,.0f}<br>"
                "Participación: %{percent}"
                "<extra></extra>"
            ),
        )

        total_mix = int(
            pd.to_numeric(
                mix_categorias["UnidadesDetalle"],
                errors="coerce",
            ).fillna(0).sum()
        )

        fig_mix.add_annotation(
            text=(
                f"<b>{formatear_entero(total_mix)}</b>"
                "<br><span style='font-size:12px'>Unidades</span>"
            ),
            x=0.5,
            y=0.5,
            showarrow=False,
            font=dict(
                size=20,
                color="#F8FAFC",
            ),
        )

        fig_mix.update_layout(
            height=360,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            legend_title_text="",
            legend=dict(
                orientation="v",
                x=1.02,
                y=0.5,
            ),
        )

        aplicar_formato_visual_plotly(fig_mix)

        st.plotly_chart(
            fig_mix,
            width="stretch",
        )

    with fila1_col3:

        st.markdown(
            "#### Insights automáticos"
        )

        insights = construir_insights(
            tareas=tareas_filtradas,
            detalle=detalle_filtrado,
            indicadores_actuales=actual,
            indicadores_anteriores=anterior,
        )

        for insight in insights[:4]:

            mostrar_insight(
                insight
            )

    fila2_col1, fila2_col2, fila2_col3 = (
        st.columns(
            [
                1.2,
                1,
                1,
            ]
        )
    )

    with fila2_col1:

        # Sin filtro de familia, el ranking principal
        # muestra únicamente artículos de Grifería.
        if filtro_familias:

            detalle_top = detalle_filtrado.copy()

            titulo_top = (
                "Top 15 artículos — "
                + ", ".join(filtro_familias)
            )

        else:

            detalle_top = detalle_filtrado[
                detalle_filtrado["FamiliaFinal"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("GRIFERIA")
            ].copy()

            titulo_top = "Top 15 artículos — Grifería"

        st.markdown(
            f"#### {titulo_top}"
        )

        top_articulos = (
            detalle_top
            .groupby(
                [
                    "CodigoArticulo",
                    "DescripcionFinal",
                ],
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
            .head(15)
        )

        top_articulos["Articulo"] = (
            top_articulos["CodigoArticulo"]
            + " · "
            + top_articulos[
                "DescripcionFinal"
            ].str.slice(
                0,
                32,
            )
        )

        fig_top = px.bar(
            top_articulos.sort_values(
                "UnidadesDetalle"
            ),
            x="UnidadesDetalle",
            y="Articulo",
            orientation="h",
            labels={
                "UnidadesDetalle": "Unidades",
                "Articulo": "",
            },
        )

        fig_top.update_traces(
            texttemplate="%{x:,.0f}",
            textposition="outside",
            cliponaxis=False,
        )

        fig_top.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=35,
                t=15,
                b=10,
            ),
            showlegend=False,
            xaxis_title="Unidades",
            yaxis_title="",
        )

        fig_top.update_xaxes(
            gridcolor="rgba(128,128,128,0.18)",
        )

        aplicar_formato_visual_plotly(fig_top)

        st.plotly_chart(
            fig_top,
            width="stretch",
        )

    with fila2_col2:

        st.markdown(
            "#### Carga operativa por día"
        )

        metrica_dia = st.selectbox(
            "Métrica",
            options=[
                "Promedio de unidades",
                "Promedio de horas",
                "Unidades/hora",
            ],
            label_visibility="collapsed",
            key="metrica_carga_dia",
        )

        base_dia = tareas_filtradas.copy()

        base_dia["FechaDia"] = pd.to_datetime(
            base_dia["Fecha"],
            errors="coerce",
        ).dt.normalize()

        resumen_fecha = (
            base_dia
            .groupby(
                [
                    "FechaDia",
                    "DiaSemana",
                ],
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=("TiempoRealSegundos", "sum"),
            )
        )

        resumen_fecha["Horas"] = (
            resumen_fecha["Segundos"]
            / 3600
        )

        resumen_fecha["UnidadesHora"] = (
            resumen_fecha["Unidades"]
            / resumen_fecha["Horas"].replace(
                0,
                np.nan,
            )
        )

        carga_dia = (
            resumen_fecha
            .groupby(
                "DiaSemana",
                as_index=False,
            )
            .agg(
                PromedioUnidades=("Unidades", "mean"),
                PromedioHoras=("Horas", "mean"),
                UnidadesHora=("UnidadesHora", "mean"),
            )
        )

        carga_dia["DiaSemana"] = pd.Categorical(
            carga_dia["DiaSemana"],
            categories=ORDEN_DIAS,
            ordered=True,
        )

        carga_dia = carga_dia.sort_values(
            "DiaSemana"
        )

        mapa_dia = {
            "Promedio de unidades": (
                "PromedioUnidades",
                "Unidades promedio",
            ),
            "Promedio de horas": (
                "PromedioHoras",
                "Horas promedio",
            ),
            "Unidades/hora": (
                "UnidadesHora",
                "Unidades/hora",
            ),
        }

        columna_dia, etiqueta_dia = mapa_dia[
            metrica_dia
        ]

        fig_carga = px.bar(
            carga_dia,
            x="DiaSemana",
            y=columna_dia,
            text_auto=".1f",
            labels={
                "DiaSemana": "",
                columna_dia: etiqueta_dia,
            },
        )

        fig_carga.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig_carga.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
            yaxis_title=etiqueta_dia,
            xaxis_title="",
        )

        fig_carga.update_yaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        aplicar_formato_visual_plotly(fig_carga)

        st.plotly_chart(
            fig_carga,
            width="stretch",
        )


    with fila2_col3:

        st.markdown(
            "#### Productividad por familia"
        )

        productividad_familia = (
            tareas_filtradas
            .assign(
                Familia=lambda tabla: (
                    tabla["FamiliaPrincipal"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        "SIN FAMILIA",
                    )
                )
            )
            .groupby(
                "Familia",
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=("TiempoRealSegundos", "sum"),
                Tareas=("ClaveTarea", "nunique"),
            )
        )

        productividad_familia["Horas"] = (
            productividad_familia["Segundos"]
            / 3600
        )

        productividad_familia["UnidadesHora"] = (
            productividad_familia["Unidades"]
            / productividad_familia["Horas"].replace(
                0,
                np.nan,
            )
        )

        productividad_familia = (
            productividad_familia
            .dropna(
                subset=["UnidadesHora"]
            )
            .sort_values(
                "UnidadesHora",
                ascending=False,
            )
            .head(10)
        )

        fig_prod_familia = px.bar(
            productividad_familia.sort_values(
                "UnidadesHora"
            ),
            x="UnidadesHora",
            y="Familia",
            orientation="h",
            text_auto=".1f",
            labels={
                "UnidadesHora": "Unidades/hora",
                "Familia": "",
            },
        )

        fig_prod_familia.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig_prod_familia.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=35,
                t=15,
                b=10,
            ),
            showlegend=False,
            xaxis_title="Unidades/hora",
            yaxis_title="",
        )

        fig_prod_familia.update_xaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        aplicar_formato_visual_plotly(fig_prod_familia)

        st.plotly_chart(
            fig_prod_familia,
            width="stretch",
        )
