# pages/08_Consultas.py

from __future__ import annotations

import pandas as pd
import streamlit as st

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
)

from utils.gestion_urgencias_digip import (
    obtener_urgencias_pendientes_digip,
    obtener_pedidos_pendientes_digip,
    marcar_lote_procesando,
    marcar_lote_exitoso,
    marcar_lote_error,
)

from Automatizacion.ejecutar_agrupaciones import (
    ejecutar_agrupaciones,
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
                st.exception(error)

    elif modo_accion == "Eliminar":

        st.warning(
            "Esta acción elimina definitivamente la solicitud."
        )

        confirmar = st.checkbox(
            "Confirmo que quiero eliminar esta solicitud.",
            key=f"confirmar_eliminar_{solicitud_id}",
        )

        eliminar = st.button(
            "🗑️ Eliminar solicitud",
            type="primary",
            use_container_width=True,
            disabled=not confirmar,
            key=f"btn_eliminar_{solicitud_id}",
        )

        if eliminar:

            try:
                resultado = eliminar_solicitud(
                    solicitud_id
                )

                st.success(resultado["mensaje"])
                st.toast(
                    "Solicitud eliminada.",
                    icon="🗑️",
                )
                st.rerun()

            except Exception as error:
                st.error(
                    "No se pudo eliminar la solicitud."
                )
                st.exception(error)


# ==========================================================
# PERMISOS Y CONFIGURACIÓN
# ==========================================================

requerir_roles(
    "admin",
    "gerencia",
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
    col_actualizar,
) = st.columns(
    [5.2, 1.35, 1],
    vertical_alignment="center",
)

with col_info:
    st.caption(
        "Buscá por número de pedido, código o nombre del cliente."
    )

with col_reclamo:
    espacio_boton_reclamo = st.empty()

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
    st.exception(error)
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

solicitudes_totales = leer_solicitudes()
urgencias_totales = leer_urgencias()
reclamos_totales = leer_reclamos()

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


def construir_agrupaciones_urgentes(
    pedidos_urgentes: list[str],
    tabla_pedidos: pd.DataFrame,
) -> tuple[list[dict], list[str]]:
    """
    Separa los pedidos urgentes por Código de Despacho.

    DIGIP utiliza el código para filtrar los pedidos antes de
    seleccionarlos. Todas las agrupaciones tienen como destino
    final el despacho URGENTES.
    """

    if not pedidos_urgentes:
        return [], []

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
            "No se pueden preparar las urgencias. "
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

    tabla_base = (
        tabla_base[
            tabla_base["Pedido"].isin(
                pedidos_urgentes
            )
        ]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .copy()
    )

    pedidos_sin_codigo = (
        tabla_base.loc[
            tabla_base["CodigoDespacho"].eq(""),
            "Pedido",
        ]
        .astype(str)
        .tolist()
    )

    pedidos_encontrados = set(
        tabla_base["Pedido"].tolist()
    )

    pedidos_no_encontrados = [
        pedido
        for pedido in pedidos_urgentes
        if pedido not in pedidos_encontrados
    ]

    pedidos_con_error = sorted(
        set(
            pedidos_sin_codigo
            + pedidos_no_encontrados
        )
    )

    tabla_valida = tabla_base[
        tabla_base["CodigoDespacho"].ne("")
    ].copy()

    agrupaciones = []

    for codigo_despacho, bloque in (
        tabla_valida.groupby(
            "CodigoDespacho",
            sort=True,
        )
    ):
        pedidos_grupo = (
            bloque["Pedido"]
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

        agrupaciones.append(
            {
                "codigo_despacho": codigo_despacho,
                "despacho": "URGENTES",
                "pedidos": pedidos_grupo,
                "identificador": (
                    f"URGENTES - {codigo_despacho}"
                ),
            }
        )

    return agrupaciones, pedidos_con_error


agrupaciones_urgentes = []
pedidos_urgentes_sin_codigo = []

if pedidos_urgentes_digip:
    try:
        (
            agrupaciones_urgentes,
            pedidos_urgentes_sin_codigo,
        ) = construir_agrupaciones_urgentes(
            pedidos_urgentes=pedidos_urgentes_digip,
            tabla_pedidos=tabla_operativa,
        )

    except Exception as error:
        st.error(
            "No se pudo preparar la agrupación "
            "de pedidos urgentes."
        )
        st.exception(error)


st.markdown("---")
st.markdown("### 🚨 Gestión de urgencias")

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

        st.caption(
            f"Se ejecutarán "
            f"{len(agrupaciones_urgentes)} "
            f"agrupaciones internas por código, "
            "todas con destino **URGENTES**."
        )

    else:
        st.caption(
            "No hay pedidos urgentes pendientes de agrupar."
        )

with urg_col_3:
    abrir_confirmacion_urgentes = st.button(
        "🚀 Agrupar en DIGIP",
        type="primary",
        use_container_width=True,
        disabled=(
            not agrupaciones_urgentes
            or not puede_ejecutar_urgencias
        ),
        key="btn_abrir_urgentes_digip",
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


if abrir_confirmacion_urgentes:
    st.session_state[
        "confirmar_agrupacion_urgentes"
    ] = True


if st.session_state.get(
    "confirmar_agrupacion_urgentes",
    False,
):
    with st.container(border=True):
        st.warning(
            f"Se procesarán "
            f"{sum(len(item['pedidos']) for item in agrupaciones_urgentes)} "
            "pedidos con destino URGENTES."
        )

        resumen_confirmacion = pd.DataFrame(
            [
                {
                    "Código despacho": item[
                        "codigo_despacho"
                    ],
                    "Destino": item["despacho"],
                    "Cantidad pedidos": len(
                        item["pedidos"]
                    ),
                    "Pedidos": " | ".join(
                        item["pedidos"]
                    ),
                }
                for item in agrupaciones_urgentes
            ]
        )

        st.dataframe(
            resumen_confirmacion,
            use_container_width=True,
            hide_index=True,
        )

        confirmar_col, cancelar_col = st.columns(2)

        with confirmar_col:
            confirmar_ejecucion_urgentes = st.button(
                "Confirmar agrupación",
                type="primary",
                use_container_width=True,
                key="btn_confirmar_urgentes_digip",
            )

        with cancelar_col:
            cancelar_ejecucion_urgentes = st.button(
                "Cancelar",
                use_container_width=True,
                key="btn_cancelar_urgentes_digip",
            )

    if cancelar_ejecucion_urgentes:
        st.session_state[
            "confirmar_agrupacion_urgentes"
        ] = False

        st.rerun()

    if confirmar_ejecucion_urgentes:
        pedidos_a_procesar = [
            pedido
            for agrupacion in agrupaciones_urgentes
            for pedido in agrupacion["pedidos"]
        ]

        marcar_lote_procesando(
            pedidos_a_procesar
        )

        contenedor_estado = st.empty()
        registro_estados: list[str] = []

        def mostrar_estado(
            etapa: str,
            mensaje: str,
        ) -> None:
            registro_estados.append(
                f"{etapa.upper()}: {mensaje}"
            )

            contenedor_estado.info(
                registro_estados[-1]
            )

        try:
            with st.spinner(
                "Ejecutando agrupaciones urgentes en DIGIP..."
            ):
                resultado_ejecucion = ejecutar_agrupaciones(
                    agrupaciones=agrupaciones_urgentes,
                    headless=True,
                    detener_ante_error=True,
                    callback=mostrar_estado,
                )

            pedidos_exitosos = []
            pedidos_con_error = []
            mensajes_error = []

            for resultado_agrupacion in (
                resultado_ejecucion.resultados
            ):
                if resultado_agrupacion.exito:
                    pedidos_exitosos.extend(
                        resultado_agrupacion
                        .pedidos_seleccionados
                    )
                else:
                    pedidos_con_error.extend(
                        resultado_agrupacion
                        .pedidos_solicitados
                    )

                    mensajes_error.append(
                        f"{resultado_agrupacion.identificador}: "
                        f"{resultado_agrupacion.mensaje}"
                    )

            pedidos_exitosos = sorted(
                set(pedidos_exitosos)
            )

            pedidos_con_error = sorted(
                set(pedidos_con_error)
                - set(pedidos_exitosos)
            )

            pedidos_no_procesados = sorted(
                set(pedidos_a_procesar)
                - set(pedidos_exitosos)
                - set(pedidos_con_error)
            )

            pedidos_con_error = sorted(
                set(
                    pedidos_con_error
                    + pedidos_no_procesados
                )
            )

            if pedidos_exitosos:
                marcar_lote_exitoso(
                    pedidos_exitosos,
                    mensaje=(
                        "Pedidos agrupados correctamente "
                        "en el despacho URGENTES."
                    ),
                )

            if pedidos_con_error:
                mensaje_error = (
                    " | ".join(mensajes_error)
                    or (
                        "La ejecución se detuvo antes de "
                        "procesar estos pedidos."
                    )
                )

                marcar_lote_error(
                    pedidos_con_error,
                    mensaje=mensaje_error,
                )

            st.session_state[
                "confirmar_agrupacion_urgentes"
            ] = False

            if pedidos_exitosos:
                st.success(
                    f"{len(pedidos_exitosos)} pedidos "
                    "fueron agrupados en URGENTES."
                )

            if pedidos_con_error:
                st.error(
                    f"{len(pedidos_con_error)} pedidos "
                    "quedaron pendientes por error."
                )

            st.rerun()

        except Exception as error:
            marcar_lote_error(
                pedidos_a_procesar,
                mensaje=str(error),
            )

            st.session_state[
                "confirmar_agrupacion_urgentes"
            ] = False

            st.error(
                "No se pudo completar la agrupación "
                "de urgencias en DIGIP."
            )

            st.exception(error)


st.markdown("---")
st.markdown("### 📩 Solicitudes pendientes")

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
                        st.exception(error)

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
                    st.exception(error)

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

