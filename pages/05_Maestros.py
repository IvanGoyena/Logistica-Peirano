from config import *


from utils.autenticacion import requerir_roles
from models.pedidos import construir_tabla_pedidos

requerir_roles(
    "admin",
    "gerencia",
)

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

from utils.leer_fuente_flexible import leer_archivo_flexible

from models.pendiente import (
    construir_tabla_pendientes
)

from models.transmisiones import (
    construir_tabla_transmisiones
)

from models.expresos import (
    construir_tabla_expresos
)

from models.clientes import (
    construir_tabla_clientes
)

from models.volumetria import (
    construir_tabla_volumetria
)

from models.metricas import (
    leer_historico_controles,
    leer_historico_preparaciones,
)

from models.sincronizar_clientes import (
    validar_maestro_clientes,
    actualizar_maestro_clientes,
)

import streamlit as st
import pandas as pd


# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(
    page_title="Maestros",
    page_icon="⚙️",
    layout="wide"
)


# =====================================================
# FUNCIONES AUXILIARES
# =====================================================

@st.cache_data(max_entries=15)
def dataframe_a_csv(df):
    """
    Convierte un DataFrame en CSV descargable,
    compatible con Excel en español.
    """

    return (
        df.to_csv(
            index=False,
            sep=";",
            encoding="utf-8-sig"
        )
        .encode("utf-8-sig")
    )

    """
    Convierte un DataFrame en CSV descargable,
    compatible con Excel en español.
    """

    return (
        df.to_csv(
            index=False,
            sep=";",
            encoding="utf-8-sig"
        )
        .encode("utf-8-sig")
    )


def mostrar_tarjeta_reporte(
    titulo,
    icono,
    dataframe,
    nombre_archivo_fuente,
    nombre_descarga,
    key_boton,
    carpeta=CARPETA_DATOS
):
    """
    Muestra el estado, cantidad de registros,
    fecha del archivo y botón de descarga.
    """

    cantidad_registros = len(dataframe)

    if cantidad_registros > 0:

        st.success(
            f"{icono} {titulo}"
        )

    else:

        st.warning(
            f"{icono} {titulo}"
        )

    st.metric(
        "Registros",
        f"{cantidad_registros:,}".replace(",", ".")
    )

    try:

        ultima_actualizacion = fecha_archivo(
            carpeta,
            nombre_archivo_fuente
        )

    except Exception:

        ultima_actualizacion = (
            "Fecha de actualización no disponible"
        )

    st.caption(
        f"🕒 {ultima_actualizacion}"
    )

    st.download_button(
        label="⬇️ Descargar",
        data=dataframe_a_csv(dataframe),
        file_name=nombre_descarga,
        mime="text/csv",
        key=key_boton,
        width="stretch"
    )


# =====================================================
# CARGA CONTROLADA DE FUENTES
# =====================================================

@st.cache_data(
    show_spinner="Cargando reportes operativos...",
)
def cargar_fuentes_operativas():
    """
    Lee una sola vez las fuentes dinámicas y ERP.

    Los reruns normales de Streamlit —filtros, botones,
    multiselección o checkboxes— reutilizan estos DataFrames
    desde memoria y no vuelven a consultar Google Drive.
    """

    return {
        "tareas": leer_archivo(
            CARPETA_DATOS,
            "Informe Tareas",
            cache=False,
        ),
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
    }


@st.cache_data(
    show_spinner="Cargando reportes de stock...",
)
def cargar_fuentes_stock():
    """Lee las cuatro fuentes reales de stock y la configuración Max & Min."""

    configuracion = {
        "stock_detallado": ["stock_detallado", "Stock_Detallado", "Stock Detallado"],
        "stock_recepcion": ["stock_recepcion", "Stock_Recepcion", "Stock Recepcion"],
        "disponible": ["Disponible Digip", "Disponible_Digip", "disponible_digip"],
        "calidad": ["stock_calidad_laboratorio", "Stock_Calidad_Laboratorio"],
        "max_min": ["Max & Min", "Max_Min", "max_min"],
    }

    resultado = {}
    for clave, nombres in configuracion.items():
        df, _ = leer_archivo_flexible(
            CARPETA_DATOS,
            nombres,
            cache=False,
        )
        resultado[clave] = df

    return resultado


