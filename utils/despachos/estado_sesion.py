from __future__ import annotations

import streamlit as st

CLAVES_PLANIFICACION_DESPACHOS = [
    "asignacion_camionetas",
    "pedidos_planificados",
    "capacidad_camioneta",
    "agrupadores_ocupados",
    "agrupadores_a_crear",
]


def limpiar_estado_planificacion_despachos() -> None:
    for clave in CLAVES_PLANIFICACION_DESPACHOS:
        st.session_state.pop(clave, None)

    claves_ejecucion = [
        clave
        for clave in st.session_state.keys()
        if str(clave).startswith("resultado_digip_")
    ]
    for clave in claves_ejecucion:
        st.session_state.pop(clave, None)
