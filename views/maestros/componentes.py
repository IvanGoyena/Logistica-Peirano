from __future__ import annotations

import pandas as pd
import streamlit as st

from models.maestros.catalogo import FuenteMaestro
from utils.maestros.descargas import dataframe_a_csv


def mostrar_tarjeta_fuente(
    fuente: FuenteMaestro,
    resultado,
) -> None:
    estado = "🟢" if resultado.disponible else "🟠"

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
            f"Fuente: "
            f"{resultado.nombre_resuelto or 'No detectada'}"
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
