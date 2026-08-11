from __future__ import annotations

import pandas as pd
import streamlit as st

from models.pedidos import construir_tabla_pedidos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos
from models.consultas_comerciales.consultas import (
    construir_tabla_consultas,
)


@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner=False,
)
def construir_tabla_operativa(
    datos: dict[str, pd.DataFrame],
) -> pd.DataFrame:

    tabla = construir_tabla_pedidos(
        datos["pedidos"].copy(),
        datos["detalle"].copy(),
        datos["articulos"].copy(),
        datos["clientes"].copy(),
        datos["volumetria"].copy(),
    )

    # ======================================================
    # RECUPERAR PEDIDOS DIGIP SIN DETALLE / ERP
    # ======================================================
    #
    # models.pedidos conserva únicamente pedidos que ya tienen
    # detalle consolidado. Para Consultas Comerciales necesitamos
    # mostrar también pedidos recién transmitidos que todavía no
    # fueron enriquecidos por Detalle Pendientes o por el ERP.
    #
    # Esta recuperación se hace solamente en este módulo para no
    # modificar el comportamiento de Pedidos, Despachos u otros
    # consumidores de models.pedidos.
    # ======================================================

    pedidos_digip_base = datos["pedidos"].copy()

    if not pedidos_digip_base.empty and "Codigo" in pedidos_digip_base.columns:

        codigo_normalizado = (
            pedidos_digip_base["Codigo"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        pedidos_digip_base["Pedido"] = (
            codigo_normalizado
            .str.split()
            .str[1]
            .str.split("-")
            .str[0]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        # Mantener el mismo universo operativo del modelo compartido:
        # pedidos pendientes o con preparación, pero sin exigir detalle.
        estado_digip = (
            pedidos_digip_base.get(
                "Estado",
                pd.Series("", index=pedidos_digip_base.index),
            )
            .fillna("")
            .astype(str)
            .str.strip()
        )

        pedidos_digip_base = pedidos_digip_base.loc[
            estado_digip.isin(
                [
                    "Pendiente",
                    "Preparacion",
                ]
            )
            & pedidos_digip_base["Pedido"].ne("")
        ].copy()

        pedidos_presentes = set(
            tabla["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .tolist()
        )

        pedidos_faltantes = pedidos_digip_base.loc[
            ~pedidos_digip_base["Pedido"].isin(pedidos_presentes)
        ].copy()

        if not pedidos_faltantes.empty:

            # Columnas que normalmente aporta el detalle consolidado.
            valores_defecto = {
                "TotalUnidades": 0,
                "TotalM3": 0.0,
                "TotalSKUs": 0,
                "CantidadFamilias": 0,
                "DetalleFamilias": "Sin detalle disponible",
            }

            for columna, valor in valores_defecto.items():
                if columna not in pedidos_faltantes.columns:
                    pedidos_faltantes[columna] = valor
                else:
                    pedidos_faltantes[columna] = (
                        pedidos_faltantes[columna].fillna(valor)
                    )

            columnas_descartar = [
                "PedidoID",
                "Codigo",
                "CodigoDeEnvio",
                "ServicioDeEnvioTipo",
                "OrdenPreparacion",
                "DespachoID",
                "ClienteID",
                "Tags",
            ]

            pedidos_faltantes = pedidos_faltantes.drop(
                columns=columnas_descartar,
                errors="ignore",
            )

            # Alinear estructuras sin perder columnas existentes.
            columnas_union = list(
                dict.fromkeys(
                    list(tabla.columns)
                    + list(pedidos_faltantes.columns)
                )
            )

            tabla = tabla.reindex(columns=columnas_union)
            pedidos_faltantes = pedidos_faltantes.reindex(
                columns=columnas_union
            )

            tabla = pd.concat(
                [
                    tabla,
                    pedidos_faltantes,
                ],
                ignore_index=True,
                sort=False,
            )

    tabla_transmisiones = construir_tabla_transmisiones(
        datos["transmisiones"].copy()
    )

    tabla_pendientes = construir_tabla_pendientes(
        datos["pendientes_erp"].copy()
    )

    tabla_clientes = construir_tabla_clientes(
        datos["clientes"].copy()
    )

    tabla_expresos = construir_tabla_expresos(
        datos["expresos"].copy()
    )

    for dataframe in [
        tabla,
        tabla_transmisiones,
        tabla_pendientes,
    ]:
        dataframe["Pedido"] = (
            dataframe["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.split("-")
            .str[0]
        )

    tabla = tabla.merge(
        tabla_transmisiones,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    pendientes_planificacion = (
        tabla_pendientes[
            [
                "Pedido",
                "CodigoSucursal",
                "CodigoExpreso",
                "ImporteERP",
            ]
        ]
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

    tabla["CodigoSucursal"] = (
        tabla["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla["CodigoExpreso"] = (
        tabla["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla_clientes["CodigoSucursal"] = (
        tabla_clientes["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla_expresos["CodigoExpreso"] = (
        tabla_expresos["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    clientes_planificacion = (
        tabla_clientes[
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

    expresos_planificacion = (
        tabla_expresos[
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

    for columna in [
        "FrecuenciaPreparacion",
        "FrecuenciaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    frecuencia_entrega = (
        tabla["FrecuenciaEntrega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    zona_expreso = (
        tabla["ZonaAgrupadorExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    dias_semanales = {
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "MIÉRCOLES",
        "JUEVES",
        "VIERNES",
    }

    tabla["Planificacion"] = frecuencia_entrega.where(
        frecuencia_entrega.isin(dias_semanales),
        zona_expreso.where(
            zona_expreso.ne(""),
            frecuencia_entrega,
        ),
    )

    # Los pedidos recién transmitidos pueden no tener todavía
    # información ERP, transmisión o detalle. Se mantienen visibles
    # con valores neutros en lugar de eliminarlos.
    columnas_texto_consultas = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "DespachoDescripcion",
        "DetalleFamilias",
        "NroEnvioERP",
        "EstadoTransmisionERP",
        "HoraTransmisionERP",
        "Planificacion",
    ]

    for columna in columnas_texto_consultas:
        if columna not in tabla.columns:
            tabla[columna] = ""
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

    if "DetalleFamilias" in tabla.columns:
        tabla["DetalleFamilias"] = tabla[
            "DetalleFamilias"
        ].replace("", "Sin detalle disponible")

    for columna in [
        "TotalUnidades",
        "TotalSKUs",
        "CantidadFamilias",
        "ImporteERP",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = 0
        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    if "TotalM3" not in tabla.columns:
        tabla["TotalM3"] = 0.0

    tabla["TotalM3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .round(3)
    )

    return tabla



@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner=False,
)
def construir_tabla_consultas_cache(
    tabla_operativa: pd.DataFrame,
    df_tareas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye la tabla comercial final una sola vez por versión de datos.
    """
    return construir_tabla_consultas(
        tabla_operativa.copy(),
        df_tareas=df_tareas.copy(),
    )


def limpiar_cache_modelo_consultas() -> None:
    """Limpia solamente las transformaciones pesadas del módulo."""
    construir_tabla_operativa.clear()
    construir_tabla_consultas_cache.clear()
