from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.google_sheets import (
    COLUMNAS_CANCELACIONES_ENTREGA,
    asegurar_hoja,
    leer_hoja,
)


@st.cache_data(ttl=600, show_spinner=False)
def _validar_hoja_cancelaciones() -> bool:
    """Valida la hoja una sola vez cada 10 minutos."""
    asegurar_hoja("CancelacionesEntrega")
    return True


@st.cache_data(ttl=30, show_spinner=False)
def leer_cancelaciones_entrega() -> pd.DataFrame:
    """
    Lee CancelacionesEntrega una sola vez y conserva el resultado 30 segundos.

    Streamlit devuelve una copia del DataFrame cacheado, por lo que puede
    filtrarse en cada página sin generar nuevas consultas a Google Sheets.
    """
    _validar_hoja_cancelaciones()
    tabla = leer_hoja("CancelacionesEntrega")

    if tabla is None or tabla.empty:
        return pd.DataFrame(columns=COLUMNAS_CANCELACIONES_ENTREGA)

    tabla = tabla.copy()

    for columna in COLUMNAS_CANCELACIONES_ENTREGA:
        if columna not in tabla.columns:
            tabla[columna] = ""

    return tabla


def invalidar_cache_devoluciones() -> None:
    """Fuerza una nueva lectura después de guardar un cambio."""
    leer_cancelaciones_entrega.clear()


def obtener_cancelaciones_activas(
    tabla: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if tabla is None:
        tabla = leer_cancelaciones_entrega()

    if tabla.empty:
        return tabla.copy()

    estados = (
        tabla["EstadoCancelacion"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return tabla.loc[
        ~estados.isin({"FINALIZADA", "CANCELADA"})
    ].reset_index(drop=True)


def obtener_historial_cancelaciones(
    tabla: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if tabla is None:
        tabla = leer_cancelaciones_entrega()

    return tabla.copy().reset_index(drop=True)


def estado_para_comercial(estado: str) -> str:
    estado = str(estado or "").strip()

    mapa = {
        "Pendiente de envío": "Pendiente de aviso",
        "Alerta enviada": "Enviada a Logística",
        "Enviada a Logística": "Enviada a Logística",
        "En gestión": "En gestión",
        "Entrega detenida": "En gestión",
        "IR generado": "En gestión",
        "Mercadería reingresada": "En gestión",
        "Finalizada": "Resuelta",
        "Ya despachado": "No se pudo detener",
        "Cancelada": "Cancelada",
    }

    return mapa.get(estado, estado or "Sin estado")
