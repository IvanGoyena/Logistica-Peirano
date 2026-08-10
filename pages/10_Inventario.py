import streamlit as st

from utils.autenticacion import requerir_roles

requerir_roles(
    "admin",
    "gerencia",
    "logistica",
    "supervisor",
)

st.set_page_config(
    page_title="Inventario",
    page_icon="🧮",
    layout="wide",
)

from views.inventario.principal import render_inventario

render_inventario()
