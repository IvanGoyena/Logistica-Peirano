import streamlit as st

from utils.autenticacion import requerir_roles


requerir_roles("admin", "gerencia", "logistica", "supervisor")


from config import *

from utils.leer_datos import (
    leer_archivo
)

from utils.leer_gestion_consultas import (
    obtener_solicitudes_abiertas,
    obtener_urgencias_activas,
    obtener_anulaciones_pendientes,
    obtener_reclamos_abiertos,
    leer_reclamos,
    leer_reclamos_detalle,
    leer_reclamos_fotos,
)

from utils.gestion_consultas import (
    actualizar_solicitud,
    finalizar_solicitud_automaticamente,
)

from utils.gestion_reclamos import (
    actualizar_reclamo,
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

from utils.cola_agrupaciones import (
    crear_orden_agrupacion,
    obtener_orden,
)

import pandas as pd
import altair as alt
import re
import math

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(

    page_title="Despachos",

    page_icon="🚚",

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
        "Los datos se mantienen en memoria durante la planificación "
        "y la ejecución de camionetas."
    )

with col_actualizacion_2:
    actualizar_datos = st.button(
        "🔄 Actualizar datos",
        key="actualizar_datos_despachos",
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
            "UnidadesPendientesERP",
            "VolumenPendienteERP",
            "ImporteERP",
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
# CARGA OPERATIVA PENDIENTE ERP
# =====================================================

# Guardamos los valores originales calculados desde
# el detalle y la volumetría de los artículos.
unidades_totales_originales = (
    pd.to_numeric(
        tabla["TotalUnidades"],
        errors="coerce",
    )
    .fillna(0)
)

volumen_total_original = (
    pd.to_numeric(
        tabla["TotalM3"],
        errors="coerce",
    )
    .fillna(0)
)

# Unidades pendientes reales informadas por ERP.
tabla["UnidadesPendientesERP"] = (
    pd.to_numeric(
        tabla["UnidadesPendientesERP"],
        errors="coerce",
    )
    .fillna(0)
    .astype(int)
)

# Porcentaje del pedido que continúa pendiente.
proporcion_pendiente = (
    tabla["UnidadesPendientesERP"]
    .div(
        unidades_totales_originales.replace(0, pd.NA)
    )
    .fillna(0)
    .clip(lower=0, upper=1)
)

# Reemplazamos las unidades totales por las pendientes ERP.
tabla["TotalUnidades"] = tabla["UnidadesPendientesERP"]

# Ajustamos proporcionalmente la volumetría original
# para que represente únicamente las unidades pendientes.
tabla["TotalM3"] = (
    volumen_total_original
    * proporcion_pendiente
).round(3)


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

# RETIRA tiene prioridad absoluta sobre la frecuencia y el código de despacho.
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

tabla["Planificacion"] = ""

# 1. RETIRA siempre prevalece.
tabla.loc[es_retira, "Planificacion"] = "RETIRA"

# 2. Para el resto, aplicar la lógica semanal / expreso.
mascara_no_retira = ~es_retira
tabla.loc[mascara_no_retira, "Planificacion"] = (
    frecuencia_entrega.loc[mascara_no_retira].where(
        es_entrega_semanal.loc[mascara_no_retira],
        zona_expreso.loc[mascara_no_retira].where(
            zona_expreso.loc[mascara_no_retira].ne(""),
            frecuencia_entrega.loc[mascara_no_retira]
        )
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
# FECHAS
# -----------------------------------------------------

# Fecha del pedido
tabla["Fecha"] = (
    pd.to_datetime(
        tabla["Fecha"],
        errors="coerce",
        utc=True,
    )
    .dt.tz_localize(None)
)

# Fecha de transmisión ERP (solo fecha)
tabla["FechaTransmisionERP"] = (
    pd.to_datetime(
        tabla["FechaTransmisionERP"],
        errors="coerce",
    )
    .dt.date
)

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




st.title("🚚 Gestión de Despachos")
st.caption(
    "Planificación de camionetas y ejecución de agrupaciones en DIGIP."
)

tabla_filtrada = tabla.copy()

# =====================================================
# PEDIDOS DISPONIBLES PARA DASHBOARD Y PLANIFICADOR
# =====================================================
#
# Un pedido deja de estar disponible cuando ya tiene una
# preparación asignada en DIGIP. De esta manera:
#
# - no vuelve a consumir capacidad en el Dashboard;
# - no puede asignarse nuevamente desde el Planificador.
# =====================================================

mascara_sin_preparacion = (
    tabla_filtrada["PreparacionID"]
    .fillna("")
    .astype(str)
    .str.strip()
    .eq("")
)

tabla_disponible_planificacion = tabla_filtrada.loc[
    mascara_sin_preparacion
].copy()

tab_dashboard, tab_planificador = st.tabs(
    [
        "📊 Dashboard",
        "🚐 Planificador de camionetas",
    ]
)


# =====================================================
# DASHBOARD EJECUTIVO DE DESPACHOS
# =====================================================

with tab_dashboard:

    st.subheader("📊 Dashboard operativo")
    st.caption(
        "Estimación de vehículos sobre pedidos todavía sin preparación. "
        "Los pedidos RETIRA no consumen capacidad de reparto."
    )

    filtro_cencosud_1, filtro_cencosud_2, espacio_filtro = st.columns(
        [0.9, 0.9, 4.2],
        vertical_alignment="center",
    )

    with filtro_cencosud_1:
        incluir_cencosud_dashboard = st.toggle(
            "Incluir Cencosud",
            value=True,
            key="despachos_incluir_cencosud_dashboard",
            help=(
                "Encendido: incluye los pedidos de Cencosud. "
                "Apagado: muestra el dashboard sin Cencosud."
            ),
        )

    with filtro_cencosud_2:
        ver_solo_cencosud_dashboard = st.toggle(
            "Ver Cencosud",
            value=False,
            key="despachos_ver_solo_cencosud_dashboard",
            help=(
                "Encendido: muestra únicamente los pedidos "
                "de Cencosud."
            ),
        )

    CAPACIDAD_CAMIONETA_M3 = 8.0
    CAPACIDAD_CAMION_M3 = 15.0

    # -----------------------------------------------------
    # ESTILO VISUAL DEL DASHBOARD
    # -----------------------------------------------------
    st.markdown(
        """
        <style>
        .despachos-kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.75rem;
            margin: 0.75rem 0 1rem 0;
        }
        .despachos-kpi {
            min-height: 128px;
            padding: 0.95rem 1rem;
            border: 1px solid rgba(148, 163, 184, 0.22);
            border-radius: 12px;
            background: linear-gradient(
                145deg,
                rgba(25, 32, 43, 0.96),
                rgba(14, 20, 29, 0.98)
            );
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .despachos-kpi-cabecera {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            font-size: 0.86rem;
            font-weight: 650;
            color: rgba(240, 244, 248, 0.95);
        }
        .despachos-kpi-icono {
            font-size: 1.35rem;
        }
        .despachos-kpi-valor {
            margin-top: 0.4rem;
            font-size: 1.85rem;
            line-height: 1;
            font-weight: 750;
            color: #f8fafc;
        }
        .despachos-kpi-detalle {
            margin-top: 0.45rem;
            font-size: 0.76rem;
            color: rgba(203, 213, 225, 0.82);
        }
        .despachos-panel {
            border: 1px solid rgba(148, 163, 184, 0.20);
            border-radius: 12px;
            padding: 0.55rem 0.8rem 0.3rem 0.8rem;
            background: rgba(17, 24, 34, 0.72);
        }
        @media (max-width: 1200px) {
            .despachos-kpi-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }
        @media (max-width: 700px) {
            .despachos-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    base_dashboard = tabla_disponible_planificacion.copy()

    cliente_dashboard = (
        base_dashboard["ClienteDescripcion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    mascara_cencosud_dashboard = cliente_dashboard.str.contains(
        "CENCOSUD",
        regex=False,
    )

    # "Ver Cencosud" tiene prioridad sobre "Incluir Cencosud"
    # para evitar que ambos controles se contradigan.
    if ver_solo_cencosud_dashboard:
        base_dashboard = base_dashboard.loc[
            mascara_cencosud_dashboard
        ].copy()

    elif not incluir_cencosud_dashboard:
        base_dashboard = base_dashboard.loc[
            ~mascara_cencosud_dashboard
        ].copy()

    base_dashboard["PlanificacionDashboard"] = (
        base_dashboard["Planificacion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("", "SIN PLANIFICACIÓN")
    )

    base_dashboard["VolumenDashboard"] = (
        pd.to_numeric(
            base_dashboard["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
    )

    base_dashboard["UnidadesDashboard"] = (
        pd.to_numeric(
            base_dashboard["TotalUnidades"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    mascara_retira_dashboard = (
        base_dashboard["PlanificacionDashboard"].eq("RETIRA")
    )

    base_retira_dashboard = base_dashboard.loc[
        mascara_retira_dashboard
    ].copy()

    base_reparto_dashboard = base_dashboard.loc[
        ~mascara_retira_dashboard
    ].copy()

    mascara_camion_dashboard = (
        base_reparto_dashboard["VolumenDashboard"]
        .gt(CAPACIDAD_CAMIONETA_M3)
    )

    base_camion_dashboard = base_reparto_dashboard.loc[
        mascara_camion_dashboard
    ].copy()

    base_camioneta_dashboard = base_reparto_dashboard.loc[
        ~mascara_camion_dashboard
    ].copy()

    volumen_camionetas_dashboard = float(
        base_camioneta_dashboard["VolumenDashboard"].sum()
    )
    volumen_camiones_dashboard = float(
        base_camion_dashboard["VolumenDashboard"].sum()
    )

    camionetas_estimadas_dashboard = (
        int(math.ceil(
            volumen_camionetas_dashboard / CAPACIDAD_CAMIONETA_M3
        ))
        if volumen_camionetas_dashboard > 0
        else 0
    )

    camiones_estimados_dashboard = (
        int(math.ceil(
            volumen_camiones_dashboard / CAPACIDAD_CAMION_M3
        ))
        if volumen_camiones_dashboard > 0
        else 0
    )

    pedidos_reparto_dashboard = int(
        base_reparto_dashboard["Pedido"].nunique()
    )
    pedidos_retira_dashboard = int(
        base_retira_dashboard["Pedido"].nunique()
    )
    pedidos_camion_dashboard = int(
        base_camion_dashboard["Pedido"].nunique()
    )
    pedidos_camioneta_dashboard = int(
        base_camioneta_dashboard["Pedido"].nunique()
    )

    unidades_reparto_dashboard = int(
        base_reparto_dashboard["UnidadesDashboard"].sum()
    )
    unidades_retira_dashboard = int(
        base_retira_dashboard["UnidadesDashboard"].sum()
    )
    unidades_camion_dashboard = int(
        base_camion_dashboard["UnidadesDashboard"].sum()
    )

    volumen_reparto_dashboard = float(
        base_reparto_dashboard["VolumenDashboard"].sum()
    )

    sin_planificacion_dashboard = int(
        base_dashboard.loc[
            base_dashboard["PlanificacionDashboard"]
            .eq("SIN PLANIFICACIÓN"),
            "Pedido",
        ].nunique()
    )
    unidades_sin_planificacion = int(
        base_dashboard.loc[
            base_dashboard["PlanificacionDashboard"]
            .eq("SIN PLANIFICACIÓN"),
            "UnidadesDashboard",
        ].sum()
    )

    def formato_entero(valor: int) -> str:
        return f"{int(valor):,}".replace(",", ".")

    tarjetas_html = f"""
    <div class="despachos-kpi-grid">
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚚</span>
                <span>Pedidos reparto</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_reparto_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_reparto_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚐</span>
                <span>Camionetas estimadas</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(camionetas_estimadas_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                Capacidad: {CAPACIDAD_CAMIONETA_M3:.0f} m³
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🚛</span>
                <span>Camiones sugeridos</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(camiones_estimados_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                Capacidad: {CAPACIDAD_CAMION_M3:.0f} m³
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">📦</span>
                <span>Pedidos &gt; 8 m³</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_camion_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_camion_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">🏬</span>
                <span>RETIRA</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(pedidos_retira_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_retira_dashboard)} unidades
            </div>
        </div>
        <div class="despachos-kpi">
            <div class="despachos-kpi-cabecera">
                <span class="despachos-kpi-icono">⚠️</span>
                <span>Sin planificación</span>
            </div>
            <div class="despachos-kpi-valor">
                {formato_entero(sin_planificacion_dashboard)}
            </div>
            <div class="despachos-kpi-detalle">
                {formato_entero(unidades_sin_planificacion)} unidades
            </div>
        </div>
    </div>
    """

    st.markdown(tarjetas_html, unsafe_allow_html=True)

    # -----------------------------------------------------
    # GRÁFICOS
    # -----------------------------------------------------
    grafico_volumen, grafico_tipo = st.columns(
        [1.05, 1],
        vertical_alignment="top",
    )

    volumen_por_planificacion = (
        base_reparto_dashboard
        .groupby(
            "PlanificacionDashboard",
            as_index=False,
        )
        .agg(
            Volumen=("VolumenDashboard", "sum"),
            Pedidos=("Pedido", "nunique"),
        )
        .sort_values("Volumen", ascending=False)
    )

    with grafico_volumen:
        st.markdown("#### Volumen por planificación (m³)")

        if volumen_por_planificacion.empty:
            st.info("No hay carga de reparto para graficar.")
        else:
            volumen_por_planificacion["ValorVisible"] = (
                volumen_por_planificacion["Volumen"]
                .map(lambda valor: f"{valor:.2f}")
            )
            volumen_maximo = float(
                volumen_por_planificacion["Volumen"].max()
            )
            volumen_por_planificacion["EsMaximo"] = (
                volumen_por_planificacion["Volumen"].eq(volumen_maximo)
            )

            barras = (
                alt.Chart(volumen_por_planificacion)
                .mark_bar(cornerRadiusEnd=5, height=19)
                .encode(
                    x=alt.X(
                        "Volumen:Q",
                        title="Volumen m³",
                        axis=alt.Axis(
                            grid=True,
                            gridColor="#263241",
                            labelColor="#cbd5e1",
                            titleColor="#cbd5e1",
                        ),
                    ),
                    y=alt.Y(
                        "PlanificacionDashboard:N",
                        title=None,
                        sort="-x",
                        axis=alt.Axis(labelColor="#e2e8f0"),
                    ),
                    color=alt.condition(
                        alt.datum.EsMaximo,
                        alt.value("#1d4ed8"),
                        alt.value("#334f73"),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "PlanificacionDashboard:N",
                            title="Planificación",
                        ),
                        alt.Tooltip(
                            "Pedidos:Q",
                            title="Pedidos",
                            format=",.0f",
                        ),
                        alt.Tooltip(
                            "Volumen:Q",
                            title="Volumen m³",
                            format=".3f",
                        ),
                    ],
                )
            )

            etiquetas = (
                alt.Chart(volumen_por_planificacion)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=6,
                    color="#f8fafc",
                    fontSize=12,
                    fontWeight="bold",
                )
                .encode(
                    x="Volumen:Q",
                    y=alt.Y(
                        "PlanificacionDashboard:N",
                        sort="-x",
                    ),
                    text="ValorVisible:N",
                )
            )

            chart_volumen = (
                (barras + etiquetas)
                .properties(height=330)
                .configure_view(stroke=None)
            )

            st.altair_chart(
                chart_volumen,
                width="stretch",
            )

    total_pedidos_dashboard = (
        pedidos_camioneta_dashboard
        + pedidos_camion_dashboard
        + pedidos_retira_dashboard
    )

    distribucion_transporte = pd.DataFrame({
        "Tipo": ["Camioneta", "Camión", "RETIRA"],
        "Pedidos": [
            pedidos_camioneta_dashboard,
            pedidos_camion_dashboard,
            pedidos_retira_dashboard,
        ],
        "Orden": [1, 2, 3],
    })

    distribucion_transporte = distribucion_transporte.loc[
        distribucion_transporte["Pedidos"].gt(0)
    ].copy()

    if total_pedidos_dashboard > 0:
        distribucion_transporte["Porcentaje"] = (
            distribucion_transporte["Pedidos"]
            / total_pedidos_dashboard
            * 100
        )
    else:
        distribucion_transporte["Porcentaje"] = 0.0

    distribucion_transporte["Etiqueta"] = (
        distribucion_transporte["Pedidos"].astype(str)
        + " ("
        + distribucion_transporte["Porcentaje"]
        .map(lambda valor: f"{valor:.1f}%")
        + ")"
    )

    with grafico_tipo:
        st.markdown("#### Pedidos por tipo de gestión")

        if distribucion_transporte.empty:
            st.info("No hay pedidos para graficar.")
        else:
            escala_colores = alt.Scale(
                domain=["Camioneta", "Camión", "RETIRA"],
                range=["#174f87", "#b45309", "#166534"],
            )

            donut = (
                alt.Chart(distribucion_transporte)
                .mark_arc(
                    innerRadius=88,
                    outerRadius=135,
                    stroke="#0f1720",
                    strokeWidth=2,
                )
                .encode(
                    theta=alt.Theta(
                        "Pedidos:Q",
                        stack=True,
                    ),
                    color=alt.Color(
                        "Tipo:N",
                        scale=escala_colores,
                        legend=alt.Legend(
                            orient="right",
                            title=None,
                            labelColor="#e2e8f0",
                            labelFontSize=12,
                            symbolSize=180,
                        ),
                    ),
                    order=alt.Order("Orden:Q"),
                    tooltip=[
                        alt.Tooltip("Tipo:N", title="Tipo"),
                        alt.Tooltip(
                            "Pedidos:Q",
                            title="Pedidos",
                            format=",.0f",
                        ),
                        alt.Tooltip(
                            "Porcentaje:Q",
                            title="Participación",
                            format=".1f",
                        ),
                    ],
                )
            )

            etiquetas_donut = (
                alt.Chart(distribucion_transporte)
                .mark_text(
                    radius=155,
                    color="#f8fafc",
                    fontSize=12,
                    fontWeight="bold",
                )
                .encode(
                    theta=alt.Theta(
                        "Pedidos:Q",
                        stack=True,
                    ),
                    order=alt.Order("Orden:Q"),
                    text="Etiqueta:N",
                )
            )

            centro_total = (
                alt.Chart(
                    pd.DataFrame({
                        "Texto": [
                            str(total_pedidos_dashboard),
                            "Pedidos totales",
                        ],
                        "Y": [-7, 16],
                        "Tamanio": [30, 13],
                    })
                )
                .mark_text(
                    align="center",
                    baseline="middle",
                    color="#f8fafc",
                    fontWeight="bold",
                )
                .encode(
                    text="Texto:N",
                    y=alt.Y(
                        "Y:Q",
                        axis=None,
                        scale=alt.Scale(domain=[-100, 100]),
                    ),
                    size=alt.Size(
                        "Tamanio:Q",
                        legend=None,
                        scale=None,
                    ),
                )
            )

            chart_tipo = (
                (donut + etiquetas_donut + centro_total)
                .properties(height=330)
                .configure_view(stroke=None)
            )

            st.altair_chart(
                chart_tipo,
                width="stretch",
            )

    # -----------------------------------------------------
    # CAPACIDAD POR PLANIFICACIÓN
    # -----------------------------------------------------
    st.markdown("#### Capacidad estimada por planificación")

    def resumir_capacidad_planificacion(
        bloque: pd.DataFrame,
    ) -> pd.Series:

        volumen_camioneta = float(
            bloque.loc[
                bloque["VolumenDashboard"]
                .le(CAPACIDAD_CAMIONETA_M3),
                "VolumenDashboard",
            ].sum()
        )

        volumen_camion = float(
            bloque.loc[
                bloque["VolumenDashboard"]
                .gt(CAPACIDAD_CAMIONETA_M3),
                "VolumenDashboard",
            ].sum()
        )

        camionetas = (
            int(math.ceil(
                volumen_camioneta / CAPACIDAD_CAMIONETA_M3
            ))
            if volumen_camioneta > 0
            else 0
        )

        camiones = (
            int(math.ceil(
                volumen_camion / CAPACIDAD_CAMION_M3
            ))
            if volumen_camion > 0
            else 0
        )

        capacidad_total = (
            camionetas * CAPACIDAD_CAMIONETA_M3
            + camiones * CAPACIDAD_CAMION_M3
        )

        ocupacion = (
            (volumen_camioneta + volumen_camion)
            / capacidad_total
            * 100
            if capacidad_total > 0
            else 0
        )

        if ocupacion > 90:
            estado_ocupacion = "🔴 Alta"
        elif ocupacion >= 70:
            estado_ocupacion = "🟡 Media"
        else:
            estado_ocupacion = "🟢 Baja"

        return pd.Series({
            "Pedidos": int(bloque["Pedido"].nunique()),
            "Clientes": int(bloque["ClienteCodigo"].nunique()),
            "Unidades": int(bloque["UnidadesDashboard"].sum()),
            "Volumen m³": round(
                float(bloque["VolumenDashboard"].sum()),
                3,
            ),
            "Camionetas (8 m³)": camionetas,
            "Pedidos camión (> 8 m³)": int(
                bloque.loc[
                    bloque["VolumenDashboard"]
                    .gt(CAPACIDAD_CAMIONETA_M3),
                    "Pedido",
                ].nunique()
            ),
            "Camiones (15 m³)": camiones,
            "Nivel": estado_ocupacion,
            "Ocupación estimada %": round(ocupacion, 1),
        })

    resumen_capacidad_dashboard = (
        base_reparto_dashboard
        .groupby(
            "PlanificacionDashboard",
            dropna=False,
            sort=False,
        )
        .apply(
            resumir_capacidad_planificacion,
            include_groups=False,
        )
        .reset_index()
        .rename(
            columns={
                "Planificaciones": "Planificación",
            }
        )
        .sort_values(
            ["Camiones (15 m³)", "Camionetas (8 m³)", "Volumen m³"],
            ascending=[False, False, False],
        )
    )

    st.dataframe(
        resumen_capacidad_dashboard,
        width="stretch",
        hide_index=True,
        height=min(
            390,
            80 + len(resumen_capacidad_dashboard) * 35,
        ),
        column_config={
            "Pedidos": st.column_config.NumberColumn(
                "Pedidos",
                format="%d",
            ),
            "Clientes": st.column_config.NumberColumn(
                "Clientes",
                format="%d",
            ),
            "Unidades": st.column_config.NumberColumn(
                "Unidades",
                format="%d",
            ),
            "Volumen m³": st.column_config.NumberColumn(
                "Volumen m³",
                format="%.3f",
            ),
            "Camionetas (8 m³)": st.column_config.NumberColumn(
                "Camionetas (8 m³)",
                format="%d",
            ),
            "Pedidos camión (> 8 m³)": (
                st.column_config.NumberColumn(
                    "Pedidos camión (> 8 m³)",
                    format="%d",
                )
            ),
            "Camiones (15 m³)": st.column_config.NumberColumn(
                "Camiones (15 m³)",
                format="%d",
            ),
            "Ocupación estimada %": (
                st.column_config.ProgressColumn(
                    "Ocupación estimada",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
                )
            ),
        },
    )

    # -----------------------------------------------------
    # DETALLE Y CONTROLES
    # -----------------------------------------------------
    panel_camion, panel_alertas = st.columns(
        [1.15, 1],
        vertical_alignment="top",
    )

    with panel_camion:

        st.markdown("#### 🚛 Clientes candidatos a camión (> 8 m³)")

        # La necesidad de transporte se analiza por cliente completo.
        # Por eso se parte de TODOS los pedidos de reparto y recién después
        # se filtran los clientes cuyo volumen acumulado supera 8 m³.
        # Regla especial para Cencosud:
        # solamente se consolidan como carga de camión los pedidos
        # cuya planificación es EASY. Los pedidos Cencosud con
        # planificación semanal/diaria continúan en los repartos normales.
        cliente_reparto_normalizado = (
            base_reparto_dashboard["ClienteDescripcion"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        planificacion_reparto_normalizada = (
            base_reparto_dashboard["PlanificacionDashboard"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        es_cencosud_reparto = cliente_reparto_normalizado.str.contains(
            "CENCOSUD",
            regex=False,
        )

        base_clientes_camion = base_reparto_dashboard.loc[
            ~es_cencosud_reparto
            | planificacion_reparto_normalizada.eq("EASY")
        ].copy()

        clientes_camion_dashboard = (
            base_clientes_camion
            .groupby(
                [
                    "ClienteCodigo",
                    "ClienteDescripcion",
                ],
                as_index=False,
                dropna=False,
            )
            .agg(
                Planificaciones=(
                    "PlanificacionDashboard",
                    lambda serie: ", ".join(
                        sorted(
                            {
                                str(valor).strip()
                                for valor in serie
                                if str(valor).strip()
                            }
                        )
                    ),
                ),
                Pedidos=(
                    "Pedido",
                    lambda serie: ", ".join(
                        sorted(
                            {
                                str(valor).strip()
                                for valor in serie
                                if str(valor).strip()
                            }
                        )
                    ),
                ),
                CantidadPedidos=("Pedido", "nunique"),
                VolumenM3=("VolumenDashboard", "sum"),
                Unidades=("UnidadesDashboard", "sum"),
            )
        )

        clientes_camion_dashboard = clientes_camion_dashboard.loc[
            clientes_camion_dashboard["VolumenM3"]
            .gt(CAPACIDAD_CAMIONETA_M3)
        ].copy()

        if clientes_camion_dashboard.empty:
            st.success(
                "No hay clientes con volumen acumulado superior a 8 m³.",
                icon="✅",
            )
        else:
            clientes_camion_dashboard["CamionetasEstimadas"] = (
                clientes_camion_dashboard["VolumenM3"]
                .div(CAPACIDAD_CAMIONETA_M3)
                .apply(math.ceil)
                .astype(int)
            )

            clientes_camion_dashboard["Nivel"] = (
                clientes_camion_dashboard["CamionetasEstimadas"]
                .map(
                    lambda cantidad: (
                        "🟢 1 vehículo"
                        if cantidad == 1
                        else (
                            "🟡 2 vehículos"
                            if cantidad == 2
                            else f"🔴 {cantidad} vehículos"
                        )
                    )
                )
            )

            vista_camion_dashboard = (
                clientes_camion_dashboard
                .sort_values(
                    ["CamionetasEstimadas", "VolumenM3"],
                    ascending=[False, False],
                )
                .rename(
                    columns={
                        "ClienteCodigo": "Código cliente",
                        "ClienteDescripcion": "Cliente",
                        "PlanificacionDashboard": "Planificación",
                        "CantidadPedidos": "Cant. pedidos",
                        "VolumenM3": "Volumen m³",
                        "CamionetasEstimadas": "Vehículos estimados",
                    }
                )
            )

            st.dataframe(
                vista_camion_dashboard,
                width="stretch",
                hide_index=True,
                height=min(
                    330,
                    80 + len(vista_camion_dashboard) * 35,
                ),
                column_config={
                    "Pedidos": st.column_config.TextColumn(
                        "Pedidos",
                        width="large",
                    ),
                    "Cant. pedidos": st.column_config.NumberColumn(
                        "Cant. pedidos",
                        format="%d",
                    ),
                    "Volumen m³": st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.3f",
                    ),
                    "Unidades": st.column_config.NumberColumn(
                        "Unidades",
                        format="%d",
                    ),
                    "Vehículos estimados": (
                        st.column_config.NumberColumn(
                            "Vehículos estimados",
                            format="%d",
                        )
                    ),
                },
            )

        st.markdown("#### 🏬 Pedidos RETIRA")

        if base_retira_dashboard.empty:
            st.info(
                "No hay pedidos RETIRA pendientes de preparación."
            )
        else:
            columnas_retira_dashboard = [
                "Pedido",
                "ClienteCodigo",
                "ClienteDescripcion",
                "PlanificacionDashboard",
                "UnidadesDashboard",
                "TotalSKUs",
                "VolumenDashboard",
                "CodigoDespacho",
            ]

            columnas_retira_dashboard = [
                columna
                for columna in columnas_retira_dashboard
                if columna in base_retira_dashboard.columns
            ]

            vista_retira_dashboard = (
                base_retira_dashboard[
                    columnas_retira_dashboard
                ]
                .sort_values(
                    ["ClienteDescripcion", "Pedido"],
                    ascending=[True, True],
                )
                .rename(
                    columns={
                        "ClienteCodigo": "Código cliente",
                        "ClienteDescripcion": "Cliente",
                        "PlanificacionDashboard": "Planificación",
                        "UnidadesDashboard": "Unidades",
                        "TotalSKUs": "SKUs",
                        "VolumenDashboard": "Volumen m³",
                        "CodigoDespacho": "Código despacho",
                    }
                )
            )

            st.dataframe(
                vista_retira_dashboard,
                width="stretch",
                hide_index=True,
                height=min(
                    330,
                    80 + len(vista_retira_dashboard) * 35,
                ),
                column_config={
                    "Unidades": st.column_config.NumberColumn(
                        "Unidades",
                        format="%d",
                    ),
                    "SKUs": st.column_config.NumberColumn(
                        "SKUs",
                        format="%d",
                    ),
                    "Volumen m³": st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.3f",
                    ),
                },
            )

    with panel_alertas:

        st.markdown("#### Controles operativos")

        if pedidos_retira_dashboard:
            st.info(
                f"{pedidos_retira_dashboard} pedido(s) RETIRA "
                "se excluyen del cálculo de transporte.",
                icon="🏬",
            )

        if pedidos_camion_dashboard:
            st.warning(
                f"{pedidos_camion_dashboard} pedido(s) superan "
                "la capacidad individual de una camioneta de 8 m³.",
                icon="🚛",
            )

        if sin_planificacion_dashboard:
            st.error(
                f"{sin_planificacion_dashboard} pedido(s) todavía "
                "no tienen planificación.",
                icon="⚠️",
            )

        if (
            pedidos_retira_dashboard == 0
            and pedidos_camion_dashboard == 0
            and sin_planificacion_dashboard == 0
        ):
            st.success(
                "La carga no presenta alertas operativas principales.",
                icon="✅",
            )

        st.info(
            "Capacidades de referencia: "
            "Camioneta 8 m³ · Camión 15 m³.",
            icon="📦",
        )

        st.metric(
            "Volumen total de reparto",
            f"{volumen_reparto_dashboard:,.2f} m³"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", "."),
        )

        st.caption(
            "Estimación teórica con base en la planificación actual. "
            "La asignación definitiva continúa en el Planificador."
        )



with tab_planificador:
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
        "RETIRA": [
            "RETIRA",
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
        "RETIRA",
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

        # El número visible normalmente se extrae del nombre real
        # del agrupador, por ejemplo "CAMIONETA LUN 2" -> 2.
        #
        # RETIRA es una excepción porque el agrupador se llama
        # simplemente "RETIRA" y no termina en un número. En ese caso
        # conservamos el número lógico generado por el planificador.
        numero_desde_despacho = pd.to_numeric(
            resultado["DespachoDIGIP"]
            .fillna("")
            .astype(str)
            .str.extract(
                r"(\d+)$",
                expand=False
            ),
            errors="coerce",
        )

        numero_logico = pd.to_numeric(
            resultado["NumeroCamionetaLogica"],
            errors="coerce",
        )

        resultado["NumeroCamioneta"] = (
            numero_desde_despacho
            .fillna(numero_logico)
            .fillna(1)
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

    pedidos_excluidos_preparacion = int(
        tabla_filtrada.loc[
            ~mascara_sin_preparacion,
            "Pedido",
        ].nunique()
    )

    if pedidos_excluidos_preparacion:
        st.info(
            f"{pedidos_excluidos_preparacion} pedido(s) con preparación "
            "asignada se excluyen automáticamente del planificador.",
            icon="🚫",
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

        col_plan1, col_plan2 = st.columns(
            [1, 1]
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
                tabla_disponible_planificacion["Planificacion"]
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

        base_planificacion = tabla_disponible_planificacion.copy()

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

        if base_planificacion.empty:

            st.warning(
                "No quedaron pedidos disponibles para planificar. "
                "Los pedidos seleccionados ya tienen una preparación, "
                "poseen una gestión comercial abierta o fueron excluidos."
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

                # RETIRA se agrupa por listado de pedidos, sin importar
                # el CodigoDespacho de cada registro.
                es_camioneta_retira = (
                    normalizar_planificacion(planificacion_fila) == "RETIRA"
                )

                if es_camioneta_retira:
                    codigo_despacho = ""
                    codigos_despacho = []
                    usar_filtro_codigo_despacho = False

                despacho_digip = str(
                    fila_camioneta[
                        "DespachoDIGIP"
                    ]
                ).strip()

                ejecucion_valida = bool(
                    lista_pedidos
                )

                clave_resultado_actual = (
                    f"resultado_digip_{clave_ejecucion}"
                )

                estado_guardado = st.session_state.get(
                    clave_resultado_actual
                )

                # Antes de dibujar la fila, sincroniza el estado
                # guardado con la orden real de Google Sheets.
                if (
                    estado_guardado
                    and estado_guardado.get("orden_id")
                ):

                    orden_sincronizada = obtener_orden(
                        estado_guardado["orden_id"]
                    )

                    if orden_sincronizada:

                        estado_worker = str(
                            orden_sincronizada.get(
                                "Estado",
                                "",
                            )
                        ).strip().upper()

                        mensaje_worker = str(
                            orden_sincronizada.get(
                                "Mensaje",
                                "",
                            )
                        ).strip()

                        etapa_worker = str(
                            orden_sincronizada.get(
                                "Etapa",
                                "",
                            )
                        ).strip()

                        if estado_worker == "COMPLETADA":

                            estado_guardado = {
                                "exito": True,
                                "pendiente": False,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        elif estado_worker == "ERROR":

                            estado_guardado = {
                                "exito": False,
                                "pendiente": False,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        else:

                            estado_guardado = {
                                "exito": False,
                                "pendiente": True,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        st.session_state[
                            clave_resultado_actual
                        ] = estado_guardado

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

                        elif bool(
                            estado_guardado.get(
                                "pendiente",
                                False
                            )
                        ):
                            st.info(
                                "En proceso",
                                icon="⚙️"
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
                            and not bool(
                                estado_guardado.get(
                                    "pendiente",
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

                # -------------------------------------------------
                # DETALLE EXPANDIBLE DE LA CAMIONETA
                # -------------------------------------------------

                with st.expander(
                    f"🔎 Abrir detalle · {nombre_camioneta}",
                    expanded=False,
                ):

                    detalle_camioneta = pedidos_camioneta.copy()

                    # Una fila por pedido para evitar duplicaciones
                    # en los indicadores y en la tabla visible.
                    if "Pedido" in detalle_camioneta.columns:
                        detalle_camioneta = (
                            detalle_camioneta
                            .drop_duplicates(
                                subset=["Pedido"],
                                keep="first",
                            )
                            .reset_index(drop=True)
                        )

                    cantidad_clientes_detalle = (
                        detalle_camioneta["ClienteCodigo"].nunique()
                        if "ClienteCodigo" in detalle_camioneta.columns
                        else 0
                    )

                    cantidad_pedidos_detalle = (
                        detalle_camioneta["Pedido"].nunique()
                        if "Pedido" in detalle_camioneta.columns
                        else len(detalle_camioneta)
                    )

                    total_unidades_detalle = int(
                        pd.to_numeric(
                            detalle_camioneta.get(
                                "TotalUnidades",
                                pd.Series(dtype=float),
                            ),
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    )

                    total_m3_detalle = float(
                        pd.to_numeric(
                            detalle_camioneta.get(
                                "TotalM3",
                                pd.Series(dtype=float),
                            ),
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    )

                    detalle_kpi_1, detalle_kpi_2, \
                        detalle_kpi_3, detalle_kpi_4 = st.columns(4)

                    detalle_kpi_1.metric(
                        "👥 Clientes",
                        cantidad_clientes_detalle,
                    )

                    detalle_kpi_2.metric(
                        "📦 Pedidos",
                        cantidad_pedidos_detalle,
                    )

                    detalle_kpi_3.metric(
                        "🔢 Unidades",
                        f"{total_unidades_detalle:,}".replace(",", "."),
                    )

                    detalle_kpi_4.metric(
                        "📐 Volumen",
                        f"{total_m3_detalle:,.3f} m³"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", "."),
                    )

                    columnas_detalle_preferidas = [
                        "Pedido",
                        "FechaTransmisionERP",
                        "ClienteCodigo",
                        "ClienteDescripcion",
                        "TotalUnidades",
                        "TotalM3",
                        "TotalSKUs",
                        "DetalleFamilias",
                        "CodigoDespacho",
                        "DespachoDescripcion",
                        "Planificacion",
                    ]

                    columnas_detalle_disponibles = [
                        columna
                        for columna in columnas_detalle_preferidas
                        if columna in detalle_camioneta.columns
                    ]

                    tabla_detalle_camioneta = detalle_camioneta[
                        columnas_detalle_disponibles
                    ].copy()

                    tabla_detalle_camioneta = (
                        tabla_detalle_camioneta.rename(
                            columns={
                                "ClienteCodigo": "Código cliente",
                                "ClienteDescripcion": "Cliente",
                                "TotalUnidades": "Unidades",
                                "TotalM3": "Volumen m³",
                                "TotalSKUs": "SKUs",
                                "DetalleFamilias": "Familias",
                                "CodigoDespacho": "Código despacho",
                                "DespachoDescripcion": "Despacho actual",
                                "Planificacion": "Planificación",
                            }
                        )
                    )

                    st.dataframe(
                        tabla_detalle_camioneta,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Volumen m³": st.column_config.NumberColumn(
                                "Volumen m³",
                                format="%.3f",
                            ),
                            "Unidades": st.column_config.NumberColumn(
                                "Unidades",
                                format="%d",
                            ),
                            "SKUs": st.column_config.NumberColumn(
                                "SKUs",
                                format="%d",
                            ),
                        },
                    )

                if (
                    estado_guardado
                    and not bool(
                        estado_guardado.get(
                            "exito",
                            False
                        )
                    )
                    and not bool(
                        estado_guardado.get(
                            "pendiente",
                            False
                        )
                    )
                ):

                    with st.expander(
                        f"❌ Ver error de {nombre_camioneta}",
                        expanded=True,
                    ):

                        st.error(
                            estado_guardado.get(
                                "mensaje",
                                "Error sin detalle."
                            )
                        )

                        detalle_guardado = estado_guardado.get(
                            "detalle",
                            ""
                        )

                        if detalle_guardado:

                            st.code(
                                detalle_guardado,
                                language="text",
                            )

                if ejecutar:

                    clave_resultado = (
                        f"resultado_digip_{clave_ejecucion}"
                    )

                    usuario_ejecucion = (
                        st.session_state.get("usuario")
                        or st.session_state.get("nombre_usuario")
                        or "Usuario app"
                    )

                    try:

                        orden_id = crear_orden_agrupacion(
                            camioneta=despacho_digip,
                            codigo_despacho=codigo_despacho,
                            codigos_despacho=codigos_despacho,
                            usar_filtro_codigo_despacho=(
                                usar_filtro_codigo_despacho
                            ),
                            pedidos=lista_pedidos,
                            usuario=usuario_ejecucion,
                        )

                        st.session_state[
                            clave_resultado
                        ] = {
                            "exito": False,
                            "pendiente": True,
                            "orden_id": orden_id,
                            "mensaje": (
                                "Orden enviada al worker de la PC."
                            ),
                        }

                        st.success(
                            f"Orden {orden_id} enviada al worker."
                        )

                        st.rerun()

                    except Exception as error:

                        st.session_state[
                            clave_resultado
                        ] = {
                            "exito": False,
                            "pendiente": False,
                            "mensaje": str(error),
                        }

                        st.error(
                            "No se pudo enviar la orden al worker: "
                            f"{error}"
                        )

                estado_cola = st.session_state.get(
                    f"resultado_digip_{clave_ejecucion}"
                )

                if estado_cola and estado_cola.get("orden_id"):

                    orden_actual = obtener_orden(
                        estado_cola["orden_id"]
                    )

                    if orden_actual:

                        estado_orden = str(
                            orden_actual.get("Estado", "")
                        ).strip().upper()

                        mensaje_orden = str(
                            orden_actual.get("Mensaje", "")
                        ).strip()

                        etapa_orden = str(
                            orden_actual.get("Etapa", "")
                        ).strip()

                        if estado_orden == "COMPLETADA":

                            st.session_state[
                                f"resultado_digip_{clave_ejecucion}"
                            ] = {
                                "exito": True,
                                "pendiente": False,
                                "orden_id": orden_actual.get("OrdenID"),
                                "mensaje": mensaje_orden,
                            }

                            st.success(
                                f"✅ {nombre_camioneta}: "
                                f"{mensaje_orden}"
                            )

                        elif estado_orden == "ERROR":

                            st.error(
                                f"❌ {nombre_camioneta}: "
                                f"{mensaje_orden}"
                            )

                        elif estado_orden == "EN_PROCESO":

                            st.info(
                                f"⚙️ {nombre_camioneta} en proceso — "
                                f"{etapa_orden}: {mensaje_orden}"
                            )

                        else:

                            st.warning(
                                f"🕒 {nombre_camioneta} pendiente "
                                "de ser tomada por el worker."
                            )

                        if estado_orden not in {
                            "COMPLETADA",
                            "ERROR",
                            "CANCELADA",
                        }:

                            if st.button(
                                "🔄 Consultar estado",
                                key=(
                                    "consultar_worker_"
                                    f"{clave_ejecucion}"
                                ),
                            ):
                                st.rerun()

