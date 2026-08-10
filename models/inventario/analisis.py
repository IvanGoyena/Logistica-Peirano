from __future__ import annotations

import numpy as np
import pandas as pd

from models.inventario.conteos import (
    consolidar_resultado_articulos,
)


def convertir_numeros(
    dataframe: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    salida = dataframe.copy()

    for columna in columnas:
        if columna not in salida.columns:
            salida[columna] = 0

        salida[columna] = pd.to_numeric(
            salida[columna],
            errors="coerce",
        )

    return salida


def construir_resultado_inventario(
    *,
    inventario_id: str,
    items: pd.DataFrame,
    conteos: pd.DataFrame,
    reconteos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve:
    - resultado consolidado por artículo;
    - detalle por ubicación con conteo/reconteo.
    """

    items_plan = items.loc[
        items["InventarioID"]
        .astype(str)
        .eq(str(inventario_id))
    ].copy()

    conteos_plan = conteos.loc[
        conteos["InventarioID"]
        .astype(str)
        .eq(str(inventario_id))
    ].copy()

    reconteos_plan = reconteos.loc[
        reconteos["InventarioID"]
        .astype(str)
        .eq(str(inventario_id))
    ].copy()

    resultado = consolidar_resultado_articulos(
        items_plan,
        conteos_plan,
        reconteos_plan,
    )

    if resultado.empty:
        return resultado, items_plan

    resultado = convertir_numeros(
        resultado,
        [
            "StockERPInicial",
            "StockWMSInicial",
            "CantidadContada",
            "CantidadFinal",
            "DiferenciaVsERP",
            "DiferenciaVsWMS",
            "LineasTotales",
            "LineasContadas",
            "LineasRecontadas",
        ],
    )

    resultado["DiferenciaAbsolutaERP"] = (
        resultado["DiferenciaVsERP"].abs()
    )
    resultado["DiferenciaAbsolutaWMS"] = (
        resultado["DiferenciaVsWMS"].abs()
    )

    base_porcentaje = (
        resultado["StockWMSInicial"]
        .abs()
        .replace(0, np.nan)
    )

    porcentaje_calculado = (
        resultado["DiferenciaAbsolutaWMS"]
        .div(base_porcentaje)
        .mul(100)
    )

    porcentaje_sin_base = pd.Series(
        np.where(
            resultado[
                "DiferenciaAbsolutaWMS"
            ].eq(0),
            0.0,
            100.0,
        ),
        index=resultado.index,
        dtype="float64",
    )

    resultado["DiferenciaPorcentaje"] = (
        porcentaje_calculado
        .fillna(porcentaje_sin_base)
        .round(2)
    )

    resultado["ClasificacionResultado"] = (
        "Pendiente"
    )

    completo = resultado["ConteoCompleto"]

    resultado.loc[
        completo
        & resultado[
            "DiferenciaAbsolutaWMS"
        ].eq(0),
        "ClasificacionResultado",
    ] = "Correcto"

    resultado.loc[
        completo
        & resultado[
            "DiferenciaAbsolutaWMS"
        ].between(1, 2),
        "ClasificacionResultado",
    ] = "Diferencia menor"

    resultado.loc[
        completo
        & resultado[
            "DiferenciaAbsolutaWMS"
        ].between(3, 10),
        "ClasificacionResultado",
    ] = "Recontar"

    resultado.loc[
        completo
        & resultado[
            "DiferenciaAbsolutaWMS"
        ].gt(10),
        "ClasificacionResultado",
    ] = "Diferencia crítica"

    resultado["PrioridadAnalisis"] = "Baja"

    resultado.loc[
        resultado[
            "ClasificacionResultado"
        ].eq("Diferencia menor"),
        "PrioridadAnalisis",
    ] = "Media"

    resultado.loc[
        resultado[
            "ClasificacionResultado"
        ].eq("Recontar"),
        "PrioridadAnalisis",
    ] = "Alta"

    resultado.loc[
        resultado[
            "ClasificacionResultado"
        ].eq("Diferencia crítica"),
        "PrioridadAnalisis",
    ] = "Crítica"

    columnas_item = [
        "ItemID",
        "InventarioID",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "GrupoInventario",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Ubicacion",
        "Contenedor",
        "CantidadSistemaUbicacion",
        "StockERPInicial",
        "StockWMSInicial",
        "DiferenciaInicial",
        "PrioridadInicial",
        "ScorePrioridad",
        "MotivoPrioridad",
        "EstadoItem",
        "OrdenConteo",
    ]

    detalle = items_plan[
        [
            columna
            for columna in columnas_item
            if columna in items_plan.columns
        ]
    ].copy()

    columnas_conteo = [
        "ItemID",
        "CantidadContada",
        "UsuarioConteo",
        "UsuarioConteoNombre",
        "FechaConteo",
        "Observacion",
        "OrigenConteo",
        "ArchivoOrigen",
        "CantidadFotoUnidades",
        "DiferenciaArchivo",
        "FotoPertenece",
    ]

    if not conteos_plan.empty:
        detalle = detalle.merge(
            conteos_plan[
                [
                    columna
                    for columna in columnas_conteo
                    if columna
                    in conteos_plan.columns
                ]
            ],
            on="ItemID",
            how="left",
        )
    else:
        detalle["CantidadContada"] = pd.NA

    columnas_reconteo = [
        "ItemID",
        "CantidadRecontada",
        "UsuarioReconteo",
        "UsuarioReconteoNombre",
        "FechaReconteo",
        "Observacion",
    ]

    if not reconteos_plan.empty:
        rec = reconteos_plan[
            [
                columna
                for columna in columnas_reconteo
                if columna
                in reconteos_plan.columns
            ]
        ].copy()

        if "Observacion" in rec.columns:
            rec = rec.rename(
                columns={
                    "Observacion": (
                        "ObservacionReconteo"
                    )
                }
            )

        detalle = detalle.merge(
            rec,
            on="ItemID",
            how="left",
        )
    else:
        detalle["CantidadRecontada"] = pd.NA

    detalle = convertir_numeros(
        detalle,
        [
            "CantidadSistemaUbicacion",
            "CantidadContada",
            "CantidadRecontada",
        ],
    )

    detalle["CantidadFinalUbicacion"] = (
        detalle["CantidadRecontada"]
        .where(
            detalle[
                "CantidadRecontada"
            ].notna(),
            detalle["CantidadContada"],
        )
    )

    detalle["DiferenciaUbicacion"] = (
        detalle["CantidadFinalUbicacion"]
        - detalle[
            "CantidadSistemaUbicacion"
        ]
    )

    detalle["EstadoUbicacion"] = "Pendiente"
    detalle.loc[
        detalle[
            "CantidadFinalUbicacion"
        ].notna()
        & detalle[
            "DiferenciaUbicacion"
        ].eq(0),
        "EstadoUbicacion",
    ] = "Correcta"
    detalle.loc[
        detalle[
            "CantidadFinalUbicacion"
        ].notna()
        & detalle[
            "DiferenciaUbicacion"
        ].ne(0),
        "EstadoUbicacion",
    ] = "Con diferencia"

    return (
        resultado.sort_values(
            [
                "DiferenciaAbsolutaWMS",
                "DiferenciaPorcentaje",
            ],
            ascending=False,
        ).reset_index(drop=True),
        detalle.sort_values(
            [
                "ArticuloCodigo",
                "OrdenConteo",
            ]
        ).reset_index(drop=True),
    )


def calcular_kpis_resultado(
    resultado: pd.DataFrame,
    detalle: pd.DataFrame,
) -> dict[str, float | int]:
    if resultado is None or resultado.empty:
        return {
            "articulos": 0,
            "ubicaciones": 0,
            "ubicaciones_contadas": 0,
            "avance": 0.0,
            "articulos_correctos": 0,
            "articulos_diferencia": 0,
            "exactitud_articulos": 0.0,
            "exactitud_ubicaciones": 0.0,
            "diferencia_neta": 0.0,
            "diferencia_absoluta": 0.0,
            "reconteos": 0,
        }

    articulos = len(resultado)
    ubicaciones = len(detalle)
    ubicaciones_contadas = int(
        detalle[
            "CantidadFinalUbicacion"
        ].notna().sum()
        if "CantidadFinalUbicacion"
        in detalle.columns
        else 0
    )

    correctos = int(
        resultado[
            "ClasificacionResultado"
        ].eq("Correcto").sum()
    )

    diferencias = int(
        resultado[
            "ClasificacionResultado"
        ].isin(
            [
                "Diferencia menor",
                "Recontar",
                "Diferencia crítica",
            ]
        ).sum()
    )

    ubicaciones_correctas = int(
        detalle[
            "EstadoUbicacion"
        ].eq("Correcta").sum()
        if "EstadoUbicacion"
        in detalle.columns
        else 0
    )

    return {
        "articulos": articulos,
        "ubicaciones": ubicaciones,
        "ubicaciones_contadas": (
            ubicaciones_contadas
        ),
        "avance": (
            ubicaciones_contadas
            / ubicaciones
            * 100
            if ubicaciones
            else 0
        ),
        "articulos_correctos": correctos,
        "articulos_diferencia": diferencias,
        "exactitud_articulos": (
            correctos / articulos * 100
            if articulos
            else 0
        ),
        "exactitud_ubicaciones": (
            ubicaciones_correctas
            / ubicaciones_contadas
            * 100
            if ubicaciones_contadas
            else 0
        ),
        "diferencia_neta": float(
            resultado[
                "DiferenciaVsWMS"
            ].sum()
        ),
        "diferencia_absoluta": float(
            resultado[
                "DiferenciaAbsolutaWMS"
            ].sum()
        ),
        "reconteos": int(
            resultado[
                "ClasificacionResultado"
            ].isin(
                [
                    "Recontar",
                    "Diferencia crítica",
                ]
            ).sum()
        ),
    }


def construir_productividad(
    detalle: pd.DataFrame,
) -> pd.DataFrame:
    if (
        detalle is None
        or detalle.empty
        or "UsuarioConteoNombre"
        not in detalle.columns
    ):
        return pd.DataFrame()

    base = detalle.loc[
        detalle[
            "CantidadContada"
        ].notna()
    ].copy()

    if base.empty:
        return pd.DataFrame()

    base["UsuarioVisible"] = (
        base["UsuarioConteoNombre"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    base["UsuarioVisible"] = (
        base["UsuarioVisible"]
        .where(
            base["UsuarioVisible"].ne(""),
            base.get(
                "UsuarioConteo",
                pd.Series(
                    "Sin identificar",
                    index=base.index,
                ),
            ),
        )
    )

    base["EsCorrecta"] = (
        base["DiferenciaUbicacion"].eq(0)
    )

    return (
        base.groupby(
            "UsuarioVisible",
            as_index=False,
        )
        .agg(
            Ubicaciones=(
                "ItemID",
                "nunique",
            ),
            Articulos=(
                "ArticuloCodigo",
                "nunique",
            ),
            UnidadesContadas=(
                "CantidadContada",
                "sum",
            ),
            UbicacionesCorrectas=(
                "EsCorrecta",
                "sum",
            ),
        )
        .assign(
            Exactitud=lambda tabla: (
                tabla[
                    "UbicacionesCorrectas"
                ]
                .div(
                    tabla[
                        "Ubicaciones"
                    ].replace(0, np.nan)
                )
                .mul(100)
                .fillna(0)
                .round(2)
            )
        )
        .sort_values(
            [
                "Ubicaciones",
                "Exactitud",
            ],
            ascending=False,
        )
        .reset_index(drop=True)
    )


def resumen_planes(
    planes: pd.DataFrame,
    items: pd.DataFrame,
    conteos: pd.DataFrame,
) -> pd.DataFrame:
    if planes is None or planes.empty:
        return pd.DataFrame()

    salida = planes.copy()

    total_items = (
        items.groupby(
            "InventarioID"
        )["ItemID"]
        .nunique()
        .rename("ItemsTotales")
        if items is not None
        and not items.empty
        else pd.Series(dtype=float)
    )

    items_contados = (
        conteos.groupby(
            "InventarioID"
        )["ItemID"]
        .nunique()
        .rename("ItemsContados")
        if conteos is not None
        and not conteos.empty
        else pd.Series(dtype=float)
    )

    salida = salida.merge(
        total_items,
        on="InventarioID",
        how="left",
    )
    salida = salida.merge(
        items_contados,
        on="InventarioID",
        how="left",
    )

    salida[
        [
            "ItemsTotales",
            "ItemsContados",
        ]
    ] = (
        salida[
            [
                "ItemsTotales",
                "ItemsContados",
            ]
        ]
        .fillna(0)
        .apply(
            pd.to_numeric,
            errors="coerce",
        )
        .fillna(0)
    )

    salida["AvancePorcentaje"] = (
        salida["ItemsContados"]
        .div(
            salida[
                "ItemsTotales"
            ].replace(0, np.nan)
        )
        .mul(100)
        .fillna(0)
        .round(1)
    )

    return salida
