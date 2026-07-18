from contextlib import contextmanager
from time import perf_counter

import pandas as pd
import streamlit as st


@contextmanager
def medir_tiempo(nombre: str):
    inicio = perf_counter()

    try:
        yield
    finally:
        duracion = perf_counter() - inicio

        if st.session_state.get("debug_rendimiento", False):
            st.caption(
                f"⏱️ {nombre}: {duracion:.3f} segundos"
            )


def mostrar_info_dataframe(
    nombre: str,
    df: pd.DataFrame,
) -> None:
    if not st.session_state.get("debug_rendimiento", False):
        return

    memoria_mb = (
        df.memory_usage(deep=True).sum()
        / 1024
        / 1024
    )

    st.caption(
        f"📦 {nombre}: "
        f"{len(df):,} filas × {len(df.columns)} columnas "
        f"— {memoria_mb:.2f} MB"
    )