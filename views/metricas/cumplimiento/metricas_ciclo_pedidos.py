from __future__ import annotations

from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.metricas.metricas_helpers import formatear_entero, limitar_previsualizacion
from models.cumplimiento.indicadores_servicio import calcular_indicadores_servicio
from views.metricas.cumplimiento.metricas_fillrate import render as render_fillrate


def _fecha_en_rango(valor, fecha_minima, fecha_maxima):
    try:
        fecha = pd.Timestamp(valor).date()
    except Exception:
        return fecha_minima
    return min(max(fecha, fecha_minima), fecha_maxima)


def _normalizar_rango_guardado(fecha_minima, fecha_maxima):
    desde = _fecha_en_rango(
        st.session_state.get("ciclo_aplicado_fecha_desde", fecha_minima),
        fecha_minima,
        fecha_maxima,
    )
    hasta = _fecha_en_rango(
        st.session_state.get("ciclo_aplicado_fecha_hasta", fecha_maxima),
        fecha_minima,
        fecha_maxima,
    )
    if desde > hasta:
        desde, hasta = fecha_minima, fecha_maxima
    st.session_state["ciclo_aplicado_fecha_desde"] = desde
    st.session_state["ciclo_aplicado_fecha_hasta"] = hasta
    return desde, hasta


def _porcentaje(valor: float, total: float) -> str:
    return f"{float(valor) / max(float(total), 1) * 100:.1f}%"


def _opciones(tabla: pd.DataFrame, columna: str) -> list[str]:
    if columna not in tabla.columns:
        return []
    return sorted(
        tabla[columna]
        .fillna("")
        .astype(str)
        .str.strip()
        .loc[lambda serie: serie.ne("")]
        .unique()
        .tolist()
    )


