from __future__ import annotations

import streamlit as st

from utils.autenticacion import requerir_roles
from utils.despachos.carga import (
    construir_contexto_despachos,
    limpiar_cache_despachos,
)
from utils.despachos.estado import (
    limpiar_estado_despachos,
)
from utils.despachos.gestiones import (
    cerrar_solicitudes_resueltas,
    obtener_bloqueos_gestiones,
)
from views.despachos.dashboard import (
    render_dashboard_despachos,
)
from views.despachos.planificador import (
    render_planificador_despachos,
)


requerir_roles(
    "admin",
    "gerencia",
    "logistica",
    "supervisor",
)

st.set_page_config(
    page_title="Despachos",
    page_icon="🚚",
    layout="wide",
)


# ==========================================================
# ENCABEZADO / ACTUALIZACIÓN
# ==========================================================

col_info, col_actualizar = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with col_info:
    st.caption(
        "Los datos se mantienen en memoria durante la "
        "planificación y la ejecución de camionetas."
    )

with col_actualizar:
    actualizar_datos = st.button(
        "🔄 Actualizar datos",
        key="actualizar_datos_despachos",
        width="stretch",
        help=(
            "Vuelve a leer las fuentes WMS, ERP y Maestros "
            "y elimina la planificación anterior."
        ),
    )

if actualizar_datos:
    limpiar_cache_despachos()
    limpiar_estado_despachos()

    st.toast(
        "Datos de Despachos actualizados.",
        icon="✅",
    )

    st.rerun()


# ==========================================================
# CONTEXTO OPERATIVO
# ==========================================================

try:
    contexto = construir_contexto_despachos()
except Exception as error:
    st.error(
        "No se pudo construir la base operativa de Despachos."
    )
    st.exception(error)
    st.stop()

df_pedidos = contexto["df_pedidos"]
tabla = contexto["tabla"]


# ==========================================================
# GESTIONES COMERCIALES
# ==========================================================

try:
    solicitudes_cerradas = (
        cerrar_solicitudes_resueltas(
            df_pedidos
        )
    )
except Exception as error:
    solicitudes_cerradas = 0
    st.warning(
        "No se pudo ejecutar el cierre automático de "
        f"solicitudes comerciales. Detalle: {error}"
    )

if solicitudes_cerradas:
    st.toast(
        (
            f"{solicitudes_cerradas} solicitud(es) "
            "finalizada(s) automáticamente."
        ),
        icon="✅",
    )

try:
    (
        pedidos_bloqueados_gestion,
        pedidos_por_tipo_gestion,
    ) = obtener_bloqueos_gestiones()

except Exception as error:
    pedidos_bloqueados_gestion = set()
    pedidos_por_tipo_gestion = {}

    st.warning(
        "No se pudieron consultar los bloqueos comerciales. "
        f"Detalle: {error}"
    )


# ==========================================================
# DISPONIBILIDAD PARA PLANIFICACIÓN
# ==========================================================

st.title("🚚 Gestión de Despachos")

st.caption(
    "Planificación de camionetas y ejecución "
    "de agrupaciones en DIGIP."
)

tabla_filtrada = tabla.copy()

mascara_sin_preparacion = (
    tabla_filtrada["PreparacionID"]
    .fillna("")
    .astype(str)
    .str.strip()
    .eq("")
)

tabla_disponible_planificacion = (
    tabla_filtrada.loc[
        mascara_sin_preparacion
    ].copy()
)


# ==========================================================
# VISTAS
# ==========================================================

vista_despachos = st.segmented_control(
    "Vista de Despachos",
    options=[
        "📊 Dashboard",
        "🚐 Planificador de camionetas",
    ],
    default="📊 Dashboard",
    key="vista_principal_despachos",
    label_visibility="collapsed",
)

if vista_despachos == "📊 Dashboard":
    render_dashboard_despachos(
        tabla_disponible_planificacion
    )

else:
    render_planificador_despachos(
        tabla=tabla,
        tabla_filtrada=tabla_filtrada,
        tabla_disponible_planificacion=(
            tabla_disponible_planificacion
        ),
        mascara_sin_preparacion=(
            mascara_sin_preparacion
        ),
        pedidos_bloqueados_gestion=(
            pedidos_bloqueados_gestion
        ),
        pedidos_por_tipo_gestion=(
            pedidos_por_tipo_gestion
        ),
    )
