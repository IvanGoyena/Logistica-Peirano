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
# MAESTRO DE VOLUMETRÍA
# ==========================================================

def construir_tabla_volumetria(df_volumetria):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_volumetria.copy()

    # ------------------------------------------------------
    # NORMALIZAR ENCABEZADOS
    # ------------------------------------------------------

    tabla.columns = (
        tabla.columns
        .astype(str)
        .str.strip()
    )

    # ------------------------------------------------------
    # VALIDACIÓN DE COLUMNAS
    # ------------------------------------------------------

    columnas_requeridas = [
        "Codigo",
        "Descripcion",
        "Alto",
        "Ancho",
        "Profundo",
        "UnidadVenta",
        "Kg",
        "Familia",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in tabla.columns
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas en Maestro Volumetría: "
            f"{columnas_faltantes}"
        )

    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(
        columns={
            "Codigo": "CodigoArticulo",
            "Descripcion": "ArticuloDescripcion",
            "Alto": "AltoMM",
            "Ancho": "AnchoMM",
            "Profundo": "ProfundoMM",
            "Kg": "PesoKg",
        }
    )

    # ------------------------------------------------------
    # NORMALIZAR CÓDIGO
    # ------------------------------------------------------

    tabla["CodigoArticulo"] = normalizar_codigo(
        tabla["CodigoArticulo"]
    )

    # ------------------------------------------------------
    # LIMPIEZA DE TEXTOS
    # ------------------------------------------------------

    columnas_texto = [
        "ArticuloDescripcion",
        "Familia",
    ]

    for columna in columnas_texto:

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # ------------------------------------------------------
    # CONVERSIÓN DE MEDIDAS
    # ------------------------------------------------------

    columnas_medidas = [
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
    ]

    for columna in columnas_medidas:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce"
            )
            .fillna(0)
        )

    # ------------------------------------------------------
    # PESO
    # ------------------------------------------------------

    tabla["PesoKg"] = (
        pd.to_numeric(
            tabla["PesoKg"],
            errors="coerce"
        )
        .fillna(0)
    )

    # ------------------------------------------------------
    # UNIDAD DE VENTA
    # ------------------------------------------------------

    tabla["UnidadVenta"] = (
        pd.to_numeric(
            tabla["UnidadVenta"],
            errors="coerce"
        )
        .fillna(1)
    )

    # Evitar unidades de venta iguales a cero
    tabla.loc[
        tabla["UnidadVenta"] <= 0,
        "UnidadVenta"
    ] = 1

    tabla["UnidadVenta"] = (
        tabla["UnidadVenta"]
        .astype(int)
    )

    # ------------------------------------------------------
    # CÁLCULO DE VOLUMEN EN M³
    # ------------------------------------------------------

    tabla["VolumenM3"] = (
        tabla["AltoMM"]
        * tabla["AnchoMM"]
        * tabla["ProfundoMM"]
    ) / 1_000_000_000

    # ------------------------------------------------------
    # VOLUMEN POR UNIDAD DE VENTA
    # ------------------------------------------------------

    tabla["VolumenUnidadVentaM3"] = (
        tabla["VolumenM3"]
        * tabla["UnidadVenta"]
    )

    # ------------------------------------------------------
    # REDONDEO
    # ------------------------------------------------------

    tabla["VolumenM3"] = (
        tabla["VolumenM3"]
        .round(6)
    )

    tabla["VolumenUnidadVentaM3"] = (
        tabla["VolumenUnidadVentaM3"]
        .round(6)
    )

    tabla["PesoKg"] = (
        tabla["PesoKg"]
        .round(3)
    )

    # ------------------------------------------------------
    # ELIMINAR REGISTROS SIN CÓDIGO
    # ------------------------------------------------------

    tabla = tabla[
        tabla["CodigoArticulo"] != ""
    ].copy()

    # ------------------------------------------------------
    # EVITAR DUPLICADOS
    # Una fila por artículo
    # ------------------------------------------------------

    tabla = (
        tabla
        .sort_values(
            [
                "CodigoArticulo",
                "ArticuloDescripcion"
            ]
        )
        .drop_duplicates(
            subset=["CodigoArticulo"],
            keep="first"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # SELECCIÓN FINAL DE COLUMNAS
    # ------------------------------------------------------

    columnas_finales = [
        "CodigoArticulo",
        "ArticuloDescripcion",
        "Familia",
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
        "PesoKg",
        "UnidadVenta",
        "VolumenM3",
        "VolumenUnidadVentaM3",
    ]

    tabla = tabla[columnas_finales].copy()

    return tabla