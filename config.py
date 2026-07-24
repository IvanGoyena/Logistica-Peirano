from pathlib import Path
import os

try:
    import streamlit as st
except ImportError:
    st = None


# ==========================================================
# ENTORNO Y CARPETAS
# ==========================================================

CARPETA_DATOS_LOCAL = Path(
    r"G:\Mi unidad\Sistema_Logistico_Peirano\data"
)

CARPETA_DATOS_NUBE = Path(
    "/tmp/sistema_logistico_peirano/data"
)

ES_STREAMLIT_CLOUD = not CARPETA_DATOS_LOCAL.exists()

CARPETA_DATOS = (
    CARPETA_DATOS_NUBE
    if ES_STREAMLIT_CLOUD
    else CARPETA_DATOS_LOCAL
)


# ==========================================================
# CONFIGURACIÓN SEGURA
# ==========================================================

def obtener_secreto(
    nombre: str,
    valor_local: str = "",
) -> str:

    if st is not None:
        try:
            if nombre in st.secrets:
                return str(st.secrets[nombre]).strip()
        except Exception:
            pass

    return str(
        os.getenv(nombre, valor_local)
    ).strip()


# ==========================================================
# WMS
# ==========================================================

URL = obtener_secreto(
    "DIGIP_URL",
    "https://app.digipwms.com",
)

USUARIO = obtener_secreto(
    "USUARIO"
)

PASSWORD = obtener_secreto(
    "PASSWORD"
)

HEADLESS = True