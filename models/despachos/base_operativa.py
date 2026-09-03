from __future__ import annotations

import pandas as pd


COLUMNAS_FINALES_DESPACHOS = [
    "Pedido",
    "Fecha",
    "FechaTransmisionERP",
    "HoraTransmisionERP",
    "ClienteCodigo",
    "ClienteDescripcion",
    "Estado",
    "PreparacionEstado",
    "PreparacionID",
    "CodigoDespacho",
    "DespachoDescripcion",
    "FrecuenciaEntrega",
    "DiaEntrega",
    "ZonaAgrupadorExpreso",
    "ZonaExpreso",
    "Planificacion",
    "UnidadesPedido",
    "TotalUnidades",
    "TotalM3",
    "TotalSKUs",
    "DetalleFamilias",
    "ImporteERP",
]


def _normalizar_pedido(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def construir_tabla_operativa_despachos(
    tabla_pedidos: pd.DataFrame,
    tabla_transmisiones: pd.DataFrame,
    tabla_pendientes_erp: pd.DataFrame,
    tabla_clientes: pd.DataFrame,
    tabla_expresos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Consolida la tabla operativa final utilizada por Dashboard y Planificador.

    Esta función no lee archivos ni toca Streamlit. Solo transforma DataFrames.
    """

    tabla = tabla_pedidos.copy()
    transmisiones = tabla_transmisiones.copy()
    pendientes_erp = tabla_pendientes_erp.copy()
    clientes = tabla_clientes.copy()
    expresos = tabla_expresos.copy()

    # =====================================================
    # CLAVES DE PEDIDO
    # =====================================================

    tabla["Pedido"] = _normalizar_pedido(tabla["Pedido"])
    pendientes_erp["Pedido"] = _normalizar_pedido(
        pendientes_erp["Pedido"]
    )

    transmisiones["Pedido"] = (
        _normalizar_pedido(transmisiones["Pedido"])
        .str.split("-")
        .str[0]
    )

    # =====================================================
    # ÚLTIMA TRANSMISIÓN ERP
    # =====================================================

    tabla = tabla.merge(
        transmisiones,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    for columna in [
        "NroEnvioERP",
        "EstadoTransmisionERP",
        "HoraTransmisionERP",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabla["FechaTransmisionERP"] = pd.to_datetime(
        tabla["FechaTransmisionERP"],
        errors="coerce",
    )

    # =====================================================
    # PENDIENTES ERP
    # =====================================================

    columnas_pendientes = [
        "Pedido",
        "CodigoSucursal",
        "CodigoExpreso",
        "UnidadesPendientesERP",
        "VolumenPendienteERP",
        "ImporteERP",
    ]

    faltantes_pendientes = [
        columna
        for columna in columnas_pendientes
        if columna not in pendientes_erp.columns
    ]

    if faltantes_pendientes:
        raise ValueError(
            "Pedidos Pendientes no contiene las columnas requeridas: "
            f"{faltantes_pendientes}"
        )

    pendientes_planificacion = (
        pendientes_erp[columnas_pendientes]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        pendientes_planificacion,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    # La planificación trabaja sobre la cantidad que continúa pendiente.
    unidades_totales_originales = (
        pd.to_numeric(
            tabla["TotalUnidades"],
            errors="coerce",
        )
        .fillna(0)
    )

    # Unidades originales del pedido según la construcción base
    # utilizada también por el módulo Pedidos.
    # Se preservan para visualización y control cruzado.
    tabla["UnidadesPedido"] = (
        unidades_totales_originales
        .round(0)
        .astype(int)
    )

    volumen_total_original = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
    )

    tabla["UnidadesPendientesERP"] = (
        pd.to_numeric(
            tabla["UnidadesPendientesERP"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    proporcion_pendiente = (
        tabla["UnidadesPendientesERP"]
        .div(
            unidades_totales_originales.replace(
                0,
                pd.NA,
            )
        )
        .fillna(0)
        .clip(lower=0, upper=1)
    )

    tabla["TotalUnidades"] = (
        tabla["UnidadesPendientesERP"]
    )

    tabla["TotalM3"] = (
        volumen_total_original
        * proporcion_pendiente
    ).round(3)

    # =====================================================
    # CLAVES DE PLANIFICACIÓN
    # =====================================================

    for columna in [
        "CodigoSucursal",
        "CodigoExpreso",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    clientes["CodigoSucursal"] = (
        clientes["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    expresos["CodigoExpreso"] = (
        expresos["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # =====================================================
    # MAESTRO CLIENTES
    # =====================================================

    clientes_planificacion = (
        clientes[
            [
                "CodigoSucursal",
                "FrecuenciaPreparacion",
                "FrecuenciaEntrega",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoSucursal"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        clientes_planificacion,
        on="CodigoSucursal",
        how="left",
        validate="many_to_one",
    )

    # =====================================================
    # MAESTRO EXPRESOS
    # =====================================================

    expresos_planificacion = (
        expresos[
            [
                "CodigoExpreso",
                "LocalidadExpreso",
                "ZonaAgrupadorExpreso",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoExpreso"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        expresos_planificacion,
        on="CodigoExpreso",
        how="left",
        validate="many_to_one",
    )

    columnas_planificacion = [
        "FrecuenciaPreparacion",
        "FrecuenciaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
    ]

    for columna in columnas_planificacion:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # =====================================================
    # PLANIFICACIÓN FINAL
    # =====================================================

    zona_expreso = (
        tabla["ZonaAgrupadorExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frecuencia_entrega = (
        tabla["FrecuenciaEntrega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    es_retira = zona_expreso.eq("RETIRA")

    tabla["DiaEntrega"] = frecuencia_entrega.where(
        ~es_retira,
        "RETIRA",
    )

    tabla["ZonaExpreso"] = zona_expreso

    dias_entrega_semanal = {
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "MIÉRCOLES",
        "JUEVES",
        "VIERNES",
    }

    es_entrega_semanal = (
        frecuencia_entrega.isin(
            dias_entrega_semanal
        )
    )

    tabla["Planificacion"] = ""
    tabla.loc[
        es_retira,
        "Planificacion",
    ] = "RETIRA"

    mascara_no_retira = ~es_retira

    tabla.loc[
        mascara_no_retira,
        "Planificacion",
    ] = (
        frecuencia_entrega.loc[
            mascara_no_retira
        ].where(
            es_entrega_semanal.loc[
                mascara_no_retira
            ],
            zona_expreso.loc[
                mascara_no_retira
            ].where(
                zona_expreso.loc[
                    mascara_no_retira
                ].ne(""),
                frecuencia_entrega.loc[
                    mascara_no_retira
                ],
            ),
        )
    )

    # =====================================================
    # TIPOS
    # =====================================================

    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "FrecuenciaEntrega",
        "DiaEntrega",
        "ZonaAgrupadorExpreso",
        "ZonaExpreso",
        "Planificacion",
        "DetalleFamilias",
    ]

    for columna in columnas_texto:
        if columna in tabla.columns:
            tabla[columna] = (
                tabla[columna]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
            )

    tabla["Fecha"] = (
        pd.to_datetime(
            tabla["Fecha"],
            errors="coerce",
            utc=True,
        )
        .dt.tz_localize(None)
    )

    tabla["FechaTransmisionERP"] = (
        pd.to_datetime(
            tabla["FechaTransmisionERP"],
            errors="coerce",
        )
        .dt.date
    )

    for columna in [
        "UnidadesPedido",
        "TotalUnidades",
        "TotalSKUs",
        "ImporteERP",
    ]:
        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    tabla["TotalM3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .round(3)
    )

    columnas_faltantes = [
        columna
        for columna in COLUMNAS_FINALES_DESPACHOS
        if columna not in tabla.columns
    ]

    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas en la tabla operativa de Despachos: "
            f"{columnas_faltantes}"
        )

    return tabla[
        COLUMNAS_FINALES_DESPACHOS
    ].copy()
