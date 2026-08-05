from __future__ import annotations

import streamlit as st


def limpiar_estado_pedidos() -> None:
    claves_directas = [
        "asignacion_camionetas", "pedidos_planificados", "capacidad_camioneta",
        "agrupadores_ocupados", "agrupadores_a_crear", "filtros_pedidos",
    ]
    for clave in claves_directas:
        st.session_state.pop(clave, None)

    for clave in list(st.session_state.keys()):
        if str(clave).startswith("resultado_digip_"):
            st.session_state.pop(clave, None)
