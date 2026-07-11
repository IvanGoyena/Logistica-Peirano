from pathlib import Path

# ==========================================================
# CARPETAS BASE
# ==========================================================

BASE_DIGIP = Path(
    r"C:\Users\IRodriguez\Desktop\Informes DIGIP"
)

BASE_AUTOMATIZACION = Path(
    r"C:\Automatizacion_WMS"
)

# ==========================================================
# CARPETAS DE BUSQUEDA
# ==========================================================

CARPETA_TAREAS = (
    BASE_DIGIP /
    "A - Salidas"
)

CARPETA_CLIENTES = BASE_DIGIP

CARPETA_PEDIDOS = (
    BASE_AUTOMATIZACION /
    "descargas" /
    "pedidos_digip"
)
