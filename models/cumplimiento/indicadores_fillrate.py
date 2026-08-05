from __future__ import annotations

import numpy as np
import pandas as pd

CIRCUITOS_FILL_RATE = ("ZONA", "EXPRESO", "RETIRA", "DIARIO", "CON TURNO")


def calcular_fill_rate(tabla: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Calcula Fill Rate operativo por pedido.

    Denominador: unidades pedidas en Filtrar Preparación.
    Numerador: unidades controladas hasta el cierre del mismo mes en que
    ingresó el pedido. Los controles de meses posteriores se conservan para
    auditoría, pero no mejoran retroactivamente el Fill Rate de la cohorte.
    """
    if tabla is None or tabla.empty:
        return pd.DataFrame(), {
            "pedidos_evaluados": 0,
            "unidades_pedidas": 0.0,
            "unidades_controladas": 0.0,
            "unidades_faltantes": 0.0,
            "fill_rate_pct": 0.0,
        }

    salida = tabla.copy()
    salida["UnidadesPedidas"] = pd.to_numeric(
        salida.get("UnidadesPedidas", 0), errors="coerce"
    ).fillna(0).clip(lower=0)
    salida["UnidadesControladasRaw"] = pd.to_numeric(
        salida.get("UnidadesControladasCierreMes", 0), errors="coerce"
    ).fillna(0).clip(lower=0)
    salida["UnidadesControladasPosteriores"] = pd.to_numeric(
        salida.get("UnidadesControladasPosteriores", 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    salida["UnidadesControladasFillRate"] = np.minimum(
        salida["UnidadesControladasRaw"], salida["UnidadesPedidas"]
    )
    salida["UnidadesFaltantesFillRate"] = (
        salida["UnidadesPedidas"] - salida["UnidadesControladasFillRate"]
    ).clip(lower=0)
    salida["AplicaFillRate"] = salida["UnidadesPedidas"].gt(0)
    salida["FillRatePedidoPct"] = np.where(
        salida["AplicaFillRate"],
        salida["UnidadesControladasFillRate"]
        .div(salida["UnidadesPedidas"].replace(0, np.nan))
        .mul(100),
        np.nan,
    )
    salida["PedidoCompletoUnidades"] = (
        salida["AplicaFillRate"] & salida["UnidadesFaltantesFillRate"].le(0)
    )

    base = salida.loc[salida["AplicaFillRate"]].copy()
    pedidas = float(base["UnidadesPedidas"].sum())
    controladas = float(base["UnidadesControladasFillRate"].sum())
    faltantes = max(pedidas - controladas, 0.0)

    diagnostico = {
        "pedidos_evaluados": int(base["Pedido"].nunique()) if "Pedido" in base else len(base),
        "pedidos_completos": int(base["PedidoCompletoUnidades"].sum()),
        "unidades_pedidas": pedidas,
        "unidades_controladas": controladas,
        "unidades_faltantes": faltantes,
        "fill_rate_pct": controladas / pedidas * 100 if pedidas > 0 else 0.0,
        "pedidos_sin_unidades_pedidas": int((~salida["AplicaFillRate"]).sum()),
        "unidades_controladas_posteriores": float(
            base["UnidadesControladasPosteriores"].sum()
        ),
        "pedidos_completados_posteriormente": int(
            base.get(
                "EstadoCierreFillRate",
                pd.Series("", index=base.index),
            ).eq("COMPLETADO EN MES POSTERIOR").sum()
        ),
    }
    return salida, diagnostico


def resumir_fill_rate(tabla: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    if tabla is None or tabla.empty:
        return pd.DataFrame()
    base = tabla.loc[tabla.get("AplicaFillRate", False)].copy()
    if base.empty:
        return pd.DataFrame()
    resumen = (
        base.groupby(columnas, dropna=False, as_index=False)
        .agg(
            Pedidos=("Pedido", "nunique"),
            UnidadesPedidas=("UnidadesPedidas", "sum"),
            UnidadesControladas=("UnidadesControladasFillRate", "sum"),
            UnidadesFaltantes=("UnidadesFaltantesFillRate", "sum"),
        )
    )
    resumen["FillRatePct"] = (
        resumen["UnidadesControladas"]
        .div(resumen["UnidadesPedidas"].replace(0, np.nan))
        .mul(100)
        .fillna(0)
    )
    return resumen
