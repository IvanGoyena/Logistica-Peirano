import pandas as pd

# ==========================================================
# TABLA DETALLE
# ==========================================================

def construir_tabla_detalle(

    df_detalle,
    df_articulos

):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_detalle.copy()

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

    articulos = (

    df_articulos

    .rename(

        columns={

            "COD_ART": "ArticuloCodigo",
            "DESCRIP": "ArticuloDescripcion"

        }

    )

    [
        [
            "ArticuloCodigo",
            "ArticuloDescripcion",
            "Familia",
            "Marca",
            "Origen"
        ]
    ]

)

    # ------------------------------------------------------
    # MERGE
    # ------------------------------------------------------

    tabla = tabla.merge(

        articulos,

        on="ArticuloCodigo",

        how="left"

    )

    return tabla