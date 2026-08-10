from __future__ import annotations

import pandas as pd
import streamlit as st

from config import CARPETA_DATOS


@st.cache_data(
    ttl=600,
    show_spinner=False,
)
def cargar_historicos_maestros() -> dict[str, pd.DataFrame]:
    """
    Mantiene compatibilidad con la nueva carpeta de Métricas
    y con el wrapper temporal de versiones anteriores.
    """

    errores = []

    for modulo in (
        "models.metricas.base_historica_metricas",
        "models.base_historica_metricas",
    ):
        try:
            componente = __import__(
                modulo,
                fromlist=[
                    "leer_historico_controles",
                    "leer_historico_preparaciones",
                ],
            )

            leer_control = getattr(
                componente,
                "leer_historico_controles",
            )
            leer_preparacion = getattr(
                componente,
                "leer_historico_preparaciones",
            )

            return {
                "control": leer_control(
                    CARPETA_DATOS
                ),
                "preparacion": leer_preparacion(
                    CARPETA_DATOS
                ),
                "error": "",
            }

        except Exception as error:
            errores.append(
                f"{modulo}: {type(error).__name__}"
            )

    return {
        "control": pd.DataFrame(),
        "preparacion": pd.DataFrame(),
        "error": " · ".join(errores),
    }


def limpiar_cache_historicos() -> None:
    cargar_historicos_maestros.clear()
