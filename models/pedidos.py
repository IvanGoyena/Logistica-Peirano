import pandas as pd

from models.detalle import (

    construir_tabla_detalle,
    construir_resumen_pedidos

)

# ==========================================================
# TABLA PEDIDOS
# ==========================================================

def construir_tabla_pedidos(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes
):

    # ==========================================================
    # COPIA
    # ==========================================================

    tabla = df_pedidos.copy()

    # ==========================================================
    # NORMALIZAR PEDIDO
    # ==========================================================

    tabla["Pedido"] = (
        tabla["Codigo"]
        .fillna("")
        .astype(str)
        .str.split()
        .str[1]
        .str.split("-")
        .str[0]
    )

    # ==========================================================
    # TABLA DETALLE
    # ==========================================================

    tabla_detalle = construir_tabla_detalle(
        df_detalle,
        df_articulos
    )

    # ==========================================================
    # RESUMEN
    # ==========================================================

    resumen = construir_resumen_pedidos(
        tabla_detalle
    )

    # ==========================================================
    # MERGE
    # ==========================================================

    tabla = tabla.merge(
        resumen,
        on="Pedido",
        how="left"
    )

    # ==========================================================
    # PEDIDOS ACTIVOS
    # ==========================================================

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

    # ==========================================================
    # SOLO PEDIDOS CON DETALLE
    # ==========================================================

    tabla = tabla[
        tabla["TotalUnidades"].notna()
    ].copy()

    # ==========================================================
    # FORMATOS
    # ==========================================================

    tabla["TotalUnidades"] = (
        tabla["TotalUnidades"]
        .fillna(0)
        .astype(int)
    )

    tabla["TotalSKUs"] = (
        tabla["TotalSKUs"]
        .fillna(0)
        .astype(int)
    )

    if "CantidadFamilias" in tabla.columns:
        tabla["CantidadFamilias"] = (
            tabla["CantidadFamilias"]
            .fillna(0)
            .astype(int)
        )

    # ==========================================================
    # ELIMINAR COLUMNAS
    # ==========================================================

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

    # ==========================================================
    # ORDEN DE COLUMNAS
    # ==========================================================

    columnas_fijas = [
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
        "Importe",
        "TotalUnidades",
        "TotalSKUs",
        "CantidadFamilias",
        "DetalleFamilias"
    ]

    # Mantener únicamente las columnas existentes

    columnas_fijas = [
        c
        for c in columnas_fijas
        if c in tabla.columns
    ]

    columnas_extra = [
        c
        for c in tabla.columns
        if c not in columnas_fijas
    ]

    tabla = tabla[
        columnas_fijas +
        sorted(columnas_extra)
    ]

    return tabla
