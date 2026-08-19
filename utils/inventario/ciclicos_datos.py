from __future__ import annotations

import pandas as pd
import streamlit as st

from models.inventario.conciliacion import (
    ConfiguracionComparacion,
    construir_conciliacion,
)
from models.inventario.planificacion import (
    calcular_score_prioridad,
)
from utils.inventario.exclusiones import (
    filtrar_articulos_fuera_inventario,
)


def _columnas_existentes(
    dataframe: pd.DataFrame,
    preferidas: tuple[str, ...],
    alternativas: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Devuelve una configuración válida según las columnas reales.

    Primero intenta utilizar todas las columnas preferidas.
    Si ninguna existe, toma la primera alternativa disponible.
    """

    if dataframe is None or dataframe.empty:
        return tuple()

    disponibles = set(
        str(columna).strip()
        for columna in dataframe.columns
    )

    seleccionadas = tuple(
        columna
        for columna in preferidas
        if columna in disponibles
    )

    if seleccionadas:
        return seleccionadas

    for columna in alternativas:
        if columna in disponibles:
            return (columna,)

    return tuple()


def resolver_configuracion_ciclicos(
    df_erp: pd.DataFrame,
    df_erp_sanitarios: pd.DataFrame,
    df_wms_disponible: pd.DataFrame,
) -> ConfiguracionComparacion:
    """
    Configuración operativa predeterminada de Inventarios Cíclicos.

    ERP principal:
        est_1 + est_8

    ERP Sanitarios:
        stk_fis

    WMS:
        Disponible + Bloqueados + Recepcion

    Si una fuente cambia de estructura, utiliza una alternativa
    existente en vez de romper la pantalla.
    """

    columnas_erp = _columnas_existentes(
        df_erp,
        preferidas=(
            "est_1",
            "est_8",
        ),
        alternativas=(
            "stk_fis",
            "stk_dis",
            "est_1",
            "est_8",
        ),
    )

    columnas_sanitarios = _columnas_existentes(
        df_erp_sanitarios,
        preferidas=(
            "stk_fis",
        ),
        alternativas=(
            "est_1",
            "est_8",
            "stk_dis",
        ),
    )

    estados_wms = _columnas_existentes(
        df_wms_disponible,
        preferidas=(
            "Disponible",
            "Bloqueados",
            "Recepcion",
            "Preparacion",
        ),
        alternativas=(
            "Disponible",
            "Bloqueados",
            "Recepcion",
            "Preparacion",
        ),
    )

    if not columnas_erp:
        raise ValueError(
            "No se encontraron columnas válidas para "
            "construir el stock del ERP principal."
        )

    incluir_sanitarios = bool(
        df_erp_sanitarios is not None
        and not df_erp_sanitarios.empty
        and columnas_sanitarios
    )

    if not estados_wms:
        raise ValueError(
            "No se encontraron los estados comparables "
            "del WMS: Disponible, Bloqueados, Recepcion o Preparacion."
        )

    return ConfiguracionComparacion(
        columnas_stock_erp=columnas_erp,
        incluir_erp_sanitarios=incluir_sanitarios,
        columnas_stock_erp_sanitarios=(
            columnas_sanitarios
        ),
        incluir_estados_wms=estados_wms,
    )


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def construir_base_ciclicos(
    df_erp: pd.DataFrame,
    df_erp_sanitarios: pd.DataFrame,
    df_wms_stock_digip: pd.DataFrame,
    df_wms_recepcion: pd.DataFrame,
    df_wms_detalle_auxiliar: pd.DataFrame,
    df_wms_disponible: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_wms_preparacion: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    configuracion = resolver_configuracion_ciclicos(
        df_erp=df_erp,
        df_erp_sanitarios=df_erp_sanitarios,
        df_wms_disponible=df_wms_disponible,
    )

    tabla, detalle, _ = construir_conciliacion(
        df_erp,
        df_erp_sanitarios,
        df_wms_stock_digip,
        df_wms_recepcion,
        df_wms_detalle_auxiliar,
        df_wms_disponible,
        df_articulos,
        df_wms_preparacion=df_wms_preparacion,
        configuracion=configuracion,
    )

    tabla = filtrar_articulos_fuera_inventario(
        tabla,
        ocultar=True,
    )
    detalle = filtrar_articulos_fuera_inventario(
        detalle,
        ocultar=True,
    )

    tabla = calcular_score_prioridad(tabla)

    return tabla, detalle



def limpiar_cache_ciclicos() -> None:
    construir_base_ciclicos.clear()
