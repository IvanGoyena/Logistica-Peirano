from __future__ import annotations

import pandas as pd
import streamlit as st

from models.maestros.catalogo import FuenteMaestro
from utils.maestros.descargas import dataframe_a_csv


UBICACIONES_POR_ORIGEN = {
    "WMS": "Data_WMS",
    "ERP": "Data_ERP",
    "MAESTROS": "Data_Maestros",
}


def mostrar_tarjeta_fuente(
    fuente: FuenteMaestro,
    resultado,
) -> None:
    estado = "🟢" if resultado.disponible else "🟠"

    origen = str(
        getattr(
            fuente,
            "origen",
            "Sin definir",
        )
    ).strip().upper()

    ubicacion = UBICACIONES_POR_ORIGEN.get(
        origen,
        "Sin definir",
    )

    with st.container(border=True):
        st.markdown(
            f"### {fuente.icono} {fuente.titulo}"
        )

        c1, c2 = st.columns(2)

        with c1:
            st.metric(
                "Registros",
                f"{len(resultado.dataframe):,}"
                .replace(",", "."),
            )

        with c2:
            st.metric(
                "Estado",
                f"{estado} "
                + (
                    "Disponible"
                    if resultado.disponible
                    else "Revisar"
                ),
            )

        st.caption(
            "Fuente: "
            f"{resultado.nombre_resuelto or 'No detectada'}"
        )

        st.caption(
            f"Origen: {origen}"
        )

        st.caption(
            f"Ubicación: {ubicacion}"
        )

        st.caption(
            f"Actualización: {resultado.fecha}"
        )

        if resultado.error:
            st.error(
                resultado.error,
                icon="⚠️",
            )

        st.download_button(
            "⬇️ Descargar",
            data=dataframe_a_csv(
                resultado.dataframe
            ),
            file_name=fuente.descarga,
            mime="text/csv",
            key=f"descarga_maestros_{fuente.clave}",
            width="stretch",
            disabled=resultado.dataframe.empty,
        )
