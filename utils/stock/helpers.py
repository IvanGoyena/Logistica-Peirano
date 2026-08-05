import pandas as pd
import streamlit as st


def dataframe_a_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def formato_entero(valor: object) -> str:
    return f"{int(float(valor or 0)):,}".replace(",", ".")


def aplicar_busqueda(dataframe: pd.DataFrame, texto: str) -> pd.DataFrame:
    if dataframe is None or dataframe.empty or not texto.strip():
        return dataframe
    buscado = texto.strip().lower()
    mascara = dataframe.astype("string").apply(
        lambda columna: columna.str.lower().str.contains(buscado, na=False, regex=False)
    ).any(axis=1)
    return dataframe.loc[mascara]


def dataframe_para_streamlit(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe is None:
        return pd.DataFrame()
    tabla = dataframe.copy()
    for columna in tabla.columns:
        serie = tabla[columna]
        if (pd.api.types.is_object_dtype(serie) or isinstance(serie.dtype, pd.StringDtype)
                or isinstance(serie.dtype, pd.CategoricalDtype)):
            tabla[columna] = serie.map(lambda valor: "" if pd.isna(valor) else str(valor))
    return tabla
