import math
import pandas as pd
import altair as alt
import streamlit as st

from config import CARPETA_DATOS
from utils.confirmaciones_oc import guardar_confirmaciones_oc, eliminar_confirmaciones_oc
from utils.stock_helpers import dataframe_a_csv, formato_entero, aplicar_busqueda, dataframe_para_streamlit


def render(contexto: dict) -> None:
    tabla_pendientes_oc = contexto["tabla_pendientes_oc"]
    tabla_recepcion_agrupada = contexto["tabla_recepcion_agrupada"]
    tabla_stock_recepcion = contexto["tabla_stock_recepcion"]
    tabla_stock_total_articulo = contexto["tabla_stock_total_articulo"]
    tabla_stock_total_detallado = contexto["tabla_stock_total_detallado"]
    tabla_articulos = contexto["tabla_articulos"]
    tabla_volumetria = contexto["tabla_volumetria"]
    tabla_max_min = contexto["tabla_max_min"]
    confirmaciones_oc = contexto.get("confirmaciones_oc", pd.DataFrame())
    st.subheader("🏭 Existencia física")
    st.caption(
        "Centro de control del ingreso y la existencia física del depósito."
    )

    tab_recepcion, tab_stock_consolidado = st.tabs([
        "📥 Recepción",
        "📦 Stock consolidado",
    ])

    with tab_recepcion:
        st.markdown("### 📥 Pendientes de ingreso")
        st.caption(
            "Mercadería pendiente informada por COMEX. Se excluyen las líneas "
            "que ya tienen fecha de ingreso. La fecha estimada considera Puerto "
            "Buenos Aires + 7 días de gestión aduanera."
        )

        # -----------------------------------------------------
        # FILTROS GENERALES DE OC
        # -----------------------------------------------------
        base_fechas_oc = tabla_pendientes_oc.loc[
            tabla_pendientes_oc["FechaOperativaIngreso"].notna()
        ].copy()

        fecha_min_oc = (
            base_fechas_oc["FechaOperativaIngreso"].min().date()
            if not base_fechas_oc.empty else None
        )
        fecha_max_oc = (
            base_fechas_oc["FechaOperativaIngreso"].max().date()
            if not base_fechas_oc.empty else None
        )

        ordenes_disponibles = sorted(
            tabla_pendientes_oc["OrdenCompra"]
            .fillna("").astype(str).str.strip()
            .loc[lambda s: s.ne("")].drop_duplicates().tolist()
        ) if not tabla_pendientes_oc.empty else []

        familias_disponibles_oc = (
            tabla_pendientes_oc["Familia"]
            .fillna("").astype(str).str.strip()
            .loc[lambda s: s.ne("")].drop_duplicates().sort_values().tolist()
            if "Familia" in tabla_pendientes_oc.columns else []
        )

        prioridades_disponibles = [
            prioridad for prioridad in ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
            if prioridad in tabla_pendientes_oc.get(
                "SemaforoIngreso", pd.Series(dtype=str)
            ).astype(str).unique()
        ]

        with st.expander("🔎 Filtros y planificación de descarga", expanded=True):
            f1, f2, f3 = st.columns([1.35, 1.1, 1.1], vertical_alignment="bottom")
            with f1:
                rango_fechas_oc = st.date_input(
                    "Fecha operativa de ingreso",
                    value=(fecha_min_oc, fecha_max_oc)
                    if fecha_min_oc and fecha_max_oc else (),
                    min_value=fecha_min_oc,
                    max_value=fecha_max_oc,
                    key="rango_fecha_ingreso_oc",
                    help="Usa la fecha confirmada cuando existe; de lo contrario, la estimada.",
                )
            with f2:
                filtro_ordenes_oc = st.multiselect(
                    "Órdenes de compra",
                    options=ordenes_disponibles,
                    default=[],
                    key="filtro_ordenes_pendientes_oc",
                    placeholder="Todas las OC",
                    help="Seleccioná una o varias OC para planificar una jornada de descarga.",
                )
            with f3:
                filtro_familias_oc = st.multiselect(
                    "Familias",
                    options=familias_disponibles_oc,
                    default=[],
                    key="familias_pendientes_oc",
                    placeholder="Todas las familias",
                )

            f4, f5, f6 = st.columns([1.1, 1.1, 1], vertical_alignment="bottom")
            with f4:
                filtro_prioridades_general = st.multiselect(
                    "Prioridad",
                    options=prioridades_disponibles,
                    default=[],
                    key="prioridad_general_pendientes_oc",
                    placeholder="Todas las prioridades",
                )
            with f5:
                mostrar_sin_puerto = st.toggle(
                    "Mostrar líneas sin fecha de puerto",
                    value=False,
                    key="mostrar_oc_sin_fecha_puerto",
                )
            with f6:
                operarios_por_camion = st.selectbox(
                    "Operarios por camión",
                    options=[3, 4],
                    index=1,
                    key="operarios_por_camion_recepcion",
                    help="Regla operativa utilizada para estimar la dotación de descarga.",
                )

        vista_base_oc = tabla_pendientes_oc.copy()

        if not mostrar_sin_puerto and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["FechaPuertoBuenosAires"].notna()
            ].copy()
        if filtro_ordenes_oc and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["OrdenCompra"].astype(str).isin(filtro_ordenes_oc)
            ].copy()
        if filtro_familias_oc and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["Familia"].isin(filtro_familias_oc)
            ].copy()
        if filtro_prioridades_general and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["SemaforoIngreso"].isin(filtro_prioridades_general)
            ].copy()

        if (
            isinstance(rango_fechas_oc, (list, tuple))
            and len(rango_fechas_oc) == 2
            and not vista_base_oc.empty
        ):
            fecha_desde_oc = pd.Timestamp(rango_fechas_oc[0])
            fecha_hasta_oc = pd.Timestamp(rango_fechas_oc[1])
            mascara_fecha = vista_base_oc["FechaOperativaIngreso"].between(
                fecha_desde_oc, fecha_hasta_oc, inclusive="both"
            )
            if mostrar_sin_puerto:
                mascara_fecha = mascara_fecha | vista_base_oc["FechaOperativaIngreso"].isna()
            vista_base_oc = vista_base_oc.loc[mascara_fecha].copy()

        oc_pendientes = int(vista_base_oc["OrdenCompra"].nunique()) if not vista_base_oc.empty else 0
        sku_oc = int(vista_base_oc["ArticuloCodigo"].nunique()) if not vista_base_oc.empty else 0
        unidades_oc = float(vista_base_oc["CantidadPendiente"].sum()) if not vista_base_oc.empty else 0
        volumen_oc = float(vista_base_oc["VolumenTotalM3"].sum()) if not vista_base_oc.empty else 0
        sin_fecha_puerto = int(tabla_pendientes_oc["FechaPuertoBuenosAires"].isna().sum()) if not tabla_pendientes_oc.empty else 0
        atrasadas = int(vista_base_oc["EstadoIngreso"].eq("Atrasado").sum()) if not vista_base_oc.empty else 0
        prioritarias = int(vista_base_oc["SemaforoIngreso"].isin(["Sin stock", "Crítico"]).sum()) if not vista_base_oc.empty else 0
        stock_disponible_total = float(vista_base_oc["StockDisponibleActual"].sum()) if not vista_base_oc.empty else 0
        impacto_global = unidades_oc / stock_disponible_total * 100 if stock_disponible_total > 0 else 0

        resumen_camiones_oc = (
            vista_base_oc.groupby("OrdenCompra", as_index=False)
            .agg(VolumenOC=("VolumenTotalM3", "sum"))
            if not vista_base_oc.empty else pd.DataFrame(columns=["OrdenCompra", "VolumenOC"])
        )
        if not resumen_camiones_oc.empty:
            resumen_camiones_oc["CamionesEstimados"] = resumen_camiones_oc["VolumenOC"].map(
                lambda volumen: int(math.ceil(max(float(volumen), 0) / 45.0)) if float(volumen) > 0 else 0
            )
        camiones_estimados = int(resumen_camiones_oc.get("CamionesEstimados", pd.Series(dtype=int)).sum())
        operarios_sugeridos = int(camiones_estimados * int(operarios_por_camion))

        # -----------------------------------------------------
        # TARJETAS KPI — MISMO LENGUAJE VISUAL DEL SISTEMA
        # -----------------------------------------------------
        st.markdown(
            """
            <style>
            .recepcion-kpi-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                margin: 10px 0 18px 0;
            }
            .recepcion-kpi-card {
                min-height: 118px;
                padding: 15px 17px;
                border: 1px solid rgba(148, 163, 184, 0.22);
                border-radius: 11px;
                background: linear-gradient(145deg, #121923 0%, #0f151e 100%);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .recepcion-kpi-label {
                color: #d8dee9;
                font-size: 0.84rem;
                font-weight: 650;
            }
            .recepcion-kpi-value {
                color: #f8fafc;
                font-size: 1.82rem;
                font-weight: 750;
                line-height: 1.05;
                margin-top: 7px;
            }
            .recepcion-kpi-detail {
                color: #9ba8b7;
                font-size: 0.75rem;
                margin-top: 8px;
            }
            .recepcion-panel {
                border: 1px solid rgba(148, 163, 184, 0.20);
                border-radius: 12px;
                padding: 10px 14px 4px 14px;
                background: rgba(15, 23, 34, 0.58);
            }
            @media (max-width: 1100px) {
                .recepcion-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            @media (max-width: 650px) {
                .recepcion-kpi-grid { grid-template-columns: 1fr; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        def _fmt_m3(valor):
            return (
                f"{float(valor):,.2f} m³"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        tarjetas_recepcion = [
            ("📥 OC pendientes", formato_entero(oc_pendientes),
             f"{formato_entero(sku_oc)} SKU · {formato_entero(atrasadas)} líneas atrasadas"),
            ("📦 Unidades pendientes", formato_entero(unidades_oc),
             "Mercadería todavía sin ingreso"),
            ("📐 Volumen estimado", _fmt_m3(volumen_oc),
             "Carga física pendiente de recibir"),
            ("🚛 Camiones estimados", formato_entero(camiones_estimados),
             "Capacidad de referencia: 45 m³ por camión y por OC"),
            ("👷 Operarios sugeridos", formato_entero(operarios_sugeridos),
             f"{formato_entero(camiones_estimados)} camiones × {operarios_por_camion} operarios"),
            ("🚨 Prioridad alta / crítica", formato_entero(prioritarias),
             "Líneas que requieren planificación"),
            ("❔ Sin fecha de puerto", formato_entero(sin_fecha_puerto),
             "Ocultas salvo que se habiliten"),
            ("📊 Ingreso vs disponible", f"{impacto_global:.1f} %".replace(".", ","),
             "Peso del ingreso frente al stock actual"),
        ]

        html_kpis = '<div class="recepcion-kpi-grid">'
        for etiqueta, valor, detalle in tarjetas_recepcion:
            html_kpis += (
                '<div class="recepcion-kpi-card">'
                f'<div class="recepcion-kpi-label">{etiqueta}</div>'
                f'<div class="recepcion-kpi-value">{valor}</div>'
                f'<div class="recepcion-kpi-detail">{detalle}</div>'
                '</div>'
            )
        html_kpis += '</div>'
        st.markdown(html_kpis, unsafe_allow_html=True)

        with st.expander("📅 Confirmar fecha exacta de ingreso", expanded=False):
            st.caption(
                "La confirmación se aplica a toda la OC y se guarda en "
                "Confirmaciones_Ingreso_OC.csv, sin modificar el reporte de COMEX."
            )
            c1, c2 = st.columns([1.6, 1], vertical_alignment="bottom")
            with c1:
                oc_confirmar = st.multiselect(
                    "OC a confirmar",
                    options=ordenes_disponibles,
                    default=filtro_ordenes_oc,
                    key="oc_confirmar_fecha_ingreso",
                    placeholder="Seleccioná una o varias OC",
                )
            with c2:
                fecha_confirmacion = st.date_input(
                    "Fecha confirmada",
                    value=pd.Timestamp.today().date(),
                    key="fecha_confirmada_ingreso_oc",
                )

            usuario_confirmacion = str(
                st.session_state.get("usuario")
                or st.session_state.get("username")
                or st.session_state.get("nombre_usuario")
                or ""
            )
            b1, b2 = st.columns(2)
            with b1:
                guardar_fecha = st.button(
                    "💾 Guardar confirmación",
                    type="primary",
                    width="stretch",
                    disabled=not oc_confirmar,
                    key="guardar_fecha_confirmada_oc",
                )
            with b2:
                quitar_fecha = st.button(
                    "🗑️ Quitar confirmación",
                    width="stretch",
                    disabled=not oc_confirmar,
                    key="quitar_fecha_confirmada_oc",
                )

            if guardar_fecha:
                try:
                    resumen_guardado = guardar_confirmaciones_oc(
                        CARPETA_DATOS,
                        oc_confirmar,
                        fecha_confirmacion,
                        usuario_confirmacion,
                    )
                    st.success(
                        f"Fecha {fecha_confirmacion.strftime('%d/%m/%Y')} confirmada "
                        f"para {resumen_guardado['cantidad']} OC."
                    )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as error:
                    st.error(f"No se pudo guardar la confirmación: {error}")

            if quitar_fecha:
                try:
                    resumen_eliminado = eliminar_confirmaciones_oc(
                        CARPETA_DATOS,
                        oc_confirmar,
                    )
                    st.success(
                        f"Se quitaron {resumen_eliminado['cantidad']} confirmaciones."
                    )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as error:
                    st.error(f"No se pudo quitar la confirmación: {error}")

            confirmaciones_visibles = confirmaciones_oc.copy()
            if not confirmaciones_visibles.empty:
                st.dataframe(
                    dataframe_para_streamlit(confirmaciones_visibles),
                    hide_index=True,
                    width="stretch",
                    height=min(260, 75 + len(confirmaciones_visibles) * 34),
                    column_config={
                        "FechaConfirmadaIngreso": st.column_config.DateColumn(
                            "Fecha confirmada", format="DD/MM/YYYY"
                        ),
                        "FechaRegistro": st.column_config.DatetimeColumn(
                            "Registrado", format="DD/MM/YYYY HH:mm"
                        ),
                    },
                )

        if not vista_base_oc.empty:
            st.markdown("#### Lectura visual de los ingresos esperados")
            grafico_1, grafico_2 = st.columns(
                [1.05, 1],
                vertical_alignment="top",
            )

            with grafico_1:
                st.markdown("##### Evolución de OC esperadas")
                por_fecha = (
                    vista_base_oc.loc[
                        vista_base_oc["FechaOperativaIngreso"].notna()
                    ]
                    .groupby("FechaOperativaIngreso", as_index=False)
                    .agg(
                        Ordenes=("OrdenCompra", "nunique"),
                        Unidades=("CantidadPendiente", "sum"),
                        SKU=("ArticuloCodigo", "nunique"),
                        VolumenM3=("VolumenTotalM3", "sum"),
                    )
                    .sort_values("FechaOperativaIngreso")
                )

                if por_fecha.empty:
                    st.info("No hay fechas estimadas disponibles para graficar.")
                else:
                    por_fecha["FechaVisible"] = (
                        por_fecha["FechaOperativaIngreso"].dt.strftime("%d/%m")
                    )
                    orden_fechas = por_fecha["FechaVisible"].tolist()
                    por_fecha["EsMaximo"] = (
                        por_fecha["Ordenes"].eq(por_fecha["Ordenes"].max())
                    )

                    barras_oc = (
                        alt.Chart(por_fecha)
                        .mark_bar(
                            cornerRadiusTopLeft=5,
                            cornerRadiusTopRight=5,
                            size=26,
                        )
                        .encode(
                            x=alt.X(
                                "FechaVisible:N",
                                title=None,
                                sort=orden_fechas,
                                axis=alt.Axis(
                                    labelAngle=0,
                                    grid=False,
                                    labelColor="#CBD5E1",
                                    labelPadding=8,
                                    domainColor="#3B4655",
                                    tickColor="#3B4655",
                                ),
                            ),
                            y=alt.Y(
                                "Ordenes:Q",
                                title="Cantidad de OC",
                                scale=alt.Scale(zero=True),
                                axis=alt.Axis(
                                    tickMinStep=1,
                                    grid=True,
                                    gridColor="#26303D",
                                    labelColor="#CBD5E1",
                                    titleColor="#CBD5E1",
                                ),
                            ),
                            color=alt.condition(
                                alt.datum.EsMaximo,
                                alt.value("#2563EB"),
                                alt.value("#3B5F8A"),
                            ),
                            tooltip=[
                                alt.Tooltip("FechaVisible:N", title="Ingreso estimado"),
                                alt.Tooltip("Ordenes:Q", title="OC", format=",.0f"),
                                alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                                alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                                alt.Tooltip("VolumenM3:Q", title="Volumen m³", format=".2f"),
                            ],
                        )
                    )

                    etiquetas_oc = (
                        alt.Chart(por_fecha)
                        .mark_text(
                            align="center",
                            baseline="bottom",
                            dy=-7,
                            color="#F8FAFC",
                            fontSize=11,
                            fontWeight=700,
                        )
                        .encode(
                            x=alt.X("FechaVisible:N", sort=orden_fechas),
                            y="Ordenes:Q",
                            text=alt.Text("Ordenes:Q", format=",.0f"),
                        )
                    )

                    st.altair_chart(
                        (barras_oc + etiquetas_oc)
                        .properties(height=310)
                        .configure_view(strokeOpacity=0),
                        width="stretch",
                    )

            with grafico_2:
                st.markdown("##### Impacto esperado del ingreso")
                orden_prioridad = ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
                por_prioridad = (
                    vista_base_oc.groupby("SemaforoIngreso", as_index=False)
                    .agg(
                        Unidades=("CantidadPendiente", "sum"),
                        SKU=("ArticuloCodigo", "nunique"),
                    )
                )
                por_prioridad = por_prioridad.loc[
                    por_prioridad["SemaforoIngreso"].isin(orden_prioridad)
                ].copy()
                por_prioridad["Etiqueta"] = por_prioridad["Unidades"].map(
                    lambda valor: f"{int(valor):,}".replace(",", ".")
                )

                if por_prioridad.empty:
                    st.info("No hay prioridades disponibles para graficar.")
                else:
                    barras_prioridad = (
                        alt.Chart(por_prioridad)
                        .mark_bar(cornerRadiusEnd=5, size=24, color="#74B9E8")
                        .encode(
                            x=alt.X(
                                "Unidades:Q",
                                title="Unidades",
                                axis=alt.Axis(
                                    grid=True,
                                    gridColor="#26303D",
                                    labelColor="#CBD5E1",
                                    titleColor="#CBD5E1",
                                ),
                            ),
                            y=alt.Y(
                                "SemaforoIngreso:N",
                                title=None,
                                sort=orden_prioridad,
                                axis=alt.Axis(labelColor="#E2E8F0"),
                            ),
                            tooltip=[
                                alt.Tooltip("SemaforoIngreso:N", title="Prioridad"),
                                alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                                alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                            ],
                        )
                    )
                    etiquetas_prioridad = (
                        alt.Chart(por_prioridad)
                        .mark_text(
                            align="left",
                            baseline="middle",
                            dx=7,
                            color="#F8FAFC",
                            fontSize=11,
                            fontWeight=700,
                        )
                        .encode(
                            x="Unidades:Q",
                            y=alt.Y("SemaforoIngreso:N", sort=orden_prioridad),
                            text="Etiqueta:N",
                        )
                    )
                    st.altair_chart(
                        (barras_prioridad + etiquetas_prioridad)
                        .properties(height=310)
                        .configure_view(strokeOpacity=0),
                        width="stretch",
                    )

            st.markdown("##### OC con mayor volumen pendiente")
            por_oc = (
                vista_base_oc.groupby("OrdenCompra", as_index=False)
                .agg(
                    VolumenM3=("VolumenTotalM3", "sum"),
                    Unidades=("CantidadPendiente", "sum"),
                    SKU=("ArticuloCodigo", "nunique"),
                    FechaIngreso=("FechaOperativaIngreso", "min"),
                )
                .sort_values("VolumenM3", ascending=False)
                .head(10)
            )
            por_oc["OrdenCompra"] = por_oc["OrdenCompra"].astype(str)
            por_oc["EtiquetaVolumen"] = por_oc["VolumenM3"].map(
                lambda valor: f"{valor:.2f} m³".replace(".", ",")
            )
            por_oc["EsMaximo"] = por_oc["VolumenM3"].eq(por_oc["VolumenM3"].max())

            barras_oc_volumen = (
                alt.Chart(por_oc)
                .mark_bar(cornerRadiusEnd=5, size=22)
                .encode(
                    x=alt.X(
                        "VolumenM3:Q",
                        title="Volumen pendiente m³",
                        axis=alt.Axis(
                            grid=True,
                            gridColor="#26303D",
                            labelColor="#CBD5E1",
                            titleColor="#CBD5E1",
                        ),
                    ),
                    y=alt.Y(
                        "OrdenCompra:N",
                        title="OC",
                        sort="-x",
                        axis=alt.Axis(labelColor="#E2E8F0"),
                    ),
                    color=alt.condition(
                        alt.datum.EsMaximo,
                        alt.value("#2563EB"),
                        alt.value("#74B9E8"),
                    ),
                    tooltip=[
                        alt.Tooltip("OrdenCompra:N", title="OC"),
                        alt.Tooltip("VolumenM3:Q", title="Volumen m³", format=".2f"),
                        alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                        alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                        alt.Tooltip("FechaIngreso:T", title="Ingreso", format="%d/%m/%Y"),
                    ],
                )
            )
            etiquetas_oc_volumen = (
                alt.Chart(por_oc)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=7,
                    color="#F8FAFC",
                    fontSize=11,
                    fontWeight=700,
                )
                .encode(
                    x="VolumenM3:Q",
                    y=alt.Y("OrdenCompra:N", sort="-x"),
                    text="EtiquetaVolumen:N",
                )
            )
            st.altair_chart(
                (barras_oc_volumen + etiquetas_oc_volumen)
                .properties(height=max(260, len(por_oc) * 34))
                .configure_view(strokeOpacity=0),
                width="stretch",
            )

        if not resumen_camiones_oc.empty:
            st.markdown("#### Planificación de descarga por OC")
            resumen_descarga = (
                vista_base_oc.groupby("OrdenCompra", as_index=False)
                .agg(
                    FechaOperativa=("FechaOperativaIngreso", "min"),
                    TipoFecha=("TipoFechaIngreso", "first"),
                    SKU=("ArticuloCodigo", "nunique"),
                    Unidades=("CantidadPendiente", "sum"),
                    VolumenM3=("VolumenTotalM3", "sum"),
                    PrioridadAltaCritica=("SemaforoIngreso", lambda s: int(s.isin(["Sin stock", "Crítico"]).sum())),
                )
            )
            resumen_descarga["Camiones"] = resumen_descarga["VolumenM3"].map(
                lambda volumen: int(math.ceil(max(float(volumen), 0) / 45.0)) if float(volumen) > 0 else 0
            )
            resumen_descarga["Operarios"] = (
                resumen_descarga["Camiones"]
                * int(operarios_por_camion)
            ).astype(int)
            resumen_descarga = resumen_descarga.sort_values(
                ["FechaOperativa", "Camiones", "VolumenM3"],
                ascending=[True, False, False],
                na_position="last",
            )
            st.dataframe(
                dataframe_para_streamlit(resumen_descarga),
                hide_index=True,
                width="stretch",
                height=min(360, 80 + len(resumen_descarga) * 35),
                column_config={
                    "FechaOperativa": st.column_config.DateColumn("Ingreso", format="DD/MM/YYYY"),
                    "VolumenM3": st.column_config.NumberColumn("Volumen m³", format="%.2f"),
                    "Camiones": st.column_config.NumberColumn("Camiones (45 m³)", format="%d"),
                    "Operarios": st.column_config.NumberColumn("Operarios sugeridos", format="%d"),
                },
            )

        st.markdown("#### Detalle operativo de OC pendientes")
        filtro_oc_1, filtro_oc_2, filtro_oc_3 = st.columns([2, 1, 1])
        with filtro_oc_1:
            buscar_oc = st.text_input(
                "Buscar en pendientes de OC",
                key="buscar_pendientes_oc",
                placeholder="OC, código, descripción, proforma...",
            )
        with filtro_oc_2:
            estados_oc = sorted(vista_base_oc["EstadoIngreso"].dropna().unique().tolist()) if not vista_base_oc.empty else []
            filtro_estado_oc = st.multiselect(
                "Estado de ingreso", estados_oc, key="estado_pendientes_oc"
            )
        with filtro_oc_3:
            prioridades_oc = [
                p for p in ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
                if p in vista_base_oc.get("SemaforoIngreso", pd.Series(dtype=str)).unique()
            ]
            filtro_prioridad_oc = st.multiselect(
                "Prioridad", prioridades_oc, key="prioridad_pendientes_oc"
            )

        vista_oc = aplicar_busqueda(vista_base_oc, buscar_oc)
        if filtro_estado_oc:
            vista_oc = vista_oc.loc[vista_oc["EstadoIngreso"].isin(filtro_estado_oc)]
        if filtro_prioridad_oc:
            vista_oc = vista_oc.loc[vista_oc["SemaforoIngreso"].isin(filtro_prioridad_oc)]

        columnas_oc_vista = [
            "OrdenCompra", "ArticuloCodigo", "ArticuloDescripcion", "Familia",
            "CantidadPendiente", "FechaPuertoBuenosAires", "FechaIngresoEstimada",
            "FechaConfirmadaIngreso", "FechaOperativaIngreso", "EstadoFechaIngreso",
            "StockDisponibleActual", "PorcentajeSobreTotal",
            "PorcentajeSobreStockActual", "SemaforoIngreso", "AccionRecomendada",
            "VolumenTotalM3", "EstadoOC", "Proforma",
        ]
        columnas_oc_vista = [c for c in columnas_oc_vista if c in vista_oc.columns]

        st.download_button(
            "⬇️ Descargar pendientes de OC",
            data=dataframe_a_csv(vista_oc),
            file_name="Pendientes_OC_Enriquecidos.csv",
            mime="text/csv",
            key="descargar_pendientes_oc_enriquecidos",
        )
        st.dataframe(
            dataframe_para_streamlit(vista_oc[columnas_oc_vista]),
            hide_index=True,
            width="stretch",
            height=460,
            column_config={
                "OrdenCompra": st.column_config.TextColumn("Orden"),
                "ArticuloCodigo": st.column_config.TextColumn("Artículo"),
                "ArticuloDescripcion": st.column_config.TextColumn("Descripción"),
                "CantidadPendiente": st.column_config.NumberColumn("Cant.", format="%d"),
                "FechaPuertoBuenosAires": st.column_config.DateColumn("Puerto Bs.As.", format="DD/MM/YYYY"),
                "FechaIngresoEstimada": st.column_config.DateColumn("Estimado", format="DD/MM/YYYY"),
                "FechaConfirmadaIngreso": st.column_config.DateColumn("Confirmado", format="DD/MM/YYYY"),
                "FechaOperativaIngreso": st.column_config.DateColumn("Fecha operativa", format="DD/MM/YYYY"),
                "StockDisponibleActual": st.column_config.NumberColumn("Disponible", format="%d"),
                "PorcentajeSobreTotal": st.column_config.ProgressColumn(
                    "% sobre total", min_value=0, max_value=100, format="%.1f %%"
                ),
                "PorcentajeSobreStockActual": st.column_config.NumberColumn(
                    "% sobre actual", format="%.1f %%"
                ),
                "SemaforoIngreso": st.column_config.TextColumn("Semáforo"),
                "AccionRecomendada": st.column_config.TextColumn("Acción"),
                "VolumenTotalM3": st.column_config.NumberColumn("Vol. m³", format="%.2f"),
            },
        )

        st.markdown("---")
        st.markdown("### 📦 Mercadería recibida pendiente de guardar")
        st.caption(
            "Stock ya ingresado al WMS y ubicado en Recepción, agrupado por artículo."
        )

        unidades_rec = tabla_recepcion_agrupada["UnidadesRecepcion"].sum() if not tabla_recepcion_agrupada.empty else 0
        contenedores_rec = tabla_recepcion_agrupada["Contenedores"].sum() if not tabla_recepcion_agrupada.empty else 0
        sku_rec = tabla_recepcion_agrupada["ArticuloCodigo"].nunique() if not tabla_recepcion_agrupada.empty else 0
        volumen_rec = tabla_recepcion_agrupada["VolumenTotalM3"].sum() if not tabla_recepcion_agrupada.empty else 0

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Unidades en Recepción", formato_entero(unidades_rec))
        r2.metric("Contenedores", formato_entero(contenedores_rec))
        r3.metric("SKU", formato_entero(sku_rec))
        r4.metric("Volumen pendiente", f"{volumen_rec:,.2f} m³".replace(",", "X").replace(".", ",").replace("X", "."))

        buscar_rec = st.text_input(
            "Buscar en recepción", key="buscar_recepcion_agrupada",
            placeholder="Código, descripción, familia...",
        )
        vista_rec = aplicar_busqueda(tabla_recepcion_agrupada, buscar_rec)
        st.download_button(
            "⬇️ Descargar recepción agrupada",
            data=dataframe_a_csv(vista_rec),
            file_name="Stock_Recepcion_Agrupado.csv",
            mime="text/csv",
            key="descargar_recepcion_agrupada",
        )
        st.dataframe(
            vista_rec, hide_index=True, width="stretch", height=430,
            column_config={
                "UnidadesRecepcion": st.column_config.NumberColumn("Unidades", format="%d"),
                "Contenedores": st.column_config.NumberColumn("Contenedores", format="%d"),
                "VolumenTotalM3": st.column_config.NumberColumn("Volumen total m³", format="%.3f"),
                "PesoTotalKg": st.column_config.NumberColumn("Peso total kg", format="%.2f"),
                "CoberturaMaximoPickingPorcentaje": st.column_config.ProgressColumn(
                    "% del máximo picking", min_value=0, max_value=100, format="%.1f %%"
                ),
                "VencimientoMasProximo": st.column_config.DateColumn("Vencimiento próximo", format="DD/MM/YYYY"),
            },
        )

    with tab_stock_consolidado:
        st.markdown("### 🏭 Stock físico consolidado")
        st.caption(
            "Existencia física consolidada considerando Almacén/Picking y Recepción."
        )
        total_fisico = tabla_stock_total_articulo["StockFisicoTotal"].sum()
        total_almacen = tabla_stock_total_articulo["StockAlmacenPicking"].sum()
        total_recepcion = tabla_stock_total_articulo["StockRecepcion"].sum()
        articulos_stock = tabla_stock_total_articulo.loc[
            tabla_stock_total_articulo["StockFisicoTotal"].gt(0), "ArticuloCodigo"
        ].nunique()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Stock físico total", formato_entero(total_fisico))
        k2.metric("Almacén + Picking", formato_entero(total_almacen))
        k3.metric("Recepción", formato_entero(total_recepcion))
        k4.metric("Artículos con stock", formato_entero(articulos_stock))

        filtro_codigo = st.text_input(
            "Buscar artículo", key="buscar_stock_total_articulo",
            placeholder="Código o descripción...",
        )
        resumen_vista = aplicar_busqueda(tabla_stock_total_articulo, filtro_codigo)
        st.download_button(
            "⬇️ Descargar resumen", data=dataframe_a_csv(resumen_vista),
            file_name="Stock_Fisico_Por_Articulo.csv", mime="text/csv",
            key="descargar_stock_total_articulo",
        )
        st.dataframe(dataframe_para_streamlit(resumen_vista), hide_index=True, width="stretch", height=500)

        with st.expander("🔎 Ver detalle físico unificado"):
            filtro_detalle = st.text_input(
                "Buscar en el detalle físico", key="buscar_stock_total_detallado",
                placeholder="Código, descripción, área, ubicación o contenedor...",
            )
            detalle_vista = aplicar_busqueda(tabla_stock_total_detallado, filtro_detalle)
            st.dataframe(dataframe_para_streamlit(detalle_vista), hide_index=True, width="stretch", height=540)



