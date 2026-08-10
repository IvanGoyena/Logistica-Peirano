from __future__ import annotations

import streamlit as st

from views.maestros.clientes import (
    render_clientes,
)
from views.maestros.fuentes import (
    render_fuentes,
)
from views.maestros.historicos import (
    render_historicos,
)
from views.maestros.publicacion import (
    render_publicacion,
)


def render_maestros() -> None:
    st.title("⚙️ Maestros y Fuentes")

    st.caption(
        "Centro de administración de reportes, "
        "maestros e históricos del Sistema Logístico."
    )

    vista = st.segmented_control(
        "Vista",
        options=[
            "📂 Fuentes y descargas",
            "👥 Maestro Clientes",
            "📈 Históricos",
            "⬆️ Publicación manual",
        ],
        default="📂 Fuentes y descargas",
        label_visibility="collapsed",
        key="vista_maestros",
    )

    st.divider()

    if vista == "📂 Fuentes y descargas":
        render_fuentes()

    elif vista == "👥 Maestro Clientes":
        render_clientes()

    elif vista == "📈 Históricos":
        render_historicos()

    else:
        render_publicacion()
