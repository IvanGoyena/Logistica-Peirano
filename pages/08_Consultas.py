from __future__ import annotations

import streamlit as st

from utils.autenticacion import requerir_roles
from views.consultas.principal import render

requerir_roles(
    "admin",
    "gerencia",
    "logistica",
    "supervisor",
    "comercial",
)

st.set_page_config(
    page_title="Consultas Comerciales",
    page_icon="🔎",
    layout="wide",
)

render()
