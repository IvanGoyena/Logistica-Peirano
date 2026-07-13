import pandas as pd

# ==========================================================
# RESUMEN DE PEDIDOS
# ==========================================================

def construir_resumen_pedidos(

    df_detalle,
    df_articulos

):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    detalle = df_detalle.copy()

    # ------------------------------------------------------
    # TIPOS DE DATOS
    # ------------------------------------------------------

    detalle["nro_com"] = (

        detalle["nro_com"]

        .fillna("")

        .astype(str)

    )

    detalle["can_art"] = (

        pd.to_numeric(

            detalle["can_art"],

            errors="coerce"

        )

        .fillna(0)

    )

    # ------------------------------------------------------
    # RESUMEN POR PEDIDO
    # ------------------------------------------------------

    resumen = (

        detalle

        .groupby("nro_com")

        .agg(

            TotalUnidades=("can_art", "sum"),

            TotalSKUs=("cod_art", "nunique")

        )

        .reset_index()

    )

    return resumen


# ==========================================================
# TABLA OPERATIVA DE PEDIDOS
# ==========================================================

def construir_tabla_pedidos(

    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes

):


# ------------------------------------------------------
# COPIA
# ------------------------------------------------------

    tabla = df_pedidos.copy()

    # ------------------------------------------------------
    # NORMALIZAR PEDIDO
    # ------------------------------------------------------

    tabla["Pedido"] = (

        tabla["Codigo"]

        .fillna("")

        .astype(str)

        .str.split()

        .str[1]

        .str.split("-")

        .str[0]

    )

    # ------------------------------------------------------
    # ELIMINAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.drop(

        columns=[

            "PedidoID",
            "Codigo",
            "CodigoDeEnvio",
            "ServicioDeEnvioTipo",
            "OrdenPreparacion",
            "DespachoID",
            "ClienteID",
            "Tags"

        ],

        errors="ignore"

    )

    # ------------------------------------------------------
    # ORDENAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla[

        [

            "Pedido",

            "ClienteCodigo",
            "ClienteDescripcion",

            "Estado",
            "TipoPreparacion",
            "PreparacionEstado",

            "CodigoDespacho",
            "DespachoDescripcion",

            "Fecha",
            "FechaEstimadaEntrega",

            "PreparacionID",

            "Importe"

        ]

    ].copy()

    # ------------------------------------------------------
    # RESUMEN PEDIDOS
    # ------------------------------------------------------

    resumen = construir_resumen_pedidos(

        df_detalle,
        df_articulos

    )

    # ------------------------------------------------------
    # MERGE RESUMEN
    # ------------------------------------------------------

    tabla = tabla.merge(

        resumen,

        left_on="Pedido",

        right_on="nro_com",

        how="left"

    )
    # ------------------------------------------------------
# SOLO PEDIDOS ACTIVOS
# ------------------------------------------------------

    tabla = tabla[

    tabla["Estado"]

    .fillna("")

    .isin(

        [

            "Pendiente",
            "Preparacion"

        ]

    )

].copy()

    # ------------------------------------------------------
# SOLO PEDIDOS CON DETALLE PENDIENTE
# ------------------------------------------------------

    tabla = tabla[

    tabla["TotalUnidades"]

    .notna()

].copy()

    tabla["TotalUnidades"] = (

        tabla["TotalUnidades"]

        .astype(int)

    )

    tabla["TotalSKUs"] = (

        tabla["TotalSKUs"]

        .astype(int)

    )


# ------------------------------------------------------
# LIMPIEZA
# ------------------------------------------------------

    tabla = tabla.drop(

        columns=["nro_com"],

        errors="ignore"

    )
    return tabla    