import streamlit as st

from utils.autenticacion import requerir_roles
from utils.metricas.metricas_carga import (
    completar_contexto_vista,
    construir_contexto_base_metricas,
    limpiar_cache_metricas_completa,
)
from utils.metricas.metricas_estilos import aplicar_estilos_metricas
from views.metricas.dashboard.metricas_filtros import render as render_filtros
from views.metricas.dashboard.metricas_kpis import render as render_kpis
from views.metricas.dashboard.metricas_resumen import render as render_resumen
from views.metricas.dashboard.metricas_productividad import render as render_productividad
from views.metricas.dashboard.metricas_productos import render as render_productos
from views.metricas.dashboard.metricas_insights import render as render_insights
from views.metricas.cumplimiento.metricas_ciclo_pedidos import render as render_ciclo
from views.metricas.dashboard.metricas_calidad_datos import render as render_calidad


requerir_roles("admin", "gerencia")
st.set_page_config(page_title="Métricas", page_icon="📈", layout="wide")
aplicar_estilos_metricas()


# ==========================================================
# NAVEGACIÓN PRINCIPAL DEL MÓDULO
# ==========================================================
seccion_principal = st.segmented_control(
    "Sección principal",
    options=[
        "📊 Dashboard Gerencial",
        "🚚 Cumplimiento de Pedidos",
    ],
    default="📊 Dashboard Gerencial",
    key="seccion_principal_metricas",
    label_visibility="collapsed",
)


# ==========================================================
# ENCABEZADO Y ACTUALIZACIÓN
# ==========================================================
col_titulo, col_actualizar = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with col_titulo:
    if seccion_principal == "🚚 Cumplimiento de Pedidos":
        st.title("🚚 Cumplimiento de Pedidos")
        st.caption(
            "Planificación, ciclo de vida y nivel de servicio de los pedidos "
            "cerrados en DIGIP."
        )
    else:
        st.title("📊 Dashboard Gerencial")
        st.caption(
            "Análisis histórico de Preparación y Control, enriquecido con "
            "artículos, volumen y peso."
        )

with col_actualizar:
    if st.button(
        "🔄 Actualizar",
        width="stretch",
        type="primary",
        key="actualizar_metricas",
    ):
        limpiar_cache_metricas_completa()
        for clave in [
            "ciclo_borrador_rango_fechas",
            "ciclo_aplicado_fecha_desde",
            "ciclo_aplicado_fecha_hasta",
        ]:
            st.session_state.pop(clave, None)
        st.toast(
            "Mes actual actualizado. Históricos cerrados conservados.",
            icon="✅",
        )
        st.rerun()


# ==========================================================
# CONTEXTO COMPARTIDO
# ==========================================================
try:
    contexto = construir_contexto_base_metricas()
except Exception as error:
    st.error("No se pudieron procesar las métricas.")
    st.exception(error)
    st.stop()

if contexto["error_publicacion"] is not None:
    st.warning(
        "Las métricas se procesaron, pero no se pudo publicar la base "
        "histórica compartida: "
        f"{contexto['error_publicacion']}"
    )

if contexto["df_tareas"].empty:
    st.warning("No existen tareas enriquecidas para mostrar.")
    st.stop()


# ==========================================================
# CUMPLIMIENTO DE PEDIDOS
# Pantalla independiente: no muestra filtros ni KPI operativos.
# ==========================================================
if seccion_principal == "🚚 Cumplimiento de Pedidos":
    contexto = completar_contexto_vista(
        "🚚 Cumplimiento de Pedidos",
        contexto,
    )
    render_ciclo(contexto)
    st.stop()


# ==========================================================
# DASHBOARD GERENCIAL
# ==========================================================
contexto = render_filtros(contexto)
render_kpis(contexto)

vista = st.segmented_control(
    "Vista del dashboard",
    options=[
        "🏠 Resumen",
        "⚡ Productividad",
        "📦 Productos",
        "💡 Insights",
        "🧪 Calidad de datos",
    ],
    default="🏠 Resumen",
    key="vista_principal_metricas",
    label_visibility="collapsed",
)

if vista == "🏠 Resumen":
    render_resumen(contexto)
elif vista == "⚡ Productividad":
    render_productividad(contexto)
elif vista == "📦 Productos":
    render_productos(contexto)
elif vista == "💡 Insights":
    render_insights(contexto)
else:
    # Compatibilidad con los nombres esperados por la sección técnica original.
    contexto["datos"] = {
        "df_articulos": contexto["df_articulos"],
        "tabla_volumetria": contexto["tabla_volumetria"],
    }
    render_calidad(contexto)
