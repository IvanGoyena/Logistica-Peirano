from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from models.inventario.analisis import (
    calcular_kpis_resultado,
    construir_productividad,
    construir_resultado_inventario,
)
from utils.exportaciones import (
    dataframe_a_csv_limpio,
)
from utils.inventario.persistencia import (
    leer_conteos,
    leer_items,
    leer_planes,
    leer_reconteos,
)


def render_analisis_diferencias() -> None:
    st.subheader(
        "🔍 Análisis de diferencias"
    )
    st.caption(
        "Comparación entre ERP, WMS y el conteo "
        "físico importado."
    )

    planes = leer_planes()

    if planes.empty:
        st.info(
            "No existen inventarios guardados."
        )
        return

    inventario_id = st.selectbox(
        "Inventario",
        options=planes[
            "InventarioID"
        ].astype(str).tolist(),
        format_func=lambda valor: (
            f"{valor} · "
            f"{planes.loc[
                planes['InventarioID']
                .astype(str).eq(valor),
                'Estado'
            ].iloc[0]}"
        ),
        key="analisis_inventario_id",
    )

    items = leer_items()
    conteos = leer_conteos()
    reconteos = leer_reconteos()

    resultado, detalle = (
        construir_resultado_inventario(
            inventario_id=inventario_id,
            items=items,
            conteos=conteos,
            reconteos=reconteos,
        )
    )

    if resultado.empty:
        st.info(
            "El inventario todavía no tiene "
            "resultados para analizar."
        )
        return

    kpis = calcular_kpis_resultado(
        resultado,
        detalle,
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Correctos",
        kpis["articulos_correctos"],
    )
    k2.metric(
        "Con diferencia",
        kpis["articulos_diferencia"],
    )
    k3.metric(
        "Diferencia absoluta",
        f"{kpis['diferencia_absoluta']:,.0f}"
        .replace(",", "."),
        "unidades",
    )
    k4.metric(
        "Reconteos",
        kpis["reconteos"],
    )

    f1, f2, f3 = st.columns(3)

    with f1:
        clasificaciones = st.multiselect(
            "Resultado",
            options=sorted(
                resultado[
                    "ClasificacionResultado"
                ].dropna().unique()
            ),
            default=[
                valor
                for valor in [
                    "Diferencia menor",
                    "Recontar",
                    "Diferencia crítica",
                ]
                if valor in set(
                    resultado[
                        "ClasificacionResultado"
                    ]
                )
            ],
        )

    with f2:
        prioridad = st.multiselect(
            "Prioridad",
            options=sorted(
                resultado[
                    "PrioridadAnalisis"
                ].dropna().unique()
            ),
        )

    with f3:
        busqueda = st.text_input(
            "Buscar artículo",
            placeholder="Código o descripción",
        )

    visual = resultado.copy()

    if clasificaciones:
        visual = visual.loc[
            visual[
                "ClasificacionResultado"
            ].isin(clasificaciones)
        ]

    if prioridad:
        visual = visual.loc[
            visual[
                "PrioridadAnalisis"
            ].isin(prioridad)
        ]

    if busqueda.strip():
        patron = busqueda.strip().lower()
        visual = visual.loc[
            visual[
                "ArticuloCodigo"
            ].astype(str).str.lower().str.contains(
                patron,
                na=False,
            )
            | visual[
                "ArticuloDescripcion"
            ].astype(str).str.lower().str.contains(
                patron,
                na=False,
            )
        ]

    columnas_tabla = [
        "PrioridadAnalisis",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "StockERPInicial",
        "StockWMSInicial",
        "CantidadContada",
        "CantidadFinal",
        "DiferenciaVsERP",
        "DiferenciaVsWMS",
        "DiferenciaPorcentaje",
        "ClasificacionResultado",
        "LineasTotales",
        "LineasContadas",
        "LineasRecontadas",
    ]

    st.dataframe(
        visual[
            [
                columna
                for columna in columnas_tabla
                if columna in visual.columns
            ]
        ],
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "DiferenciaPorcentaje": (
                st.column_config.NumberColumn(
                    "Diferencia %",
                    format="%.2f %%",
                )
            ),
        },
    )

    if visual.empty:
        st.warning(
            "No hay resultados con los filtros actuales."
        )
        return

    articulo = st.selectbox(
        "Abrir ficha del artículo",
        options=visual[
            "ArticuloCodigo"
        ].astype(str).tolist(),
        format_func=lambda codigo: (
            f"{codigo} — "
            f"{visual.loc[
                visual['ArticuloCodigo']
                .astype(str).eq(codigo),
                'ArticuloDescripcion'
            ].iloc[0]}"
        ),
    )

    ficha = visual.loc[
        visual["ArticuloCodigo"]
        .astype(str).eq(articulo)
    ].iloc[0]

    st.markdown(
        f"### {articulo} — "
        f"{ficha['ArticuloDescripcion']}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "ERP inicial",
        f"{ficha['StockERPInicial']:,.0f}"
        .replace(",", "."),
    )
    c2.metric(
        "WMS inicial",
        f"{ficha['StockWMSInicial']:,.0f}"
        .replace(",", "."),
    )
    c3.metric(
        "Conteo final",
        f"{ficha['CantidadFinal']:,.0f}"
        .replace(",", "."),
    )
    c4.metric(
        "Diferencia vs WMS",
        f"{ficha['DiferenciaVsWMS']:,.0f}"
        .replace(",", "."),
    )

    detalle_articulo = detalle.loc[
        detalle["ArticuloCodigo"]
        .astype(str).eq(articulo)
    ].copy()

    if not detalle_articulo.empty:
        st.markdown(
            "#### Resultado por ubicación"
        )

        columnas_detalle = [
            "Ubicacion",
            "Contenedor",
            "CantidadSistemaUbicacion",
            "CantidadContada",
            "CantidadRecontada",
            "CantidadFinalUbicacion",
            "DiferenciaUbicacion",
            "EstadoUbicacion",
            "UsuarioConteoNombre",
            "FechaConteo",
            "OrigenConteo",
            "ArchivoOrigen",
        ]

        st.dataframe(
            detalle_articulo[
                [
                    columna
                    for columna in columnas_detalle
                    if columna
                    in detalle_articulo.columns
                ]
            ],
            hide_index=True,
            width="stretch",
            height=350,
        )

        grafico = (
            detalle_articulo[
                [
                    "Ubicacion",
                    "DiferenciaUbicacion",
                ]
            ]
            .dropna()
        )

        if not grafico.empty:
            chart = (
                alt.Chart(grafico)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "DiferenciaUbicacion:Q",
                        title="Diferencia",
                    ),
                    y=alt.Y(
                        "Ubicacion:N",
                        sort="-x",
                        title=None,
                    ),
                    tooltip=[
                        "Ubicacion:N",
                        "DiferenciaUbicacion:Q",
                    ],
                )
                .properties(
                    height=min(
                        max(
                            len(grafico) * 28,
                            180,
                        ),
                        500,
                    )
                )
            )

            st.altair_chart(
                chart,
                width="stretch",
            )

    productividad = construir_productividad(
        detalle
    )

    with st.expander(
        "👷 Productividad del inventario",
        expanded=False,
    ):
        if productividad.empty:
            st.info(
                "No hay usuarios de relevamiento "
                "para mostrar."
            )
        else:
            st.dataframe(
                productividad,
                hide_index=True,
                width="stretch",
            )

    d1, d2 = st.columns(2)

    with d1:
        st.download_button(
            "⬇️ Descargar resumen analítico",
            data=dataframe_a_csv_limpio(
                resultado
            ),
            file_name=(
                f"{inventario_id}_analisis.csv"
            ),
            mime="text/csv",
            width="stretch",
        )

    with d2:
        st.download_button(
            "⬇️ Descargar detalle por ubicación",
            data=dataframe_a_csv_limpio(
                detalle
            ),
            file_name=(
                f"{inventario_id}_ubicaciones.csv"
            ),
            mime="text/csv",
            width="stretch",
        )
