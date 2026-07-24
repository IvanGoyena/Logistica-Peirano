import streamlit as st

from utils.autenticacion import requerir_roles


requerir_roles(
    "admin",
    "gerencia"
)


from config import *

from utils.leer_datos import (
    leer_archivo
)

from utils.leer_gestion_consultas import (
    obtener_solicitudes_abiertas,
    obtener_urgencias_activas,
    obtener_anulaciones_pendientes,
    obtener_reclamos_abiertos,
)

from utils.gestion_consultas import (
    actualizar_solicitud,
    finalizar_solicitud_automaticamente,
)

from models.detalle import (
    construir_tabla_detalle,
    construir_resumen_pedidos
)

from models.pedidos import (
    construir_tabla_pedidos,
)

from models.pendiente import (
    construir_tabla_pendientes
)

from models.transmisiones import (
    construir_tabla_transmisiones
)

from models.clientes import (
    construir_tabla_clientes
)

from models.expresos import (
    construir_tabla_expresos
)

from models.planificacion import (
    construir_resumen_clientes_planificacion,
    asignar_camionetas,
    asignar_camioneta_a_pedidos,
)

from Automatizacion.ejecutar_agrupaciones import (
    ejecutar_agrupacion,
)

import pandas as pd
import re

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(

    page_title="Pedidos",

    page_icon="📦",

    layout="wide"

)

# =====================================================
# CARGA CONTROLADA DE DATOS
# =====================================================

@st.cache_data(
    show_spinner="Cargando datos operativos..."
)
def cargar_datos_operativos():
    """
    Lee los archivos una sola vez y conserva los DataFrames
    durante los reruns normales de Streamlit.

    La caché se limpia únicamente desde el botón
    'Actualizar datos'.
    """

    return {
        "pedidos": leer_archivo(
            CARPETA_DATOS,
            "Pedidos DIGIP",
            cache=False
        ),
        "detalle": leer_archivo(
            CARPETA_DATOS,
            "Detalle Pendientes",
            cache=False
        ),
        "articulos": leer_archivo(
            CARPETA_DATOS,
            "Maestro Articulo",
            cache=True
        ),
        "clientes": leer_archivo(
            CARPETA_DATOS,
            "Maestro Clientes",
            cache=True
        ),
        
        "pendientes_erp": leer_archivo(
            CARPETA_DATOS,
            "Pedidos Pendientes",
            cache=False
        ),
        "transmisiones": leer_archivo(
            CARPETA_DATOS,
            "Pedidos Transmicion",
            cache=False
        ),
        "expresos": leer_archivo(
            CARPETA_DATOS,
            "Datos Expresos",
            cache=True
        ),
        "volumetria": leer_archivo(
            CARPETA_DATOS,
            "Maestro Volumetria",
            cache=True
        ),
    }


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

    cargar_datos_operativos.clear()

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


datos_operativos = cargar_datos_operativos()

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
# CONSTRUIR TABLA PRINCIAL
# =====================================================

tabla = construir_tabla_pedidos(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes,
    df_volumetria
)

# =====================================================
# CONSTRUIR TABLAS SATÉLITES
# =====================================================

tabla_transmisiones = construir_tabla_transmisiones(
    df_transmisiones
)

tabla_expresos = construir_tabla_expresos(
    df_expresos
)

tabla_clientes = construir_tabla_clientes(
    df_clientes
)

tabla_pendientes_erp = construir_tabla_pendientes(
    df_pendientes_erp
)


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
        "Reclamo": obtener_reclamos_abiertos(),
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

tabla["DiaEntrega"] = frecuencia_entrega
tabla["ZonaExpreso"] = zona_expreso

# =====================================================
# REGLA DEFINITIVA DE PLANIFICACIÓN
# =====================================================
#
# La frecuencia de entrega semanal tiene prioridad.
#
# Ejemplo:
# FrecuenciaEntrega = JUEVES
# CodigoExpreso = 05010001
# ZonaExpreso = CABA SUR
#
# Resultado:
# Planificacion = JUEVES
#
# Solo cuando el pedido NO tiene un día semanal asignado
# se utiliza la zona del expreso como planificación.
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

