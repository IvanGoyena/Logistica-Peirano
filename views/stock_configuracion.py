import pandas as pd
import streamlit as st

from utils.stock_helpers import dataframe_a_csv, formato_entero, aplicar_busqueda, dataframe_para_streamlit


def render(contexto: dict) -> None:
    tabla_articulos = contexto["tabla_articulos"]
    tabla_volumetria = contexto["tabla_volumetria"]
    tabla_max_min = contexto["tabla_max_min"]
    st.subheader("⚙️ Configuración y producto")
    st.caption(
        "Información maestra para enriquecer cada código: descripción, familia, "
        "sectorización, origen, volumetría y configuración de reposición."
    )

    cfg1, cfg2, cfg3 = st.columns(3)
    cfg1.metric("Artículos", formato_entero(len(tabla_articulos)))
    cfg2.metric("Con volumetría", formato_entero(len(tabla_volumetria)))
    cfg3.metric("Con Max & Min", formato_entero(len(tabla_max_min)))

    vista_configuracion = st.radio(
        "Información a visualizar",
        options=[
            "Configuración Max & Min",
            "Maestro de Artículos",
            "Maestro de Volumetría",
        ],
        horizontal=True,
        key="vista_configuracion_stock",
    )

    if vista_configuracion == "Configuración Max & Min":
        dataframe_config = tabla_max_min
        clave_config = "max_min_configuracion"
    elif vista_configuracion == "Maestro de Artículos":
        dataframe_config = tabla_articulos
        clave_config = "articulos_configuracion"
    else:
        dataframe_config = tabla_volumetria
        clave_config = "volumetria_configuracion"

    busqueda_config = st.text_input(
        "Buscar dentro de la información seleccionada",
        key=f"buscar_{clave_config}",
        placeholder="Código, descripción, familia, ubicación...",
    )
    configuracion_vista = aplicar_busqueda(dataframe_config, busqueda_config)

    st.download_button(
        "⬇️ Descargar vista",
        data=dataframe_a_csv(configuracion_vista),
        file_name=f"{clave_config}.csv",
        mime="text/csv",
        key=f"descargar_{clave_config}",
    )

    st.dataframe(
        dataframe_para_streamlit(configuracion_vista),
        hide_index=True,
        width="stretch",
        height=540,
    )

