# pages/09_Devoluciones.py
from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

import pandas as pd
import streamlit as st

from utils.autenticacion import requerir_roles
from utils.dashboard_devoluciones import (
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
from utils.graficos_devoluciones import (
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

requerir_roles("admin", "gerencia", "logistica", "supervisor")

st.set_page_config(
    page_title="Devoluciones",
    page_icon="↩️",
    layout="wide",
)

TELEFONO = "5491172151924"


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


def construir_url_whatsapp(registro: dict) -> str:
    return f"https://wa.me/{TELEFONO}?text={quote(construir_mensaje(registro))}"


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

        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Gestiones del período", f"{metricas.periodo:,}")
        k2.metric("Pendientes", f"{metricas.pendientes:,}")
        k3.metric("Finalizadas", f"{metricas.finalizadas:,}")
        k4.metric("Entregas detenidas", f"{metricas.porcentaje_detenidas:.1f}%")
        k5.metric("Ya despachadas", f"{metricas.porcentaje_despachadas:.1f}%")
        k6.metric("Promedio de cierre", f"{metricas.tiempo_promedio_cierre_horas:.1f} h")

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

                st.link_button(
                    "📲 Abrir / reenviar alerta de WhatsApp",
                    construir_url_whatsapp(registro.to_dict()),
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
