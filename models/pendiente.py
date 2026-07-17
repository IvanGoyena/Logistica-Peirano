import pandas as pd


# ==========================================================
# NORMALIZACIÓN DE CLAVES
# ==========================================================

def normalizar_pedido(serie):

    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.split("-")
        .str[0]
    )


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
# TABLA PEDIDOS PENDIENTES ERP
# ==========================================================

def construir_tabla_pendientes(df_pendientes):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_pendientes.copy()

    # ------------------------------------------------------
    # VALIDACIÓN DE COLUMNAS
    # ------------------------------------------------------

    columnas_requeridas = [
        "nro_com",
        "fec_com",
        "fec_vto",
        "antigua",
        "atraso",
        "cod_cli",
        "nombre",
        "importe",
        "imp_pend",
        "estado",
        "prioridad",
        "nom_dist",
        "cod_expre",
        "des_expre",
        "can_art",
        "can_rem",
        "voltotpd",
        "voltotrm",
        "cod_zona",
        "des_zona",
        "cod_flete",
        "des_flete",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in tabla.columns
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas en Pedidos Pendientes ERP: "
            f"{columnas_faltantes}"
        )

    # ------------------------------------------------------
    # RENOMBRAR COLUMNAS
    # ------------------------------------------------------

    tabla = tabla.rename(
        columns={
            "nro_com": "Pedido",
            "fec_com": "FechaPedidoERP",
            "fec_vto": "FechaVencimientoERP",
            "antigua": "AntiguedadDiasERP",
            "atraso": "AtrasoDiasERP",
            "cod_cli": "ClienteCodigoERP",
            "nombre": "ClienteDescripcionERP",
            "importe": "ImporteERP",
            "imp_pend": "ImportePendienteERP",
            "estado": "EstadoERP",
            "prioridad": "PrioridadERP",
            "nom_dist": "DistribuidorERP",
            "cod_expre": "CodigoExpreso",
            "des_expre": "ExpresoERP",
            "can_art": "CantidadArticulosERP",
            "can_rem": "CantidadRemitidaERP",
            "voltotpd": "VolumenPedidoERP",
            "voltotrm": "VolumenRemitidoERP",
            "cod_zona": "CodigoZonaERP",
            "des_zona": "ZonaERP",
            "cod_flete": "CodigoFleteERP",
            "des_flete": "FleteERP",
            "des_moneda": "MonedaERP",
            "ocp_cli": "OrdenCompraCliente",
            "cod_ven": "VendedorCodigoERP",
            "des_ven": "VendedorERP",
            "cod_vta": "CondicionVentaCodigoERP",
            "des_vta": "CondicionVentaERP",
            "cod_dist": "DistribuidorCodigoERP",
            "des_clase": "ClaseClienteERP",
            "mark_comen": "MarcaComercialERP",
        }
    )

    # ------------------------------------------------------
    # NORMALIZAR CLAVES
    # ------------------------------------------------------

    tabla["Pedido"] = normalizar_pedido(
        tabla["Pedido"]
    )

    tabla["ClienteCodigoERP"] = normalizar_codigo(
    tabla["ClienteCodigoERP"]
    )

    tabla["DistribuidorCodigoERP"] = normalizar_codigo(
        tabla["DistribuidorCodigoERP"]
    )   

    tabla["CodigoExpreso"] = normalizar_codigo(
        tabla["CodigoExpreso"]
    )

    if "CodigoZonaERP" in tabla.columns:

        tabla["CodigoZonaERP"] = normalizar_codigo(
            tabla["CodigoZonaERP"]
        )

    if "CodigoFleteERP" in tabla.columns:

        tabla["CodigoFleteERP"] = normalizar_codigo(
            tabla["CodigoFleteERP"]
        )


    # ------------------------------------------------------
    # CÓDIGO SUCURSAL
    # Cliente + distribuidor, sin separador
    # ------------------------------------------------------

    tabla["CodigoSucursal"] = (
        tabla["ClienteCodigoERP"]
        .fillna("")
        .astype(str)
        .str.strip()
        + "-"
        +
        tabla["DistribuidorCodigoERP"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    # ------------------------------------------------------
    # FECHAS
    # ------------------------------------------------------

    columnas_fecha = [
        "FechaPedidoERP",
        "FechaVencimientoERP",
    ]

    for columna in columnas_fecha:

        tabla[columna] = pd.to_datetime(
            tabla[columna],
            errors="coerce",
            dayfirst=True
        )

    # ------------------------------------------------------
    # CAMPOS NUMÉRICOS ENTEROS
    # ------------------------------------------------------

    columnas_enteras = [
        "AntiguedadDiasERP",
        "AtrasoDiasERP",
        "PrioridadERP",
        "CantidadArticulosERP",
        "CantidadRemitidaERP",
    ]

    for columna in columnas_enteras:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce"
            )
            .fillna(0)
            .astype(int)
        )

    # ------------------------------------------------------
    # IMPORTES Y VOLUMEN
    # ------------------------------------------------------

    columnas_decimales = [
        "ImporteERP",
        "ImportePendienteERP",
        "VolumenPedidoERP",
        "VolumenRemitidoERP",
    ]

    for columna in columnas_decimales:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce"
            )
            .fillna(0)
        )

    # ------------------------------------------------------
    # TEXTOS
    # ------------------------------------------------------

    columnas_texto = [
        "ClienteDescripcionERP",
        "EstadoERP",
        "DistribuidorERP",
        "ExpresoERP",
        "ZonaERP",
        "FleteERP",
    ]

    for columna in columnas_texto:

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabla["EstadoERP"] = (
        tabla["EstadoERP"]
        .str.upper()
    )

    # ------------------------------------------------------
    # CAMPOS CALCULADOS INICIALES
    # ------------------------------------------------------

    tabla["TieneExpreso"] = (
        tabla["CodigoExpreso"] != ""
    )

    tabla["UnidadesPendientesERP"] = (
        tabla["CantidadArticulosERP"]
        - tabla["CantidadRemitidaERP"]
    ).clip(lower=0)

    tabla["VolumenPendienteERP"] = (
        tabla["VolumenPedidoERP"]
        - tabla["VolumenRemitidoERP"]
    ).clip(lower=0)

    tabla["PedidoVencidoERP"] = (
        tabla["AtrasoDiasERP"] > 0
    )

        # ------------------------------------------------------
    # EVITAR DUPLICADOS
    # ------------------------------------------------------

    tabla = (
        tabla
        .sort_values(
            [
                "Pedido",
                "FechaPedidoERP"
            ],
            ascending=[
                True,
                False
            ]
        )
        .drop_duplicates(
            subset=["Pedido"],
            keep="first"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # ELIMINAR COLUMNAS SIN USO
    # ------------------------------------------------------

    columnas_eliminar = [
        "ini_com",
        "nro_rev",
        "imp_bonificado",
        "tot_descuento",
        "imp_fac",
        "imp_afac",
        "imp_facant",
        "cod_ope",
        "des_ope",
        "cod_suc",
        "des_suc",
        "cod_moneda",
        "por_bon1",
        "por_bon2",
        "por_bon3",
        "tip_com",
        "a_pagar",
        "ali_iva",
        "imp_iva",
        "obs_credres",
        "des_creditres",
        "cod_clase",
        "no_comer",
        "usuariogenero",
        "fechagenero",
        "cod_lis",
        "des_lis",
        "obs_cred",
        "des_credit",
        "leyenda",
    ]

    tabla = tabla.drop(
        columns=columnas_eliminar,
        errors="ignore"
    )

    # ------------------------------------------------------
    # ORDEN DEFINITIVO DE COLUMNAS
    # ------------------------------------------------------

    columnas_finales = [
        "Pedido",
        "EstadoERP",
        "PrioridadERP",

        "FechaPedidoERP",
        "FechaVencimientoERP",
        "AntiguedadDiasERP",
        "AtrasoDiasERP",
        "PedidoVencidoERP",

        "ClienteCodigoERP",
        "DistribuidorCodigoERP",
        "CodigoSucursal",
        "ClienteDescripcionERP",
        "DistribuidorERP",

        "CodigoExpreso",
        "ExpresoERP",
        "TieneExpreso",
        "CodigoZonaERP",
        "ZonaERP",
        "CodigoFleteERP",
        "FleteERP",

        "CantidadArticulosERP",
        "CantidadRemitidaERP",
        "UnidadesPendientesERP",

        "VolumenPedidoERP",
        "VolumenRemitidoERP",
        "VolumenPendienteERP",

        "ImporteERP",
        "ImportePendienteERP",
        "MonedaERP",

        "OrdenCompraCliente",
        "VendedorCodigoERP",
        "VendedorERP",
        "CondicionVentaCodigoERP",
        "CondicionVentaERP",
        "ClaseClienteERP",
        "MarcaComercialERP",
    ]

    columnas_finales = [
        columna
        for columna in columnas_finales
        if columna in tabla.columns
    ]

    tabla = tabla[columnas_finales].copy()

    # ------------------------------------------------------
    # TABLA SATÉLITE FINAL
    # Solo información necesaria para enriquecer
    # la tabla principal de Pedidos DIGIP
    # ------------------------------------------------------

    columnas_satelite = [

        # CLAVE PARA EL MERGE CON PEDIDOS DIGIP
        "Pedido",

        # INFORMACIÓN ERP QUE NO ESTÁ EN DIGIP
        "FechaPedidoERP",
        "AtrasoDiasERP",

        # CLAVE DE CLIENTE + SUCURSAL
        "CodigoSucursal",

        # PLANIFICACIÓN Y EXPRESOS
        "CodigoExpreso",

        # CARGA PENDIENTE
        "UnidadesPendientesERP",

        # INFORMACIÓN ECONÓMICA
        "ImporteERP",

    ]

    # Validar que las columnas existan
    columnas_satelite = [
        columna
        for columna in columnas_satelite
        if columna in tabla.columns
    ]

    # Salida definitiva del modelo
    tabla = tabla[columnas_satelite].copy()

    return tabla