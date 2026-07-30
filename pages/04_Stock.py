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

if st.button(
    "🔄 Actualizar stock",
    type="primary",
    key="actualizar_fuentes_stock",
    help=(
        "Actualiza Stock Recepción, Stock Disponible, Stock DIGIP y "
        "Stock Calidad/Laboratorio sin borrar la caché de los maestros."
    ),
):
    limpiar_cache_fuentes_dinamicas_stock()
    st.toast("Fuentes operativas actualizadas", icon="✅")
    st.rerun()

contexto = construir_contexto_stock()

tab_fisico, tab_ocupacion, tab_operativo, tab_configuracion = st.tabs([
    "🏭 Existencia física",
    "🗺️ Ocupación del depósito",
    "📦 Situación operativa",
    "⚙️ Configuración y producto",
])

with tab_fisico:
    render_existencia(contexto)
with tab_ocupacion:
    render_ocupacion(contexto)
with tab_operativo:
    render_operativo(contexto)
with tab_configuracion:
    render_configuracion(contexto)
