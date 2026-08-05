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
    detalle_filtrado = contexto["detalle_filtrado"]
    producto1, producto2 = st.columns(2)

    with producto1:

        st.markdown(
            "#### Familias por unidades"
        )

        familias = (
            detalle_filtrado
            .assign(
                Familia=lambda tabla: (
                    tabla["FamiliaFinal"]
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
                Unidades=(
                    "UnidadesDetalle",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenLineaM3",
                    "sum",
                ),
                PesoKg=(
                    "PesoLineaKg",
                    "sum",
                ),
            )
            .sort_values(
                "Unidades",
                ascending=False,
            )
        )

        fig_familias = px.bar(
            familias.head(15).sort_values(
                "Unidades"
            ),
            x="Unidades",
            y="Familia",
            orientation="h",
            labels={
                "Familia": "",
                "Unidades": "Unidades",
            },
        )

        fig_familias.update_layout(
            height=450,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        aplicar_formato_visual_plotly(fig_familias)

        st.plotly_chart(
            fig_familias,
            width="stretch",
        )

    with producto2:

        st.markdown(
            "#### Curva ABC por unidades"
        )

        abc = (
            detalle_filtrado
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
            .reset_index(drop=True)
        )

        total_abc = abc[
            "UnidadesDetalle"
        ].sum()

        abc["AcumuladoPct"] = (
            abc["UnidadesDetalle"]
            .cumsum()
            / max(
                total_abc,
                1,
            )
            * 100
        )

        abc["ArticuloPct"] = (
            (
                np.arange(
                    1,
                    len(abc) + 1,
                )
                / max(
                    len(abc),
                    1,
                )
            )
            * 100
        )

        abc["ClaseABC"] = np.select(
            [
                abc["AcumuladoPct"] <= 80,
                abc["AcumuladoPct"] <= 95,
            ],
            [
                "A",
                "B",
            ],
            default="C",
        )

        fig_abc = go.Figure()

        fig_abc.add_trace(
            go.Scatter(
                x=abc["ArticuloPct"],
                y=abc["AcumuladoPct"],
                mode="lines",
                name="% acumulado",
            )
        )

        fig_abc.add_hline(
            y=80,
            line_dash="dash",
        )

        fig_abc.add_hline(
            y=95,
            line_dash="dash",
        )

        fig_abc.update_layout(
            height=450,
            xaxis_title="% de artículos",
            yaxis_title="% acumulado de unidades",
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        aplicar_formato_visual_plotly(fig_abc)

        st.plotly_chart(
            fig_abc,
            width="stretch",
        )

    st.markdown(
        "#### Ranking de artículos"
    )

    ranking_articulos = (
        detalle_filtrado
        .groupby(
            [
                "CodigoArticulo",
                "DescripcionFinal",
                "FamiliaFinal",
            ],
            as_index=False,
        )
        .agg(
            Unidades=("UnidadesDetalle", "sum"),
            VolumenM3=(
                "VolumenLineaM3",
                "sum",
            ),
            PesoKg=(
                "PesoLineaKg",
                "sum",
            ),
            Tareas=("ClaveTarea", "nunique"),
        )
        .sort_values(
            "Unidades",
            ascending=False,
        )
    )

    st.dataframe(
        ranking_articulos,
        width="stretch",
        hide_index=True,
        column_config={
            "VolumenM3": (
                st.column_config.NumberColumn(
                    "Volumen m³",
                    format="%.3f",
                )
            ),
            "PesoKg": (
                st.column_config.NumberColumn(
                    "Peso kg",
                    format="%.2f",
                )
            ),
        },
    )
