from __future__ import annotations

import streamlit as st

from views.stock.configuracion_picking import (
    render as render_picking,
)
from views.stock.slotting_almacen import (
    render as render_almacen,
)


def render(
    contexto: dict,
) -> None:
    st.subheader(
        "⚙️ Configuración y Slotting"
    )
    st.caption(
        "Análisis separado de la capacidad del Picking y "
        "la distribución física del Almacén."
    )

    vista = st.segmented_control(
        "Tipo de análisis",
        options=[
            "📦 Configuración de Picking",
            "🗺️ Slotting de Almacén",
        ],
        default="📦 Configuración de Picking",
        key="stock_configuracion_vista",
        label_visibility="collapsed",
    )

    st.divider()

    if vista == "🗺️ Slotting de Almacén":
        render_almacen(contexto)
    else:
        render_picking(contexto)
