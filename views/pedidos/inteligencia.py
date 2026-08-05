from __future__ import annotations

import pandas as pd
import streamlit as st

from models.dashboard_pedidos import (
    evaluar_riesgo_operativo, indicadores_inteligencia, indice_complejidad_pedidos,
    resumen_abc_detalle, resumen_categoria, resumen_clientes_analitico,
    resumen_clientes_impacto, resumen_planificacion_analitico,
)
from utils.graficos_pedidos import (
    barras_antiguedad_unidades, grafico_abc, grafico_impacto_clientes, pareto_clientes,
)

def render_inteligencia(datos_dashboard: pd.DataFrame, tabla_detalle_dashboard: pd.DataFrame) -> None:
        st.subheader("🧠 Inteligencia analítica del pendiente")
        st.caption(
            "Lectura de concentración, tendencia, antigüedad y dimensión "
            "operativa sobre los mismos filtros aplicados en Dashboard."
        )

        if datos_dashboard.empty:
            st.info("No hay pedidos disponibles para analizar.")
        else:
            # Se reutilizan los filtros definidos en Dashboard.
            # Streamlit ejecuta la página completa en cada interacción.
            if "dashboard_filtrado" not in locals():
                dashboard_filtrado = datos_dashboard.copy()

            inteligencia = indicadores_inteligencia(
                dashboard_filtrado
            )

            tendencia = inteligencia["tendencia_reciente"]
            tendencia_texto = (
                f"{tendencia:+.1f}%"
                if tendencia is not None
                else "Sin base"
            )

            tarjetas_inteligencia = [
                (
                    "📦 Unidades / pedido",
                    f"{inteligencia['unidades_promedio_pedido']:.1f}",
                    "Dimensión media del pedido",
                ),
                (
                    "📐 M³ / pedido",
                    f"{inteligencia['volumen_promedio_pedido']:.2f}",
                    "Volumen medio operativo",
                ),
                (
                    "🎯 Concentración Top 5",
                    f"{inteligencia['concentracion_top_5']:.1f}%",
                    "Participación de los 5 principales clientes",
                ),
                (
                    "🏢 Cliente principal",
                    inteligencia["cliente_principal"],
                    (
                        f"{inteligencia['participacion_cliente_principal']:.1f}% "
                        "de las unidades"
                    ),
                ),
                (
                    "⏳ Pedidos +5 días",
                    f"{inteligencia['pedidos_mas_5_dias']:,}".replace(",", "."),
                    (
                        f"{inteligencia['unidades_mas_5_dias']:,} unidades"
                    ).replace(",", "."),
                ),
                (
                    "📈 Tendencia reciente",
                    tendencia_texto,
                    "Comparación contra el bloque anterior",
                ),
            ]

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
                    background: linear-gradient(
                        145deg,
                        rgba(20, 29, 41, 0.98),
                        rgba(11, 17, 25, 0.98)
                    );
                }
                .inteligencia-card .pedidos-kpi-value {
                    font-size: 1.42rem;
                    overflow-wrap: anywhere;
                }
                @media (max-width: 1400px) {
                    .inteligencia-grid {
                        grid-template-columns: repeat(3, minmax(0, 1fr));
                    }
                }
                @media (max-width: 900px) {
                    .inteligencia-grid {
                        grid-template-columns: repeat(2, minmax(0, 1fr));
                    }
                }
                @media (max-width: 640px) {
                    .inteligencia-grid {
                        grid-template-columns: 1fr;
                    }
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            html_inteligencia = '<div class="pedidos-kpi-grid inteligencia-grid">'
            for etiqueta, valor, detalle in tarjetas_inteligencia:
                html_inteligencia += (
                    '<div class="pedidos-kpi-card inteligencia-card">'
                    f'<div class="pedidos-kpi-label">{etiqueta}</div>'
                    f'<div class="pedidos-kpi-value">{valor}</div>'
                    f'<div class="pedidos-kpi-detail">{detalle}</div>'
                    '</div>'
                )
            html_inteligencia += "</div>"
            st.markdown(html_inteligencia, unsafe_allow_html=True)

            st.divider()

            analitica_1, analitica_2 = st.columns([1.45, 1])

            with analitica_1:
                st.markdown(
                    "#### Pareto de clientes por unidades"
                )
                tabla_pareto = resumen_clientes_analitico(
                    dashboard_filtrado,
                    top=12,
                )
                pareto_clientes(tabla_pareto)

            with analitica_2:
                st.markdown(
                    "#### Unidades por antigüedad"
                )
                antiguedad_unidades = resumen_categoria(
                    dashboard_filtrado,
                    "RangoAntiguedad",
                    "Antigüedad",
                    medida="Unidades",
                )
                barras_antiguedad_unidades(
                    antiguedad_unidades
                )

            st.markdown("### Diagnóstico operativo avanzado")

            avanzada_1, avanzada_2 = st.columns([1.15, 1])

            with avanzada_1:
                st.markdown("#### ABC de la composición")

                dimension_abc = st.radio(
                    "Dimensión ABC",
                    options=["Familia", "Sectorización"],
                    horizontal=True,
                    key="pedidos_dimension_abc",
                    label_visibility="collapsed",
                )
                columna_abc = (
                    "Familia"
                    if dimension_abc == "Familia"
                    else "Sectorizacion"
                )
                tabla_abc = resumen_abc_detalle(
                    tabla_detalle_dashboard,
                    pedidos=dashboard_filtrado[
                        "Pedido"
                    ].tolist(),
                    dimension=columna_abc,
                )

                grafico_abc(
                    tabla_abc.head(15),
                    dimension_abc,
                )

                st.caption(
                    "Clase A: hasta 80% acumulado · "
                    "Clase B: 80–95% · Clase C: restante. "
                    "El importe no se reparte por familia porque "
                    "el detalle no contiene valor por línea."
                )

            with avanzada_2:
                st.markdown("#### Riesgo operativo")

                riesgo = evaluar_riesgo_operativo(
                    dashboard_filtrado,
                    inteligencia,
                )

                color_riesgo = {
                    "Alto": "error",
                    "Medio": "warning",
                    "Bajo": "success",
                }.get(riesgo["nivel"], "info")

                mensaje_riesgo = (
                    f"Nivel {riesgo['nivel']} · "
                    f"{riesgo['puntaje']} puntos"
                )

                if color_riesgo == "error":
                    st.error(mensaje_riesgo, icon="🔴")
                elif color_riesgo == "warning":
                    st.warning(mensaje_riesgo, icon="🟡")
                elif color_riesgo == "success":
                    st.success(mensaje_riesgo, icon="🟢")
                else:
                    st.info(mensaje_riesgo)

                for motivo in riesgo["motivos"]:
                    st.markdown(f"- {motivo}")

                st.markdown("#### Clientes calientes")
                clientes_impacto = resumen_clientes_impacto(
                    dashboard_filtrado,
                    top=8,
                )
                grafico_impacto_clientes(
                    clientes_impacto
                )

            analitica_3, analitica_4 = st.columns(2)

            with analitica_3:
                st.markdown(
                    "#### Productividad por planificación"
                )
                tabla_planificacion = (
                    resumen_planificacion_analitico(
                        dashboard_filtrado
                    )
                )

                st.dataframe(
                    tabla_planificacion,
                    width="stretch",
                    hide_index=True,
                    height=min(
                        420,
                        75 + len(tabla_planificacion) * 35,
                    ),
                    column_config={
                        "Pedidos": st.column_config.NumberColumn(
                            format="%d"
                        ),
                        "Unidades": st.column_config.NumberColumn(
                            format="%d"
                        ),
                        "Volumen": st.column_config.NumberColumn(
                            "Volumen (m³)",
                            format="%.2f",
                        ),
                        "Unidades por pedido": (
                            st.column_config.NumberColumn(
                                format="%.1f"
                            )
                        ),
                        "M3 por pedido": (
                            st.column_config.NumberColumn(
                                "M³ por pedido",
                                format="%.2f",
                            )
                        ),
                    },
                )

            with analitica_4:
                st.markdown("#### Señales de gestión")

                if (
                    inteligencia["concentracion_top_5"]
                    >= 60
                ):
                    st.warning(
                        (
                            "Alta concentración: los cinco principales "
                            f"clientes representan "
                            f"{inteligencia['concentracion_top_5']:.1f}% "
                            "de las unidades pendientes."
                        ),
                        icon="⚠️",
                    )
                else:
                    st.success(
                        (
                            "La carga está relativamente distribuida: "
                            f"el Top 5 concentra "
                            f"{inteligencia['concentracion_top_5']:.1f}%."
                        ),
                        icon="✅",
                    )

                if inteligencia["pedidos_mas_5_dias"] > 0:
                    st.error(
                        (
                            f"Hay {inteligencia['pedidos_mas_5_dias']} "
                            "pedido(s) con más de 5 días, por "
                            f"{inteligencia['unidades_mas_5_dias']:,} "
                            "unidades."
                        ).replace(",", "."),
                        icon="⏳",
                    )
                else:
                    st.success(
                        "No hay pedidos con más de 5 días.",
                        icon="✅",
                    )

                if tendencia is not None:
                    if tendencia > 10:
                        st.warning(
                            (
                                "La carga reciente está creciendo: "
                                f"{tendencia:+.1f}% frente al bloque "
                                "de fechas anterior."
                            ),
                            icon="📈",
                        )
                    elif tendencia < -10:
                        st.success(
                            (
                                "La carga reciente está bajando: "
                                f"{tendencia:+.1f}% frente al bloque "
                                "de fechas anterior."
                            ),
                            icon="📉",
                        )
                    else:
                        st.info(
                            (
                                "La carga reciente se mantiene estable: "
                                f"{tendencia:+.1f}%."
                            ),
                            icon="➡️",
                        )

                st.info(
                    (
                        "Cliente con mayor impacto: "
                        f"{inteligencia['cliente_principal']} "
                        f"({inteligencia['participacion_cliente_principal']:.1f}% "
                        "de las unidades)."
                    ),
                    icon="🏢",
                )

            st.markdown(
                "#### Priorización por complejidad operativa"
            )
            st.caption(
                "El puntaje combina antigüedad, unidades, volumen, "
                "SKU, cantidad de familias e importe. El ranking es "
                "relativo al conjunto filtrado y explica sus motivos."
            )

            tabla_criticos = indice_complejidad_pedidos(
                dashboard_filtrado,
                tabla_detalle_dashboard,
                limite=20,
            )

            st.dataframe(
                tabla_criticos,
                width="stretch",
                hide_index=True,
                height=min(
                    560,
                    75 + len(tabla_criticos) * 35,
                ),
                column_config={
                    "Pedido": st.column_config.TextColumn(
                        width="small"
                    ),
                    "Cliente": st.column_config.TextColumn(
                        width="large"
                    ),
                    "Prioridad": st.column_config.NumberColumn(
                        "#",
                        format="%d",
                        width="small",
                    ),
                    "Puntaje": st.column_config.ProgressColumn(
                        "Complejidad",
                        min_value=0,
                        max_value=100,
                        format="%.1f",
                        width="medium",
                    ),
                    "Días": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "Unidades": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "SKU": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "Familias": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "M3": st.column_config.NumberColumn(
                        "M³",
                        format="%.2f",
                    ),
                    "Importe": st.column_config.NumberColumn(
                        "Importe",
                        format="$ %.0f",
                    ),
                    "Planificación": st.column_config.TextColumn(
                        width="medium"
                    ),
                    "Motivos": st.column_config.TextColumn(
                        width="large"
                    ),
                },
            )


