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

from utils.leer_fuente_flexible import leer_archivo_flexible
from models.cobertura_pedidos import analizar_cobertura_pedidos_erp



import pandas as pd
import altair as alt
import re

from models.dashboard_pedidos import (
    aplicar_filtros_dashboard,
    calcular_kpis,
    evaluar_riesgo_operativo,
    formatear_importe_compacto,
    indicadores_inteligencia,
    indice_complejidad_pedidos,
    pedidos_criticos,
    preparar_datos_dashboard,
    resumen_abc_detalle,
    resumen_clientes_impacto,
    resumen_categoria,
    resumen_clientes_analitico,
    resumen_composicion_detalle,
    resumen_evolucion,
    resumen_periodo,
    resumen_planificacion_analitico,
)
from utils.graficos_pedidos import (
    barras as grafico_barras_pedidos,
    barras_antiguedad_unidades,
    donut_composicion as grafico_donut_composicion,
    grafico_abc,
    grafico_impacto_clientes,
    evolucion as grafico_evolucion_pedidos,
    pareto_clientes,
)

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
        "stock_detallado": leer_archivo_flexible(
            CARPETA_DATOS, ["stock_detallado"], cache=False
        )[0],
        "stock_recepcion": leer_archivo_flexible(
            CARPETA_DATOS, ["stock_recepcion"], cache=False
        )[0],
        "disponible_digip": leer_archivo_flexible(
            CARPETA_DATOS, ["Disponible Digip", "disponible_digip"], cache=False
        )[0],
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
df_stock_detallado = datos_operativos["stock_detallado"].copy()
df_stock_recepcion = datos_operativos["stock_recepcion"].copy()
df_disponible_digip = datos_operativos["disponible_digip"].copy()


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



datos_dashboard = preparar_datos_dashboard(tabla)

# Detalle enriquecido con Maestro de Artículos.
# Se utiliza para analizar la composición real del pendiente.
tabla_detalle_dashboard = construir_tabla_detalle(
    df_detalle,
    df_articulos,
    df_volumetria,
)

lineas_cobertura_erp, resumen_cobertura_erp = analizar_cobertura_pedidos_erp(
    tabla_detalle_erp=tabla_detalle_dashboard,
    tabla_pendientes_erp=tabla_pendientes_erp,
    df_pedidos_digip=df_pedidos,
    df_disponible=df_disponible_digip,
)

tab_dashboard, tab_inteligencia, tab_cobertura, tab_operacion = st.tabs(
    [
        "📊 Dashboard",
        "🧠 Inteligencia analítica",
        "🚨 Compromisos sin cobertura",
        "📋 Tabla y gestiones",
    ]
)

