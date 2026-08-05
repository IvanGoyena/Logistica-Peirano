from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from models.stock.ocupacion import mostrar_tarjeta_donut
from utils.stock.helpers import (
    aplicar_busqueda,
    dataframe_a_csv,
    dataframe_para_streamlit,
    formato_entero,
)


def _resumen_donut(
    tabla_ocupacion: pd.DataFrame,
    grupo: str,
) -> dict:
    vacio = {
        "capacidad": 0.0,
        "ocupado": 0.0,
        "libre": 0.0,
        "porcentaje": 0.0,
        "ubicaciones": 0,
        "unidad": "ubicaciones",
    }

    if (
        tabla_ocupacion is None
        or tabla_ocupacion.empty
    ):
        return vacio

    base = tabla_ocupacion.loc[
        tabla_ocupacion[
            "GrupoCalidad"
        ].eq(grupo)
    ]

    if base.empty:
        return vacio

    fila = base.iloc[0]

    return {
        "capacidad": float(
            fila["Capacidad"]
        ),
        "ocupado": float(
            fila["Ocupado"]
        ),
        "libre": float(
            fila["Libre"]
        ),
        "porcentaje": float(
            fila["Porcentaje"]
        ),
        "ubicaciones": int(
            fila["Ubicaciones"]
        ),
        "unidad": (
            "contenedores"
            if fila["Unidad"] == "pallets"
            else "ubicaciones"
        ),
    }


