import streamlit as st

st.set_page_config(
    page_title="Sistema Logístico Peirano",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================================================
# SIDEBAR
# ======================================================

st.sidebar.title("Sistema Logístico")

st.sidebar.success("Versión 1.0")

st.sidebar.markdown("---")

st.sidebar.info("Proyecto de Automatización Logística")

# ======================================================
# PANTALLA PRINCIPAL
# ======================================================

st.title("📦 Sistema Logístico Peirano")

st.subheader("Centro de Control Operativo")

st.markdown("---")

st.write(
"""
Bienvenido al Sistema Logístico.

Seleccione el módulo sobre el que desea trabajar.
"""
)

st.markdown("")

col1, col2 = st.columns(2)

with col1:

    st.page_link(
        "pages/01_Tareas.py",
        label="📋 Gestión de Tareas",
        icon="📋"
    )

    st.page_link(
        "pages/02_Pedidos.py",
        label="📦 Gestión de Pedidos",
        icon="📦"
    )

    st.page_link(
        "pages/03_Despachos.py",
        label="🚚 Gestión de Despachos",
        icon="🚚"
    )

with col2:

    st.page_link(
        "pages/04_Stock.py",
        label="📊 Gestión de Stock",
        icon="📊"
    )

    st.page_link(
        "pages/05_Maestros.py",
        label="⚙ Maestros",
        icon="⚙"
    )

st.markdown("---")

st.caption("Sistema desarrollado por Logística - Peirano")