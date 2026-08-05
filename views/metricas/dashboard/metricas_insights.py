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
    tareas_filtradas = contexto["tareas_filtradas"]
    st.subheader(
        "💡 Insights automáticos"
    )

    st.caption(
        "Conclusiones calculadas sobre los datos filtrados. "
        "Esta será la base del futuro analista con IA."
    )

    insights = construir_insights(
        tareas=tareas_filtradas,
        detalle=detalle_filtrado,
        indicadores_actuales=actual,
        indicadores_anteriores=anterior,
    )

    insight_col1, insight_col2 = st.columns(2)

    for indice, insight in enumerate(
        insights
    ):

        with (
            insight_col1
            if indice % 2 == 0
            else insight_col2
        ):

            mostrar_insight(
                insight
            )

    st.markdown(
        "#### Tareas fuera de comportamiento"
    )

    tareas_anomalias = (
        tareas_filtradas[
            [
                "Proceso",
                "TareaId",
                "Fecha",
                "Usuario",
                "FamiliaPrincipal",
                "UnidadesAnalisis",
                "TiempoRealSegundos",
                "SegundosPorUnidad",
                "NivelComplejidad",
                "VolumenTotalM3",
                "ArchivoOrigen",
            ]
        ]
        .copy()
    )

    mediana = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .median()
    )

    q3 = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .quantile(0.75)
    )

    q1 = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .quantile(0.25)
    )

    limite_anomalia = (
        q3
        + 1.5
        * (q3 - q1)
    )

    tareas_anomalias["Motivo"] = np.where(
        tareas_anomalias[
            "SegundosPorUnidad"
        ] > limite_anomalia,
        "Tiempo por unidad fuera de rango",
        "",
    )

    tareas_anomalias = (
        tareas_anomalias[
            tareas_anomalias[
                "Motivo"
            ].ne("")
        ]
        .sort_values(
            "SegundosPorUnidad",
            ascending=False,
        )
        .head(100)
    )

    st.caption(
        f"Mediana: {mediana:.2f} s/unidad · "
        f"Límite estadístico: {limite_anomalia:.2f} s/unidad"
    )

    st.dataframe(
        tareas_anomalias,
        width="stretch",
        hide_index=True,
    )
