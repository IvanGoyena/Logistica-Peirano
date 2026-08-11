from __future__ import annotations

import streamlit as st


CLAVES_PLANIFICACION_DESPACHOS = [
    "asignacion_camionetas",
    "pedidos_planificados",
    "capacidad_camioneta",
    "agrupadores_ocupados",
    "agrupadores_a_crear",
]


def limpiar_estado_despachos() -> None:
    """Limpia solamente el estado de sesión propio de Despachos."""

    for clave in CLAVES_PLANIFICACION_DESPACHOS:
        st.session_state.pop(clave, None)

    claves_ejecucion = [
        clave
        for clave in list(st.session_state.keys())
        if str(clave).startswith("resultado_digip_")
    ]

    for clave in claves_ejecucion:
        st.session_state.pop(clave, None)

    # Compatibilidad con filtros compartidos del flujo de pedidos.
    st.session_state.pop("filtros_pedidos", None)
