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
# MAESTRO DE CLIENTES
# ==========================================================

def construir_tabla_clientes(df_clientes):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_clientes.copy()

    # ------------------------------------------------------
    # NORMALIZAR NOMBRES DE COLUMNAS
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
    "codigo_logistico",
    "Codigo_Cliente",
    "Cliente",
    "tipo",
    "Entrega",
    "Preparacion2",
]

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in tabla.columns
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas en Maestro Clientes: "
            f"{columnas_faltantes}"
        )

    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(
    columns={
        "codigo_logistico": "CodigoSucursal",
        "Codigo_Cliente": "ClienteCodigo",
        "Cliente": "ClienteDescripcion",
        "tipo": "TipoCliente",
        "Entrega": "FrecuenciaEntrega",
        "Preparacion2": "FrecuenciaPreparacion",
    }
    )

    # ------------------------------------------------------
    # NORMALIZAR CLAVES
    # ------------------------------------------------------

    tabla["CodigoSucursal"] = normalizar_codigo(
        tabla["CodigoSucursal"]
    )

    tabla["ClienteCodigo"] = normalizar_codigo(
        tabla["ClienteCodigo"]
    )

    # ------------------------------------------------------
    # LIMPIEZA DE TEXTOS
    # ------------------------------------------------------

    columnas_texto = [
        "ClienteDescripcion",
        "TipoCliente",
        "FrecuenciaEntrega",
        "FrecuenciaPreparacion",
    ]

    for columna in columnas_texto:

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # ------------------------------------------------------
    # NORMALIZAR CATEGORÍAS
    # ------------------------------------------------------

    tabla["TipoCliente"] = (
        tabla["TipoCliente"]
        .str.upper()
    )

    tabla["FrecuenciaEntrega"] = (
        tabla["FrecuenciaEntrega"]
        .str.upper()
    )

    tabla["FrecuenciaPreparacion"] = (
        tabla["FrecuenciaPreparacion"]
        .str.upper()
    )

    # ------------------------------------------------------
    # ELIMINAR REGISTROS SIN CLAVE
    # ------------------------------------------------------

    tabla = tabla[
        tabla["CodigoSucursal"] != ""
    ].copy()

    # ------------------------------------------------------
    # EVITAR DUPLICADOS
    # Una fila por código logístico / sucursal
    # ------------------------------------------------------

    tabla = (
        tabla
        .sort_values(
            [
                "CodigoSucursal",
                "ClienteDescripcion"
            ]
        )
        .drop_duplicates(
            subset=["CodigoSucursal"],
            keep="first"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # TABLA SATÉLITE FINAL
    # ------------------------------------------------------

    columnas_finales = [
        "CodigoSucursal",
        "ClienteCodigo",
        "ClienteDescripcion",
        "TipoCliente",
        "FrecuenciaEntrega",
        "FrecuenciaPreparacion",
    ]

    tabla = tabla[columnas_finales].copy()

    return tabla