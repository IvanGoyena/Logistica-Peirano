from __future__ import annotations

import pandas as pd


def calcular_resumen_fuentes(
    resultados: list,
) -> dict[str, int]:
    total = len(resultados)
    disponibles = sum(
        int(resultado.disponible)
        for resultado in resultados
    )
    registros = sum(
        len(resultado.dataframe)
        for resultado in resultados
        if isinstance(
            resultado.dataframe,
            pd.DataFrame,
        )
    )

    return {
        "total": total,
        "disponibles": disponibles,
        "con_error": sum(
            bool(resultado.error)
            for resultado in resultados
        ),
        "registros": registros,
    }


def diagnosticar_maestro_clientes(
    tabla_clientes: pd.DataFrame,
) -> dict[str, int]:
    if tabla_clientes is None or tabla_clientes.empty:
        return {
            "registros": 0,
            "duplicados": 0,
            "sin_entrega": 0,
            "sin_preparacion": 0,
            "sin_cliente": 0,
        }

    tabla = tabla_clientes.copy()

    return {
        "registros": len(tabla),
        "duplicados": int(
            tabla["CodigoSucursal"]
            .duplicated(keep=False)
            .sum()
            if "CodigoSucursal" in tabla.columns
            else 0
        ),
        "sin_entrega": int(
            tabla["FrecuenciaEntrega"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
            if "FrecuenciaEntrega" in tabla.columns
            else 0
        ),
        "sin_preparacion": int(
            tabla["FrecuenciaPreparacion"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
            if "FrecuenciaPreparacion" in tabla.columns
            else 0
        ),
        "sin_cliente": int(
            tabla["ClienteDescripcion"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
            .sum()
            if "ClienteDescripcion" in tabla.columns
            else 0
        ),
    }
