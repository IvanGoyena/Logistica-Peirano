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


from utils.cola_agrupaciones import (
    crear_orden_agrupacion,
    obtener_orden,
)

import pandas as pd
import altair as alt
import re
import math

from views.despachos.dashboard import render_dashboard_despachos
from views.despachos.planificador import render_planificador_despachos

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

    st.cache_data.clear()

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


@st.cache_data(show_spinner="Preparando tablas de Despachos...")
def construir_tablas_base_despachos():
    """Construye una sola vez las tablas reutilizadas por ambas vistas."""

    datos = cargar_datos_operativos()

    df_pedidos_local = datos["pedidos"].copy()
    df_detalle_local = datos["detalle"].copy()
    df_articulos_local = datos["articulos"].copy()
    df_clientes_local = datos["clientes"].copy()
    df_pendientes_erp_local = datos["pendientes_erp"].copy()
    df_transmisiones_local = datos["transmisiones"].copy()
    df_expresos_local = datos["expresos"].copy()
    df_volumetria_local = datos["volumetria"].copy()

    tabla_local = construir_tabla_pedidos(
        df_pedidos_local,
        df_detalle_local,
        df_articulos_local,
        df_clientes_local,
        df_volumetria_local,
    )

    return {
        "df_pedidos": df_pedidos_local,
        "df_detalle": df_detalle_local,
        "df_articulos": df_articulos_local,
        "df_clientes": df_clientes_local,
        "df_pendientes_erp": df_pendientes_erp_local,
        "df_transmisiones": df_transmisiones_local,
        "df_expresos": df_expresos_local,
        "df_volumetria": df_volumetria_local,
        "tabla": tabla_local,
        "tabla_transmisiones": construir_tabla_transmisiones(
            df_transmisiones_local
        ),
        "tabla_expresos": construir_tabla_expresos(
            df_expresos_local
        ),
        "tabla_clientes": construir_tabla_clientes(
            df_clientes_local
        ),
        "tabla_pendientes_erp": construir_tabla_pendientes(
            df_pendientes_erp_local
        ),
    }


base_despachos = construir_tablas_base_despachos()

df_pedidos = base_despachos["df_pedidos"]
df_detalle = base_despachos["df_detalle"]
df_articulos = base_despachos["df_articulos"]
df_clientes = base_despachos["df_clientes"]
df_pendientes_erp = base_despachos["df_pendientes_erp"]
df_transmisiones = base_despachos["df_transmisiones"]
df_expresos = base_despachos["df_expresos"]
df_volumetria = base_despachos["df_volumetria"]
tabla = base_despachos["tabla"]
tabla_transmisiones = base_despachos["tabla_transmisiones"]
tabla_expresos = base_despachos["tabla_expresos"]
tabla_clientes = base_despachos["tabla_clientes"]
tabla_pendientes_erp = base_despachos["tabla_pendientes_erp"]


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


vista_despachos = st.segmented_control(
    "Vista de Despachos",
    options=[
        "📊 Dashboard",
        "🚐 Planificador de camionetas",
    ],
    default="📊 Dashboard",
    key="vista_principal_despachos",
    label_visibility="collapsed",
)

if vista_despachos == "📊 Dashboard":
    render_dashboard_despachos(tabla_disponible_planificacion)
else:
    render_planificador_despachos(
        tabla=tabla,
        tabla_filtrada=tabla_filtrada,
        tabla_disponible_planificacion=tabla_disponible_planificacion,
        mascara_sin_preparacion=mascara_sin_preparacion,
        pedidos_bloqueados_gestion=pedidos_bloqueados_gestion,
        pedidos_por_tipo_gestion=pedidos_por_tipo_gestion,
    )

