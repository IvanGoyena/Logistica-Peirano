from pathlib import Path


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
# WMS
# ==========================================================

URL = "https://app.digipwms.com"

USUARIO = "igoyena"

PASSWORD = "0802"

HEADLESS = False
