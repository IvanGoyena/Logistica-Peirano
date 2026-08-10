from __future__ import annotations

import pandas as pd
import streamlit as st


@st.cache_data(max_entries=30, show_spinner=False)
def dataframe_a_csv(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
    ).encode("utf-8-sig")
