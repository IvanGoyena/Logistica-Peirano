from __future__ import annotations

import pandas as pd
import streamlit as st

from models.stock.slotting import construir_diagnostico_slotting


COLUMNAS_RESUMEN_PICKING = [
    "ScoreSlotting",
    "NivelPrioridad",
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "Sectorizacion",
    "CategoriaRotacion",
    "AreaPicking",
    "UbicacionPicking",
    "StockPickingActual",
    "StockMinimoActual",
    "StockMaximoActual",
    "StockMaximoSugerido",
    "PalletsActuales",
    "PalletsSugeridos",
    "UnidadesPorPallet",
    "AccionSugerida",
]

COLUMNAS_DETALLE_PICKING = [
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "Familia",
    "Familia2",
    "Sectorizacion",
    "Origen",
    "CategoriaRotacion",
    "AccionSugerida",
    "Motivo",
    "ScoreSlotting",
    "NivelPrioridad",
    "AreaPicking",
    "UbicacionPicking",
    "MetodoReposicionInferido",
    "StockFisico",
    "StockPickingActual",
    "StockMinimoActual",
    "StockMaximoActual",
    "StockMinimoSugerido",
    "StockMaximoSugerido",
    "DiferenciaMaximo",
    "UnidadesPorPallet",
    "MetodoEstandarizacion",
    "FuenteEstandarizacion",
    "PalletsActuales",
    "PalletsSugeridos",
    "VentaPromedioMensual",
    "VentaPromedioDiaria",
    "DiasConMovimiento",
    "DiasSinVenta",
    "DiasDesdeIngresoStock",
    "CoberturaPickingDias",
    "PresionPickingPct",
]


def _columnas_existentes(
    tabla: pd.DataFrame,
    columnas: list[str],
) -> list[str]:
    return [
        columna
        for columna in columnas
        if columna in tabla.columns
    ]


@st.cache_data(
    max_entries=6,
    show_spinner="Preparando configuración de Picking...",
)
def construir_analisis_picking(
    tabla_articulos: pd.DataFrame,
    tabla_volumetria: pd.DataFrame,
    tabla_max_min: pd.DataFrame,
    tabla_stock_detallado: pd.DataFrame,
    tabla_maestro_ubicaciones: pd.DataFrame,
    historico_ventas: pd.DataFrame,
    meses_analisis: int,
    dias_caliente: int,
    dias_intermedio: int,
    dias_frio: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    diagnostico, metadata = construir_diagnostico_slotting(
        tabla_articulos=tabla_articulos,
        tabla_volumetria=tabla_volumetria,
        tabla_max_min=tabla_max_min,
        tabla_stock_detallado=tabla_stock_detallado,
        tabla_maestro_ubicaciones=tabla_maestro_ubicaciones,
        historico_ventas=historico_ventas,
        meses_analisis=meses_analisis,
        dias_caliente=dias_caliente,
        dias_intermedio=dias_intermedio,
        dias_frio=dias_frio,
    )

    if diagnostico.empty:
        return diagnostico, diagnostico, metadata

    resumen = diagnostico[
        _columnas_existentes(
            diagnostico,
            COLUMNAS_RESUMEN_PICKING,
        )
    ].copy()

    detalle = diagnostico[
        _columnas_existentes(
            diagnostico,
            COLUMNAS_DETALLE_PICKING,
        )
    ].copy()

    return resumen, detalle, metadata


def obtener_detalle_picking(
    tabla_detalle: pd.DataFrame,
    codigo: str,
) -> pd.DataFrame:
    if tabla_detalle.empty or not codigo:
        return pd.DataFrame()

    return tabla_detalle.loc[
        tabla_detalle["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .eq(str(codigo))
    ].copy()
