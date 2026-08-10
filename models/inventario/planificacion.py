from __future__ import annotations

import pandas as pd


PUNTOS_PRIORIDAD = {
    "Crítica": 20,
    "Alta": 14,
    "Media": 8,
    "Baja": 3,
    "Sin acción": 0,
}


def calcular_score_prioridad(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    """
    Score V1 explicable para ordenar candidatos.

    Componentes:
    - diferencia absoluta: hasta 40;
    - diferencia porcentual: hasta 20;
    - cantidad de ubicaciones: hasta 10;
    - integridad WMS: hasta 15;
    - prioridad inicial: hasta 20.
    """

    salida = tabla.copy()

    diferencia_maxima = max(
        float(
            salida["DiferenciaAbsoluta"].max()
        ),
        1.0,
    )

    salida["PuntosDiferencia"] = (
        salida["DiferenciaAbsoluta"]
        .div(diferencia_maxima)
        .mul(40)
        .clip(0, 40)
    )

    salida["PuntosPorcentaje"] = (
        salida["DiferenciaPorcentaje"]
        .div(100)
        .mul(20)
        .clip(0, 20)
    )

    salida["PuntosUbicaciones"] = (
        salida["CantidadUbicaciones"]
        .div(
            max(
                float(
                    salida[
                        "CantidadUbicaciones"
                    ].max()
                ),
                1.0,
            )
        )
        .mul(10)
        .clip(0, 10)
    )

    salida["PuntosIntegridad"] = (
        salida["IntegridadWMS"]
        .ne("Coincide")
        .astype(int)
        .mul(15)
    )

    salida["PuntosPrioridad"] = (
        salida["PrioridadInventario"]
        .map(PUNTOS_PRIORIDAD)
        .fillna(0)
    )

    salida["ScorePrioridad"] = (
        salida[
            [
                "PuntosDiferencia",
                "PuntosPorcentaje",
                "PuntosUbicaciones",
                "PuntosIntegridad",
                "PuntosPrioridad",
            ]
        ]
        .sum(axis=1)
        .round(1)
        .clip(0, 100)
    )

    def motivo(fila: pd.Series) -> str:
        razones = []

        if fila["DiferenciaAbsoluta"] > 0:
            razones.append(
                f"Diferencia {fila['DiferenciaAbsoluta']:.0f} u."
            )

        if fila["DiferenciaPorcentaje"] >= 10:
            razones.append(
                f"{fila['DiferenciaPorcentaje']:.1f}%"
            )

        if fila["CantidadUbicaciones"] > 1:
            razones.append(
                f"{int(fila['CantidadUbicaciones'])} ubicaciones"
            )

        if fila["IntegridadWMS"] != "Coincide":
            razones.append("Integridad WMS")

        if not razones:
            razones.append("Conteo preventivo")

        return " · ".join(razones)

    salida["MotivoPrioridad"] = salida.apply(
        motivo,
        axis=1,
    )

    return salida.sort_values(
        [
            "ScorePrioridad",
            "DiferenciaAbsoluta",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)


def construir_items_plan(
    articulos: pd.DataFrame,
    detalle_ubicaciones: pd.DataFrame,
) -> pd.DataFrame:
    """
    Expande los artículos seleccionados a una fila por ubicación.
    """

    columnas_articulo = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "GrupoInventario",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "StockERP",
        "StockWMSResumen",
        "DiferenciaERPvsWMS",
        "PrioridadInventario",
        "ScorePrioridad",
        "MotivoPrioridad",
    ]

    articulos_base = articulos[
        [
            columna
            for columna in columnas_articulo
            if columna in articulos.columns
        ]
    ].copy()

    detalle = detalle_ubicaciones.copy()

    columnas_detalle = [
        "ArticuloCodigo",
        "Ubicacion",
        "Contenedor",
        "Cantidad",
        "FuenteDetalle",
        "TipoUbicacion",
        "AreaUbicacion",
        "PasilloUbicacion",
    ]

    for columna in columnas_detalle:
        if columna not in detalle.columns:
            detalle[columna] = ""

    detalle = detalle[columnas_detalle].copy()

    items = articulos_base.merge(
        detalle,
        on="ArticuloCodigo",
        how="left",
    )

    items["Ubicacion"] = (
        items["Ubicacion"]
        .fillna("")
        .replace("", "SIN UBICACIÓN")
    )
    items["Contenedor"] = (
        items["Contenedor"]
        .fillna("")
    )
    items["FuenteDetalle"] = (
        items["FuenteDetalle"]
        .fillna("")
    )
    items["Cantidad"] = pd.to_numeric(
        items["Cantidad"],
        errors="coerce",
    ).fillna(0)

    items = items.sort_values(
        [
            "ScorePrioridad",
            "ArticuloCodigo",
            "Ubicacion",
        ],
        ascending=[
            False,
            True,
            True,
        ],
    ).reset_index(drop=True)

    items["OrdenConteo"] = (
        items.index + 1
    )

    return items
