import streamlit as st
import streamlit_authenticator as stauth


# ==========================================================
# CONSTRUCCIÓN DEL AUTENTICADOR
# ==========================================================

def crear_autenticador():
    """
    Construye el autenticador usando los usuarios definidos
    en .streamlit/secrets.toml.
    """

    credenciales = {
        "usernames": {}
    }

    for usuario, datos in st.secrets["usuarios"].items():

        credenciales["usernames"][usuario] = {
            "name": datos["nombre"],
            "password": datos["password"],
            "roles": [datos["rol"]],
        }

    autenticador = stauth.Authenticate(
        credentials=credenciales,
        cookie_name=st.secrets["cookie"]["name"],
        cookie_key=st.secrets["cookie"]["key"],
        cookie_expiry_days=float(
            st.secrets["cookie"]["expiry_days"]
        ),
        auto_hash=True,
    )

    return autenticador


# ==========================================================
# INICIALIZACIÓN
# ==========================================================

def inicializar_sesion() -> None:
    """
    Inicializa campos propios utilizados por la aplicación.
    """

    valores = {
        "usuario": None,
        "nombre_usuario": None,
        "rol": None,
    }

    for clave, valor in valores.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor


# ==========================================================
# LOGIN
# ==========================================================

def mostrar_login(autenticador):

    # Si ya inició sesión, no mostrar el formulario
    if st.session_state.get("authentication_status") is True:
        return

    st.title("📦 Sistema Logístico Peirano")
    st.subheader("Inicio de sesión")

    st.write(
        "Ingresá tu usuario y contraseña para acceder al sistema."
    )

    autenticador.login(
        location="main",
        fields={
            "Form name": "Acceso al sistema",
            "Username": "Usuario",
            "Password": "Contraseña",
            "Login": "Ingresar",
        },
    )

    estado = st.session_state.get("authentication_status")

    if estado is False:
        st.error("Usuario o contraseña incorrectos.")

    elif estado is None:
        st.info("Ingresá tus credenciales.")

# ==========================================================
# SINCRONIZAR USUARIO Y ROL
# ==========================================================

def sincronizar_usuario() -> None:
    """
    Guarda en session_state el usuario, nombre y rol
    entregados por streamlit-authenticator.
    """

    if st.session_state.get("authentication_status") is not True:
        return

    usuario = st.session_state.get("username")

    if not usuario:
        return

    datos = st.secrets["usuarios"].get(usuario)

    if datos is None:
        return

    st.session_state["usuario"] = usuario
    st.session_state["nombre_usuario"] = datos["nombre"]
    st.session_state["rol"] = datos["rol"]


# ==========================================================
# CONTROL DE ACCESO
# ==========================================================

def requerir_login() -> None:
    """
    Bloquea la ejecución si no existe una sesión válida.
    """

    if st.session_state.get("authentication_status") is not True:
        st.error("Tenés que iniciar sesión para acceder.")
        st.stop()

    sincronizar_usuario()


def requerir_roles(*roles_permitidos: str) -> None:
    """
    Permite el acceso únicamente a los roles indicados.
    """

    requerir_login()

    rol_actual = st.session_state.get("rol")

    if rol_actual not in roles_permitidos:
        st.error(
            "⛔ No tenés permisos para acceder a este módulo."
        )
        st.stop()


def tiene_rol(*roles_permitidos: str) -> bool:
    """
    Indica si el usuario posee alguno de los roles solicitados.
    """

    return st.session_state.get("rol") in roles_permitidos


# ==========================================================
# SIDEBAR
# ==========================================================

def mostrar_usuario_sidebar(autenticador) -> None:
    """
    Muestra los datos del usuario y el cierre de sesión.
    """

    requerir_login()

    with st.sidebar:

        st.markdown("### 👤 Sesión")

        st.write(
            f"**{st.session_state['nombre_usuario']}**"
        )

        st.caption(
            f"Rol: {st.session_state['rol'].capitalize()}"
        )

        autenticador.logout(
            button_name="Cerrar sesión",
            location="sidebar",
            use_container_width="stretch",
        )

        st.divider()