from __future__ import annotations

import streamlit as st

from utils.autenticacion import requerir_roles
from views.devoluciones.principal import render

requerir_roles("admin", "gerencia", "logistica", "supervisor")

st.set_page_config(
    page_title="Devoluciones",
    page_icon="↩️",
    layout="wide",
)

render()
