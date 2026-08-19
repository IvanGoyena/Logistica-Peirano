from __future__ import annotations

import math

import altair as alt
import pandas as pd
import streamlit as st


def render_dashboard_despachos(
    tabla_pedidos: pd.DataFrame,
) -> None:

    st.subheader("📊 Dashboard operativo")
    st.caption(
        "Estimación de vehículos sobre pedidos con Estado Pendiente. "
        "Los pedidos RETIRA no consumen capacidad de reparto."
    )

    filtro_cencosud_1, filtro_cencosud_2, espacio_filtro = st.columns(
        [0.9, 0.9, 4.2],
        vertical_alignment="center",
    )

    with filtro_cencosud_1:
        incluir_cencosud_dashboard = st.toggle(
            "Incluir Cencosud",
            value=True,
            key="despachos_incluir_cencosud_dashboard",
            help=(
                "Encendido: incluye los pedidos de Cencosud. "
                "Apagado: muestra el dashboard sin Cencosud."
            ),
        )

    with filtro_cencosud_2:
        ver_solo_cencosud_dashboard = st.toggle(
            "Ver Cencosud",
            value=False,
            key="despachos_ver_solo_cencosud_dashboard",
            help=(
                "Encendido: muestra únicamente los pedidos "
                "de Cencosud."
            ),
        )

    CAPACIDAD_CAMIONETA_M3 = 8.0
    CAPACIDAD_CAMION_M3 = 15.0

    # -----------------------------------------------------
    # ESTILO VISUAL DEL DASHBOARD
    # -----------------------------------------------------
    st.markdown(
        """
        <style>
        .despachos-kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.75rem 0 1rem 0;
        }
        .despachos-kpi {
            min-height: 128px;
            padding: 0.95rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 12px;
            background: linear-gradient(
                145deg,
                rgba(25, 32, 43, 0.96),
                rgba(14, 20, 29, 0.98)
            );
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .despachos-kpi-cabecera {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 0.86rem;
            font-weight: 650;
            color: rgba(240, 244, 248, 0.95);
        }
        .despachos-kpi-icono {
            font-size: 1.35rem;
        }
        .despachos-kpi-valor {
            margin-top: 0.4rem;
            font-size: 1.85rem;
            line-height: 1;
            font-weight: 750;
            color: #f8fafc;
        }
        .despachos-kpi-detalle {
            margin-top: 0.45rem;
            font-size: 0.76rem;
            color: rgba(203, 213, 225, 0.82);
        }
        .despachos-panel {
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 12px;
            padding: 0.55rem 0.8rem 0.3rem 0.8rem;
            background: rgba(17, 24, 34, 0.72);
        }
        @media (max-width: 1200px) {
            .despachos-kpi-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }
        @media (max-width: 700px) {
            .despachos-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    base_dashboard = tabla_pedidos.copy()

    # =====================================================
    # FILTRO OPERATIVO DEL DASHBOARD
    # =====================================================
    # El Dashboard utiliza exactamente el mismo criterio que el
    # Planificador: sólo pedidos cuyo Estado sea "Pendiente".
    #
    # PreparacionID NO participa del criterio de disponibilidad.
    if "Estado" in base_dashboard.columns:
        mascara_estado_pendiente = (
            base_dashboard["Estado"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("PENDIENTE")
        )
        base_dashboard = base_dashboard.loc[
            mascara_estado_pendiente
        ].copy()
    else:
        base_dashboard = base_dashboard.iloc[0:0].copy()

    cliente_dashboard = (
        base_dashboard["ClienteDescripcion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    mascara_cencosud_dashboard = cliente_dashboard.str.contains(
        "CENCOSUD",
        regex=False,
    )

    # "Ver Cencosud" tiene prioridad sobre "Incluir Cencosud"
    # para evitar que ambos controles se contradigan.
    if ver_solo_cencosud_dashboard:
        base_dashboard = base_dashboard.loc[
            mascara_cencosud_dashboard
        ].copy()

    elif not incluir_cencosud_dashboard:
        base_dashboard = base_dashboard.loc[
            ~mascara_cencosud_dashboard
        ].copy()

    base_dashboard["PlanificacionDashboard"] = (
        base_dashboard["Planificacion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("", "SIN PLANIFICACIÓN")
    )

    base_dashboard["VolumenDashboard"] = (
        pd.to_numeric(
            base_dashboard["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
    )

    base_dashboard["UnidadesDashboard"] = (
        pd.to_numeric(
            base_dashboard["TotalUnidades"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    mascara_retira_dashboard = (
        base_dashboard["PlanificacionDashboard"].eq("RETIRA")
    )

    base_retira_dashboard = base_dashboard.loc[
        mascara_retira_dashboard
    ].copy()

    base_reparto_dashboard = base_dashboard.loc[
        ~mascara_retira_dashboard
    ].copy()

    mascara_camion_dashboard = (
        base_reparto_dashboard["VolumenDashboard"]
        .gt(CAPACIDAD_CAMIONETA_M3)
    )

    base_camion_dashboard = base_reparto_dashboard.loc[
        mascara_camion_dashboard
    ].copy()

    base_camioneta_dashboard = base_reparto_dashboard.loc[
        ~mascara_camion_dashboard
    ].copy()

    volumen_camionetas_dashboard = float(
        base_camioneta_dashboard["VolumenDashboard"].sum()
    )
    volumen_camiones_dashboard = float(
        base_camion_dashboard["VolumenDashboard"].sum()
    )

    camionetas_estimadas_dashboard = (
        int(math.ceil(
            volumen_camionetas_dashboard / CAPACIDAD_CAMIONETA_M3
        ))
        if volumen_camionetas_dashboard > 0
        else 0
    )

    camiones_estimados_dashboard = (
        int(math.ceil(
            volumen_camiones_dashboard / CAPACIDAD_CAMION_M3
        ))
        if volumen_camiones_dashboard > 0
        else 0
    )

    pedidos_reparto_dashboard = int(
        base_reparto_dashboard["Pedido"].nunique()
    )
    pedidos_retira_dashboard = int(
        base_retira_dashboard["Pedido"].nunique()
    )
    pedidos_camion_dashboard = int(
        base_camion_dashboard["Pedido"].nunique()
    )
    pedidos_camioneta_dashboard = int(
        base_camioneta_dashboard["Pedido"].nunique()
    )

    unidades_reparto_dashboard = int(
        base_reparto_dashboard["UnidadesDashboard"].sum()
    )
    unidades_retira_dashboard = int(
        base_retira_dashboard["UnidadesDashboard"].sum()
    )
    unidades_camion_dashboard = int(
        base_camion_dashboard["UnidadesDashboard"].sum()
    )

    volumen_reparto_dashboard = float(
        base_reparto_dashboard["VolumenDashboard"].sum()
    )

    sin_planificacion_dashboard = int(
        base_dashboard.loc[
            base_dashboard["PlanificacionDashboard"]
            .eq("SIN PLANIFICACIÓN"),
            "Pedido",
        ].nunique()
    )
    unidades_sin_planificacion = int(
        base_dashboard.loc[
            base_dashboard["PlanificacionDashboard"]
            .eq("SIN PLANIFICACIÓN"),
            "UnidadesDashboard",
        ].sum()
    )

    def formato_entero(valor: int) -> str:
        return f"{int(valor):,}".replace(",", ".")

    tarjetas_html = f"""
    <div class="despachos-kpi-grid">
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚚</span>
                <span>Pedidos reparto</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_reparto_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_reparto_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚐</span>
                <span>Camionetas estimadas</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(camionetas_estimadas_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                Capacidad: {CAPACIDAD_CAMIONETA_M3:.0f} m³
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚛</span>
                <span>Camiones sugeridos</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(camiones_estimados_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                Capacidad: {CAPACIDAD_CAMION_M3:.0f} m³
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">📦</span>
                <span>Pedidos &gt; 8 m³</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_camion_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_camion_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🏬</span>
                <span>RETIRA</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_retira_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_retira_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">⚠️</span>
                <span>Sin planificación</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(sin_planificacion_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_sin_planificacion)} unidades
            </div>
        </div>
    </div>
    """

    st.markdown(tarjetas_html, unsafe_allow_html=True)

    # -----------------------------------------------------
    # GRÁFICOS
    # -----------------------------------------------------
    grafico_volumen, grafico_tipo = st.columns(
        [1.05, 1],
        vertical_alignment="top",
    )

    volumen_por_planificacion = (
        base_reparto_dashboard
        .groupby(
            "PlanificacionDashboard",
            as_index=False,
        )
        .agg(
            Volumen=("VolumenDashboard", "sum"),
            Pedidos=("Pedido", "nunique"),
        )
        .sort_values("Volumen", ascending=False)
    )

    with grafico_volumen:
        st.markdown("#### Volumen por planificación (m³)")

        if volumen_por_planificacion.empty:
            st.info("No hay carga de reparto para graficar.")
        else:
            volumen_por_planificacion["ValorVisible"] = (
                volumen_por_planificacion["Volumen"]
                .map(lambda valor: f"{valor:.2f}")
            )
            volumen_maximo = float(
                volumen_por_planificacion["Volumen"].max()
            )
            volumen_por_planificacion["EsMaximo"] = (
                volumen_por_planificacion["Volumen"].eq(volumen_maximo)
            )

            barras = (
                alt.Chart(volumen_por_planificacion)
                .mark_bar(cornerRadiusEnd=5, height=19)
                .encode(
                    x=alt.X(
                        "Volumen:Q",
                        title="Volumen m³",
                        axis=alt.Axis(
                            grid=True,
                            gridColor="#263241",
                            labelColor="#cbd5e1",
                            titleColor="#cbd5e1",
                        ),
                    ),
                    y=alt.Y(
                        "PlanificacionDashboard:N",
                        title=None,
                        sort="-x",
                        axis=alt.Axis(labelColor="#e2e8f0"),
                    ),
                    color=alt.condition(
                        alt.datum.EsMaximo,
                        alt.value("#1d4ed8"),
                        alt.value("#334f73"),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "PlanificacionDashboard:N",
                            title="Planificación",
                        ),
                        alt.Tooltip(
                            "Pedidos:Q",
                            title="Pedidos",
                            format=",.0f",
                        ),
                        alt.Tooltip(
                            "Volumen:Q",
                            title="Volumen m³",
                            format=".3f",
                        ),
                    ],
                )
            )

            etiquetas = (
                alt.Chart(volumen_por_planificacion)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=6,
                    color="#f8fafc",
                    fontSize=12,
                    fontWeight="bold",
                )
                .encode(
                    x="Volumen:Q",
                    y=alt.Y(
                        "PlanificacionDashboard:N",
                        sort="-x",
                    ),
                    text="ValorVisible:N",
                )
            )

            chart_volumen = (
                (barras + etiquetas)
                .properties(height=330)
                .configure_view(stroke=None)
            )

            st.altair_chart(
                chart_volumen,
                width="stretch",
            )

    total_pedidos_dashboard = (
        pedidos_camioneta_dashboard
        + pedidos_camion_dashboard
        + pedidos_retira_dashboard
    )

    distribucion_transporte = pd.DataFrame({
        "Tipo": ["Camioneta", "Camión", "RETIRA"],
        "Pedidos": [
            pedidos_camioneta_dashboard,
            pedidos_camion_dashboard,
            pedidos_retira_dashboard,
        ],
        "Orden": [1, 2, 3],
    })

    distribucion_transporte = distribucion_transporte.loc[
        distribucion_transporte["Pedidos"].gt(0)
    ].copy()

    if total_pedidos_dashboard > 0:
        distribucion_transporte["Porcentaje"] = (
            distribucion_transporte["Pedidos"]
            / total_pedidos_dashboard
            * 100
        )
    else:
        distribucion_transporte["Porcentaje"] = 0.0

    # Construcción segura de etiqueta: evita operaciones aritméticas
    # entre StringDtype/Arrow y float en versiones nuevas de pandas.
    distribucion_transporte["Etiqueta"] = [
        f"{int(pedidos)} ({float(porcentaje):.1f}%)"
        for pedidos, porcentaje in zip(
            distribucion_transporte["Pedidos"].tolist(),
            distribucion_transporte["Porcentaje"].tolist(),
        )
    ]

    with grafico_tipo:
        st.markdown("#### Pedidos por tipo de gestión")

        if distribucion_transporte.empty:
            st.info("No hay pedidos para graficar.")
        else:
            escala_colores = alt.Scale(
                domain=["Camioneta", "Camión", "RETIRA"],
                range=["#174f87", "#b45309", "#166534"],
            )

            donut = (
                alt.Chart(distribucion_transporte)
                .mark_arc(
                    innerRadius=88,
                    outerRadius=135,
                    stroke="#0f1720",
                    strokeWidth=2,
                )
                .encode(
                    theta=alt.Theta(
                        "Pedidos:Q",
                        stack=True,
                    ),
                    color=alt.Color(
                        "Tipo:N",
                        scale=escala_colores,
                        legend=alt.Legend(
                            orient="right",
                            title=None,
                            labelColor="#e2e8f0",
                            labelFontSize=12,
                            symbolSize=180,
                        ),
                    ),
                    order=alt.Order("Orden:Q"),
                    tooltip=[
                        alt.Tooltip("Tipo:N", title="Tipo"),
                        alt.Tooltip(
                            "Pedidos:Q",
                            title="Pedidos",
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

            etiquetas_donut = (
                alt.Chart(distribucion_transporte)
                .mark_text(
                    radius=155,
                    color="#f8fafc",
                    fontSize=12,
                    fontWeight="bold",
                )
                .encode(
                    theta=alt.Theta(
                        "Pedidos:Q",
                        stack=True,
                    ),
                    order=alt.Order("Orden:Q"),
                    text="Etiqueta:N",
                )
            )

            centro_total = (
                alt.Chart(
                    pd.DataFrame({
                        "Texto": [
                            str(total_pedidos_dashboard),
                            "Pedidos totales",
                        ],
                        "Y": [-7, 16],
                        "Tamanio": [30, 13],
                    })
                )
                .mark_text(
                    align="center",
                    baseline="middle",
                    color="#f8fafc",
                    fontWeight="bold",
                )
                .encode(
                    text="Texto:N",
                    y=alt.Y(
                        "Y:Q",
                        axis=None,
                        scale=alt.Scale(domain=[-100, 100]),
                    ),
                    size=alt.Size(
                        "Tamanio:Q",
                        legend=None,
                        scale=None,
                    ),
                )
            )

            chart_tipo = (
                (donut + etiquetas_donut + centro_total)
                .properties(height=330)
                .configure_view(stroke=None)
            )

            st.altair_chart(
                chart_tipo,
                width="stretch",
            )

    # -----------------------------------------------------
    # CAPACIDAD POR PLANIFICACIÓN
    # -----------------------------------------------------
    st.markdown("#### Capacidad estimada por planificación")

    def resumir_capacidad_planificacion(
        bloque: pd.DataFrame,
    ) -> pd.Series:

        volumen_camioneta = float(
            bloque.loc[
                bloque["VolumenDashboard"]
                .le(CAPACIDAD_CAMIONETA_M3),
                "VolumenDashboard",
            ].sum()
        )

        volumen_camion = float(
            bloque.loc[
                bloque["VolumenDashboard"]
                .gt(CAPACIDAD_CAMIONETA_M3),
                "VolumenDashboard",
            ].sum()
        )

        camionetas = (
            int(math.ceil(
                volumen_camioneta / CAPACIDAD_CAMIONETA_M3
            ))
            if volumen_camioneta > 0
            else 0
        )

        camiones = (
            int(math.ceil(
                volumen_camion / CAPACIDAD_CAMION_M3
            ))
            if volumen_camion > 0
            else 0
        )

        capacidad_total = (
            camionetas * CAPACIDAD_CAMIONETA_M3
            + camiones * CAPACIDAD_CAMION_M3
        )

        ocupacion = (
            (volumen_camioneta + volumen_camion)
            / capacidad_total
            * 100
            if capacidad_total > 0
            else 0
        )

        if ocupacion > 90:
            estado_ocupacion = "🔴 Alta"
        elif ocupacion >= 70:
            estado_ocupacion = "🟡 Media"
        else:
            estado_ocupacion = "🟢 Baja"

        return pd.Series({
            "Pedidos": int(bloque["Pedido"].nunique()),
            "Clientes": int(bloque["ClienteCodigo"].nunique()),
            "Unidades": int(bloque["UnidadesDashboard"].sum()),
            "Volumen m³": round(
                float(bloque["VolumenDashboard"].sum()),
                3,
            ),
            "Camionetas (8 m³)": camionetas,
            "Pedidos camión (> 8 m³)": int(
                bloque.loc[
                    bloque["VolumenDashboard"]
                    .gt(CAPACIDAD_CAMIONETA_M3),
                    "Pedido",
                ].nunique()
            ),
            "Camiones (15 m³)": camiones,
            "Nivel": estado_ocupacion,
            "Ocupación estimada %": round(ocupacion, 1),
        })

    columnas_resumen_capacidad = [
        "Planificación",
        "Pedidos",
        "Clientes",
        "Unidades",
        "Volumen m³",
        "Camionetas (8 m³)",
        "Pedidos camión (> 8 m³)",
        "Camiones (15 m³)",
        "Nivel",
        "Ocupación estimada %",
    ]

    if base_reparto_dashboard.empty:
        resumen_capacidad_dashboard = pd.DataFrame(
            columns=columnas_resumen_capacidad
        )
    else:
        filas_capacidad = []

        for planificacion, bloque in (
            base_reparto_dashboard
            .groupby(
                "PlanificacionDashboard",
                dropna=False,
                sort=False,
            )
        ):
            resumen = resumir_capacidad_planificacion(
                bloque
            ).to_dict()

            resumen["Planificación"] = (
                str(planificacion).strip()
                if pd.notna(planificacion)
                else "SIN PLANIFICACIÓN"
            )

            filas_capacidad.append(resumen)

        resumen_capacidad_dashboard = pd.DataFrame(
            filas_capacidad
        )

        for columna in columnas_resumen_capacidad:
            if columna not in resumen_capacidad_dashboard.columns:
                resumen_capacidad_dashboard[columna] = (
                    0
                    if columna
                    in {
                        "Pedidos",
                        "Clientes",
                        "Unidades",
                        "Volumen m³",
                        "Camionetas (8 m³)",
                        "Pedidos camión (> 8 m³)",
                        "Camiones (15 m³)",
                        "Ocupación estimada %",
                    }
                    else ""
                )

        resumen_capacidad_dashboard = (
            resumen_capacidad_dashboard[
                columnas_resumen_capacidad
            ]
            .sort_values(
                [
                    "Camiones (15 m³)",
                    "Camionetas (8 m³)",
                    "Volumen m³",
                ],
                ascending=[False, False, False],
            )
            .reset_index(drop=True)
        )

    st.dataframe(
        resumen_capacidad_dashboard,
        width="stretch",
        hide_index=True,
        height=min(
            390,
            80 + len(resumen_capacidad_dashboard) * 35,
        ),
        column_config={
            "Pedidos": st.column_config.NumberColumn(
                "Pedidos",
                format="%d",
            ),
            "Clientes": st.column_config.NumberColumn(
                "Clientes",
                format="%d",
            ),
            "Unidades": st.column_config.NumberColumn(
                "Unidades",
                format="%d",
            ),
            "Volumen m³": st.column_config.NumberColumn(
                "Volumen m³",
                format="%.3f",
            ),
            "Camionetas (8 m³)": st.column_config.NumberColumn(
                "Camionetas (8 m³)",
                format="%d",
            ),
            "Pedidos camión (> 8 m³)": (
                st.column_config.NumberColumn(
                    "Pedidos camión (> 8 m³)",
                    format="%d",
                )
            ),
            "Camiones (15 m³)": st.column_config.NumberColumn(
                "Camiones (15 m³)",
                format="%d",
            ),
            "Ocupación estimada %": (
                st.column_config.ProgressColumn(
                    "Ocupación estimada",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
                )
            ),
        },
    )

    # -----------------------------------------------------
    # DETALLE Y CONTROLES
    # -----------------------------------------------------
    panel_camion, panel_alertas = st.columns(
        [1.15, 1],
        vertical_alignment="top",
    )

    with panel_camion:

        st.markdown("#### 🚛 Clientes candidatos a camión (> 8 m³)")

        # La necesidad de transporte se analiza por cliente completo.
        # Por eso se parte de TODOS los pedidos de reparto y recién después
        # se filtran los clientes cuyo volumen acumulado supera 8 m³.
        # Regla especial para Cencosud:
        # solamente se consolidan como carga de camión los pedidos
        # cuya planificación es EASY. Los pedidos Cencosud con
        # planificación semanal/diaria continúan en los repartos normales.
        cliente_reparto_normalizado = (
            base_reparto_dashboard["ClienteDescripcion"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        planificacion_reparto_normalizada = (
            base_reparto_dashboard["PlanificacionDashboard"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        es_cencosud_reparto = cliente_reparto_normalizado.str.contains(
            "CENCOSUD",
            regex=False,
        )

        base_clientes_camion = base_reparto_dashboard.loc[
            ~es_cencosud_reparto
            | planificacion_reparto_normalizada.eq("EASY")
        ].copy()

        clientes_camion_dashboard = (
            base_clientes_camion
            .groupby(
                [
                    "ClienteCodigo",
                    "ClienteDescripcion",
                ],
                as_index=False,
                dropna=False,
            )
            .agg(
                Planificaciones=(
                    "PlanificacionDashboard",
                    lambda serie: ", ".join(
                        sorted(
                            {
                                str(valor).strip()
                                for valor in serie
                                if str(valor).strip()
                            }
                        )
                    ),
                ),
                Pedidos=(
                    "Pedido",
                    lambda serie: ", ".join(
                        sorted(
                            {
                                str(valor).strip()
                                for valor in serie
                                if str(valor).strip()
                            }
                        )
                    ),
                ),
                CantidadPedidos=("Pedido", "nunique"),
                VolumenM3=("VolumenDashboard", "sum"),
                Unidades=("UnidadesDashboard", "sum"),
            )
        )

        clientes_camion_dashboard = clientes_camion_dashboard.loc[
            clientes_camion_dashboard["VolumenM3"]
            .gt(CAPACIDAD_CAMIONETA_M3)
        ].copy()

        if clientes_camion_dashboard.empty:
            st.success(
                "No hay clientes con volumen acumulado superior a 8 m³.",
                icon="✅",
            )
        else:
            clientes_camion_dashboard["CamionetasEstimadas"] = (
                clientes_camion_dashboard["VolumenM3"]
                .div(CAPACIDAD_CAMIONETA_M3)
                .apply(math.ceil)
                .astype(int)
            )

            clientes_camion_dashboard["Nivel"] = (
                clientes_camion_dashboard["CamionetasEstimadas"]
                .map(
                    lambda cantidad: (
                        "🟢 1 vehículo"
                        if cantidad == 1
                        else (
                            "🟡 2 vehículos"
                            if cantidad == 2
                            else f"🔴 {cantidad} vehículos"
                        )
                    )
                )
            )

            vista_camion_dashboard = (
                clientes_camion_dashboard
                .sort_values(
                    ["CamionetasEstimadas", "VolumenM3"],
                    ascending=[False, False],
                )
                .rename(
                    columns={
                        "ClienteCodigo": "Código cliente",
                        "ClienteDescripcion": "Cliente",
                        "PlanificacionDashboard": "Planificación",
                        "CantidadPedidos": "Cant. pedidos",
                        "VolumenM3": "Volumen m³",
                        "CamionetasEstimadas": "Vehículos estimados",
                    }
                )
            )

            st.dataframe(
                vista_camion_dashboard,
                width="stretch",
                hide_index=True,
                height=min(
                    330,
                    80 + len(vista_camion_dashboard) * 35,
                ),
                column_config={
                    "Pedidos": st.column_config.TextColumn(
                        "Pedidos",
                        width="large",
                    ),
                    "Cant. pedidos": st.column_config.NumberColumn(
                        "Cant. pedidos",
                        format="%d",
                    ),
                    "Volumen m³": st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.3f",
                    ),
                    "Unidades": st.column_config.NumberColumn(
                        "Unidades",
                        format="%d",
                    ),
                    "Vehículos estimados": (
                        st.column_config.NumberColumn(
                            "Vehículos estimados",
                            format="%d",
                        )
                    ),
                },
            )

        st.markdown("#### 🏬 Pedidos RETIRA")

        if base_retira_dashboard.empty:
            st.info(
                "No hay pedidos RETIRA con Estado Pendiente."
            )
        else:
            columnas_retira_dashboard = [
                "Pedido",
                "ClienteCodigo",
                "ClienteDescripcion",
                "PlanificacionDashboard",
                "UnidadesDashboard",
                "TotalSKUs",
                "VolumenDashboard",
                "CodigoDespacho",
            ]

            columnas_retira_dashboard = [
                columna
                for columna in columnas_retira_dashboard
                if columna in base_retira_dashboard.columns
            ]

            vista_retira_dashboard = (
                base_retira_dashboard[
                    columnas_retira_dashboard
                ]
                .sort_values(
                    ["ClienteDescripcion", "Pedido"],
                    ascending=[True, True],
                )
                .rename(
                    columns={
                        "ClienteCodigo": "Código cliente",
                        "ClienteDescripcion": "Cliente",
                        "PlanificacionDashboard": "Planificación",
                        "UnidadesDashboard": "Unidades",
                        "TotalSKUs": "SKUs",
                        "VolumenDashboard": "Volumen m³",
                        "CodigoDespacho": "Código despacho",
                    }
                )
            )

            st.dataframe(
                vista_retira_dashboard,
                width="stretch",
                hide_index=True,
                height=min(
                    330,
                    80 + len(vista_retira_dashboard) * 35,
                ),
                column_config={
                    "Unidades": st.column_config.NumberColumn(
                        "Unidades",
                        format="%d",
                    ),
                    "SKUs": st.column_config.NumberColumn(
                        "SKUs",
                        format="%d",
                    ),
                    "Volumen m³": st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.3f",
                    ),
                },
            )

    with panel_alertas:

        st.markdown("#### Controles operativos")

        if pedidos_retira_dashboard:
            st.info(
                f"{pedidos_retira_dashboard} pedido(s) RETIRA "
                "se excluyen del cálculo de transporte.",
                icon="🏬",
            )

        if pedidos_camion_dashboard:
            st.warning(
                f"{pedidos_camion_dashboard} pedido(s) superan "
                "la capacidad individual de una camioneta de 8 m³.",
                icon="🚛",
            )

        if sin_planificacion_dashboard:
            st.error(
                f"{sin_planificacion_dashboard} pedido(s) todavía "
                "no tienen planificación.",
                icon="⚠️",
            )

        if (
            pedidos_retira_dashboard == 0
            and pedidos_camion_dashboard == 0
            and sin_planificacion_dashboard == 0
        ):
            st.success(
                "La carga no presenta alertas operativas principales.",
                icon="✅",
            )

        st.info(
            "Capacidades de referencia: "
            "Camioneta 8 m³ · Camión 15 m³.",
            icon="📦",
        )

        st.metric(
            "Volumen total de reparto",
            f"{volumen_reparto_dashboard:,.2f} m³"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", "."),
        )

        st.caption(
            "Estimación teórica con base en la planificación actual. "
            "La asignación definitiva continúa en el Planificador."
        )



