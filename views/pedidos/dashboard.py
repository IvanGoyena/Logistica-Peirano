from __future__ import annotations

import pandas as pd
import altair as alt
import streamlit as st

from models.dashboard_pedidos import (
    aplicar_filtros_dashboard, calcular_kpis, formatear_importe_compacto,
    resumen_categoria, resumen_composicion_detalle, resumen_evolucion,
)

def render_dashboard(datos_dashboard: pd.DataFrame, tabla_detalle_dashboard: pd.DataFrame) -> None:
        st.subheader("📊 Panorama operativo de pedidos")
        st.caption(
            "Lectura ejecutiva del pendiente, su volumen, antigüedad "
            "y distribución operativa."
        )

        st.markdown(
            """
            <style>
            .pedidos-kpi-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                margin: 8px 0 18px 0;
            }
            .pedidos-kpi-card {
                background: linear-gradient(145deg, #121923 0%, #0f151e 100%);
                border: 1px solid #2a3442;
                border-radius: 10px;
                padding: 16px 18px;
                min-height: 118px;
            }
            .pedidos-kpi-label {
                color: #d8dee9;
                font-size: 0.84rem;
                font-weight: 600;
                margin-bottom: 8px;
            }
            .pedidos-kpi-value {
                color: #f8fafc;
                font-size: 1.85rem;
                font-weight: 700;
                line-height: 1.1;
            }
            .pedidos-kpi-detail {
                color: #9ba8b7;
                font-size: 0.76rem;
                margin-top: 9px;
            }
            .inteligencia-grid {
                grid-template-columns: repeat(6, minmax(0, 1fr));
                margin-bottom: 1rem;
            }
            .inteligencia-card {
                min-height: 128px;
                background:
                    linear-gradient(145deg, rgba(20, 29, 41, 0.98), rgba(11, 17, 25, 0.98));
            }
            .inteligencia-card .pedidos-kpi-value {
                font-size: 1.42rem;
                overflow-wrap: anywhere;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: rgba(15, 23, 34, 0.58);
                border-color: #2A3543;
                border-radius: 12px;
            }

            .pedidos-panel {
                background: linear-gradient(145deg, #111822 0%, #0d141d 100%);
                border: 1px solid #2a3442;
                border-radius: 10px;
                padding: 12px 14px 4px 14px;
                margin-bottom: 12px;
            }
            @media (max-width: 1100px) {
                .pedidos-kpi-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
            @media (max-width: 640px) {
                .pedidos-kpi-grid {
                    grid-template-columns: 1fr;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        if datos_dashboard.empty:
            st.info("No hay pedidos disponibles para analizar.")
        else:
            fecha_min = datos_dashboard["FechaDia"].dropna().min()
            fecha_max = datos_dashboard["FechaDia"].dropna().max()

            with st.expander("🔎 Filtros del dashboard", expanded=False):
                (
                    filtro_1,
                    filtro_2,
                    filtro_3,
                    filtro_4,
                    filtro_5,
                    filtro_6,
                ) = st.columns(
                    [1.25, 1, 1, 1, 0.85, 0.85]
                )

                with filtro_1:
                    rango = st.date_input(
                        "Período de transmisión",
                        value=(
                            fecha_min.date(),
                            fecha_max.date(),
                        )
                        if pd.notna(fecha_min) and pd.notna(fecha_max)
                        else (),
                        key="pedidos_dashboard_periodo",
                    )

                with filtro_2:
                    estados_filtro = st.multiselect(
                        "Estado del pedido",
                        options=sorted(
                            datos_dashboard["Estado"]
                            .loc[datos_dashboard["Estado"].ne("")]
                            .unique()
                            .tolist()
                        ),
                        default=[],
                    )

                with filtro_3:
                    preparacion_filtro = st.multiselect(
                        "Preparación",
                        options=sorted(
                            datos_dashboard["CategoriaPreparacion"]
                            .unique()
                            .tolist()
                        ),
                        default=[],
                    )

                with filtro_4:
                    planificacion_filtro = st.multiselect(
                        "Planificación",
                        options=sorted(
                            datos_dashboard["PlanificacionVisible"]
                            .unique()
                            .tolist()
                        ),
                        default=[],
                    )

                with filtro_5:
                    incluir_cencosud = st.toggle(
                        "Incluir Cencosud",
                        value=True,
                        key="pedidos_incluir_cencosud",
                        help=(
                            "Encendido: incluye los pedidos de Cencosud. "
                            "Apagado: muestra el pendiente sin Cencosud."
                        ),
                    )

                with filtro_6:
                    ver_solo_cencosud = st.toggle(
                        "Ver Cencosud",
                        value=False,
                        key="pedidos_ver_solo_cencosud",
                        help=(
                            "Encendido: muestra únicamente los pedidos "
                            "de Cencosud."
                        ),
                    )

            fecha_desde = None
            fecha_hasta = None
            if isinstance(rango, (list, tuple)) and len(rango) == 2:
                fecha_desde, fecha_hasta = rango

            # Si se activa "Ver Cencosud", se fuerza la inclusión
            # para evitar que ambos controles se contradigan.
            incluir_cencosud_aplicado = (
                True
                if ver_solo_cencosud
                else incluir_cencosud
            )

            dashboard_filtrado = aplicar_filtros_dashboard(
                datos_dashboard,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                estados=estados_filtro,
                preparaciones=preparacion_filtro,
                planificaciones=planificacion_filtro,
                incluir_cencosud=incluir_cencosud_aplicado,
            )

            if ver_solo_cencosud:
                columna_cliente_cencosud = (
                    "ClienteVisible"
                    if "ClienteVisible" in dashboard_filtrado.columns
                    else "ClienteDescripcion"
                )

                dashboard_filtrado = dashboard_filtrado.loc[
                    dashboard_filtrado[columna_cliente_cencosud]
                    .fillna("")
                    .astype(str)
                    .str.upper()
                    .str.contains("CENCOSUD", regex=False)
                ].copy()

            kpis = calcular_kpis(dashboard_filtrado)

            pedidos_preparados = int(
                dashboard_filtrado.loc[
                    dashboard_filtrado["CategoriaPreparacion"].eq("Preparado"),
                    "Pedido",
                ].nunique()
            )
            pedidos_en_preparacion = int(
                dashboard_filtrado.loc[
                    dashboard_filtrado["CategoriaPreparacion"].eq("En preparación"),
                    "Pedido",
                ].nunique()
            )
            unidades_criticas = int(
                dashboard_filtrado.loc[
                    dashboard_filtrado["AntiguedadDias"].gt(5),
                    "TotalUnidades",
                ].sum()
            )

            def _fmt_entero(valor):
                return f"{int(valor):,}".replace(",", ".")

            def _fmt_decimal(valor, decimales=2):
                return (
                    f"{float(valor):,.{decimales}f}"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

            tarjetas = [
                ("📦 Pedidos", _fmt_entero(kpis["pedidos"]),
                 f"{_fmt_entero(kpis['unidades'])} unidades"),
                ("💰 Importe pendiente", formatear_importe_compacto(kpis["importe"]),
                 "Valor pendiente informado por ERP"),
                ("📐 Volumen", f"{_fmt_decimal(kpis['volumen'])} m³",
                 f"{kpis['clientes']} clientes"),
                ("⏳ Antigüedad promedio",
                 f"{_fmt_decimal(kpis['antiguedad_promedio'], 1)} días",
                 f"{_fmt_entero(unidades_criticas)} unidades con más de 5 días"),
                ("🚨 Pedidos críticos", _fmt_entero(kpis["pedidos_criticos"]),
                 "Antigüedad o dimensión excepcional"),
                ("🧰 En preparación", _fmt_entero(pedidos_en_preparacion),
                 f"{_fmt_entero(pedidos_preparados)} preparados"),
                ("🚚 Planificaciones", _fmt_entero(kpis["planificaciones"]),
                 "Agrupaciones operativas activas"),
                ("👥 Clientes", _fmt_entero(kpis["clientes"]),
                 "Clientes incluidos en los filtros"),
            ]

            html_tarjetas = '<div class="pedidos-kpi-grid">'
            for etiqueta, valor, detalle in tarjetas:
                html_tarjetas += (
                    '<div class="pedidos-kpi-card">'
                    f'<div class="pedidos-kpi-label">{etiqueta}</div>'
                    f'<div class="pedidos-kpi-value">{valor}</div>'
                    f'<div class="pedidos-kpi-detail">{detalle}</div>'
                    '</div>'
                )
            html_tarjetas += "</div>"
            st.markdown(html_tarjetas, unsafe_allow_html=True)

            st.markdown("### Lectura visual del pendiente")

            evolucion_dashboard = resumen_evolucion(dashboard_filtrado)
            resumen_planificacion = resumen_categoria(
                dashboard_filtrado,
                "PlanificacionVisible",
                "Planificación",
                top=10,
                medida="Volumen",
            )

            grafico_1, grafico_2 = st.columns([1.45, 1], vertical_alignment="top")

            with grafico_1:
                st.markdown("#### Evolución de unidades transmitidas")

                if evolucion_dashboard.empty:
                    st.info("No hay fechas válidas para graficar.")
                else:
                    linea = (
                        alt.Chart(evolucion_dashboard)
                        .mark_line(
                            point=alt.OverlayMarkDef(
                                filled=True,
                                size=60,
                                color="#2563EB",
                            ),
                            strokeWidth=3,
                            color="#1D4ED8",
                        )
                        .encode(
                            x=alt.X(
                                "Fecha:T",
                                title=None,
                                axis=alt.Axis(format="%d/%m"),
                            ),
                            y=alt.Y(
                                "Unidades:Q",
                                title="Unidades",
                                axis=alt.Axis(grid=True),
                            ),
                            tooltip=[
                                alt.Tooltip("FechaVisible:N", title="Fecha"),
                                alt.Tooltip(
                                    "Unidades:Q",
                                    title="Unidades",
                                    format=",.0f",
                                ),
                            ],
                        )
                    )

                    etiquetas = (
                        alt.Chart(evolucion_dashboard)
                        .mark_text(
                            align="center",
                            baseline="bottom",
                            dy=-8,
                            color="#D7DEE8",
                            fontSize=11,
                            fontWeight=600,
                        )
                        .encode(
                            x="Fecha:T",
                            y="Unidades:Q",
                            text=alt.Text("Unidades:Q", format=",.0f"),
                        )
                    )

                    st.altair_chart(
                        (linea + etiquetas)
                        .properties(height=310)
                        .configure_view(strokeOpacity=0)
                        .configure_axis(
                            labelColor="#B8C2CF",
                            titleColor="#D8DEE9",
                            gridColor="#26303D",
                            domainColor="#3B4655",
                        ),
                        width="stretch",
                    )

            with grafico_2:
                st.markdown("#### Composición del pendiente")

                dimension_composicion = st.radio(
                    "Analizar unidades por",
                    options=["Sectorización", "Familia"],
                    horizontal=True,
                    key="pedidos_dimension_composicion",
                    label_visibility="collapsed",
                )

                columna_dimension = (
                    "Sectorizacion"
                    if dimension_composicion == "Sectorización"
                    else "Familia"
                )

                pedidos_dashboard = (
                    dashboard_filtrado["Pedido"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .tolist()
                )

                resumen_composicion = resumen_composicion_detalle(
                    tabla_detalle_dashboard,
                    pedidos=pedidos_dashboard,
                    dimension=columna_dimension,
                    top=7,
                )

                if resumen_composicion.empty:
                    st.info("No hay detalle disponible para la composición.")
                else:
                    nombre_dimension = dimension_composicion
                    resumen_composicion = resumen_composicion.copy()
                    resumen_composicion["Total"] = (
                        resumen_composicion["Unidades"].sum()
                    )
                    resumen_composicion["Porcentaje"] = (
                        resumen_composicion["Unidades"]
                        / resumen_composicion["Total"].replace(0, pd.NA)
                        * 100
                    ).fillna(0)
                    resumen_composicion["Etiqueta"] = (
                        resumen_composicion["Unidades"]
                        .map(lambda valor: f"{int(valor):,}".replace(",", "."))
                        + " | "
                        + resumen_composicion["Porcentaje"]
                        .map(lambda valor: f"{valor:.1f}%")
                    )

                    paleta_composicion = [
                        "#1E3A5F",
                        "#155E75",
                        "#166534",
                        "#854D0E",
                        "#7C2D12",
                        "#4C1D95",
                        "#374151",
                        "#111827",
                    ]

                    donut_composicion = (
                        alt.Chart(resumen_composicion)
                        .mark_arc(
                            innerRadius=72,
                            outerRadius=116,
                            stroke="#0B1119",
                            strokeWidth=2,
                        )
                        .encode(
                            theta=alt.Theta("Unidades:Q", stack=True),
                            color=alt.Color(
                                f"{nombre_dimension}:N",
                                scale=alt.Scale(range=paleta_composicion),
                                legend=alt.Legend(
                                    orient="right",
                                    title=None,
                                    labelColor="#D8DEE9",
                                    labelLimit=190,
                                ),
                            ),
                            tooltip=[
                                alt.Tooltip(
                                    f"{nombre_dimension}:N",
                                    title=nombre_dimension,
                                ),
                                alt.Tooltip(
                                    "Unidades:Q",
                                    title="Unidades",
                                    format=",.0f",
                                ),
                                alt.Tooltip(
                                    "Porcentaje:Q",
                                    title="Participación",
                                    format=".1f",
                                ),
                            ],
                        )
                    )

                    etiquetas_composicion = (
                        alt.Chart(resumen_composicion)
                        .mark_text(
                            radius=137,
                            fontSize=10,
                            fontWeight=600,
                            color="#F8FAFC",
                        )
                        .encode(
                            theta=alt.Theta("Unidades:Q", stack=True),
                            text="Etiqueta:N",
                        )
                    )

                    total_unidades_composicion = int(
                        resumen_composicion["Unidades"].sum()
                    )
                    centro_composicion = (
                        alt.Chart(
                            pd.DataFrame(
                                {
                                    "texto": [
                                        f"{total_unidades_composicion:,}"
                                        .replace(",", ".")
                                        + "\nUnidades"
                                    ]
                                }
                            )
                        )
                        .mark_text(
                            align="center",
                            baseline="middle",
                            fontSize=18,
                            fontWeight=700,
                            color="#F8FAFC",
                            lineBreak="\n",
                        )
                        .encode(text="texto:N")
                    )

                    st.altair_chart(
                        (
                            donut_composicion
                            + etiquetas_composicion
                            + centro_composicion
                        )
                        .properties(height=310)
                        .configure_view(strokeOpacity=0),
                        width="stretch",
                    )

                st.caption(
                    "Incluye Cencosud"
                    if incluir_cencosud
                    else "Vista sin Cencosud"
                )

            st.markdown("#### Volumen por planificación")

            if resumen_planificacion.empty:
                st.info("No hay planificaciones para graficar.")
            else:
                max_volumen = float(
                    resumen_planificacion["Volumen"].max()
                )
                resumen_planificacion["EsMayor"] = (
                    resumen_planificacion["Volumen"].eq(max_volumen)
                )

                barras = (
                    alt.Chart(resumen_planificacion)
                    .mark_bar(cornerRadiusEnd=5, size=22)
                    .encode(
                        x=alt.X(
                            "Volumen:Q",
                            title="Volumen m³",
                        ),
                        y=alt.Y(
                            "Planificación:N",
                            sort="-x",
                            title=None,
                        ),
                        color=alt.condition(
                            "datum.EsMayor",
                            alt.value("#1D4ED8"),
                            alt.value("#27496D"),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Planificación:N",
                                title="Planificación",
                            ),
                            alt.Tooltip(
                                "Volumen:Q",
                                title="Volumen m³",
                                format=".2f",
                            ),
                        ],
                    )
                )

                etiquetas = (
                    alt.Chart(resumen_planificacion)
                    .mark_text(
                        align="left",
                        baseline="middle",
                        dx=7,
                        color="#E5E7EB",
                        fontSize=11,
                        fontWeight=600,
                    )
                    .encode(
                        x="Volumen:Q",
                        y=alt.Y("Planificación:N", sort="-x"),
                        text=alt.Text("Volumen:Q", format=".2f"),
                    )
                )

                st.altair_chart(
                    (barras + etiquetas)
                    .properties(height=max(260, len(resumen_planificacion) * 34))
                    .configure_view(strokeOpacity=0)
                    .configure_axis(
                        labelColor="#B8C2CF",
                        titleColor="#D8DEE9",
                        gridColor="#26303D",
                        domainColor="#3B4655",
                    ),
                    width="stretch",
                )

            detalle_1, detalle_2 = st.columns(2, vertical_alignment="top")

            with detalle_1:
                st.markdown("#### Clientes con mayor carga")

                clientes_carga = resumen_categoria(
                    dashboard_filtrado,
                    "ClienteVisible",
                    "Cliente",
                    top=8,
                    medida="Unidades",
                )

                if clientes_carga.empty:
                    st.info("No hay clientes para mostrar.")
                else:
                    barras_clientes = (
                        alt.Chart(clientes_carga)
                        .mark_bar(cornerRadiusEnd=4, color="#4C1D95")
                        .encode(
                            x=alt.X("Unidades:Q", title="Unidades"),
                            y=alt.Y("Cliente:N", sort="-x", title=None),
                            tooltip=[
                                alt.Tooltip("Cliente:N"),
                                alt.Tooltip(
                                    "Unidades:Q",
                                    format=",.0f",
                                ),
                            ],
                        )
                    )
                    texto_clientes = (
                        alt.Chart(clientes_carga)
                        .mark_text(
                            align="left",
                            baseline="middle",
                            dx=6,
                            color="#E5E7EB",
                        )
                        .encode(
                            x="Unidades:Q",
                            y=alt.Y("Cliente:N", sort="-x"),
                            text=alt.Text("Unidades:Q", format=",.0f"),
                        )
                    )
                    st.altair_chart(
                        (barras_clientes + texto_clientes)
                        .properties(height=300)
                        .configure_view(strokeOpacity=0)
                        .configure_axis(
                            labelColor="#B8C2CF",
                            titleColor="#D8DEE9",
                            gridColor="#26303D",
                        ),
                        width="stretch",
                    )

            with detalle_2:
                st.markdown("#### Antigüedad de pedidos")

                antiguedad = resumen_categoria(
                    dashboard_filtrado,
                    "RangoAntiguedad",
                    "Antigüedad",
                    medida="Pedidos",
                )

                orden_antiguedad = [
                    "Hoy",
                    "1 día",
                    "2 días",
                    "3 a 5 días",
                    "Más de 5 días",
                ]

                if antiguedad.empty:
                    st.info("No hay antigüedad para mostrar.")
                else:
                    barras_antiguedad = (
                        alt.Chart(antiguedad)
                        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                        .encode(
                            x=alt.X(
                                "Antigüedad:N",
                                sort=orden_antiguedad,
                                title=None,
                            ),
                            y=alt.Y("Pedidos:Q", title="Pedidos"),
                            color=alt.Color(
                                "Antigüedad:N",
                                sort=orden_antiguedad,
                                scale=alt.Scale(
                                    domain=orden_antiguedad,
                                    range=[
                                        "#1E3A5F",
                                        "#27496D",
                                        "#8A5A00",
                                        "#9A3412",
                                        "#7F1D1D",
                                    ],
                                ),
                                legend=None,
                            ),
                            tooltip=[
                                alt.Tooltip("Antigüedad:N"),
                                alt.Tooltip("Pedidos:Q"),
                            ],
                        )
                    )
                    texto_antiguedad = (
                        alt.Chart(antiguedad)
                        .mark_text(
                            baseline="bottom",
                            dy=-6,
                            color="#F8FAFC",
                            fontWeight=600,
                        )
                        .encode(
                            x=alt.X(
                                "Antigüedad:N",
                                sort=orden_antiguedad,
                            ),
                            y="Pedidos:Q",
                            text="Pedidos:Q",
                        )
                    )
                    st.altair_chart(
                        (barras_antiguedad + texto_antiguedad)
                        .properties(height=300)
                        .configure_view(strokeOpacity=0)
                        .configure_axis(
                            labelColor="#B8C2CF",
                            titleColor="#D8DEE9",
                            gridColor="#26303D",
                        ),
                        width="stretch",
                    )


