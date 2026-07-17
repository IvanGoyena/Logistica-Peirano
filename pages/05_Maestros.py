from config import *

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

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
        use_container_width=True
    )


# =====================================================
# CARGA DE FUENTES
# =====================================================

# -----------------------------------------------------
# FUENTES DINÁMICAS
# -----------------------------------------------------

df_tareas = leer_archivo(
    CARPETA_DATOS,
    "Informe Tareas",
    cache=False
)

df_pedidos = leer_archivo(
    CARPETA_DATOS,
    "Pedidos DIGIP",
    cache=False
)


# -----------------------------------------------------
# FUENTES ERP
# -----------------------------------------------------

df_detalle = leer_archivo(
    CARPETA_DATOS,
    "Detalle Pendientes",
    cache=False
)

df_pendientes_erp = leer_archivo(
    CARPETA_DATOS,
    "Pedidos Pendientes",
    cache=False
)

df_transmisiones = leer_archivo(
    CARPETA_DATOS,
    "Pedidos Transmicion",
    cache=False
)


# -----------------------------------------------------
# MAESTROS CON CACHÉ
# -----------------------------------------------------

df_articulos = leer_archivo(
    CARPETA_DATOS,
    "Maestro Articulo",
    cache=True
)

df_clientes = leer_archivo(
    CARPETA_DATOS,
    "Maestro Clientes",
    cache=False
)

df_expresos = leer_archivo(
    CARPETA_DATOS,
    "Datos Expresos",
    cache=True
)

df_volumetria = leer_archivo(
    CARPETA_DATOS,
    "Maestro Volumetria",
    cache=False
)

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
# INFORMACIÓN
# =====================================================

st.info(
    """
    Esta pantalla concentra todas las fuentes utilizadas
    por el Sistema Logístico.

    **Fuentes dinámicas**
    - Informe Tareas.
    - Pedidos DIGIP.

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