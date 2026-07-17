import pandas as pd


# ==========================================================
# NORMALIZACIÓN DE CÓDIGOS
# ==========================================================

def normalizar_codigo(serie):

    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


# ==========================================================
# MAESTRO DE EXPRESOS
# ==========================================================

def construir_tabla_expresos(df_expresos):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_expresos.copy()

    # ------------------------------------------------------
    # VALIDACIÓN DE COLUMNAS
    # ------------------------------------------------------

    columnas_requeridas = [
        "Cod_Expre",
        "Nombre",
        "Direccion",
        "Localidad",
        "Agrupador",
        "Zona Agrupador",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in tabla.columns
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas en Maestro Expresos: "
            f"{columnas_faltantes}"
        )

    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(
        columns={
            "Cod_Expre": "CodigoExpreso",
            "Nombre": "Expreso",
            "Direccion": "DireccionExpreso",
            "Localidad": "LocalidadExpreso",
            "Agrupador": "AgrupadorExpreso",
            "Zona Agrupador": "ZonaAgrupadorExpreso",
        }
    )

    # ------------------------------------------------------
    # NORMALIZAR CLAVE
    # ------------------------------------------------------

    tabla["CodigoExpreso"] = normalizar_codigo(
        tabla["CodigoExpreso"]
    )

    # ------------------------------------------------------
    # LIMPIEZA DE TEXTOS
    # ------------------------------------------------------

    columnas_texto = [
        "Expreso",
        "DireccionExpreso",
        "LocalidadExpreso",
        "AgrupadorExpreso",
        "ZonaAgrupadorExpreso",
    ]

    for columna in columnas_texto:

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # ------------------------------------------------------
    # ELIMINAR REGISTROS SIN CÓDIGO
    # ------------------------------------------------------

    tabla = tabla[
        tabla["CodigoExpreso"] != ""
    ].copy()

    # ------------------------------------------------------
    # EVITAR DUPLICADOS
    # Una fila por código de expreso
    # ------------------------------------------------------

    tabla = (
        tabla
        .sort_values(
            [
                "CodigoExpreso",
                "Expreso"
            ]
        )
        .drop_duplicates(
            subset=["CodigoExpreso"],
            keep="first"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # TABLA SATÉLITE FINAL
    # ------------------------------------------------------

    columnas_finales = [
        "CodigoExpreso",
        "Expreso",
        "DireccionExpreso",
        "LocalidadExpreso",
        "AgrupadorExpreso",
        "ZonaAgrupadorExpreso",
    ]

    tabla = tabla[columnas_finales].copy()

    return tabla