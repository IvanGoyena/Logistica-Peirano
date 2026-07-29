from config import *
import streamlit as st

from utils.autenticacion import requerir_roles
from utils.stock_carga import construir_contexto_stock, cargar_fuentes_stock
from views.stock_existencia import render as render_existencia
from views.stock_ocupacion import render as render_ocupacion
from views.stock_operativo import render as render_operativo
from views.stock_configuracion import render as render_configuracion

requerir_roles("admin", "gerencia")
st.set_page_config(page_title="Stock", page_icon="📊", layout="wide")

st.title("📊 Gestión de Stock")
st.caption("Existencia física, ocupación, situación operativa y configuración de producto.")

if st.button("🔄 Actualizar fuentes", type="primary", key="actualizar_fuentes_stock"):
    cargar_fuentes_stock.clear()
    st.cache_data.clear()
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