with tab_dashboard:
    st.subheader("📊 Panorama operativo de pedidos")
    st.caption(
        "Lectura ejecutiva del pendiente, su volumen, antigüedad "
        "y distribución operativa."
    )

    st.markdown(
        """
        <style>
        .pedidos-kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 8px 0 18px 0;
        }
        .pedidos-kpi-card {
            background: linear-gradient(145deg, #121923 0%, #0f151e 100%);
            border: 1px solid #2a3442;
            border-radius: 10px;
            padding: 16px 18px;
            min-height: 118px;
        }
        .pedidos-kpi-label {
            color: #d8dee9;
            font-size: 0.84rem;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .pedidos-kpi-value {
            color: #f8fafc;
            font-size: 1.85rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .pedidos-kpi-detail {
            color: #9ba8b7;
            font-size: 0.76rem;
            margin-top: 9px;
        }
        .inteligencia-grid {
            grid-template-columns: repeat(6, minmax(0, 1fr));
            margin-bottom: 1rem;
        }
        .inteligencia-card {
            min-height: 128px;
            background:
                linear-gradient(145deg, rgba(20, 29, 41, 0.98), rgba(11, 17, 25, 0.98));
        }
        .inteligencia-card .pedidos-kpi-value {
            font-size: 1.42rem;
            overflow-wrap: anywhere;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(15, 23, 34, 0.58);
            border-color: #2A3543;
            border-radius: 12px;
        }

        .pedidos-panel {
            background: linear-gradient(145deg, #111822 0%, #0d141d 100%);
            border: 1px solid #2a3442;
            border-radius: 10px;
            padding: 12px 14px 4px 14px;
            margin-bottom: 12px;
        }
        @media (max-width: 1100px) {
            .pedidos-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        @media (max-width: 640px) {
            .pedidos-kpi-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if datos_dashboard.empty:
        st.info("No hay pedidos disponibles para analizar.")
    else:
        fecha_min = datos_dashboard["FechaDia"].dropna().min()
        fecha_max = datos_dashboard["FechaDia"].dropna().max()

        with st.expander("🔎 Filtros del dashboard", expanded=False):
            filtro_1, filtro_2, filtro_3, filtro_4, filtro_5 = st.columns(
                [1.25, 1, 1, 1, 0.85]
            )

            with filtro_1:
                rango = st.date_input(
                    "Período de transmisión",
                    value=(
                        fecha_min.date(),
                        fecha_max.date(),
                    )
                    if pd.notna(fecha_min) and pd.notna(fecha_max)
                    else (),
                    key="pedidos_dashboard_periodo",
                )

            with filtro_2:
                estados_filtro = st.multiselect(
                    "Estado del pedido",
                    options=sorted(
                        datos_dashboard["Estado"]
                        .loc[datos_dashboard["Estado"].ne("")]
                        .unique()
                        .tolist()
                    ),
                    default=[],
                )

            with filtro_3:
                preparacion_filtro = st.multiselect(
                    "Preparación",
                    options=sorted(
                        datos_dashboard["CategoriaPreparacion"]
                        .unique()
                        .tolist()
                    ),
                    default=[],
                )

            with filtro_4:
                planificacion_filtro = st.multiselect(
                    "Planificación",
                    options=sorted(
                        datos_dashboard["PlanificacionVisible"]
                        .unique()
                        .tolist()
                    ),
                    default=[],
                )

            with filtro_5:
                incluir_cencosud = st.toggle(
                    "Incluir Cencosud",
                    value=True,
                    key="pedidos_incluir_cencosud",
                    help=(
                        "Encendido: incluye los pedidos de Cencosud. "
                        "Apagado: muestra el pendiente sin Cencosud."
                    ),
                )

        fecha_desde = None
        fecha_hasta = None
        if isinstance(rango, (list, tuple)) and len(rango) == 2:
            fecha_desde, fecha_hasta = rango

        dashboard_filtrado = aplicar_filtros_dashboard(
            datos_dashboard,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estados=estados_filtro,
            preparaciones=preparacion_filtro,
            planificaciones=planificacion_filtro,
            incluir_cencosud=incluir_cencosud,
        )

        kpis = calcular_kpis(dashboard_filtrado)

        pedidos_preparados = int(
            dashboard_filtrado.loc[
                dashboard_filtrado["CategoriaPreparacion"].eq("Preparado"),
                "Pedido",
            ].nunique()
        )
        pedidos_en_preparacion = int(
            dashboard_filtrado.loc[
                dashboard_filtrado["CategoriaPreparacion"].eq("En preparación"),
                "Pedido",
            ].nunique()
        )
        unidades_criticas = int(
            dashboard_filtrado.loc[
                dashboard_filtrado["AntiguedadDias"].gt(5),
                "TotalUnidades",
            ].sum()
        )

        def _fmt_entero(valor):
            return f"{int(valor):,}".replace(",", ".")

        def _fmt_decimal(valor, decimales=2):
            return (
                f"{float(valor):,.{decimales}f}"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        tarjetas = [
            ("📦 Pedidos", _fmt_entero(kpis["pedidos"]),
             f"{_fmt_entero(kpis['unidades'])} unidades"),
            ("💰 Importe pendiente", formatear_importe_compacto(kpis["importe"]),
             "Valor pendiente informado por ERP"),
            ("📐 Volumen", f"{_fmt_decimal(kpis['volumen'])} m³",
             f"{kpis['clientes']} clientes"),
            ("⏳ Antigüedad promedio",
             f"{_fmt_decimal(kpis['antiguedad_promedio'], 1)} días",
             f"{_fmt_entero(unidades_criticas)} unidades con más de 5 días"),
            ("🚨 Pedidos críticos", _fmt_entero(kpis["pedidos_criticos"]),
             "Antigüedad o dimensión excepcional"),
            ("🧰 En preparación", _fmt_entero(pedidos_en_preparacion),
             f"{_fmt_entero(pedidos_preparados)} preparados"),
            ("🚚 Planificaciones", _fmt_entero(kpis["planificaciones"]),
             "Agrupaciones operativas activas"),
            ("👥 Clientes", _fmt_entero(kpis["clientes"]),
             "Clientes incluidos en los filtros"),
        ]

        html_tarjetas = '<div class="pedidos-kpi-grid">'
        for etiqueta, valor, detalle in tarjetas:
            html_tarjetas += (
                '<div class="pedidos-kpi-card">'
                f'<div class="pedidos-kpi-label">{etiqueta}</div>'
                f'<div class="pedidos-kpi-value">{valor}</div>'
                f'<div class="pedidos-kpi-detail">{detalle}</div>'
                '</div>'
            )
        html_tarjetas += "</div>"
        st.markdown(html_tarjetas, unsafe_allow_html=True)

        st.markdown("### Lectura visual del pendiente")

        evolucion_dashboard = resumen_evolucion(dashboard_filtrado)
        resumen_planificacion = resumen_categoria(
            dashboard_filtrado,
            "PlanificacionVisible",
            "Planificación",
            top=10,
            medida="Volumen",
        )

        grafico_1, grafico_2 = st.columns([1.45, 1], vertical_alignment="top")

        with grafico_1:
            st.markdown("#### Evolución de unidades transmitidas")

            if evolucion_dashboard.empty:
                st.info("No hay fechas válidas para graficar.")
            else:
                linea = (
                    alt.Chart(evolucion_dashboard)
                    .mark_line(
                        point=alt.OverlayMarkDef(
                            filled=True,
                            size=60,
                            color="#2563EB",
                        ),
                        strokeWidth=3,
                        color="#1D4ED8",
                    )
                    .encode(
                        x=alt.X(
                            "Fecha:T",
                            title=None,
                            axis=alt.Axis(format="%d/%m"),
                        ),
                        y=alt.Y(
                            "Unidades:Q",
                            title="Unidades",
                            axis=alt.Axis(grid=True),
                        ),
                        tooltip=[
                            alt.Tooltip("FechaVisible:N", title="Fecha"),
                            alt.Tooltip(
                                "Unidades:Q",
                                title="Unidades",
                                format=",.0f",
                            ),
                        ],
                    )
                )

                etiquetas = (
                    alt.Chart(evolucion_dashboard)
                    .mark_text(
                        align="center",
                        baseline="bottom",
                        dy=-8,
                        color="#D7DEE8",
                        fontSize=11,
                        fontWeight=600,
                    )
                    .encode(
                        x="Fecha:T",
                        y="Unidades:Q",
                        text=alt.Text("Unidades:Q", format=",.0f"),
                    )
                )

                st.altair_chart(
                    (linea + etiquetas)
                    .properties(height=310)
                    .configure_view(strokeOpacity=0)
                    .configure_axis(
                        labelColor="#B8C2CF",
                        titleColor="#D8DEE9",
                        gridColor="#26303D",
                        domainColor="#3B4655",
                    ),
                    width="stretch",
                )

        with grafico_2:
            st.markdown("#### Composición del pendiente")

            dimension_composicion = st.radio(
                "Analizar unidades por",
                options=["Sectorización", "Familia"],
                horizontal=True,
                key="pedidos_dimension_composicion",
                label_visibility="collapsed",
            )

            columna_dimension = (
                "Sectorizacion"
                if dimension_composicion == "Sectorización"
                else "Familia"
            )

            pedidos_dashboard = (
                dashboard_filtrado["Pedido"]
                .fillna("")
                .astype(str)
                .str.strip()
                .tolist()
            )

            resumen_composicion = resumen_composicion_detalle(
                tabla_detalle_dashboard,
                pedidos=pedidos_dashboard,
                dimension=columna_dimension,
                top=7,
            )

            if resumen_composicion.empty:
                st.info("No hay detalle disponible para la composición.")
            else:
                nombre_dimension = dimension_composicion
                resumen_composicion = resumen_composicion.copy()
                resumen_composicion["Total"] = (
                    resumen_composicion["Unidades"].sum()
                )
                resumen_composicion["Porcentaje"] = (
                    resumen_composicion["Unidades"]
                    / resumen_composicion["Total"].replace(0, pd.NA)
                    * 100
                ).fillna(0)
                resumen_composicion["Etiqueta"] = (
                    resumen_composicion["Unidades"]
                    .map(lambda valor: f"{int(valor):,}".replace(",", "."))
                    + " | "
                    + resumen_composicion["Porcentaje"]
                    .map(lambda valor: f"{valor:.1f}%")
                )

                paleta_composicion = [
                    "#1E3A5F",
                    "#155E75",
                    "#166534",
                    "#854D0E",
                    "#7C2D12",
                    "#4C1D95",
                    "#374151",
                    "#111827",
                ]

                donut_composicion = (
                    alt.Chart(resumen_composicion)
                    .mark_arc(
                        innerRadius=72,
                        outerRadius=116,
                        stroke="#0B1119",
                        strokeWidth=2,
                    )
                    .encode(
                        theta=alt.Theta("Unidades:Q", stack=True),
                        color=alt.Color(
                            f"{nombre_dimension}:N",
                            scale=alt.Scale(range=paleta_composicion),
                            legend=alt.Legend(
                                orient="right",
                                title=None,
                                labelColor="#D8DEE9",
                                labelLimit=190,
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                f"{nombre_dimension}:N",
                                title=nombre_dimension,
                            ),
                            alt.Tooltip(
                                "Unidades:Q",
                                title="Unidades",
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

                etiquetas_composicion = (
                    alt.Chart(resumen_composicion)
                    .mark_text(
                        radius=137,
                        fontSize=10,
                        fontWeight=600,
                        color="#F8FAFC",
                    )
                    .encode(
                        theta=alt.Theta("Unidades:Q", stack=True),
                        text="Etiqueta:N",
                    )
                )

                total_unidades_composicion = int(
                    resumen_composicion["Unidades"].sum()
                )
                centro_composicion = (
                    alt.Chart(
                        pd.DataFrame(
                            {
                                "texto": [
                                    f"{total_unidades_composicion:,}"
                                    .replace(",", ".")
                                    + "\nUnidades"
                                ]
                            }
                        )
                    )
                    .mark_text(
                        align="center",
                        baseline="middle",
                        fontSize=18,
                        fontWeight=700,
                        color="#F8FAFC",
                        lineBreak="\n",
                    )
                    .encode(text="texto:N")
                )

                st.altair_chart(
                    (
                        donut_composicion
                        + etiquetas_composicion
                        + centro_composicion
                    )
                    .properties(height=310)
                    .configure_view(strokeOpacity=0),
                    width="stretch",
                )

            st.caption(
                "Incluye Cencosud"
                if incluir_cencosud
                else "Vista sin Cencosud"
            )

        st.markdown("#### Volumen por planificación")

        if resumen_planificacion.empty:
            st.info("No hay planificaciones para graficar.")
        else:
            max_volumen = float(
                resumen_planificacion["Volumen"].max()
            )
            resumen_planificacion["EsMayor"] = (
                resumen_planificacion["Volumen"].eq(max_volumen)
            )

            barras = (
                alt.Chart(resumen_planificacion)
                .mark_bar(cornerRadiusEnd=5, size=22)
                .encode(
                    x=alt.X(
                        "Volumen:Q",
                        title="Volumen m³",
                    ),
                    y=alt.Y(
                        "Planificación:N",
                        sort="-x",
                        title=None,
                    ),
                    color=alt.condition(
                        "datum.EsMayor",
                        alt.value("#1D4ED8"),
                        alt.value("#27496D"),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "Planificación:N",
                            title="Planificación",
                        ),
                        alt.Tooltip(
                            "Volumen:Q",
                            title="Volumen m³",
                            format=".2f",
                        ),
                    ],
                )
            )

            etiquetas = (
                alt.Chart(resumen_planificacion)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=7,
                    color="#E5E7EB",
                    fontSize=11,
                    fontWeight=600,
                )
                .encode(
                    x="Volumen:Q",
                    y=alt.Y("Planificación:N", sort="-x"),
                    text=alt.Text("Volumen:Q", format=".2f"),
                )
            )

            st.altair_chart(
                (barras + etiquetas)
                .properties(height=max(260, len(resumen_planificacion) * 34))
                .configure_view(strokeOpacity=0)
                .configure_axis(
                    labelColor="#B8C2CF",
                    titleColor="#D8DEE9",
                    gridColor="#26303D",
                    domainColor="#3B4655",
                ),
                width="stretch",
            )

        detalle_1, detalle_2 = st.columns(2, vertical_alignment="top")

        with detalle_1:
            st.markdown("#### Clientes con mayor carga")

            clientes_carga = resumen_categoria(
                dashboard_filtrado,
                "ClienteVisible",
                "Cliente",
                top=8,
                medida="Unidades",
            )

            if clientes_carga.empty:
                st.info("No hay clientes para mostrar.")
            else:
                barras_clientes = (
                    alt.Chart(clientes_carga)
                    .mark_bar(cornerRadiusEnd=4, color="#4C1D95")
                    .encode(
                        x=alt.X("Unidades:Q", title="Unidades"),
                        y=alt.Y("Cliente:N", sort="-x", title=None),
                        tooltip=[
                            alt.Tooltip("Cliente:N"),
                            alt.Tooltip(
                                "Unidades:Q",
                                format=",.0f",
                            ),
                        ],
                    )
                )
                texto_clientes = (
                    alt.Chart(clientes_carga)
                    .mark_text(
                        align="left",
                        baseline="middle",
                        dx=6,
                        color="#E5E7EB",
                    )
                    .encode(
                        x="Unidades:Q",
                        y=alt.Y("Cliente:N", sort="-x"),
                        text=alt.Text("Unidades:Q", format=",.0f"),
                    )
                )
                st.altair_chart(
                    (barras_clientes + texto_clientes)
                    .properties(height=300)
                    .configure_view(strokeOpacity=0)
                    .configure_axis(
                        labelColor="#B8C2CF",
                        titleColor="#D8DEE9",
                        gridColor="#26303D",
                    ),
                    width="stretch",
                )

        with detalle_2:
            st.markdown("#### Antigüedad de pedidos")

            antiguedad = resumen_categoria(
                dashboard_filtrado,
                "RangoAntiguedad",
                "Antigüedad",
                medida="Pedidos",
            )

            orden_antiguedad = [
                "Hoy",
                "1 día",
                "2 días",
                "3 a 5 días",
                "Más de 5 días",
            ]

            if antiguedad.empty:
                st.info("No hay antigüedad para mostrar.")
            else:
                barras_antiguedad = (
                    alt.Chart(antiguedad)
                    .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                    .encode(
                        x=alt.X(
                            "Antigüedad:N",
                            sort=orden_antiguedad,
                            title=None,
                        ),
                        y=alt.Y("Pedidos:Q", title="Pedidos"),
                        color=alt.Color(
                            "Antigüedad:N",
                            sort=orden_antiguedad,
                            scale=alt.Scale(
                                domain=orden_antiguedad,
                                range=[
                                    "#1E3A5F",
                                    "#27496D",
                                    "#8A5A00",
                                    "#9A3412",
                                    "#7F1D1D",
                                ],
                            ),
                            legend=None,
                        ),
                        tooltip=[
                            alt.Tooltip("Antigüedad:N"),
                            alt.Tooltip("Pedidos:Q"),
                        ],
                    )
                )
                texto_antiguedad = (
                    alt.Chart(antiguedad)
                    .mark_text(
                        baseline="bottom",
                        dy=-6,
                        color="#F8FAFC",
                        fontWeight=600,
                    )
                    .encode(
                        x=alt.X(
                            "Antigüedad:N",
                            sort=orden_antiguedad,
                        ),
                        y="Pedidos:Q",
                        text="Pedidos:Q",
                    )
                )
                st.altair_chart(
                    (barras_antiguedad + texto_antiguedad)
                    .properties(height=300)
                    .configure_view(strokeOpacity=0)
                    .configure_axis(
                        labelColor="#B8C2CF",
                        titleColor="#D8DEE9",
                        gridColor="#26303D",
                    ),
                    width="stretch",
                )


with tab_inteligencia:
    st.subheader("🧠 Inteligencia analítica del pendiente")
    st.caption(
        "Lectura de concentración, tendencia, antigüedad y dimensión "
        "operativa sobre los mismos filtros aplicados en Dashboard."
    )

    if datos_dashboard.empty:
        st.info("No hay pedidos disponibles para analizar.")
    else:
        # Se reutilizan los filtros definidos en Dashboard.
        # Streamlit ejecuta la página completa en cada interacción.
        if "dashboard_filtrado" not in locals():
            dashboard_filtrado = datos_dashboard.copy()

        inteligencia = indicadores_inteligencia(
            dashboard_filtrado
        )

        tendencia = inteligencia["tendencia_reciente"]
        tendencia_texto = (
            f"{tendencia:+.1f}%"
            if tendencia is not None
            else "Sin base"
        )

        tarjetas_inteligencia = [
            (
                "📦 Unidades / pedido",
                f"{inteligencia['unidades_promedio_pedido']:.1f}",
                "Dimensión media del pedido",
            ),
            (
                "📐 M³ / pedido",
                f"{inteligencia['volumen_promedio_pedido']:.2f}",
                "Volumen medio operativo",
            ),
            (
                "🎯 Concentración Top 5",
                f"{inteligencia['concentracion_top_5']:.1f}%",
                "Participación de los 5 principales clientes",
            ),
            (
                "🏢 Cliente principal",
                inteligencia["cliente_principal"],
                (
                    f"{inteligencia['participacion_cliente_principal']:.1f}% "
                    "de las unidades"
                ),
            ),
            (
                "⏳ Pedidos +5 días",
                f"{inteligencia['pedidos_mas_5_dias']:,}".replace(",", "."),
                (
                    f"{inteligencia['unidades_mas_5_dias']:,} unidades"
                ).replace(",", "."),
            ),
            (
                "📈 Tendencia reciente",
                tendencia_texto,
                "Comparación contra el bloque anterior",
            ),
        ]

        html_inteligencia = '<div class="pedidos-kpi-grid inteligencia-grid">'
        for etiqueta, valor, detalle in tarjetas_inteligencia:
            html_inteligencia += (
                '<div class="pedidos-kpi-card inteligencia-card">'
                f'<div class="pedidos-kpi-label">{etiqueta}</div>'
                f'<div class="pedidos-kpi-value">{valor}</div>'
                f'<div class="pedidos-kpi-detail">{detalle}</div>'
                '</div>'
            )
        html_inteligencia += "</div>"
        st.markdown(html_inteligencia, unsafe_allow_html=True)

        st.divider()

        analitica_1, analitica_2 = st.columns([1.45, 1])

        with analitica_1:
            st.markdown(
                "#### Pareto de clientes por unidades"
            )
            tabla_pareto = resumen_clientes_analitico(
                dashboard_filtrado,
                top=12,
            )
            pareto_clientes(tabla_pareto)

        with analitica_2:
            st.markdown(
                "#### Unidades por antigüedad"
            )
            antiguedad_unidades = resumen_categoria(
                dashboard_filtrado,
                "RangoAntiguedad",
                "Antigüedad",
                medida="Unidades",
            )
            barras_antiguedad_unidades(
                antiguedad_unidades
            )

        st.markdown("### Diagnóstico operativo avanzado")

        avanzada_1, avanzada_2 = st.columns([1.15, 1])

        with avanzada_1:
            st.markdown("#### ABC de la composición")

            dimension_abc = st.radio(
                "Dimensión ABC",
                options=["Familia", "Sectorización"],
                horizontal=True,
                key="pedidos_dimension_abc",
                label_visibility="collapsed",
            )
            columna_abc = (
                "Familia"
                if dimension_abc == "Familia"
                else "Sectorizacion"
            )
            tabla_abc = resumen_abc_detalle(
                tabla_detalle_dashboard,
                pedidos=dashboard_filtrado[
                    "Pedido"
                ].tolist(),
                dimension=columna_abc,
            )

            grafico_abc(
                tabla_abc.head(15),
                dimension_abc,
            )

            st.caption(
                "Clase A: hasta 80% acumulado · "
                "Clase B: 80–95% · Clase C: restante. "
                "El importe no se reparte por familia porque "
                "el detalle no contiene valor por línea."
            )

        with avanzada_2:
            st.markdown("#### Riesgo operativo")

            riesgo = evaluar_riesgo_operativo(
                dashboard_filtrado,
                inteligencia,
            )

            color_riesgo = {
                "Alto": "error",
                "Medio": "warning",
                "Bajo": "success",
            }.get(riesgo["nivel"], "info")

            mensaje_riesgo = (
                f"Nivel {riesgo['nivel']} · "
                f"{riesgo['puntaje']} puntos"
            )

            if color_riesgo == "error":
                st.error(mensaje_riesgo, icon="🔴")
            elif color_riesgo == "warning":
                st.warning(mensaje_riesgo, icon="🟡")
            elif color_riesgo == "success":
                st.success(mensaje_riesgo, icon="🟢")
            else:
                st.info(mensaje_riesgo)

            for motivo in riesgo["motivos"]:
                st.markdown(f"- {motivo}")

            st.markdown("#### Clientes calientes")
            clientes_impacto = resumen_clientes_impacto(
                dashboard_filtrado,
                top=8,
            )
            grafico_impacto_clientes(
                clientes_impacto
            )

        analitica_3, analitica_4 = st.columns(2)

        with analitica_3:
            st.markdown(
                "#### Productividad por planificación"
            )
            tabla_planificacion = (
                resumen_planificacion_analitico(
                    dashboard_filtrado
                )
            )

            st.dataframe(
                tabla_planificacion,
                width="stretch",
                hide_index=True,
                height=min(
                    420,
                    75 + len(tabla_planificacion) * 35,
                ),
                column_config={
                    "Pedidos": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "Unidades": st.column_config.NumberColumn(
                        format="%d"
                    ),
                    "Volumen": st.column_config.NumberColumn(
                        "Volumen (m³)",
                        format="%.2f",
                    ),
                    "Unidades por pedido": (
                        st.column_config.NumberColumn(
                            format="%.1f"
                        )
                    ),
                    "M3 por pedido": (
                        st.column_config.NumberColumn(
                            "M³ por pedido",
                            format="%.2f",
                        )
                    ),
                },
            )

        with analitica_4:
            st.markdown("#### Señales de gestión")

            if (
                inteligencia["concentracion_top_5"]
                >= 60
            ):
                st.warning(
                    (
                        "Alta concentración: los cinco principales "
                        f"clientes representan "
                        f"{inteligencia['concentracion_top_5']:.1f}% "
                        "de las unidades pendientes."
                    ),
                    icon="⚠️",
                )
            else:
                st.success(
                    (
                        "La carga está relativamente distribuida: "
                        f"el Top 5 concentra "
                        f"{inteligencia['concentracion_top_5']:.1f}%."
                    ),
                    icon="✅",
                )

            if inteligencia["pedidos_mas_5_dias"] > 0:
                st.error(
                    (
                        f"Hay {inteligencia['pedidos_mas_5_dias']} "
                        "pedido(s) con más de 5 días, por "
                        f"{inteligencia['unidades_mas_5_dias']:,} "
                        "unidades."
                    ).replace(",", "."),
                    icon="⏳",
                )
            else:
                st.success(
                    "No hay pedidos con más de 5 días.",
                    icon="✅",
                )

            if tendencia is not None:
                if tendencia > 10:
                    st.warning(
                        (
                            "La carga reciente está creciendo: "
                            f"{tendencia:+.1f}% frente al bloque "
                            "de fechas anterior."
                        ),
                        icon="📈",
                    )
                elif tendencia < -10:
                    st.success(
                        (
                            "La carga reciente está bajando: "
                            f"{tendencia:+.1f}% frente al bloque "
                            "de fechas anterior."
                        ),
                        icon="📉",
                    )
                else:
                    st.info(
                        (
                            "La carga reciente se mantiene estable: "
                            f"{tendencia:+.1f}%."
                        ),
                        icon="➡️",
                    )

            st.info(
                (
                    "Cliente con mayor impacto: "
                    f"{inteligencia['cliente_principal']} "
                    f"({inteligencia['participacion_cliente_principal']:.1f}% "
                    "de las unidades)."
                ),
                icon="🏢",
            )

        st.markdown(
            "#### Priorización por complejidad operativa"
        )
        st.caption(
            "El puntaje combina antigüedad, unidades, volumen, "
            "SKU, cantidad de familias e importe. El ranking es "
            "relativo al conjunto filtrado y explica sus motivos."
        )

        tabla_criticos = indice_complejidad_pedidos(
            dashboard_filtrado,
            tabla_detalle_dashboard,
            limite=20,
        )

        st.dataframe(
            tabla_criticos,
            width="stretch",
            hide_index=True,
            height=min(
                560,
                75 + len(tabla_criticos) * 35,
            ),
            column_config={
                "Pedido": st.column_config.TextColumn(
                    width="small"
                ),
                "Cliente": st.column_config.TextColumn(
                    width="large"
                ),
                "Prioridad": st.column_config.NumberColumn(
                    "#",
                    format="%d",
                    width="small",
                ),
                "Puntaje": st.column_config.ProgressColumn(
                    "Complejidad",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                    width="medium",
                ),
                "Días": st.column_config.NumberColumn(
                    format="%d"
                ),
                "Unidades": st.column_config.NumberColumn(
                    format="%d"
                ),
                "SKU": st.column_config.NumberColumn(
                    format="%d"
                ),
                "Familias": st.column_config.NumberColumn(
                    format="%d"
                ),
                "M3": st.column_config.NumberColumn(
                    "M³",
                    format="%.2f",
                ),
                "Importe": st.column_config.NumberColumn(
                    "Importe",
                    format="$ %.0f",
                ),
                "Planificación": st.column_config.TextColumn(
                    width="medium"
                ),
                "Motivos": st.column_config.TextColumn(
                    width="large"
                ),
            },
        )


with tab_cobertura:
    st.subheader("🚨 Compromisos ERP sin cobertura")
    st.caption(
        "Pedidos que permanecen pendientes en el ERP y no están activos actualmente en DIGIP. "
        "Una transmisión histórica anterior no los excluye del análisis."
    )

    if resumen_cobertura_erp.empty:
        st.success("No hay pedidos pendientes fuera de DIGIP para evaluar.")
    else:
        total_pedidos = int(resumen_cobertura_erp["Pedido"].nunique())
        con_faltante = int(resumen_cobertura_erp["UnidadesFaltantes"].gt(0).sum())
        sin_cobertura = int(resumen_cobertura_erp["EstadoCobertura"].eq("Sin cobertura").sum())
        unidades_faltantes = float(resumen_cobertura_erp["UnidadesFaltantes"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pendientes fuera de DIGIP", f"{total_pedidos:,}".replace(",", "."))
        c2.metric("Pedidos con faltante", f"{con_faltante:,}".replace(",", "."))
        c3.metric("Sin cobertura", f"{sin_cobertura:,}".replace(",", "."))
        c4.metric("Unidades faltantes", f"{unidades_faltantes:,.0f}".replace(",", "."))

        solo_faltantes = st.toggle(
            "Mostrar solamente pedidos con faltante", value=True,
            key="pedidos_solo_faltantes_cobertura",
        )
        vista_resumen = resumen_cobertura_erp.copy()
        if solo_faltantes:
            vista_resumen = vista_resumen.loc[vista_resumen["UnidadesFaltantes"].gt(0)].copy()

        pedidos_visibles = set(vista_resumen["Pedido"].astype(str))
        vista_lineas = lineas_cobertura_erp.loc[
            lineas_cobertura_erp["Pedido"].astype(str).isin(pedidos_visibles)
        ].copy()

        if solo_faltantes:
            vista_lineas = vista_lineas.loc[
                vista_lineas["CantidadFaltante"].gt(0)
            ].copy()

        # =====================================================
        # CONSOLIDADO DE CÓDIGOS CON FALTANTE
        # =====================================================
        lineas_codigos = lineas_cobertura_erp.loc[
            lineas_cobertura_erp["Pedido"].astype(str).isin(pedidos_visibles)
        ].copy()

        if lineas_codigos.empty:
            resumen_codigos_faltantes = pd.DataFrame(
                columns=[
                    "ArticuloCodigo",
                    "ArticuloDescripcion",
                    "Disponible",
                    "Comprometido",
                    "Faltante",
                    "PedidosAfectados",
                ]
            )
        else:
            resumen_codigos_faltantes = (
                lineas_codigos
                .groupby(
                    ["ArticuloCodigo", "ArticuloDescripcion"],
                    as_index=False,
                    dropna=False,
                )
                .agg(
                    Disponible=("StockDisponibleInicial", "max"),
                    Comprometido=("CantidadSolicitada", "sum"),
                    Faltante=("CantidadFaltante", "sum"),
                    PedidosAfectados=("Pedido", "nunique"),
                )
            )

            resumen_codigos_faltantes = (
                resumen_codigos_faltantes
                .loc[resumen_codigos_faltantes["Faltante"].gt(0)]
                .sort_values(
                    by=["Faltante", "Comprometido", "ArticuloCodigo"],
                    ascending=[False, False, True],
                )
                .reset_index(drop=True)
            )

            for columna in [
                "Disponible",
                "Comprometido",
                "Faltante",
                "PedidosAfectados",
            ]:
                resumen_codigos_faltantes[columna] = (
                    pd.to_numeric(
                        resumen_codigos_faltantes[columna],
                        errors="coerce",
                    )
                    .fillna(0)
                    .astype(int)
                )

        columna_tablas, columna_codigos = st.columns(
            [1, 1],
            gap="large",
            vertical_alignment="top",
        )

        with columna_tablas:
            st.markdown("#### Resumen por pedido")
            st.dataframe(
                vista_resumen,
                hide_index=True,
                width="stretch",
                height=300,
                column_config={
                    "Fecha": st.column_config.DateColumn(
                        "Fecha",
                        format="DD/MM/YYYY",
                    ),
                    "PorcentajeCobertura": st.column_config.ProgressColumn(
                        "Cobertura",
                        min_value=0,
                        max_value=100,
                        format="%.1f %%",
                    ),
                    "UnidadesFaltantes": st.column_config.NumberColumn(
                        "Faltante",
                        format="%.0f",
                    ),
                },
            )

            st.markdown("#### Detalle de artículos")
            st.dataframe(
                vista_lineas,
                hide_index=True,
                width="stretch",
                height=390,
                column_config={
                    "Fecha": st.column_config.DateColumn(
                        "Fecha",
                        format="DD/MM/YYYY",
                    ),
                    "CantidadSolicitada": st.column_config.NumberColumn(
                        "Solicitado",
                        format="%d",
                    ),
                    "StockDisponibleInicial": st.column_config.NumberColumn(
                        "Disponible inicial",
                        format="%d",
                    ),
                    "CantidadCubierta": st.column_config.NumberColumn(
                        "Cubierto",
                        format="%d",
                    ),
                    "CantidadFaltante": st.column_config.NumberColumn(
                        "Faltante",
                        format="%d",
                    ),
                },
            )

        with columna_codigos:
            st.markdown("#### Artículos comprometidos sin stock")
            st.caption(
                "Consolidado por código de las ventas pendientes fuera de DIGIP."
            )

            if resumen_codigos_faltantes.empty:
                st.success(
                    "No hay artículos con faltante para los pedidos visibles."
                )
            else:
                st.dataframe(
                    resumen_codigos_faltantes,
                    hide_index=True,
                    width="stretch",
                    height=750,
                    column_config={
                        "ArticuloCodigo": st.column_config.TextColumn(
                            "Código",
                            width="small",
                        ),
                        "ArticuloDescripcion": st.column_config.TextColumn(
                            "Descripción",
                            width="large",
                        ),
                        "Disponible": st.column_config.NumberColumn(
                            "Disponible",
                            format="%d",
                        ),
                        "Comprometido": st.column_config.NumberColumn(
                            "Comprometido",
                            format="%d",
                        ),
                        "Faltante": st.column_config.NumberColumn(
                            "Faltante",
                            format="%d",
                        ),
                        "PedidosAfectados": st.column_config.NumberColumn(
                            "Pedidos",
                            format="%d",
                        ),
                    },
                )

        col_descarga1, col_descarga2, col_descarga3 = st.columns(3)
        with col_descarga1:
            st.download_button(
                "⬇️ Descargar resumen",
                data=vista_resumen.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig"),
                file_name="Pedidos_ERP_Sin_Cobertura.csv", mime="text/csv",
                key="descargar_resumen_cobertura_erp", width="stretch",
            )
        with col_descarga2:
            st.download_button(
                "⬇️ Descargar detalle",
                data=vista_lineas.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig"),
                file_name="Detalle_Pedidos_ERP_Sin_Cobertura.csv", mime="text/csv",
                key="descargar_detalle_cobertura_erp", width="stretch",
            )
        with col_descarga3:
            st.download_button(
                "⬇️ Descargar artículos",
                data=resumen_codigos_faltantes.to_csv(
                    index=False,
                    sep=";",
                    encoding="utf-8-sig",
                ).encode("utf-8-sig"),
                file_name="Articulos_Comprometidos_Sin_Stock.csv",
                mime="text/csv",
                key="descargar_articulos_sin_stock_erp",
                width="stretch",
            )


with tab_operacion:
    # =====================================================
    # AVISO Y GESTIÓN DE SOLICITUDES COMERCIALES
    # =====================================================

    ESTADOS_SOLICITUD = [
        "Pendiente",
        "En revisión",
        "En curso",
        "Finalizada",
    ]


    # =====================================================
    # RECLAMOS PENDIENTES
    # =====================================================

    ESTADOS_RECLAMO_GESTION = [
        "Pendiente",
        "En revisión",
        "En gestión",
        "Resuelto",
        "Rechazado",
    ]


    @st.dialog(
        "🧾 Gestionar reclamos",
        width="large",
    )
    def abrir_reclamos_pendientes() -> None:
        """
        Permite consultar y gestionar los reclamos abiertos sin
        ocupar espacio permanente en la página de Pedidos.
        """

        reclamos_actuales = obtener_reclamos_abiertos()

        if reclamos_actuales is None or reclamos_actuales.empty:
            st.success(
                "No hay reclamos pendientes de revisión.",
                icon="✅",
            )
            return

        tabla_reclamos = reclamos_actuales.copy()

        columnas_reclamos = [
            "ReclamoID",
            "Pedido",
            "Remito",
            "Cliente",
            "FechaReclamo",
            "TipoReclamo",
            "Descripcion",
            "Responsable",
            "EstadoReclamo",
            "Resolucion",
            "UsuarioCreador",
            "FechaCreacion",
            "FechaCierre",
        ]

        for columna in columnas_reclamos:
            if columna not in tabla_reclamos.columns:
                tabla_reclamos[columna] = ""

        tabla_reclamos["FechaCreacionOrden"] = pd.to_datetime(
            tabla_reclamos["FechaCreacion"],
            errors="coerce",
        )

        tabla_reclamos["FechaCreacionVisible"] = (
            tabla_reclamos["FechaCreacionOrden"]
            .dt.strftime("%d/%m/%Y %H:%M")
            .fillna(
                tabla_reclamos["FechaCreacion"]
                .fillna("")
                .astype(str)
            )
        )

        tabla_reclamos = (
            tabla_reclamos
            .sort_values(
                by="FechaCreacionOrden",
                ascending=False,
                na_position="last",
            )
            .reset_index(drop=True)
        )

        total_reclamos = len(tabla_reclamos)
        pedidos_afectados = tabla_reclamos["Pedido"].nunique()

        resumen_1, resumen_2 = st.columns(2)
        resumen_1.metric("Reclamos abiertos", total_reclamos)
        resumen_2.metric("Pedidos involucrados", pedidos_afectados)

        opciones_reclamo = {}

        for _, fila in tabla_reclamos.iterrows():
            reclamo_id = str(fila.get("ReclamoID", "")).strip()
            pedido = str(fila.get("Pedido", "")).strip()
            cliente = str(fila.get("Cliente", "")).strip()
            incidencia = str(fila.get("TipoReclamo", "")).strip()
            estado = str(fila.get("EstadoReclamo", "")).strip()

            etiqueta = (
                f"{pedido or 'Sin pedido'} · "
                f"{incidencia or 'Sin incidencia'} · "
                f"{estado or 'Pendiente'} · "
                f"{cliente or 'Cliente sin identificar'}"
            )
            opciones_reclamo[etiqueta] = reclamo_id

        etiqueta_seleccionada = st.selectbox(
            "Seleccionar reclamo",
            options=list(opciones_reclamo.keys()),
            key="selector_reclamo_gestion",
        )

        reclamo_id = opciones_reclamo[etiqueta_seleccionada]

        coincidencia = tabla_reclamos.loc[
            tabla_reclamos["ReclamoID"]
            .astype(str)
            .eq(str(reclamo_id))
        ]

        if coincidencia.empty:
            st.error("No se encontró el reclamo seleccionado.")
            return

        reclamo = coincidencia.iloc[0]

        pedido = str(reclamo.get("Pedido", "")).strip()
        remito = str(reclamo.get("Remito", "")).strip()
        cliente = str(reclamo.get("Cliente", "")).strip()
        incidencia = str(reclamo.get("TipoReclamo", "")).strip()
        descripcion = str(reclamo.get("Descripcion", "")).strip()
        registrado_por = str(reclamo.get("UsuarioCreador", "")).strip()
        fecha_creacion = str(
            reclamo.get("FechaCreacionVisible", "")
        ).strip()
        responsable_actual = str(
            reclamo.get("Responsable", "")
        ).strip()
        resolucion_actual = str(
            reclamo.get("Resolucion", "")
        ).strip()
        estado_actual = str(
            reclamo.get("EstadoReclamo", "Pendiente")
        ).strip()

        if estado_actual not in ESTADOS_RECLAMO_GESTION:
            estado_actual = "Pendiente"

        cabecera_1, cabecera_2, cabecera_3 = st.columns(
            [1, 2.4, 1.2],
            vertical_alignment="center",
        )

        with cabecera_1:
            st.metric("Pedido", pedido or "Sin dato")

        with cabecera_2:
            st.markdown(f"**{cliente or 'Cliente sin identificar'}**")
            st.caption(
                f"{incidencia or 'Reclamo'} · Remito {remito or 'Sin dato'}"
            )

        with cabecera_3:
            st.metric("Estado", estado_actual)

        st.info(
            descripcion or "El reclamo no tiene descripción.",
            icon="📝",
        )

        datos_1, datos_2, datos_3 = st.columns(3)

        with datos_1:
            st.caption(
                f"**Registrado por**  \n{registrado_por or 'Sin dato'}"
            )

        with datos_2:
            st.caption(
                f"**Fecha de creación**  \n{fecha_creacion or 'Sin dato'}"
            )

        with datos_3:
            st.caption(
                f"**Responsable actual**  \n"
                f"{responsable_actual or 'Logistica'}"
            )

        detalle_reclamos = leer_reclamos_detalle()

        if detalle_reclamos is not None and not detalle_reclamos.empty:
            detalle_seleccionado = detalle_reclamos.loc[
                detalle_reclamos["ReclamoID"]
                .astype(str)
                .eq(str(reclamo_id))
            ].copy()

            if not detalle_seleccionado.empty:
                st.markdown("#### Artículos reclamados")

                columnas_detalle = [
                    "CodigoArticulo",
                    "DescripcionArticulo",
                    "Cantidad",
                    "Observacion",
                ]

                for columna in columnas_detalle:
                    if columna not in detalle_seleccionado.columns:
                        detalle_seleccionado[columna] = ""

                st.dataframe(
                    detalle_seleccionado[columnas_detalle].rename(
                        columns={
                            "CodigoArticulo": "Código",
                            "DescripcionArticulo": "Descripción",
                            "Cantidad": "Cantidad reclamada",
                            "Observacion": "Detalle de cantidades",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                )

        fotos_reclamos = leer_reclamos_fotos()

        if fotos_reclamos is not None and not fotos_reclamos.empty:
            fotos_seleccionadas = fotos_reclamos.loc[
                fotos_reclamos["ReclamoID"]
                .astype(str)
                .eq(str(reclamo_id))
            ].copy()

            if not fotos_seleccionadas.empty:
                st.markdown("#### Fotografías")

                for posicion, (_, foto) in enumerate(
                    fotos_seleccionadas.iterrows(),
                    start=1,
                ):
                    nombre_foto = str(
                        foto.get("NombreArchivo", f"Fotografía {posicion}")
                    ).strip()
                    url_foto = str(
                        foto.get("URLArchivo", "")
                    ).strip()

                    if url_foto:
                        st.link_button(
                            f"📷 {nombre_foto or f'Fotografía {posicion}'}",
                            url_foto,
                            width="stretch",
                        )

        st.divider()

        with st.form(
            f"form_gestion_reclamo_{reclamo_id}",
            clear_on_submit=False,
        ):
            formulario_1, formulario_2 = st.columns([1, 2])

            with formulario_1:
                nuevo_estado_reclamo = st.selectbox(
                    "Estado",
                    options=ESTADOS_RECLAMO_GESTION,
                    index=ESTADOS_RECLAMO_GESTION.index(
                        estado_actual
                    ),
                )

            with formulario_2:
                resolucion_reclamo = st.text_area(
                    "Respuesta / resolución",
                    value=resolucion_actual,
                    placeholder=(
                        "Detalle de la revisión, respuesta al reclamo "
                        "o solución aplicada por Logística..."
                    ),
                    height=120,
                )

            guardar_reclamo = st.form_submit_button(
                "💾 Guardar gestión del reclamo",
                type="primary",
                width="stretch",
            )

        if guardar_reclamo:
            usuario_logistica = (
                st.session_state.get("usuario")
                or st.session_state.get("nombre_usuario")
                or "Logistica"
            )

            try:
                resultado = actualizar_reclamo(
                    reclamo_id=reclamo_id,
                    estado_reclamo=nuevo_estado_reclamo,
                    resolucion=resolucion_reclamo,
                    responsable=usuario_logistica,
                )

                st.toast("Reclamo actualizado.", icon="✅")

                # Fuerza el rerun completo de la aplicación para cerrar
                # el diálogo después de guardar la gestión.
                st.rerun(scope="app")

            except Exception as error:
                st.error("No se pudo actualizar el reclamo.")
                st.exception(error)


    @st.dialog(
        "📚 Histórico de reclamos",
        width="large",
    )
    def abrir_historico_reclamos() -> None:
        """
        Muestra todos los reclamos guardados en Google Sheets,
        tanto abiertos como cerrados, sin permitir su modificación.
        """

        reclamos_historicos = leer_reclamos()

        if reclamos_historicos is None or reclamos_historicos.empty:
            st.info(
                "Todavía no hay reclamos registrados.",
                icon="🧾",
            )
            return

        tabla_historica = reclamos_historicos.copy()

        columnas_requeridas = [
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

        for columna in columnas_requeridas:
            if columna not in tabla_historica.columns:
                tabla_historica[columna] = ""

        tabla_historica["Pedido"] = (
            tabla_historica["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

        tabla_historica["FechaCreacionOrden"] = pd.to_datetime(
            tabla_historica["FechaCreacion"],
            errors="coerce",
        )

        tabla_historica["FechaVisible"] = (
            tabla_historica["FechaCreacionOrden"]
            .dt.strftime("%d/%m/%Y %H:%M")
            .fillna(
                tabla_historica["FechaCreacion"]
                .fillna("")
                .astype(str)
            )
        )

        tabla_historica["FechaCierreVisible"] = (
            pd.to_datetime(
                tabla_historica["FechaCierre"],
                errors="coerce",
            )
            .dt.strftime("%d/%m/%Y %H:%M")
            .fillna(
                tabla_historica["FechaCierre"]
                .fillna("")
                .astype(str)
            )
            .replace("", "Abierto")
        )

        tabla_historica = (
            tabla_historica
            .sort_values(
                "FechaCreacionOrden",
                ascending=False,
                na_position="last",
            )
            .reset_index(drop=True)
        )

        estados = sorted(
            estado
            for estado in tabla_historica["EstadoReclamo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
            if estado
        )

        filtro_1, filtro_2 = st.columns([2, 1])

        with filtro_1:
            busqueda = st.text_input(
                "Buscar",
                placeholder="Pedido, remito, cliente, incidencia o ID...",
                key="buscar_historico_reclamos_pedidos",
            )

        with filtro_2:
            estado_filtro = st.selectbox(
                "Estado",
                options=["Todos"] + estados,
                key="estado_historico_reclamos_pedidos",
            )

        reclamos_filtrados = tabla_historica.copy()

        if busqueda.strip():
            texto_busqueda = busqueda.strip()
            mascara = pd.Series(False, index=reclamos_filtrados.index)

            for columna in [
                "ReclamoID",
                "Pedido",
                "Remito",
                "Cliente",
                "TipoReclamo",
            ]:
                mascara = mascara | (
                    reclamos_filtrados[columna]
                    .fillna("")
                    .astype(str)
                    .str.contains(
                        texto_busqueda,
                        case=False,
                        na=False,
                        regex=False,
                    )
                )

            reclamos_filtrados = reclamos_filtrados.loc[mascara].copy()

        if estado_filtro != "Todos":
            reclamos_filtrados = reclamos_filtrados[
                reclamos_filtrados["EstadoReclamo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq(estado_filtro)
            ].copy()

        tabla_visible = (
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
                    "FechaCierreVisible",
                ]
            ]
            .rename(
                columns={
                    "ReclamoID": "ID",
                    "TipoReclamo": "Incidencia",
                    "EstadoReclamo": "Estado",
                    "FechaVisible": "Fecha alta",
                    "FechaCierreVisible": "Fecha cierre",
                }
            )
            .reset_index(drop=True)
        )

        st.caption(
            f"{len(tabla_visible):,} reclamo(s) registrado(s)"
            .replace(",", ".")
        )

        evento = st.dataframe(
            tabla_visible,
            width="stretch",
            hide_index=True,
            height=min(420, 85 + len(tabla_visible) * 35),
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_historico_reclamos_pedidos",
            column_config={
                "ID": None,
                "Pedido": st.column_config.TextColumn(width="small"),
                "Remito": st.column_config.TextColumn(width="small"),
                "Cliente": st.column_config.TextColumn(width="large"),
                "Incidencia": st.column_config.TextColumn(width="medium"),
                "Estado": st.column_config.TextColumn(width="small"),
                "Responsable": st.column_config.TextColumn(width="small"),
                "Fecha alta": st.column_config.TextColumn(width="small"),
                "Fecha cierre": st.column_config.TextColumn(width="small"),
            },
        )

        filas = evento.selection.rows if evento is not None else []

        if not filas:
            st.caption(
                "Seleccioná un registro para ver su descripción y resolución."
            )
            return

        reclamo = (
            reclamos_filtrados
            .reset_index(drop=True)
            .iloc[filas[0]]
        )

        st.divider()

        detalle_1, detalle_2, detalle_3 = st.columns([1, 2.3, 1])
        detalle_1.metric("Pedido", str(reclamo.get("Pedido", "")) or "Sin dato")

        with detalle_2:
            st.markdown(
                f"**{str(reclamo.get('Cliente', '')).strip() or 'Cliente sin identificar'}**"
            )
            st.caption(
                f"{str(reclamo.get('TipoReclamo', '')).strip() or 'Reclamo'} · "
                f"Remito {str(reclamo.get('Remito', '')).strip() or 'Sin dato'}"
            )

        detalle_3.metric(
            "Estado",
            str(reclamo.get("EstadoReclamo", "")).strip() or "Sin estado",
        )

        st.info(
            str(reclamo.get("Descripcion", "")).strip()
            or "El reclamo no tiene descripción.",
            icon="📝",
        )

        resolucion = str(reclamo.get("Resolucion", "")).strip()

        if resolucion:
            st.success(resolucion, icon="✅")
        else:
            st.warning(
                "El reclamo todavía no tiene una resolución registrada.",
                icon="⏳",
            )

        info_1, info_2, info_3 = st.columns(3)
        info_1.caption(
            f"**Registrado por**  \n"
            f"{str(reclamo.get('UsuarioCreador', '')).strip() or 'Sin dato'}"
        )
        info_2.caption(
            f"**Fecha de alta**  \n"
            f"{str(reclamo.get('FechaVisible', '')).strip() or 'Sin dato'}"
        )
        info_3.caption(
            f"**Fecha de cierre**  \n"
            f"{str(reclamo.get('FechaCierreVisible', '')).strip() or 'Abierto'}"
        )

        reclamo_id = str(reclamo.get("ReclamoID", "")).strip()
        detalle_reclamos = leer_reclamos_detalle()

        if detalle_reclamos is not None and not detalle_reclamos.empty:
            detalle_seleccionado = detalle_reclamos.loc[
                detalle_reclamos["ReclamoID"]
                .astype(str)
                .eq(reclamo_id)
            ].copy()

            if not detalle_seleccionado.empty:
                st.markdown("#### Artículos reclamados")
                columnas_detalle = [
                    "CodigoArticulo",
                    "DescripcionArticulo",
                    "Cantidad",
                    "Observacion",
                ]

                for columna in columnas_detalle:
                    if columna not in detalle_seleccionado.columns:
                        detalle_seleccionado[columna] = ""

                st.dataframe(
                    detalle_seleccionado[columnas_detalle].rename(
                        columns={
                            "CodigoArticulo": "Código",
                            "DescripcionArticulo": "Descripción",
                            "Cantidad": "Cantidad reclamada",
                            "Observacion": "Detalle de cantidades",
                        }
                    ),
                    width="stretch",
                    hide_index=True,
                )

        fotos_reclamos = leer_reclamos_fotos()

        if fotos_reclamos is not None and not fotos_reclamos.empty:
            fotos_seleccionadas = fotos_reclamos.loc[
                fotos_reclamos["ReclamoID"]
                .astype(str)
                .eq(reclamo_id)
            ].copy()

            if not fotos_seleccionadas.empty:
                st.markdown("#### Fotografías")

                for posicion, (_, foto) in enumerate(
                    fotos_seleccionadas.iterrows(),
                    start=1,
                ):
                    nombre = str(
                        foto.get("NombreArchivo", f"Fotografía {posicion}")
                    ).strip()
                    url = str(foto.get("URLArchivo", "")).strip()

                    if url:
                        st.link_button(
                            f"📷 {nombre or f'Fotografía {posicion}'}",
                            url,
                            width="stretch",
                        )


    reclamos_totales_historial = leer_reclamos()

    if reclamos_totales_historial is None:
        reclamos_totales_historial = pd.DataFrame()

    if not reclamos_abiertos.empty:

        cantidad_reclamos_abiertos = len(reclamos_abiertos)
        pedidos_con_reclamo = (
            reclamos_abiertos["Pedido"].nunique()
            if "Pedido" in reclamos_abiertos.columns
            else 0
        )

        aviso_reclamo, boton_reclamo, boton_historico = st.columns(
            [4.6, 1.25, 1.15],
            vertical_alignment="center",
        )

        with aviso_reclamo:
            st.warning(
                (
                    f"Hay {cantidad_reclamos_abiertos} reclamo(s) "
                    f"pendiente(s) de revisión sobre "
                    f"{pedidos_con_reclamo} pedido(s)."
                ),
                icon="🧾",
            )

        with boton_reclamo:
            ver_reclamos_pendientes = st.button(
                "Gestionar reclamos",
                icon="🧾",
                type="primary",
                width="stretch",
                key="btn_ver_reclamos_pendientes",
            )

        with boton_historico:
            ver_historico_reclamos = st.button(
                "Histórico",
                icon="📚",
                width="stretch",
                key="btn_historico_reclamos_pedidos",
            )

        if ver_reclamos_pendientes:
            abrir_reclamos_pendientes()

        if ver_historico_reclamos:
            abrir_historico_reclamos()

    else:
        aviso_sin_reclamos, boton_historico = st.columns(
            [5.85, 1.15],
            vertical_alignment="center",
        )

        with aviso_sin_reclamos:
            st.success(
                "No hay reclamos pendientes de revisión.",
                icon="✅",
            )

        with boton_historico:
            ver_historico_reclamos = st.button(
                "Histórico",
                icon="📚",
                width="stretch",
                disabled=reclamos_totales_historial.empty,
                key="btn_historico_reclamos_pedidos_sin_abiertos",
            )

        if ver_historico_reclamos:
            abrir_historico_reclamos()


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
    # El planificador de camionetas fue trasladado a 03_Despachos.py.

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