def _render_otif(contexto: dict) -> None:
    df_ciclo = contexto.get("df_ciclo_pedidos", pd.DataFrame())
    df_excluidos = contexto.get("df_ciclo_excluidos", pd.DataFrame())
    diagnostico = contexto.get("diagnostico_ciclo", {})
    error = contexto.get("error_ciclo_pedidos")

    st.markdown("### 🧭 Ciclo de vida y cumplimiento del pedido")
    st.caption(
        "Universo basado exclusivamente en pedidos cerrados de Pedidos DIGIP, "
        "enriquecido con preparación, control, hoja de ruta y planificación comercial. "
        "Esta tabla será el motor de OTIF, Fill Rate, lead times, cumplimiento y alertas."
    )

    if error is not None:
        st.error("No se pudo construir la Base Analítica de Pedidos.")
        st.exception(error)
        return

    if df_ciclo.empty:
        st.warning(
            "Todavía no hay registros para construir el ciclo. Verificá Pedidos "
            "DIGIP, Hojas de Ruta, históricos de proceso y Maestro Clientes."
        )
        return

    with st.expander("ℹ️ Reglas activas del motor", expanded=False):
        st.markdown(
            """
            - **Universo maestro:** únicamente pedidos cerrados/completos existentes en Pedidos DIGIP.
            - Preparación, Control, Filtrar Preparación y Hoja de Ruta solo enriquecen la base; no agregan pedidos nuevos.
            - **Ciclo vigente:** el pedido debe haber sido creado al menos 24 horas antes del inicio de preparación.
            - **Zona:** usa directamente los días de `Preparacion2` y `Entrega` del Maestro Clientes.
            - **Diario:** puede salir cualquier día; la entrega final se evalúa dentro de 72 horas desde la creación.
            - **Expreso:** entrega objetivo a las 96 horas corridas desde la creación.
            - **Con turno:** se conserva en la base, pero queda excluido del universo OTIF.
            - Los clientes sin cruce o sin planificación válida se identifican para corregir el maestro.
            - **Maduración:** los pedidos controlados en las últimas 48 horas esperan la próxima salida y no afectan todavía los indicadores.
            - **Pedidos internos:** códigos que comienzan con `TR` o `RM` se eliminan del universo de servicio.
            - **Anulados operativos:** pedidos cerrados en DIGIP sin cierre de Preparación ni Control se excluyen del análisis.
            """
        )

    # ======================================================
    # DEPURACIÓN DEL UNIVERSO DE SERVICIO
    # ======================================================
    depurados_total = int(diagnostico.get("universo_pedidos_excluidos", 0) or 0)
    internos_total = int(diagnostico.get("universo_pedidos_internos", 0) or 0)
    anulados_total = int(diagnostico.get("universo_pedidos_anulados_operativos", 0) or 0)
    maduracion_total = int(diagnostico.get("universo_pedidos_en_maduracion_48h", 0) or 0)

    st.markdown("#### Depuración automática del universo")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Fuera del análisis", formatear_entero(depurados_total))
    d2.metric("Internos TR / RM", formatear_entero(internos_total), "Eliminados")
    d3.metric("Anulados operativos", formatear_entero(anulados_total), "Sin cierre de etapas")
    d4.metric("En maduración · 48 h", formatear_entero(maduracion_total), "Esperando próxima salida")

    if not df_excluidos.empty:
        with st.expander("🔎 Ver diagnóstico de pedidos excluidos", expanded=False):
            columnas_excluidos = [
                columna for columna in [
                    "Pedido", "ClienteFinal", "ClienteCodigo",
                    "FechaHoraCreacion", "FechaHoraFinPreparacion",
                    "FechaHoraFinControl", "FechaDisponibleAnalisis",
                    "MotivoExclusionServicio", "HorasDesdeFinControl",
                ]
                if columna in df_excluidos.columns
            ]
            st.dataframe(
                limitar_previsualizacion(
                    df_excluidos[columnas_excluidos],
                    limite=2000,
                ),
                width="stretch",
                hide_index=True,
                column_config={
                    "FechaHoraCreacion": st.column_config.DatetimeColumn(
                        "Creación", format="DD/MM/YYYY HH:mm"
                    ),
                    "FechaHoraFinPreparacion": st.column_config.DatetimeColumn(
                        "Fin preparación", format="DD/MM/YYYY HH:mm"
                    ),
                    "FechaHoraFinControl": st.column_config.DatetimeColumn(
                        "Fin control", format="DD/MM/YYYY HH:mm"
                    ),
                    "FechaDisponibleAnalisis": st.column_config.DatetimeColumn(
                        "Disponible para análisis", format="DD/MM/YYYY HH:mm"
                    ),
                    "HorasDesdeFinControl": st.column_config.NumberColumn(
                        "Horas desde control", format="%.1f h"
                    ),
                },
            )

    st.divider()

    # ======================================================
    # FECHA DE REFERENCIA PARA FILTRAR EL CICLO
    # ======================================================
    # Se prioriza la creación. Cuando ese dato falta, se utiliza
    # el primer hito operativo disponible para que los pedidos
    # incompletos no desaparezcan del análisis.
    columnas_fecha_referencia = [
        "FechaHoraCreacion",
        "FechaHoraInicioPreparacion",
        "FechaHoraFinPreparacion",
        "FechaHoraInicioControl",
        "FechaHoraFinControl",
        "FechaHoraPrimeraHojaRuta",
    ]

    fecha_referencia = pd.Series(pd.NaT, index=df_ciclo.index, dtype="datetime64[ns]")
    for columna in columnas_fecha_referencia:
        if columna in df_ciclo.columns:
            fecha_referencia = fecha_referencia.combine_first(
                pd.to_datetime(df_ciclo[columna], errors="coerce")
            )

    df_ciclo = df_ciclo.copy()
    df_ciclo["FechaReferenciaFiltro"] = fecha_referencia

    fechas_validas = fecha_referencia.dropna()
    if fechas_validas.empty:
        fecha_minima = pd.Timestamp.today().normalize().date()
        fecha_maxima = fecha_minima
    else:
        fecha_minima = fechas_validas.min().date()
        fecha_maxima = fechas_validas.max().date()

    defaults_aplicados = {
        "ciclo_aplicado_fecha_desde": fecha_minima,
        "ciclo_aplicado_fecha_hasta": fecha_maxima,
        "ciclo_aplicado_circuitos": [],
        "ciclo_aplicado_grupos": [],
        "ciclo_aplicado_estados_plan": [],
        "ciclo_aplicado_etapas": [],
        "ciclo_aplicado_busqueda": "",
        "ciclo_aplicado_solo_otif": False,
        "ciclo_aplicado_solo_incompletos": False,
    }
    for clave, valor in defaults_aplicados.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor

    # Corrige tipos y rangos guardados antes de crear el widget. Esto evita
    # que date_input reutilice un valor obsoleto después de Actualizar.
    fecha_desde_guardada, fecha_hasta_guardada = _normalizar_rango_guardado(
        fecha_minima,
        fecha_maxima,
    )

    rango_widget = st.session_state.get("ciclo_borrador_rango_fechas")
    if not isinstance(rango_widget, (tuple, list)) or len(rango_widget) != 2:
        st.session_state["ciclo_borrador_rango_fechas"] = (
            fecha_desde_guardada,
            fecha_hasta_guardada,
        )
    else:
        st.session_state["ciclo_borrador_rango_fechas"] = (
            _fecha_en_rango(rango_widget[0], fecha_minima, fecha_maxima),
            _fecha_en_rango(rango_widget[1], fecha_minima, fecha_maxima),
        )

    with st.form(
        "form_filtros_ciclo_pedidos",
        clear_on_submit=False,
        border=True,
    ):
        fila_fecha, fila_circuito, fila_grupo, fila_plan = st.columns(
            [1.25, 1.0, 1.1, 1.1],
            vertical_alignment="bottom",
        )

        rango_fechas = fila_fecha.date_input(
            "Período de referencia",
            min_value=fecha_minima,
            max_value=fecha_maxima,
            key="ciclo_borrador_rango_fechas",
            help=(
                "Usa la fecha de creación y, cuando falta, el primer hito "
                "disponible de preparación, control u hoja de ruta."
            ),
        )
        circuitos = fila_circuito.multiselect(
            "Circuito",
            _opciones(df_ciclo, "TipoCircuito"),
            default=st.session_state["ciclo_aplicado_circuitos"],
            placeholder="Todos",
            key="ciclo_borrador_circuitos",
        )
        grupos = fila_grupo.multiselect(
            "Grupo de entrega",
            _opciones(df_ciclo, "GrupoEntrega"),
            default=st.session_state["ciclo_aplicado_grupos"],
            placeholder="Todos",
            key="ciclo_borrador_grupos",
        )
        estados_plan = fila_plan.multiselect(
            "Planificación",
            _opciones(df_ciclo, "EstadoPlanificacion"),
            default=st.session_state["ciclo_aplicado_estados_plan"],
            placeholder="Todas",
            key="ciclo_borrador_estados_plan",
        )

        fila_etapa, fila_busqueda = st.columns([1.05, 2.2])
        etapas = fila_etapa.multiselect(
            "Última etapa",
            _opciones(df_ciclo, "UltimaEtapaRegistrada"),
            default=st.session_state["ciclo_aplicado_etapas"],
            placeholder="Todas",
            key="ciclo_borrador_etapas",
        )
        busqueda = fila_busqueda.text_input(
            "Buscar pedido o cliente",
            value=st.session_state["ciclo_aplicado_busqueda"],
            placeholder="Ej.: 202684, código o nombre del cliente",
            key="ciclo_borrador_busqueda",
        )

        opciones = st.columns([1.2, 1.2, 4])
        solo_universo_otif = opciones[0].checkbox(
            "Solo universo OTIF",
            value=bool(st.session_state["ciclo_aplicado_solo_otif"]),
            key="ciclo_borrador_solo_otif",
        )
        solo_incompletos = opciones[1].checkbox(
            "Solo ciclos incompletos",
            value=bool(st.session_state["ciclo_aplicado_solo_incompletos"]),
            key="ciclo_borrador_solo_incompletos",
        )

        aplicar_col, borrar_col, _ = st.columns([1, 1, 5])
        aplicar_filtros = aplicar_col.form_submit_button(
            "✅ Aplicar filtros",
            type="primary",
            width="stretch",
        )
        borrar_filtros = borrar_col.form_submit_button(
            "🧹 Borrar filtros",
            width="stretch",
        )

    if borrar_filtros:
        for clave, valor in defaults_aplicados.items():
            st.session_state[clave] = valor
        for clave in [
            "ciclo_borrador_rango_fechas",
            "ciclo_borrador_circuitos",
            "ciclo_borrador_grupos",
            "ciclo_borrador_estados_plan",
            "ciclo_borrador_etapas",
            "ciclo_borrador_busqueda",
            "ciclo_borrador_solo_otif",
            "ciclo_borrador_solo_incompletos",
        ]:
            st.session_state.pop(clave, None)
        st.rerun()

    if aplicar_filtros:
        if isinstance(rango_fechas, (tuple, list)) and len(rango_fechas) == 2:
            fecha_desde_aplicada, fecha_hasta_aplicada = rango_fechas
        else:
            fecha_desde_aplicada = fecha_minima
            fecha_hasta_aplicada = fecha_maxima

        st.session_state["ciclo_aplicado_fecha_desde"] = fecha_desde_aplicada
        st.session_state["ciclo_aplicado_fecha_hasta"] = fecha_hasta_aplicada
        st.session_state["ciclo_aplicado_circuitos"] = circuitos
        st.session_state["ciclo_aplicado_grupos"] = grupos
        st.session_state["ciclo_aplicado_estados_plan"] = estados_plan
        st.session_state["ciclo_aplicado_etapas"] = etapas
        st.session_state["ciclo_aplicado_busqueda"] = busqueda
        st.session_state["ciclo_aplicado_solo_otif"] = bool(solo_universo_otif)
        st.session_state["ciclo_aplicado_solo_incompletos"] = bool(solo_incompletos)
        st.rerun()

    fecha_desde = st.session_state["ciclo_aplicado_fecha_desde"]
    fecha_hasta = st.session_state["ciclo_aplicado_fecha_hasta"]
    circuitos_aplicados = st.session_state["ciclo_aplicado_circuitos"]
    grupos_aplicados = st.session_state["ciclo_aplicado_grupos"]
    estados_plan_aplicados = st.session_state["ciclo_aplicado_estados_plan"]
    etapas_aplicadas = st.session_state["ciclo_aplicado_etapas"]
    busqueda_aplicada = st.session_state["ciclo_aplicado_busqueda"]
    solo_universo_otif_aplicado = st.session_state["ciclo_aplicado_solo_otif"]
    solo_incompletos_aplicado = st.session_state["ciclo_aplicado_solo_incompletos"]

    visible = df_ciclo.copy()
    fecha_inicio = pd.Timestamp(fecha_desde)
    fecha_fin = pd.Timestamp(fecha_hasta) + pd.Timedelta(days=1)
    visible = visible.loc[
        visible["FechaReferenciaFiltro"].notna()
        & visible["FechaReferenciaFiltro"].ge(fecha_inicio)
        & visible["FechaReferenciaFiltro"].lt(fecha_fin)
    ].copy()

    if circuitos_aplicados:
        visible = visible.loc[visible["TipoCircuito"].isin(circuitos_aplicados)].copy()
    if grupos_aplicados:
        visible = visible.loc[visible["GrupoEntrega"].isin(grupos_aplicados)].copy()
    if estados_plan_aplicados:
        visible = visible.loc[visible["EstadoPlanificacion"].isin(estados_plan_aplicados)].copy()
    if etapas_aplicadas:
        visible = visible.loc[visible["UltimaEtapaRegistrada"].isin(etapas_aplicadas)].copy()
    if solo_universo_otif_aplicado and "AplicaOTIFBase" in visible.columns:
        visible = visible.loc[visible["AplicaOTIFBase"].fillna(False)].copy()
    if solo_incompletos_aplicado:
        columnas_hitos = [
            columna for columna in ["TieneCreacion", "TienePreparacion", "TieneControl", "TieneHojaRuta"]
            if columna in visible.columns
        ]
        if columnas_hitos:
            visible = visible.loc[~visible[columnas_hitos].fillna(False).all(axis=1)].copy()

    if str(busqueda_aplicada).strip():
        patron = str(busqueda_aplicada).strip()
        mascara = pd.Series(False, index=visible.index)
        for columna in [
            "Pedido", "ClienteFinal", "ClienteMaestro", "ClienteCodigo",
            "ClienteCodigoHR", "CodigoEntrega", "CodigoDespacho",
            "CodigoLogisticoMaestro",
        ]:
            if columna in visible.columns:
                mascara |= visible[columna].fillna("").astype(str).str.contains(
                    patron, case=False, na=False, regex=False
                )
        visible = visible.loc[mascara].copy()

    st.caption(
        f"Filtros aplicados: {pd.Timestamp(fecha_desde).strftime('%d/%m/%Y')} "
        f"al {pd.Timestamp(fecha_hasta).strftime('%d/%m/%Y')}"
    )

    # ======================================================
    # MOTOR DE CUMPLIMIENTO SOBRE LA BASE FILTRADA
    # ======================================================
    visible, diagnostico_servicio = calcular_indicadores_servicio(visible)

    evaluados = int(diagnostico_servicio.get("evaluados", 0) or 0)
    cumplen = int(diagnostico_servicio.get("cumplen", 0) or 0)
    no_cumplen = int(diagnostico_servicio.get("no_cumplen", 0) or 0)
    otif_total = float(diagnostico_servicio.get("otif_pct", 0) or 0)
    lead_time_promedio = float(
        diagnostico_servicio.get("lead_time_promedio_horas", 0) or 0
    )
    atraso_promedio = float(
        diagnostico_servicio.get("atraso_promedio_horas", 0) or 0
    )

    # ======================================================
    # DONUTS DE CUMPLIMIENTO POR CIRCUITO
    # ======================================================
    circuitos_objetivo = ["ZONA", "EXPRESO", "RETIRA", "DIARIO"]

    def renderizar_fila_donuts(
        titulo: str,
        columna_aplica: str,
        columna_cumple: str,
        etiqueta_centro: str,
    ) -> None:
        st.markdown(f"#### {titulo}")
        columnas_donut = st.columns(4, gap="small")

        for columna, circuito in zip(columnas_donut, circuitos_objetivo):
            with columna:
                base_circuito = visible.loc[
                    visible.get(
                        "CircuitoOTIF",
                        pd.Series("", index=visible.index),
                    ).eq(circuito)
                    & visible.get(
                        columna_aplica,
                        pd.Series(False, index=visible.index),
                    ).fillna(False)
                ].copy()

                total_circuito = len(base_circuito)
                cumplen_circuito = int(
                    base_circuito.get(
                        columna_cumple,
                        pd.Series(False, index=base_circuito.index),
                    ).fillna(False).sum()
                )
                porcentaje_circuito = (
                    cumplen_circuito / total_circuito * 100
                    if total_circuito else 0.0
                )

                datos_donut = pd.DataFrame(
                    {
                        "Estado": ["Cumple", "No cumple"],
                        "Pedidos": [
                            cumplen_circuito,
                            max(total_circuito - cumplen_circuito, 0),
                        ],
                    }
                )

                with st.container(border=True):
                    st.markdown(f"##### {circuito}")
                    if total_circuito:
                        figura = px.pie(
                            datos_donut,
                            names="Estado",
                            values="Pedidos",
                            hole=0.68,
                            color="Estado",
                            color_discrete_map={
                                "Cumple": "#22C55E",
                                "No cumple": "#EF4444",
                            },
                        )
                        figura.update_traces(
                            textinfo="none",
                            hovertemplate=(
                                "%{label}: %{value} pedidos "
                                "(%{percent})<extra></extra>"
                            ),
                        )
                        figura.add_annotation(
                            text=(
                                f"<b>{porcentaje_circuito:.1f}%</b>"
                                f"<br>{etiqueta_centro}"
                            ),
                            x=0.5,
                            y=0.5,
                            showarrow=False,
                            font=dict(size=19),
                        )
                        figura.update_layout(
                            template="plotly_dark",
                            height=245,
                            margin=dict(l=2, r=2, t=4, b=2),
                            paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)",
                            showlegend=False,
                        )
                        st.plotly_chart(
                            figura,
                            width="stretch",
                            config={"displaylogo": False},
                            key=(
                                f"donut_{columna_cumple.lower()}_"
                                f"{circuito.lower()}"
                            ),
                        )
                        st.caption(
                            f"{cumplen_circuito:,} de "
                            f"{total_circuito:,} pedidos"
                        )
                    else:
                        st.info("Sin pedidos evaluables en el período.")

    renderizar_fila_donuts(
        "Cumplimiento OTIF final por circuito",
        "AplicaOTIF",
        "CumpleOTIF",
        "OTIF final",
    )

    renderizar_fila_donuts(
        "Cumplimiento del ciclo Preparación + Control por circuito",
        "AplicaPreparacionOTIF",
        "CumplePreparacionOTIF",
        "Prep. + Control",
    )

    preparacion_evaluados = int(
        diagnostico_servicio.get("preparacion_evaluados", 0) or 0
    )
    preparacion_cumplen = int(
        diagnostico_servicio.get("preparacion_cumplen", 0) or 0
    )
    preparacion_no_cumplen = int(
        diagnostico_servicio.get("preparacion_no_cumplen", 0) or 0
    )
    preparacion_otif = float(
        diagnostico_servicio.get("preparacion_otif_pct", 0) or 0
    )
    preparacion_lead_time = float(
        diagnostico_servicio.get(
            "preparacion_lead_time_promedio_horas",
            0,
        ) or 0
    )
    demora_posterior = int(
        diagnostico_servicio.get("demora_posterior_preparacion", 0) or 0
    )
    referencia_provisoria = int(
        diagnostico_servicio.get(
            "referencia_provisoria_inicio_preparacion",
            0,
        ) or 0
    )

    st.markdown("#### Indicadores de cumplimiento")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("OTIF final", f"{otif_total:.1f}%")
    k2.metric("OTIF Prep. + Control", f"{preparacion_otif:.1f}%")
    k3.metric("Pedidos evaluados", formatear_entero(evaluados))
    k4.metric(
        "Demora posterior a preparación",
        formatear_entero(demora_posterior),
        _porcentaje(demora_posterior, evaluados),
        delta_color="inverse",
    )
    k5.metric("Lead time final", f"{lead_time_promedio:.1f} h")
    k6.metric("Tiempo Prep. + Control", f"{preparacion_lead_time:.1f} h")

    st.caption(
        "OTIF final mide el cumplimiento del hito de salida o cierre. "
        "OTIF Prep. + Control mide si el ciclo operativo terminó Control "
        "dentro del compromiso. Hasta contar con la fecha real de transmisión, "
        "los pedidos cuya creación quedó más de 10 días antes del inicio de "
        "preparación usan ese inicio como referencia provisoria. "
        f"Registros alcanzados por la regla en este período: "
        f"{formatear_entero(referencia_provisoria)}."
    )

    # ======================================================
    # MATRIZ PREPARACIÓN VS CUMPLIMIENTO FINAL
    # ======================================================
    st.markdown("#### Dónde se origina el incumplimiento")
    matriz_base = visible.loc[
        visible.get(
            "DiagnosticoPreparacionEntrega",
            pd.Series("", index=visible.index),
        ).ne("SIN EVALUAR")
    ].copy()

    m1, m2 = st.columns([1.05, 1.45], gap="small")
    with m1:
        resumen_matriz = (
            matriz_base.get(
                "DiagnosticoPreparacionEntrega",
                pd.Series(dtype="object"),
            )
            .fillna("SIN EVALUAR")
            .value_counts()
            .rename_axis("Diagnóstico")
            .reset_index(name="Pedidos")
        )
        if not resumen_matriz.empty:
            figura = px.bar(
                resumen_matriz.sort_values("Pedidos"),
                x="Pedidos",
                y="Diagnóstico",
                orientation="h",
                text="Pedidos",
                title="Resultado combinado del pedido",
            )
            figura.update_traces(textposition="outside", cliponaxis=False)
            figura.update_layout(
                template="plotly_dark",
                height=350,
                margin=dict(l=10, r=25, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(
                figura,
                width="stretch",
                config={"displaylogo": False},
                key="matriz_diagnostico_prep_entrega",
            )
        else:
            st.info("Sin pedidos comparables entre preparación y entrega.")

    with m2:
        comparativa = visible.loc[
            visible.get("AplicaOTIF", pd.Series(False, index=visible.index)).fillna(False)
            & visible.get(
                "AplicaPreparacionOTIF",
                pd.Series(False, index=visible.index),
            ).fillna(False)
        ].copy()
        fecha_semana = pd.to_datetime(
            comparativa.get("FechaObjetivoCumplimiento"),
            errors="coerce",
        )
        comparativa = comparativa.loc[fecha_semana.notna()].copy()
        if not comparativa.empty:
            comparativa["Semana"] = (
                fecha_semana.loc[fecha_semana.notna()]
                .dt.to_period("W")
                .apply(lambda periodo: periodo.start_time)
            )
            tendencia_comparada = (
                comparativa.groupby("Semana", as_index=False)
                .agg(
                    Pedidos=("Pedido", "size"),
                    CumplenFinal=("CumpleOTIF", "sum"),
                    CumplenPreparacion=("CumplePreparacionOTIF", "sum"),
                )
            )
            tendencia_comparada["OTIF final"] = (
                tendencia_comparada["CumplenFinal"]
                .div(tendencia_comparada["Pedidos"].replace(0, pd.NA))
                .mul(100)
                .fillna(0)
            )
            tendencia_comparada["OTIF Prep. + Control"] = (
                tendencia_comparada["CumplenPreparacion"]
                .div(tendencia_comparada["Pedidos"].replace(0, pd.NA))
                .mul(100)
                .fillna(0)
            )
            tendencia_larga = tendencia_comparada.melt(
                id_vars=["Semana"],
                value_vars=["OTIF final", "OTIF Prep. + Control"],
                var_name="Indicador",
                value_name="CumplimientoPct",
            )
            figura = px.line(
                tendencia_larga,
                x="Semana",
                y="CumplimientoPct",
                color="Indicador",
                markers=True,
                title="Evolución semanal: Prep. + Control vs resultado final",
                labels={"CumplimientoPct": "% cumplimiento"},
            )
            figura.update_yaxes(range=[0, 105])
            figura.update_layout(
                template="plotly_dark",
                height=350,
                margin=dict(l=10, r=10, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend_title_text="",
            )
            st.plotly_chart(
                figura,
                width="stretch",
                config={"displaylogo": False},
                key="tendencia_comparada_prep_final",
            )
        else:
            st.info("Sin fechas comparables para construir la evolución.")

    # ======================================================
    # VISUALES PRINCIPALES DE CUMPLIMIENTO
    # ======================================================
    st.markdown("#### Análisis de cumplimiento")
    g1, g2, g3 = st.columns(3, gap="small")

    base_otif = visible.loc[
        visible.get(
            "AplicaOTIF",
            pd.Series(False, index=visible.index),
        ).fillna(False)
    ].copy()

    with g1:
        if not base_otif.empty:
            resumen_circuito = (
                base_otif.groupby("CircuitoOTIF", as_index=False)
                .agg(
                    Pedidos=("Pedido", "size"),
                    Cumplen=("CumpleOTIF", "sum"),
                )
            )
            resumen_circuito["OTIFPct"] = (
                resumen_circuito["Cumplen"]
                .div(resumen_circuito["Pedidos"].replace(0, pd.NA))
                .mul(100)
                .fillna(0)
            )
            figura = px.bar(
                resumen_circuito,
                x="CircuitoOTIF",
                y="OTIFPct",
                text="OTIFPct",
                title="OTIF por circuito",
                labels={"CircuitoOTIF": "Circuito", "OTIFPct": "% OTIF"},
            )
            figura.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            figura.update_yaxes(range=[0, 105])
            figura.update_layout(
                template="plotly_dark",
                height=355,
                margin=dict(l=10, r=10, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
        else:
            st.info("Sin datos evaluables para OTIF.")

    with g2:
        if not base_otif.empty:
            fecha_tendencia = pd.to_datetime(
                base_otif.get("FechaObjetivoCumplimiento"),
                errors="coerce",
            )
            tendencia = base_otif.loc[fecha_tendencia.notna()].copy()
            tendencia["Semana"] = (
                fecha_tendencia.loc[fecha_tendencia.notna()]
                .dt.to_period("W")
                .apply(lambda periodo: periodo.start_time)
            )
            tendencia = (
                tendencia.groupby("Semana", as_index=False)
                .agg(Pedidos=("Pedido", "size"), Cumplen=("CumpleOTIF", "sum"))
            )
            tendencia["OTIFPct"] = (
                tendencia["Cumplen"]
                .div(tendencia["Pedidos"].replace(0, pd.NA))
                .mul(100)
                .fillna(0)
            )
            if not tendencia.empty:
                figura = px.line(
                    tendencia,
                    x="Semana",
                    y="OTIFPct",
                    markers=True,
                    title="Evolución semanal del OTIF",
                    labels={"OTIFPct": "% OTIF"},
                )
                figura.update_yaxes(range=[0, 105])
                figura.update_layout(
                    template="plotly_dark",
                    height=355,
                    margin=dict(l=10, r=10, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
            else:
                st.info("Sin fechas objetivo para construir tendencia.")
        else:
            st.info("Sin datos evaluables para tendencia.")

    with g3:
        incumplimientos = base_otif.loc[
            ~base_otif.get(
                "CumpleOTIF",
                pd.Series(False, index=base_otif.index),
            ).fillna(False)
        ].copy()
        causas = (
            incumplimientos.get(
                "MotivoIncumplimientoOTIF",
                pd.Series(dtype="object"),
            )
            .fillna("SIN MOTIVO")
            .astype(str)
            .replace("", "SIN MOTIVO")
            .value_counts()
            .sort_values()
            .rename_axis("Motivo")
            .reset_index(name="Pedidos")
        )
        if not causas.empty:
            figura = px.bar(
                causas,
                x="Pedidos",
                y="Motivo",
                orientation="h",
                text="Pedidos",
                title="Causas de incumplimiento",
            )
            figura.update_traces(textposition="outside", cliponaxis=False)
            figura.update_layout(
                template="plotly_dark",
                height=355,
                margin=dict(l=10, r=20, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(figura, width="stretch", config={"displaylogo": False})
        else:
            st.success("No hay incumplimientos en el período filtrado.")

    g4, g5 = st.columns(2, gap="small")

    with g4:
        if not base_otif.empty:
            grupos_cumplimiento = (
                base_otif.groupby("GrupoEntrega", as_index=False)
                .agg(Pedidos=("Pedido", "size"), Cumplen=("CumpleOTIF", "sum"))
            )
            grupos_cumplimiento["OTIFPct"] = (
                grupos_cumplimiento["Cumplen"]
                .div(grupos_cumplimiento["Pedidos"].replace(0, pd.NA))
                .mul(100)
                .fillna(0)
            )
            grupos_cumplimiento = (
                grupos_cumplimiento.sort_values("OTIFPct")
                .tail(15)
            )
            figura = px.bar(
                grupos_cumplimiento,
                x="OTIFPct",
                y="GrupoEntrega",
                orientation="h",
                text="OTIFPct",
                title="Cumplimiento por grupo de entrega",
                labels={"OTIFPct": "% OTIF", "GrupoEntrega": "Grupo"},
            )
            figura.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            figura.update_xaxes(range=[0, 105])
            figura.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=10, r=25, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

    with g5:
        lead_time_circuito = (
            base_otif.assign(
                LeadTimeServicioHoras=pd.to_numeric(
                    base_otif.get("LeadTimeServicioHoras"),
                    errors="coerce",
                )
            )
            .dropna(subset=["LeadTimeServicioHoras"])
            .groupby("CircuitoOTIF", as_index=False)
            .agg(LeadTimePromedio=("LeadTimeServicioHoras", "mean"))
        )
        if not lead_time_circuito.empty:
            figura = px.bar(
                lead_time_circuito,
                x="CircuitoOTIF",
                y="LeadTimePromedio",
                text="LeadTimePromedio",
                title="Lead time promedio por circuito",
                labels={
                    "CircuitoOTIF": "Circuito",
                    "LeadTimePromedio": "Horas",
                },
            )
            figura.update_traces(
                texttemplate="%{text:.1f} h",
                textposition="outside",
            )
            figura.update_layout(
                template="plotly_dark",
                height=390,
                margin=dict(l=10, r=10, t=55, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

    # ======================================================
    # GRÁFICOS DE CALIDAD / DATOS (OCULTOS POR DEFECTO)
    # ======================================================
    with st.expander("📊 Ver gráficos de datos", expanded=False):
        total = len(visible)
        con_maestro = int(
            visible.get(
                "TieneMaestroCliente",
                pd.Series(False, index=visible.index),
            ).fillna(False).sum()
        )
        configurados = int(
            visible.get(
                "PlanificacionValida",
                pd.Series(False, index=visible.index),
            ).fillna(False).sum()
        )
        universo_otif = int(
            visible.get(
                "AplicaOTIFBase",
                pd.Series(False, index=visible.index),
            ).fillna(False).sum()
        )
        tipo_circuito = visible.get(
            "TipoCircuito",
            pd.Series("", index=visible.index, dtype="object"),
        ).fillna("").astype(str)
        turnos = int(tipo_circuito.eq("CON TURNO").sum())
        sin_config = int(tipo_circuito.eq("SIN CONFIGURACION").sum())

        st.markdown("##### Calidad de la base filtrada")
        q1, q2, q3, q4, q5, q6 = st.columns(6)
        q1.metric("Pedidos analizados", formatear_entero(total))
        q2.metric("Con maestro", formatear_entero(con_maestro), _porcentaje(con_maestro, total))
        q3.metric("Planificados", formatear_entero(configurados), _porcentaje(configurados, total))
        q4.metric("Universo OTIF", formatear_entero(universo_otif), _porcentaje(universo_otif, total))
        q5.metric("Con turno", formatear_entero(turnos), "Excluidos de OTIF")
        q6.metric("Sin configuración", formatear_entero(sin_config), _porcentaje(sin_config, total))

        graf_1, graf_2, graf_3 = st.columns(3, gap="small")
        with graf_1:
            circuito_resumen = (
                tipo_circuito.replace("", "SIN INFORMACIÓN")
                .value_counts()
                .rename_axis("Circuito")
                .reset_index(name="Pedidos")
            )
            if not circuito_resumen.empty:
                figura = px.pie(
                    circuito_resumen,
                    names="Circuito",
                    values="Pedidos",
                    hole=0.58,
                    title="Distribución por circuito",
                )
                figura.update_layout(
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=10, r=10, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    legend_title_text="",
                )
                figura.update_traces(textinfo="percent+label")
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

        with graf_2:
            grupos_resumen = (
                visible.get("GrupoEntrega", pd.Series("", index=visible.index))
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", "SIN INFORMACIÓN")
                .value_counts()
                .head(10)
                .sort_values()
                .rename_axis("Grupo")
                .reset_index(name="Pedidos")
            )
            if not grupos_resumen.empty:
                figura = px.bar(
                    grupos_resumen,
                    x="Pedidos",
                    y="Grupo",
                    orientation="h",
                    text="Pedidos",
                    title="Pedidos por grupo de entrega",
                )
                figura.update_layout(
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=10, r=20, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                figura.update_traces(textposition="outside", cliponaxis=False)
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

        with graf_3:
            etapas_resumen = (
                visible.get("UltimaEtapaRegistrada", pd.Series("", index=visible.index))
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", "SIN INFORMACIÓN")
                .value_counts()
                .sort_values()
                .rename_axis("Etapa")
                .reset_index(name="Pedidos")
            )
            if not etapas_resumen.empty:
                figura = px.bar(
                    etapas_resumen,
                    x="Pedidos",
                    y="Etapa",
                    orientation="h",
                    text="Pedidos",
                    title="Estado del ciclo",
                )
                figura.update_layout(
                    template="plotly_dark",
                    height=350,
                    margin=dict(l=10, r=20, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                figura.update_traces(textposition="outside", cliponaxis=False)
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

        hr_1, hr_2 = st.columns(2, gap="small")
        with hr_1:
            origen_hr = (
                visible.get("OrigenHojaRutaFinal", pd.Series("SIN HR", index=visible.index))
                .fillna("SIN HR")
                .astype(str)
                .str.strip()
                .replace("", "SIN HR")
                .value_counts()
                .rename_axis("Origen HR")
                .reset_index(name="Pedidos")
            )
            if not origen_hr.empty:
                figura = px.pie(
                    origen_hr,
                    names="Origen HR",
                    values="Pedidos",
                    hole=0.58,
                    title="Origen de la Hoja de Ruta",
                )
                figura.update_layout(
                    template="plotly_dark",
                    height=330,
                    margin=dict(l=10, r=10, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    legend_title_text="",
                )
                figura.update_traces(textinfo="value+label")
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

        with hr_2:
            estado_vinculo = (
                visible.get("TipoAsignacionHR", pd.Series("SIN INFORMACIÓN", index=visible.index))
                .fillna("SIN INFORMACIÓN")
                .astype(str)
                .str.strip()
                .replace("", "SIN INFORMACIÓN")
                .value_counts()
                .sort_values()
                .rename_axis("Resultado")
                .reset_index(name="Pedidos")
            )
            if not estado_vinculo.empty:
                figura = px.bar(
                    estado_vinculo,
                    x="Pedidos",
                    y="Resultado",
                    orientation="h",
                    text="Pedidos",
                    title="Vinculación de HR entre cuentas",
                )
                figura.update_layout(
                    template="plotly_dark",
                    height=330,
                    margin=dict(l=10, r=20, t=55, b=10),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                )
                figura.update_traces(textposition="outside", cliponaxis=False)
                st.plotly_chart(figura, width="stretch", config={"displaylogo": False})

        sin_hr = int((~visible.get("TieneHojaRuta", pd.Series(False, index=visible.index)).fillna(False)).sum())
        ambiguos = int(visible.get("TipoAsignacionHR", pd.Series("", index=visible.index)).eq("AMBIGUO — REVISAR").sum())
        heredados_hermano = int(visible.get("TipoAsignacionHR", pd.Series("", index=visible.index)).eq("HR HEREDADA CUENTA 1").sum())
        heredados_7d = int(visible.get("TipoAsignacionHR", pd.Series("", index=visible.index)).eq("HR HEREDADA ULTIMA CLIENTE 7D").sum())
        cuenta2_sin_hr = int(visible.get("TipoAsignacionHR", pd.Series("", index=visible.index)).eq("CUENTA 2 CERRADA SIN HR REFERENCIA").sum())
        retira = int(visible.get("TipoCircuito", pd.Series("", index=visible.index)).eq("RETIRA").sum())
        sin_maestro = int((~visible.get("TieneMaestroCliente", pd.Series(False, index=visible.index)).fillna(False)).sum())

        st.markdown("##### Alertas y correcciones de datos")
        a1, a2, a3, a4, a5, a6 = st.columns(6)
        a1.metric("Sin Hoja de Ruta final", formatear_entero(sin_hr))
        a2.metric("HR por pedido hermano", formatear_entero(heredados_hermano))
        a3.metric("HR por cliente · 7 días", formatear_entero(heredados_7d))
        a4.metric("Cuenta 2 cerrada sin HR", formatear_entero(cuenta2_sin_hr))
        a5.metric("Pedidos RETIRA", formatear_entero(retira))
        a6.metric("Sin cruce con maestro", formatear_entero(sin_maestro))

    columnas_vista = [
        "Pedido",
        "ClienteFinal",
        "ClienteCodigoHR",
        "CodigoEntrega",
        "CodigoDespacho",
        "CodigoLogisticoPedido",
        "DespachoDescripcion",
        "CodigoLogisticoMaestro",
        "ClienteMaestro",
        "OrigenCruceCliente",
        "TipoCircuito",
        "TipoCumplimiento",
        "GrupoEntrega",
        "ZonaPlanificacion",
        "PreparacionConfigurada",
        "EntregaConfigurada",
        "FechaHoraCreacion",
        "FechaCorteCiclo",
        "FechaReferenciaIngresoCiclo",
        "OrigenFechaIngresoCiclo",
        "FechaCorteIngresoCiclo",
        "SemanaCiclo",
        "FechaObjetivoPreparacion",
        "FechaObjetivoEntrega",
        "FechaHoraInicioPreparacion",
        "FechaHoraFinPreparacion",
        "FechaHoraInicioControl",
        "FechaHoraFinControl",
        "FechaHoraPrimeraHojaRuta",
        "HojaRuta",
        "OrigenHojaRutaFinal",
        "CuentaPedido",
        "PedidoCuenta1Relacionado",
        "TipoAsignacionHR",
        "HorasDiferenciaPedidoHermano",
        "DiasDiferenciaUltimaHRCliente",
        "ConfianzaAsignacionHR",
        "CantidadCandidatosHR",
        "MotivoNoAsignacionHR",
        "HorasAnticipacionCreacion",
        "CumpleAnticipacion24h",
        "CumpleSlaRetira",
        "AplicaOTIFBase",
        "EstadoPlanificacion",
        "EstadoOTIF",
        "CumpleOTIF",
        "MotivoIncumplimientoOTIF",
        "EstadoPreparacionOTIF",
        "CumplePreparacionOTIF",
        "MotivoIncumplimientoPreparacion",
        "FechaObjetivoPreparacionOTIF",
        "FechaRealPreparacionOTIF",
        "LeadTimePreparacionOTIFHoras",
        "DesvioPreparacionHoras",
        "DiagnosticoPreparacionEntrega",
        "FechaObjetivoCumplimiento",
        "FechaEventoCumplimiento",
        "LeadTimeServicioHoras",
        "DesvioOTIFHoras",
        "MotivoExclusionOTIF",
        "ZonaHR",
        "Flete",
        "UltimaEtapaRegistrada",
    ]
    columnas_vista = [columna for columna in columnas_vista if columna in visible.columns]

    st.caption(
        f"{len(visible):,} pedidos visibles · "
        f"{diagnostico.get('pedidos_digip_cerrados', 0):,} cerrados en Pedidos DIGIP · "
        f"{diagnostico.get('pedidos_digip_excluidos_estado', 0):,} excluidos por estado · "
        f"{diagnostico.get('pedidos_metricas', 0):,} en históricos · "
        f"{diagnostico.get('pedidos_proceso_mensual', 0):,} en proceso mensual · "
        f"{diagnostico.get('pedidos_hoja_ruta', 0):,} en Hojas de Ruta · "
        f"{diagnostico.get('vinculacion_hr_heredadas_hermano', 0):,} HR por pedido hermano · "
        f"{diagnostico.get('vinculacion_hr_heredadas_cliente_7d', 0):,} HR por cliente 7d · "
        f"{diagnostico.get('vinculacion_cuenta_2_cerrada_sin_hr', 0):,} cuenta 2 cerrada sin HR · "
        f"{diagnostico.get('planificacion_circuito_retira', 0):,} RETIRA · "
        f"{diagnostico.get('planificacion_cencosud_easy_turno', 0):,} CENCOSUD EASY con turno"
    )

    st.dataframe(
        limitar_previsualizacion(visible[columnas_vista], limite=10000),
        width="stretch",
        hide_index=True,
        column_config={
            "FechaHoraCreacion": st.column_config.DatetimeColumn("Creación", format="DD/MM/YYYY HH:mm"),
            "FechaCorteCiclo": st.column_config.DatetimeColumn("Referencia +24 h", format="DD/MM/YYYY HH:mm"),
            "FechaReferenciaIngresoCiclo": st.column_config.DatetimeColumn("Ingreso al ciclo", format="DD/MM/YYYY HH:mm"),
            "FechaCorteIngresoCiclo": st.column_config.DatetimeColumn("Corte del ciclo", format="DD/MM/YYYY HH:mm"),
            "FechaObjetivoPreparacion": st.column_config.DatetimeColumn("Preparación objetivo", format="DD/MM/YYYY HH:mm"),
            "FechaObjetivoEntrega": st.column_config.DatetimeColumn("Entrega objetivo", format="DD/MM/YYYY HH:mm"),
            "FechaHoraInicioPreparacion": st.column_config.DatetimeColumn("Inicio preparación", format="DD/MM/YYYY HH:mm"),
            "FechaHoraFinPreparacion": st.column_config.DatetimeColumn("Fin preparación", format="DD/MM/YYYY HH:mm"),
            "FechaHoraInicioControl": st.column_config.DatetimeColumn("Inicio control", format="DD/MM/YYYY HH:mm"),
            "FechaHoraFinControl": st.column_config.DatetimeColumn("Fin control", format="DD/MM/YYYY HH:mm"),
            "FechaHoraPrimeraHojaRuta": st.column_config.DatetimeColumn("Primera hoja de ruta", format="DD/MM/YYYY HH:mm"),
            "HorasAnticipacionCreacion": st.column_config.NumberColumn("Anticipación creación", format="%.1f h"),
            "CumpleAnticipacion24h": st.column_config.CheckboxColumn("Cumple 24 h"),
            "CumpleSlaRetira": st.column_config.CheckboxColumn("Cumple RETIRA 48 h"),
            "AplicaOTIFBase": st.column_config.CheckboxColumn("Aplica OTIF"),
            "CumpleOTIF": st.column_config.CheckboxColumn("Cumple OTIF final"),
            "CumplePreparacionOTIF": st.column_config.CheckboxColumn("Cumple Prep. + Control"),
            "FechaObjetivoPreparacionOTIF": st.column_config.DatetimeColumn("Objetivo preparación OTIF", format="DD/MM/YYYY HH:mm"),
            "FechaRealPreparacionOTIF": st.column_config.DatetimeColumn("Fin de control real", format="DD/MM/YYYY HH:mm"),
            "LeadTimePreparacionOTIFHoras": st.column_config.NumberColumn("Tiempo Prep. + Control", format="%.1f h"),
            "HorasAnticipacionInicioPreparacion": st.column_config.NumberColumn("Anticipación a preparación", format="%.1f h"),
            "CumpleAnticipacionPreparacion24h": st.column_config.CheckboxColumn("Cumple corte del ciclo"),
            "DesvioPreparacionHoras": st.column_config.NumberColumn("Desvío preparación", format="%.1f h"),
            "FechaObjetivoCumplimiento": st.column_config.DatetimeColumn("Objetivo cumplimiento", format="DD/MM/YYYY HH:mm"),
            "FechaEventoCumplimiento": st.column_config.DatetimeColumn("Evento real", format="DD/MM/YYYY HH:mm"),
            "LeadTimeServicioHoras": st.column_config.NumberColumn("Lead time servicio", format="%.1f h"),
            "DesvioOTIFHoras": st.column_config.NumberColumn("Desvío OTIF", format="%.1f h"),
        },
    )

    columnas_resumen = [
        "Pedido", "ClienteFinal", "ClienteCodigoHR", "ClienteCodigo",
        "CodigoEntrega", "CodigoDespacho", "CodigoLogisticoPedido",
        "DespachoDescripcion", "CodigoLogisticoMaestro",
        "TipoCircuito", "TipoCumplimiento", "GrupoEntrega", "ZonaPlanificacion",
        "PreparacionConfigurada", "EntregaConfigurada",
        "FechaReferenciaIngresoCiclo", "OrigenFechaIngresoCiclo",
        "FechaCorteIngresoCiclo", "SemanaCiclo",
        "FechaHoraCreacion", "FechaHoraInicioPreparacion",
        "FechaHoraFinPreparacion", "FechaHoraInicioControl",
        "FechaHoraFinControl", "FechaHoraPrimeraHojaRuta",
        "HojaRutaFinal", "OrigenHojaRutaFinal", "PedidoCuenta1Relacionado",
        "TipoAsignacionHR", "ConfianzaAsignacionHR",
        "HorasDiferenciaPedidoHermano", "DiasDiferenciaUltimaHRCliente",
        "CumpleSlaRetira", "ZonaHR", "Flete",
        "UltimaEtapaRegistrada", "EstadoPlanificacion",
        "EstadoOTIF", "CumpleOTIF", "MotivoIncumplimientoOTIF",
        "EstadoPreparacionOTIF", "CumplePreparacionOTIF",
        "MotivoIncumplimientoPreparacion",
        "DiagnosticoPreparacionEntrega",
        "FechaObjetivoPreparacionOTIF", "FechaRealPreparacionOTIF",
        "LeadTimePreparacionOTIFHoras", "DesvioPreparacionHoras",
        "FechaObjetivoCumplimiento", "FechaEventoCumplimiento",
        "LeadTimeServicioHoras", "DesvioOTIFHoras",
        "FechaObjetivoPreparacion", "FechaObjetivoEntrega",
        "HorasPreparacion", "HorasControl", "HorasCicloHastaHojaRuta",
    ]
    columnas_resumen = [c for c in columnas_resumen if c in visible.columns]

    resumen_excel = BytesIO()
    with pd.ExcelWriter(resumen_excel, engine="openpyxl") as writer:
        visible[columnas_resumen].to_excel(writer, index=False, sheet_name="Resumen")

    salida_excel = BytesIO()
    with pd.ExcelWriter(salida_excel, engine="openpyxl") as writer:
        visible.to_excel(writer, index=False, sheet_name="Ciclo y Planificacion")
        if not df_excluidos.empty:
            df_excluidos.to_excel(
                writer,
                index=False,
                sheet_name="Excluidos del universo",
            )
        pd.DataFrame([diagnostico]).to_excel(writer, index=False, sheet_name="Diagnostico")

    st.markdown("#### Exportaciones")
    descarga_1, descarga_2, _ = st.columns([1, 1, 4])
    descarga_1.download_button(
        "📊 Descargar resumen",
        data=resumen_excel.getvalue(),
        file_name="Resumen_Cumplimiento_Pedidos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        width="stretch",
    )
    descarga_2.download_button(
        "🔎 Descargar base analítica",
        data=salida_excel.getvalue(),
        file_name="Base_Planificacion_Nivel_Servicio.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )


def render(contexto: dict) -> None:
    vista = st.segmented_control(
        "Indicador de cumplimiento",
        options=["📊 OTIF", "📦 Fill Rate", "⭐ Calidad", "⏱ SLA y Lead Time"],
        default="📊 OTIF",
        key="vista_cumplimiento_pedidos",
        label_visibility="collapsed",
    )
    if vista == "📦 Fill Rate":
        render_fillrate(contexto)
        return
    if vista == "⭐ Calidad":
        st.info("La vista de Calidad se conectará con la página de reclamos de pedidos.")
        return
    if vista == "⏱ SLA y Lead Time":
        st.info("La vista específica de SLA y Lead Time se construirá sobre los hitos ya calculados.")
        return
    _render_otif(contexto)
