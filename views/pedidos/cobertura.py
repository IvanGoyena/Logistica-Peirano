from __future__ import annotations

import pandas as pd
import streamlit as st

from models.cobertura_pedidos import analizar_cobertura_pedidos_erp
from utils.gestion_cobertura import (
    leer_pedidos_informados, marcar_pedidos_informados,
    obtener_pedidos_informados, reabrir_pedidos_informados,
)
from utils.pedidos.carga import cargar_datos_cobertura

def render_cobertura(
    df_pedidos: pd.DataFrame,
    df_pendientes_erp: pd.DataFrame,
    tabla_clientes: pd.DataFrame,
    tabla_detalle_dashboard: pd.DataFrame,
) -> None:
        datos_cobertura = cargar_datos_cobertura()
        df_disponible_digip = datos_cobertura["disponible_digip"]
        df_stock_total_erp = datos_cobertura["stock_total_erp"]
        df_fechas_oc = datos_cobertura["fechas_oc"]

        lineas_cobertura_erp, resumen_cobertura_erp = analizar_cobertura_pedidos_erp(
            tabla_detalle_erp=tabla_detalle_dashboard,
            tabla_pendientes_erp=df_pendientes_erp,
            df_pedidos_digip=df_pedidos,
            df_disponible=df_disponible_digip,
            df_stock_erp=df_stock_total_erp,
            tabla_clientes=tabla_clientes,
            tabla_pendientes_oc=df_fechas_oc,
        )
        st.subheader("🚨 Compromisos ERP sin cobertura")
        st.caption(
            "La cobertura inmediata se calcula con el disponible aprobado del ERP "
            "(est_1). El pendiente o tránsito se toma de est_8. El stock WMS se "
            "mantiene como control para detectar diferencias entre sistemas."
        )

        if resumen_cobertura_erp.empty:
            st.success("No hay pedidos pendientes fuera de DIGIP para evaluar.")
        else:
            total_pedidos = int(
                resumen_cobertura_erp["Pedido"].nunique()
            )
            con_faltante = int(
                resumen_cobertura_erp["UnidadesFaltantes"].gt(0).sum()
            )
            sin_cobertura = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("Sin cobertura")
                .sum()
            )
            cobertura_transito = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("Cobertura en tránsito")
                .sum()
            )
            con_diferencias = int(
                resumen_cobertura_erp["CodigosConDiferencia"].gt(0).sum()
            )
            unidades_faltantes = int(
                resumen_cobertura_erp["UnidadesFaltantes"].sum()
            )

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric(
                "Pendientes fuera de DIGIP",
                f"{total_pedidos:,}".replace(",", "."),
            )
            c2.metric(
                "Pedidos con faltante",
                f"{con_faltante:,}".replace(",", "."),
            )
            c3.metric(
                "Sin cobertura real",
                f"{sin_cobertura:,}".replace(",", "."),
            )
            c4.metric(
                "Cubiertos por tránsito",
                f"{cobertura_transito:,}".replace(",", "."),
            )
            c5.metric(
                "Diferencias ERP/WMS",
                f"{con_diferencias:,}".replace(",", "."),
            )

            st.caption(
                f"Unidades sin cobertura inmediata: "
                f"{unidades_faltantes:,}".replace(",", ".")
            )

            pedidos_informados = obtener_pedidos_informados()

            filtro_1, filtro_2, filtro_3 = st.columns(
                [1.05, 1.05, 1.35]
            )

            with filtro_1:
                solo_problemas = st.toggle(
                    "Mostrar solo casos con problemas",
                    value=True,
                    key="pedidos_solo_problemas_cobertura",
                    help=(
                        "Muestra únicamente Sin cobertura y "
                        "Cobertura en tránsito."
                    ),
                )

            with filtro_2:
                ocultar_informados = st.toggle(
                    "Ocultar pedidos informados",
                    value=True,
                    key="pedidos_ocultar_informados_cobertura",
                )

            with filtro_3:
                estados_cobertura = st.multiselect(
                    "Estado de cobertura",
                    options=[
                        "Sin cobertura",
                        "Cobertura en tránsito",
                        "Con cobertura",
                    ],
                    default=[],
                    key="filtro_estado_cobertura_erp",
                )

            vista_resumen = resumen_cobertura_erp.copy()

            vista_resumen["Informado"] = (
                vista_resumen["Pedido"]
                .astype(str)
                .isin(pedidos_informados)
            )

            if solo_problemas:
                vista_resumen = vista_resumen.loc[
                    vista_resumen["EstadoCobertura"].isin(
                        [
                            "Sin cobertura",
                            "Cobertura en tránsito",
                        ]
                    )
                ].copy()

            if ocultar_informados:
                vista_resumen = vista_resumen.loc[
                    ~vista_resumen["Informado"]
                ].copy()

            if estados_cobertura:
                vista_resumen = vista_resumen.loc[
                    vista_resumen["EstadoCobertura"].isin(
                        estados_cobertura
                    )
                ].copy()

            pedidos_visibles = set(
                vista_resumen["Pedido"].astype(str)
            )

            vista_lineas = lineas_cobertura_erp.loc[
                lineas_cobertura_erp["Pedido"]
                .astype(str)
                .isin(pedidos_visibles)
            ].copy()

            if solo_problemas:
                # El botón controla específicamente la tabla de detalle:
                # cuando está activo, oculta todos los ítems con cobertura,
                # aunque tengan una alerta de diferencia ERP/WMS.
                vista_lineas = vista_lineas.loc[
                    vista_lineas["EstadoCobertura"].isin(
                        [
                            "Sin cobertura",
                            "Cobertura en tránsito",
                        ]
                    )
                ].copy()

            if vista_lineas.empty:
                resumen_codigos_faltantes = pd.DataFrame(
                    columns=[
                        "ArticuloCodigo",
                        "ArticuloDescripcion",
                        "DisponibleERP",
                        "TransitoERP",
                        "DisponibleWMS",
                        "DiferenciaERPvsWMS",
                        "Comprometido",
                        "FaltanteInmediato",
                        "FaltanteLuegoTransito",
                        "PedidosAfectados",
                        "AlertaStock",
                    ]
                )
            else:
                resumen_codigos_faltantes = (
                    vista_lineas
                    .groupby(
                        [
                            "ArticuloCodigo",
                            "ArticuloDescripcion",
                        ],
                        as_index=False,
                        dropna=False,
                    )
                    .agg(
                        DisponibleERP=(
                            "DisponibleERPInicial",
                            "max",
                        ),
                        TransitoERP=("TransitoERP", "max"),
                        DisponibleWMS=("DisponibleWMS", "max"),
                        DiferenciaERPvsWMS=(
                            "DiferenciaERPvsWMS",
                            "max",
                        ),
                        Comprometido=(
                            "CantidadSolicitada",
                            "sum",
                        ),
                        FaltanteInmediato=(
                            "CantidadFaltante",
                            "sum",
                        ),
                        FaltanteLuegoTransito=(
                            "FaltanteLuegoTransito",
                            "sum",
                        ),
                        ProximoIngresoOC=(
                            "FechaPrevistaIngresoOC",
                            "min",
                        ),
                        PedidosAfectados=("Pedido", "nunique"),
                        AlertaStock=(
                            "AlertaStock",
                            lambda serie: " | ".join(
                                dict.fromkeys(
                                    valor
                                    for valor in serie.astype(str)
                                    if valor.strip()
                                )
                            ),
                        ),
                    )
                )

                resumen_codigos_faltantes = (
                    resumen_codigos_faltantes
                    .loc[
                        resumen_codigos_faltantes[
                            "FaltanteInmediato"
                        ].gt(0)
                        | resumen_codigos_faltantes[
                            "AlertaStock"
                        ].ne("")
                    ]
                    .sort_values(
                        by=[
                            "FaltanteLuegoTransito",
                            "FaltanteInmediato",
                            "ArticuloCodigo",
                        ],
                        ascending=[False, False, True],
                    )
                    .reset_index(drop=True)
                )

            st.markdown("#### Gestión de pedidos informados")

            usuario_actual = str(
                st.session_state.get(
                    "usuario",
                    st.session_state.get(
                        "username",
                        st.session_state.get(
                            "email",
                            "",
                        ),
                    ),
                )
            ).strip()

            opciones_para_informar = (
                vista_resumen.loc[
                    ~vista_resumen["Informado"],
                    "Pedido",
                ]
                .astype(str)
                .tolist()
            )

            col_informar_1, col_informar_2 = st.columns(
                [3, 1],
                vertical_alignment="bottom",
            )

            with col_informar_1:
                pedidos_a_informar = st.multiselect(
                    "Pedidos incluidos en el mail a Comercial",
                    options=opciones_para_informar,
                    default=[],
                    key="pedidos_seleccionados_para_informar",
                    placeholder="Seleccioná uno o varios pedidos",
                )

            with col_informar_2:
                confirmar_informados = st.button(
                    "📨 Marcar como informados",
                    key="marcar_cobertura_como_informada",
                    width="stretch",
                    disabled=not pedidos_a_informar,
                )

            if confirmar_informados:
                marcar_pedidos_informados(
                    pedidos=pedidos_a_informar,
                    usuario=usuario_actual,
                )

                st.toast(
                    f"{len(pedidos_a_informar)} pedido(s) "
                    "marcado(s) como informados.",
                    icon="✅",
                )
                st.rerun()

            with st.expander(
                f"📬 Historial de informados ({len(pedidos_informados)})",
                expanded=False,
            ):
                historial_informados = leer_pedidos_informados()
                historial_activo = historial_informados.loc[
                    historial_informados["Estado"].eq("INFORMADO")
                ].copy()

                if historial_activo.empty:
                    st.info("Todavía no hay pedidos marcados como informados.")
                else:
                    st.dataframe(
                        historial_activo,
                        hide_index=True,
                        width="stretch",
                        height=min(
                            330,
                            75 + len(historial_activo) * 35,
                        ),
                    )

                    pedidos_a_reabrir = st.multiselect(
                        "Volver a mostrar pedidos",
                        options=historial_activo["Pedido"].tolist(),
                        default=[],
                        key="pedidos_informados_a_reabrir",
                    )

                    if st.button(
                        "↩️ Quitar marca de informado",
                        key="reabrir_pedidos_cobertura",
                        disabled=not pedidos_a_reabrir,
                    ):
                        reabrir_pedidos_informados(
                            pedidos=pedidos_a_reabrir,
                            usuario=usuario_actual,
                        )

                        st.toast(
                            f"{len(pedidos_a_reabrir)} pedido(s) "
                            "vuelven a estar visibles.",
                            icon="↩️",
                        )
                        st.rerun()

            st.markdown("#### Resumen por pedido")
            st.dataframe(
                vista_resumen,
                hide_index=True,
                width="stretch",
                height=300,
                column_config={
                    "Informado": st.column_config.CheckboxColumn(
                        "Informado",
                        disabled=True,
                    ),
                    "Fecha": st.column_config.DateColumn(
                        "Fecha",
                        format="DD/MM/YYYY",
                    ),
                    "Planificacion": st.column_config.TextColumn(
                        "Día de entrega",
                        width="medium",
                    ),
                    "ProximoIngresoOC": st.column_config.DateColumn(
                        "Próximo ingreso OC",
                        format="DD/MM/YYYY",
                        width="medium",
                    ),
                    "EstadoIngresoOC": st.column_config.TextColumn(
                        "Estado ingreso OC",
                        width="medium",
                    ),
                    "PorcentajeCobertura": (
                        st.column_config.ProgressColumn(
                            "Cobertura inmediata",
                            min_value=0,
                            max_value=100,
                            format="%.1f %%",
                        )
                    ),
                    "UnidadesFaltantes": (
                        st.column_config.NumberColumn(
                            "Faltante inmediato",
                            format="%d",
                        )
                    ),
                    "UnidadesEnTransito": (
                        st.column_config.NumberColumn(
                            "Cubierto por tránsito",
                            format="%d",
                        )
                    ),
                    "FaltanteLuegoTransito": (
                        st.column_config.NumberColumn(
                            "Faltante real",
                            format="%d",
                        )
                    ),
                    "CodigosConDiferencia": (
                        st.column_config.NumberColumn(
                            "Diferencias ERP/WMS",
                            format="%d",
                        )
                    ),
                },
            )

            columna_detalle, columna_codigos = st.columns(
                [1.35, 1],
                gap="large",
                vertical_alignment="top",
            )

            with columna_detalle:
                st.markdown("#### Detalle por artículo y pedido")
                st.dataframe(
                    vista_lineas,
                    hide_index=True,
                    width="stretch",
                    height=600,
                    column_config={
                        "Fecha": st.column_config.DateColumn(
                            "Fecha",
                            format="DD/MM/YYYY",
                        ),
                        "OrdenCompraProxima": st.column_config.TextColumn(
                            "OC próxima",
                            width="small",
                        ),
                        "FechaPrevistaIngresoOC": st.column_config.DateColumn(
                            "Fecha prevista OC",
                            format="DD/MM/YYYY",
                            width="medium",
                        ),
                        "EstadoIngresoOC": st.column_config.TextColumn(
                            "Estado ingreso OC",
                            width="medium",
                        ),
                        "CantidadSolicitada": (
                            st.column_config.NumberColumn(
                                "Solicitado",
                                format="%d",
                            )
                        ),
                        "DisponibleERPInicial": (
                            st.column_config.NumberColumn(
                                "Disponible ERP",
                                format="%d",
                            )
                        ),
                        "TransitoERP": (
                            st.column_config.NumberColumn(
                                "Tránsito ERP",
                                format="%d",
                            )
                        ),
                        "DisponibleWMS": (
                            st.column_config.NumberColumn(
                                "Disponible WMS",
                                format="%d",
                            )
                        ),
                        "DiferenciaERPvsWMS": (
                            st.column_config.NumberColumn(
                                "Dif. ERP-WMS",
                                format="%d",
                            )
                        ),
                        "CantidadFaltante": (
                            st.column_config.NumberColumn(
                                "Faltante inmediato",
                                format="%d",
                            )
                        ),
                        "FaltanteLuegoTransito": (
                            st.column_config.NumberColumn(
                                "Faltante real",
                                format="%d",
                            )
                        ),
                    },
                )

            with columna_codigos:
                st.markdown("#### Diagnóstico consolidado por código")
                st.caption(
                    "Compara el disponible aprobado del ERP, el tránsito "
                    "y el disponible operativo del WMS."
                )

                if resumen_codigos_faltantes.empty:
                    st.success(
                        "No hay faltantes ni diferencias para los pedidos visibles."
                    )
                else:
                    st.dataframe(
                        resumen_codigos_faltantes,
                        hide_index=True,
                        width="stretch",
                        height=600,
                        column_config={
                            "ArticuloCodigo": (
                                st.column_config.TextColumn(
                                    "Código",
                                    width="small",
                                )
                            ),
                            "ArticuloDescripcion": (
                                st.column_config.TextColumn(
                                    "Descripción",
                                    width="large",
                                )
                            ),
                            "ProximoIngresoOC": st.column_config.DateColumn(
                                "Próximo ingreso OC",
                                format="DD/MM/YYYY",
                                width="medium",
                            ),
                            "DisponibleERP": (
                                st.column_config.NumberColumn(
                                    "ERP disponible",
                                    format="%d",
                                )
                            ),
                            "TransitoERP": (
                                st.column_config.NumberColumn(
                                    "ERP tránsito",
                                    format="%d",
                                )
                            ),
                            "DisponibleWMS": (
                                st.column_config.NumberColumn(
                                    "WMS disponible",
                                    format="%d",
                                )
                            ),
                            "DiferenciaERPvsWMS": (
                                st.column_config.NumberColumn(
                                    "Dif. ERP-WMS",
                                    format="%d",
                                )
                            ),
                            "Comprometido": (
                                st.column_config.NumberColumn(
                                    "Comprometido",
                                    format="%d",
                                )
                            ),
                            "FaltanteInmediato": (
                                st.column_config.NumberColumn(
                                    "Faltante inmediato",
                                    format="%d",
                                )
                            ),
                            "FaltanteLuegoTransito": (
                                st.column_config.NumberColumn(
                                    "Faltante real",
                                    format="%d",
                                )
                            ),
                        },
                    )

            col_descarga1, col_descarga2, col_descarga3 = st.columns(3)

            with col_descarga1:
                st.download_button(
                    "⬇️ Descargar resumen",
                    data=vista_resumen.to_csv(
                        index=False,
                        sep=";",
                        encoding="utf-8-sig",
                    ).encode("utf-8-sig"),
                    file_name="Pedidos_ERP_Sin_Cobertura.csv",
                    mime="text/csv",
                    key="descargar_resumen_cobertura_erp",
                    width="stretch",
                )

            with col_descarga2:
                st.download_button(
                    "⬇️ Descargar detalle",
                    data=vista_lineas.to_csv(
                        index=False,
                        sep=";",
                        encoding="utf-8-sig",
                    ).encode("utf-8-sig"),
                    file_name="Detalle_Pedidos_ERP_Sin_Cobertura.csv",
                    mime="text/csv",
                    key="descargar_detalle_cobertura_erp",
                    width="stretch",
                )

            with col_descarga3:
                st.download_button(
                    "⬇️ Descargar diagnóstico",
                    data=resumen_codigos_faltantes.to_csv(
                        index=False,
                        sep=";",
                        encoding="utf-8-sig",
                    ).encode("utf-8-sig"),
                    file_name="Diagnostico_Stock_ERP_WMS.csv",
                    mime="text/csv",
                    key="descargar_diagnostico_stock_erp_wms",
                    width="stretch",
                )


