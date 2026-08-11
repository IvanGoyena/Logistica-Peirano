import streamlit as st

from utils.cache_app import (
    limpiar_cache_aplicacion,
)
from utils.estado_actualizacion import (
    preparar_indicador_sidebar,
)

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
# ACTUALIZACIÓN GLOBAL DE DATOS
# ==========================================================

with st.sidebar:
    st.divider()

    if st.button(
        "🔄 Actualizar datos",
        use_container_width=True,
        key="sidebar_actualizar_datos_global",
        help=(
            "Limpia la caché de datos de toda la aplicación "
            "y vuelve a leer las fuentes disponibles en el repositorio."
        ),
    ):
        with st.spinner("Actualizando fuentes..."):
            limpiar_cache_aplicacion()

        st.toast(
            "Fuentes actualizadas correctamente.",
            icon="✅",
        )
        st.rerun()

    preparar_indicador_sidebar()


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

pagina_metricas = st.Page(
    "pages/06_Metricas.py",
    title="Métricas",
    icon="📈",
)

pagina_auditoria = st.Page(
    "pages/07_Auditoria_ETL.py",
    title="Auditoría ETL",
    icon="🧪",
)


pagina_consultas = st.Page(
    "pages/08_Consultas.py",
    title="Consultas Comerciales",
    icon="💬",
)



pagina_devoluciones = st.Page(
    "pages/09_Devoluciones.py",
    title="Gestión de Devoluciones",
    icon="↩️",
)


pagina_inventario = st.Page(
    "pages/10_Inventario.py",
    title="Gestión de Inventario",
    icon="🧮",
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
        pagina_inventario,
        pagina_devoluciones,
    ]

    paginas["Comercial"] = [
        pagina_consultas,
    ]

    paginas["Análisis"] = [
        pagina_metricas,
    ]

    paginas["Configuración"] = [
        pagina_maestros,
        pagina_auditoria,
    ]


# GERENCIA
elif tiene_rol("gerencia"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_pedidos,
        pagina_despachos,
        pagina_stock,
        pagina_inventario,
        pagina_devoluciones,
    ]

    paginas["Comercial"] = [
        pagina_consultas,
    ]

    paginas["Análisis"] = [
        pagina_metricas,
    ]


# LOGÍSTICA
elif tiene_rol("logistica"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_despachos,
        pagina_stock,
        pagina_inventario,
        pagina_devoluciones,
    ]

    paginas["Comercial"] = [
        pagina_consultas,
    ]

    paginas["Configuración"] = [
        pagina_maestros,
    ]


# SUPERVISOR
elif tiene_rol("supervisor"):

    paginas["Operación"] = [
        pagina_tareas,
        pagina_despachos,
        pagina_stock,
        pagina_inventario,
        pagina_devoluciones,
    ]

    paginas["Comercial"] = [
        pagina_consultas,
    ]


# COMERCIAL
elif tiene_rol("comercial"):

    paginas["Comercial"] = [
        pagina_consultas,
    ]


# ==========================================================
# EJECUTAR NAVEGACIÓN
# ==========================================================

navegacion = st.navigation(paginas)
navegacion.run()