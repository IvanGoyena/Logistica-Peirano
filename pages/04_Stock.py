from config import *
import streamlit as st

from utils.autenticacion import requerir_roles
from utils.stock_carga import construir_contexto_stock, limpiar_cache_stock_completa
from views.stock import (
    render_existencia,
    render_ocupacion,
    render_calidad,
    render_operativo,
    render_configuracion,
)
from utils.stock.estado_sesion import limpiar_estado_temporal_stock


requerir_roles("admin", "gerencia")
st.set_page_config(page_title="Stock", page_icon="📊", layout="wide")

st.title("📊 Gestión de Stock")
st.caption("Existencia física, ocupación, disponibilidad, cobertura y configuración de producto.")


if st.button(
    "🔄 Actualizar stock y maestros",
    type="primary",
    key="actualizar_fuentes_stock",
    help=("Actualiza reportes y maestros de Stock. El histórico de cobertura "
          "se publica y actualiza desde el módulo Métricas."),
):
    limpiar_cache_stock_completa()
    limpiar_estado_temporal_stock()
    st.toast("Stock y maestros actualizados. El histórico se conserva.", icon="✅")
    st.rerun()

vista = st.segmented_control(
    "Vista de stock",
    options=[
        "🏭 Existencia física",
        "🗺️ Ocupación del depósito",
        "🧪 Calidad y Reproceso",
        "📦 Disponible y Cobertura",
        "⚙️ Configuración y producto",
    ],
    default="🏭 Existencia física",
    key="vista_principal_stock",
    label_visibility="collapsed",
)

# Se construye únicamente el contexto de la pantalla visible.
contexto = construir_contexto_stock(vista)

if vista == "🏭 Existencia física":
    render_existencia(contexto)
elif vista == "🗺️ Ocupación del depósito":
    render_ocupacion(contexto)
elif vista == "🧪 Calidad y Reproceso":
    render_calidad(contexto)
elif vista == "📦 Disponible y Cobertura":
    render_operativo(contexto)
else:
    render_configuracion(contexto)
