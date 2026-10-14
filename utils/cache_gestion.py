from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.consultas.leer_gestion_consultas import (
    leer_solicitudes,
    leer_reclamos,
)
from utils.consultas.leer_devoluciones import (
    leer_cancelaciones_entrega,
    obtener_cancelaciones_activas,
    obtener_historial_cancelaciones,
    invalidar_cache_devoluciones,
)

_ESTADOS_ABIERTOS_SOLICITUD = {
    "PENDIENTE", "PROGRAMADA", "EN REVISIÓN", "EN REVISION",
    "EN CURSO", "EN GESTIÓN", "EN GESTION",
}

def _estado(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.strip().str.upper()

@st.cache_data(ttl=45, max_entries=4, show_spinner=False)
def cargar_gestion_comercial_cache() -> dict[str, pd.DataFrame]:
    """
    Gestión comercial visible en el host: Solicitudes y Reclamos.
    Urgencia es un TipoSolicitud y ya no utiliza commercial.urgencia
    ni cola/worker DIGIP desde Consultas Comerciales.
    """
    solicitudes = leer_solicitudes()
    reclamos = leer_reclamos()

    if solicitudes is None:
        solicitudes = pd.DataFrame()
    if reclamos is None:
        reclamos = pd.DataFrame()

    if solicitudes.empty or "EstadoSolicitud" not in solicitudes.columns:
        solicitudes_abiertas = solicitudes.copy()
    else:
        estados = _estado(solicitudes["EstadoSolicitud"])
        solicitudes_abiertas = solicitudes.loc[
            estados.isin(_ESTADOS_ABIERTOS_SOLICITUD)
        ].copy().reset_index(drop=True)

    vacio = pd.DataFrame()
    return {
        "solicitudes_abiertas": solicitudes_abiertas,
        "solicitudes_totales": solicitudes.copy().reset_index(drop=True),
        "reclamos_totales": reclamos.copy().reset_index(drop=True),
        # Claves legacy vacías para que ninguna pantalla secundaria rompa
        # durante la transición. No representan una función disponible.
        "urgencias_activas": vacio.copy(),
        "urgencias_totales": vacio.copy(),
        "urgencias_digip": vacio.copy(),
        "pedidos_urgentes_digip": [],
    }

@st.cache_data(ttl=45, max_entries=4, show_spinner=False)
def cargar_cancelaciones_cache() -> dict[str, pd.DataFrame]:
    tabla = leer_cancelaciones_entrega()
    return {
        "totales": obtener_historial_cancelaciones(tabla),
        "activas": obtener_cancelaciones_activas(tabla),
    }

def invalidar_cache_gestion() -> None:
    cargar_gestion_comercial_cache.clear()
    cargar_cancelaciones_cache.clear()
    invalidar_cache_devoluciones()
