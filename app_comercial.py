import streamlit as st

from utils.cache_app import limpiar_cache_aplicacion
from utils.estado_actualizacion import obtener_ultima_actualizacion, registrar_actualizacion_manual
from utils.autenticacion import (
    crear_autenticador,
    inicializar_sesion,
    mostrar_login,
    sincronizar_usuario,
    mostrar_usuario_sidebar,
    tiene_rol,
)

st.set_page_config(
    page_title="Sistema Comercial Peirano",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

inicializar_sesion()
autenticador = crear_autenticador()
mostrar_login(autenticador)

if st.session_state.get("authentication_status") is not True:
    st.stop()

sincronizar_usuario()
mostrar_usuario_sidebar(autenticador)

if not any(tiene_rol(rol) for rol in ("admin", "gerencia", "logistica", "supervisor", "comercial")):
    st.error("Tu usuario no tiene acceso al Sistema Comercial.")
    st.stop()

@st.fragment(run_every="5s")
def mostrar_ultima_actualizacion() -> None:
    ultima_actualizacion = obtener_ultima_actualizacion()
    if ultima_actualizacion is None:
        st.caption("🕒 Última actualización: --")
        return
    st.caption(
        "🕒 Última actualización: "
        f"{ultima_actualizacion.strftime('%d/%m/%Y %H:%M:%S')}"
    )

with st.sidebar:
    st.divider()
    if st.button(
        "🔄 Actualizar datos",
        use_container_width=True,
        key="sidebar_actualizar_datos_comercial",
        help="Limpia la caché del módulo Comercial y vuelve a leer las fuentes disponibles.",
    ):
        with st.spinner("Actualizando fuentes..."):
            limpiar_cache_aplicacion()
            st.cache_data.clear()
        registrar_actualizacion_manual()
        st.toast("Datos comerciales actualizados correctamente.", icon="✅")
        st.rerun()
    mostrar_ultima_actualizacion()

def mostrar_inicio_comercial() -> None:
    st.title("💬 Sistema Comercial Peirano")
    st.subheader("Gestión Comercial")
    st.divider()
    st.success(f"Bienvenido, {st.session_state['nombre_usuario']}.")
    st.write(
        "Desde esta aplicación podés consultar pedidos y gestionar "
        "Solicitudes, Reclamos y Cancelaciones de entrega."
    )
    st.write(f"**Rol asignado:** {st.session_state['rol'].capitalize()}")
    st.divider()
    st.caption("Sistema Comercial conectado al entorno operativo Peirano")

pagina_inicio = st.Page(
    mostrar_inicio_comercial,
    title="Inicio",
    icon="🏠",
    default=True,
)

pagina_consultas = st.Page(
    "pages/08_Consultas.py",
    title="Gestión Comercial",
    icon="💬",
)

paginas = {
    "Comercial": [
        pagina_inicio,
        pagina_consultas,
    ]
}

navegacion = st.navigation(paginas)
navegacion.run()
