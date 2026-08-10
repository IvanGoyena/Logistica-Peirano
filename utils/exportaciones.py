from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st


def _serie_numerica_limpia(
    serie: pd.Series,
) -> pd.Series:
    """
    Convierte una serie numérica al formato más limpio posible.

    - 521.0 -> 521
    - -9.0 -> -9
    - 98.4 -> 98.4
    - NaN -> vacío al exportar
    """

    numerica = pd.to_numeric(
        serie,
        errors="coerce",
    )

    valores_validos = numerica.dropna()

    if valores_validos.empty:
        return serie

    son_enteros = np.isclose(
        valores_validos % 1,
        0,
        atol=1e-9,
    ).all()

    if son_enteros:
        return numerica.round(0).astype("Int64")

    return numerica


def preparar_dataframe_exportacion(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara un DataFrame para CSV sin alterar el objeto original.

    Las columnas numéricas enteras se exportan sin `.0`.
    Las columnas con decimales reales mantienen sus decimales.
    """

    salida = dataframe.copy()

    for columna in salida.columns:
        serie = salida[columna]

        if (
            pd.api.types.is_numeric_dtype(serie)
            and not pd.api.types.is_bool_dtype(serie)
        ):
            salida[columna] = _serie_numerica_limpia(
                serie
            )

    return salida


@st.cache_data(
    max_entries=20,
    show_spinner=False,
)
def dataframe_a_csv_limpio(
    dataframe: pd.DataFrame,
    *,
    separador: str = ";",
) -> bytes:
    """
    Genera un CSV compatible con Excel en español.

    - separador `;`;
    - UTF-8 con BOM;
    - enteros sin `.0`;
    - sin separadores de miles;
    - decimales reales conservados.
    """

    salida = preparar_dataframe_exportacion(
        dataframe
    )

    return salida.to_csv(
        index=False,
        sep=separador,
        encoding="utf-8-sig",
        na_rep="",
        float_format="%.10g",
    ).encode("utf-8-sig")
