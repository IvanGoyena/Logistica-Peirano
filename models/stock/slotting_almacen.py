from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from models.stock.slotting import construir_diagnostico_slotting


COLUMNAS_RESUMEN_ALMACEN = [
    "ScoreSlotting",
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "Sectorizacion",
    "CategoriaRotacion",
    "AreaPicking",
    "PasilloPicking",
    "AreaAlmacenPrincipal",
    "PasillosStock",
    "CantidadPasillos",
    "CantidadPalletsAlmacen",
    "DistanciaPromedioPonderada",
    "StockCercanoPct",
    "StockFueraBloquePct",
    "EstadoDistribucion",
]

COLUMNAS_DETALLE_ALMACEN = [
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "Familia",
    "Familia2",
    "Sectorizacion",
    "CategoriaRotacion",
    "StockFisico",
    "StockAlmacenDetectado",
    "AreaPicking",
    "UbicacionPicking",
    "PasilloPicking",
    "AreaAlmacenPrincipal",
    "PasillosStock",
    "PasilloStockPrincipal",
    "CantidadUbicaciones",
    "CantidadPasillos",
    "CantidadPalletsAlmacen",
    "UnidadesPorPallet",
    "MetodoEstandarizacion",
    "DistanciaPromedioPonderada",
    "DistanciaMaxima",
    "StockCercano",
    "StockLejano",
    "StockCercanoPct",
    "StockFueraBloque",
    "StockFueraBloquePct",
    "BloqueEsperado",
    "EstadoDistribucion",
    "ScoreSlotting",
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
    show_spinner="Preparando Slotting de Almacén...",
)
def construir_analisis_almacen(
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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
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
        return (
            diagnostico,
            diagnostico,
            pd.DataFrame(),
            metadata,
        )

    resumen = diagnostico[
        _columnas_existentes(
            diagnostico,
            COLUMNAS_RESUMEN_ALMACEN,
        )
    ].copy()

    resumen["PrioridadDistribucion"] = (
        pd.to_numeric(
            diagnostico.get(
                "DistanciaPromedioPonderada",
                0,
            ),
            errors="coerce",
        ).fillna(0)
        * 8
        + pd.to_numeric(
            diagnostico.get(
                "CantidadPasillos",
                0,
            ),
            errors="coerce",
        ).fillna(0)
        * 5
        + pd.to_numeric(
            diagnostico.get(
                "StockFueraBloquePct",
                0,
            ),
            errors="coerce",
        ).fillna(0)
        * 0.45
        + np.where(
            diagnostico[
                "CategoriaRotacion"
            ].eq("🔥 Caliente"),
            15,
            0,
        )
    ).clip(0, 100)

    columnas_orden = [
        "PrioridadDistribucion",
        *[
            columna
            for columna in COLUMNAS_RESUMEN_ALMACEN
            if columna in resumen.columns
        ],
    ]
    resumen = resumen[
        list(dict.fromkeys(columnas_orden))
    ].sort_values(
        "PrioridadDistribucion",
        ascending=False,
    )

    detalle = diagnostico[
        _columnas_existentes(
            diagnostico,
            COLUMNAS_DETALLE_ALMACEN,
        )
    ].copy()

    resumen_pasillos = metadata.get(
        "resumen_pasillos",
        pd.DataFrame(),
    )

    return (
        resumen,
        detalle,
        resumen_pasillos,
        metadata,
    )


def obtener_detalle_almacen(
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