@st.cache_data(
    show_spinner="Cargando maestros de planificación...",
)
def cargar_maestros_planificacion():
    """
    Mantiene los maestros en una caché independiente.

    Después de incorporar clientes nuevos se limpia solamente
    esta función, evitando volver a descargar los reportes
    operativos y ERP que no fueron modificados.
    """

    return {
        "articulos": leer_archivo(
            CARPETA_DATOS,
            "Maestro Articulo",
            cache=True,
        ),
        "clientes": leer_archivo(
            CARPETA_DATOS,
            "Maestro Clientes",
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
    }


@st.cache_data(
    show_spinner="Cargando históricos de métricas...",
)
def cargar_historicos_metricas():
    """Lee los históricos una sola vez durante la sesión."""

    return {
        "control": leer_historico_controles(
            CARPETA_DATOS,
        ),
        "preparacion": leer_historico_preparaciones(
            CARPETA_DATOS,
        ),
    }


fuentes_operativas = cargar_fuentes_operativas()
fuentes_stock = cargar_fuentes_stock()
maestros_planificacion = cargar_maestros_planificacion()
historicos_metricas = cargar_historicos_metricas()

# Se entregan copias para que las transformaciones posteriores
# no modifiquen accidentalmente los objetos guardados en caché.
df_tareas = fuentes_operativas["tareas"].copy()
df_pedidos = fuentes_operativas["pedidos"].copy()
df_detalle = fuentes_operativas["detalle"].copy()
df_pendientes_erp = fuentes_operativas["pendientes_erp"].copy()
df_transmisiones = fuentes_operativas["transmisiones"].copy()

df_stock_detallado = fuentes_stock["stock_detallado"].copy()
df_stock_recepcion = fuentes_stock["stock_recepcion"].copy()
df_disponible_digip = fuentes_stock["disponible"].copy()
df_stock_calidad = fuentes_stock["calidad"].copy()
df_max_min = fuentes_stock["max_min"].copy()

df_articulos = maestros_planificacion["articulos"].copy()
df_clientes = maestros_planificacion["clientes"].copy()
df_expresos = maestros_planificacion["expresos"].copy()
df_volumetria = maestros_planificacion["volumetria"].copy()

df_historico_control = historicos_metricas["control"].copy()
df_historico_preparacion = historicos_metricas[
    "preparacion"
].copy()

# =====================================================
# CONSTRUCCIÓN DE TABLAS LIMPIAS
# =====================================================

tabla_pendientes_erp = construir_tabla_pendientes(
    df_pendientes_erp
)

tabla_transmisiones = construir_tabla_transmisiones(
    df_transmisiones
)

tabla_expresos = construir_tabla_expresos(
    df_expresos
)

tabla_clientes = construir_tabla_clientes(
    df_clientes
)

tabla_volumetria = construir_tabla_volumetria(
    df_volumetria
)


tabla_pedidos = construir_tabla_pedidos(
    df_pedidos,
    df_detalle,
    df_articulos,
    tabla_clientes,
    df_volumetria
)

# =====================================================
# CATÁLOGO DE REPORTES
# =====================================================

reportes = [

    {
        "titulo": "Informe Tareas",
        "icono": "📋",
        "dataframe": df_tareas,
        "fuente": "Informe Tareas",
        "descarga": "Informe_Tareas.csv",
        "key": "descarga_informe_tareas",
    },

    {
        "titulo": "Pedidos DIGIP",
        "icono": "📦",
        "dataframe": df_pedidos,
        "fuente": "Pedidos DIGIP",
        "descarga": "Pedidos_DIGIP.csv",
        "key": "descarga_pedidos_digip",
    },

    {
        "titulo": "Detalle Pendientes",
        "icono": "📑",
        "dataframe": df_detalle,
        "fuente": "Detalle Pendientes",
        "descarga": "Detalle_Pendientes.csv",
        "key": "descarga_detalle_pendientes",
    },

    {
        "titulo": "Pedidos Pendientes ERP",
        "icono": "🧾",
        "dataframe": tabla_pendientes_erp,
        "fuente": "Pedidos Pendientes",
        "descarga": "Pedidos_Pendientes_ERP_Limpio.csv",
        "key": "descarga_pendientes_erp",
    },

    {
        "titulo": "Transmisiones ERP",
        "icono": "🔄",
        "dataframe": tabla_transmisiones,
        "fuente": "Pedidos Transmicion",
        "descarga": "Transmisiones_ERP_Limpio.csv",
        "key": "descarga_transmisiones_erp",
    },

    {
        "titulo": "Stock detallado",
        "icono": "🏭",
        "dataframe": df_stock_detallado,
        "fuente": "stock_detallado",
        "descarga": "Stock_Detallado.csv",
        "key": "descarga_stock_detallado",
    },

    {
        "titulo": "Stock recepción",
        "icono": "📥",
        "dataframe": df_stock_recepcion,
        "fuente": "stock_recepcion",
        "descarga": "Stock_Recepcion.csv",
        "key": "descarga_stock_recepcion",
    },

    {
        "titulo": "Disponible DIGIP",
        "icono": "📦",
        "dataframe": df_disponible_digip,
        "fuente": "Disponible Digip",
        "descarga": "Disponible_Digip.csv",
        "key": "descarga_disponible_digip",
    },

    {
        "titulo": "Stock Calidad / Laboratorio",
        "icono": "🧪",
        "dataframe": df_stock_calidad,
        "fuente": "stock_calidad_laboratorio",
        "descarga": "Stock_Calidad_Laboratorio.csv",
        "key": "descarga_stock_calidad",
    },

    {
        "titulo": "Max & Min Picking",
        "icono": "⚙️",
        "dataframe": df_max_min,
        "fuente": "Max & Min",
        "descarga": "Max_y_Min_Picking.csv",
        "key": "descarga_max_min",
    },

    {
        "titulo": "Maestro Artículos",
        "icono": "📚",
        "dataframe": df_articulos,
        "fuente": "Maestro Articulo",
        "descarga": "Maestro_Articulos.csv",
        "key": "descarga_maestro_articulos",
    },

    {
        "titulo": "Maestro Clientes",
        "icono": "👥",
        "dataframe": tabla_clientes,
        "fuente": "Maestro Clientes",
        "descarga": "Maestro_Clientes_Limpio.csv",
        "key": "descarga_maestro_clientes",
    },

    {
        "titulo": "Maestro Expresos",
        "icono": "🚚",
        "dataframe": tabla_expresos,
        "fuente": "Datos Expresos",
        "descarga": "Maestro_Expresos_Limpio.csv",
        "key": "descarga_maestro_expresos",
    },

    {
    "titulo": "Maestro Volumetría",
    "icono": "📐",
    "dataframe": tabla_volumetria,
    "fuente": "Maestro Volumetria",
    "descarga": "Maestro_Volumetria_Limpio.csv",
    "key": "descarga_maestro_volumetria",
    },

    {
        "titulo": "Histórico Control",
        "icono": "✅",
        "dataframe": df_historico_control,
        "fuente": "Control",
        "descarga": "Historico_Control_Crudo.csv",
        "key": "descarga_historico_control",
    },

    {
        "titulo": "Histórico Preparación",
        "icono": "📦",
        "dataframe": df_historico_preparacion,
        "fuente": "Preparacion",
        "descarga": "Historico_Preparacion_Crudo.csv",
        "key": "descarga_historico_preparacion",
    },
]


# =====================================================
# CABECERA
# =====================================================

st.title("⚙️ Maestros")

st.caption(
    "Estado, actualización y descarga de las fuentes "
    "utilizadas por el Sistema Logístico"
)

st.markdown("---")


# =====================================================
# RESUMEN GENERAL
# =====================================================

st.subheader("📊 Resumen del Sistema")

total_reportes = len(reportes)

total_registros = sum(
    len(reporte["dataframe"])
    for reporte in reportes
)

reportes_con_datos = sum(
    len(reporte["dataframe"]) > 0
    for reporte in reportes
)

col_resumen1, col_resumen2, col_resumen3 = st.columns(3)

with col_resumen1:

    st.metric(
        "Reportes",
        total_reportes
    )

with col_resumen2:

    st.metric(
        "Registros totales",
        f"{total_registros:,}".replace(",", ".")
    )

with col_resumen3:

    if reportes_con_datos == total_reportes:

        st.metric(
            "Estado",
            "🟢 OK"
        )

    else:

        st.metric(
            "Estado",
            "🟠 Revisar"
        )

st.markdown("---")


# =====================================================
# FUENTES DINÁMICAS
# =====================================================

st.subheader("⚡ Fuentes Dinámicas")

st.caption(
    "Reportes que se actualizan durante la operación."
)

col1, col2 = st.columns(2)

with col1:

    mostrar_tarjeta_reporte(
        titulo="Informe Tareas",
        icono="📋",
        dataframe=df_tareas,
        nombre_archivo_fuente="Informe Tareas",
        nombre_descarga="Informe_Tareas.csv",
        key_boton="boton_tareas"
    )

with col2:

    mostrar_tarjeta_reporte(
        titulo="Pedidos DIGIP",
        icono="📦",
        dataframe=df_pedidos,
        nombre_archivo_fuente="Pedidos DIGIP",
        nombre_descarga="Pedidos_DIGIP.csv",
        key_boton="boton_pedidos_digip"
    )

st.markdown("---")


# =====================================================
# FUENTES DE STOCK
# =====================================================

st.subheader("📊 Fuentes de Stock")
st.caption("Reportes reales del WMS utilizados por el módulo de Stock.")

col_stock1, col_stock2, col_stock3 = st.columns(3)

with col_stock1:
    mostrar_tarjeta_reporte(
        titulo="Stock detallado",
        icono="🏭",
        dataframe=df_stock_detallado,
        nombre_archivo_fuente="stock_detallado",
        nombre_descarga="Stock_Detallado.csv",
        key_boton="boton_stock_detallado",
    )

with col_stock2:
    mostrar_tarjeta_reporte(
        titulo="Stock recepción",
        icono="📥",
        dataframe=df_stock_recepcion,
        nombre_archivo_fuente="stock_recepcion",
        nombre_descarga="Stock_Recepcion.csv",
        key_boton="boton_stock_recepcion",
    )

with col_stock3:
    mostrar_tarjeta_reporte(
        titulo="Disponible DIGIP",
        icono="📦",
        dataframe=df_disponible_digip,
        nombre_archivo_fuente="Disponible Digip",
        nombre_descarga="Disponible_Digip.csv",
        key_boton="boton_disponible_digip",
    )

col_stock4, col_stock5 = st.columns(2)

with col_stock4:
    mostrar_tarjeta_reporte(
        titulo="Stock Calidad / Laboratorio",
        icono="🧪",
        dataframe=df_stock_calidad,
        nombre_archivo_fuente="stock_calidad_laboratorio",
        nombre_descarga="Stock_Calidad_Laboratorio.csv",
        key_boton="boton_stock_calidad",
    )

with col_stock5:
    mostrar_tarjeta_reporte(
        titulo="Max & Min Picking",
        icono="⚙️",
        dataframe=df_max_min,
        nombre_archivo_fuente="Max & Min",
        nombre_descarga="Max_y_Min_Picking.csv",
        key_boton="boton_max_min",
    )

st.markdown("---")

# =====================================================
# FUENTES ERP
# =====================================================

st.subheader("🏢 Fuentes ERP")

st.caption(
    "Reportes extraídos del ERP y actualizados manualmente."
)

col3, col4, col5 = st.columns(3)

with col3:

    mostrar_tarjeta_reporte(
        titulo="Detalle Pendientes",
        icono="📑",
        dataframe=df_detalle,
        nombre_archivo_fuente="Detalle Pendientes",
        nombre_descarga="Detalle_Pendientes.csv",
        key_boton="boton_detalle"
    )

with col4:

    mostrar_tarjeta_reporte(
        titulo="Pedidos Pendientes ERP",
        icono="🧾",
        dataframe=tabla_pendientes_erp,
        nombre_archivo_fuente="Pedidos Pendientes",
        nombre_descarga="Pedidos_Pendientes_ERP_Limpio.csv",
        key_boton="boton_pendientes_erp"
    )

with col5:

    mostrar_tarjeta_reporte(
        titulo="Transmisiones ERP",
        icono="🔄",
        dataframe=tabla_transmisiones,
        nombre_archivo_fuente="Pedidos Transmicion",
        nombre_descarga="Transmisiones_ERP_Limpio.csv",
        key_boton="boton_transmisiones"
    )

st.markdown("---")


# =====================================================
# MAESTROS DE PLANIFICACIÓN
# =====================================================

st.subheader("🗺️ Maestros de Planificación")

st.caption(
    "Fuentes utilizadas para enriquecer la planificación "
    "de clientes, zonas y expresos."
)

col6, col7, col8, col9 = st.columns(4)

with col6:

    mostrar_tarjeta_reporte(
        titulo="Maestro Artículos",
        icono="📚",
        dataframe=df_articulos,
        nombre_archivo_fuente="Maestro Articulo",
        nombre_descarga="Maestro_Articulos.csv",
        key_boton="boton_articulos"
    )

with col7:

    mostrar_tarjeta_reporte(
        titulo="Maestro Clientes",
        icono="👥",
        dataframe=tabla_clientes,
        nombre_archivo_fuente="Maestro Clientes",
        nombre_descarga="Maestro_Clientes_Limpio.csv",
        key_boton="boton_clientes"
    )

with col8:

    mostrar_tarjeta_reporte(
        titulo="Maestro Expresos",
        icono="🚚",
        dataframe=tabla_expresos,
        nombre_archivo_fuente="Datos Expresos",
        nombre_descarga="Maestro_Expresos_Limpio.csv",
        key_boton="boton_expresos"
    )

    with col9:

        mostrar_tarjeta_reporte(
        titulo="Maestro Volumetría",
        icono="📐",
        dataframe=tabla_volumetria,
        nombre_archivo_fuente="Maestro Volumetria",
        nombre_descarga="Maestro_Volumetria_Limpio.csv",
        key_boton="boton_volumetria"
    )

    st.markdown("---")
# =====================================================
# SINCRONIZACIÓN MAESTRO CLIENTES
# =====================================================

st.subheader("👥 Actualización de nuevos clientes")

st.caption(
    "Primero valida los códigos logísticos nuevos, propone su planificación "
    "y luego permite seleccionar cuáles incorporar al Maestro Clientes."
)

mensaje_alta = st.session_state.pop(
    "mensaje_actualizacion_clientes",
    None,
)

if mensaje_alta:
    st.success(mensaje_alta)

if "validacion_clientes_resultado" not in st.session_state:
    st.session_state["validacion_clientes_resultado"] = None

if st.button(
    "🔍 Validar actualización de clientes",
    type="primary",
    width="stretch",
    key="validar_actualizacion_clientes",
):

    with st.spinner("Analizando códigos logísticos y planificación..."):
        try:
            resultado = validar_maestro_clientes(
                tabla_clientes=tabla_clientes,
                tabla_pendientes=df_pendientes_erp,
                df_pedidos_digip=df_pedidos,
            )
            st.session_state["validacion_clientes_resultado"] = resultado

        except Exception as error:
            st.session_state["validacion_clientes_resultado"] = None
            st.error(f"No se pudo completar la validación: {error}")

resultado_clientes = st.session_state.get(
    "validacion_clientes_resultado"
)

if isinstance(resultado_clientes, pd.DataFrame):

    if resultado_clientes.empty:
        st.success(
            "El Maestro Clientes está actualizado: no se detectaron "
            "códigos logísticos nuevos en Pedidos Pendientes ERP."
        )

    else:
        cantidad_total = len(resultado_clientes)
        cantidad_listos = int(
            resultado_clientes["ListoParaAlta"].fillna(False).sum()
        )
        cantidad_revision = cantidad_total - cantidad_listos
        sin_despacho = int(
            resultado_clientes["Estado"]
            .eq("SIN_CODIGO_DESPACHO")
            .sum()
        )

        col_sync_1, col_sync_2, col_sync_3, col_sync_4 = st.columns(4)

        with col_sync_1:
            st.metric("Clientes nuevos", cantidad_total)

        with col_sync_2:
            st.metric("Listos para alta", cantidad_listos)

        with col_sync_3:
            st.metric("Requieren revisión", cantidad_revision)

        with col_sync_4:
            st.metric("Sin código despacho", sin_despacho)

        columnas_vista = [
            "Estado",
            "ListoParaAlta",
            "CodigoLogistico",
            "CodigoCliente",
            "Cliente",
            "Distribuidor",
            "PedidoReferencia",
            "CodigoDespacho",
            "Zona",
            "EntregaPropuesta",
            "PreparacionPropuesta",
            "MetodoInferencia",
            "ClientesReferencia",
            "CombinacionesDetectadas",
            "ConfianzaPorcentaje",
            "ObservacionValidacion",
        ]

        columnas_vista = [
            columna
            for columna in columnas_vista
            if columna in resultado_clientes.columns
        ]

        st.dataframe(
            resultado_clientes[columnas_vista],
            hide_index=True,
            width="stretch",
            column_config={
                "ListoParaAlta": st.column_config.CheckboxColumn(
                    "Listo",
                    disabled=True,
                ),
                "ConfianzaPorcentaje": st.column_config.ProgressColumn(
                    "Confianza",
                    min_value=0,
                    max_value=100,
                    format="%.1f %%",
                ),
            },
        )

        with st.expander("Ver todos los campos detectados"):
            st.dataframe(
                resultado_clientes,
                hide_index=True,
                width="stretch",
            )

        st.download_button(
            label="⬇️ Descargar validación",
            data=dataframe_a_csv(resultado_clientes),
            file_name="Validacion_Nuevos_Clientes.csv",
            mime="text/csv",
            key="descargar_validacion_clientes",
            width="stretch",
        )

        st.markdown("#### ✅ Seleccionar registros para actualizar")

        registros_listos = resultado_clientes.loc[
            resultado_clientes["ListoParaAlta"].fillna(False)
        ].copy()

        if registros_listos.empty:
            st.warning(
                "No hay registros habilitados para actualización. Los casos "
                "con observaciones deben resolverse antes de incorporarlos."
            )

        else:
            opciones = registros_listos["CodigoLogistico"].tolist()
            descripcion_por_codigo = {
                fila["CodigoLogistico"]: (
                    f"{fila['CodigoLogistico']} — {fila['Cliente']} — "
                    f"Entrega {fila['EntregaPropuesta']} / "
                    f"Preparación {fila['PreparacionPropuesta']}"
                )
                for _, fila in registros_listos.iterrows()
            }

            seleccionados = st.multiselect(
                "Clientes a incorporar al Maestro Clientes",
                options=opciones,
                default=opciones,
                format_func=lambda codigo: descripcion_por_codigo.get(
                    codigo,
                    codigo,
                ),
                key="clientes_seleccionados_actualizacion",
                help=(
                    "Solo aparecen registros que superaron la validación. "
                    "Podés quitar de la selección los que no quieras cargar."
                ),
            )

            registros_seleccionados = registros_listos.loc[
                registros_listos["CodigoLogistico"].isin(seleccionados)
            ].copy()

            st.caption(
                f"Se actualizarán {len(registros_seleccionados)} de "
                f"{len(registros_listos)} registros listos."
            )

            confirmar_actualizacion = st.checkbox(
                "Confirmo que revisé la planificación de los clientes "
                "seleccionados.",
                key="confirmar_actualizacion_maestro_clientes",
            )

            actualizar_clientes = st.button(
                "💾 Actualizar registros seleccionados",
                type="primary",
                width="stretch",
                key="actualizar_registros_maestro_clientes",
                disabled=(
                    registros_seleccionados.empty
                    or not confirmar_actualizacion
                ),
            )

            if actualizar_clientes:
                with st.spinner(
                    "Creando respaldo y actualizando Maestro Clientes..."
                ):
                    try:
                        resumen_actualizacion = actualizar_maestro_clientes(
                            registros_seleccionados=(
                                registros_seleccionados
                            ),
                            carpeta_datos=CARPETA_DATOS,
                            nombre_base="Maestro Clientes",
                        )

                        cantidad_agregados = resumen_actualizacion[
                            "cantidad_agregados"
                        ]
                        cantidad_omitidos = resumen_actualizacion[
                            "cantidad_omitidos"
                        ]

                        # Solo cambió Maestro Clientes. Se invalida la
                        # caché de maestros para leer el XLSM actualizado,
                        # sin volver a descargar las fuentes operativas,
                        # ERP ni los históricos.
                        cargar_maestros_planificacion.clear()

                        st.session_state.pop(
                            "validacion_clientes_resultado",
                            None,
                        )
                        st.session_state.pop(
                            "clientes_seleccionados_actualizacion",
                            None,
                        )
                        st.session_state.pop(
                            "confirmar_actualizacion_maestro_clientes",
                            None,
                        )

                        mensaje = (
                            f"Maestro Clientes actualizado: "
                            f"{cantidad_agregados} registro(s) agregado(s)."
                        )

                        if cantidad_omitidos:
                            mensaje += (
                                f" {cantidad_omitidos} registro(s) ya "
                                "existían y fueron omitidos."
                            )

                        st.session_state[
                            "mensaje_actualizacion_clientes"
                        ] = mensaje

                        st.rerun()

                    except Exception as error:
                        st.error(
                            "No se pudo actualizar el maestro. "
                            f"{error}"
                        )

st.markdown("---")


# =====================================================
# HISTÓRICOS DE MÉTRICAS
# =====================================================

st.subheader("📈 Históricos de Métricas")

st.caption(
    "Reportes mensuales crudos utilizados para construir "
    "la base analítica de Control y Preparación."
)

col_hist1, col_hist2 = st.columns(2)

with col_hist1:

    mostrar_tarjeta_reporte(
        titulo="Histórico Control",
        icono="✅",
        dataframe=df_historico_control,
        nombre_archivo_fuente="Control",
        nombre_descarga="Historico_Control_Crudo.csv",
        key_boton="boton_historico_control",
    )

with col_hist2:

    mostrar_tarjeta_reporte(
        titulo="Histórico Preparación",
        icono="📦",
        dataframe=df_historico_preparacion,
        nombre_archivo_fuente="Preparacion",
        nombre_descarga="Historico_Preparacion_Crudo.csv",
        key_boton="boton_historico_preparacion",
    )

st.markdown("---")


# =====================================================
# INFORMACIÓN
# =====================================================

st.info(
    """
    Esta pantalla concentra todas las fuentes utilizadas
    por el Sistema Logístico.

    **Fuentes dinámicas**
    - Informe Tareas.
    - Pedidos DIGIP.

    **Fuentes de Stock**
    - Stock Almacén.
    - Stock_Picking.
    - Stock_Recepciones.
    - Stock Calidad / Laboratorio.
    - Max & Min Picking.

    **Fuentes ERP**
    - Detalle Pendientes.
    - Pedidos Pendientes ERP.
    - Transmisiones ERP.

    **Maestros de planificación**
    - Maestro Artículos.
    - Maestro Clientes.
    - Maestro Expresos.
    - Maestro Volumetría.

    Los botones descargan la versión utilizada por el sistema.
    En las tablas satélite se descarga la versión ya limpia.
    """
)