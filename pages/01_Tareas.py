import streamlit as st

from utils.autenticacion import requerir_roles

requerir_roles("admin", "gerencia", "logistica", "supervisor")

st.set_page_config(
    page_title="Centro de Control Operativo",
    page_icon="📋",
    layout="wide",
)

from views.tareas.principal import render_tareas

render_tareas()
