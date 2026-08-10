import pandas as pd

from models.tareas_modulo.detalle_tareas import (
    construir_tabla_detalle_tareas,
    construir_resumen_pedidos_tareas,
)

# ==========================================================
# TABLA PEDIDOS
# ==========================================================

def construir_tabla_pedidos_tareas(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes,
    df_volumetria,
    tabla_detalle_preparada=None,
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

    tabla_detalle = (
        tabla_detalle_preparada
        if tabla_detalle_preparada is not None
        else construir_tabla_detalle_tareas(
            df_detalle,
            df_articulos,
            df_volumetria,
        )
    )

    # ==========================================================
    # RESUMEN
    # ==========================================================

    resumen = construir_resumen_pedidos_tareas(
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
    # UNIVERSO PARA TAREAS
    # ==========================================================
    # NO filtrar por estado.
    # Informe Tareas puede seguir mostrando una preparación/carrito
    # aunque el pedido en Pedidos DIGIP ya haya cambiado de estado.
    # Necesitamos conservarlo para recuperar TipoPreparacion,
    # Cliente, Unidades, SKUs y Familias.

    # ==========================================================
    # NO DESCARTAR PEDIDOS SIN DETALLE
    # ==========================================================
    # El pedido debe seguir disponible para el cruce por PreparacionID.
    # Si no hay detalle, las métricas de unidades/SKUs quedan en cero.

    # PreparacionID vacío debe seguir significando "sin preparación".
    # Esto evita contar un único "" como una preparación pendiente.
    if "PreparacionID" in tabla.columns:
        prep_texto = (
            tabla["PreparacionID"]
            .astype("string")
            .str.strip()
        )
        tabla["PreparacionID"] = tabla["PreparacionID"].where(
            prep_texto.notna() & prep_texto.ne(""),
            pd.NA,
        )

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

    tabla["TotalM3"] = (
    tabla["TotalM3"]
    .fillna(0)
    .round(3)
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
        "TotalM3",
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
