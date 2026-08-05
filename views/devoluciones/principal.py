# pages/09_Devoluciones.py
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

import pandas as pd
import streamlit as st

from models.devoluciones.dashboard import (
    aplicar_filtros_dashboard,
    calcular_metricas,
    distribucion_tiempos,
    embudo_gestion,
    preparar_datos_devoluciones,
    ranking_responsables,
    resumen_categoria,
    resumen_evolucion_diaria,
    solicitudes_por_dia_semana,
    solicitudes_por_hora,
    tiempos_por_etapa,
    top_clientes,
)
from utils.gestion_devoluciones import (
    confirmar_reingreso,
    confirmar_resultado_operativo,
    finalizar_gestion,
    registrar_ir,
    tomar_gestion,
)
from views.devoluciones.graficos import (
    grafico_barras,
    grafico_donut,
    grafico_embudo,
    grafico_evolucion,
    grafico_responsables,
    grafico_tiempos_etapa,
)
from utils.leer_devoluciones import (
    invalidar_cache_devoluciones,
    leer_cancelaciones_entrega,
    obtener_cancelaciones_activas,
    obtener_historial_cancelaciones,
)



def render() -> None:


    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 3rem;
        }

        [data-testid="stMetric"] {
            background:
                linear-gradient(
                    145deg,
                    rgba(24, 34, 47, 0.98),
                    rgba(11, 17, 25, 0.98)
                );
            border: 1px solid #2A3543;
            border-radius: 12px;
            padding: 0.95rem 1rem;
            min-height: 122px;
        }

        [data-testid="stMetricLabel"] {
            color: #D8DEE9;
            font-weight: 600;
        }

        [data-testid="stMetricValue"] {
            color: #F8FAFC;
            font-size: 1.65rem;
            font-weight: 700;
        }

        [data-testid="stMetricDelta"] {
            font-size: 0.76rem;
            white-space: normal;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(15, 23, 34, 0.62);
            border-color: #2A3543;
            border-radius: 12px;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid #2A3543;
            border-radius: 10px;
            overflow: hidden;
        }

        button[data-baseweb="tab"] {
            font-weight: 600;
        }

        .operativo-kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.7rem;
            margin: 0.65rem 0 1.15rem 0;
        }

        .operativo-kpi-card {
            min-height: 126px;
            padding: 0.95rem 1rem;
            border: 1px solid #2A3543;
            border-radius: 12px;
            background:
                linear-gradient(
                    145deg,
                    rgba(24, 34, 47, 0.98),
                    rgba(11, 17, 25, 0.98)
                );
        }

        .operativo-kpi-label {
            color: #D8DEE9;
            font-size: 0.82rem;
            font-weight: 600;
            min-height: 2.1rem;
        }

        .operativo-kpi-value {
            color: #F8FAFC;
            font-size: 1.72rem;
            font-weight: 750;
            margin-top: 0.36rem;
            line-height: 1.05;
        }

        .operativo-kpi-detail {
            color: #93A4B8;
            font-size: 0.76rem;
            margin-top: 0.52rem;
            line-height: 1.25;
        }

        @media (max-width: 1100px) {
            .operativo-kpi-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 680px) {
            .operativo-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


    DESTINATARIOS_WHATSAPP = {
        "Leo": "5491124714063",
        "Juanma": "5491133914080",
    }


    def usuario_actual() -> str:
        return (
            st.session_state.get("usuario")
            or st.session_state.get("nombre_usuario")
            or "Usuario app"
        )


    def construir_mensaje(registro: dict) -> str:
        remitos = "\n".join(
            f"• {valor.strip()}"
            for valor in str(registro.get("Remito", ""))
            .replace(",", "\n")
            .splitlines()
            if valor.strip()
        )

        return (
            "🚨 CANCELACIÓN DE ENTREGA 🚨\n\n"
            f"Remitos:\n{remitos}\n\n"
            f"Cliente: {registro.get('Cliente', '')}\n"
            f"Motivo: {registro.get('Motivo', '')}\n"
            f"Observación: {registro.get('Observacion', '')}\n\n"
            "⛔ NO CARGAR NI DESPACHAR ESTA MERCADERÍA.\n\n"
            f"ID: {registro.get('CancelacionEntregaID', '')}"
        )


    def construir_url_whatsapp(registro: dict, telefono: str) -> str:
        return f"https://wa.me/{telefono}?text={quote(construir_mensaje(registro))}"


    st.title("↩️ Devoluciones")
    st.caption(
        "Gestión operativa, seguimiento e indicadores de cancelaciones de entrega."
    )

    try:
        tabla_completa = leer_cancelaciones_entrega()
        activas = obtener_cancelaciones_activas(tabla_completa)
        historial = obtener_historial_cancelaciones(tabla_completa)
        datos = preparar_datos_devoluciones(tabla_completa)
    except Exception as error:
        mensaje = str(error)
        if "429" in mensaje or "Quota exceeded" in mensaje:
            st.error(
                "Google Sheets alcanzó temporalmente el límite de lecturas por "
                "minuto. Esperá unos segundos y volvé a intentar."
            )
            if st.button("🔄 Reintentar lectura", width="stretch"):
                invalidar_cache_devoluciones()
                st.rerun()
        else:
            st.error(f"No se pudo leer la gestión: {error}")
        st.stop()

    pestana_dashboard, pestana_activa, pestana_historico = st.tabs(
        ["📊 Dashboard", "🛠️ Gestión activa", "📚 Histórico"]
    )

    with pestana_dashboard:
        st.subheader("Panel de indicadores")

        fechas_validas = datos["FechaSolicitud"].dropna()
        if fechas_validas.empty:
            st.info("No hay fechas válidas para construir el dashboard.")
        else:
            fecha_maxima = fechas_validas.max().date()
            fecha_minima = fechas_validas.min().date()
            fecha_inicial = max(fecha_minima, fecha_maxima - timedelta(days=59))

            with st.container(border=True):
                st.markdown("##### 🔎 Filtros del dashboard")
                f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1])
            with f1:
                rango = st.date_input(
                    "Período",
                    value=(fecha_inicial, fecha_maxima),
                    min_value=fecha_minima,
                    max_value=fecha_maxima,
                    key="dev_rango",
                )

            motivos_disponibles = sorted(
                datos.loc[datos["Motivo"].ne(""), "Motivo"].unique().tolist()
            )
            clientes_disponibles = sorted(
                datos.loc[datos["Cliente"].ne(""), "Cliente"].unique().tolist()
            )
            responsables_disponibles = sorted(
                datos.loc[
                    datos["ResponsableGestion"].ne(""), "ResponsableGestion"
                ].unique().tolist()
            )

            with f2:
                motivos_filtro = st.multiselect(
                    "Motivo", motivos_disponibles, placeholder="Todos"
                )
            with f3:
                clientes_filtro = st.multiselect(
                    "Cliente", clientes_disponibles, placeholder="Todos"
                )
            with f4:
                responsables_filtro = st.multiselect(
                    "Responsable", responsables_disponibles, placeholder="Todos"
                )

            if isinstance(rango, (list, tuple)) and len(rango) == 2:
                fecha_desde, fecha_hasta = rango
            else:
                fecha_desde = fecha_hasta = rango

            filtrados = aplicar_filtros_dashboard(
                datos,
                fecha_desde,
                fecha_hasta,
                motivos=motivos_filtro,
                clientes=clientes_filtro,
                responsables=responsables_filtro,
            )

            metricas = calcular_metricas(filtrados, fecha_desde, fecha_hasta)

            tarjetas_devoluciones = [
                (
                    "↩️ Gestiones del período",
                    f"{metricas.periodo:,}".replace(",", "."),
                    (
                        f"{fecha_desde.strftime('%d/%m/%Y')} al "
                        f"{fecha_hasta.strftime('%d/%m/%Y')}"
                    ),
                ),
                (
                    "⏳ Pendientes",
                    f"{metricas.pendientes:,}".replace(",", "."),
                    "Requieren continuidad operativa",
                ),
                (
                    "✅ Finalizadas",
                    f"{metricas.finalizadas:,}".replace(",", "."),
                    "Gestiones cerradas en el período",
                ),
                (
                    "🛑 Entregas detenidas",
                    f"{metricas.porcentaje_detenidas:.1f}%",
                    "Mercadería interceptada a tiempo",
                ),
                (
                    "🚚 Ya despachadas",
                    f"{metricas.porcentaje_despachadas:.1f}%",
                    "No pudieron detenerse antes de la salida",
                ),
                (
                    "⏱️ Promedio de cierre",
                    f"{metricas.tiempo_promedio_cierre_horas:.1f} h",
                    f"Promedio hasta IR: {metricas.tiempo_promedio_ir_horas:.1f} h",
                ),
            ]

            html_kpis_devoluciones = '<div class="operativo-kpi-grid">'
            for etiqueta, valor, detalle in tarjetas_devoluciones:
                html_kpis_devoluciones += (
                    '<div class="operativo-kpi-card">'
                    f'<div class="operativo-kpi-label">{etiqueta}</div>'
                    f'<div class="operativo-kpi-value">{valor}</div>'
                    f'<div class="operativo-kpi-detail">{detalle}</div>'
                    '</div>'
                )
            html_kpis_devoluciones += "</div>"

            st.markdown(
                html_kpis_devoluciones,
                unsafe_allow_html=True,
            )

            st.caption(
                f"Período analizado: {fecha_desde.strftime('%d/%m/%Y')} al "
                f"{fecha_hasta.strftime('%d/%m/%Y')} · "
                f"Promedio hasta generar IR: {metricas.tiempo_promedio_ir_horas:.1f} h"
            )

            st.divider()
            col_evolucion, col_motivos = st.columns([1.7, 1])
            with col_evolucion:
                st.markdown("#### Evolución diaria")
                grafico_evolucion(resumen_evolucion_diaria(filtrados))
            with col_motivos:
                st.markdown("#### Motivos")
                grafico_donut(resumen_categoria(filtrados, "Motivo"), "Motivo")

            col_resultado, col_embudo = st.columns([1, 1.5])
            with col_resultado:
                st.markdown("#### Resultado operativo")
                grafico_donut(
                    resumen_categoria(filtrados, "ResultadoOperativo"),
                    "ResultadoOperativo",
                )
            with col_embudo:
                st.markdown("#### Embudo del proceso")
                grafico_embudo(embudo_gestion(filtrados))

            col_clientes, col_responsables = st.columns(2)
            with col_clientes:
                st.markdown("#### Clientes con más gestiones")
                grafico_barras(
                    top_clientes(filtrados),
                    "Cliente",
                    horizontal=True,
                    altura=340,
                )
            with col_responsables:
                st.markdown("#### Gestión por responsable")
                grafico_responsables(ranking_responsables(filtrados))

            col_tiempos, col_rangos = st.columns(2)
            with col_tiempos:
                st.markdown("#### Tiempo promedio por etapa")
                grafico_tiempos_etapa(tiempos_por_etapa(filtrados))
            with col_rangos:
                st.markdown("#### Distribución del tiempo total")
                grafico_barras(
                    distribucion_tiempos(filtrados),
                    "Rango",
                    horizontal=True,
                )

            col_dias, col_horas = st.columns(2)
            with col_dias:
                st.markdown("#### Gestiones por día de la semana")
                grafico_barras(
                    solicitudes_por_dia_semana(filtrados),
                    "DiaSemana",
                )
            with col_horas:
                st.markdown("#### Horario de ingreso")
                grafico_barras(
                    solicitudes_por_hora(filtrados),
                    "HoraSolicitud",
                )

            st.markdown("#### Últimas gestiones del período")
            columnas_resumen = [
                "CancelacionEntregaID",
                "Remito",
                "Cliente",
                "Motivo",
                "EstadoCancelacion",
                "ResultadoOperativo",
                "ResponsableGestion",
                "FechaSolicitud",
                "FechaCierre",
                "HorasResolucion",
            ]
            columnas_resumen = [c for c in columnas_resumen if c in filtrados.columns]
            tabla_resumen = filtrados.sort_values(
                "FechaSolicitud", ascending=False
            ).head(20)[columnas_resumen]
            st.dataframe(
                tabla_resumen,
                width="stretch",
                hide_index=True,
                column_config={
                    "CancelacionEntregaID": None,
                    "HorasResolucion": st.column_config.NumberColumn(
                        "Horas de resolución", format="%.2f h"
                    ),
                    "FechaSolicitud": st.column_config.DatetimeColumn(
                        "Fecha solicitud", format="DD/MM/YYYY HH:mm"
                    ),
                    "FechaCierre": st.column_config.DatetimeColumn(
                        "Fecha cierre", format="DD/MM/YYYY HH:mm"
                    ),
                },
            )

    with pestana_historico:
        if historial.empty:
            st.info("Todavía no hay registros.")
        else:
            columnas = [
                "CancelacionEntregaID",
                "Remito",
                "Cliente",
                "Motivo",
                "EstadoCancelacion",
                "ResponsableGestion",
                "NumeroIR",
                "ResultadoFinal",
                "FechaSolicitud",
                "FechaCierre",
            ]
            columnas = [col for col in columnas if col in historial.columns]
            st.dataframe(
                historial[columnas],
                width="stretch",
                hide_index=True,
            )

        with pestana_activa:
            if activas.empty:
                st.success("No hay cancelaciones pendientes.")
            else:
                tabla = activas.copy().reset_index(drop=True)
                columnas_tabla = [
                    "CancelacionEntregaID",
                    "Remito",
                    "Cliente",
                    "Motivo",
                    "EstadoCancelacion",
                    "ResponsableGestion",
                    "FechaSolicitud",
                ]

                evento = st.dataframe(
                    tabla[columnas_tabla],
                    width="stretch",
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    column_config={"CancelacionEntregaID": None},
                    key="devoluciones_activas",
                )

                filas = evento.selection.rows if evento is not None else []

                if filas:
                    registro = tabla.iloc[filas[0]]
                    cancelacion_id = str(registro["CancelacionEntregaID"]).strip()
                    estado = str(registro["EstadoCancelacion"]).strip()

                    if estado == "Alerta enviada":
                        estado = "Enviada a Logística"

                    st.divider()
                    st.subheader("Paso a paso de la gestión")

                    d1, d2, d3 = st.columns(3)
                    d1.metric("Estado", estado)
                    d2.metric(
                        "Responsable",
                        str(registro.get("ResponsableGestion", "")) or "Sin asignar",
                    )
                    d3.metric(
                        "IR",
                        str(registro.get("NumeroIR", "")) or "Pendiente",
                    )

                    st.write(
                        f"**Remitos:** {registro.get('Remito', '')}  ·  "
                        f"**Cliente:** {registro.get('Cliente', '')}  ·  "
                        f"**Motivo:** {registro.get('Motivo', '')}"
                    )

                    w1, w2 = st.columns(2)
                    with w1:
                        st.link_button(
                            "📲 Enviar a Leo",
                            construir_url_whatsapp(
                                registro.to_dict(),
                                DESTINATARIOS_WHATSAPP["Leo"],
                            ),
                            type="primary",
                            width="stretch",
                        )
                    with w2:
                        st.link_button(
                            "📲 Enviar a Juanma",
                            construir_url_whatsapp(
                                registro.to_dict(),
                                DESTINATARIOS_WHATSAPP["Juanma"],
                            ),
                            type="primary",
                            width="stretch",
                        )

                    usuario = usuario_actual()

                    if estado in {"Enviada a Logística", "Pendiente de envío"}:
                        with st.form(f"tomar_{cancelacion_id}"):
                            responsable = st.text_input(
                                "Responsable logístico",
                                value=usuario,
                            )
                            guardar = st.form_submit_button(
                                "🟠 Tomar gestión",
                                type="primary",
                                width="stretch",
                            )

                        if guardar:
                            tomar_gestion(cancelacion_id, responsable)
                            st.success("Gestión tomada.")
                            invalidar_cache_devoluciones()
                            st.rerun()

                    elif estado in {"En gestión", "Ya despachado"}:
                        with st.form(f"resultado_{cancelacion_id}"):
                            resultado = st.radio(
                                "Resultado operativo",
                                ["Entrega detenida", "Ya despachado", "Cancelada"],
                                horizontal=True,
                            )
                            responsable = st.text_input(
                                "Responsable que confirma",
                                value=usuario,
                            )
                            observacion = st.text_area("Observación")
                            guardar = st.form_submit_button(
                                "Guardar resultado",
                                type="primary",
                                width="stretch",
                            )

                        if guardar:
                            confirmar_resultado_operativo(
                                cancelacion_id,
                                resultado,
                                responsable,
                                observacion,
                            )
                            st.success("Resultado registrado.")
                            invalidar_cache_devoluciones()
                            st.rerun()

                    elif estado == "Entrega detenida":
                        with st.form(f"ir_{cancelacion_id}"):
                            numero_ir = st.text_input("Número de IR *")
                            responsable = st.text_input(
                                "Responsable del IR",
                                value=usuario,
                            )
                            observacion = st.text_area("Observación del IR")
                            guardar = st.form_submit_button(
                                "📄 Registrar IR",
                                type="primary",
                                width="stretch",
                            )

                        if guardar:
                            try:
                                registrar_ir(
                                    cancelacion_id,
                                    numero_ir,
                                    responsable,
                                    observacion,
                                )
                                st.success("IR registrado.")
                                invalidar_cache_devoluciones()
                                st.rerun()
                            except Exception as error:
                                st.error(str(error))

                    elif estado == "IR generado":
                        with st.form(f"reingreso_{cancelacion_id}"):
                            responsable = st.text_input(
                                "Responsable del reingreso",
                                value=usuario,
                            )
                            observacion = st.text_area("Observación del reingreso")
                            guardar = st.form_submit_button(
                                "📦 Confirmar reingreso",
                                type="primary",
                                width="stretch",
                            )

                        if guardar:
                            confirmar_reingreso(
                                cancelacion_id,
                                responsable,
                                observacion,
                            )
                            st.success("Reingreso confirmado.")
                            invalidar_cache_devoluciones()
                            st.rerun()

                    elif estado == "Mercadería reingresada":
                        with st.form(f"cierre_{cancelacion_id}"):
                            responsable = st.text_input(
                                "Responsable del cierre",
                                value=usuario,
                            )
                            observacion = st.text_area("Observación final")
                            guardar = st.form_submit_button(
                                "✅ Finalizar gestión",
                                type="primary",
                                width="stretch",
                            )

                        if guardar:
                            finalizar_gestion(
                                cancelacion_id,
                                responsable,
                                observacion,
                            )
                            st.success("Gestión finalizada.")
                            invalidar_cache_devoluciones()
                            st.rerun()
