from __future__ import annotations

import pandas as pd
import streamlit as st

from config import CARPETA_WMS
from models.metricas.metricas import (
    leer_historico_controles,
    leer_historico_preparaciones,
    limpiar_cache_mes_actual_metricas,
)


@st.cache_data(
    ttl=600,
    show_spinner=False,
)
def cargar_historicos_maestros() -> dict[str, pd.DataFrame]:
    """
    Carga los históricos crudos de Control y Preparación desde Data_WMS.
    """

    try:
        control = leer_historico_controles(
            CARPETA_WMS
        )

        preparacion = leer_historico_preparaciones(
            CARPETA_WMS
        )

        return {
            "control": (
                control
                if control is not None
                else pd.DataFrame()
            ),
            "preparacion": (
                preparacion
                if preparacion is not None
                else pd.DataFrame()
            ),
            "error": "",
        }

    except Exception as error:
        return {
            "control": pd.DataFrame(),
            "preparacion": pd.DataFrame(),
            "error": (
                f"{type(error).__name__}: {error}"
            ),
        }


def limpiar_cache_historicos() -> None:
    """
    Actualiza la vista Históricos de Maestros.

    - limpia la caché propia de esta pantalla;
    - invalida la lectura del mes actual de Métricas;
    - conserva la caché persistente de meses cerrados.
    """

    cargar_historicos_maestros.clear()
    limpiar_cache_mes_actual_metricas()
