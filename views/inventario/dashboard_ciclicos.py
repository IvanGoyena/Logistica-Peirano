from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from models.inventario.analisis import (
    calcular_kpis_resultado,
    construir_productividad,
    construir_resultado_inventario,
    resumen_planes,
)
from utils.inventario.persistencia import (
    leer_conteos,
    leer_items,
    leer_planes,
    leer_reconteos,
    leer_acciones,
)


def _porcentaje(valor: float) -> str:
    return f"{valor:,.1f}%".replace(
        ",",
        "X",
    ).replace(
        ".",
        ",",
    ).replace(
        "X",
        ".",
    )


def _entero(valor: float | int) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def render_dashboard_ciclicos() -> None:
    st.subheader(
        "📊 Dashboard de inventarios"
    )
    st.caption(
        "Estado operativo y resultados de los "
        "inventarios cíclicos guardados."
    )

    planes = leer_planes()
    items = leer_items()
    conteos = leer_conteos()
    reconteos = leer_reconteos()
    acciones = leer_acciones()

    if planes.empty:
        st.info(
            "Todavía no existen inventarios para analizar."
        )
        return

    resumen = resumen_planes(
        planes,
        items,
        conteos,
    )

    activos = resumen.loc[
        ~resumen["Estado"].isin(
            [
                "Cerrado",
                "Cancelado",
            ]
        )
    ]

    pendientes_accion = 0 if acciones.empty else int((~acciones["EstadoAccion"].isin(["Verificada","Descartada"])).sum())
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Inventarios totales",
        _entero(len(resumen)),
    )
    k2.metric(
        "Inventarios activos",
        _entero(len(activos)),
    )
    k3.metric(
        "Ubicaciones planificadas",
        _entero(
            resumen["ItemsTotales"].sum()
        ),
    )
    k4.metric(
        "Ubicaciones contadas",
        _entero(resumen["ItemsContados"].sum()),
    )
    k5.metric("Acciones pendientes", _entero(pendientes_accion))

    opciones = resumen[
        "InventarioID"
    ].astype(str).tolist()

    inventario_default = (
        activos["InventarioID"]
        .astype(str)
        .iloc[0]
        if not activos.empty
        else opciones[-1]
    )

    inventario_id = st.selectbox(
        "Inventario analizado",
        options=opciones,
        index=opciones.index(
            inventario_default
        ),
        format_func=lambda valor: (
            f"{valor} · "
            f"{resumen.loc[
                resumen['InventarioID']
                .astype(str).eq(valor),
                'Estado'
            ].iloc[0]}"
        ),
        key="dashboard_inventario_id",
    )

    plan = resumen.loc[
        resumen["InventarioID"]
        .astype(str)
        .eq(inventario_id)
    ].iloc[0]

    resultado, detalle = (
        construir_resultado_inventario(
            inventario_id=inventario_id,
            items=items,
            conteos=conteos,
            reconteos=reconteos,
        )
    )

    kpis = calcular_kpis_resultado(
        resultado,
        detalle,
    )

    st.markdown(
        f"### {inventario_id}"
    )
    st.caption(
        f"Estado: {plan['Estado']} · "
        f"Responsable: "
        f"{plan.get('ResponsableNombre', '')} · "
        f"Fecha planificada: "
        f"{plan.get('FechaPlanificada', '')}"
    )

    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric(
        "Avance",
        _porcentaje(kpis["avance"]),
        f"{kpis['ubicaciones_contadas']} / "
        f"{kpis['ubicaciones']} ubicaciones",
    )
    a2.metric(
        "Exactitud artículos",
        _porcentaje(
            kpis["exactitud_articulos"]
        ),
        f"{kpis['articulos_correctos']} correctos",
    )
    a3.metric(
        "Exactitud ubicaciones",
        _porcentaje(
            kpis["exactitud_ubicaciones"]
        ),
    )
    a4.metric(
        "Diferencia neta",
        _entero(
            kpis["diferencia_neta"]
        ),
        "unidades vs WMS",
    )
    a5.metric(
        "A recontar",
        _entero(kpis["reconteos"]),
    )

    if resultado.empty:
        st.info(
            "El plan todavía no tiene conteos importados."
        )
        return

    grafico_1, grafico_2 = st.columns(2)

    distribucion = (
        resultado[
            "ClasificacionResultado"
        ]
        .value_counts()
        .rename_axis("Resultado")
        .reset_index(name="Articulos")
    )

    with grafico_1:
        st.markdown(
            "#### Resultado por artículo"
        )

        chart = (
            alt.Chart(distribucion)
            .mark_arc(innerRadius=65)
            .encode(
                theta=alt.Theta(
                    "Articulos:Q"
                ),
                color=alt.Color(
                    "Resultado:N",
                    legend=alt.Legend(
                        orient="bottom",
                    ),
                ),
                tooltip=[
                    "Resultado:N",
                    "Articulos:Q",
                ],
            )
            .properties(height=310)
        )

        st.altair_chart(
            chart,
            width="stretch",
        )

    ranking = (
        resultado.head(15).copy()
    )

    with grafico_2:
        st.markdown(
            "#### Mayores diferencias"
        )

        chart = (
            alt.Chart(ranking)
            .mark_bar()
            .encode(
                x=alt.X(
                    "DiferenciaAbsolutaWMS:Q",
                    title="Diferencia absoluta",
                ),
                y=alt.Y(
                    "ArticuloCodigo:N",
                    sort="-x",
                    title=None,
                ),
                tooltip=[
                    "ArticuloCodigo:N",
                    "ArticuloDescripcion:N",
                    "StockWMSInicial:Q",
                    "CantidadFinal:Q",
                    "DiferenciaVsWMS:Q",
                    "ClasificacionResultado:N",
                ],
            )
            .properties(height=310)
        )

        st.altair_chart(
            chart,
            width="stretch",
        )

    productividad = construir_productividad(
        detalle
    )

    if not productividad.empty:
        st.markdown(
            "#### Productividad por relevador"
        )
        st.dataframe(
            productividad,
            hide_index=True,
            width="stretch",
            column_config={
                "Exactitud": (
                    st.column_config.ProgressColumn(
                        "Exactitud",
                        min_value=0,
                        max_value=100,
                        format="%.1f %%",
                    )
                ),
            },
        )

    st.markdown(
        "#### Estado de todos los planes"
    )

    columnas_planes = [
        "InventarioID",
        "FechaPlanificada",
        "ResponsableNombre",
        "Estado",
        "CantidadArticulos",
        "ItemsTotales",
        "ItemsContados",
        "AvancePorcentaje",
    ]

    st.dataframe(
        resumen[
            [
                columna
                for columna in columnas_planes
                if columna in resumen.columns
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "AvancePorcentaje": (
                st.column_config.ProgressColumn(
                    "Avance",
                    min_value=0,
                    max_value=100,
                    format="%.1f %%",
                )
            ),
        },
    )
