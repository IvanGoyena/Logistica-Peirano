from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from models.inventario.conciliacion import (
    ConfiguracionComparacion,
    construir_conciliacion,
)
from models.inventario.diagnostico_preventivo import (
    construir_diagnostico_preventivo,
)


CLAVE_DATOS = "inventario_snapshot_datos"
CLAVE_NOMBRES = "inventario_snapshot_nombres"
CLAVE_ERRORES = "inventario_snapshot_errores"
CLAVE_FECHA = "inventario_snapshot_fecha"


@st.cache_data(
    show_spinner=False,
    max_entries=8,
)
def procesar_inventario_cacheado(
    df_erp: pd.DataFrame,
    df_erp_sanitarios: pd.DataFrame,
    df_wms_stock_digip: pd.DataFrame,
    df_wms_recepcion: pd.DataFrame,
    df_wms_detalle_auxiliar: pd.DataFrame,
    df_wms_disponible: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_ubicaciones: pd.DataFrame,
    df_picking_config: pd.DataFrame,
    *,
    columnas_stock_erp: tuple[str, ...],
    incluir_erp_sanitarios: bool,
    columnas_stock_erp_sanitarios: tuple[str, ...],
    estados_wms: tuple[str, ...],
    tolerancia_unidades: float,
    tolerancia_porcentaje: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict,
]:
    """
    Consolida y diagnostica el inventario una sola vez para
    cada combinación real de fuentes y configuración.

    Los filtros visuales no vuelven a ejecutar este proceso.
    """

    tabla, detalle, config = construir_conciliacion(
        df_erp,
        df_erp_sanitarios,
        df_wms_stock_digip,
        df_wms_recepcion,
        df_wms_detalle_auxiliar,
        df_wms_disponible,
        df_articulos,
        configuracion=ConfiguracionComparacion(
            columnas_stock_erp=(
                columnas_stock_erp
            ),
            incluir_erp_sanitarios=(
                incluir_erp_sanitarios
            ),
            columnas_stock_erp_sanitarios=(
                columnas_stock_erp_sanitarios
            ),
            incluir_estados_wms=estados_wms,
        ),
        tolerancia_unidades=(
            tolerancia_unidades
        ),
        tolerancia_porcentaje=(
            tolerancia_porcentaje
        ),
    )

    tabla, detalle = (
        construir_diagnostico_preventivo(
            tabla,
            detalle,
            maestro_ubicaciones=df_ubicaciones,
            configuracion_picking=(
                df_picking_config
            ),
        )
    )

    return tabla, detalle, config


def guardar_snapshot_fuentes(
    datos: dict[str, pd.DataFrame],
    nombres: dict[str, str],
    errores: list[str],
) -> None:
    """
    Mantiene las fuentes cargadas durante toda la sesión.
    """

    st.session_state[CLAVE_DATOS] = datos
    st.session_state[CLAVE_NOMBRES] = nombres
    st.session_state[CLAVE_ERRORES] = errores
    st.session_state[CLAVE_FECHA] = (
        datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )
    )


def obtener_snapshot_fuentes() -> tuple[
    dict[str, pd.DataFrame] | None,
    dict[str, str],
    list[str],
    str,
]:
    return (
        st.session_state.get(CLAVE_DATOS),
        st.session_state.get(
            CLAVE_NOMBRES,
            {},
        ),
        st.session_state.get(
            CLAVE_ERRORES,
            [],
        ),
        st.session_state.get(
            CLAVE_FECHA,
            "",
        ),
    )


def limpiar_snapshot_inventario() -> None:
    for clave in (
        CLAVE_DATOS,
        CLAVE_NOMBRES,
        CLAVE_ERRORES,
        CLAVE_FECHA,
    ):
        st.session_state.pop(clave, None)

    procesar_inventario_cacheado.clear()
