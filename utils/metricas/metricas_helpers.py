from __future__ import annotations

import pandas as pd
import streamlit as st

def formatear_entero(valor) -> str:

    return f"{float(valor):,.0f}".replace(",", ".")


def formatear_decimal(
    valor,
    decimales=1,
) -> str:

    texto = f"{float(valor):,.{decimales}f}"

    return (
        texto
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def formatear_peso(
    valor,
) -> str:
    """
    Muestra siempre el peso total en kilogramos.
    """

    return (
        formatear_entero(valor)
        + " kg"
    )


def texto_delta(
    variacion,
) -> str | None:
    """
    Devuelve una comparación breve pero informativa.
    """

    if variacion is None or pd.isna(variacion):
        return None

    signo = "+" if variacion >= 0 else ""

    return (
        f"{signo}{variacion:.1f}% "
        "vs período anterior"
    )


def limitar_previsualizacion(
    dataframe: pd.DataFrame,
    limite: int = 5000,
) -> pd.DataFrame:
    """
    Evita enviar cientos de miles de filas al navegador.
    La base completa sigue disponible en memoria.
    """

    if len(dataframe) <= limite:
        return dataframe

    return dataframe.head(limite)


def mostrar_insight(
    insight: dict,
):

    iconos = {
        "positivo": "📈",
        "alerta": "⚠️",
        "informativo": "💡",
    }

    icono = iconos.get(
        insight["tipo"],
        "💡",
    )

    st.markdown(
        f"""
        <div class="insight-card">
            <div class="insight-icon">{icono}</div>
            <div>
                <div class="insight-title">
                    {insight["titulo"]}
                </div>
                <div class="insight-text">
                    {insight["texto"]}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
