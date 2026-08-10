from __future__ import annotations

import pandas as pd


def consolidar_resultado_articulos(
    items: pd.DataFrame,
    conteos: pd.DataFrame,
    reconteos: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if items is None or items.empty:
        return pd.DataFrame()

    base = items.copy()

    conteos_utiles = (
        conteos[
            [
                "ItemID",
                "CantidadContada",
            ]
        ].copy()
        if conteos is not None
        and not conteos.empty
        else pd.DataFrame(
            columns=[
                "ItemID",
                "CantidadContada",
            ]
        )
    )

    conteos_utiles["CantidadContada"] = (
        pd.to_numeric(
            conteos_utiles["CantidadContada"],
            errors="coerce",
        )
    )

    base = base.merge(
        conteos_utiles,
        on="ItemID",
        how="left",
    )

    if (
        reconteos is not None
        and not reconteos.empty
    ):
        rec = reconteos[
            [
                "ItemID",
                "CantidadRecontada",
            ]
        ].copy()

        rec["CantidadRecontada"] = (
            pd.to_numeric(
                rec["CantidadRecontada"],
                errors="coerce",
            )
        )

        base = base.merge(
            rec,
            on="ItemID",
            how="left",
        )
    else:
        base["CantidadRecontada"] = pd.NA

    base["CantidadFinal"] = (
        base["CantidadRecontada"]
        .where(
            base["CantidadRecontada"].notna(),
            base["CantidadContada"],
        )
    )

    resumen = (
        base.groupby(
            [
                "InventarioID",
                "ArticuloCodigo",
                "ArticuloDescripcion",
            ],
            as_index=False,
        )
        .agg(
            StockERPInicial=(
                "StockERPInicial",
                "first",
            ),
            StockWMSInicial=(
                "StockWMSInicial",
                "first",
            ),
            CantidadContada=(
                "CantidadContada",
                "sum",
            ),
            CantidadFinal=(
                "CantidadFinal",
                "sum",
            ),
            LineasTotales=("ItemID", "size"),
            LineasContadas=(
                "CantidadContada",
                lambda serie: int(
                    serie.notna().sum()
                ),
            ),
            LineasRecontadas=(
                "CantidadRecontada",
                lambda serie: int(
                    serie.notna().sum()
                ),
            ),
        )
    )

    resumen["ConteoCompleto"] = (
        resumen["LineasContadas"]
        .eq(resumen["LineasTotales"])
    )

    resumen["DiferenciaVsERP"] = (
        resumen["CantidadFinal"]
        - pd.to_numeric(
            resumen["StockERPInicial"],
            errors="coerce",
        ).fillna(0)
    )

    resumen["DiferenciaVsWMS"] = (
        resumen["CantidadFinal"]
        - pd.to_numeric(
            resumen["StockWMSInicial"],
            errors="coerce",
        ).fillna(0)
    )

    resumen["EstadoResultado"] = (
        "Pendiente de conteo"
    )

    completo = resumen["ConteoCompleto"]

    resumen.loc[
        completo
        & resumen["DiferenciaVsERP"].eq(0)
        & resumen["DiferenciaVsWMS"].eq(0),
        "EstadoResultado",
    ] = "Coincide"

    resumen.loc[
        completo
        & (
            resumen["DiferenciaVsERP"].ne(0)
            | resumen["DiferenciaVsWMS"].ne(0)
        ),
        "EstadoResultado",
    ] = "Requiere reconteo"

    return resumen
