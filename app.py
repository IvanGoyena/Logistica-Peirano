import streamlit as st

from utils.autenticacion import (
    crear_autenticador,
    inicializar_sesion,
    mostrar_login,
    sincronizar_usuario,
    mostrar_usuario_sidebar,
    tiene_rol,
)


st.set_page_config(
    page_title="Sistema Logístico Peirano",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================================
# AUTENTICACIÓN
# ==========================================================

inicializar_sesion()

autenticador = crear_autenticador()

mostrar_login(autenticador)


if st.session_state.get("authentication_status") is not True:
    st.stop()


sincronizar_usuario()
mostrar_usuario_sidebar(autenticador)


# ==========================================================
# CONFIGURACIÓN GENERAL
# ==========================================================

st.set_page_config(
    page_title="Sistema Logístico Peirano",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================================
# INICIALIZAR SESIÓN
# ==========================================================

inicializar_sesion()


# ==========================================================
# ==========================================================
# PÁGINA DE INICIO
# ==========================================================

def mostrar_inicio() -> None:

    st.title("📦 Sistema Logístico Peirano")

    st.subheader("Centro de Control Operativo")

    st.divider()

    st.success(
        f"Bienvenido, "
        f"{st.session_state['nombre_usuario']}."
    )

    st.write(
        "Seleccioná el módulo sobre el que deseas trabajar "
        "desde el menú lateral."
    )

    st.write(
        f"**Rol asignado:** "
        f"{st.session_state['rol'].capitalize()}"
    )

    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Usuario",
            value=st.session_state["usuario"],
        )

    with col2:
        st.metric(
            label="Rol",
            value=st.session_state["rol"].capitalize(),
        )

    with col3:
        st.metric(
            label="Estado",
            value="Conectado",
        )

    st.divider()

    st.caption(
        "Sistema desarrollado por Logística - Peirano"
    )


# ==========================================================
# DEFINICIÓN DE PÁGINAS
# ==========================================================

pagina_inicio = st.Page(
    mostrar_inicio,
    title="Inicio",
    icon="🏠",
    default=True,
)

pagina_tareas = st.Page(
    "pages/01_Tareas.py",
    title="Gestión de Tareas",
    icon="📋",
)

pagina_pedidos = st.Page(
    "pages/02_Pedidos.py",
    title="Gestión de Pedidos",
    icon="📦",
)

pagina_despachos = st.Page(
    "pages/03_Despachos.py",
    title="Gestión de Despachos",
    icon="🚚",
)

pagina_stock = st.Page(
    "pages/04_Stock.py",
    title="Gestión de Stock",
    icon="📊",
)

pagina_maestros = st.Page(
    "pages/05_Maestros.py",
    title="Maestros",
    icon="⚙️",
)



# ==========================================================
# MENÚ SEGÚN ROL
# ==========================================================

paginas = {
    "General": [
        pagina_inicio,
    ]
}


# ADMINISTRADOR
if tiene_rol("admin"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_pedidos,
        pagina_despachos,
        pagina_stock,
    ]

    paginas["Configuración"] = [
        pagina_maestros,
    ]


# GERENCIA
elif tiene_rol("gerencia"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_pedidos,
        pagina_despachos,
        pagina_stock,
    ]



# LOGÍSTICA
elif tiene_rol("logistica"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_pedidos,
        pagina_despachos,
        pagina_stock,
    ]

    paginas["Configuración"] = [
        pagina_maestros,
    ]


# SUPERVISOR
elif tiene_rol("supervisor"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_pedidos,
        pagina_despachos,
        pagina_stock,
    ]


# ==========================================================
# EJECUTAR NAVEGACIÓN
# ==========================================================

navegacion = st.navigation(paginas)
navegacion.run()