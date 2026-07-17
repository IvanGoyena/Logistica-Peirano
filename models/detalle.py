import pandas as pd


from models.volumetria import (
    construir_tabla_volumetria
)


# ==========================================================
# TABLA DETALLE PEDIDOS
# ==========================================================

def construir_tabla_detalle(

    df_detalle,
    df_articulos,
    df_volumetria

):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_detalle.copy()


    # ------------------------------------------------------
    # MAESTRO VOLUMETRÍA
    # ------------------------------------------------------

    volumetria = construir_tabla_volumetria(
        df_volumetria
    )


    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(

        columns={

            "nro_com": "Pedido",

            "cod_art": "ArticuloCodigo",

            "can_art": "Cantidad"

        }

    )

    # ------------------------------------------------------
    # TIPOS DE DATOS
    # ------------------------------------------------------

    tabla["Pedido"] = (

        tabla["Pedido"]

        .fillna("")

        .astype(str)

    )


    tabla["ArticuloCodigo"] = (
        tabla["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )

    tabla["Cantidad"] = (

        pd.to_numeric(

            tabla["Cantidad"],

            errors="coerce"

        )

        .fillna(0)

        .astype(int)

    )

    # ------------------------------------------------------
    # MAESTRO ARTICULOS
    # ------------------------------------------------------

    articulos = df_articulos.copy()

    # ------------------------------------------------------
    # COLUMNAS REQUERIDAS
    # ------------------------------------------------------

    columnas_requeridas = [

        "COD_ART",
        "DESCRIP",
        "Rubro",
        "Marca",
        "Terminacion",
        "Tipo",
        "Origen",
        "Gama",
        "Familia",
        "Sector",
        "Familia_2",
        "Sectorizacion"

    ]

    faltantes = [

        c

        for c in columnas_requeridas

        if c not in articulos.columns

    ]

    if len(faltantes) > 0:

        raise ValueError(

            f"Faltan columnas en Maestro Articulos: {faltantes}"

        )

    # ------------------------------------------------------
    # TIPOS DE DATOS
    # ------------------------------------------------------

    articulos["COD_ART"] = (
        articulos["COD_ART"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )

    # ------------------------------------------------------
    # MERGE
    # ------------------------------------------------------

    tabla = tabla.merge(

        articulos,

        left_on="ArticuloCodigo",

        right_on="COD_ART",

        how="left"

    )

    volumetria["CodigoArticulo"] = (
        volumetria["CodigoArticulo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(

        columns={

            "DESCRIP": "ArticuloDescripcion",

            "Familia_2": "Familia2"

        }

    )


    # ------------------------------------------------------
    # PREPARAR MAESTRO VOLUMETRÍA
    # ------------------------------------------------------

    volumetria_merge = (
        volumetria[
            [
                "CodigoArticulo",
                "AltoMM",
                "AnchoMM",
                "ProfundoMM",
                "PesoKg",
                "VolumenM3",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoArticulo"],
            keep="first"
        )
        .copy()
    )

    # ------------------------------------------------------
    # MERGE CON MAESTRO VOLUMETRÍA
    # ------------------------------------------------------

    tabla = tabla.merge(
        volumetria_merge,
        left_on="ArticuloCodigo",
        right_on="CodigoArticulo",
        how="left",
        validate="many_to_one"
    )

    tabla = tabla.drop(
        columns=["CodigoArticulo"],
        errors="ignore"
    )

    # ------------------------------------------------------
    # FORMATOS DE VOLUMETRÍA
    # ------------------------------------------------------

    columnas_volumetria = [
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
        "PesoKg",
        "VolumenM3",
    ]

    for columna in columnas_volumetria:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce"
            )
            .fillna(0)
        )

    # ------------------------------------------------------
    # VOLUMEN TOTAL POR LÍNEA
    # ------------------------------------------------------

    tabla["VolumenLineaM3"] = (
        tabla["Cantidad"]
        * tabla["VolumenM3"]
    )

    tabla["VolumenM3"] = (
        tabla["VolumenM3"]
        .round(6)
    )

    tabla["VolumenLineaM3"] = (
        tabla["VolumenLineaM3"]
        .round(4)
    )


    # ------------------------------------------------------
    # ELIMINAR COLUMNAS AUXILIARES
    # ------------------------------------------------------

    tabla = tabla.drop(

        columns=[

            "COD_ART",
            "COD_RUB",
            "COD_MAR"

        ],

        errors="ignore"

    )

    # ------------------------------------------------------
    # ORDENAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla[
        [
            "Pedido",
            "ArticuloCodigo",
            "ArticuloDescripcion",
            "Cantidad",
            "Familia",
            "Familia2",
            "Marca",
            "Tipo",
            "Origen",
            "Gama",
            "Rubro",
            "Sector",
            "Sectorizacion",
            "Terminacion",
            "AltoMM",
            "AnchoMM",
            "ProfundoMM",
            "PesoKg",
            "VolumenM3",
            "VolumenLineaM3",
        ]
    ].copy()


    # ------------------------------------------------------
    # ORDENAR REGISTROS
    # ------------------------------------------------------

    tabla = tabla.sort_values(

        [

            "Pedido",

            "Familia",

            "ArticuloDescripcion"

        ]

    ).reset_index(

        drop=True

    )


    return tabla    

# ==========================================================
# RESUMEN PEDIDOS
# ==========================================================

def construir_resumen_pedidos(

    tabla_detalle

):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    resumen = tabla_detalle.copy()

    # ------------------------------------------------------
    # TOTAL UNIDADES
    # ------------------------------------------------------

    resumen = (
        resumen
        .groupby(
            "Pedido",
            as_index=False
        )
        .agg(
            TotalUnidades=(
                "Cantidad",
                "sum"
            ),
            TotalSKUs=(
                "ArticuloCodigo",
                "nunique"
            ),
            TotalM3=(
                "VolumenLineaM3",
                "sum"
            )
        )
    )

    resumen["TotalM3"] = (
        resumen["TotalM3"]
        .fillna(0)
        .round(3)
    )

# ------------------------------------------------------
# UNIDADES POR SECTORIZACION
# ------------------------------------------------------

    familias = (
    tabla_detalle
    .groupby(
        [
            "Pedido",
            "Sectorizacion"
        ],
        as_index=False
    )
    .agg(
        Unidades=(
            "Cantidad",
            "sum"
        )
    )
)

    familias = familias.rename(
    columns={
        "Sectorizacion": "Familia"
    }
)

    # ------------------------------------------------------
    # TEXTO FAMILIAS
    # ------------------------------------------------------

    familias["Detalle"] = (

        familias["Familia"]

        +

        " ("

        +

        familias["Unidades"]

        .astype(int)

        .astype(str)

        +

        ")"

    )

    detalle_familias = (

        familias

        .groupby(

            "Pedido"

        )["Detalle"]

        .apply(

            " | ".join

        )

        .reset_index(

            name="DetalleFamilias"

        )

    )

    # ------------------------------------------------------
    # FAMILIAS EN COLUMNAS
    # ------------------------------------------------------

    familias_pivot = (

        familias

        .pivot(

            index="Pedido",

            columns="Familia",

            values="Unidades"

        )

        .fillna(0)

        .astype(int)

        .reset_index()

    )

    familias_pivot.columns.name = None

    # ------------------------------------------------------
    # MERGE RESUMEN
    # ------------------------------------------------------

    resumen = resumen.merge(

        detalle_familias,

        on="Pedido",

        how="left"

    )

    resumen = resumen.merge(

        familias_pivot,

        on="Pedido",

        how="left"

    )

    resumen = resumen.fillna(0)

    return resumen

