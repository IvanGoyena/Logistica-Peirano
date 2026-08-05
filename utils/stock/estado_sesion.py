from __future__ import annotations

import streamlit as st

PREFIJOS_ESTADO_STOCK = (
    "stock_",
    "mapa_",
    "ocupacion_",
    "calidad_",
    "cobertura_",
    "picking_",
    "almacen_",
)

CLAVES_PROTEGIDAS_STOCK = {
    "vista_principal_stock",
    "actualizar_fuentes_stock",
}


def limpiar_estado_temporal_stock() -> None:
    """Elimina filtros y resultados temporales sin borrar la vista activa."""
    for clave in list(st.session_state.keys()):
        if clave in CLAVES_PROTEGIDAS_STOCK:
            continue
        if str(clave).startswith(PREFIJOS_ESTADO_STOCK):
            st.session_state.pop(clave, None)
