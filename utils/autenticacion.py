import hmac

import streamlit as st


# ==========================================================
# SESIÓN
# ==========================================================

def inicializar_sesion() -> None:
    """
    Inicializa las variables utilizadas para mantener
    el usuario autenticado.
    """

    valores_iniciales = {
        "autenticado": False,
        "usuario": None,
        "nombre_usuario": None,
        "rol": None,
    }

    for clave, valor in valores_iniciales.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor


# ==========================================================
# VALIDACIÓN DE CREDENCIALES
# ==========================================================

def validar_usuario(
    usuario: str,
    password: str,
) -> bool:
    """
    Valida las credenciales contra .streamlit/secrets.toml.
    """

    usuario = usuario.strip().lower()

    try:
        usuarios = st.secrets["usuarios"]
    except KeyError:
        st.error(
            "No se encontró la sección [usuarios] "
            "en .streamlit/secrets.toml."
        )
        return False

    if usuario not in usuarios:
        return False

    datos_usuario = usuarios[usuario]

    password_guardada = str(datos_usuario["password"])

    password_valida = hmac.compare_digest(
        password,
        password_guardada,
    )

    if not password_valida:
        return False

    st.session_state["autenticado"] = True
    st.session_state["usuario"] = usuario
    st.session_state["nombre_usuario"] = datos_usuario["nombre"]
    st.session_state["rol"] = datos_usuario["rol"]

    return True


# ==========================================================
# LOGIN
# ==========================================================

def mostrar_login() -> None:
    """
    Muestra la pantalla de inicio de sesión.
    """

    inicializar_sesion()

    st.title("📦 Sistema Logístico Peirano")
    st.subheader("Inicio de sesión")

    st.write(
        "Ingresá tu usuario y contraseña para acceder al sistema."
    )

    with st.form("formulario_login"):

        usuario = st.text_input(
            "Usuario",
            placeholder="Ingresá tu usuario",
        )

        password = st.text_input(
            "Contraseña",
            type="password",
            placeholder="Ingresá tu contraseña",
        )

        ingresar = st.form_submit_button(
            "Ingresar",
            type="primary",
            use_container_width=True,
        )

    if ingresar:

        if not usuario.strip() or not password:
            st.warning("Completá el usuario y la contraseña.")
            return

        if validar_usuario(usuario, password):
            st.rerun()

        else:
            st.error("Usuario o contraseña incorrectos.")


# ==========================================================
# CONTROL DE ACCESO
# ==========================================================

def requerir_login() -> None:
    """
    Detiene la ejecución si el usuario no está autenticado.
    """

    inicializar_sesion()

    if not st.session_state["autenticado"]:
        mostrar_login()
        st.stop()


def requerir_roles(*roles_permitidos: str) -> None:
    """
    Detiene la página si el rol actual no está autorizado.

    Ejemplo:
        requerir_roles("admin", "gerencia")
    """

    requerir_login()

    rol_actual = st.session_state.get("rol")

    if rol_actual not in roles_permitidos:
        st.error(
            "⛔ No tenés permisos para acceder a este módulo."
        )

        st.info(
            f"Tu rol actual es: {rol_actual}"
        )

        st.stop()


def tiene_rol(*roles_permitidos: str) -> bool:
    """
    Devuelve True si el usuario tiene alguno de los roles.
    """

    rol_actual = st.session_state.get("rol")

    return rol_actual in roles_permitidos


# ==========================================================
# CIERRE DE SESIÓN
# ==========================================================

def cerrar_sesion() -> None:
    """
    Elimina los datos de sesión del usuario.
    """

    claves_sesion = [
        "autenticado",
        "usuario",
        "nombre_usuario",
        "rol",
    ]

    for clave in claves_sesion:
        st.session_state.pop(clave, None)

    st.rerun()


def mostrar_usuario_sidebar() -> None:
    """
    Muestra el usuario, rol y botón para cerrar sesión.
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

        if st.button(
            "Cerrar sesión",
            use_container_width=True,
            key="boton_cerrar_sesion",
        ):
            cerrar_sesion()

        st.divider()