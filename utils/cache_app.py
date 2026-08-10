from __future__ import annotations

import streamlit as st


def limpiar_cache_aplicacion() -> None:
    """
    Limpia la caché de datos global de Streamlit.

    Incluye DataFrames, lecturas cacheadas de Excel/CSV, contextos
    derivados y cualquier función decorada con @st.cache_data.

    No limpia @st.cache_resource para no reiniciar conexiones,
    clientes de API u otros recursos compartidos innecesariamente.
    """
    st.cache_data.clear()
