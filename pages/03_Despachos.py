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
from views.despachos.ubicador import (
    render_ubicador_despachos,
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
    st.session_state.pop("_contexto_despachos_ubicador", None)

    st.toast(
        "Datos de Despachos actualizados.",
        icon="✅",
    )

    st.rerun()


# ==========================================================
# CONTEXTO OPERATIVO
# ==========================================================

vista_actual = st.session_state.get(
    "vista_principal_despachos",
    "📊 Dashboard",
)

# En el Ubicador trabajamos con un contexto congelado en memoria.
# Así cada escaneo puede hacer rerun para refrescar la interfaz SIN
# reconstruir las tablas pesadas de Despachos.
usar_contexto_ubicador = (
    vista_actual == "📍 Ubicador de despacho"
    and "_contexto_despachos_ubicador" in st.session_state
)

try:
    if usar_contexto_ubicador:
        contexto = st.session_state["_contexto_despachos_ubicador"]
    else:
        contexto = construir_contexto_despachos()

        # Guardamos una copia del contexto ya construido para que,
        # al entrar al Ubicador, los siguientes reruns sean instantáneos.
        st.session_state["_contexto_despachos_ubicador"] = contexto

except Exception as error:
    st.error(
        "No se pudo construir la base operativa de Despachos."
    )
    st.exception(error)
    st.stop()

df_pedidos = contexto["df_pedidos"]
df_informe_tareas = contexto["df_informe_tareas"]
df_filtrar_preparacion = contexto["df_filtrar_preparacion"]
tabla = contexto["tabla"]


# ==========================================================
# GESTIONES COMERCIALES
# ==========================================================

# Las gestiones comerciales son necesarias para Dashboard/Planificador,
# pero no para escanear bultos en el Ubicador.
if vista_actual != "📍 Ubicador de despacho":
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
else:
    solicitudes_cerradas = 0
    pedidos_bloqueados_gestion = set()
    pedidos_por_tipo_gestion = {}


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
        "📍 Ubicador de despacho",
    ],
    default="📊 Dashboard",
    key="vista_principal_despachos",
    label_visibility="collapsed",
)

if vista_despachos == "📊 Dashboard":
    render_dashboard_despachos(
        tabla_disponible_planificacion
    )

elif vista_despachos == "🚐 Planificador de camionetas":
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


if vista_despachos == "📍 Ubicador de despacho":
    render_ubicador_despachos(
        df_filtrar_preparacion=df_filtrar_preparacion,
        df_informe_tareas=df_informe_tareas,
        tabla=tabla,
    )
