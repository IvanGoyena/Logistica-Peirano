from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.consultas.leer_gestion_consultas import (
    obtener_urgencias_activas,
    obtener_solicitudes_abiertas,
    obtener_historial_solicitudes,
    obtener_historial_urgencias,
    obtener_historial_reclamos,
)
from utils.consultas.leer_devoluciones import (
    obtener_cancelaciones_activas,
    obtener_historial_cancelaciones,
)
from utils.consultas.gestion_urgencias_digip import (
    obtener_urgencias_pendientes_digip,
    obtener_pedidos_pendientes_digip,
)


@st.cache_data(
    ttl=60,
    max_entries=4,
    show_spinner=False,
)
def cargar_gestion_comercial_cache() -> dict[str, pd.DataFrame]:
    """
    Centraliza la lectura de la gestiÃ³n persistida en Google Sheets.

    Esta capa es intencionalmente independiente de los crudos WMS/ERP.
    """
    return {
        "urgencias_activas": obtener_urgencias_activas(),
        "solicitudes_abiertas": obtener_solicitudes_abiertas(),
        "solicitudes_totales": obtener_historial_solicitudes(),
        "urgencias_totales": obtener_historial_urgencias(),
        "reclamos_totales": obtener_historial_reclamos(),
    }


@st.cache_data(
    ttl=60,
    max_entries=4,
    show_spinner=False,
)
def cargar_cancelaciones_cache() -> dict[str, pd.DataFrame]:
    """Lee la gestiÃ³n de cancelaciones de entrega desde Google Sheets."""
    return {
        "totales": obtener_historial_cancelaciones(),
        "activas": obtener_cancelaciones_activas(),
    }


@st.cache_data(
    ttl=30,
    max_entries=4,
    show_spinner=False,
)
def cargar_urgencias_digip_cache() -> dict[str, object]:
    """
    Obtiene las urgencias comerciales todavÃ­a pendientes de ejecuciÃ³n
    por el worker DIGIP.
    """
    return {
        "urgencias": obtener_urgencias_pendientes_digip(),
        "pedidos": obtener_pedidos_pendientes_digip(),
    }


def invalidar_cache_gestion() -> None:
    """
    Invalida Ãºnicamente datos dinÃ¡micos de Google Sheets.

    Registrar, editar o cerrar una gestiÃ³n no vuelve a leer los crudos
    operativos de WMS/ERP/Maestros.
    """
    cargar_gestion_comercial_cache.clear()
    cargar_cancelaciones_cache.clear()
    cargar_urgencias_digip_cache.clear()

