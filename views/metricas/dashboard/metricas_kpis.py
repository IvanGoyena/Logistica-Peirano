import streamlit as st

from models.metricas.metricas_dashboard import calcular_variacion
from utils.metricas.metricas_helpers import (
    formatear_decimal,
    formatear_entero,
    formatear_peso,
    texto_delta,
)


def render(contexto: dict) -> None:
    actual, anterior = contexto["actual"], contexto["anterior"]
    st.markdown("### Actividad")
    columnas = st.columns(8)
    specs = [
        ("📋 Tareas", "Tareas", lambda v: formatear_entero(v)),
        ("📦 Unidades", "Unidades", lambda v: formatear_entero(v)),
        ("🧾 Líneas", "Lineas", lambda v: formatear_entero(v)),
        ("📐 Volumen", "VolumenM3", lambda v: formatear_entero(v) + " m³"),
        ("⚖️ Peso", "PesoKg", formatear_peso),
        ("⚡ Unid./hora", "UnidadesHora", lambda v: formatear_entero(v)),
        ("👥 Usuarios", "UsuariosActivos", lambda v: formatear_entero(v)),
        ("📏 Unid./línea", "PromedioUnidadesLinea", lambda v: formatear_decimal(v, 2)),
    ]
    for col, (titulo, clave, fmt) in zip(columnas, specs):
        with col:
            st.metric(
                titulo,
                fmt(actual[clave]),
                texto_delta(calcular_variacion(actual[clave], anterior[clave])),
            )
    st.divider()
