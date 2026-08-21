from __future__ import annotations

import pandas as pd
import streamlit as st

from models.cobertura_pedidos import analizar_cobertura_pedidos_erp
from utils.gestion_cobertura import (
    leer_pedidos_informados, marcar_pedidos_informados,
    obtener_pedidos_informados, reabrir_pedidos_informados,
)
from utils.pedidos.carga import cargar_datos_cobertura


def _normalizar_pedido_cobertura(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.split()
        .str[-1]
        .str.split("-")
        .str[0]
        .str.strip()
    )


def _construir_estado_transmision_cobertura(
    df_detalle_erp: pd.DataFrame | None,
    df_pedidos_digip: pd.DataFrame | None,
    tabla_transmisiones: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Construye una fila por pedido con el avance operativo de transmisión.

    Unidades transmitidas/gestionadas = remitidas + reservadas del ERP,
    limitadas a la cantidad original de cada línea. Esto mantiene el avance
    aun cuando una parte ya fue remitida y la reserva vuelve a cero.

    DIGIP y Pedidos Transmisión se usan como evidencia de transmisión y
    para obtener la fecha.
    """
    columnas = [
        "Pedido",
        "UnidadesOriginales",
        "UnidadesTransmitidas",
        "UnidadesSinTransmitir",
        "PorcentajeTransmitido",
        "FechaTransmision",
        "PedidoTransmitido",
    ]

    if df_detalle_erp is None or df_detalle_erp.empty:
        return pd.DataFrame(columns=columnas)

    detalle = df_detalle_erp.copy()

    if "nro_com" not in detalle.columns or "can_art" not in detalle.columns:
        return pd.DataFrame(columns=columnas)

    detalle["Pedido"] = _normalizar_pedido_cobertura(detalle["nro_com"])

    for columna in ["can_art", "can_rem", "can_reserv"]:
        if columna not in detalle.columns:
            detalle[columna] = 0
        detalle[columna] = (
            pd.to_numeric(detalle[columna], errors="coerce")
            .fillna(0)
            .clip(lower=0)
        )

    detalle["UnidadesOriginalesLinea"] = detalle["can_art"]
    detalle["UnidadesGestionadasLinea"] = (
        detalle["can_rem"] + detalle["can_reserv"]
    ).clip(lower=0)

    detalle["UnidadesGestionadasLinea"] = detalle[
        ["UnidadesGestionadasLinea", "UnidadesOriginalesLinea"]
    ].min(axis=1)

    avance = (
        detalle
        .groupby("Pedido", as_index=False)
        .agg(
            UnidadesOriginales=("UnidadesOriginalesLinea", "sum"),
            UnidadesTransmitidas=("UnidadesGestionadasLinea", "sum"),
        )
    )

    avance["UnidadesOriginales"] = (
        pd.to_numeric(avance["UnidadesOriginales"], errors="coerce")
        .fillna(0).round(0).astype(int)
    )
    avance["UnidadesTransmitidas"] = (
        pd.to_numeric(avance["UnidadesTransmitidas"], errors="coerce")
        .fillna(0).round(0).astype(int)
    )
    avance["UnidadesSinTransmitir"] = (
        avance["UnidadesOriginales"] - avance["UnidadesTransmitidas"]
    ).clip(lower=0)

    avance["PorcentajeTransmitido"] = (
        avance["UnidadesTransmitidas"]
        .div(avance["UnidadesOriginales"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .clip(lower=0, upper=100)
        .round(1)
    )

    pedidos_en_digip: set[str] = set()
    fecha_digip = pd.DataFrame(columns=["Pedido", "FechaDIGIP"])
    unidades_digip_por_pedido = pd.DataFrame(
        columns=["Pedido", "UnidadesTransmitidasDIGIP"]
    )

    if df_pedidos_digip is not None and not df_pedidos_digip.empty:
        digip = df_pedidos_digip.copy()

        # El modelo nuevo entrega "Pedido" ya normalizado. Se mantienen
        # aliases históricos para compatibilidad con reportes anteriores.
        columna_codigo = next(
            (
                c for c in [
                    "Pedido",
                    "Codigo",
                    "Código pedido",
                    "Codigo pedido",
                ]
                if c in digip.columns
            ),
            None,
        )

        if columna_codigo is not None:
            digip["Pedido"] = _normalizar_pedido_cobertura(
                digip[columna_codigo]
            )

            estado = (
                digip.get("Estado", pd.Series("", index=digip.index))
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )

            # Fuente prioritaria: unidades reales informadas por DIGIP.
            # No usamos TotalUnidades aquí porque ese campo pertenece al
            # cálculo histórico del modelo y puede repetirse por transmisión.
            columna_unidades_digip = next(
                (
                    c for c in [
                        "UnidadesPedidas",
                        "Unidades pedidas",
                    ]
                    if c in digip.columns
                ),
                None,
            )

            mascara_base = (
                digip["Pedido"].ne("")
                & ~estado.eq("ELIMINADO")
            )

            if columna_unidades_digip is not None:
                digip["UnidadesTransmitidasDIGIP"] = (
                    pd.to_numeric(
                        digip[columna_unidades_digip],
                        errors="coerce",
                    )
                    .fillna(0)
                    .clip(lower=0)
                )

                mascara_valida = (
                    mascara_base
                    & digip["UnidadesTransmitidasDIGIP"].gt(0)
                )

                pedidos_en_digip = set(
                    digip.loc[mascara_valida, "Pedido"].astype(str)
                )

                unidades_digip_por_pedido = (
                    digip.loc[
                        mascara_base,
                        ["Pedido", "UnidadesTransmitidasDIGIP"],
                    ]
                    .groupby("Pedido", as_index=False)
                    .agg(
                        UnidadesTransmitidasDIGIP=(
                            "UnidadesTransmitidasDIGIP",
                            "sum",
                        )
                    )
                )
            else:
                # Compatibilidad con el reporte anterior: si todavía no
                # existe la columna nueva, no se cambia el cálculo histórico.
                mascara_valida = mascara_base
                pedidos_en_digip = set(
                    digip.loc[mascara_valida, "Pedido"].astype(str)
                )

            if "Fecha" in digip.columns:
                digip["FechaDIGIP"] = pd.to_datetime(
                    digip["Fecha"],
                    errors="coerce",
                    dayfirst=True,
                )
                fecha_digip = (
                    digip.loc[mascara_valida, ["Pedido", "FechaDIGIP"]]
                    .groupby("Pedido", as_index=False)
                    .agg(FechaDIGIP=("FechaDIGIP", "max"))
                )

    # Si DIGIP ya informa unidades, reemplaza exclusivamente el numerador
    # del avance. Las unidades originales continúan saliendo del ERP.
    if not unidades_digip_por_pedido.empty:
        avance = avance.merge(
            unidades_digip_por_pedido,
            on="Pedido",
            how="left",
            validate="one_to_one",
        )

        tiene_unidades_digip = avance[
            "UnidadesTransmitidasDIGIP"
        ].notna()

        avance.loc[
            tiene_unidades_digip,
            "UnidadesTransmitidas",
        ] = (
            pd.to_numeric(
                avance.loc[
                    tiene_unidades_digip,
                    "UnidadesTransmitidasDIGIP",
                ],
                errors="coerce",
            )
            .fillna(0)
            .round(0)
            .astype(int)
        )

        # Nunca permitir que el WMS supere el total original ERP para
        # este indicador porcentual.
        avance["UnidadesTransmitidas"] = avance[
            ["UnidadesTransmitidas", "UnidadesOriginales"]
        ].min(axis=1)

        avance["UnidadesSinTransmitir"] = (
            avance["UnidadesOriginales"]
            - avance["UnidadesTransmitidas"]
        ).clip(lower=0)

        avance["PorcentajeTransmitido"] = (
            avance["UnidadesTransmitidas"]
            .div(avance["UnidadesOriginales"].replace(0, pd.NA))
            .mul(100)
            .fillna(0)
            .clip(lower=0, upper=100)
            .round(1)
        )

        avance = avance.drop(
            columns=["UnidadesTransmitidasDIGIP"],
            errors="ignore",
        )

    fechas_transmision = pd.DataFrame(
        columns=["Pedido", "FechaTransmisionERP"]
    )
    pedidos_con_transmision: set[str] = set()

    if tabla_transmisiones is not None and not tabla_transmisiones.empty:
        trans = tabla_transmisiones.copy()

        if "Pedido" in trans.columns:
            trans["Pedido"] = _normalizar_pedido_cobertura(trans["Pedido"])

            fecha_col = next(
                (
                    c for c in [
                        "FechaTransmisionERP",
                        "F Envio Digip",
                        "FechaEnvioDIGIP",
                    ]
                    if c in trans.columns
                ),
                None,
            )

            if fecha_col is not None:
                trans["FechaTransmisionERP"] = pd.to_datetime(
                    trans[fecha_col],
                    errors="coerce",
                    dayfirst=True,
                )
                fechas_transmision = (
                    trans[["Pedido", "FechaTransmisionERP"]]
                    .groupby("Pedido", as_index=False)
                    .agg(FechaTransmisionERP=("FechaTransmisionERP", "max"))
                )

            pedidos_con_transmision = set(
                trans.loc[trans["Pedido"].ne(""), "Pedido"].astype(str)
            )

    avance = avance.merge(
        fechas_transmision,
        on="Pedido",
        how="left",
        validate="one_to_one",
    )
    avance = avance.merge(
        fecha_digip,
        on="Pedido",
        how="left",
        validate="one_to_one",
    )

    avance["FechaTransmision"] = (
        avance["FechaTransmisionERP"]
        .combine_first(avance["FechaDIGIP"])
    )

    evidencia = (
        avance["Pedido"].isin(pedidos_en_digip)
        | avance["Pedido"].isin(pedidos_con_transmision)
    )
    avance["PedidoTransmitido"] = (
        avance["UnidadesTransmitidas"].gt(0) & evidencia
    )

    return avance[columnas].copy()


def render_cobertura(
    df_pedidos: pd.DataFrame,
    df_pendientes_erp: pd.DataFrame,
    tabla_clientes: pd.DataFrame,
    tabla_detalle_dashboard: pd.DataFrame,
    df_detalle_erp: pd.DataFrame | None = None,
    tabla_transmisiones: pd.DataFrame | None = None,
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

        estado_transmision = _construir_estado_transmision_cobertura(
            df_detalle_erp=df_detalle_erp,
            df_pedidos_digip=df_pedidos,
            tabla_transmisiones=tabla_transmisiones,
        )

        if not resumen_cobertura_erp.empty:
            resumen_cobertura_erp = resumen_cobertura_erp.copy()
            resumen_cobertura_erp["Pedido"] = _normalizar_pedido_cobertura(
                resumen_cobertura_erp["Pedido"]
            )
            resumen_cobertura_erp = resumen_cobertura_erp.merge(
                estado_transmision,
                on="Pedido",
                how="left",
                validate="one_to_one",
            )

            for columna in [
                "UnidadesOriginales",
                "UnidadesTransmitidas",
                "UnidadesSinTransmitir",
            ]:
                resumen_cobertura_erp[columna] = (
                    pd.to_numeric(
                        resumen_cobertura_erp[columna],
                        errors="coerce",
                    )
                    .fillna(0)
                    .astype(int)
                )

            resumen_cobertura_erp["PorcentajeTransmitido"] = (
                pd.to_numeric(
                    resumen_cobertura_erp["PorcentajeTransmitido"],
                    errors="coerce",
                )
                .fillna(0)
                .round(1)
            )

            resumen_cobertura_erp["PedidoTransmitido"] = (
                resumen_cobertura_erp["PedidoTransmitido"]
                .fillna(False)
                .astype(bool)
            )
        st.subheader("🚨 Compromisos ERP sin cobertura")
        st.caption(
            "La cobertura inmediata se calcula con el disponible aprobado del ERP "
            "(est_1). El pendiente o tránsito se toma de est_8. El stock WMS se "
            "mantiene como control para detectar diferencias entre sistemas."
        )

        if resumen_cobertura_erp.empty:
            st.success("No hay pedidos con saldo pendiente para evaluar.")
        else:
            casos_sin_cobertura = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .isin([
                    "SIN COBERTURA TOTAL",
                    "SIN COBERTURA PARCIAL",
                ])
                .sum()
            )
            sin_cobertura_total = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("SIN COBERTURA TOTAL")
                .sum()
            )
            sin_cobertura_parcial = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("SIN COBERTURA PARCIAL")
                .sum()
            )
            cobertura_transito = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("COBERTURA EN TRÁNSITO")
                .sum()
            )
            cobertura_completa = int(
                resumen_cobertura_erp["EstadoCobertura"]
                .eq("COBERTURA COMPLETA")
                .sum()
            )
            con_diferencias = int(
                resumen_cobertura_erp["CodigosConDiferencia"].gt(0).sum()
            )
            unidades_faltantes = int(
                resumen_cobertura_erp["UnidadesFaltantes"].sum()
            )

            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric(
                "Casos sin cobertura",
                f"{casos_sin_cobertura:,}".replace(",", "."),
            )
            c2.metric(
                "Sin cobertura total",
                f"{sin_cobertura_total:,}".replace(",", "."),
            )
            c3.metric(
                "Sin cobertura parcial",
                f"{sin_cobertura_parcial:,}".replace(",", "."),
            )
            c4.metric(
                "Cobertura en tránsito",
                f"{cobertura_transito:,}".replace(",", "."),
            )
            c5.metric(
                "Cobertura completa",
                f"{cobertura_completa:,}".replace(",", "."),
            )
            c6.metric(
                "Diferencias ERP/WMS",
                f"{con_diferencias:,}".replace(",", "."),
            )

            st.caption(
                f"Unidades sin cobertura inmediata: "
                f"{unidades_faltantes:,}".replace(",", ".")
            )

            pedidos_informados = obtener_pedidos_informados()

            filtro_1, filtro_2, filtro_3, filtro_4 = st.columns(
                [0.95, 1.05, 1.25, 1.25]
            )

            with filtro_1:
                solo_problemas = st.toggle(
                    "Mostrar solo casos con problemas",
                    value=True,
                    key="pedidos_solo_problemas_cobertura",
                    help=(
                        "Oculta Cobertura completa y muestra únicamente "
                        "los pedidos que requieren seguimiento."
                    ),
                )

            with filtro_2:
                ocultar_informados = st.toggle(
                    "Ocultar pedidos informados",
                    value=True,
                    key="pedidos_ocultar_informados_cobertura",
                )

            with filtro_3:
                etiquetas_estado = {
                    "Sin cobertura total": "SIN COBERTURA TOTAL",
                    "Sin cobertura parcial": "SIN COBERTURA PARCIAL",
                    "Cobertura en tránsito": "COBERTURA EN TRÁNSITO",
                    "Cobertura completa": "COBERTURA COMPLETA",
                }

                estados_cobertura_ui = st.multiselect(
                    "Estado de cobertura",
                    options=list(etiquetas_estado.keys()),
                    default=[],
                    key="filtro_estado_cobertura_erp",
                )

                estados_cobertura = [
                    etiquetas_estado[estado]
                    for estado in estados_cobertura_ui
                ]

            with filtro_4:
                etiquetas_gestion = {
                    "Pendiente de informar": "PENDIENTE DE INFORMAR",
                    "Informado": "INFORMADO",
                    "Pedido transmitido": "PEDIDO TRANSMITIDO",
                }
                estados_gestion_ui = st.multiselect(
                    "Estado de gestión",
                    options=list(etiquetas_gestion.keys()),
                    default=[],
                    key="filtro_estado_gestion_cobertura",
                )
                estados_gestion = [
                    etiquetas_gestion[estado]
                    for estado in estados_gestion_ui
                ]

            vista_resumen = resumen_cobertura_erp.copy()

            vista_resumen["Informado"] = (
                vista_resumen["Pedido"]
                .astype(str)
                .isin(pedidos_informados)
            )

            vista_resumen["EstadoGestion"] = "PENDIENTE DE INFORMAR"
            vista_resumen.loc[
                vista_resumen["Informado"],
                "EstadoGestion",
            ] = "INFORMADO"
            vista_resumen.loc[
                vista_resumen["PedidoTransmitido"],
                "EstadoGestion",
            ] = "PEDIDO TRANSMITIDO"

            gestion_problemas = vista_resumen.loc[
                vista_resumen["EstadoCobertura"].isin(
                    [
                        "SIN COBERTURA TOTAL",
                        "SIN COBERTURA PARCIAL",
                        "COBERTURA EN TRÁNSITO",
                    ]
                )
            ].copy()

            g1, g2, g3 = st.columns(3)
            g1.metric(
                "🔴 Pendientes de informar",
                int(
                    gestion_problemas["EstadoGestion"]
                    .eq("PENDIENTE DE INFORMAR")
                    .sum()
                ),
            )
            g2.metric(
                "📨 Informados",
                int(
                    gestion_problemas["EstadoGestion"]
                    .eq("INFORMADO")
                    .sum()
                ),
            )
            g3.metric(
                "✅ Pedidos transmitidos",
                int(
                    gestion_problemas["EstadoGestion"]
                    .eq("PEDIDO TRANSMITIDO")
                    .sum()
                ),
                help=(
                    "Pedidos con unidades remitidas/reservadas y evidencia "
                    "de transmisión en DIGIP o Pedidos Transmisión."
                ),
            )

            if solo_problemas:
                vista_resumen = vista_resumen.loc[
                    vista_resumen["EstadoCobertura"].isin(
                        [
                            "SIN COBERTURA TOTAL",
                            "SIN COBERTURA PARCIAL",
                            "COBERTURA EN TRÁNSITO",
                        ]
                    )
                ].copy()

            if ocultar_informados:
                vista_resumen = vista_resumen.loc[
                    ~vista_resumen["EstadoGestion"].eq("INFORMADO")
                ].copy()

            if estados_gestion:
                vista_resumen = vista_resumen.loc[
                    vista_resumen["EstadoGestion"].isin(estados_gestion)
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

            vista_resumen_display = vista_resumen.copy()

            columnas_prioritarias = [
                "Pedido",
                "Fecha",
                "ClienteCodigo",
                "ClienteDescripcion",
                "Planificacion",
                "EstadoGestion",
                "PorcentajeTransmitido",
                "UnidadesOriginales",
                "UnidadesTransmitidas",
                "UnidadesSinTransmitir",
                "FechaTransmision",
                "CategoriaPedidoPendiente",
            ]
            columnas_ordenadas = [
                c for c in columnas_prioritarias
                if c in vista_resumen_display.columns
            ] + [
                c for c in vista_resumen_display.columns
                if c not in columnas_prioritarias
            ]
            vista_resumen_display = vista_resumen_display[
                columnas_ordenadas
            ]

            etiquetas_estado_display = {
                "SIN COBERTURA TOTAL": "Sin cobertura total",
                "SIN COBERTURA PARCIAL": "Sin cobertura parcial",
                "COBERTURA EN TRÁNSITO": "Cobertura en tránsito",
                "COBERTURA COMPLETA": "Cobertura completa",
            }

            vista_resumen_display["EstadoGestion"] = (
                vista_resumen_display["EstadoGestion"].replace(
                    {
                        "PENDIENTE DE INFORMAR": "Pendiente de informar",
                        "INFORMADO": "Informado",
                        "PEDIDO TRANSMITIDO": "Pedido transmitido",
                    }
                )
            )

            for columna_estado in [
                "EstadoCobertura",
                "CategoriaPedidoPendiente",
            ]:
                if columna_estado in vista_resumen_display.columns:
                    vista_resumen_display[columna_estado] = (
                        vista_resumen_display[columna_estado]
                        .replace(etiquetas_estado_display)
                    )

            st.dataframe(
                vista_resumen_display,
                hide_index=True,
                width="stretch",
                height=300,
                column_config={
                    "EstadoGestion": st.column_config.TextColumn(
                        "Estado gestión",
                        width="medium",
                    ),
                    "PorcentajeTransmitido": st.column_config.ProgressColumn(
                        "% transmitido",
                        min_value=0,
                        max_value=100,
                        format="%.1f %%",
                        width="medium",
                    ),
                    "UnidadesOriginales": st.column_config.NumberColumn(
                        "Unidades originales",
                        format="%d",
                    ),
                    "UnidadesTransmitidas": st.column_config.NumberColumn(
                        "Unidades transmitidas",
                        format="%d",
                    ),
                    "UnidadesSinTransmitir": st.column_config.NumberColumn(
                        "Sin transmitir",
                        format="%d",
                    ),
                    "FechaTransmision": st.column_config.DateColumn(
                        "Fecha transmisión",
                        format="DD/MM/YYYY",
                        width="medium",
                    ),
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


