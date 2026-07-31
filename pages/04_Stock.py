from config import *
import streamlit as st

from utils.autenticacion import requerir_roles
from utils.stock_carga import (
    construir_contexto_stock,
    limpiar_cache_fuentes_dinamicas_stock,
)
from views.stock_existencia import render as render_existencia
from views.stock_ocupacion import render as render_ocupacion
from views.stock_operativo import render as render_operativo
from views.stock_configuracion import render as render_configuracion


requerir_roles("admin", "gerencia")
st.set_page_config(page_title="Stock", page_icon="📊", layout="wide")

st.title("📊 Gestión de Stock")
st.caption("Existencia física, ocupación, situación operativa y configuración de producto.")

def limpiar_estado_temporal_stock() -> None:
    """Elimina resultados temporales del módulo sin borrar la vista elegida."""
    prefijos = ("stock_", "mapa_", "ocupacion_")
    claves_protegidas = {
        "vista_principal_stock",
        "actualizar_fuentes_stock",
    }

    claves_a_eliminar = [
        clave
        for clave in list(st.session_state.keys())
        if clave not in claves_protegidas
        and str(clave).startswith(prefijos)
    ]

    for clave in claves_a_eliminar:
        st.session_state.pop(clave, None)


if st.button(
    "🔄 Actualizar stock y maestros",
    type="primary",
    key="actualizar_fuentes_stock",
    help=(
        "Limpia la caché del módulo y vuelve a leer stock, ocupación, "
        "maestros de ubicaciones, artículos, volumetría y configuraciones."
    ),
):
    # Limpieza específica de las fuentes operativas del módulo.
    limpiar_cache_fuentes_dinamicas_stock()

    # Limpieza completa de datos cacheados para incorporar cambios en maestros.
    # No se limpia cache_resource para conservar conexiones y servicios externos.
    st.cache_data.clear()

    # Elimina resultados temporales que puedan haber quedado en la sesión.
    limpiar_estado_temporal_stock()

    st.toast("Stock, ocupación y maestros actualizados", icon="✅")
    st.rerun()

vista = st.segmented_control(
    "Vista de stock",
    options=[
        "🏭 Existencia física",
        "🗺️ Ocupación del depósito",
        "📦 Situación operativa",
        "⚙️ Configuración y producto",
    ],
    default="🏭 Existencia física",
    key="vista_principal_stock",
    label_visibility="collapsed",
)

# IMPORTANTE: con segmented_control se renderiza una sola vista por ejecución.
# El contexto todavía se construye una vez. Para separar también las lecturas
# por vista hace falta adaptar utils/stock_carga.py.
contexto = construir_contexto_stock()

if vista == "🏭 Existencia física":
    render_existencia(contexto)
elif vista == "🗺️ Ocupación del depósito":
    render_ocupacion(contexto)
elif vista == "📦 Situación operativa":
    render_operativo(contexto)
else:
    render_configuracion(contexto)
