from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.leer_gestion_consultas import (
    obtener_solicitudes_abiertas, obtener_urgencias_activas,
    obtener_anulaciones_pendientes, obtener_reclamos_abiertos,
)
from utils.gestion_consultas import finalizar_solicitud_automaticamente
from models.dashboard_pedidos import preparar_datos_dashboard
from utils.pedidos.carga import (
    cargar_datos_base, cargar_datos_cobertura, construir_tablas_base_cacheadas,
    limpiar_cache_pedidos,
)


def render_modulo_pedidos() -> None:
    # -----------------------------------------------------
    # BARRA DE ACTUALIZACIÓN
    # -----------------------------------------------------

    col_actualizacion_1, col_actualizacion_2 = st.columns(
        [5, 1],
        vertical_alignment="center"
    )

    with col_actualizacion_1:
        st.caption(
            "Los datos se mantienen en memoria mientras filtrás, "
            "planificás o ejecutás camionetas."
        )

    with col_actualizacion_2:
        actualizar_datos = st.button(
            "🔄 Actualizar datos",
            key="actualizar_datos_pedidos",
            width="stretch",
            help=(
                "Vuelve a leer todos los archivos de origen "
                "y elimina la planificación anterior."
            )
        )


    if actualizar_datos:

        limpiar_cache_pedidos()

        claves_planificacion = [
            "asignacion_camionetas",
            "pedidos_planificados",
            "capacidad_camioneta",
            "agrupadores_ocupados",
            "agrupadores_a_crear",
        ]

        for clave in claves_planificacion:
            st.session_state.pop(
                clave,
                None
            )

        claves_ejecucion = [
            clave
            for clave in st.session_state.keys()
            if str(clave).startswith(
                "resultado_digip_"
            )
        ]

        for clave in claves_ejecucion:
            st.session_state.pop(
                clave,
                None
            )

        # Limpiar filtros porque el rango de fechas puede cambiar
        st.session_state.pop(
            "filtros_pedidos",
            None
        )

        st.toast(
            "Datos actualizados correctamente.",
            icon="✅"
        )

        st.rerun()


    datos_operativos = cargar_datos_base()

    # Se entregan copias para evitar que las transformaciones
    # posteriores modifiquen accidentalmente la caché.
    df_pedidos = datos_operativos["pedidos"].copy()
    df_detalle = datos_operativos["detalle"].copy()
    df_articulos = datos_operativos["articulos"].copy()
    df_clientes = datos_operativos["clientes"].copy()
    df_pendientes_erp = datos_operativos[
        "pendientes_erp"
    ].copy()
    df_transmisiones = datos_operativos[
        "transmisiones"
    ].copy()
    df_expresos = datos_operativos["expresos"].copy()
    df_volumetria = datos_operativos["volumetria"].copy()


    # =====================================================
    # CONSTRUIR TABLAS BASE CACHEADAS
    # =====================================================

    tablas_base = construir_tablas_base_cacheadas(
        df_pedidos,
        df_detalle,
        df_articulos,
        df_clientes,
        df_volumetria,
        df_transmisiones,
        df_expresos,
        df_pendientes_erp,
    )

    tabla = tablas_base["pedidos"].copy()
    tabla_detalle_dashboard = tablas_base["detalle"]
    tabla_transmisiones = tablas_base["transmisiones"]
    tabla_expresos = tablas_base["expresos"]
    tabla_clientes = tablas_base["clientes"]
    tabla_pendientes_erp = tablas_base["pendientes_erp"]


    # =====================================================
    # BLOQUEOS POR GESTIONES COMERCIALES ABIERTAS
    # =====================================================

    def normalizar_pedido_gestion(valor: object) -> str:
        """
        Normaliza la clave utilizada para comparar las gestiones
        comerciales con la tabla operativa.
        """

        texto = str(valor or "").strip()

        if texto.endswith(".0"):
            texto = texto[:-2]

        return texto


    reclamos_abiertos = obtener_reclamos_abiertos()

    if reclamos_abiertos is None:
        reclamos_abiertos = pd.DataFrame()


    def obtener_pedidos_con_gestion_abierta() -> tuple[
        set[str],
        dict[str, set[str]],
    ]:
        """
        Devuelve todos los pedidos que no deben entrar en la
        planificación automática porque requieren revisión.

        Incluye:
        - solicitudes abiertas;
        - urgencias activas;
        - anulaciones pendientes;
        - reclamos abiertos.
        """

        gestiones = {
            "Solicitud": obtener_solicitudes_abiertas(),
            "Urgencia": obtener_urgencias_activas(),
            "Anulación": obtener_anulaciones_pendientes(),
            "Reclamo": reclamos_abiertos,
        }

        pedidos_por_gestion: dict[str, set[str]] = {}
        pedidos_bloqueados: set[str] = set()

        for tipo_gestion, dataframe in gestiones.items():

            if dataframe is None or dataframe.empty:
                pedidos_por_gestion[tipo_gestion] = set()
                continue

            if "Pedido" not in dataframe.columns:
                pedidos_por_gestion[tipo_gestion] = set()
                continue

            pedidos = set(
                dataframe["Pedido"]
                .apply(normalizar_pedido_gestion)
                .loc[lambda serie: serie.ne("")]
                .tolist()
            )

            pedidos_por_gestion[tipo_gestion] = pedidos
            pedidos_bloqueados.update(pedidos)

        return pedidos_bloqueados, pedidos_por_gestion


    pedidos_bloqueados_gestion, pedidos_por_tipo_gestion = (
        obtener_pedidos_con_gestion_abierta()
    )


    # =====================================================
    # SOLICITUDES COMERCIALES PENDIENTES
    # =====================================================

    def normalizar_pedido_wms_desde_codigo(valor: object) -> str:
        """
        Obtiene la clave utilizada por la tabla operativa desde
        el código completo del WMS.

        Ejemplo:
            9999 70-1 -> 70
        """

        texto = str(valor or "").strip()

        if not texto:
            return ""

        partes = texto.split()

        if len(partes) >= 2:
            texto = partes[1]

        return texto.split("-")[0].strip()


    # -----------------------------------------------------
    # CIERRE AUTOMÁTICO POR ESTADO REAL DEL PEDIDO
    # -----------------------------------------------------

    solicitudes_abiertas = obtener_solicitudes_abiertas()

    if solicitudes_abiertas is None:
        solicitudes_abiertas = pd.DataFrame()

    if (
        not solicitudes_abiertas.empty
        and df_pedidos is not None
        and not df_pedidos.empty
    ):

        pedidos_crudo = df_pedidos.copy()

        if "Codigo" in pedidos_crudo.columns:

            pedidos_crudo["PedidoGestion"] = (
                pedidos_crudo["Codigo"]
                .apply(normalizar_pedido_wms_desde_codigo)
            )

            pedidos_crudo["EstadoGestion"] = (
                pedidos_crudo.get(
                    "Estado",
                    pd.Series("", index=pedidos_crudo.index),
                )
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )

            pedidos_presentes = set(
                pedidos_crudo["PedidoGestion"]
                .loc[
                    pedidos_crudo["PedidoGestion"].ne("")
                ]
                .tolist()
            )

            pedidos_completos = set(
                pedidos_crudo.loc[
                    pedidos_crudo["EstadoGestion"].eq("COMPLETO"),
                    "PedidoGestion",
                ].tolist()
            )

            solicitudes_cerradas_automaticamente = 0

            for _, solicitud in solicitudes_abiertas.iterrows():

                solicitud_id = str(
                    solicitud.get("SolicitudID", "")
                ).strip()

                pedido_solicitud = str(
                    solicitud.get("Pedido", "")
                ).strip()

                motivo_cierre = ""

                if pedido_solicitud in pedidos_completos:
                    motivo_cierre = (
                        "Gestión cerrada automáticamente porque "
                        "el pedido pasó al estado Completo en DIGIP."
                    )

                elif pedido_solicitud not in pedidos_presentes:
                    motivo_cierre = (
                        "Gestión cerrada automáticamente porque "
                        "el pedido ya no figura en el reporte actual "
                        "de Pedidos DIGIP."
                    )

                if solicitud_id and motivo_cierre:

                    finalizar_solicitud_automaticamente(
                        solicitud_id=solicitud_id,
                        motivo=motivo_cierre,
                    )

                    solicitudes_cerradas_automaticamente += 1

            if solicitudes_cerradas_automaticamente:

                solicitudes_abiertas = (
                    obtener_solicitudes_abiertas()
                )

                st.toast(
                    (
                        f"{solicitudes_cerradas_automaticamente} "
                        "solicitud(es) finalizada(s) "
                        "automáticamente."
                    ),
                    icon="✅",
                )


    # -----------------------------------------------------
    # PREPARAR SOLICITUDES ABIERTAS PARA VISUALIZACIÓN
    # -----------------------------------------------------

    if solicitudes_abiertas is None:
        solicitudes_abiertas = pd.DataFrame()

    if not solicitudes_abiertas.empty:

        solicitudes_abiertas = solicitudes_abiertas.copy()

        solicitudes_abiertas["Pedido"] = (
            solicitudes_abiertas["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        solicitudes_abiertas["FechaSolicitudOrden"] = pd.to_datetime(
            solicitudes_abiertas["FechaSolicitud"],
            errors="coerce",
        )

        solicitudes_abiertas["FechaSolicitudVisible"] = (
            solicitudes_abiertas["FechaSolicitudOrden"]
            .dt.strftime("%d/%m/%Y %H:%M")
            .fillna(
                solicitudes_abiertas["FechaSolicitud"]
                .fillna("")
                .astype(str)
            )
        )

        solicitudes_abiertas = solicitudes_abiertas.sort_values(
            by="FechaSolicitudOrden",
            ascending=False,
            na_position="last",
        ).reset_index(drop=True)

        cantidad_solicitudes = (
            solicitudes_abiertas
            .groupby("Pedido", as_index=False)
            .agg(CantidadSolicitudes=("SolicitudID", "nunique"))
        )

        ultima_solicitud = (
            solicitudes_abiertas
            .drop_duplicates(subset=["Pedido"], keep="first")
            [[
                "Pedido",
                "TipoSolicitud",
                "Prioridad",
                "Descripcion",
                "UsuarioSolicitante",
                "FechaSolicitudVisible",
                "EstadoSolicitud",
            ]]
            .rename(columns={
                "TipoSolicitud": "TipoSolicitudPendiente",
                "Prioridad": "PrioridadSolicitud",
                "Descripcion": "DetalleSolicitud",
                "UsuarioSolicitante": "UsuarioSolicitud",
                "FechaSolicitudVisible": "FechaSolicitudPendiente",
                "EstadoSolicitud": "EstadoSolicitudPendiente",
            })
            .copy()
        )

        resumen_solicitudes = ultima_solicitud.merge(
            cantidad_solicitudes,
            on="Pedido",
            how="left",
            validate="one_to_one",
        )

    else:

        resumen_solicitudes = pd.DataFrame(columns=[
            "Pedido",
                                    ])


    # =====================================================
    # NORMALIZAR CLAVE PEDIDO
    # =====================================================

    tabla["Pedido"] = (
        tabla["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    tabla_pendientes_erp["Pedido"] = (
        tabla_pendientes_erp["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


    tabla_transmisiones["Pedido"] = (
        tabla_transmisiones["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.split("-")
        .str[0]
    )


    # =====================================================
    # MERGE PEDIDOS DIGIP + ÚLTIMA TRANSMISIÓN ERP
    # =====================================================

    tabla = tabla.merge(
        tabla_transmisiones,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    tabla["NroEnvioERP"] = (
        tabla["NroEnvioERP"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["EstadoTransmisionERP"] = (
        tabla["EstadoTransmisionERP"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["FechaTransmisionERP"] = pd.to_datetime(
        tabla["FechaTransmisionERP"],
        errors="coerce",
    )

    tabla["HoraTransmisionERP"] = (
        tabla["HoraTransmisionERP"]
        .fillna("")
        .astype(str)
        .str.strip()
    )


    # =====================================================
    # 1. MERGE PEDIDOS DIGIP + PENDIENTES ERP
    # =====================================================

    pendientes_planificacion = (
        tabla_pendientes_erp[
            [
                "Pedido",
                "CodigoSucursal",
                "CodigoExpreso",
                "ImporteERP"
            ]
        ]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first"
        )
        .copy()
    )

    tabla = tabla.merge(
        pendientes_planificacion,
        on="Pedido",
        how="left",
        validate="many_to_one"
    )


    # =====================================================
    # NORMALIZAR CLAVES DE PLANIFICACIÓN
    # =====================================================

    tabla["CodigoSucursal"] = (
        tabla["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla["CodigoExpreso"] = (
        tabla["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla_clientes["CodigoSucursal"] = (
        tabla_clientes["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla_expresos["CodigoExpreso"] = (
        tabla_expresos["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )


    # =====================================================
    # 2. MERGE CON MAESTRO CLIENTES
    # =====================================================

    clientes_planificacion = (
        tabla_clientes[
            [
                "CodigoSucursal",
                "FrecuenciaPreparacion",
                "FrecuenciaEntrega",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoSucursal"],
            keep="first"
        )
        .copy()
    )

    tabla = tabla.merge(
        clientes_planificacion,
        on="CodigoSucursal",
        how="left",
        validate="many_to_one"
    )


    # =====================================================
    # 3. MERGE CON MAESTRO EXPRESOS
    # =====================================================

    expresos_planificacion = (
        tabla_expresos[
            [
                "CodigoExpreso",
                "LocalidadExpreso",
                "ZonaAgrupadorExpreso",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoExpreso"],
            keep="first"
        )
        .copy()
    )

    tabla = tabla.merge(
        expresos_planificacion,
        on="CodigoExpreso",
        how="left",
        validate="many_to_one"
    )


    # =====================================================
    # LIMPIAR CAMPOS DE PLANIFICACIÓN
    # =====================================================

    columnas_planificacion = [
        "FrecuenciaPreparacion",
        "FrecuenciaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
    ]

    for columna in columnas_planificacion:

            tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )


    # =====================================================
    # REFERENCIAS FINALES DE PLANIFICACIÓN
    # =====================================================
    #
    # El día de entrega es siempre la referencia principal:
    # LUNES, MARTES, MIERCOLES, JUEVES, VIERNES, DIARIOS
    # o EXPRESOS.
    #
    # La zona del expreso se conserva en una columna separada
    # para determinar el grupo dentro de ese día.
    # =====================================================

    zona_expreso = (
        tabla["ZonaAgrupadorExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frecuencia_entrega = (
        tabla["FrecuenciaEntrega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # =====================================================
    # REGLA DE PRIORIDAD ABSOLUTA: RETIRA
    # =====================================================
    #
    # La referencia RETIRA proviene del agrupador de expresos.
    # Si ZonaAgrupadorExpreso indica RETIRA, debe prevalecer sobre
    # cualquier frecuencia semanal, zona o código de despacho.
    # =====================================================

    es_retira = zona_expreso.eq("RETIRA")

    tabla["DiaEntrega"] = frecuencia_entrega.where(
        ~es_retira,
        "RETIRA"
    )

    tabla["ZonaExpreso"] = zona_expreso

    # =====================================================
    # REGLA DEFINITIVA DE PLANIFICACIÓN
    # =====================================================
    #
    # Orden de prioridad:
    # 1. RETIRA informado en ZonaAgrupadorExpreso.
    # 2. Día semanal informado en FrecuenciaEntrega.
    # 3. Zona del expreso.
    # 4. Frecuencia de entrega restante.
    # =====================================================

    dias_entrega_semanal = {
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "MIÉRCOLES",
        "JUEVES",
        "VIERNES",
    }

    es_entrega_semanal = frecuencia_entrega.isin(
        dias_entrega_semanal
    )

    planificacion_base = frecuencia_entrega.where(
        es_entrega_semanal,
        zona_expreso.where(
            zona_expreso.ne(""),
            frecuencia_entrega
        )
    )

    tabla["Planificacion"] = planificacion_base.where(
        ~es_retira,
        "RETIRA"
    )

    # =====================================================
    # TIPOS DE DATOS DE LA TABLA OPERATIVA
    # =====================================================

    # -----------------------------------------------------
    # TEXTOS
    # -----------------------------------------------------

    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "FrecuenciaEntrega",
        "DiaEntrega",
        "ZonaAgrupadorExpreso",
        "ZonaExpreso",
        "Planificacion",
        "DetalleFamilias",
    ]

    for columna in columnas_texto:

        if columna in tabla.columns:

            tabla[columna] = (
                tabla[columna]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )


    # -----------------------------------------------------
    # FECHA
    # -----------------------------------------------------

    tabla["Fecha"] = pd.to_datetime(
        tabla["Fecha"],
        errors="coerce",
        dayfirst=True,
        utc=True,
    ).dt.tz_localize(None)


    # -----------------------------------------------------
    # ENTEROS
    # -----------------------------------------------------

    columnas_enteras = [
        "TotalUnidades",
        "TotalSKUs",
        "ImporteERP"
    ]

    for columna in columnas_enteras:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce"
            )
            .fillna(0)
            .astype(int)
        )

    # -----------------------------------------------------
    # DECIMALES
    # -----------------------------------------------------

        tabla["TotalM3"] = (
             pd.to_numeric(
             tabla["TotalM3"],
             errors="coerce"
        )
        .fillna(0)
        .round(3)
    )

    # =====================================================
    # SELECCIÓN FINAL Y ORDEN DE COLUMNAS
    # =====================================================

    columnas_finales = [
        "Pedido",
        "Fecha",
        "FechaTransmisionERP",
        "HoraTransmisionERP",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "DespachoDescripcion",
        "FrecuenciaEntrega",
        "DiaEntrega",
        "ZonaAgrupadorExpreso",
        "ZonaExpreso",
        "Planificacion",
        "TotalUnidades",
        "TotalM3",
        "TotalSKUs",
        "DetalleFamilias",
        "ImporteERP",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_finales
        if columna not in tabla.columns
    ]

    if columnas_faltantes:

        st.error(
            "Faltan columnas en la tabla operativa: "
            f"{columnas_faltantes}"
        )

        st.stop()

    # Selección estricta:
    # todo lo que no está en la lista queda eliminado
    tabla = tabla[columnas_finales].copy()


    # =====================================================
    # ENRIQUECER SOLICITUDES PARA EL PANEL SUPERIOR
    # =====================================================

    if not solicitudes_abiertas.empty:

        resumen_dimension_pedidos = (
            tabla[
                [
                    "Pedido",
                    "TotalUnidades",
                    "TotalM3",
                ]
            ]
            .drop_duplicates(
                subset=["Pedido"],
                keep="first",
            )
            .copy()
        )

        solicitudes_abiertas = solicitudes_abiertas.merge(
            resumen_dimension_pedidos,
            on="Pedido",
            how="left",
            validate="many_to_one",
        )

        solicitudes_abiertas["TotalUnidades"] = (
            pd.to_numeric(
                solicitudes_abiertas["TotalUnidades"],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

        solicitudes_abiertas["TotalM3"] = (
            pd.to_numeric(
                solicitudes_abiertas["TotalM3"],
                errors="coerce",
            )
            .fillna(0)
            .round(3)
        )


    # =====================================================
    # VISUALIZACIÓN
    # =====================================================

    st.title("📦 Gestión de Pedidos")

    st.caption(
        "Tabla operativa consolidada de pedidos DIGIP"
    )



    datos_dashboard = preparar_datos_dashboard(tabla)

    vista_pedidos = st.segmented_control(
        "Vista del módulo",
        options=[
            "📊 Dashboard",
            "🧠 Inteligencia analítica",
            "🚨 Compromisos sin cobertura",
            "📋 Tabla y gestiones",
        ],
        default="📊 Dashboard",
        key="vista_principal_pedidos",
        label_visibility="collapsed",
    )


    if vista_pedidos == "📊 Dashboard":
        from views.pedidos.dashboard import render_dashboard
        render_dashboard(datos_dashboard, tabla_detalle_dashboard)
    elif vista_pedidos == "🧠 Inteligencia analítica":
        from views.pedidos.inteligencia import render_inteligencia
        render_inteligencia(datos_dashboard, tabla_detalle_dashboard)
    elif vista_pedidos == "🚨 Compromisos sin cobertura":
        from views.pedidos.cobertura import render_cobertura
        render_cobertura(
            df_pedidos=df_pedidos,
            df_pendientes_erp=df_pendientes_erp,
            tabla_clientes=tabla_clientes,
            tabla_detalle_dashboard=tabla_detalle_dashboard,
        )
    else:
        from views.pedidos.tabla_gestiones import render_tabla_gestiones
        render_tabla_gestiones(
            tabla=tabla,
            solicitudes_abiertas=solicitudes_abiertas,
            reclamos_abiertos=reclamos_abiertos,
        )