def _fmt_m3(valor: float) -> str:
    return (
        f"{float(valor):,.2f} m³"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _mostrar_tarjetas_kpi(
    indicadores: list[tuple[str, str, str]],
    columnas_por_fila: int = 4,
) -> None:
    """
    Renderiza KPI en tarjetas nativas para no depender del CSS
    cargado por otra pestaña del módulo.
    """
    if not indicadores:
        return

    for inicio in range(
        0,
        len(indicadores),
        columnas_por_fila,
    ):
        fila_indicadores = indicadores[
            inicio: inicio + columnas_por_fila
        ]
        columnas = st.columns(
            columnas_por_fila,
            gap="small",
        )

        for indice, columna in enumerate(
            columnas
        ):
            if indice >= len(
                fila_indicadores
            ):
                continue

            etiqueta, valor, aclaracion = (
                fila_indicadores[indice]
            )

            with columna:
                with st.container(
                    border=True
                ):
                    st.markdown(
                        f"""
                        <div style="
                            min-height:128px;
                            display:flex;
                            flex-direction:column;
                            justify-content:space-between;
                            padding:.05rem .08rem;
                        ">
                            <div style="
                                color:#E5E7EB;
                                font-size:.82rem;
                                font-weight:700;
                                line-height:1.25;
                            ">
                                {etiqueta}
                            </div>
                            <div style="
                                color:#F8FAFC;
                                font-size:1.72rem;
                                font-weight:800;
                                line-height:1.12;
                                margin:.55rem 0 .35rem 0;
                            ">
                                {valor}
                            </div>
                            <div style="
                                color:#7DD3FC;
                                font-size:.72rem;
                                line-height:1.25;
                            ">
                                {aclaracion}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )


def render(
    contexto: dict,
) -> None:
    detalle = contexto.get(
        "tabla_calidad_detallada",
        pd.DataFrame(),
    )
    resumen = contexto.get(
        "tabla_calidad_resumen",
        pd.DataFrame(),
    )
    ocupacion = contexto.get(
        "tabla_ocupacion_calidad",
        pd.DataFrame(),
    )
    resumen_global = contexto.get(
        "resumen_global_calidad",
        {},
    )

    st.subheader(
        "🧪 Calidad y Reproceso"
    )
    st.caption(
        "Mercadería no apta para la venta pendiente de análisis, "
        "reproceso, clasificación o definición."
    )

    if detalle.empty:
        st.warning(
            "El reporte `Stock Calidad Laboratorio` no contiene "
            "registros activos o no pudo vincularse con sus ubicaciones."
        )
        return

    # ------------------------------------------------------
    # FILTROS
    # ------------------------------------------------------
    with st.form(
        "form_filtros_calidad",
        clear_on_submit=False,
        border=True,
    ):
        f1, f2, f3, f4 = st.columns(
            [1.1, 1.1, 1.1, 1.6],
            vertical_alignment="bottom",
        )

        sectores_disponibles = sorted(
            detalle[
                "SectorCalidad"
            ]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )
        familias_disponibles = sorted(
            detalle["Familia"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )
        sectorizaciones = sorted(
            detalle["Sectorizacion"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )

        sectores = f1.multiselect(
            "Condición / sector",
            sectores_disponibles,
            key="calidad_borrador_sectores",
            placeholder="Todos",
        )
        familias = f2.multiselect(
            "Familia",
            familias_disponibles,
            key="calidad_borrador_familias",
            placeholder="Todas",
        )
        sectores_producto = f3.multiselect(
            "Sectorización",
            sectorizaciones,
            key="calidad_borrador_sectorizacion",
            placeholder="Todas",
        )
        busqueda = f4.text_input(
            "Buscar producto",
            key="calidad_borrador_busqueda",
            placeholder=(
                "Código, descripción, contenedor o ubicación..."
            ),
        )

        aplicar, limpiar, _ = st.columns(
            [1, 1, 5]
        )
        aplicar_filtros = aplicar.form_submit_button(
            "✅ Aplicar filtros",
            type="primary",
            width="stretch",
        )
        limpiar_filtros = limpiar.form_submit_button(
            "🧹 Quitar filtros",
            width="stretch",
        )

    defaults = {
        "calidad_aplicado_sectores": [],
        "calidad_aplicado_familias": [],
        "calidad_aplicado_sectorizacion": [],
        "calidad_aplicado_busqueda": "",
    }

    for clave, valor in defaults.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor

    if limpiar_filtros:
        for clave, valor in defaults.items():
            st.session_state[clave] = valor

        for clave in [
            "calidad_borrador_sectores",
            "calidad_borrador_familias",
            "calidad_borrador_sectorizacion",
            "calidad_borrador_busqueda",
        ]:
            st.session_state.pop(
                clave,
                None,
            )

        st.rerun()

    if aplicar_filtros:
        st.session_state[
            "calidad_aplicado_sectores"
        ] = sectores
        st.session_state[
            "calidad_aplicado_familias"
        ] = familias
        st.session_state[
            "calidad_aplicado_sectorizacion"
        ] = sectores_producto
        st.session_state[
            "calidad_aplicado_busqueda"
        ] = busqueda
        st.rerun()

    detalle_filtrado = detalle.copy()

    if st.session_state[
        "calidad_aplicado_sectores"
    ]:
        detalle_filtrado = (
            detalle_filtrado.loc[
                detalle_filtrado[
                    "SectorCalidad"
                ].isin(
                    st.session_state[
                        "calidad_aplicado_sectores"
                    ]
                )
            ].copy()
        )

    if st.session_state[
        "calidad_aplicado_familias"
    ]:
        detalle_filtrado = (
            detalle_filtrado.loc[
                detalle_filtrado[
                    "Familia"
                ].isin(
                    st.session_state[
                        "calidad_aplicado_familias"
                    ]
                )
            ].copy()
        )

    if st.session_state[
        "calidad_aplicado_sectorizacion"
    ]:
        detalle_filtrado = (
            detalle_filtrado.loc[
                detalle_filtrado[
                    "Sectorizacion"
                ].isin(
                    st.session_state[
                        "calidad_aplicado_sectorizacion"
                    ]
                )
            ].copy()
        )

    detalle_filtrado = aplicar_busqueda(
        detalle_filtrado,
        st.session_state[
            "calidad_aplicado_busqueda"
        ],
    )

    if detalle_filtrado.empty:
        st.info(
            "No hay registros para los filtros aplicados."
        )
        return

    # ------------------------------------------------------
    # PANORAMA GENERAL
    # ------------------------------------------------------
    unidades = float(
        detalle_filtrado[
            "Cantidad"
        ].sum()
    )
    sku = int(
        detalle_filtrado[
            "ArticuloCodigo"
        ].nunique()
    )
    contenedores = int(
        detalle_filtrado.loc[
            detalle_filtrado[
                "Contenedor"
            ].ne(""),
            "Contenedor",
        ].nunique()
    )
    ubicaciones = int(
        detalle_filtrado.loc[
            detalle_filtrado[
                "Ubicacion"
            ].ne(""),
            "Ubicacion",
        ].nunique()
    )
    volumen = float(
        detalle_filtrado[
            "VolumenTotalM3"
        ].sum()
    )
    antiguedad = (
        detalle_filtrado[
            "DiasEnCalidad"
        ].dropna().mean()
    )
    criticos = int(
        detalle_filtrado[
            "DiasEnCalidad"
        ].fillna(0).gt(30).sum()
    )
    porcentaje_ocupacion = float(
        resumen_global.get(
            "porcentaje_total",
            0,
        )
    )

    kpis = [
        (
            "📦 Unidades no aptas",
            formato_entero(
                unidades
            ),
            "Stock actualmente en Calidad",
        ),
        (
            "🏷️ SKU afectados",
            formato_entero(
                sku
            ),
            "Artículos distintos",
        ),
        (
            "🧱 Contenedores",
            formato_entero(
                contenedores
            ),
            "Contenedores únicos",
        ),
        (
            "📍 Ubicaciones en uso",
            formato_entero(
                ubicaciones
            ),
            "Posiciones con stock",
        ),
        (
            "📐 Volumen",
            _fmt_m3(
                volumen
            ),
            "Volumen conocido",
        ),
        (
            "⏱️ Antigüedad promedio",
            (
                f"{float(antiguedad):.1f} días"
                .replace(".", ",")
                if pd.notna(antiguedad)
                else "—"
            ),
            "Desde el alta estimada",
        ),
        (
            "🔴 Registros > 30 días",
            formato_entero(
                criticos
            ),
            "Pendientes de revisión",
        ),
        (
            "⚠️ Ocupación Calidad",
            (
                f"{porcentaje_ocupacion:.1f}%"
                .replace(".", ",")
            ),
            "Sin incluir tránsito",
        ),
    ]

    _mostrar_tarjetas_kpi(
        kpis,
        columnas_por_fila=4,
    )

    # ------------------------------------------------------
    # OCUPACIÓN
    # ------------------------------------------------------
    st.markdown(
        "### 🔴 Ocupación de Calidad"
    )
    st.markdown(
        "<hr style='border-color:#DC2626;margin-top:-.55rem'>",
        unsafe_allow_html=True,
    )

    fila_donuts = st.columns(
        [1, 1, 1]
    )

    with fila_donuts[0]:
        mostrar_tarjeta_donut(
            "Laboratorio",
            _resumen_donut(
                ocupacion,
                "Laboratorio",
            ),
            key="calidad_donut_laboratorio",
            color_ocupado="#DC2626",
            color_libre="#FEE2E2",
            icono="🧪",
        )

    with fila_donuts[1]:
        mostrar_tarjeta_donut(
            "Piso Calidad",
            _resumen_donut(
                ocupacion,
                "Piso Calidad",
            ),
            key="calidad_donut_piso",
            color_ocupado="#EF4444",
            color_libre="#FEE2E2",
            icono="📦",
        )

    with fila_donuts[2]:
        mostrar_tarjeta_donut(
            "Racks Calidad",
            _resumen_donut(
                ocupacion,
                "Racks Calidad",
            ),
            key="calidad_donut_racks",
            color_ocupado="#B91C1C",
            color_libre="#FECACA",
            icono="🏗️",
        )

    with st.expander(
        "ℹ️ Metodología de ocupación",
        expanded=False,
    ):
        st.markdown(
            """
            - **Laboratorio:** ubicaciones `LAB-...`, medido por
              contenedores distintos contra la capacidad de pallets.
            - **Piso Calidad:** mercadería de segunda
              (`CAL-002-001-001`) y reproceso pendiente
              (`CAL-003-001-001`), medido por contenedores.
            - **Racks Calidad:** restantes ubicaciones `CAL-...`,
              medidas como ubicaciones ocupadas o vacías.
            - **Tránsito:** `CAL-001-001-001` se muestra en la tabla,
              pero no se incluye en la ocupación consolidada de no aptos.
            """
        )

    # ------------------------------------------------------
    # VISUALES
    # ------------------------------------------------------
    st.markdown(
        "### 📊 Análisis del pendiente"
    )

    col_condicion, col_antiguedad = st.columns(
        [1, 1]
    )

    resumen_condicion = (
        detalle_filtrado.groupby(
            "SectorCalidad",
            as_index=False,
        )
        .agg(
            Unidades=(
                "Cantidad",
                "sum",
            ),
            SKU=(
                "ArticuloCodigo",
                "nunique",
            ),
            Contenedores=(
                "Contenedor",
                lambda serie: serie.loc[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
        )
        .sort_values(
            "Unidades",
            ascending=False,
        )
    )

    with col_condicion:
        st.markdown(
            "#### Unidades por condición"
        )

        grafico_condicion = (
            alt.Chart(
                resumen_condicion
            )
            .mark_bar(
                cornerRadiusEnd=5,
                color="#EF4444",
            )
            .encode(
                x=alt.X(
                    "Unidades:Q",
                    title="Unidades",
                ),
                y=alt.Y(
                    "SectorCalidad:N",
                    title=None,
                    sort="-x",
                ),
                tooltip=[
                    alt.Tooltip(
                        "SectorCalidad:N",
                        title="Condición",
                    ),
                    alt.Tooltip(
                        "Unidades:Q",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "SKU:Q",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "Contenedores:Q",
                        format=",.0f",
                    ),
                ],
            )
            .properties(
                height=340
            )
        )

        st.altair_chart(
            grafico_condicion,
            width="stretch",
        )

    with col_antiguedad:
        st.markdown(
            "#### Antigüedad del stock"
        )

        analisis_antiguedad = (
            detalle_filtrado.copy()
        )
        analisis_antiguedad[
            "RangoAntiguedad"
        ] = pd.cut(
            analisis_antiguedad[
                "DiasEnCalidad"
            ],
            bins=[
                -1,
                7,
                15,
                30,
                60,
                float("inf"),
            ],
            labels=[
                "0 a 7 días",
                "8 a 15 días",
                "16 a 30 días",
                "31 a 60 días",
                "Más de 60 días",
            ],
        )

        resumen_antiguedad = (
            analisis_antiguedad.groupby(
                "RangoAntiguedad",
                observed=False,
                as_index=False,
            )
            .agg(
                Unidades=(
                    "Cantidad",
                    "sum",
                ),
                Registros=(
                    "ClaveRegistroCalidad",
                    "nunique",
                ),
            )
        )

        grafico_antiguedad = (
            alt.Chart(
                resumen_antiguedad
            )
            .mark_bar(
                cornerRadiusTopLeft=5,
                cornerRadiusTopRight=5,
            )
            .encode(
                x=alt.X(
                    "RangoAntiguedad:N",
                    title=None,
                    sort=[
                        "0 a 7 días",
                        "8 a 15 días",
                        "16 a 30 días",
                        "31 a 60 días",
                        "Más de 60 días",
                    ],
                    axis=alt.Axis(
                        labelAngle=0,
                    ),
                ),
                y=alt.Y(
                    "Unidades:Q",
                    title="Unidades",
                ),
                color=alt.Color(
                    "RangoAntiguedad:N",
                    legend=None,
                    scale=alt.Scale(
                        range=[
                            "#FCA5A5",
                            "#FB7185",
                            "#EF4444",
                            "#DC2626",
                            "#7F1D1D",
                        ]
                    ),
                ),
                tooltip=[
                    alt.Tooltip(
                        "RangoAntiguedad:N",
                        title="Antigüedad",
                    ),
                    alt.Tooltip(
                        "Unidades:Q",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "Registros:Q",
                        format=",.0f",
                    ),
                ],
            )
            .properties(
                height=340
            )
        )

        st.altair_chart(
            grafico_antiguedad,
            width="stretch",
        )

    # ------------------------------------------------------
    # TABLA RESUMEN
    # ------------------------------------------------------
    st.markdown(
        "### 📋 Stock no apto por artículo"
    )

    resumen_filtrado = (
        detalle_filtrado.groupby(
            [
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Familia2",
                "Sectorizacion",
                "SectorCalidad",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Unidades=(
                "Cantidad",
                "sum",
            ),
            Contenedores=(
                "Contenedor",
                lambda serie: serie.loc[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            Ubicaciones=(
                "Ubicacion",
                lambda serie: serie.loc[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            VolumenTotalM3=(
                "VolumenTotalM3",
                "sum",
            ),
            DiasEnCalidad=(
                "DiasEnCalidad",
                "max",
            ),
            FechaIngresoEstimada=(
                "FechaIngresoEstimada",
                "min",
            ),
        )
        .sort_values(
            [
                "DiasEnCalidad",
                "Unidades",
            ],
            ascending=[
                False,
                False,
            ],
            na_position="last",
        )
    )

    descargar, texto = st.columns(
        [1, 4],
        vertical_alignment="center",
    )

    descargar.download_button(
        "⬇️ Descargar resumen",
        data=dataframe_a_csv(
            resumen_filtrado
        ),
        file_name=(
            "Stock_Calidad_Reproceso.csv"
        ),
        mime="text/csv",
        width="stretch",
    )
    texto.caption(
        "La fecha de ingreso es estimada utilizando la vida "
        "estándar de 2.000 días."
    )

    st.dataframe(
        dataframe_para_streamlit(
            resumen_filtrado
        ),
        hide_index=True,
        width="stretch",
        height=460,
        column_config={
            "ArticuloCodigo":
                st.column_config.TextColumn(
                    "Código",
                ),
            "ArticuloDescripcion":
                st.column_config.TextColumn(
                    "Descripción",
                    width="large",
                ),
            "SectorCalidad":
                st.column_config.TextColumn(
                    "Condición",
                    width="medium",
                ),
            "Unidades":
                st.column_config.NumberColumn(
                    "Unidades",
                    format="%.0f",
                ),
            "Contenedores":
                st.column_config.NumberColumn(
                    "Contenedores",
                    format="%d",
                ),
            "Ubicaciones":
                st.column_config.NumberColumn(
                    "Ubicaciones",
                    format="%d",
                ),
            "VolumenTotalM3":
                st.column_config.NumberColumn(
                    "Volumen m³",
                    format="%.3f",
                ),
            "DiasEnCalidad":
                st.column_config.NumberColumn(
                    "Días en Calidad",
                    format="%d",
                ),
            "FechaIngresoEstimada":
                st.column_config.DateColumn(
                    "Ingreso estimado",
                    format="DD/MM/YYYY",
                ),
        },
    )

    # ------------------------------------------------------
    # DETALLE BAJO DEMANDA
    # ------------------------------------------------------
    st.markdown(
        "### 🔎 Detalle operativo"
    )

    opciones = (
        resumen_filtrado[
            [
                "ArticuloCodigo",
                "ArticuloDescripcion",
            ]
        ]
        .drop_duplicates(
            "ArticuloCodigo"
        )
        .copy()
    )
    opciones["Etiqueta"] = (
        opciones["ArticuloCodigo"]
        + " · "
        + opciones[
            "ArticuloDescripcion"
        ].fillna("")
    )

    mapa_codigos = dict(
        zip(
            opciones["Etiqueta"],
            opciones["ArticuloCodigo"],
        )
    )

    selector, boton = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    etiqueta = selector.selectbox(
        "Artículo",
        options=opciones[
            "Etiqueta"
        ].tolist(),
        key="calidad_selector_articulo",
    )
    mostrar = boton.button(
        "🔎 Ver detalle",
        type="primary",
        width="stretch",
        key="calidad_ver_detalle",
    )

    if mostrar:
        st.session_state[
            "calidad_codigo_detalle"
        ] = mapa_codigos[
            etiqueta
        ]

    codigo_detalle = st.session_state.get(
        "calidad_codigo_detalle"
    )

    if codigo_detalle:
        detalle_articulo = (
            detalle_filtrado.loc[
                detalle_filtrado[
                    "ArticuloCodigo"
                ].eq(
                    codigo_detalle
                )
            ][
                [
                    "SectorCalidad",
                    "AreaReporte",
                    "Ubicacion",
                    "Contenedor",
                    "Lote",
                    "ArticuloCodigo",
                    "ArticuloDescripcion",
                    "Cantidad",
                    "VolumenTotalM3",
                    "FechaIngresoEstimada",
                    "DiasEnCalidad",
                    "FechaVencimiento",
                ]
            ]
            .sort_values(
                [
                    "DiasEnCalidad",
                    "Ubicacion",
                ],
                ascending=[
                    False,
                    True,
                ],
            )
        )

        st.dataframe(
            dataframe_para_streamlit(
                detalle_articulo
            ),
            hide_index=True,
            width="stretch",
            height=300,
            column_config={
                "Cantidad":
                    st.column_config.NumberColumn(
                        "Unidades",
                        format="%.0f",
                    ),
                "VolumenTotalM3":
                    st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.3f",
                    ),
                "FechaIngresoEstimada":
                    st.column_config.DateColumn(
                        "Ingreso estimado",
                        format="DD/MM/YYYY",
                    ),
                "DiasEnCalidad":
                    st.column_config.NumberColumn(
                        "Días",
                        format="%d",
                    ),
                "FechaVencimiento":
                    st.column_config.DateColumn(
                        "Vencimiento",
                        format="DD/MM/YYYY",
                    ),
            },
        )

    st.info(
        "La gestión de incidencias, responsables, acciones y cierre "
        "de reprocesos se incorporará sobre esta base operativa."
    )
