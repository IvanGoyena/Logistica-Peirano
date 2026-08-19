import pandas as pd

from models.pedidos import normalizar_pedidos_digip

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

    tabla = normalizar_pedidos_digip(
        df_pedidos
    )

    # ==========================================================
    # NOMBRE DE CLIENTE DESDE MAESTRO
    # ==========================================================
    # "ClienteUbicacion Descripcion" de DIGIP describe la
    # ubicación logística, no el nombre comercial.
    # Tareas usa el mismo criterio que Pedidos:
    # Codigo_Cliente -> Cliente.
    maestro_clientes = (
        df_clientes.copy()
        if df_clientes is not None
        else pd.DataFrame()
    )

    if not maestro_clientes.empty:
        maestro_clientes.columns = (
            maestro_clientes.columns
            .astype(str)
            .str.strip()
        )

        if (
            "Codigo_Cliente" in maestro_clientes.columns
            and "Cliente" in maestro_clientes.columns
        ):
            nombres = maestro_clientes[
                ["Codigo_Cliente", "Cliente"]
            ].copy()

            nombres["ClienteCodigo"] = (
                nombres["Codigo_Cliente"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .str.replace(r"\.0$", "", regex=True)
            )

            nombres["ClienteDescripcionMaestro"] = (
                nombres["Cliente"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            nombres = (
                nombres.loc[nombres["ClienteCodigo"].ne("")]
                .drop_duplicates(
                    subset=["ClienteCodigo"],
                    keep="first",
                )
                [["ClienteCodigo", "ClienteDescripcionMaestro"]]
            )

            tabla["ClienteCodigo"] = (
                tabla["ClienteCodigo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .str.replace(r"\.0$", "", regex=True)
            )

            tabla = tabla.merge(
                nombres,
                on="ClienteCodigo",
                how="left",
                validate="many_to_one",
            )

            tabla["ClienteDescripcion"] = (
                tabla["ClienteDescripcionMaestro"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            tabla = tabla.drop(
                columns=["ClienteDescripcionMaestro"],
                errors="ignore",
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

    if "Pedido" in tabla_detalle.columns:
        tabla_detalle = tabla_detalle.copy()
        tabla_detalle["Pedido"] = (
            tabla_detalle["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
            .str.split("-")
            .str[0]
        )

    # ==========================================================
    # RESUMEN
    # ==========================================================

    resumen = construir_resumen_pedidos_tareas(
        tabla_detalle
    )

    if not resumen.empty:
        resumen = resumen.copy()
        resumen["Pedido"] = (
            resumen["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
            .str.split("-")
            .str[0]
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
