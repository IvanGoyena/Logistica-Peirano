from config import *

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

import streamlit as st

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(

    page_title="Maestros",

    page_icon="⚙",

    layout="wide"

)

# =====================================================
# CARGA DE DATOS
# =====================================================

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

df_detalle = leer_archivo(
    CARPETA_DATOS,
    "Detalle Pendientes",
    cache=False
)

df_clientes = leer_archivo(
    CARPETA_DATOS,
    "Maestro Clientes",
    cache=True
)

df_articulos = leer_archivo(
    CARPETA_DATOS,
    "Maestro Articulo",
    cache=True
)


# =====================================================
# CABECERA
# =====================================================

st.title("⚙ Maestros")

st.caption(
    "Estado de actualización de las fuentes de datos"
)

st.markdown("---")

# =====================================================
# ESTADO DEL SISTEMA
# =====================================================

st.subheader("📂 Estado del Sistema")

col1, col2, col3 = st.columns(3)

# -----------------------------------------------------

with col1:

    st.success("📋 Informe Tareas")

    st.metric(
        "Registros",
        len(df_tareas)
    )

    st.caption(

        fecha_archivo(
            CARPETA_DATOS,
            "Informe Tareas"
        )

    )

# -----------------------------------------------------

with col2:

    st.success("📦 Pedidos DIGIP")

    st.metric(
        "Registros",
        len(df_pedidos)
    )

    st.caption(

        fecha_archivo(
            CARPETA_DATOS,
            "Pedidos DIGIP"
        )

    )

# -----------------------------------------------------

with col3:

    st.success("👤 Maestro Clientes")

    st.metric(
        "Registros",
        len(df_clientes)
    )

    st.caption(

        fecha_archivo(
            CARPETA_DATOS,
            "Maestro Clientes"
        )

    )

# =====================================================

col4, col5, col6 = st.columns(3)

# -----------------------------------------------------

with col4:

    st.success("📑 Detalle Pendientes")

    st.metric(
        "Registros",
        len(df_detalle)
    )

    st.caption(

        fecha_archivo(
            CARPETA_DATOS,
            "Detalle Pendientes"
        )

    )

# -----------------------------------------------------

with col5:

    st.success("📚 Maestro Artículos")

    st.metric(
        "Registros",
        len(df_articulos)
    )

    st.caption(

        fecha_archivo(
            CARPETA_DATOS,
            "Maestro Articulo"
        )

    )

# -----------------------------------------------------

with col6:

    st.info("➕ Próximamente")

    st.metric(
        "Reportes",
        "..."
    )

    st.caption(
        "Espacio reservado"
    )

st.markdown("---")

# =====================================================
# RESUMEN
# =====================================================

st.subheader("📈 Resumen")

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(

        "Reportes",

        5

    )

with col2:

    st.metric(

        "Registros Totales",

        f"{len(df_tareas)+len(df_pedidos)+len(df_detalle)+len(df_clientes)+len(df_articulos):,}"

    )

with col3:

    st.metric(

        "Estado",

        "🟢 OK"

    )

st.markdown("---")

# =====================================================
# INFORMACIÓN
# =====================================================

st.info(
"""
Esta pantalla concentra el estado de todos los reportes utilizados por el Sistema Logístico.

Desde aquí se controlará:

- Actualización de archivos.
- Cantidad de registros.
- Calidad de datos.
- Integridad de maestros.
- Estado de sincronización con DIGIP.
"""
)