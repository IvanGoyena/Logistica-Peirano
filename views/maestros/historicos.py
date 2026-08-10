from __future__ import annotations

import streamlit as st

from utils.maestros.descargas import (
    dataframe_a_csv,
)
from utils.maestros.historicos import (
    cargar_historicos_maestros,
    limpiar_cache_historicos,
)


def render_historicos() -> None:
    cabecera, accion = st.columns(
        [5, 1],
        vertical_alignment="center",
    )

    with cabecera:
        st.subheader(
            "📈 Históricos de métricas"
        )
        st.caption(
            "Control y Preparación consolidados "
            "desde la nueva estructura de Métricas."
        )

    with accion:
        if st.button(
            "🔄 Actualizar",
            key="actualizar_historicos_maestros",
            width="stretch",
        ):
            limpiar_cache_historicos()
            st.rerun()

    with st.spinner(
        "Cargando históricos..."
    ):
        datos = cargar_historicos_maestros()

    if datos.get("error"):
        st.warning(
            "No se pudieron resolver los lectores "
            "de históricos: "
            + datos["error"]
        )

    configuracion = [
        (
            "control",
            "✅ Histórico Control",
            "Historico_Control_Crudo.csv",
        ),
        (
            "preparacion",
            "📦 Histórico Preparación",
            "Historico_Preparacion_Crudo.csv",
        ),
    ]

    columnas = st.columns(2)

    for columna, (
        clave,
        titulo,
        archivo,
    ) in zip(columnas, configuracion):
        dataframe = datos[clave]

        with columna:
            with st.container(border=True):
                st.markdown(f"### {titulo}")
                st.metric(
                    "Registros",
                    f"{len(dataframe):,}"
                    .replace(",", "."),
                )
                st.download_button(
                    "⬇️ Descargar",
                    data=dataframe_a_csv(
                        dataframe
                    ),
                    file_name=archivo,
                    mime="text/csv",
                    width="stretch",
                    disabled=dataframe.empty,
                )
