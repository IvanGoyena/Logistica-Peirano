from config import *

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

from models.tareas import (
    construir_tabla_tareas,
    obtener_resumen_operativo,
    obtener_tabla_operativa
)

import streamlit as st

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(
    page_title="Gestión de Tareas",
    page_icon="📋",
    layout="wide"
)

# =====================================================
# CARGA DE DATOS
# =====================================================

df_tareas = leer_archivo(
    CARPETA_TAREAS,
    "Informe Tareas"
)

df_pedidos = leer_archivo(
    CARPETA_PEDIDOS,
    "Pedidos DIGIP"
)

df_clientes = leer_archivo(
    CARPETA_CLIENTES,
    "Maestro Clientes"
)

# =====================================================
# TABLA OPERATIVA
# =====================================================

tabla_tareas = construir_tabla_tareas(
    df_tareas,
    df_pedidos,
    df_clientes
)

tabla_operativa = obtener_tabla_operativa(
    tabla_tareas
)

resumen = obtener_resumen_operativo(
    tabla_tareas,
    df_pedidos
)


# =====================================================
# CABECERA
# =====================================================

st.title("📋 Gestión de Tareas")

st.caption("Centro de Control Operativo")

st.markdown("---")

# =====================================================
# RESUMEN OPERATIVO
# =====================================================

st.subheader("📊 Resumen Operativo")

col1, col2, col3 = st.columns(3)

# ---------------------------------------
# PEDIDOS PENDIENTES
# ---------------------------------------

pedidos_pendientes = len(

    df_pedidos[
        df_pedidos["Estado"]
        .fillna("")
        .str.upper()
        != "COMPLETO"
    ]

)

with col1:

    st.metric(

        "📦 Pedidos Pendientes",

        pedidos_pendientes

    )

# ---------------------------------------
# CARROS EN CURSO
# ---------------------------------------

with col2:

    st.metric(

        "🛒 Carros en Curso",

        resumen["CarrosEnCurso"]

    )

# ---------------------------------------
# CARROS FINALIZADOS
# ---------------------------------------

with col3:

    st.metric(

        "✅ Carros Finalizados",

        resumen["CarrosFinalizados"]

    )

st.subheader("📋 Operación en Curso")

st.caption(
    f"{len(tabla_operativa)} registros"
)

st.dataframe(

    tabla_operativa,

    use_container_width=True,

    hide_index=True,

    height=600

)

# =====================================================
# INDICADORES
# =====================================================

st.subheader("📈 Indicadores")

st.info(
    "En este espacio construiremos los gráficos operativos del depósito."
)

st.markdown("---")

# =====================================================
# ESTADO DEL SISTEMA
# =====================================================

st.subheader("⚙ Estado del Sistema")

col1, col2, col3 = st.columns(3)

with col1:

    st.success("Informe Tareas")

    st.metric(
        "Registros",
        len(df_tareas)
    )

    st.caption(
        fecha_archivo(
            CARPETA_TAREAS,
            "Informe Tareas"
        )
    )

with col2:

    st.success("Pedidos DIGIP")

    st.metric(
        "Registros",
        len(df_pedidos)
    )

    st.caption(
        fecha_archivo(
            CARPETA_PEDIDOS,
            "Pedidos DIGIP"
        )
    )

with col3:

    st.success("Maestro Clientes")

    st.metric(
        "Registros",
        len(df_clientes)
    )

    st.caption(
        fecha_archivo(
            CARPETA_CLIENTES,
            "Maestro Clientes"
        )
    )

st.markdown("---")

# =====================================================
# BOTÓN
# =====================================================

if st.button("🏠 Volver al Inicio"):

    st.switch_page("app.py")

    