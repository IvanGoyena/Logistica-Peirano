# pages/08_Consultas.py

from __future__ import annotations

import logging
from urllib.parse import quote

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

from config import CARPETA_DATOS
from utils.autenticacion import requerir_roles
from utils.leer_datos import leer_archivo
from utils.gestion_consultas import (
    guardar_urgencia,
    guardar_solicitud,
    editar_solicitud,
    eliminar_solicitud,
)
from utils.leer_gestion_consultas import (
    leer_solicitudes,
    leer_urgencias,
    leer_reclamos,
    obtener_urgencias_activas,
    obtener_solicitudes_abiertas,
    obtener_solicitudes_pedido,
    obtener_historial_solicitudes,
    obtener_historial_urgencias,
    obtener_historial_reclamos,
)

from utils.gestion_devoluciones import (
    guardar_cancelacion_entrega,
    confirmar_envio_whatsapp,
)
from utils.leer_devoluciones import (
    obtener_cancelaciones_activas,
    obtener_historial_cancelaciones,
    estado_para_comercial,
)

from utils.gestion_urgencias_digip import (
    obtener_urgencias_pendientes_digip,
    obtener_pedidos_pendientes_digip,
    marcar_lote_procesando,
    marcar_lote_exitoso,
    marcar_lote_error,
)

from utils.cola_agrupaciones import (
    crear_orden_agrupacion,
    obtener_orden,
)

from models.pedidos import construir_tabla_pedidos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos
from models.consultas import construir_tabla_consultas
from components.reclamos import (
    mostrar_boton_carga_reclamo,
)


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
            "Solicitud de prioridad",
            "Retiro en Depósito",
            "Revisión de Stock",
            "Postergar Entrega",
            "Cancelación",
            "Otros",
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
                use_container_width=True,
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
            use_container_width=True,
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


# ==========================================================
# PERMISOS Y CONFIGURACIÓN
# ==========================================================

requerir_roles(
    "admin",
    "gerencia",
    "logistica",
    "supervisor",
    "comercial",
)

st.set_page_config(
    page_title="Consultas Comerciales",
    page_icon="🔎",
    layout="wide",
)


# ==========================================================
# CARGA DE DATOS
# ==========================================================

@st.cache_data(show_spinner="Cargando información comercial...")
def cargar_datos_consultas() -> dict[str, pd.DataFrame]:
    return {
        "pedidos": leer_archivo(
            CARPETA_DATOS,
            "Pedidos DIGIP",
            cache=False,
        ),
        "detalle": leer_archivo(
            CARPETA_DATOS,
            "Detalle Pendientes",
            cache=False,
        ),
        "articulos": leer_archivo(
            CARPETA_DATOS,
            "Maestro Articulo",
            cache=True,
        ),
        "clientes": leer_archivo(
            CARPETA_DATOS,
            "Maestro Clientes",
            cache=True,
        ),
        "pendientes_erp": leer_archivo(
            CARPETA_DATOS,
            "Pedidos Pendientes",
            cache=False,
        ),
        "transmisiones": leer_archivo(
            CARPETA_DATOS,
            "Pedidos Transmicion",
            cache=False,
        ),
        "expresos": leer_archivo(
            CARPETA_DATOS,
            "Datos Expresos",
            cache=True,
        ),
        "volumetria": leer_archivo(
            CARPETA_DATOS,
            "Maestro Volumetria",
            cache=True,
        ),
        "tareas": leer_archivo(
            CARPETA_DATOS,
            "Informe Tareas",
            cache=False,
        ),
    }


# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def construir_tabla_operativa(
    datos: dict[str, pd.DataFrame],
) -> pd.DataFrame:

    tabla = construir_tabla_pedidos(
        datos["pedidos"].copy(),
        datos["detalle"].copy(),
        datos["articulos"].copy(),
        datos["clientes"].copy(),
        datos["volumetria"].copy(),
    )

    tabla_transmisiones = construir_tabla_transmisiones(
        datos["transmisiones"].copy()
    )

    tabla_pendientes = construir_tabla_pendientes(
        datos["pendientes_erp"].copy()
    )

    tabla_clientes = construir_tabla_clientes(
        datos["clientes"].copy()
    )

    tabla_expresos = construir_tabla_expresos(
        datos["expresos"].copy()
    )

    for dataframe in [
        tabla,
        tabla_transmisiones,
        tabla_pendientes,
    ]:
        dataframe["Pedido"] = (
            dataframe["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.split("-")
            .str[0]
        )

    tabla = tabla.merge(
        tabla_transmisiones,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    pendientes_planificacion = (
        tabla_pendientes[
            [
                "Pedido",
                "CodigoSucursal",
                "CodigoExpreso",
                "ImporteERP",
            ]
        ]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        pendientes_planificacion,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

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
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        clientes_planificacion,
        on="CodigoSucursal",
        how="left",
        validate="many_to_one",
    )

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
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        expresos_planificacion,
        on="CodigoExpreso",
        how="left",
        validate="many_to_one",
    )

    for columna in [
        "FrecuenciaPreparacion",
        "FrecuenciaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    frecuencia_entrega = (
        tabla["FrecuenciaEntrega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    zona_expreso = (
        tabla["ZonaAgrupadorExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    dias_semanales = {
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "MIÉRCOLES",
        "JUEVES",
        "VIERNES",
    }

    tabla["Planificacion"] = frecuencia_entrega.where(
        frecuencia_entrega.isin(dias_semanales),
        zona_expreso.where(
            zona_expreso.ne(""),
            frecuencia_entrega,
        ),
    )

    return tabla


# ==========================================================
# ESTADO INICIAL
# ==========================================================

if "consultas_filtros_aplicados" not in st.session_state:
    st.session_state["consultas_filtros_aplicados"] = {
        "busqueda": "",
    }

if "consultas_detalle_abierto" not in st.session_state:
    st.session_state["consultas_detalle_abierto"] = False

if "consultas_pedido_detalle" not in st.session_state:
    st.session_state["consultas_pedido_detalle"] = ""

if "mostrar_historico_reclamos" not in st.session_state:
    st.session_state["mostrar_historico_reclamos"] = False

if "mostrar_historico_solicitudes" not in st.session_state:
    st.session_state["mostrar_historico_solicitudes"] = False

if "mostrar_historico_urgencias" not in st.session_state:
    st.session_state["mostrar_historico_urgencias"] = False

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
        "conservadas en Google Sheets."
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
        vista, use_container_width=True, hide_index=True,
        height=min(420, 85 + len(vista) * 35),
        key="tabla_historico_solicitudes",
    )


def mostrar_historial_urgencias(
    urgencias: pd.DataFrame,
) -> None:
    st.markdown("#### 📚 Histórico de urgencias")
    st.caption(
        "Urgencias pendientes, procesadas, agrupadas y con error "
        "conservadas en Google Sheets."
    )

    if urgencias is None or urgencias.empty:
        st.info("Todavía no hay urgencias registradas.", icon="🚨")
        return

    tabla = urgencias.copy()
    for columna in [
        "UrgenciaID", "Pedido", "Cliente", "Motivo",
        "FechaRequerida", "Observacion", "UsuarioSolicitante",
        "FechaSolicitud", "EstadoUrgencia", "AgrupadorDestino",
        "EstadoEjecucionDIGIP", "MensajeEjecucionDIGIP",
        "FechaEjecucionDIGIP",
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
        "Buscar en urgencias",
        placeholder="Pedido, cliente, motivo o ID...",
        key="buscar_historico_urgencias",
    )
    if busqueda.strip():
        mascara = pd.Series(False, index=tabla.index)
        for columna in [
            "UrgenciaID", "Pedido", "Cliente",
            "Motivo", "Observacion",
        ]:
            mascara |= tabla[columna].astype(str).str.contains(
                busqueda.strip(), case=False, na=False, regex=False
            )
        tabla = tabla.loc[mascara]

    vista = tabla[[
        "UrgenciaID", "Pedido", "Cliente", "Motivo",
        "FechaRequerida", "EstadoUrgencia",
        "EstadoEjecucionDIGIP", "Fecha",
        "MensajeEjecucionDIGIP",
    ]].rename(columns={
        "UrgenciaID": "ID",
        "FechaRequerida": "Fecha requerida",
        "EstadoUrgencia": "Estado",
        "EstadoEjecucionDIGIP": "Ejecución DIGIP",
        "MensajeEjecucionDIGIP": "Resultado DIGIP",
    })

    st.dataframe(
        vista, use_container_width=True, hide_index=True,
        height=min(420, 85 + len(vista) * 35),
        key="tabla_historico_urgencias",
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


def obtener_telefono_cancelaciones() -> str:
    """Obtiene el teléfono de prueba desde Secrets o usa el número empresarial."""

    try:
        telefono = str(st.secrets.get("WHATSAPP_CANCELACIONES", "")).strip()
    except Exception:
        telefono = ""

    return telefono or "5491172151924"


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


def construir_url_whatsapp_cancelacion(registro: dict) -> str:
    telefono = obtener_telefono_cancelaciones()
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
        use_container_width=True,
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
        use_container_width=True,
        key="btn_historico_reclamos_consultas",
    ):
        st.session_state["mostrar_historico_reclamos"] = (
            not st.session_state["mostrar_historico_reclamos"]
        )
        st.rerun()

with col_actualizar:
    actualizar = st.button(
        "🔄 Actualizar",
        use_container_width=True,
    )

if actualizar:
    cargar_datos_consultas.clear()
    st.rerun()


# ==========================================================
# CONSTRUIR DATOS
# ==========================================================

try:
    datos = cargar_datos_consultas()

    tabla_operativa = construir_tabla_operativa(
        datos
    )

    tabla_consultas = construir_tabla_consultas(
        tabla_operativa,
        df_tareas=datos["tareas"],
    )

    # ------------------------------------------------------
    # URGENCIAS ACTIVAS
    # ------------------------------------------------------

    urgencias_activas = obtener_urgencias_activas()

    if urgencias_activas is None:
        urgencias_activas = pd.DataFrame()

    if not urgencias_activas.empty:
        urgencias_activas = urgencias_activas.copy()

        urgencias_activas["Pedido"] = (
            urgencias_activas["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
            .str.split("-")
            .str[0]
        )

        urgencias_activas["FechaSolicitudOrden"] = pd.to_datetime(
            urgencias_activas["FechaSolicitud"],
            errors="coerce",
        )

        urgencias_activas = (
            urgencias_activas
            .sort_values(
                "FechaSolicitudOrden",
                ascending=False,
                na_position="last",
            )
            .drop_duplicates(
                subset=["Pedido"],
                keep="first",
            )
            .reset_index(drop=True)
        )

        pedidos_urgentes = set(
            urgencias_activas["Pedido"].tolist()
        )

    else:
        pedidos_urgentes = set()

    tabla_consultas["Urgencia"] = (
        tabla_consultas["Pedido"]
        .astype(str)
        .isin(pedidos_urgentes)
        .map({
            True: "🚨 Urgente",
            False: "",
        })
    )

    # ------------------------------------------------------
    # SOLICITUDES ABIERTAS
    # ------------------------------------------------------

    solicitudes_abiertas = obtener_solicitudes_abiertas()

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
    else:
        pedidos_con_solicitud = set()

    tabla_consultas["Solicitud"] = (
        tabla_consultas["Pedido"]
        .astype(str)
        .isin(pedidos_con_solicitud)
        .map({
            True: "📩 Pendiente",
            False: "",
        })
    )

except Exception as error:
    st.error("No se pudo construir la tabla de consultas.")
    logger.exception("Error controlado en el módulo de Consultas Comerciales.")
    st.stop()


# ==========================================================
# CARGA INDEPENDIENTE DE RECLAMOS
# ==========================================================

with espacio_boton_reclamo.container():
    mostrar_boton_carga_reclamo(
        df_clientes=datos["clientes"],
        df_articulos=datos["articulos"],
    )


# ==========================================================
# KPIs GENERALES DE GESTIÓN
# ==========================================================

solicitudes_totales = obtener_historial_solicitudes()
urgencias_totales = obtener_historial_urgencias()
reclamos_totales = obtener_historial_reclamos()

if solicitudes_totales is None:
    solicitudes_totales = pd.DataFrame()

if urgencias_totales is None:
    urgencias_totales = pd.DataFrame()

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
cantidad_urgencias = len(
    urgencias_totales
)
cantidad_reclamos = len(
    reclamos_totales
)

total_gestiones = (
    cantidad_solicitudes
    + cantidad_urgencias
    + cantidad_reclamos
)

gestiones_cerradas = (
    contar_cerradas(
        solicitudes_totales,
        "EstadoSolicitud",
    )
    + contar_cerradas(
        urgencias_totales,
        "EstadoUrgencia",
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
    kpi_gestion_6,
) = st.columns(6)

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
    "🚨 Urgencias",
    f"{cantidad_urgencias:,}".replace(",", "."),
)

kpi_gestion_6.metric(
    "🧾 Reclamos",
    f"{cantidad_reclamos:,}".replace(",", "."),
)


if st.session_state["mostrar_historico_reclamos"]:
    # ==========================================================
    # HISTORIAL Y SEGUIMIENTO DE RECLAMOS
    # ==========================================================

    st.markdown("### 📚 Histórico de reclamos")
    st.caption(
        "Incluye todos los reclamos abiertos, resueltos y rechazados "
        "guardados en Google Sheets. La actualización del estado se realiza "
        "desde Gestión de Pedidos."
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
            use_container_width=True,
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
            if filas_reclamos_consultas:
                fila_reclamo_seleccionada = (
                    tabla_reclamos_consultas.iloc[
                        filas_reclamos_consultas[0]
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
                use_container_width=True,
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


# ==========================================================
# APLICAR BÚSQUEDA GENERAL
# ==========================================================

filtros = st.session_state[
    "consultas_filtros_aplicados"
]

tabla_filtrada = tabla_consultas.copy()

texto_busqueda = str(
    filtros.get("busqueda", "")
).strip()

if texto_busqueda:

    mascara = (
        tabla_filtrada["Pedido"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False,
            regex=False,
        )
        |
        tabla_filtrada["ClienteCodigo"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False,
            regex=False,
        )
        |
        tabla_filtrada["Cliente"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False,
            regex=False,
        )
    )

    tabla_filtrada = tabla_filtrada.loc[
        mascara
    ].copy()


# ==========================================================

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
        use_container_width=True, key="btn_historico_cancelaciones_entrega"):
        st.session_state["mostrar_historico_cancelaciones_entrega"] = not st.session_state["mostrar_historico_cancelaciones_entrega"]
        st.rerun()

try:
    cancelaciones_totales = obtener_historial_cancelaciones()
    cancelaciones_activas = obtener_cancelaciones_activas()
except Exception as error:
    cancelaciones_totales = pd.DataFrame(); cancelaciones_activas = pd.DataFrame()
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
        telefono_prueba=obtener_telefono_cancelaciones()
        st.caption(f"El aviso se preparará para el WhatsApp: **{telefono_prueba}**")
        cargar_cancelacion=st.form_submit_button("🚨 Registrar y preparar WhatsApp",type="primary",use_container_width=True)
    if cargar_cancelacion:
        usuario_cancelacion=st.session_state.get("usuario") or st.session_state.get("nombre_usuario") or "Usuario app"
        if cliente_cancelacion=="Seleccionar cliente...":
            st.error("Seleccioná un cliente.")
        else:
            try:
                resultado=guardar_cancelacion_entrega(remito_cancelacion,cliente_cancelacion,motivo_cancelacion,observacion_cancelacion,usuario_cancelacion,telefono_prueba)
                if resultado.get("duplicado"): st.warning(resultado["mensaje"])
                else:
                    st.session_state["ultima_cancelacion_whatsapp"]={"id":resultado["id"],"url":construir_url_whatsapp_cancelacion(resultado["registro"]),"registro":resultado["registro"]}
                    st.success("Cancelación registrada. Abrí WhatsApp y enviá la alerta.")
            except Exception as error: st.error(f"No se pudo registrar: {error}")

ultima=st.session_state.get("ultima_cancelacion_whatsapp")
if ultima:
    st.error("🚨 Aviso pendiente de envío.")
    w1,w2=st.columns([3,1.25])
    with w1: st.link_button("📲 Abrir WhatsApp con la alerta",ultima["url"],type="primary",use_container_width=True)
    with w2:
        if st.button("✅ Confirmar envío",use_container_width=True,key="btn_confirmar_whatsapp_enviado"):
            usuario=st.session_state.get("usuario") or st.session_state.get("nombre_usuario") or "Usuario app"
            confirmar_envio_whatsapp(ultima["id"],usuario)
            st.session_state["ultima_cancelacion_whatsapp"]=None
            st.success("Aviso enviado y gestión derivada a Logística.")
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
    st.dataframe(vista[columnas].rename(columns={"EstadoComercial":"Estado","ResponsableGestion":"Responsable Logística","UltimaActualizacion":"Última actualización","ResultadoFinal":"Resultado"}),use_container_width=True,hide_index=True)


# GESTIÓN DE URGENCIAS DIGIP
# ==========================================================

urgencias_digip = obtener_urgencias_pendientes_digip()
pedidos_urgentes_digip = obtener_pedidos_pendientes_digip()

roles_ejecucion_urgencias = {
    "admin",
    "logistica",
    "supervisor",
}

rol_actual = (
    str(st.session_state.get("rol", ""))
    .strip()
    .lower()
)

puede_ejecutar_urgencias = (
    rol_actual in roles_ejecucion_urgencias
)


def construir_orden_urgentes(
    pedidos_urgentes: list[str],
    tabla_pedidos: pd.DataFrame,
) -> tuple[dict | None, list[str]]:
    """
    Prepara una única orden para el worker.

    Si existen varios códigos de despacho, el worker abre una sola
    preparación URGENTES, limpia el filtro de código y selecciona
    todos los pedidos por número. Así se evita crear varias
    preparaciones internas para el mismo destino.
    """

    if not pedidos_urgentes:
        return None, []

    columnas_requeridas = {
        "Pedido",
        "CodigoDespacho",
    }

    if not columnas_requeridas.issubset(
        tabla_pedidos.columns
    ):
        faltantes = sorted(
            columnas_requeridas
            - set(tabla_pedidos.columns)
        )

        raise ValueError(
            "No se puede preparar la urgencia. "
            f"Faltan columnas: {faltantes}"
        )

    tabla_base = tabla_pedidos[
        [
            "Pedido",
            "CodigoDespacho",
        ]
    ].copy()

    tabla_base["Pedido"] = (
        tabla_base["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.split("-")
        .str[0]
    )

    tabla_base["CodigoDespacho"] = (
        tabla_base["CodigoDespacho"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    pedidos_normalizados = list(
        dict.fromkeys(
            str(pedido).strip()
            for pedido in pedidos_urgentes
            if str(pedido).strip()
        )
    )

    tabla_base = (
        tabla_base[
            tabla_base["Pedido"].isin(
                pedidos_normalizados
            )
        ]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .copy()
    )

    pedidos_encontrados = set(
        tabla_base["Pedido"].tolist()
    )

    pedidos_sin_codigo = set(
        tabla_base.loc[
            tabla_base["CodigoDespacho"].eq(""),
            "Pedido",
        ].tolist()
    )

    pedidos_no_encontrados = {
        pedido
        for pedido in pedidos_normalizados
        if pedido not in pedidos_encontrados
    }

    pedidos_con_error = sorted(
        pedidos_sin_codigo
        | pedidos_no_encontrados
    )

    tabla_valida = tabla_base[
        tabla_base["CodigoDespacho"].ne("")
    ].copy()

    pedidos_validos = (
        tabla_valida["Pedido"]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    codigos_despacho = (
        tabla_valida["CodigoDespacho"]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    if not pedidos_validos or not codigos_despacho:
        return None, pedidos_con_error

    orden = {
        "codigo_despacho": codigos_despacho[0],
        "codigos_despacho": codigos_despacho,
        "usar_filtro_codigo_despacho": (
            len(codigos_despacho) == 1
        ),
        "despacho": "URGENTES",
        "pedidos": pedidos_validos,
        "identificador": "URGENTES",
    }

    return orden, pedidos_con_error


orden_urgentes = None
pedidos_urgentes_sin_codigo = []

if pedidos_urgentes_digip:
    try:
        (
            orden_urgentes,
            pedidos_urgentes_sin_codigo,
        ) = construir_orden_urgentes(
            pedidos_urgentes=pedidos_urgentes_digip,
            tabla_pedidos=tabla_operativa,
        )

    except Exception as error:
        st.error(
            "No se pudo preparar la agrupación "
            "de pedidos urgentes."
        )
        logger.exception("Error controlado en el módulo de Consultas Comerciales.")


st.markdown("---")
urg_titulo, urg_historial = st.columns(
    [5, 1.25], vertical_alignment="center"
)
with urg_titulo:
    st.markdown("### 🚨 Gestión de urgencias")
with urg_historial:
    if st.button(
        "Ocultar histórico"
        if st.session_state["mostrar_historico_urgencias"]
        else "📚 Histórico",
        use_container_width=True,
        key="btn_historico_urgencias",
    ):
        st.session_state["mostrar_historico_urgencias"] = (
            not st.session_state["mostrar_historico_urgencias"]
        )
        st.rerun()

if st.session_state["mostrar_historico_urgencias"]:
    mostrar_historial_urgencias(urgencias_totales)
    st.divider()

urg_col_1, urg_col_2, urg_col_3 = st.columns(
    [1.2, 4.2, 1.6],
    vertical_alignment="center",
)

with urg_col_1:
    st.metric(
        "Pendientes",
        len(pedidos_urgentes_digip),
    )

with urg_col_2:
    if pedidos_urgentes_digip:
        st.caption(
            "**Pedidos pendientes:** "
            + " | ".join(
                pedidos_urgentes_digip
            )
        )

        if orden_urgentes:
            cantidad_codigos = len(
                orden_urgentes["codigos_despacho"]
            )

            if cantidad_codigos == 1:
                st.caption(
                    "Se enviará una orden al worker con destino "
                    "**URGENTES**, filtrando por un código de despacho."
                )
            else:
                st.caption(
                    f"Se enviará una única orden al worker con "
                    f"{cantidad_codigos} códigos de despacho. "
                    "DIGIP buscará los pedidos por número sin "
                    "filtrar la grilla."
                )

    else:
        st.caption(
            "No hay pedidos urgentes pendientes de agrupar."
        )

with urg_col_3:
    enviar_urgentes_worker = st.button(
        "🚀 Enviar al worker",
        type="primary",
        use_container_width=True,
        disabled=(
            orden_urgentes is None
            or not puede_ejecutar_urgencias
        ),
        key="btn_enviar_urgentes_worker",
    )


if pedidos_urgentes_sin_codigo:
    st.warning(
        "Los siguientes pedidos no tienen un Código de "
        "Despacho válido y no podrán ejecutarse: "
        + " | ".join(
            pedidos_urgentes_sin_codigo
        )
    )


if not puede_ejecutar_urgencias:
    st.caption(
        "La ejecución está habilitada únicamente para "
        "Administración, Logística y Supervisión."
    )


if enviar_urgentes_worker and orden_urgentes:

    pedidos_a_procesar = orden_urgentes["pedidos"]

    usuario_solicitud = (
        st.session_state.get("usuario")
        or st.session_state.get("nombre_usuario")
        or "Usuario app"
    )

    try:
        # Primero se crea la orden. Solo después se cambia el
        # estado de las urgencias a Procesando. Así, si Google
        # Sheets falla, las urgencias no quedan bloqueadas.
        orden_id = crear_orden_agrupacion(
            camioneta="URGENTES",
            codigo_despacho=(
                orden_urgentes["codigo_despacho"]
            ),
            codigos_despacho=(
                orden_urgentes["codigos_despacho"]
            ),
            usar_filtro_codigo_despacho=(
                orden_urgentes[
                    "usar_filtro_codigo_despacho"
                ]
            ),
            pedidos=pedidos_a_procesar,
            usuario=usuario_solicitud,
        )

        marcar_lote_procesando(
            pedidos_a_procesar
        )

        st.session_state[
            "orden_worker_urgentes"
        ] = orden_id

        st.session_state[
            "pedidos_orden_worker_urgentes"
        ] = pedidos_a_procesar

        st.session_state.pop(
            "resultado_worker_urgentes_aplicado",
            None,
        )

        st.success(
            f"Orden {orden_id} enviada al worker de la PC."
        )

    except Exception as error:
        st.error(
            "No se pudo enviar la agrupación de urgencias "
            "al worker."
        )

        logger.exception("Error controlado en el módulo de Consultas Comerciales.")


orden_worker_urgentes = st.session_state.get(
    "orden_worker_urgentes",
    "",
)

if orden_worker_urgentes:
    orden_actual = obtener_orden(
        orden_worker_urgentes
    )

    if orden_actual:
        estado_orden = str(
            orden_actual.get("Estado", "")
        ).strip().upper()

        etapa_orden = str(
            orden_actual.get("Etapa", "")
        ).strip()

        mensaje_orden = str(
            orden_actual.get("Mensaje", "")
        ).strip()

        pedidos_orden = st.session_state.get(
            "pedidos_orden_worker_urgentes",
            [],
        )

        if estado_orden == "COMPLETADA":
            clave_aplicada = (
                "resultado_worker_urgentes_aplicado"
            )

            if (
                st.session_state.get(clave_aplicada)
                != orden_worker_urgentes
            ):
                marcar_lote_exitoso(
                    pedidos_orden,
                    mensaje=(
                        "Pedidos agrupados correctamente "
                        "en el despacho URGENTES."
                    ),
                )

                st.session_state[
                    clave_aplicada
                ] = orden_worker_urgentes

            st.success(
                f"✅ {len(pedidos_orden)} pedidos fueron "
                "agrupados correctamente en URGENTES."
            )

        elif estado_orden == "ERROR":
            clave_aplicada = (
                "resultado_worker_urgentes_aplicado"
            )

            if (
                st.session_state.get(clave_aplicada)
                != orden_worker_urgentes
            ):
                marcar_lote_error(
                    pedidos_orden,
                    mensaje=mensaje_orden,
                )

                st.session_state[
                    clave_aplicada
                ] = orden_worker_urgentes

            st.error(
                "La agrupación URGENTES terminó con error: "
                f"{mensaje_orden}"
            )

        elif estado_orden == "EN_PROCESO":
            st.info(
                f"⚙️ Worker ejecutando URGENTES — "
                f"{etapa_orden}: {mensaje_orden}"
            )

        else:
            st.warning(
                "🕒 La orden URGENTES está pendiente de ser "
                "tomada por el worker."
            )

        if estado_orden not in {
            "COMPLETADA",
            "ERROR",
            "CANCELADA",
        }:
            st.button(
                "🔄 Consultar estado del worker",
                key="btn_consultar_worker_urgentes",
                help=(
                    "Actualiza únicamente cuando necesitás "
                    "consultar el avance."
                ),
            )

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
        use_container_width=True,
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

    tabla_solicitudes_superior = (
        solicitudes_resumen[
            [
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
        ]
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
        use_container_width=True,
        hide_index=True,
        height=min(
            420,
            85 + len(tabla_solicitudes_superior) * 35,
        ),
        on_select="rerun",
        selection_mode="single-row",
        key="tabla_solicitudes_pendientes_consultas",
        column_config={
            "ID": None,
            "Pedido": st.column_config.TextColumn(
                "Pedido",
                width="small",
            ),
            "Cliente": st.column_config.TextColumn(
                "Cliente",
                width="medium",
            ),
            "Tipo": st.column_config.TextColumn(
                "Tipo",
                width="medium",
            ),
            "Prioridad": st.column_config.TextColumn(
                "Prioridad",
                width="small",
            ),
            "Detalle": st.column_config.TextColumn(
                "Detalle",
                width="large",
            ),
            "Solicitado por": st.column_config.TextColumn(
                "Solicitado por",
                width="small",
            ),
            "Fecha": st.column_config.TextColumn(
                "Fecha",
                width="small",
            ),
            "Estado": st.column_config.TextColumn(
                "Estado",
                width="small",
            ),
            "Responsable": st.column_config.TextColumn(
                "Responsable",
                width="small",
            ),
            "Respuesta Logística": st.column_config.TextColumn(
                "Respuesta Logística",
                width="large",
            ),
        },
    )

    filas_solicitudes_superior = (
        evento_solicitudes_superior.selection.rows
        if evento_solicitudes_superior is not None
        else []
    )

    accion_solicitud_1, accion_solicitud_2 = st.columns(
        [4, 1],
        vertical_alignment="center",
    )

    with accion_solicitud_1:
        if filas_solicitudes_superior:
            seleccion_superior = (
                tabla_solicitudes_superior.iloc[
                    filas_solicitudes_superior[0]
                ]
            )

            st.caption(
                f"Seleccionada: pedido "
                f"**{seleccion_superior['Pedido']}** · "
                f"{seleccion_superior['Tipo']} · "
                f"{seleccion_superior['Estado']}"
            )
        else:
            st.caption(
                "Seleccioná una solicitud para ver, editar "
                "o eliminar su gestión."
            )

    with accion_solicitud_2:
        gestionar_solicitud_superior = st.button(
            "📩 Gestionar",
            type="primary",
            use_container_width=True,
            disabled=not bool(
                filas_solicitudes_superior
            ),
            key="btn_gestionar_solicitud_consultas",
        )

    if (
        gestionar_solicitud_superior
        and filas_solicitudes_superior
    ):
        indice_superior = filas_solicitudes_superior[0]

        solicitud_superior = (
            solicitudes_resumen.iloc[
                indice_superior
            ]
        )

        abrir_detalle_solicitud(
            solicitud_superior
        )


st.markdown("---")


# ==========================================================
# CENTRO DE GESTIÓN DEL PEDIDO
# ==========================================================

@st.dialog(
    "📦 Centro de gestión del pedido",
    width="large",
)
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
        st.markdown("##### 📋 Nueva gestión")

        tipo_gestion = st.selectbox(
            "Tipo de gestión",
            options=[
                "Urgencia",
                "Solicitud",
            ],
            key=f"tipo_gestion_{fila['Pedido']}",
        )

        if tipo_gestion == "Urgencia":
            # Regla operativa:
            # los pedidos mayores a 2 m³ no se registran como urgencia.
            # Se convierten automáticamente en una solicitud de prioridad.
            try:
                volumen_pedido = float(fila.get("M3", 0) or 0)
            except (TypeError, ValueError):
                volumen_pedido = 0.0

            limite_urgencia_m3 = 2.0
            convertir_a_solicitud = (
                volumen_pedido > limite_urgencia_m3
            )

            if convertir_a_solicitud:
                st.warning(
                    f"Este pedido tiene {volumen_pedido:.3f} m³ y "
                    f"supera el límite de {limite_urgencia_m3:.2f} m³ "
                    "para urgencias. La gestión se registrará "
                    "automáticamente como SOLICITUD de prioridad."
                )

            urgencia_pedido = pd.DataFrame()

            if not urgencias_activas.empty:
                urgencia_pedido = urgencias_activas[
                    urgencias_activas["Pedido"]
                    .astype(str)
                    .eq(str(fila["Pedido"]))
                ].copy()

            if not urgencia_pedido.empty:
                ultima_urgencia = urgencia_pedido.iloc[0]

                st.warning(
                    "Este pedido ya está marcado como urgente."
                )

                st.caption(
                    f"**Motivo:** "
                    f"{ultima_urgencia.get('Motivo', '') or 'Sin detalle'}  \\n"
                    f"**Solicitado por:** "
                    f"{ultima_urgencia.get('UsuarioSolicitante', '') or 'Sin dato'}  \\n"
                    f"**Fecha:** "
                    f"{ultima_urgencia.get('FechaSolicitud', '') or 'Sin dato'}  \\n"
                    f"**Estado DIGIP:** "
                    f"{ultima_urgencia.get('EstadoEjecucionDIGIP', '') or 'Pendiente'}"
                )

            else:
                with st.form(
                    f"form_urgencia_{fila['Pedido']}",
                    clear_on_submit=True,
                ):
                    motivo_urgencia = st.selectbox(
                        "Motivo de la urgencia",
                        options=[
                            "Entrega comprometida",
                            "Cliente prioritario",
                            "Pedido demorado",
                            "Retiro coordinado",
                            "Otro",
                        ],
                    )

                    fecha_requerida = st.date_input(
                        "Fecha requerida",
                        value=None,
                    )

                    observacion_urgencia = st.text_area(
                        "Observación",
                        placeholder=(
                            "Detalle breve para Logística..."
                        ),
                        height=90,
                    )

                    texto_boton_urgencia = (
                        "📩 Registrar como solicitud"
                        if convertir_a_solicitud
                        else "🚨 Marcar como urgente"
                    )

                    confirmar_urgencia = st.form_submit_button(
                        texto_boton_urgencia,
                        type="primary",
                        use_container_width=True,
                    )

                if confirmar_urgencia:
                    usuario_solicitante = (
                        st.session_state.get("usuario")
                        or st.session_state.get("nombre_usuario")
                        or "Usuario no identificado"
                    )

                    try:
                        fecha_requerida_texto = (
                            fecha_requerida.strftime("%Y-%m-%d")
                            if fecha_requerida is not None
                            else "Sin fecha requerida"
                        )

                        if convertir_a_solicitud:
                            descripcion_convertida = (
                                "Solicitud convertida automáticamente desde "
                                "URGENCIA por superar el límite operativo "
                                f"de {limite_urgencia_m3:.2f} m³.\n"
                                f"Volumen del pedido: {volumen_pedido:.3f} m³.\n"
                                f"Motivo informado: {motivo_urgencia}.\n"
                                f"Fecha requerida: {fecha_requerida_texto}.\n"
                                f"Observación: "
                                f"{observacion_urgencia.strip() or 'Sin observación'}"
                            )

                            resultado_solicitud = guardar_solicitud(
                                pedido=fila["Pedido"],
                                cliente=fila["Cliente"],
                                tipo_solicitud="Solicitud de prioridad",
                                descripcion=descripcion_convertida,
                                usuario_solicitante=usuario_solicitante,
                                prioridad="Alta",
                            )

                            st.success(
                                "El pedido supera los 2 m³. "
                                "La gestión se registró como SOLICITUD "
                                "de prioridad."
                            )

                            st.toast(
                                "Urgencia convertida en solicitud.",
                                icon="📩",
                            )

                        else:
                            resultado_urgencia = guardar_urgencia(
                                pedido=fila["Pedido"],
                                cliente=fila["Cliente"],
                                motivo=motivo_urgencia,
                                usuario_solicitante=usuario_solicitante,
                                fecha_requerida=(
                                    fecha_requerida.strftime("%Y-%m-%d")
                                    if fecha_requerida is not None
                                    else ""
                                ),
                                observacion=observacion_urgencia,
                            )

                            st.success(
                                resultado_urgencia["mensaje"]
                            )

                            st.toast(
                                "Pedido agregado a la cola de urgencias.",
                                icon="🚨",
                            )

                        st.rerun()

                    except Exception as error:
                        st.error(
                            "No se pudo registrar la gestión."
                        )
                        logger.exception("Error controlado en el módulo de Consultas Comerciales.")

        elif tipo_gestion == "Solicitud":
            st.caption(
                "Las solicitudes existentes se administran "
                "desde la tabla superior «Solicitudes pendientes»."
            )

            with st.form(
                f"form_solicitud_{fila['Pedido']}",
                clear_on_submit=True,
            ):
                tipo_solicitud = st.selectbox(
                    "Tipo de solicitud",
                    options=[
                        "Solicitud de prioridad",
                        "Retiro en Depósito",
                        "Revisión de Stock",
                        "Postergar Entrega",
                        "Cancelación",
                        "Otros",
                    ],
                )

                prioridad_solicitud = st.selectbox(
                    "Prioridad",
                    options=[
                        "Normal",
                        "Alta",
                        "Baja",
                    ],
                )

                descripcion_solicitud = st.text_area(
                    "Descripción",
                    placeholder=(
                        "Detalle de la solicitud para Logística..."
                    ),
                    height=110,
                )

                confirmar_solicitud = st.form_submit_button(
                    "📩 Registrar solicitud",
                    type="primary",
                    use_container_width=True,
                )

            if confirmar_solicitud:
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
                    )

                    st.success(
                        resultado_solicitud["mensaje"]
                    )

                    st.toast(
                        "Solicitud agregada a la gestión comercial.",
                        icon="📩",
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        "No se pudo registrar la solicitud."
                    )
                    logger.exception("Error controlado en el módulo de Consultas Comerciales.")

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
# BÚSQUEDA Y RESUMEN DE LA TABLA
# ==========================================================

st.markdown("---")
st.subheader("🔎 Buscar y consultar pedidos")

filtros_actuales = st.session_state[
    "consultas_filtros_aplicados"
]

with st.form(
    "form_busqueda_consultas",
    clear_on_submit=False,
):

    buscar_col, aplicar_col, limpiar_col = st.columns(
        [5, 1.15, 1.15],
        vertical_alignment="bottom",
    )

    with buscar_col:
        busqueda_form = st.text_input(
            "Pedido o cliente",
            value=filtros_actuales["busqueda"],
            placeholder=(
                "Ingresá un pedido, código de cliente "
                "o nombre del cliente"
            ),
            label_visibility="collapsed",
        )

    with aplicar_col:
        aplicar = st.form_submit_button(
            "🔎 Buscar",
            type="primary",
            use_container_width=True,
        )

    with limpiar_col:
        limpiar = st.form_submit_button(
            "🧹 Quitar filtro",
            use_container_width=True,
        )


if aplicar:
    st.session_state["consultas_filtros_aplicados"] = {
        "busqueda": busqueda_form.strip(),
    }

    st.session_state["consultas_detalle_abierto"] = False
    st.session_state["consultas_pedido_detalle"] = ""
    st.session_state["consulta_pedido_seleccionado"] = ""

    st.rerun()


if limpiar:
    st.session_state["consultas_filtros_aplicados"] = {
        "busqueda": "",
    }

    st.session_state["consultas_detalle_abierto"] = False
    st.session_state["consultas_pedido_detalle"] = ""
    st.session_state["consulta_pedido_seleccionado"] = ""

    st.rerun()


# ==========================================================
# TABLA GENERAL DE PEDIDOS
# ==========================================================

st.subheader("Tabla general de pedidos")

# ==========================================================
# TABLA GENERAL A ANCHO COMPLETO
# ==========================================================

COLUMN_CONFIG = {
    "Pedido": st.column_config.TextColumn(
        "Pedido",
        width="small",
    ),
    "Fecha": st.column_config.DateColumn(
        "Fecha",
        format="DD/MM/YYYY",
        width="small",
    ),
    "FechaTransmisionERP": st.column_config.DateColumn(
        "Fecha transmisión",
        format="DD/MM/YYYY",
        width="small",
    ),
    "HoraTransmisionERP": st.column_config.TextColumn(
        "Hora",
        width="small",
    ),
    "NroEnvioERP": st.column_config.TextColumn(
        "N.º envío",
        width="small",
    ),
    "ClienteCodigo": st.column_config.TextColumn(
        "Código",
        width="small",
    ),
    "Cliente": st.column_config.TextColumn(
        "Cliente",
        width="large",
    ),
    "Unidades": st.column_config.NumberColumn(
        "Unidades",
        format="%d",
        width="small",
    ),
    "M3": st.column_config.NumberColumn(
        "M³",
        format="%.3f",
        width="small",
    ),
    "Familias": st.column_config.TextColumn(
        "Familias",
        width="medium",
    ),
    "Planificacion": st.column_config.TextColumn(
        "Planificación",
        width="small",
    ),
    "Despacho": st.column_config.TextColumn(
        "Despacho",
        width="medium",
    ),
    "Urgencia": st.column_config.TextColumn(
        "Urgencia",
        width="small",
    ),
    "Solicitud": st.column_config.TextColumn(
        "Solicitud",
        width="small",
    ),
    "CategoriaComercial": st.column_config.TextColumn(
        "Estado",
        width="medium",
    ),
    "EstadoComercial": st.column_config.TextColumn(
        "Situación actual",
        width="large",
    ),
    "Contenedor": st.column_config.TextColumn(
        "Carro / Contenedor",
        width="medium",
    ),
}


tabla_visible_pedidos = (
    tabla_filtrada
    .reset_index(drop=True)
    .copy()
)

st.caption(
    (
        f"{len(tabla_visible_pedidos):,} pedidos visibles "
        f"de {len(tabla_consultas):,}"
    ).replace(",", ".")
)

pedido_seleccionado_guardado = st.session_state.get(
    "consulta_pedido_seleccionado",
    "",
)

cabecera_tabla_1, cabecera_tabla_2 = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with cabecera_tabla_1:
    if pedido_seleccionado_guardado:
        coincidencia_seleccionada = tabla_visible_pedidos[
            tabla_visible_pedidos["Pedido"]
            .astype(str)
            .eq(str(pedido_seleccionado_guardado))
        ]

        if not coincidencia_seleccionada.empty:
            fila_seleccionada_guardada = (
                coincidencia_seleccionada.iloc[0]
            )

            st.caption(
                f"Seleccionado: pedido "
                f"**{fila_seleccionada_guardada['Pedido']}** · "
                f"{fila_seleccionada_guardada['Cliente']}"
            )
        else:
            st.caption(
                "Seleccioná un pedido de la tabla para abrir "
                "su centro de gestión."
            )
            pedido_seleccionado_guardado = ""
    else:
        st.caption(
            "Seleccioná un pedido de la tabla para abrir "
            "su centro de gestión."
        )

with cabecera_tabla_2:
    abrir_detalle = st.button(
        "👁 Ver detalle",
        type="primary",
        use_container_width=True,
        disabled=not bool(pedido_seleccionado_guardado),
        key="btn_detalle_tabla_consultas",
    )

if abrir_detalle and pedido_seleccionado_guardado:
    abrir_detalle_pedido(
        str(pedido_seleccionado_guardado).strip()
    )

evento_tabla_pedidos = st.dataframe(
    tabla_visible_pedidos,
    use_container_width=True,
    hide_index=True,
    height=1000,
    column_config=COLUMN_CONFIG,
    on_select="rerun",
    selection_mode="single-row",
    key="tabla_general_consultas",
)

filas_pedido_seleccionadas = (
    evento_tabla_pedidos.selection.rows
    if evento_tabla_pedidos is not None
    else []
)

if filas_pedido_seleccionadas:
    pedido_seleccionado = (
        tabla_visible_pedidos.iloc[
            filas_pedido_seleccionadas[0]
        ]
    )

    pedido_nuevo = str(
        pedido_seleccionado["Pedido"]
    ).strip()

    if (
        st.session_state.get(
            "consulta_pedido_seleccionado",
            "",
        )
        != pedido_nuevo
    ):
        st.session_state[
            "consulta_pedido_seleccionado"
        ] = pedido_nuevo
        st.rerun()

