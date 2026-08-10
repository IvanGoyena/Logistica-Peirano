from __future__ import annotations

import pandas as pd


def calcular_kpis_inventario(
    tabla: pd.DataFrame,
) -> dict[str, float | int]:
    if tabla is None or tabla.empty:
        return {
            "codigos": 0,
            "conciliados": 0,
            "con_diferencia": 0,
            "exactitud_codigos": 0.0,
            "exactitud_unidades": 0.0,
            "diferencia_absoluta": 0.0,
            "diferencia_neta": 0.0,
            "integridad_wms": 0.0,
            "codigos_integridad_wms": 0,
        }

    codigos = int(
        tabla["ArticuloCodigo"].nunique()
    )

    conciliados = int(
        tabla["EstadoConciliacion"]
        .eq("Conciliado")
        .sum()
    )

    con_diferencia = int(
        tabla["EstadoConciliacion"]
        .ne("Conciliado")
        .sum()
    )

    diferencia_absoluta = float(
        tabla["DiferenciaAbsoluta"].sum()
    )

    referencia = float(
        tabla[
            [
                "StockERP",
                "StockWMSResumen",
            ]
        ]
        .abs()
        .max(axis=1)
        .sum()
    )

    integridad_ok = int(
        tabla["IntegridadWMS"]
        .eq("Coincide")
        .sum()
    )

    return {
        "codigos": codigos,
        "conciliados": conciliados,
        "con_diferencia": con_diferencia,
        "exactitud_codigos": (
            conciliados / codigos * 100
            if codigos
            else 0.0
        ),
        "exactitud_unidades": (
            max(
                0.0,
                (
                    1
                    - diferencia_absoluta
                    / referencia
                )
                * 100,
            )
            if referencia
            else 100.0
        ),
        "diferencia_absoluta": diferencia_absoluta,
        "diferencia_neta": float(
            tabla["DiferenciaERPvsWMS"].sum()
        ),
        "integridad_wms": (
            integridad_ok / codigos * 100
            if codigos
            else 0.0
        ),
        "codigos_integridad_wms": int(
            tabla["IntegridadWMS"]
            .ne("Coincide")
            .sum()
        ),
    }


def resumen_por_categoria(
    tabla: pd.DataFrame,
    columna: str,
    *,
    top: int = 12,
) -> pd.DataFrame:
    if (
        tabla is None
        or tabla.empty
        or columna not in tabla.columns
    ):
        return pd.DataFrame()

    return (
        tabla
        .groupby(
            columna,
            as_index=False,
        )
        .agg(
            Codigos=(
                "ArticuloCodigo",
                "nunique",
            ),
            CodigosConDiferencia=(
                "EstadoConciliacion",
                lambda serie: int(
                    serie.ne("Conciliado").sum()
                ),
            ),
            DiferenciaAbsoluta=(
                "DiferenciaAbsoluta",
                "sum",
            ),
            DiferenciaNeta=(
                "DiferenciaERPvsWMS",
                "sum",
            ),
        )
        .sort_values(
            "DiferenciaAbsoluta",
            ascending=False,
        )
        .head(top)
        .reset_index(drop=True)
    )
