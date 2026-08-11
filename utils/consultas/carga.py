from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo


@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner="Cargando información comercial...",
)
def cargar_datos_consultas() -> dict[str, pd.DataFrame]:
    """
    Carga únicamente los crudos operativos de Consultas Comerciales.

    Los reportes y maestros se consumen desde las carpetas versionadas
    en el repositorio. Google Sheets queda reservado para la gestión
    dinámica: solicitudes, urgencias, anulaciones, reclamos y cola.
    """

    return {
        # ======================================================
        # WMS
        # ======================================================
        "pedidos": leer_archivo(
            CARPETA_WMS,
            "Pedidos DIGIP",
            cache=False,
        ),
        "tareas": leer_archivo(
            CARPETA_WMS,
            "Informe Tareas",
            cache=False,
        ),

        # ======================================================
        # ERP
        # ======================================================
        "detalle": leer_archivo(
            CARPETA_ERP,
            "Detalle Pendientes",
            cache=False,
        ),
        "pendientes_erp": leer_archivo(
            CARPETA_ERP,
            "Pedidos Pendientes",
            cache=False,
        ),
        "transmisiones": leer_archivo(
            CARPETA_ERP,
            "Pedidos Transmicion",
            cache=False,
        ),

        # ======================================================
        # MAESTROS
        # ======================================================
        "articulos": leer_archivo(
            CARPETA_MAESTROS,
            "Maestro Articulo",
            cache=True,
        ),
        "clientes": leer_archivo(
            CARPETA_MAESTROS,
            "Maestro Clientes",
            cache=True,
        ),
        "expresos": leer_archivo(
            CARPETA_MAESTROS,
            "Datos Expresos",
            cache=True,
        ),
        "volumetria": leer_archivo(
            CARPETA_MAESTROS,
            "Maestro Volumetria",
            cache=True,
        ),
    }


def limpiar_cache_datos_consultas() -> None:
    """Invalida solamente los crudos operativos del módulo."""

    cargar_datos_consultas.clear()
