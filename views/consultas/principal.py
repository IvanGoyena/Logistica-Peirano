# views/consultas/principal.py

from __future__ import annotations

import logging
from urllib.parse import quote

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

from utils.consultas.gestion_consultas import (
    guardar_solicitud,
    editar_solicitud,
    eliminar_solicitud,
)
from utils.consultas.leer_gestion_consultas import (
    obtener_solicitudes_abiertas,
)

from utils.consultas.gestion_devoluciones import (
    guardar_cancelacion_entrega,
    confirmar_envio_whatsapp,
)
from utils.consultas.leer_devoluciones import (
    estado_para_comercial,
)

from views.consultas.reclamos import (
    mostrar_boton_carga_reclamo,
)

from utils.consultas.carga import (
    cargar_datos_consultas,
    limpiar_cache_datos_consultas,
)
from utils.consultas.cache_gestion import (
    cargar_gestion_comercial_cache,
    cargar_cancelaciones_cache,
    invalidar_cache_gestion,
)
from models.consultas_comerciales.base_operativa import (
    construir_tabla_operativa,
    construir_tabla_consultas_cache,
    limpiar_cache_modelo_consultas,
)






def render() -> None:
    # ==========================================================
    # DIÁLOGO DE DETALLE DE SOLICITUD
    # ==========================================================

    @st.dialog(
        "📩 Detalle de solicitud",
        width="large",
    )
    def abrir_detalle_solicitud(
        solicitud: pd.Series,
    ) -> None:
        """
        Muestra el detalle completo de la solicitud y concentra
        las acciones de edición y eliminación dentro del modal.
        """

        solicitud_id = str(
            solicitud.get("SolicitudID", "")
        ).strip()

        pedido = str(
            solicitud.get("Pedido", "")
        ).strip()

        cliente = str(
            solicitud.get("Cliente", "")
        ).strip()

        tipo_actual = str(
            solicitud.get("TipoSolicitud", "")
        ).strip()

        prioridad_actual = str(
            solicitud.get("Prioridad", "Normal")
        ).strip()

        descripcion_actual = str(
            solicitud.get("Descripcion", "")
        ).strip()

        estado_actual = str(
            solicitud.get("EstadoSolicitud", "")
        ).strip()

        responsable = str(
            solicitud.get("Responsable", "")
        ).strip()

        respuesta = str(
            solicitud.get("Respuesta", "")
        ).strip()

        fecha_solicitud = pd.to_datetime(
            solicitud.get("FechaSolicitud", ""),
            errors="coerce",
        )

        fecha_texto = (
            fecha_solicitud.strftime("%d/%m/%Y %H:%M")
            if pd.notna(fecha_solicitud)
            else str(
                solicitud.get("FechaSolicitud", "")
            ).strip()
        )

        finalizada = estado_actual.upper() in {
            "FINALIZADA",
            "FINALIZADO",
        }

        cabecera_1, cabecera_2, cabecera_3 = st.columns(
            [1, 2.3, 1],
            vertical_alignment="center",
        )

        with cabecera_1:
            st.metric(
                "Pedido",
                pedido or "Sin dato",
            )

        with cabecera_2:
            st.markdown(
                f"**{cliente or 'Cliente sin identificar'}**"
            )
            st.caption(
                f"{tipo_actual or 'Solicitud'} · "
                f"{prioridad_actual or 'Sin prioridad'}"
            )

        with cabecera_3:
            st.metric(
                "Estado",
                estado_actual or "Sin estado",
            )

        st.info(
            descripcion_actual or "Sin detalle.",
            icon="📝",
        )

        detalle_1, detalle_2, detalle_3 = st.columns(3)

        with detalle_1:
            st.caption(
                f"**Solicitado por**  \n"
                f"{solicitud.get('UsuarioSolicitante', '') or 'Sin dato'}"
            )

        with detalle_2:
            st.caption(
                f"**Fecha**  \n"
                f"{fecha_texto or 'Sin dato'}"
            )

        with detalle_3:
            st.caption(
                f"**Responsable Logística**  \n"
                f"{responsable or 'Sin asignar'}"
            )

        if respuesta:
            st.success(
                respuesta,
                icon="💬",
            )

        st.divider()

        modo_accion = st.radio(
            "Acción",
            options=[
                "Ver detalle",
                "Editar",
                "Eliminar",
            ],
            horizontal=True,
            disabled=finalizada,
            key=f"accion_solicitud_{solicitud_id}",
        )

        if finalizada:
            st.caption(
                "La solicitud está finalizada y se conserva "
                "solo como historial."
            )
            return

        if modo_accion == "Editar":

            tipos_solicitud = [
                "Consulta de estado",
                "Cambio de prioridad",
                "Coordinación de entrega",
                "Postergar Entrega",
                "Urgencia",
                "Documentación",
                "Otro",
            ]

            prioridades = [
                "Normal",
                "Alta",
                "Baja",
            ]

            if tipo_actual not in tipos_solicitud:
                tipos_solicitud.append(tipo_actual)

            if prioridad_actual not in prioridades:
                prioridades.append(prioridad_actual)

            with st.form(
                f"form_editar_solicitud_{solicitud_id}",
                clear_on_submit=False,
            ):

                tipo_editado = st.selectbox(
                    "Tipo de solicitud",
                    options=tipos_solicitud,
                    index=tipos_solicitud.index(
                        tipo_actual
                    ),
                )

                prioridad_editada = st.selectbox(
                    "Prioridad",
                    options=prioridades,
                    index=prioridades.index(
                        prioridad_actual
                    ),
                )

                descripcion_editada = st.text_area(
                    "Descripción",
                    value=descripcion_actual,
                    height=120,
                )

                guardar_cambios = st.form_submit_button(
                    "💾 Guardar cambios",
                    type="primary",
                    width="stretch",
                )

            if guardar_cambios:

                try:
                    resultado = editar_solicitud(
                        solicitud_id=solicitud_id,
                        tipo_solicitud=tipo_editado,
                        prioridad=prioridad_editada,
                        descripcion=descripcion_editada,
                    )

                    st.success(resultado["mensaje"])
                    st.toast(
                        "Solicitud actualizada.",
                        icon="✅",
                    )
                    invalidar_cache_gestion()
                    st.rerun()

                except Exception as error:
                    st.error(
                        "No se pudo modificar la solicitud."
                    )
                    logger.exception("Error controlado en el módulo de Consultas Comerciales.")

        elif modo_accion == "Eliminar":

            st.warning(
                "La solicitud se cancelará y seguirá disponible en su histórico."
            )

            confirmar = st.checkbox(
                "Confirmo que quiero cancelar esta solicitud.",
                key=f"confirmar_eliminar_{solicitud_id}",
            )

            eliminar = st.button(
                "🚫 Cancelar solicitud",
                type="primary",
                width="stretch",
                disabled=not confirmar,
                key=f"btn_eliminar_{solicitud_id}",
            )

            if eliminar:

                try:
                    usuario_cancelacion = (
                        st.session_state.get("usuario")
                        or st.session_state.get("nombre_usuario")
                        or "Usuario no identificado"
                    )

                    resultado = eliminar_solicitud(
                        solicitud_id=solicitud_id,
                        usuario_cancelacion=usuario_cancelacion,
                    )

                    st.success(resultado["mensaje"])
                    st.toast(
                        "Solicitud cancelada.",
                        icon="🚫",
                    )
                    invalidar_cache_gestion()
                    st.rerun()

                except Exception as error:
                    st.error(
                        "No se pudo cancelar la solicitud."
                    )
                    logger.exception("Error controlado en el módulo de Consultas Comerciales.")



    # ==========================================================
    # DIÁLOGO DE DETALLE DE RECLAMO
    # ==========================================================

    @st.dialog(
        "🧾 Detalle del reclamo",
        width="large",
    )
    def abrir_detalle_reclamo_consultas(
        reclamo: pd.Series,
    ) -> None:
        """
        Muestra el reclamo completo y la respuesta registrada por Logística.
        Esta vista es informativa: la gestión se realiza desde 02_Pedidos.
        """

        reclamo_id = str(
            reclamo.get("ReclamoID", "")
        ).strip()

        pedido = str(
            reclamo.get("Pedido", "")
        ).strip()

        remito = str(
            reclamo.get("Remito", "")
        ).strip()

        cliente = str(
            reclamo.get("Cliente", "")
        ).strip()

        tipo_reclamo = str(
            reclamo.get("TipoReclamo", "")
        ).strip()

        descripcion = str(
            reclamo.get("Descripcion", "")
        ).strip()

        responsable = str(
            reclamo.get("Responsable", "")
        ).strip()

        estado = str(
            reclamo.get("EstadoReclamo", "")
        ).strip()

        resolucion = str(
            reclamo.get("Resolucion", "")
        ).strip()

        usuario_creador = str(
            reclamo.get("UsuarioCreador", "")
        ).strip()

        fecha_creacion = pd.to_datetime(
            reclamo.get("FechaCreacion", ""),
            errors="coerce",
        )

        fecha_cierre = pd.to_datetime(
            reclamo.get("FechaCierre", ""),
            errors="coerce",
        )

        fecha_creacion_texto = (
            fecha_creacion.strftime("%d/%m/%Y %H:%M")
            if pd.notna(fecha_creacion)
            else str(
                reclamo.get("FechaCreacion", "")
            ).strip()
        )

        fecha_cierre_texto = (
            fecha_cierre.strftime("%d/%m/%Y %H:%M")
            if pd.notna(fecha_cierre)
            else str(
                reclamo.get("FechaCierre", "")
            ).strip()
        )

        cabecera_1, cabecera_2, cabecera_3 = st.columns(
            [1, 2.4, 1],
            vertical_alignment="center",
        )

        with cabecera_1:
            st.metric(
                "Pedido",
                pedido or "Sin dato",
            )

        with cabecera_2:
            st.markdown(
                f"**{cliente or 'Cliente sin identificar'}**"
            )
            st.caption(
                f"{tipo_reclamo or 'Reclamo'} · "
                f"Remito {remito or 'sin dato'}"
            )

        with cabecera_3:
            st.metric(
                "Estado",
                estado or "Sin estado",
            )

        st.info(
            descripcion or "Sin descripción.",
            icon="📝",
        )

        detalle_1, detalle_2, detalle_3 = st.columns(3)

        with detalle_1:
            st.caption(
                f"**Registrado por**  \n"
                f"{usuario_creador or 'Sin dato'}"
            )

        with detalle_2:
            st.caption(
                f"**Fecha de registro**  \n"
                f"{fecha_creacion_texto or 'Sin dato'}"
            )

        with detalle_3:
            st.caption(
                f"**Responsable**  \n"
                f"{responsable or 'Sin asignar'}"
            )

        st.divider()
        st.markdown("#### 💬 Respuesta de Logística")

        if resolucion:
            st.success(
                resolucion,
                icon="✅",
            )
        else:
            st.warning(
                "Logística todavía no registró una resolución.",
                icon="⏳",
            )

        if fecha_cierre_texto:
            st.caption(
                f"Fecha de cierre: **{fecha_cierre_texto}**"
            )

        st.caption(
            f"ID del reclamo: {reclamo_id or 'Sin dato'}"
        )



    # La carga, el modelo operativo y las cachés de gestión se
    # encuentran desacoplados en utils/consultas y models/consultas_comerciales.

    # ==========================================================
    # ESTADO INICIAL
    # ==========================================================

    if "consultas_filtros_aplicados" not in st.session_state:
        st.session_state["consultas_filtros_aplicados"] = {
            "busqueda": "",
            "estado_pedido": [],
            "estado_preparacion": [],
            "estado_operativo": [],
        }

    if "consultas_detalle_abierto" not in st.session_state:
        st.session_state["consultas_detalle_abierto"] = False

    if "consultas_pedido_detalle" not in st.session_state:
        st.session_state["consultas_pedido_detalle"] = ""

    if "consultas_pedidos_gestion_multiple" not in st.session_state:
        st.session_state["consultas_pedidos_gestion_multiple"] = []

    if "consultas_abrir_gestion_multiple" not in st.session_state:
        st.session_state["consultas_abrir_gestion_multiple"] = False

    if "mostrar_historico_reclamos" not in st.session_state:
        st.session_state["mostrar_historico_reclamos"] = False

    if "mostrar_historico_solicitudes" not in st.session_state:
        st.session_state["mostrar_historico_solicitudes"] = False

    if "mostrar_historico_cancelaciones_entrega" not in st.session_state:
        st.session_state["mostrar_historico_cancelaciones_entrega"] = False

    if "ultima_cancelacion_whatsapp" not in st.session_state:
        st.session_state["ultima_cancelacion_whatsapp"] = None


    # ==========================================================
    # HISTÓRICOS ESPECÍFICOS DE LA INTERFAZ
    # ==========================================================

    def mostrar_historial_solicitudes(
        solicitudes: pd.DataFrame,
    ) -> None:
        st.markdown("#### 📚 Histórico de solicitudes")
        st.caption(
            "Solicitudes pendientes, en curso, finalizadas y canceladas "
            "conservadas en PostgreSQL."
        )

        if solicitudes is None or solicitudes.empty:
            st.info("Todavía no hay solicitudes registradas.", icon="📩")
            return

        tabla = solicitudes.copy()
        for columna in [
            "SolicitudID", "Pedido", "Cliente", "TipoSolicitud",
            "Prioridad", "Descripcion", "UsuarioSolicitante",
            "FechaSolicitud", "EstadoSolicitud", "Responsable",
            "Respuesta", "FechaResolucion",
        ]:
            if columna not in tabla.columns:
                tabla[columna] = ""

        tabla["FechaOrden"] = pd.to_datetime(
            tabla["FechaSolicitud"], errors="coerce"
        )
        tabla["Fecha"] = tabla["FechaOrden"].dt.strftime(
            "%d/%m/%Y %H:%M"
        ).fillna(tabla["FechaSolicitud"].astype(str))
        tabla = tabla.sort_values(
            "FechaOrden", ascending=False, na_position="last"
        )

        busqueda = st.text_input(
            "Buscar en solicitudes",
            placeholder="Pedido, cliente, tipo o ID...",
            key="buscar_historico_solicitudes",
        )
        if busqueda.strip():
            mascara = pd.Series(False, index=tabla.index)
            for columna in [
                "SolicitudID", "Pedido", "Cliente",
                "TipoSolicitud", "Descripcion",
            ]:
                mascara |= tabla[columna].astype(str).str.contains(
                    busqueda.strip(), case=False, na=False, regex=False
                )
            tabla = tabla.loc[mascara]

        vista = tabla[[
            "SolicitudID", "Pedido", "Cliente", "TipoSolicitud",
            "Prioridad", "EstadoSolicitud", "Responsable", "Fecha",
            "Respuesta",
        ]].rename(columns={
            "SolicitudID": "ID",
            "TipoSolicitud": "Tipo",
            "EstadoSolicitud": "Estado",
            "Respuesta": "Respuesta Logística",
        })

        st.dataframe(
            vista, width="stretch", hide_index=True,
            height=min(420, 85 + len(vista) * 35),
            key="tabla_historico_solicitudes",
        )


    def construir_opciones_clientes_cancelacion(
        df_clientes: pd.DataFrame,
    ) -> list[str]:
        """Construye opciones legibles desde el Maestro de Clientes."""

        if df_clientes is None or df_clientes.empty:
            return ["Seleccionar cliente..."]

        tabla = df_clientes.copy()
        columnas = list(tabla.columns)

        candidatas_codigo = [
            "CodigoCliente", "CódigoCliente", "ClienteCodigo",
            "CodigoSucursal", "Código", "Codigo",
        ]
        candidatas_nombre = [
            "ClienteDescripcion", "RazonSocial", "Razón Social",
            "NombreCliente", "Cliente", "Descripcion", "Descripción",
        ]

        columna_codigo = next(
            (col for col in candidatas_codigo if col in columnas),
            None,
        )
        columna_nombre = next(
            (col for col in candidatas_nombre if col in columnas),
            None,
        )

        if columna_nombre is None:
            columnas_texto = [
                col for col in columnas
                if tabla[col].dtype == "object"
            ]
            columna_nombre = columnas_texto[0] if columnas_texto else columnas[0]

        opciones: list[str] = []
        for _, fila in tabla.iterrows():
            nombre = str(fila.get(columna_nombre, "") or "").strip()
            codigo = (
                str(fila.get(columna_codigo, "") or "").strip()
                if columna_codigo
                else ""
            )
            if codigo.endswith(".0"):
                codigo = codigo[:-2]
            if not nombre:
                continue
            etiqueta = f"{codigo} - {nombre}" if codigo else nombre
            if etiqueta not in opciones:
                opciones.append(etiqueta)

        opciones = sorted(opciones, key=str.upper)
        return ["Seleccionar cliente..."] + opciones


    DESTINATARIOS_WHATSAPP = {
        "Leo": "5491124714063",
        "Juanma": "5491133914080",
    }


    def construir_mensaje_whatsapp_cancelacion(registro: dict) -> str:
        """Construye el mensaje crítico para WhatsApp."""

        remitos = str(registro.get("Remito", "") or "").split(" | ")
        remitos = [remito.strip() for remito in remitos if remito.strip()]
        detalle_remitos = "\n".join(f"• {remito}" for remito in remitos)
        etiqueta_remitos = "Remitos" if len(remitos) > 1 else "Remito"

        return (
            "🚨 *CANCELACIÓN DE ENTREGA* 🚨\n\n"
            f"*{etiqueta_remitos}:*\n{detalle_remitos}\n"
            f"*Cliente:* {registro.get('Cliente', '') or 'Sin informar'}\n"
            f"*Motivo:* {registro.get('Motivo', '')}\n"
            f"*Observación:* {registro.get('Observacion', '') or 'Sin observaciones'}\n"
            f"*Solicitado por:* {registro.get('UsuarioSolicitante', '')}\n"
            f"*Fecha:* {registro.get('FechaSolicitud', '')}\n\n"
            "⛔ *NO CARGAR NI DESPACHAR ESTA MERCADERÍA.*\n"
            "Separar el remito y confirmar que la entrega fue detenida.\n\n"
            f"ID de gestión: {registro.get('CancelacionEntregaID', '')}"
        )


    def construir_url_whatsapp_cancelacion(registro: dict, telefono: str) -> str:
        mensaje = construir_mensaje_whatsapp_cancelacion(registro)
        return f"https://wa.me/{telefono}?text={quote(mensaje)}"


    def mostrar_historial_cancelaciones_entrega(cancelaciones: pd.DataFrame) -> None:
        st.markdown("#### 📚 Histórico de cancelaciones de entrega")

        if cancelaciones is None or cancelaciones.empty:
            st.info("Todavía no hay cancelaciones de entrega registradas.")
            return

        tabla = cancelaciones.copy()
        tabla["Fecha"] = pd.to_datetime(
            tabla["FechaSolicitud"], errors="coerce"
        ).dt.strftime("%d/%m/%Y %H:%M").fillna(
            tabla["FechaSolicitud"].fillna("").astype(str)
        )

        busqueda = st.text_input(
            "Buscar en cancelaciones",
            placeholder="Remito, cliente, motivo o ID...",
            key="buscar_historico_cancelaciones_entrega",
        )

        if busqueda.strip():
            mascara = pd.Series(False, index=tabla.index)
            for columna in [
                "CancelacionEntregaID", "Remito", "Cliente", "Motivo",
            ]:
                mascara |= tabla[columna].fillna("").astype(str).str.contains(
                    busqueda.strip(), case=False, na=False, regex=False
                )
            tabla = tabla.loc[mascara]

        vista = tabla[[
            "CancelacionEntregaID", "Remito", "Cliente", "Motivo",
            "EstadoCancelacion", "EstadoWhatsApp", "NumeroIR",
            "EstadoReingreso", "Fecha",
        ]].rename(columns={
            "CancelacionEntregaID": "ID",
            "EstadoCancelacion": "Estado",
            "EstadoWhatsApp": "WhatsApp",
            "NumeroIR": "IR",
            "EstadoReingreso": "Reingreso",
        })

        st.dataframe(
            vista,
             width="stretch",
            hide_index=True,
            height=min(420, 85 + len(vista) * 35),
            key="tabla_historico_cancelaciones_entrega",
        )


    # ==========================================================
    # CABECERA
    # ==========================================================

    st.title("🔎 Consultas Comerciales")
    st.caption(
        "Consulta informativa de pedidos para el área Comercial."
    )

    (
        col_info,
        col_reclamo,
        col_historico,
        col_actualizar,
    ) = st.columns(
        [4.2, 1.35, 1.2, 1],
        vertical_alignment="center",
    )

    with col_info:
        st.caption(
            "Buscá por número de pedido, código o nombre del cliente."
        )

    with col_reclamo:
        espacio_boton_reclamo = st.empty()

    with col_historico:
        texto_historico = (
            "Ocultar histórico"
            if st.session_state["mostrar_historico_reclamos"]
            else "Histórico"
        )

        if st.button(
            texto_historico,
            icon="📚",
            width="stretch",
            key="btn_historico_reclamos_consultas",
        ):
            st.session_state["mostrar_historico_reclamos"] = (
                not st.session_state["mostrar_historico_reclamos"]
            )
            st.rerun()

    with col_actualizar:
        actualizar = st.button(
            "🔄 Actualizar",
            width="stretch",
        )

    if actualizar:
        limpiar_cache_datos_consultas()
        limpiar_cache_modelo_consultas()
        invalidar_cache_gestion()
        st.rerun()


    # ==========================================================
    # CONSTRUIR DATOS
    # ==========================================================

    try:
        datos = cargar_datos_consultas()

        tabla_operativa = construir_tabla_operativa(
            datos
        )

        tabla_consultas = construir_tabla_consultas_cache(
            tabla_operativa,
            datos["tareas"],
        )

        # Comercial trabaja sólo con pedidos todavía sin Hoja de Ruta.
        # El histórico conserva las gestiones cerradas por separado.

        gestion_cache = cargar_gestion_comercial_cache()

        # ------------------------------------------------------
        # SOLICITUDES ABIERTAS
        # ------------------------------------------------------

        solicitudes_abiertas = gestion_cache["solicitudes_abiertas"]

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

            solicitudes_abiertas = (
                solicitudes_abiertas
                .sort_values(
                    "FechaSolicitudOrden",
                    ascending=False,
                    na_position="last",
                )
                .reset_index(drop=True)
            )

            pedidos_con_solicitud = set(
                solicitudes_abiertas["Pedido"].tolist()
            )

            tipos_por_pedido = (
                solicitudes_abiertas
                .drop_duplicates(subset=["Pedido"], keep="first")
                .set_index("Pedido")["TipoSolicitud"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .to_dict()
            )
        else:
            pedidos_con_solicitud = set()
            tipos_por_pedido = {}

        def _estado_solicitud_tabla(pedido: object) -> str:
            pedido_txt = str(pedido).strip()
            if pedido_txt not in pedidos_con_solicitud:
                return ""
            if tipos_por_pedido.get(pedido_txt, "") == "URGENCIA":
                return "🚨 Urgente"
            return "📩 Pendiente"

        tabla_consultas["Solicitud"] = (
            tabla_consultas["Pedido"]
            .apply(_estado_solicitud_tabla)
        )

    except Exception as error:
        st.error("No se pudo construir la tabla de consultas.")
        logger.exception("Error controlado en el módulo de Consultas Comerciales.")
        st.stop()


    # ==========================================================
    # CONSULTA RÁPIDA - PRIMERA ACCIÓN DEL USUARIO
    # ==========================================================

    st.markdown("### ⚡ Consulta rápida")
    consulta_rapida = st.text_input(
        "Pedido o cliente",
        placeholder="Escribí número de pedido, código o nombre del cliente...",
        key="consulta_rapida_comercial",
        label_visibility="collapsed",
    ).strip()

    if consulta_rapida:
        mascara_rapida = pd.Series(False, index=tabla_consultas.index)
        for columna in ("Pedido", "ClienteCodigo", "CodigoLogistico", "Cliente"):
            if columna in tabla_consultas.columns:
                mascara_rapida |= (
                    tabla_consultas[columna]
                    .fillna("")
                    .astype(str)
                    .str.contains(consulta_rapida, case=False, na=False, regex=False)
                )

        resultado_rapido = tabla_consultas.loc[mascara_rapida].copy()
        columnas_rapidas = [
            "Pedido", "ClienteCodigo", "Cliente", "Unidades", "M3", "EstadoVolumetria",
            "Planificacion", "Despacho",
            "EstadoPedido", "EstadoPreparacion", "EstadoOperativo",
            "Contenedor", "Solicitud",
        ]
        columnas_rapidas = [
            columna for columna in columnas_rapidas
            if columna in resultado_rapido.columns
        ]

        if resultado_rapido.empty:
            st.info("No hay pedidos operativos que coincidan con la búsqueda.")
        else:
            st.dataframe(
                resultado_rapido[columnas_rapidas].head(25),
                width="stretch",
                hide_index=True,
                height=min(360, 85 + min(len(resultado_rapido), 25) * 35),
                key="tabla_consulta_rapida_comercial",
            )
            if len(resultado_rapido) > 25:
                st.caption(
                    f"Se muestran 25 de {len(resultado_rapido)} coincidencias. "
                    "Usá los filtros de la tabla general para acotar el resultado."
                )
    else:
        st.caption(
            f"{len(tabla_consultas):,} pedidos en el universo operativo actual."
            .replace(",", ".")
        )


    # ==========================================================
    # CARGA INDEPENDIENTE DE RECLAMOS
    # ==========================================================

    with espacio_boton_reclamo.container():
        mostrar_boton_carga_reclamo()


    # ==========================================================
    # KPIs GENERALES DE GESTIÓN
    # ==========================================================

    solicitudes_totales = gestion_cache["solicitudes_totales"]
    reclamos_totales = gestion_cache["reclamos_totales"]

    if solicitudes_totales is None:
        solicitudes_totales = pd.DataFrame()

    if reclamos_totales is None:
        reclamos_totales = pd.DataFrame()


    def contar_cerradas(
        dataframe: pd.DataFrame,
        columna_estado: str,
    ) -> int:
        if (
            dataframe.empty
            or columna_estado not in dataframe.columns
        ):
            return 0

        estados_cerrados = {
            "FINALIZADA",
            "FINALIZADO",
            "RESUELTA",
            "RESUELTO",
            "CERRADA",
            "CERRADO",
            "RECHAZADA",
            "RECHAZADO",
            "CANCELADA",
            "CANCELADO",
        }

        return int(
            dataframe[columna_estado]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(estados_cerrados)
            .sum()
        )


    cantidad_solicitudes = len(
        solicitudes_totales
    )
    cantidad_reclamos = len(
        reclamos_totales
    )

    total_gestiones = (
        cantidad_solicitudes
        + cantidad_reclamos
    )

    gestiones_cerradas = (
        contar_cerradas(
            solicitudes_totales,
            "EstadoSolicitud",
        )
        + contar_cerradas(
            reclamos_totales,
            "EstadoReclamo",
        )
    )

    gestiones_abiertas = max(
        total_gestiones - gestiones_cerradas,
        0,
    )

    st.markdown("### 📊 Resumen de gestión")

    (
        kpi_gestion_1,
        kpi_gestion_2,
        kpi_gestion_3,
        kpi_gestion_4,
        kpi_gestion_5,
    ) = st.columns(5)

    kpi_gestion_1.metric(
        "📋 Total gestiones",
        f"{total_gestiones:,}".replace(",", "."),
    )

    kpi_gestion_2.metric(
        "🟠 Abiertas",
        f"{gestiones_abiertas:,}".replace(",", "."),
    )

    kpi_gestion_3.metric(
        "✅ Cerradas",
        f"{gestiones_cerradas:,}".replace(",", "."),
    )

    kpi_gestion_4.metric(
        "📩 Solicitudes",
        f"{cantidad_solicitudes:,}".replace(",", "."),
    )

    kpi_gestion_5.metric(
        "🧾 Reclamos",
        f"{cantidad_reclamos:,}".replace(",", "."),
    )


    # ==========================================================
    # SOLICITUDES PENDIENTES - VISTA PRINCIPAL DE GESTIÓN
    # ==========================================================

    st.markdown("---")
    sol_titulo, sol_historial = st.columns(
        [5, 1.25], vertical_alignment="center"
    )

    with sol_titulo:
        st.markdown("### 📩 Solicitudes pendientes")

    with sol_historial:
        if st.button(
            "Ocultar histórico"
            if st.session_state["mostrar_historico_solicitudes"]
            else "📚 Histórico",
            width="stretch",
            key="btn_historico_solicitudes",
        ):
            st.session_state["mostrar_historico_solicitudes"] = (
                not st.session_state["mostrar_historico_solicitudes"]
            )
            st.rerun()

    if st.session_state["mostrar_historico_solicitudes"]:
        mostrar_historial_solicitudes(solicitudes_totales)
        st.divider()

    if solicitudes_abiertas.empty:
        st.info("No hay solicitudes pendientes de gestión.")
    else:
        solicitudes_resumen = solicitudes_abiertas.copy()

        solicitudes_resumen["FechaSolicitudVisible"] = (
            pd.to_datetime(
                solicitudes_resumen["FechaSolicitud"],
                errors="coerce",
            )
            .dt.strftime("%d/%m/%Y %H:%M")
            .fillna(
                solicitudes_resumen["FechaSolicitud"]
                .fillna("")
                .astype(str)
            )
        )

        columnas_solicitudes = [
            "SolicitudID",
            "Pedido",
            "Cliente",
            "TipoSolicitud",
            "Prioridad",
            "Descripcion",
            "UsuarioSolicitante",
            "FechaSolicitudVisible",
            "EstadoSolicitud",
            "Responsable",
            "Respuesta",
        ]

        for columna in columnas_solicitudes:
            if columna not in solicitudes_resumen.columns:
                solicitudes_resumen[columna] = ""

        tabla_solicitudes_superior = (
            solicitudes_resumen[columnas_solicitudes]
            .rename(
                columns={
                    "SolicitudID": "ID",
                    "TipoSolicitud": "Tipo",
                    "Descripcion": "Detalle",
                    "UsuarioSolicitante": "Solicitado por",
                    "FechaSolicitudVisible": "Fecha",
                    "EstadoSolicitud": "Estado",
                    "Respuesta": "Respuesta Logística",
                }
            )
            .reset_index(drop=True)
        )

        st.caption(
            f"{len(tabla_solicitudes_superior):,} solicitudes abiertas"
            .replace(",", ".")
        )

        evento_solicitudes_superior = st.dataframe(
            tabla_solicitudes_superior,
            width="stretch",
            hide_index=True,
            height=min(420, 85 + len(tabla_solicitudes_superior) * 35),
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_solicitudes_pendientes_consultas",
            column_config={
                "ID": None,
                "Pedido": st.column_config.TextColumn("Pedido", width="small"),
                "Cliente": st.column_config.TextColumn("Cliente", width="medium"),
                "Tipo": st.column_config.TextColumn("Tipo", width="medium"),
                "Prioridad": st.column_config.TextColumn("Prioridad", width="small"),
                "Detalle": st.column_config.TextColumn("Detalle", width="large"),
                "Solicitado por": st.column_config.TextColumn("Solicitado por", width="small"),
                "Fecha": st.column_config.TextColumn("Fecha", width="small"),
                "Estado": st.column_config.TextColumn("Estado", width="small"),
                "Responsable": st.column_config.TextColumn("Responsable", width="small"),
                "Respuesta Logística": st.column_config.TextColumn(
                    "Respuesta Logística", width="large"
                ),
            },
        )

        filas_solicitudes_superior = (
            evento_solicitudes_superior.selection.rows
            if evento_solicitudes_superior is not None
            else []
        )

        accion_solicitud_1, accion_solicitud_2 = st.columns(
            [4, 1], vertical_alignment="center"
        )

        indice_solicitud_superior = (
            filas_solicitudes_superior[0]
            if filas_solicitudes_superior
            else None
        )

        seleccion_solicitud_valida = (
            indice_solicitud_superior is not None
            and 0 <= int(indice_solicitud_superior) < len(tabla_solicitudes_superior)
            and 0 <= int(indice_solicitud_superior) < len(solicitudes_resumen)
        )

        with accion_solicitud_1:
            if seleccion_solicitud_valida:
                seleccion_superior = tabla_solicitudes_superior.iloc[
                    int(indice_solicitud_superior)
                ]
                st.caption(
                    f"Seleccionada: pedido **{seleccion_superior['Pedido']}** · "
                    f"{seleccion_superior['Tipo']} · {seleccion_superior['Estado']}"
                )
            else:
                st.caption(
                    "Seleccioná una solicitud para ver, editar o cancelar su gestión."
                )

        with accion_solicitud_2:
            gestionar_solicitud_superior = st.button(
                "📩 Gestionar",
                type="primary",
                width="stretch",
                disabled=not seleccion_solicitud_valida,
                key="btn_gestionar_solicitud_consultas",
            )

        if gestionar_solicitud_superior and seleccion_solicitud_valida:
            solicitud_superior = solicitudes_resumen.iloc[
                int(indice_solicitud_superior)
            ]
            abrir_detalle_solicitud(solicitud_superior)


    if st.session_state["mostrar_historico_reclamos"]:
        # ==========================================================
        # HISTORIAL Y SEGUIMIENTO DE RECLAMOS
        # ==========================================================

        st.markdown("### 📚 Histórico de reclamos")
        st.caption(
            "Incluye todos los reclamos abiertos, resueltos y rechazados "
            "registrados en PostgreSQL."
        )

        if reclamos_totales.empty:
            st.info(
                "Todavía no hay reclamos registrados.",
                icon="🧾",
            )
        else:
            reclamos_vista = reclamos_totales.copy()

            columnas_reclamos_requeridas = [
                "ReclamoID",
                "Pedido",
                "Remito",
                "Cliente",
                "TipoReclamo",
                "Descripcion",
                "Responsable",
                "EstadoReclamo",
                "Resolucion",
                "UsuarioCreador",
                "FechaCreacion",
                "FechaCierre",
            ]

            for columna in columnas_reclamos_requeridas:
                if columna not in reclamos_vista.columns:
                    reclamos_vista[columna] = ""

            reclamos_vista["Pedido"] = (
                reclamos_vista["Pedido"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )

            reclamos_vista["FechaCreacionOrden"] = pd.to_datetime(
                reclamos_vista["FechaCreacion"],
                errors="coerce",
            )

            reclamos_vista["FechaVisible"] = (
                reclamos_vista["FechaCreacionOrden"]
                .dt.strftime("%d/%m/%Y %H:%M")
                .fillna(
                    reclamos_vista["FechaCreacion"]
                    .fillna("")
                    .astype(str)
                )
            )

            reclamos_vista["ResolucionVisible"] = (
                reclamos_vista["Resolucion"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", "Pendiente de respuesta")
            )

            reclamos_vista = (
                reclamos_vista
                .sort_values(
                    "FechaCreacionOrden",
                    ascending=False,
                    na_position="last",
                )
                .reset_index(drop=True)
            )

            estados_disponibles = sorted(
                estado
                for estado in reclamos_vista["EstadoReclamo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
                if estado
            )

            filtro_reclamo_1, filtro_reclamo_2 = st.columns(
                [2, 1],
                vertical_alignment="bottom",
            )

            with filtro_reclamo_1:
                busqueda_reclamo = st.text_input(
                    "Buscar reclamo",
                    placeholder=(
                        "Pedido, remito, cliente, incidencia o ID..."
                    ),
                    key="buscar_reclamos_consultas",
                )

            with filtro_reclamo_2:
                estado_reclamo_filtro = st.selectbox(
                    "Estado",
                    options=["Todos"] + estados_disponibles,
                    key="estado_reclamos_consultas",
                )

            reclamos_filtrados = reclamos_vista.copy()

            if busqueda_reclamo.strip():
                texto_reclamo = busqueda_reclamo.strip()

                mascara_reclamos = pd.Series(
                    False,
                    index=reclamos_filtrados.index,
                )

                for columna in [
                    "ReclamoID",
                    "Pedido",
                    "Remito",
                    "Cliente",
                    "TipoReclamo",
                ]:
                    mascara_reclamos = (
                        mascara_reclamos
                        | reclamos_filtrados[columna]
                        .fillna("")
                        .astype(str)
                        .str.contains(
                            texto_reclamo,
                            case=False,
                            na=False,
                            regex=False,
                        )
                    )

                reclamos_filtrados = reclamos_filtrados.loc[
                    mascara_reclamos
                ].copy()

            if estado_reclamo_filtro != "Todos":
                reclamos_filtrados = reclamos_filtrados[
                    reclamos_filtrados["EstadoReclamo"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .eq(estado_reclamo_filtro)
                ].copy()

            tabla_reclamos_consultas = (
                reclamos_filtrados[
                    [
                        "ReclamoID",
                        "Pedido",
                        "Remito",
                        "Cliente",
                        "TipoReclamo",
                        "EstadoReclamo",
                        "Responsable",
                        "FechaVisible",
                        "ResolucionVisible",
                    ]
                ]
                .rename(
                    columns={
                        "ReclamoID": "ID",
                        "TipoReclamo": "Incidencia",
                        "EstadoReclamo": "Estado",
                        "FechaVisible": "Fecha",
                        "ResolucionVisible": "Respuesta Logística",
                    }
                )
                .reset_index(drop=True)
            )

            st.caption(
                f"{len(tabla_reclamos_consultas):,} reclamo(s) visible(s)"
                .replace(",", ".")
            )

            evento_reclamos_consultas = st.dataframe(
                tabla_reclamos_consultas,
                width="stretch",
                hide_index=True,
                height=min(
                    430,
                    85 + len(tabla_reclamos_consultas) * 35,
                ),
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_historial_reclamos_consultas",
                column_config={
                    "ID": None,
                    "Pedido": st.column_config.TextColumn(
                        "Pedido",
                        width="small",
                    ),
                    "Remito": st.column_config.TextColumn(
                        "Remito",
                        width="small",
                    ),
                    "Cliente": st.column_config.TextColumn(
                        "Cliente",
                        width="large",
                    ),
                    "Incidencia": st.column_config.TextColumn(
                        "Incidencia",
                        width="medium",
                    ),
                    "Estado": st.column_config.TextColumn(
                        "Estado",
                        width="small",
                    ),
                    "Responsable": st.column_config.TextColumn(
                        "Responsable",
                        width="small",
                    ),
                    "Fecha": st.column_config.TextColumn(
                        "Fecha",
                        width="small",
                    ),
                    "Respuesta Logística": st.column_config.TextColumn(
                        "Respuesta Logística",
                        width="large",
                    ),
                },
            )

            filas_reclamos_consultas = (
                evento_reclamos_consultas.selection.rows
                if evento_reclamos_consultas is not None
                else []
            )

            reclamo_accion_1, reclamo_accion_2 = st.columns(
                [4, 1],
                vertical_alignment="center",
            )

            with reclamo_accion_1:
                indice_reclamo_tabla = (
                    filas_reclamos_consultas[0]
                    if filas_reclamos_consultas
                    else None
                )

                seleccion_reclamo_valida = (
                    indice_reclamo_tabla is not None
                    and 0 <= int(indice_reclamo_tabla) < len(tabla_reclamos_consultas)
                )

                if seleccion_reclamo_valida:
                    fila_reclamo_seleccionada = (
                        tabla_reclamos_consultas.iloc[
                            int(indice_reclamo_tabla)
                        ]
                    )

                    st.caption(
                        f"Seleccionado: pedido "
                        f"**{fila_reclamo_seleccionada['Pedido']}** · "
                        f"{fila_reclamo_seleccionada['Incidencia']} · "
                        f"{fila_reclamo_seleccionada['Estado']}"
                    )
                else:
                    st.caption(
                        "Seleccioná un reclamo para ver el detalle "
                        "y la respuesta completa."
                    )

            with reclamo_accion_2:
                ver_detalle_reclamo = st.button(
                    "🧾 Ver detalle",
                    type="primary",
                    width="stretch",
                    disabled=not bool(
                        filas_reclamos_consultas
                    ),
                    key="btn_ver_detalle_reclamo_consultas",
                )

            if (
                ver_detalle_reclamo
                and filas_reclamos_consultas
            ):
                indice_reclamo = filas_reclamos_consultas[0]

                reclamo_seleccionado = (
                    reclamos_filtrados
                    .reset_index(drop=True)
                    .iloc[indice_reclamo]
                )

                abrir_detalle_reclamo_consultas(
                    reclamo_seleccionado
                )
    st.markdown("---")


    # La búsqueda/filtros se aplican junto a la tabla comercial compacta.

    # CANCELACIONES DE ENTREGA - CARGA Y SEGUIMIENTO COMERCIAL
    # ==========================================================

    st.divider()
    can_titulo, can_historial = st.columns([4, 1])
    with can_titulo:
        st.markdown("### 🚫 Cancelaciones de entrega")
        st.caption(
            "Comercial registra y envía el aviso urgente. La resolución operativa "
            "continúa en el módulo Devoluciones de Logística."
        )
    with can_historial:
        if st.button(
            "Ocultar histórico" if st.session_state["mostrar_historico_cancelaciones_entrega"] else "📚 Histórico",
            width="stretch", key="btn_historico_cancelaciones_entrega"):
            st.session_state["mostrar_historico_cancelaciones_entrega"] = not st.session_state["mostrar_historico_cancelaciones_entrega"]
            st.rerun()

    try:
        cancelaciones_cache = cargar_cancelaciones_cache()
        cancelaciones_totales = cancelaciones_cache["totales"]
        cancelaciones_activas = cancelaciones_cache["activas"]
    except Exception as error:
        cancelaciones_totales = pd.DataFrame()
        cancelaciones_activas = pd.DataFrame()
        st.error(f"No se pudieron leer las cancelaciones de entrega: {error}")

    if st.session_state["mostrar_historico_cancelaciones_entrega"]:
        mostrar_historial_cancelaciones_entrega(cancelaciones_totales)
        st.divider()

    with st.expander("➕ Cargar cancelación de entrega", expanded=False):
        st.warning("Gestión de SUPER PRIORIDAD. Registrala y enviá el aviso inmediatamente.")
        opciones_clientes_cancelacion = construir_opciones_clientes_cancelacion(datos.get("clientes", pd.DataFrame()))
        with st.form("form_cancelacion_entrega", clear_on_submit=True):
            c1,c2=st.columns(2)
            with c1:
                remito_cancelacion=st.text_area("Remitos *",placeholder="Uno por línea o separados por coma",height=110)
                cliente_cancelacion=st.selectbox("Cliente *",options=opciones_clientes_cancelacion,index=0)
            with c2:
                motivo_cancelacion=st.selectbox("Motivo *",options=["Devolución del cliente","Error de carga del vendedor","Pedido duplicado","Error de carga de productos","Otros"])
                observacion_cancelacion=st.text_area("Observación")
            st.caption(
                "La alerta se preparará para **Leo y Juanma**. "
                "Después de registrar la cancelación aparecerán dos botones de WhatsApp."
            )
            cargar_cancelacion=st.form_submit_button(
                "🚨 Registrar y preparar WhatsApp",
                type="primary",
                width="stretch",
            )
        if cargar_cancelacion:
            usuario_cancelacion=st.session_state.get("usuario") or st.session_state.get("nombre_usuario") or "Usuario app"
            if cliente_cancelacion=="Seleccionar cliente...":
                st.error("Seleccioná un cliente.")
            else:
                try:
                    telefonos_destino = " | ".join(DESTINATARIOS_WHATSAPP.values())
                    resultado=guardar_cancelacion_entrega(
                        remito_cancelacion,
                        cliente_cancelacion,
                        motivo_cancelacion,
                        observacion_cancelacion,
                        usuario_cancelacion,
                        telefonos_destino,
                    )
                    if resultado.get("duplicado"):
                        st.warning(resultado["mensaje"])
                    else:
                        urls_whatsapp = {
                            nombre: construir_url_whatsapp_cancelacion(
                                resultado["registro"], telefono
                            )
                            for nombre, telefono in DESTINATARIOS_WHATSAPP.items()
                        }
                        st.session_state["ultima_cancelacion_whatsapp"] = {
                            "id": resultado["id"],
                            "urls": urls_whatsapp,
                            "registro": resultado["registro"],
                        }
                        invalidar_cache_gestion()
                        st.success(
                            "Cancelación registrada. Enviá la alerta a Leo y a Juanma."
                        )
                except Exception as error:
                    st.error(f"No se pudo registrar: {error}")

    ultima=st.session_state.get("ultima_cancelacion_whatsapp")
    if ultima:
        st.error("🚨 Aviso pendiente de envío a Leo y Juanma.")
        urls_whatsapp = ultima.get("urls", {})
        w1,w2,w3=st.columns([1.4,1.4,1.1])
        with w1:
            st.link_button(
                "📲 Enviar a Leo",
                urls_whatsapp.get("Leo", "#"),
                type="primary",
                width="stretch",
            )
        with w2:
            st.link_button(
                "📲 Enviar a Juanma",
                urls_whatsapp.get("Juanma", "#"),
                type="primary",
                width="stretch",
            )
        with w3:
            if st.button(
                "✅ Confirmar ambos",
                width="stretch",
                key="btn_confirmar_whatsapp_enviado",
            ):
                usuario=st.session_state.get("usuario") or st.session_state.get("nombre_usuario") or "Usuario app"
                confirmar_envio_whatsapp(ultima["id"],usuario)
                st.session_state["ultima_cancelacion_whatsapp"]=None
                invalidar_cache_gestion()
                st.success("Avisos enviados y gestión derivada a Logística.")
                st.rerun()

    if cancelaciones_activas.empty:
        st.info("No hay cancelaciones abiertas.")
    else:
        vista=cancelaciones_activas.copy()
        vista["EstadoComercial"]=vista["EstadoCancelacion"].apply(estado_para_comercial)
        vista["Fecha"]=pd.to_datetime(vista["FechaSolicitud"],errors="coerce").dt.strftime("%d/%m/%Y %H:%M").fillna(vista["FechaSolicitud"].astype(str))
        columnas=["Remito","Cliente","Motivo","EstadoComercial","ResponsableGestion","UltimaActualizacion","ResultadoFinal","Fecha"]
        columnas=[c for c in columnas if c in vista.columns]
        st.markdown("#### Seguimiento de cancelaciones abiertas")
        st.dataframe(vista[columnas].rename(columns={"EstadoComercial":"Estado","ResponsableGestion":"Responsable Logística","UltimaActualizacion":"Última actualización","ResultadoFinal":"Resultado"}),width="stretch",hide_index=True)


    # ==========================================================
    # URGENCIAS
    # ==========================================================
    # Desde V9 las urgencias son un TIPO DE SOLICITUD comercial.
    # Comercial no tiene acceso a cola/worker DIGIP desde este módulo.

    # ==========================================================
    # CENTRO DE GESTIÓN DEL PEDIDO
    # ==========================================================

    @st.dialog("📚 Gestión múltiple", width="large")
    def abrir_gestion_multiple(seleccionados: pd.DataFrame) -> None:
        tabla_lote = seleccionados.copy().reset_index(drop=True)
        cantidad = len(tabla_lote)
        clientes_lote = sorted(
            tabla_lote["Cliente"]
            .fillna("")
            .astype(str)
            .str.strip()
            .loc[lambda x: x.ne("")]
            .unique()
            .tolist()
        )
        pedidos_lote = tabla_lote["Pedido"].astype(str).tolist()

        c1, c2, c3 = st.columns(3)
        c1.metric("Pedidos", cantidad)
        c2.metric("Clientes", len(clientes_lote))
        c3.metric(
            "Unidades",
            int(
                pd.to_numeric(
                    tabla_lote.get("Unidades", 0),
                    errors="coerce",
                ).fillna(0).sum()
            ),
        )
        st.caption("Pedidos: " + " · ".join(pedidos_lote))
        st.info(
            "La gestión múltiple genera Solicitudes. "
            "Urgencia es un tipo de solicitud y no dispara ningún worker."
        )

        usuario = (
            st.session_state.get("usuario")
            or st.session_state.get("nombre_usuario")
            or ""
        )

        tipo_solicitud = st.selectbox(
            "Tipo de solicitud",
            [
                "Urgencia",
                "Consulta de estado",
                "Cambio de prioridad",
                "Coordinación de entrega",
                "Postergar Entrega",
                "Documentación",
                "Otro",
            ],
            key="tipo_solicitud_multiple",
        )

        with st.form("form_solicitud_multiple", clear_on_submit=False):
            opciones_prioridad = (
                ["Alta", "Crítica"]
                if tipo_solicitud == "Urgencia"
                else ["Normal", "Alta", "Baja"]
            )
            prioridad = st.selectbox("Prioridad", opciones_prioridad)

            fecha_habilitacion = None
            if tipo_solicitud == "Postergar Entrega":
                fecha_habilitacion = st.date_input(
                    "Habilitar pedidos desde",
                    value=None,
                    help=(
                        "Los pedidos quedan bloqueados hasta el día anterior y "
                        "se liberan automáticamente desde esta fecha."
                    ),
                )

            descripcion = st.text_area(
                "Descripción",
                placeholder=(
                    "Detalle común para todos los pedidos seleccionados..."
                    if tipo_solicitud != "Urgencia"
                    else "Indicá motivo, compromiso/fecha requerida y contexto de la urgencia..."
                ),
                height=110,
            )
            confirmar = st.form_submit_button(
                f"📩 Generar solicitud para {cantidad} pedidos",
                type="primary",
                width="stretch",
            )

        if confirmar:
            if not descripcion.strip() or not usuario:
                st.error(
                    "No se puede registrar la gestión: descripción y usuario son obligatorios."
                )
                return
            if tipo_solicitud == "Postergar Entrega" and fecha_habilitacion is None:
                st.error(
                    "La fecha de habilitación es obligatoria para Postergar Entrega."
                )
                return

            creadas, duplicadas, errores = [], [], []
            for _, fila_lote in tabla_lote.iterrows():
                pedido = str(fila_lote.get("Pedido", "")).strip()
                cliente = str(fila_lote.get("Cliente", "")).strip()
                if not pedido or not cliente:
                    errores.append(
                        f"{pedido or 'Sin pedido'}: faltan datos del pedido/cliente"
                    )
                    continue
                try:
                    r = guardar_solicitud(
                        pedido=pedido,
                        cliente=cliente,
                        tipo_solicitud=tipo_solicitud,
                        descripcion=descripcion.strip(),
                        usuario_solicitante=usuario,
                        prioridad=prioridad,
                        fecha_habilitacion=(
                            fecha_habilitacion.strftime("%Y-%m-%d")
                            if fecha_habilitacion is not None
                            else ""
                        ),
                    )
                    (duplicadas if r.get("duplicado") else creadas).append(pedido)
                except Exception as error:
                    errores.append(f"{pedido}: {error}")

            invalidar_cache_gestion()
            if creadas:
                st.success(
                    f"Solicitudes creadas: {len(creadas)} · " + ", ".join(creadas)
                )
            if duplicadas:
                st.warning(
                    f"Ya tenían una solicitud equivalente: {len(duplicadas)} · "
                    + ", ".join(duplicadas)
                )
            if errores:
                st.error("No se pudieron procesar:\n- " + "\n- ".join(errores))
            if not errores:
                st.session_state["consultas_pedidos_gestion_multiple"] = []
                st.session_state["consultas_abrir_gestion_multiple"] = False
                st.toast("Gestión múltiple registrada.", icon="✅")


    def abrir_detalle_pedido(
        pedido_detalle: str,
    ) -> None:
        pedido_detalle = str(pedido_detalle).strip()

        coincidencia = tabla_consultas[
            tabla_consultas["Pedido"]
            .astype(str)
            .eq(pedido_detalle)
        ].copy()

        if coincidencia.empty:
            st.warning(
                f"No se encontró el pedido {pedido_detalle}."
            )

        else:
            fila = coincidencia.iloc[0]

            st.markdown(
                f"""
                <div style="
                    line-height:1.15;
                    margin-bottom:0.35rem;
                ">
                    <div style="
                        font-size:0.78rem;
                        opacity:0.72;
                    ">
                        📦 PEDIDO
                    </div>
                    <div style="
                        font-size:1.35rem;
                        font-weight:700;
                        margin:0.05rem 0 0.30rem 0;
                    ">
                        {fila["Pedido"]}
                    </div>
                    <div style="
                        font-size:1.05rem;
                        font-weight:650;
                        margin-bottom:0.40rem;
                    ">
                        {fila["Cliente"]}
                    </div>
                    <div style="
                        font-size:0.78rem;
                        opacity:0.72;
                    ">
                        Estado
                    </div>
                    <div style="
                        font-size:1.05rem;
                        font-weight:600;
                    ">
                        {fila["CategoriaComercial"]}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.info(fila["EstadoComercial"])

            st.markdown("##### Operación")

            operacion_1, operacion_2, operacion_3 = st.columns(
                3,
                gap="small",
            )

            with operacion_1:
                with st.container(border=True):
                    st.caption("📅 PLANIFICACIÓN")
                    st.markdown(
                        f"**{fila['Planificacion'] or 'Sin definir'}**"
                    )

            with operacion_2:
                with st.container(border=True):
                    st.caption("🚚 DESPACHO")
                    st.markdown(
                        f"**{fila['Despacho'] or 'Sin despacho asignado'}**"
                    )

            with operacion_3:
                with st.container(border=True):
                    st.caption("🛒 CARRO / CONTENEDOR")
                    st.markdown(
                        f"**{fila['Contenedor'] or 'Sin asignar'}**"
                    )

            st.divider()
            st.markdown("##### 📋 Nueva solicitud")
            st.caption(
                "Urgencia se registra como tipo de Solicitud. "
                "Comercial no ejecuta workers ni agrupaciones desde este módulo."
            )

            st.caption(
                "Las solicitudes existentes se administran "
                "desde la tabla superior «Solicitudes pendientes»."
            )

            tipo_solicitud = st.selectbox(
                "Tipo de solicitud",
                options=[
                    "Urgencia",
                    "Consulta de estado",
                    "Cambio de prioridad",
                    "Coordinación de entrega",
                    "Postergar Entrega",
                    "Documentación",
                    "Otro",
                ],
                key=f"tipo_solicitud_nueva_{fila['Pedido']}",
            )

            with st.form(
                f"form_solicitud_{fila['Pedido']}",
                clear_on_submit=True,
            ):
                opciones_prioridad = (
                    ["Alta", "Crítica"]
                    if tipo_solicitud == "Urgencia"
                    else ["Normal", "Alta", "Baja"]
                )
                prioridad_solicitud = st.selectbox(
                    "Prioridad",
                    options=opciones_prioridad,
                )

                fecha_habilitacion = None
                if tipo_solicitud == "Postergar Entrega":
                    fecha_habilitacion = st.date_input(
                        "Habilitar pedido desde",
                        value=None,
                        help=(
                            "Hasta el día anterior el pedido queda bloqueado. "
                            "Desde esta fecha vuelve automáticamente a planificación."
                        ),
                    )

                descripcion_solicitud = st.text_area(
                    "Descripción",
                    placeholder=(
                        "Indicá motivo, compromiso/fecha requerida y contexto de la urgencia..."
                        if tipo_solicitud == "Urgencia"
                        else "Detalle de la solicitud para Logística..."
                    ),
                    height=110,
                )

                confirmar_solicitud = st.form_submit_button(
                    "📩 Registrar solicitud",
                    type="primary",
                    width="stretch",
                )

            if confirmar_solicitud:
                if not str(descripcion_solicitud).strip():
                    st.error("La descripción es obligatoria.")
                    st.stop()

                if (
                    tipo_solicitud == "Postergar Entrega"
                    and fecha_habilitacion is None
                ):
                    st.error(
                        "Indicá la fecha desde la que el pedido vuelve a quedar habilitado."
                    )
                    st.stop()

                usuario_solicitante = (
                    st.session_state.get("usuario")
                    or st.session_state.get("nombre_usuario")
                    or "Usuario no identificado"
                )

                try:
                    resultado_solicitud = guardar_solicitud(
                        pedido=fila["Pedido"],
                        cliente=fila["Cliente"],
                        tipo_solicitud=tipo_solicitud,
                        descripcion=descripcion_solicitud,
                        usuario_solicitante=usuario_solicitante,
                        prioridad=prioridad_solicitud,
                        fecha_habilitacion=(
                            fecha_habilitacion.strftime("%Y-%m-%d")
                            if fecha_habilitacion is not None
                            else ""
                        ),
                    )

                    st.success(resultado_solicitud["mensaje"])
                    st.toast(
                        "Solicitud agregada a la gestión comercial.",
                        icon="📩",
                    )
                    invalidar_cache_gestion()
                    st.rerun(scope="fragment")

                except Exception:
                    st.error("No se pudo registrar la solicitud.")
                    logger.exception(
                        "Error controlado en el módulo de Consultas Comerciales."
                    )

            fecha_transmision = fila[
                "FechaTransmisionERP"
            ]

            fecha_transmision_texto = (
                fecha_transmision.strftime("%d/%m/%Y")
                if pd.notna(fecha_transmision)
                else "Sin dato"
            )

            detalle_erp, detalle_composicion = st.columns(
                2,
                gap="small",
            )

            with detalle_erp:
                st.markdown("##### Transmisión ERP")
                st.caption(
                    f"**N.º envío:** "
                    f"{fila['NroEnvioERP'] or 'Sin dato'}  \\n"
                    f"**Fecha:** {fecha_transmision_texto}  \\n"
                    f"**Hora:** "
                    f"{fila['HoraTransmisionERP'] or 'Sin dato'}"
                )

            with detalle_composicion:
                st.markdown("##### Composición")
                st.caption(
                    f"**Unidades:** "
                    f"{int(fila['Unidades']):,}"
                    .replace(",", ".")
                    + "  \\n"
                    + f"**Volumen:** "
                    f"{float(fila['M3']):.3f} m³  \\n"
                    + f"**Familias:** {fila['Familias']}"
                )


    # ==========================================================
    # BÚSQUEDA Y FILTROS DE LA TABLA
    # ==========================================================

    st.markdown("---")
    st.subheader("🔎 Pedidos activos")

    filtros_actuales = st.session_state["consultas_filtros_aplicados"]

    def _opciones(columna: str) -> list[str]:
        if columna not in tabla_consultas.columns:
            return []
        return sorted(
            x for x in
            tabla_consultas[columna].fillna("").astype(str).str.strip().unique().tolist()
            if x
        )

    opciones_estado_pedido = _opciones("EstadoPedido")
    opciones_estado_preparacion = _opciones("EstadoPreparacion")
    opciones_estado_operativo = _opciones("EstadoOperativo")

    with st.form("form_busqueda_consultas", clear_on_submit=False):
        f1, f2, f3, f4 = st.columns([2.8, 1.4, 1.5, 1.4])

        with f1:
            busqueda_form = st.text_input(
                "Buscar",
                value=filtros_actuales.get("busqueda", ""),
                placeholder="Pedido, código o cliente",
            )

        with f2:
            estado_pedido_form = st.multiselect(
                "Estado pedido",
                options=opciones_estado_pedido,
                default=[
                    x for x in filtros_actuales.get("estado_pedido", [])
                    if x in opciones_estado_pedido
                ],
            )

        with f3:
            estado_preparacion_form = st.multiselect(
                "Estado preparación",
                options=opciones_estado_preparacion,
                default=[
                    x for x in filtros_actuales.get("estado_preparacion", [])
                    if x in opciones_estado_preparacion
                ],
            )

        with f4:
            estado_operativo_form = st.multiselect(
                "Semáforo",
                options=opciones_estado_operativo,
                default=[
                    x for x in filtros_actuales.get("estado_operativo", [])
                    if x in opciones_estado_operativo
                ],
            )

        b1, b2, _ = st.columns([1.2, 1.2, 5])
        with b1:
            aplicar = st.form_submit_button("🔎 Aplicar", type="primary", width="stretch")
        with b2:
            limpiar = st.form_submit_button("🧹 Limpiar", width="stretch")

    if aplicar:
        st.session_state["consultas_filtros_aplicados"] = {
            "busqueda": busqueda_form.strip(),
            "estado_pedido": estado_pedido_form,
            "estado_preparacion": estado_preparacion_form,
            "estado_operativo": estado_operativo_form,
        }
        st.session_state["consultas_detalle_abierto"] = False
        st.session_state["consultas_pedido_detalle"] = ""
        st.session_state["consulta_pedido_seleccionado"] = ""
        st.rerun()

    if limpiar:
        st.session_state["consultas_filtros_aplicados"] = {
            "busqueda": "",
            "estado_pedido": [],
            "estado_preparacion": [],
            "estado_operativo": [],
        }
        st.session_state["consultas_detalle_abierto"] = False
        st.session_state["consultas_pedido_detalle"] = ""
        st.session_state["consulta_pedido_seleccionado"] = ""
        st.rerun()

    filtros = st.session_state["consultas_filtros_aplicados"]
    tabla_filtrada = tabla_consultas.copy()

    texto_busqueda = str(filtros.get("busqueda", "")).strip()
    if texto_busqueda:
        mascara = pd.Series(False, index=tabla_filtrada.index)
        for columna in ["Pedido", "ClienteCodigo", "CodigoLogistico", "Cliente"]:
            if columna in tabla_filtrada.columns:
                mascara |= (
                    tabla_filtrada[columna].fillna("").astype(str)
                    .str.contains(texto_busqueda, case=False, na=False, regex=False)
                )
        tabla_filtrada = tabla_filtrada.loc[mascara].copy()

    for columna, clave in [
        ("EstadoPedido", "estado_pedido"),
        ("EstadoPreparacion", "estado_preparacion"),
        ("EstadoOperativo", "estado_operativo"),
    ]:
        seleccion = filtros.get(clave, [])
        if seleccion and columna in tabla_filtrada.columns:
            tabla_filtrada = tabla_filtrada[
                tabla_filtrada[columna].fillna("").astype(str).isin(seleccion)
            ].copy()

    @st.fragment
    def render_tabla_comercial_fragment() -> None:
        # ==========================================================
        # TABLA COMERCIAL COMPACTA
        # ==========================================================

        st.subheader("Tabla general de pedidos")

        columnas_visibles = [
            "Pedido",
            "FechaCreacion",
            "FechaTransmisionERP",
            "ClienteCodigo",
            "Cliente",
            "Unidades",
            "M3",
            "EstadoVolumetria",
            "Planificacion",
            "Despacho",
            "EstadoPedido",
            "EstadoPreparacion",
            "EstadoOperativo",
            "Contenedor",
            "Solicitud",
        ]
        columnas_visibles = [c for c in columnas_visibles if c in tabla_filtrada.columns]

        tabla_visible_pedidos = (
            tabla_filtrada[columnas_visibles]
            .reset_index(drop=True)
            .copy()
        )

        COLUMN_CONFIG = {
            "Pedido": st.column_config.TextColumn("Pedido", width="small"),
            "FechaCreacion": st.column_config.DateColumn(
                "Creación", format="DD/MM/YYYY", width="small"
            ),
            "FechaTransmisionERP": st.column_config.DateColumn(
                "Transmisión", format="DD/MM/YYYY", width="small"
            ),
            "ClienteCodigo": st.column_config.TextColumn(
                "Código cliente", width="small"
            ),
            "Cliente": st.column_config.TextColumn("Cliente", width="large"),
            "Unidades": st.column_config.NumberColumn("Unid.", format="%d", width="small"),
            "M3": st.column_config.NumberColumn("M³", format="%.3f", width="small"),
            "EstadoVolumetria": st.column_config.TextColumn("Volumetría", width="small"),
            "Planificacion": st.column_config.TextColumn("Planificación", width="small"),
            "Despacho": st.column_config.TextColumn("Despacho", width="medium"),
            "EstadoPedido": st.column_config.TextColumn("Estado pedido", width="small"),
            "EstadoPreparacion": st.column_config.TextColumn(
                "Estado preparación", width="small"
            ),
            "EstadoOperativo": st.column_config.TextColumn("Estado", width="small"),
            "Contenedor": st.column_config.TextColumn("Carro pendiente", width="medium"),
            "Solicitud": st.column_config.TextColumn("Solicitud", width="small"),
        }

        st.caption(
            f"{len(tabla_visible_pedidos):,} pedidos visibles".replace(",", ".")
        )

        evento_tabla_pedidos = st.dataframe(
            tabla_visible_pedidos,
            width="stretch",
            hide_index=True,
            height=500,
            column_config=COLUMN_CONFIG,
            on_select="rerun",
            selection_mode="multi-row",
            key="tabla_general_consultas",
        )

        indices_seleccionados = (
            list(evento_tabla_pedidos.selection.rows)
            if evento_tabla_pedidos is not None
            else []
        )
        indices_seleccionados = [
            i for i in indices_seleccionados
            if 0 <= i < len(tabla_visible_pedidos)
        ]
        seleccionados = tabla_visible_pedidos.iloc[indices_seleccionados].copy()

        cantidad_seleccionada = len(seleccionados)
        if cantidad_seleccionada == 0:
            st.caption(
                "Seleccioná uno o varios pedidos. Con uno podés abrir el detalle; "
                "con varios podés generar una misma urgencia o solicitud en lote."
            )
        elif cantidad_seleccionada == 1:
            fila_sel = seleccionados.iloc[0]
            c_info, c_accion = st.columns([5, 1], vertical_alignment="center")
            with c_info:
                st.caption(
                    f"Seleccionado: pedido **{fila_sel['Pedido']}** · {fila_sel['Cliente']}"
                )
            with c_accion:
                abrir_detalle = st.button(
                    "👁 Ver detalle", type="primary", width="stretch",
                    key="btn_detalle_tabla_consultas",
                )
            if abrir_detalle:
                st.session_state["consultas_pedido_detalle"] = (
                    str(fila_sel["Pedido"]).strip()
                )
                st.session_state["consultas_detalle_abierto"] = True
                st.session_state["consultas_pedidos_gestion_multiple"] = []
                st.session_state["consultas_abrir_gestion_multiple"] = False
        else:
            clientes = seleccionados["Cliente"].fillna("").astype(str).str.strip().nunique()
            unidades = int(pd.to_numeric(seleccionados["Unidades"], errors="coerce").fillna(0).sum())
            c_info, c_accion = st.columns([4, 1.4], vertical_alignment="center")
            with c_info:
                st.caption(
                    f"**{cantidad_seleccionada} pedidos seleccionados** · "
                    f"{clientes} cliente{'s' if clientes != 1 else ''} · "
                    f"{unidades} unidades"
                )
            with c_accion:
                gestionar_lote = st.button(
                    "📚 Gestionar selección", type="primary", width="stretch",
                    key="btn_gestion_multiple_consultas",
                )
            if gestionar_lote:
                st.session_state["consultas_pedidos_gestion_multiple"] = (
                    seleccionados["Pedido"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s.ne("")]
                    .tolist()
                )
                st.session_state["consultas_abrir_gestion_multiple"] = True
                st.session_state["consultas_detalle_abierto"] = False
                st.session_state["consultas_pedido_detalle"] = ""

        # ======================================================
        # GESTIÓN PERSISTENTE DENTRO DEL FRAGMENT
        # ======================================================
        # La selección de la tabla provoca un rerun del fragmento.
        # Por eso el pedido/lote elegido se guarda en session_state.
        # Los widgets de la gestión pueden rerunear sin cerrar el panel.

        pedido_abierto = str(
            st.session_state.get("consultas_pedido_detalle", "")
            or ""
        ).strip()

        detalle_abierto = bool(
            st.session_state.get("consultas_detalle_abierto", False)
        )

        pedidos_lote = [
            str(p).strip()
            for p in st.session_state.get(
                "consultas_pedidos_gestion_multiple",
                [],
            )
            if str(p).strip()
        ]

        if detalle_abierto and pedido_abierto:
            st.markdown("---")

            _, col_cerrar = st.columns([6, 1])
            with col_cerrar:
                cerrar_detalle = st.button(
                    "✖ Cerrar gestión",
                    width="stretch",
                    key="btn_cerrar_gestion_pedido_consultas",
                )

            if cerrar_detalle:
                st.session_state["consultas_detalle_abierto"] = False
                st.session_state["consultas_pedido_detalle"] = ""
                st.rerun(scope="fragment")

            abrir_detalle_pedido(pedido_abierto)

        elif (
            st.session_state.get(
                "consultas_abrir_gestion_multiple",
                False,
            )
            and pedidos_lote
        ):
            lote_actual = tabla_visible_pedidos.loc[
                tabla_visible_pedidos["Pedido"]
                .fillna("")
                .astype(str)
                .isin(pedidos_lote)
            ].copy()

            # El disparador se consume ANTES de abrir el diálogo.
            # Así, al cerrarlo con la X no vuelve a abrirse solo.
            st.session_state["consultas_abrir_gestion_multiple"] = False

            if not lote_actual.empty:
                abrir_gestion_multiple(lote_actual)

    render_tabla_comercial_fragment()
