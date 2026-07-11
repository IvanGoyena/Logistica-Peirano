from config import *

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

from models.tareas import (
    construir_tabla_tareas,
    obtener_resumen_operativo,
    obtener_carros_en_curso
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
carros_en_curso = obtener_carros_en_curso(
    tabla_tareas
)

# =====================================================
# KPIs
# =====================================================

# resumen = obtener_resumen_operativo(tabla_tareas)
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

with col1:

    st.metric(

        "🛒 Carros en Curso",

        carros_en_curso["Carro"].nunique()

    )

with col2:

    st.metric(

        "📦 Pedidos Pendientes",

        "-"

    )

with col3:

    st.metric(

        "✅ Carros Cerrados",

        "-"

    )

st.markdown("---")

st.subheader("🛒 Validación - Carros en Curso")

st.write(
    f"Registros encontrados: {len(carros_en_curso)}"
)

st.dataframe(

    carros_en_curso,

    use_container_width=True,

    hide_index=True,

    height=300

)
st.subheader("Validación")

st.dataframe(carros_en_curso)

# =====================================================
# INDICADORES
# =====================================================

st.subheader("📈 Indicadores")

st.info(
    "En este espacio construiremos los gráficos operativos del depósito."
)

st.markdown("---")

# =====================================================
# TABLA OPERATIVA
# =====================================================

st.subheader("📋 Tabla Operativa")

st.dataframe(
    tabla_tareas,
    use_container_width=True,
    hide_index=True,
    height=550
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

    