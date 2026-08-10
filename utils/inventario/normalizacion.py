from __future__ import annotations

import csv
import io
import re
import unicodedata
from typing import Iterable

import pandas as pd


def normalizar_nombre_columna(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def normalizar_codigo_valor(valor: object) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip().upper()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    return serie.map(normalizar_codigo_valor)


def convertir_numero(serie: pd.Series) -> pd.Series:
    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(" ", "", regex=False)
    )

    tiene_coma = texto.str.contains(",", regex=False)

    texto.loc[tiene_coma] = (
        texto.loc[tiene_coma]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    return pd.to_numeric(
        texto,
        errors="coerce",
    ).fillna(0.0)


def buscar_columna(
    dataframe: pd.DataFrame,
    candidatos: Iterable[str],
    *,
    obligatoria: bool = False,
) -> str | None:
    if dataframe is None:
        if obligatoria:
            raise ValueError("No se recibió un DataFrame.")
        return None

    mapa = {
        normalizar_nombre_columna(columna): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        clave = normalizar_nombre_columna(candidato)

        if clave in mapa:
            return mapa[clave]

    if obligatoria:
        raise ValueError(
            "No se encontró ninguna de estas columnas: "
            + ", ".join(str(valor) for valor in candidatos)
        )

    return None


def primer_texto_no_vacio(serie: pd.Series) -> str:
    for valor in serie:
        texto = str(valor or "").strip()

        if texto and texto.lower() != "nan":
            return texto

    return ""


def expandir_archivo_separado_por_punto_y_coma(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Algunos reportes descargados como XLSX contienen todo el CSV
    separado por punto y coma dentro de una única columna.
    """

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    if len(dataframe.columns) != 1:
        return dataframe.copy()

    nombre_columna = str(dataframe.columns[0])

    if ";" not in nombre_columna:
        return dataframe.copy()

    lineas = [nombre_columna]

    lineas.extend(
        dataframe.iloc[:, 0]
        .fillna("")
        .astype(str)
        .tolist()
    )

    contenido = "\n".join(lineas)

    lector = csv.reader(
        io.StringIO(contenido),
        delimiter=";",
        quotechar='"',
    )

    filas = list(lector)

    if not filas:
        return pd.DataFrame()

    encabezados = [
        str(valor).strip()
        for valor in filas[0]
    ]

    datos = []

    for fila in filas[1:]:
        completa = fila + [""] * (
            len(encabezados) - len(fila)
        )

        datos.append(
            completa[:len(encabezados)]
        )

    return pd.DataFrame(
        datos,
        columns=encabezados,
    )
