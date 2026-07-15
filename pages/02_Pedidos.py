from config import *

from utils.leer_datos import (
    leer_archivo
)

from models.detalle import (
    construir_tabla_detalle,
    construir_resumen_pedidos
)

from models.pedidos import (
    construir_tabla_pedidos,
)

import streamlit as st

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(

    page_title="Pedidos",

    page_icon="📦",

    layout="wide"

)

# =====================================================
# CARGA
# =====================================================

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

df_articulos = leer_archivo(
    CARPETA_DATOS,
    "Maestro Articulo",
    cache=False
)

df_clientes = leer_archivo(
    CARPETA_DATOS,
    "Maestro Clientes",
    cache=True
)


# =====================================================
# TABLA
# =====================================================

tabla = construir_tabla_pedidos(

    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes

)


tabla_detalle = construir_tabla_detalle(

    df_detalle,

    df_articulos

)

resumen = construir_resumen_pedidos(

    tabla_detalle

)



# =====================================================
# VISUALIZACIÓN
# =====================================================

st.title("📦 Modelo de Pedidos")

st.caption(
    "Construcción de la tabla operativa"
)

st.markdown("---")

st.dataframe(

    tabla,

    width="stretch",

    hide_index=True,

    height=750

)

st.dataframe(

    resumen,

    width="stretch",

    hide_index=True,

    height=500

)

