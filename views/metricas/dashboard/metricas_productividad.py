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
    tareas_filtradas = contexto["tareas_filtradas"]
    prod1, prod2 = st.columns(2)

    with prod1:

        st.markdown(
            "#### Productividad por proceso"
        )

        productividad_proceso = (
            tareas_filtradas
            .groupby(
                "Proceso",
                as_index=False,
            )
            .agg(
                Unidades=(
                    "UnidadesAnalisis",
                    "sum",
                ),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenTotalM3",
                    "sum",
                ),
            )
        )

        productividad_proceso[
            "UnidadesHora"
        ] = (
            productividad_proceso[
                "Unidades"
            ]
            / (
                productividad_proceso[
                    "Segundos"
                ]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        productividad_proceso[
            "M3Hora"
        ] = (
            productividad_proceso[
                "VolumenM3"
            ]
            / (
                productividad_proceso[
                    "Segundos"
                ]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        fig_prod_proceso = px.bar(
            productividad_proceso,
            x="Proceso",
            y="UnidadesHora",
            text_auto=".1f",
            labels={
                "Proceso": "",
                "UnidadesHora": "Unidades/hora",
            },
        )

        fig_prod_proceso.update_layout(
            height=340,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        aplicar_formato_visual_plotly(fig_prod_proceso)

        st.plotly_chart(
            fig_prod_proceso,
            width="stretch",
        )

    with prod2:

        st.markdown(
            "#### Tiempo promedio por proceso"
        )

        tiempo_proceso = (
            tareas_filtradas
            .groupby(
                "Proceso",
                as_index=False,
            )
            .agg(
                TiempoPromedioSegundos=(
                    "TiempoRealSegundos",
                    "mean",
                ),
            )
        )

        tiempo_proceso[
            "TiempoPromedioMinutos"
        ] = (
            tiempo_proceso[
                "TiempoPromedioSegundos"
            ]
            / 60
        )

        fig_tiempo = px.bar(
            tiempo_proceso,
            x="Proceso",
            y="TiempoPromedioMinutos",
            text_auto=".1f",
            labels={
                "Proceso": "",
                "TiempoPromedioMinutos": (
                    "Minutos promedio"
                ),
            },
        )

        fig_tiempo.update_layout(
            height=340,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        aplicar_formato_visual_plotly(fig_tiempo)

        st.plotly_chart(
            fig_tiempo,
            width="stretch",
        )

    st.markdown(
        "#### Ranking de productividad por usuario"
    )

    ranking_usuario = (
        tareas_filtradas
        .groupby(
            [
                "Proceso",
                "Usuario",
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
            Segundos=(
                "TiempoRealSegundos",
                "sum",
            ),
        )
    )

    ranking_usuario["Horas"] = (
        ranking_usuario["Segundos"]
        / 3600
    )

    ranking_usuario["UnidadesHora"] = (
        ranking_usuario["Unidades"]
        / ranking_usuario["Horas"].replace(
            0,
            np.nan,
        )
    )

    ranking_usuario["M3Hora"] = (
        ranking_usuario["VolumenM3"]
        / ranking_usuario["Horas"].replace(
            0,
            np.nan,
        )
    )

    ranking_usuario = ranking_usuario.sort_values(
        "UnidadesHora",
        ascending=False,
    )

    st.dataframe(
        ranking_usuario,
        width="stretch",
        hide_index=True,
        column_config={
            "Horas": (
                st.column_config.NumberColumn(
                    "Horas",
                    format="%.2f",
                )
            ),
            "UnidadesHora": (
                st.column_config.ProgressColumn(
                    "Unidades/hora",
                    min_value=0,
                    max_value=max(
                        float(
                            ranking_usuario[
                                "UnidadesHora"
                            ].max()
                        ),
                        1,
                    ),
                    format="%.1f",
                )
            ),
            "M3Hora": (
                st.column_config.NumberColumn(
                    "m³/hora",
                    format="%.3f",
                )
            ),
        },
    )

    st.markdown(
        "#### Productividad por hora del día"
    )

    productividad_hora = (
        tareas_filtradas
        .assign(
            Hora=lambda tabla: (
                pd.to_datetime(
                    tabla["HoraInicio"],
                    format="%H:%M:%S",
                    errors="coerce",
                ).dt.hour
            )
        )
        .dropna(
            subset=["Hora"]
        )
        .groupby(
            [
                "Hora",
                "Proceso",
            ],
            as_index=False,
        )
        .agg(
            Unidades=(
                "UnidadesAnalisis",
                "sum",
            ),
            Segundos=(
                "TiempoRealSegundos",
                "sum",
            ),
        )
    )

    productividad_hora[
        "UnidadesHora"
    ] = (
        productividad_hora[
            "Unidades"
        ]
        / (
            productividad_hora[
                "Segundos"
            ]
            / 3600
        ).replace(
            0,
            np.nan,
        )
    )

    fig_hora = px.line(
        productividad_hora,
        x="Hora",
        y="UnidadesHora",
        color="Proceso",
        markers=True,
        labels={
            "Hora": "Hora del día",
            "UnidadesHora": "Unidades/hora",
            "Proceso": "Proceso",
        },
    )

    fig_hora.update_layout(
        height=380,
        margin=dict(
            l=10,
            r=10,
            t=15,
            b=10,
        ),
        legend_title_text="",
    )

    aplicar_formato_visual_plotly(fig_hora)

    st.plotly_chart(
        fig_hora,
        width="stretch",
    )