tabla["Planificacion"] = frecuencia_entrega.where(
    es_entrega_semanal,
    zona_expreso.where(
        zona_expreso.ne(""),
        frecuencia_entrega
    )
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
    utc=True
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


# =====================================================
# AVISO Y GESTIÓN DE SOLICITUDES COMERCIALES
# =====================================================

ESTADOS_SOLICITUD = [
    "Pendiente",
    "En revisión",
    "En curso",
    "Finalizada",
]


@st.dialog(
    "📩 Gestionar solicitud comercial",
    width="large",
)
def abrir_gestion_solicitud(
    solicitud_id: str,
) -> None:
    """
    Abre una ventana modal para gestionar una solicitud sin
    ocupar espacio permanente en la pantalla principal.
    """

    coincidencia = solicitudes_abiertas.loc[
        solicitudes_abiertas["SolicitudID"]
        .astype(str)
        .eq(str(solicitud_id))
    ].copy()

    if coincidencia.empty:
        st.error("No se encontró la solicitud seleccionada.")
        return

    solicitud = coincidencia.iloc[0]

    pedido = str(
        solicitud.get("Pedido", "")
    ).strip()

    cliente = str(
        solicitud.get("Cliente", "")
    ).strip()

    tipo_solicitud = str(
        solicitud.get("TipoSolicitud", "")
    ).strip()

    prioridad = str(
        solicitud.get("Prioridad", "")
    ).strip()

    descripcion = str(
        solicitud.get("Descripcion", "")
    ).strip()

    solicitado_por = str(
        solicitud.get("UsuarioSolicitante", "")
    ).strip()

    fecha_solicitud = str(
        solicitud.get("FechaSolicitudVisible", "")
    ).strip()

    responsable_actual = str(
        solicitud.get("Responsable", "")
    ).strip()

    unidades_pedido = int(
        pd.to_numeric(
            solicitud.get("TotalUnidades", 0),
            errors="coerce",
        )
        if pd.notna(
            pd.to_numeric(
                solicitud.get("TotalUnidades", 0),
                errors="coerce",
            )
        )
        else 0
    )

    volumen_pedido = float(
        pd.to_numeric(
            solicitud.get("TotalM3", 0),
            errors="coerce",
        )
        if pd.notna(
            pd.to_numeric(
                solicitud.get("TotalM3", 0),
                errors="coerce",
            )
        )
        else 0
    )

    estado_actual = str(
        solicitud.get(
            "EstadoSolicitud",
            "Pendiente",
        )
    ).strip()

    if estado_actual not in ESTADOS_SOLICITUD:
        estado_actual = "Pendiente"

    prioridad_icono = {
        "ALTA": "🔴",
        "NORMAL": "🟡",
        "BAJA": "🟢",
    }.get(
        prioridad.upper(),
        "⚪",
    )

    cabecera_1, cabecera_2, cabecera_3, cabecera_4 = st.columns(
        [0.9, 2.1, 0.9, 0.9],
        vertical_alignment="center",
    )

    with cabecera_1:
        st.metric(
            "Pedido",
            pedido or "Sin dato",
        )

    with cabecera_2:
        st.markdown(f"**{cliente or 'Cliente sin identificar'}**")
        st.caption(
            f"{tipo_solicitud or 'Solicitud'} · "
            f"{prioridad_icono} {prioridad or 'Sin prioridad'}"
        )

    with cabecera_3:
        st.metric(
            "Unidades",
            f"{unidades_pedido:,}".replace(",", "."),
        )

    with cabecera_4:
        volumen_formateado = (
            f"{volumen_pedido:,.3f} m³"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

        st.metric(
            "Volumen",
            volumen_formateado,
        )

    st.caption(
        f"**Estado actual:** {estado_actual}"
    )

    st.info(
        descripcion or "La solicitud no tiene detalle.",
        icon="📝",
    )

    datos_col_1, datos_col_2, datos_col_3 = st.columns(3)

    with datos_col_1:
        st.caption(
            f"**Solicitado por**  \n"
            f"{solicitado_por or 'Sin dato'}"
        )

    with datos_col_2:
        st.caption(
            f"**Fecha**  \n"
            f"{fecha_solicitud or 'Sin dato'}"
        )

    with datos_col_3:
        st.caption(
            f"**Responsable actual**  \n"
            f"{responsable_actual or 'Sin asignar'}"
        )

    st.divider()

    with st.form(
        f"form_gestion_solicitud_{solicitud_id}",
        clear_on_submit=False,
    ):

        formulario_1, formulario_2 = st.columns(
            [1, 2],
        )

        with formulario_1:

            nuevo_estado_solicitud = st.selectbox(
                "Estado",
                options=ESTADOS_SOLICITUD,
                index=ESTADOS_SOLICITUD.index(
                    estado_actual
                ),
            )

        with formulario_2:

            observacion_logistica = st.text_area(
                "Observación / respuesta",
                value=str(
                    solicitud.get(
                        "Respuesta",
                        "",
                    )
                ),
                placeholder=(
                    "Detalle de la revisión o acción "
                    "realizada por Logística..."
                ),
                height=110,
            )

        guardar_estado_solicitud = (
            st.form_submit_button(
                "💾 Guardar actualización",
                type="primary",
                width="stretch",
            )
        )

    if guardar_estado_solicitud:

        usuario_logistica = (
            st.session_state.get("usuario")
            or st.session_state.get("nombre_usuario")
            or "Logística"
        )

        try:

            resultado_actualizacion = actualizar_solicitud(
                solicitud_id=solicitud_id,
                estado_solicitud=nuevo_estado_solicitud,
                responsable=usuario_logistica,
                respuesta=observacion_logistica,
            )

            st.success(
                resultado_actualizacion["mensaje"]
            )

            st.toast(
                "Solicitud actualizada.",
                icon="✅",
            )

            st.rerun()

        except Exception as error:

            st.error(
                "No se pudo actualizar la solicitud."
            )

            st.exception(error)


if solicitudes_abiertas.empty:

    st.success(
        "No hay solicitudes comerciales pendientes.",
        icon="✅",
    )

else:

    total_solicitudes_abiertas = len(solicitudes_abiertas)
    pedidos_con_solicitud = solicitudes_abiertas["Pedido"].nunique()

    prioridad_alta = int(
        solicitudes_abiertas["Prioridad"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("ALTA")
        .sum()
    )

    cantidad_cancelaciones = int(
        solicitudes_abiertas["TipoSolicitud"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({"CANCELACIÓN", "CANCELACION"})
        .sum()
    )

    st.warning(
        (
            f"Hay {total_solicitudes_abiertas} solicitudes "
            f"comerciales pendientes sobre "
            f"{pedidos_con_solicitud} pedidos."
        ),
        icon="📩",
    )

    with st.expander(
        (
            f"📩 Solicitudes comerciales "
            f"({total_solicitudes_abiertas})"
        ),
        expanded=False,
    ):

        (
            resumen_col_1,
            resumen_col_2,
            resumen_col_3,
            resumen_col_4,
        ) = st.columns(4)

        resumen_col_1.metric(
            "Abiertas",
            total_solicitudes_abiertas,
        )

        resumen_col_2.metric(
            "Pedidos",
            pedidos_con_solicitud,
        )

        resumen_col_3.metric(
            "Prioridad alta",
            prioridad_alta,
        )

        resumen_col_4.metric(
            "Cancelaciones",
            cantidad_cancelaciones,
            help=(
                "Solicitudes abiertas de Cancelación que "
                "requieren revisión prioritaria."
            ),
        )

        solicitudes_abiertas_ordenadas = (
            solicitudes_abiertas
            .assign(
                EsCancelacion=(
                    solicitudes_abiertas["TipoSolicitud"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .isin({"CANCELACIÓN", "CANCELACION"})
                    .astype(int)
                ),
                EsPrioridadAlta=(
                    solicitudes_abiertas["Prioridad"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.upper()
                    .eq("ALTA")
                    .astype(int)
                ),
            )
            .sort_values(
                by=[
                    "EsCancelacion",
                    "EsPrioridadAlta",
                    "FechaSolicitudOrden",
                ],
                ascending=[False, False, False],
                na_position="last",
            )
            .reset_index(drop=True)
        )

        tabla_solicitudes_visible = (
            solicitudes_abiertas_ordenadas[
                [
                    "SolicitudID",
                    "Pedido",
                    "Cliente",
                    "TipoSolicitud",
                    "Prioridad",
                    "TotalUnidades",
                    "TotalM3",
                    "Descripcion",
                    "FechaSolicitudVisible",
                    "EstadoSolicitud",
                    "Responsable",
                ]
            ]
            .rename(
                columns={
                    "SolicitudID": "ID",
                    "TipoSolicitud": "Tipo",
                    "Descripcion": "Detalle",
                    "FechaSolicitudVisible": "Fecha",
                    "EstadoSolicitud": "Estado",
                }
            )
            .reset_index(drop=True)
        )

        evento_solicitudes = st.dataframe(
            tabla_solicitudes_visible,
            width="stretch",
            hide_index=True,
            height=min(
                340,
                85 + len(tabla_solicitudes_visible) * 35,
            ),
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_solicitudes_comerciales",
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
                    "Solicitud",
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
            },
        )

        filas_seleccionadas = (
            evento_solicitudes.selection.rows
            if evento_solicitudes is not None
            else []
        )

        accion_col_1, accion_col_2 = st.columns(
            [4, 1],
            vertical_alignment="center",
        )

        with accion_col_1:

            if filas_seleccionadas:

                fila_seleccionada = filas_seleccionadas[0]

                solicitud_seleccionada = (
                    tabla_solicitudes_visible.iloc[
                        fila_seleccionada
                    ]
                )

                st.caption(
                    f"Seleccionada: pedido "
                    f"**{solicitud_seleccionada['Pedido']}** · "
                    f"{solicitud_seleccionada['Tipo']}"
                )

            else:

                st.caption(
                    "Seleccioná una fila para gestionar la solicitud."
                )

        with accion_col_2:

            gestionar_solicitud = st.button(
                "Gestionar",
                icon="📩",
                type="primary",
                width="stretch",
                disabled=not bool(filas_seleccionadas),
                key="btn_gestionar_solicitud_seleccionada",
            )

        if gestionar_solicitud and filas_seleccionadas:

            indice_seleccionado = filas_seleccionadas[0]

            solicitud_id_seleccionada = str(
                tabla_solicitudes_visible.iloc[
                    indice_seleccionado
                ]["ID"]
            )

            abrir_gestion_solicitud(
                solicitud_id_seleccionada
            )


st.markdown("---")


# =====================================================
# CONTENEDOR DE KPIs
# Se crea acá para que aparezca arriba de los filtros
# =====================================================

contenedor_kpis = st.container()

st.markdown("---")

# =====================================================
# OPCIONES DISPONIBLES PARA LOS FILTROS
# =====================================================

opciones_estado = sorted(
    tabla["Estado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_preparacion = sorted(
    tabla["PreparacionEstado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_planificacion = sorted(
    tabla["Planificacion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_despacho = sorted(
    tabla["DespachoDescripcion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

fecha_minima = tabla["Fecha"].min()
fecha_maxima = tabla["Fecha"].max()


# =====================================================
# ESTADO INICIAL DE LOS FILTROS
# =====================================================

if "filtros_pedidos" not in st.session_state:

    st.session_state["filtros_pedidos"] = {
        "estados": [],
        "preparaciones": [],
        "planificaciones": [],
        "despachos": [],
        "fecha_desde": (
            fecha_minima.date()
            if pd.notna(fecha_minima)
            else None
        ),
        "fecha_hasta": (
            fecha_maxima.date()
            if pd.notna(fecha_maxima)
            else None
        ),
        "busqueda": ""
    }
# Ajustar las fechas guardadas al rango actual de los datos
if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

    fecha_minima_actual = fecha_minima.date()
    fecha_maxima_actual = fecha_maxima.date()

    fecha_desde_guardada = st.session_state[
        "filtros_pedidos"
    ].get("fecha_desde")

    fecha_hasta_guardada = st.session_state[
        "filtros_pedidos"
    ].get("fecha_hasta")

    if (
        fecha_desde_guardada is None
        or fecha_desde_guardada < fecha_minima_actual
        or fecha_desde_guardada > fecha_maxima_actual
    ):
        st.session_state[
            "filtros_pedidos"
        ]["fecha_desde"] = fecha_minima_actual

    if (
        fecha_hasta_guardada is None
        or fecha_hasta_guardada > fecha_maxima_actual
        or fecha_hasta_guardada < fecha_minima_actual
    ):
        st.session_state[
            "filtros_pedidos"
        ]["fecha_hasta"] = fecha_maxima_actual

filtros_aplicados = st.session_state["filtros_pedidos"]


# =====================================================
# APLICAR LOS FILTROS GUARDADOS
# =====================================================

tabla_filtrada = tabla.copy()

if filtros_aplicados["estados"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Estado"].isin(
            filtros_aplicados["estados"]
        )
    ]

if filtros_aplicados["preparaciones"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["PreparacionEstado"].isin(
            filtros_aplicados["preparaciones"]
        )
    ]

if filtros_aplicados["planificaciones"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Planificacion"].isin(
            filtros_aplicados["planificaciones"]
        )
    ]

if filtros_aplicados["despachos"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["DespachoDescripcion"].isin(
            filtros_aplicados["despachos"]
        )
    ]

fecha_desde = filtros_aplicados["fecha_desde"]
fecha_hasta = filtros_aplicados["fecha_hasta"]

if fecha_desde is not None:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Fecha"].ge(
            pd.Timestamp(fecha_desde)
        )
    ]

if fecha_hasta is not None:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Fecha"].lt(
            pd.Timestamp(fecha_hasta)
            + pd.Timedelta(days=1)
        )
    ]

texto_busqueda = filtros_aplicados["busqueda"]

if texto_busqueda:

    mascara_busqueda = (
        tabla_filtrada["Pedido"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteCodigo"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteDescripcion"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
    )

    tabla_filtrada = tabla_filtrada[
        mascara_busqueda
    ]


# =====================================================
# BASE ÚNICA PARA KPIs
# =====================================================

tabla_kpis = (
    tabla_filtrada
    .drop_duplicates(
        subset=["Pedido"],
        keep="first"
    )
    .copy()
)


# =====================================================
# CÁLCULO DE KPIs
# =====================================================

total_pedidos = tabla_kpis["Pedido"].nunique()

total_unidades = int(
    tabla_kpis["TotalUnidades"].sum()
)

total_volumetria = float(
    tabla_kpis["TotalM3"].sum()
)

total_importe = float(
    tabla_kpis["ImporteERP"].sum()
)

pedidos_en_preparacion = int(
    tabla_kpis["PreparacionEstado"]
    .fillna("")
    .astype(str)
    .str.strip()
    .ne("")
    .sum()
)


# =====================================================
# MOSTRAR KPIs ARRIBA DE LOS FILTROS
# =====================================================

with contenedor_kpis:

    st.subheader("📊 Resumen Operativo")

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

    with kpi1:

        st.metric(
            "📦 Pedidos",
            f"{total_pedidos:,}".replace(",", ".")
        )

    with kpi2:

        st.metric(
            "🔢 Unidades",
            f"{total_unidades:,}".replace(",", ".")
        )

    with kpi3:

        st.metric(
            "📐 Volumen total",
            f"{total_volumetria:,.3f} m³"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    with kpi4:

        st.metric(
            "🛒 Con preparación",
            f"{pedidos_en_preparacion:,}"
            .replace(",", ".")
        )

    with kpi5:

        st.metric(
            "📩 Solicitudes",
            f"{len(solicitudes_abiertas):,}"
            .replace(",", ".")
        )

    with kpi6:

        st.metric(
            "💰 Importe",
            f"$ {total_importe:,.0f}"
            .replace(",", ".")
        )



# =====================================================
# AGRUPADORES REALES DE DIGIP
# =====================================================

AGRUPADORES_DIGIP = {
    "LUNES": [
        "CAMIONETA LUN 1",
        "CAMIONETA LUN 2",
        "CAMIONETA LUN 3",
        "CAMIONETA LUN 4",
    ],
    "MARTES": [
        "CAMIONETA MAR 1",
        "CAMIONETA MAR 2",
        "CAMIONETA MAR 3",
    ],
    "MIERCOLES": [
        "CAMIONETA MIE 1",
        "CAMIONETA MIE 2",
        "CAMIONETA MIE 3",
    ],
    "JUEVES": [
        "CAMIONETA JUE 1",
        "CAMIONETA JUE 2",
        "CAMIONETA JUE 3",
    ],
    "VIERNES": [
        "CAMIONETA VIE 1",
        "CAMIONETA VIE 2",
        "CAMIONETA VIE 3",
    ],
    "DIARIOS": [
        "CAMIONETA DIARIOS 1",
    ],
    "EXPRESOS": [
        "CAMIONETA EXP 1",
        "CAMIONETA EXP 2",
        "CAMIONETA EXP 3",
        "CAMIONETA EXP 4",
        "CAMIONETA EXP 5",
        "CAMIONETA EXP 6",
    ],
}


PLANIFICACIONES_SEMANALES = {
    "LUNES",
    "MARTES",
    "MIERCOLES",
    "JUEVES",
    "VIERNES",
    "DIARIOS",
}


def normalizar_planificacion(
    valor: object
) -> str:
    return (
        str(valor)
        .strip()
        .upper()
    )


def obtener_pool_agrupador(
    planificacion: object
) -> str:
    """
    Las planificaciones semanales usan su propio pool.
    Todas las demás planificaciones operativas se consideran
    expresos: CABA SUR, CABA SUR II, CABA NORTE, etc.
    """

    planificacion_normalizada = (
        normalizar_planificacion(
            planificacion
        )
    )

    if (
        planificacion_normalizada
        in PLANIFICACIONES_SEMANALES
    ):
        return planificacion_normalizada

    return "EXPRESOS"


def obtener_agrupadores_ocupados(
    tabla_pedidos: pd.DataFrame
) -> set[str]:
    """
    Considera ocupado un agrupador cuando existe al menos
    un pedido con PreparacionID no vacío y su descripción
    coincide con alguno de los agrupadores configurados.
    """

    columnas_requeridas = {
        "PreparacionID",
        "DespachoDescripcion",
    }

    if not columnas_requeridas.issubset(
        tabla_pedidos.columns
    ):
        return set()

    nombres_validos = {
        nombre
        for agrupadores in (
            AGRUPADORES_DIGIP.values()
        )
        for nombre in agrupadores
    }

    preparacion_activa = (
        tabla_pedidos["PreparacionID"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    despachos = (
        tabla_pedidos.loc[
            preparacion_activa,
            "DespachoDescripcion"
        ]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    return {
        despacho
        for despacho in despachos.tolist()
        if despacho in nombres_validos
    }


def asignar_agrupadores_disponibles(
    asignacion: pd.DataFrame,
    agrupadores_ocupados: set[str],
) -> pd.DataFrame:
    """
    Asigna nombres reales de agrupadores DIGIP.

    - LUNES usa CAMIONETA LUN N.
    - MARTES usa CAMIONETA MAR N.
    - etc.
    - CABA SUR, CABA NORTE y demás zonas comparten
      CAMIONETA EXP N.
    """

    if asignacion.empty:
        return asignacion.copy()

    resultado = asignacion.copy()

    resultado["PoolAgrupador"] = (
        resultado["Planificacion"]
        .apply(obtener_pool_agrupador)
    )

    vehiculos_logicos = (
        resultado[
            [
                "PoolAgrupador",
                "Planificacion",
                "NumeroCamioneta",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            by=[
                "PoolAgrupador",
                "Planificacion",
                "NumeroCamioneta",
            ]
        )
        .reset_index(drop=True)
    )

    asignaciones_reales = []

    for pool, bloque in (
        vehiculos_logicos.groupby(
            "PoolAgrupador",
            sort=False
        )
    ):
        disponibles = [
            nombre
            for nombre in AGRUPADORES_DIGIP[
                pool
            ]
            if nombre not in agrupadores_ocupados
        ]

        cantidad_necesaria = len(bloque)

        cantidad_faltante = max(
            cantidad_necesaria - len(disponibles),
            0
        )

        agrupadores_nuevos = []

        if cantidad_faltante > 0:

            numeros_existentes = []

            for nombre in AGRUPADORES_DIGIP[pool]:

                coincidencia = re.search(
                    r"(\d+)$",
                    str(nombre).strip()
                )

                if coincidencia:
                    numeros_existentes.append(
                        int(coincidencia.group(1))
                    )

            siguiente_numero = (
                max(numeros_existentes) + 1
                if numeros_existentes
                else 1
            )

            for numero in range(
                siguiente_numero,
                siguiente_numero
                + cantidad_faltante
            ):

                if pool == "EXPRESOS":
                    nombre_nuevo = (
                        f"CAMIONETA EXP {numero}"
                    )

                elif pool == "LUNES":
                    nombre_nuevo = (
                        f"CAMIONETA LUN {numero}"
                    )

                elif pool == "MARTES":
                    nombre_nuevo = (
                        f"CAMIONETA MAR {numero}"
                    )

                elif pool == "MIERCOLES":
                    nombre_nuevo = (
                        f"CAMIONETA MIE {numero}"
                    )

                elif pool == "JUEVES":
                    nombre_nuevo = (
                        f"CAMIONETA JUE {numero}"
                    )

                elif pool == "VIERNES":
                    nombre_nuevo = (
                        f"CAMIONETA VIE {numero}"
                    )

                elif pool == "DIARIOS":
                    nombre_nuevo = (
                        f"CAMIONETA DIARIOS {numero}"
                    )

                else:
                    nombre_nuevo = (
                        f"CAMIONETA {pool} {numero}"
                    )

                agrupadores_nuevos.append(
                    nombre_nuevo
                )

            disponibles.extend(
                agrupadores_nuevos
            )

        bloque = bloque.copy()

        bloque["DespachoDIGIP"] = (
            disponibles[:cantidad_necesaria]
        )

        bloque["AgrupadorNuevo"] = (
            bloque["DespachoDIGIP"].isin(
                agrupadores_nuevos
            )
        )

        asignaciones_reales.append(bloque)

    mapa_agrupadores = pd.concat(
        asignaciones_reales,
        ignore_index=True
    )

    resultado = resultado.merge(
        mapa_agrupadores,
        on=[
            "PoolAgrupador",
            "Planificacion",
            "NumeroCamioneta",
        ],
        how="left",
        validate="many_to_one",
    )

    resultado[
        "NumeroCamionetaLogica"
    ] = resultado["NumeroCamioneta"]

    # El número visible se extrae del nombre real.
    resultado["NumeroCamioneta"] = (
        resultado["DespachoDIGIP"]
        .str.extract(
            r"(\d+)$",
            expand=False
        )
        .astype(int)
    )

    resultado["Camioneta"] = (
        resultado["Planificacion"]
        .astype(str)
        .str.strip()
        + " - "
        + resultado["DespachoDIGIP"]
    )

    return resultado


# =====================================================
# PLANIFICACIÓN DE CAMIONETAS
# =====================================================

st.markdown("---")

st.subheader("🚚 Planificación de Camionetas")

st.caption(
    "Asignación propuesta respetando planificación, "
    "antigüedad y cliente completo."
)

if pedidos_bloqueados_gestion:

    detalle_bloqueos = " · ".join(
        f"{tipo}: {len(pedidos)}"
        for tipo, pedidos in pedidos_por_tipo_gestion.items()
        if pedidos
    )

    st.warning(
        (
            f"Hay {len(pedidos_bloqueados_gestion)} pedidos "
            "bloqueados para planificación porque tienen una "
            "gestión comercial abierta. "
            f"{detalle_bloqueos}"
        ),
        icon="🔒",
    )


# =====================================================
# FORMULARIO DE CONFIGURACIÓN
# =====================================================

with st.form(
    key="formulario_planificacion_camionetas",
    clear_on_submit=False
):

    col_plan1, col_plan2, col_plan3 = st.columns(
        [1, 1, 1]
    )

    with col_plan1:

        capacidad_camioneta = st.number_input(
            "Capacidad por camioneta (m³)",
            min_value=0.1,
            value=12.0,
            step=0.5,
            format="%.1f"
        )

    with col_plan2:

        opciones_planificacion_camionetas = sorted(
            tabla_filtrada["Planificacion"]
            .dropna()
            .astype(str)
            .loc[
                lambda serie:
                serie.str.strip().ne("")
            ]
            .unique()
            .tolist()
        )

        planificaciones_camionetas = st.multiselect(
            "Planificaciones a procesar",
            options=opciones_planificacion_camionetas,
            default=[],
            placeholder="Seleccionar planificaciones..."
        )

    with col_plan3:

        incluir_preparados = st.checkbox(
            "Incluir pedidos con preparación",
            value=True
        )

    generar_planificacion = st.form_submit_button(
        "🚚 Generar propuesta de camionetas",
        type="primary",
        width="stretch"
    )


# =====================================================
# GENERAR PLANIFICACIÓN
# =====================================================

if generar_planificacion:

    if not planificaciones_camionetas:
        st.warning(
            "Seleccioná al menos una planificación para generar "
            "la propuesta de camionetas."
        )
        st.stop()

    base_planificacion = tabla_filtrada.copy()

    # Los pedidos con cualquier gestión comercial abierta
    # requieren revisión y no pueden asignarse a camionetas.
    if pedidos_bloqueados_gestion:

        base_planificacion["Pedido"] = (
            base_planificacion["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

        base_planificacion = base_planificacion[
            ~base_planificacion["Pedido"].isin(
                pedidos_bloqueados_gestion
            )
        ].copy()

    if planificaciones_camionetas:

        base_planificacion = base_planificacion[
            base_planificacion["Planificacion"].isin(
                planificaciones_camionetas
            )
        ].copy()

    if not incluir_preparados:

        base_planificacion = base_planificacion[
            base_planificacion["PreparacionID"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("")
        ].copy()

    if base_planificacion.empty:

        st.warning(
            "No quedaron pedidos disponibles para planificar. "
            "Todos los pedidos seleccionados tienen una gestión "
            "comercial abierta o fueron excluidos por los filtros."
        )

        st.stop()

    resumen_clientes = (
        construir_resumen_clientes_planificacion(
            base_planificacion
        )
    )

    asignacion_logica = asignar_camionetas(
        resumen_clientes,
        capacidad_camioneta
    )

    agrupadores_ocupados = (
        obtener_agrupadores_ocupados(
            tabla
        )
    )

    try:

        asignacion_camionetas = (
            asignar_agrupadores_disponibles(
                asignacion=asignacion_logica,
                agrupadores_ocupados=(
                    agrupadores_ocupados
                ),
            )
        )

    except ValueError as error:

        st.error(str(error))
        st.stop()

    agrupadores_a_crear = []

    if (
        not asignacion_camionetas.empty
        and "AgrupadorNuevo"
        in asignacion_camionetas.columns
    ):

        agrupadores_a_crear = sorted(
            asignacion_camionetas.loc[
                asignacion_camionetas[
                    "AgrupadorNuevo"
                ],
                "DespachoDIGIP"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

    st.session_state[
        "agrupadores_a_crear"
    ] = agrupadores_a_crear

    pedidos_planificados = asignar_camioneta_a_pedidos(
        base_planificacion,
        asignacion_camionetas
    )

    st.session_state[
        "asignacion_camionetas"
    ] = asignacion_camionetas

    st.session_state[
        "pedidos_planificados"
    ] = pedidos_planificados

    st.session_state[
        "capacidad_camioneta"
    ] = capacidad_camioneta

    st.session_state[
        "agrupadores_ocupados"
    ] = sorted(
        agrupadores_ocupados
    )


# =====================================================
# VALIDAR VERSIÓN DE LA PLANIFICACIÓN GUARDADA
# =====================================================

COLUMNAS_PLANIFICACION_ACTUAL = {
    "DespachoDIGIP",
    "PoolAgrupador",
}

asignacion_guardada = st.session_state.get(
    "asignacion_camionetas"
)

if (
    isinstance(
        asignacion_guardada,
        pd.DataFrame
    )
    and not asignacion_guardada.empty
    and not COLUMNAS_PLANIFICACION_ACTUAL.issubset(
        asignacion_guardada.columns
    )
):

    # La propuesta fue creada con una versión anterior
    # del módulo y no contiene los agrupadores reales.
    claves_planificacion_anterior = [
        "asignacion_camionetas",
        "pedidos_planificados",
        "capacidad_camioneta",
        "agrupadores_ocupados",
    ]

    for clave in claves_planificacion_anterior:
        st.session_state.pop(
            clave,
            None
        )

    claves_ejecucion_anterior = [
        clave
        for clave in list(
            st.session_state.keys()
        )
        if str(clave).startswith(
            "resultado_digip_"
        )
    ]

    for clave in claves_ejecucion_anterior:
        st.session_state.pop(
            clave,
            None
        )

    st.warning(
        "La planificación guardada pertenecía a una versión "
        "anterior. Fue eliminada para incorporar los nombres "
        "reales de los agrupadores DIGIP. Generá nuevamente "
        "la propuesta."
    )


# =====================================================
# MOSTRAR RESULTADO GUARDADO
# =====================================================

if (
    "asignacion_camionetas"
    in st.session_state
):

    asignacion_camionetas = st.session_state[
        "asignacion_camionetas"
    ]

    if asignacion_camionetas.empty:

        st.warning(
            "No existen pedidos disponibles para generar "
            "la planificación."
        )

    else:

        agrupadores_a_crear = (
            st.session_state.get(
                "agrupadores_a_crear",
                []
            )
        )

        if agrupadores_a_crear:

            st.warning(
                "La propuesta utiliza agrupadores que todavía "
                "no existen en DIGIP: "
                + ", ".join(agrupadores_a_crear)
                + ". Podés continuar con la planificación y "
                "crearlos antes de ejecutar."
            )

        capacidad_utilizada = st.session_state.get(
            "capacidad_camioneta",
            0
        )

        resumen_camionetas = (
            asignacion_camionetas[
                [
                    "Planificacion",
                    "NumeroCamioneta",
                    "Camioneta",
                    "DespachoDIGIP",
                    "PoolAgrupador",
                    "CapacidadM3",
                    "VolumenCamionetaM3",
                    "OcupacionCamionetaPct",
                    "DisponibleM3",
                    "ClientesCamioneta",
                    "PedidosCamioneta",
                    "UnidadesCamioneta",
                    "EstadoCapacidad",
                ]
            ]
            .drop_duplicates(
                subset=[
                    "Planificacion",
                    "NumeroCamioneta",
                ]
            )
            .sort_values(
                by=[
                    "Planificacion",
                    "NumeroCamioneta",
                ]
            )
        )

        total_camionetas = len(
            resumen_camionetas
        )

        total_clientes_planificados = (
            asignacion_camionetas[
                "ClienteCodigo"
            ].nunique()
        )

        total_pedidos_planificados = int(
            asignacion_camionetas[
                "CantidadPedidos"
            ].sum()
        )

        volumen_planificado = float(
            asignacion_camionetas[
                "TotalM3"
            ].sum()
        )

        ocupacion_promedio = float(
            resumen_camionetas[
                "OcupacionCamionetaPct"
            ].mean()
        )

        # -------------------------------------------------
        # DISPONIBILIDAD DE AGRUPADORES
        # -------------------------------------------------

        agrupadores_ocupados_guardados = set(
            st.session_state.get(
                "agrupadores_ocupados",
                []
            )
        )

        agrupadores_asignados = sorted(
            resumen_camionetas[
                "DespachoDIGIP"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        todos_los_agrupadores = [
            nombre
            for lista in AGRUPADORES_DIGIP.values()
            for nombre in lista
        ]

        agrupadores_libres_restantes = [
            nombre
            for nombre in todos_los_agrupadores
            if (
                nombre
                not in agrupadores_ocupados_guardados
                and nombre
                not in set(
                    agrupadores_asignados
                )
            )
        ]

        with st.expander(
            "🚦 Disponibilidad de agrupadores DIGIP",
            expanded=False
        ):

            disp_col1, disp_col2, disp_col3 = (
                st.columns(3)
            )

            with disp_col1:
                st.metric(
                    "Ocupados",
                    len(
                        agrupadores_ocupados_guardados
                    )
                )

                st.caption(
                    ", ".join(
                        sorted(
                            agrupadores_ocupados_guardados
                        )
                    )
                    or "Ninguno"
                )

            with disp_col2:
                st.metric(
                    "Asignados a la propuesta",
                    len(agrupadores_asignados)
                )

                st.caption(
                    ", ".join(
                        agrupadores_asignados
                    )
                    or "Ninguno"
                )

            with disp_col3:
                st.metric(
                    "Libres restantes",
                    len(
                        agrupadores_libres_restantes
                    )
                )

                st.caption(
                    ", ".join(
                        agrupadores_libres_restantes
                    )
                    or "Ninguno"
                )

        # -------------------------------------------------
        # KPIs DE PLANIFICACIÓN
        # -------------------------------------------------

        plan_kpi1, plan_kpi2, plan_kpi3, plan_kpi4, plan_kpi5 = (
            st.columns(5)
        )

        with plan_kpi1:

            st.metric(
                "🚚 Camionetas",
                total_camionetas
            )

        with plan_kpi2:

            st.metric(
                "👥 Clientes",
                total_clientes_planificados
            )

        with plan_kpi3:

            st.metric(
                "📦 Pedidos",
                total_pedidos_planificados
            )

        with plan_kpi4:

            st.metric(
                "📐 Volumen",
                f"{volumen_planificado:,.3f} m³"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        with plan_kpi5:

            st.metric(
                "📊 Ocupación promedio",
                f"{ocupacion_promedio:.1f}%"
            )

        # -------------------------------------------------
        # RESUMEN DE CAMIONETAS
        # -------------------------------------------------

        st.markdown("#### Resumen de cargas")

        st.dataframe(
            resumen_camionetas,
            width="stretch",
            hide_index=True,
            column_config={

                "CapacidadM3": (
                    st.column_config.NumberColumn(
                        "Capacidad m³",
                        format="%.2f"
                    )
                ),

                "VolumenCamionetaM3": (
                    st.column_config.NumberColumn(
                        "Volumen asignado",
                        format="%.3f"
                    )
                ),

                "OcupacionCamionetaPct": (
                    st.column_config.ProgressColumn(
                        "Ocupación",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    )
                ),

                "DisponibleM3": (
                    st.column_config.NumberColumn(
                        "Disponible m³",
                        format="%.3f"
                    )
                ),
            }
        )

        # -------------------------------------------------
        # EJECUCIÓN DIGIP
        # -------------------------------------------------

        st.markdown("#### 🚀 Ejecución DIGIP")

        st.caption(
            "Revisá el resumen y ejecutá únicamente la "
            "camioneta que quieras crear en DIGIP."
        )

        pedidos_planificados = st.session_state.get(
            "pedidos_planificados",
            pd.DataFrame()
        )

        # Estilo compacto del panel
        st.markdown(
            """
            <style>
            div[data-testid="stHorizontalBlock"] {
                gap: 0.65rem;
            }

            div[data-testid="stButton"] > button {
                min-height: 2.15rem;
                padding-top: 0.25rem;
                padding-bottom: 0.25rem;
            }

            div[data-testid="stAlert"] {
                padding-top: 0.45rem;
                padding-bottom: 0.45rem;
                min-height: 2.15rem;
            }

            .digip-fila {
                padding: 0.18rem 0;
                line-height: 1.15;
            }

            .digip-nombre {
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .digip-numero {
                text-align: center;
                font-weight: 600;
            }

            .digip-volumen {
                text-align: right;
                white-space: nowrap;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        # Encabezados
        encabezado_1, encabezado_2, encabezado_3, \
            encabezado_4, encabezado_5 = st.columns(
                [3.2, 0.75, 1.05, 1.35, 1.15],
                vertical_alignment="center"
            )

        with encabezado_1:
            st.caption("**Camioneta**")

        with encabezado_2:
            st.caption("**Pedidos**")

        with encabezado_3:
            st.caption("**Volumen**")

        with encabezado_4:
            st.caption("**Estado DIGIP**")

        with encabezado_5:
            st.caption("**Acción**")

        st.divider()

        for _, fila_camioneta in resumen_camionetas.iterrows():

            planificacion_fila = str(
                fila_camioneta["Planificacion"]
            ).strip()

            numero_camioneta = int(
                fila_camioneta["NumeroCamioneta"]
            )

            nombre_camioneta = str(
                fila_camioneta["Camioneta"]
            ).strip()

            volumen_camioneta = float(
                fila_camioneta["VolumenCamionetaM3"]
            )

            clave_ejecucion = (
                f"{planificacion_fila}_"
                f"{numero_camioneta}"
            )

            pedidos_camioneta = (
                pedidos_planificados[
                    (
                        pedidos_planificados[
                            "Planificacion"
                        ].astype(str).str.strip()
                        == planificacion_fila
                    )
                    &
                    (
                        pd.to_numeric(
                            pedidos_planificados[
                                "NumeroCamioneta"
                            ],
                            errors="coerce"
                        )
                        == numero_camioneta
                    )
                ]
                .copy()
            )

            lista_pedidos = (
                pedidos_camioneta["Pedido"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True
                )
                .loc[lambda serie: serie.ne("")]
                .drop_duplicates()
                .tolist()
            )

            codigos_despacho = (
                pedidos_camioneta["CodigoDespacho"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True
                )
                .loc[lambda serie: serie.ne("")]
                .drop_duplicates()
                .tolist()
            )

            codigo_despacho = (
                codigos_despacho[0]
                if codigos_despacho
                else ""
            )

            usar_filtro_codigo_despacho = (
                len(codigos_despacho) == 1
            )

            despacho_digip = str(
                fila_camioneta[
                    "DespachoDIGIP"
                ]
            ).strip()

            ejecucion_valida = bool(
                lista_pedidos
            )

            estado_guardado = st.session_state.get(
                f"resultado_digip_{clave_ejecucion}"
            )

            fila_1, fila_2, fila_3, fila_4, fila_5 = (
                st.columns(
                    [3.2, 0.75, 1.05, 1.35, 1.15],
                    vertical_alignment="center"
                )
            )

            with fila_1:
                st.markdown(
                    (
                        '<div class="digip-fila digip-nombre">'
                        f'🚚 {nombre_camioneta}'
                        '</div>'
                    ),
                    unsafe_allow_html=True
                )

            with fila_2:
                st.markdown(
                    (
                        '<div class="digip-fila digip-numero">'
                        f'{len(lista_pedidos)}'
                        '</div>'
                    ),
                    unsafe_allow_html=True
                )

            with fila_3:
                volumen_formateado = (
                    f"{volumen_camioneta:,.3f} m³"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                st.markdown(
                    (
                        '<div class="digip-fila digip-volumen">'
                        f'{volumen_formateado}'
                        '</div>'
                    ),
                    unsafe_allow_html=True
                )

            with fila_4:

                if len(codigos_despacho) > 1:

                    st.info(
                        f"{len(codigos_despacho)} códigos",
                        icon="ℹ️"
                    )

                    st.caption(
                        "Códigos encontrados: "
                        + ", ".join(codigos_despacho)
                    )

                elif not codigo_despacho:
                    st.warning(
                        "Sin código",
                        icon="⚠️"
                    )

                elif estado_guardado:

                    if bool(
                        estado_guardado.get(
                            "exito",
                            False
                        )
                    ):
                        st.success(
                            "Ejecutada",
                            icon="✅"
                        )
                    else:
                        st.error(
                            "Error",
                            icon="❌"
                        )

                else:
                    st.info(
                        "Pendiente",
                        icon="⏳"
                    )

            with fila_5:

                texto_boton = (
                    "🔄 Reintentar"
                    if (
                        estado_guardado
                        and not bool(
                            estado_guardado.get(
                                "exito",
                                False
                            )
                        )
                    )
                    else (
                        "✅ Ejecutada"
                        if (
                            estado_guardado
                            and bool(
                                estado_guardado.get(
                                    "exito",
                                    False
                                )
                            )
                        )
                        else "🚀 Ejecutar"
                    )
                )

                ejecutar = st.button(
                    texto_boton,
                    key=(
                        f"ejecutar_digip_"
                        f"{clave_ejecucion}"
                    ),
                    width="stretch",
                    type="primary",
                    disabled=bool(
                        (not ejecucion_valida)
                        or (
                            bool(estado_guardado)
                            and bool(
                                estado_guardado.get(
                                    "exito",
                                    False
                                )
                            )
                        )
                    )
                )

            if estado_guardado and not bool(
                estado_guardado.get(
                    "exito",
                    False
                )
            ):
                with st.expander(
                    f"Ver error de {nombre_camioneta}"
                ):
                    st.error(
                        estado_guardado.get(
                            "mensaje",
                            "Error sin detalle."
                        )
                    )

            if ejecutar:

                import traceback

                mensajes_proceso = st.empty()

                def actualizar_estado(
                    etapa,
                    mensaje
                ):
                    mensajes_proceso.info(mensaje)

                mensajes_proceso.info(
                    "1/4 — La app recibió la orden de ejecución."
                )

                try:

                    mensajes_proceso.info(
                        "2/4 — Iniciando navegador y sesión DIGIP..."
                    )

                    with st.spinner(
                        f"Ejecutando {nombre_camioneta} en DIGIP..."
                    ):

                        resultado_digip = ejecutar_agrupacion(
                            {
                                "codigo_despacho": codigo_despacho,
                                "codigos_despacho": codigos_despacho,
                                "usar_filtro_codigo_despacho": (
                                    usar_filtro_codigo_despacho
                                ),
                                "despacho": despacho_digip,
                                "pedidos": lista_pedidos,
                                "identificador": nombre_camioneta,
                            },
                            headless=True,
                            callback=actualizar_estado,
                        )

                    mensajes_proceso.info(
                        "3/4 — DIGIP devolvió un resultado."
                    )

                    st.session_state[
                        f"resultado_digip_{clave_ejecucion}"
                    ] = resultado_digip.como_dict()

                    if resultado_digip.exito:

                        mensajes_proceso.success(
                            "4/4 — Agrupación creada correctamente."
                        )

                        st.success(
                            f"{nombre_camioneta} creada correctamente en DIGIP."
                        )

                    else:

                        mensajes_proceso.error(
                            "4/4 — DIGIP devolvió un error."
                        )

                        st.error(
                            "No se pudo crear la agrupación: "
                            f"{resultado_digip.mensaje}"
                        )

                except Exception as error:

                    detalle_error = traceback.format_exc()

                    st.session_state[
                        f"resultado_digip_{clave_ejecucion}"
                    ] = {
                        "exito": False,
                        "mensaje": str(error),
                        "detalle": detalle_error,
                    }

                    mensajes_proceso.error(
                        f"Error ejecutando DIGIP: {error}"
                    )

                    with st.expander(
                        "Ver detalle técnico del error",
                        expanded=True,
                    ):
                        st.code(detalle_error)

                st.session_state[
                    f"resultado_digip_"
                    f"{clave_ejecucion}"
                ] = resultado_digip.como_dict()

               

                if resultado_digip.exito:

                    st.success(
                        f"{nombre_camioneta} creada "
                        "correctamente en DIGIP."
                    )


                else:

                    st.error(
                        "No se pudo crear la agrupación: "
                        f"{resultado_digip.mensaje}"
                    )

            st.markdown(
                "<hr style='margin:0.35rem 0;'>",
                unsafe_allow_html=True
            )

        # -------------------------------------------------
        # DETALLE DE CLIENTES ASIGNADOS
        # -------------------------------------------------

        st.markdown("#### Detalle por cliente")

        columnas_detalle_planificacion = [
            "PrioridadCliente",
            "Camioneta",
            "FechaPrioridad",
            "DiasPendiente",
            "ClienteCodigo",
            "ClienteDescripcion",
            "CantidadPedidos",
            "Pedidos",
            "TotalUnidades",
            "TotalM3",
            "EstadoCapacidad",
        ]

        st.dataframe(
            asignacion_camionetas[
                columnas_detalle_planificacion
            ],
            width="stretch",
            hide_index=True,
            height=500,
            column_config={

                "FechaPrioridad": (
                    st.column_config.DateColumn(
                        "Pedido más antiguo",
                        format="DD/MM/YYYY"
                    )
                ),

                "TotalM3": (
                    st.column_config.NumberColumn(
                        "Volumen cliente",
                        format="%.3f"
                    )
                ),
            }
        )


# =====================================================
# FILTROS DE LA TABLA OPERATIVA
# Se muestran después de la planificación de camionetas.
# Los filtros guardados ya fueron aplicados previamente
# para calcular los KPIs y la propuesta de planificación.
# =====================================================

st.markdown("---")

st.subheader("🔎 Filtros de la Tabla Operativa")

with st.form(
    key="formulario_filtros_pedidos",
    clear_on_submit=False
):

    filtro1, filtro2, filtro3, filtro4 = st.columns(4)

    with filtro1:

        estados_form = st.multiselect(
            "Estado",
            options=opciones_estado,
            default=filtros_aplicados["estados"]
        )

    with filtro2:

        preparaciones_form = st.multiselect(
            "Estado preparación",
            options=opciones_preparacion,
            default=filtros_aplicados["preparaciones"]
        )

    with filtro3:

        planificaciones_form = st.multiselect(
            "Planificación",
            options=opciones_planificacion,
            default=filtros_aplicados["planificaciones"]
        )

    with filtro4:

        despachos_form = st.multiselect(
            "Despacho",
            options=opciones_despacho,
            default=filtros_aplicados["despachos"]
        )

    filtro5, filtro6 = st.columns([1, 2])

    with filtro5:

        if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

            rango_fechas_form = st.date_input(
                "Rango de fechas",
                value=(
                    filtros_aplicados["fecha_desde"],
                    filtros_aplicados["fecha_hasta"]
                ),
                min_value=fecha_minima.date(),
                max_value=fecha_maxima.date()
            )

        else:

            rango_fechas_form = None

    with filtro6:

        busqueda_form = st.text_input(
            "Buscar pedido o cliente",
            value=filtros_aplicados["busqueda"],
            placeholder=(
                "Número de pedido, código "
                "o nombre del cliente..."
            )
        )

        boton1, boton2 = st.columns(2)

        with boton1:

            aplicar_filtros = st.form_submit_button(
                "🔎 Aplicar filtros",
                width="stretch",
                type="primary"
            )

        with boton2:

            quitar_filtros = st.form_submit_button(
                "🧹 Quitar filtros",
                width="stretch"
            )


# =====================================================
# GUARDAR O QUITAR FILTROS
# =====================================================

if quitar_filtros:

    st.session_state["filtros_pedidos"] = {
        "estados": [],
        "preparaciones": [],
        "planificaciones": [],
        "despachos": [],
        "fecha_desde": (
            fecha_minima.date()
            if pd.notna(fecha_minima)
            else None
        ),
        "fecha_hasta": (
            fecha_maxima.date()
            if pd.notna(fecha_maxima)
            else None
        ),
        "busqueda": ""
    }

    st.rerun()


if aplicar_filtros:

    if (
        rango_fechas_form
        and len(rango_fechas_form) == 2
    ):

        fecha_desde_form = rango_fechas_form[0]
        fecha_hasta_form = rango_fechas_form[1]

    else:

        fecha_desde_form = None
        fecha_hasta_form = None

    st.session_state["filtros_pedidos"] = {
        "estados": estados_form,
        "preparaciones": preparaciones_form,
        "planificaciones": planificaciones_form,
        "despachos": despachos_form,
        "fecha_desde": fecha_desde_form,
        "fecha_hasta": fecha_hasta_form,
        "busqueda": busqueda_form.strip()
    }

    # La planificación y la tabla fueron calculadas antes de
    # renderizar este formulario. Se relanza la página para que
    # ambos bloques utilicen inmediatamente los nuevos filtros.
    st.rerun()


# =====================================================
# DESCARGA
# =====================================================

csv_tabla_operativa = (
    tabla_filtrada.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
        date_format="%d/%m/%Y"
    )
    .encode("utf-8-sig")
)

st.download_button(
    label="⬇️ Descargar tabla operativa",
    data=csv_tabla_operativa,
    file_name="Tabla_Operativa_Pedidos.csv",
    mime="text/csv",
    width="stretch"
)


# =====================================================
# TABLA
# =====================================================

st.subheader("📋 Tabla Operativa")

st.caption(
    f"{len(tabla_filtrada):,} registros visibles · "
    f"{tabla_filtrada['Pedido'].nunique():,} pedidos únicos · "
    f"{len(tabla):,} registros totales"
    .replace(",", ".")
)

st.dataframe(
    tabla_filtrada,
    width="stretch",
    hide_index=True,
    height=750,
    column_config={

        "Fecha": st.column_config.DateColumn(
            "Fecha",
            format="DD/MM/YYYY"
        ),

        "FechaTransmisionERP": st.column_config.DateColumn(
            "Fecha transmisión",
            format="DD/MM/YYYY"
        ),

        "HoraTransmisionERP": st.column_config.TextColumn(
            "Hora transmisión"
        ),

        "TotalUnidades": st.column_config.NumberColumn(
            "Unidades",
            format="%d"
        ),
        "TotalM3": st.column_config.NumberColumn(
         "M³",
        format="%.3f"
        ),

        "TotalSKUs": st.column_config.NumberColumn(
            "SKUs",
            format="%d"
        ),

        "ImporteERP": st.column_config.NumberColumn(
            "Importe ERP",
            format="$ %.0f"
        ),
    }
)