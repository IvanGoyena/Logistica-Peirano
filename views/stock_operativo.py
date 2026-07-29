import math
import pandas as pd
import altair as alt
import streamlit as st

from config import CARPETA_DATOS
from utils.confirmaciones_oc import guardar_confirmaciones_oc, eliminar_confirmaciones_oc
from utils.stock_helpers import dataframe_a_csv, formato_entero, aplicar_busqueda, dataframe_para_streamlit


def render(contexto: dict) -> None:
    tabla_disponible = contexto["tabla_disponible"]
    articulos_stock = contexto["articulos_stock"]
    tabla_calidad = contexto["tabla_calidad"]
    tabla_stock_recepcion = contexto["tabla_stock_recepcion"]
    st.subheader("📦 Situación operativa")
    st.caption(
        "Lectura del stock según su disponibilidad y estadio dentro de DIGIP: "
        "disponible, reservado, pedidos, preparación, preparado, despacho, "
        "bloqueado y otros estados."
    )

    op1, op2, op3, op4 = st.columns(4)
    op1.metric("Registros de disponibilidad", formato_entero(len(tabla_disponible)))
    op2.metric("Artículos físicos", formato_entero(articulos_stock))
    op3.metric("Registros en Calidad", formato_entero(len(tabla_calidad)))
    op4.metric("Registros en Recepción", formato_entero(len(tabla_stock_recepcion)))

    st.info(
        "Esta pestaña ya concentra las fuentes operativas. En el próximo paso "
        "vamos a normalizar los estados reales de Disponible DIGIP y construir "
        "una fila única por artículo."
    )

    st.markdown("#### Disponible DIGIP")
    busqueda_disponible = st.text_input(
        "Buscar en disponibilidad",
        key="buscar_situacion_operativa",
        placeholder="Código, descripción o estado...",
    )
    disponible_vista = aplicar_busqueda(tabla_disponible, busqueda_disponible)

    st.dataframe(
        dataframe_para_streamlit(disponible_vista),
        hide_index=True,
        width="stretch",
        height=470,
    )

    with st.expander("🧪 Stock de Calidad / Laboratorio"):
        st.dataframe(
            dataframe_para_streamlit(tabla_calidad),
            hide_index=True,
            width="stretch",
            height=420,
        )

