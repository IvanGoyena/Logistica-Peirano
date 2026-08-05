import streamlit as st

from utils.autenticacion import requerir_roles

requerir_roles("admin", "gerencia")

st.set_page_config(
    page_title="Pedidos",
    page_icon="📦",
    layout="wide",
)

from views.pedidos.principal import render_modulo_pedidos

render_modulo_pedidos()
