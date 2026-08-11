from pathlib import Path
import os

try:
    import streamlit as st
except ImportError:
    st = None


# ==========================================================
# ENTORNO Y CARPETAS
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent

CARPETA_WMS = BASE_DIR / "Data_WMS"
CARPETA_ERP = BASE_DIR / "Data_ERP"
CARPETA_MAESTROS = BASE_DIR / "Data_Maestros"


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


# ==========================================================
# RESPONSABLES DE GESTIÓN
# ==========================================================

RESPONSABLES = {
    "Logistica": {
        "to": [
            "igoyena@peirano.com.ar",
            "control.gestion@queija.com.ar",
        ],
        "cc": [
            "lvega@peirano.com.ar",
        ],
    },
}