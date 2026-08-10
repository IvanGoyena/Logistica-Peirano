from __future__ import annotations

import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo
from utils.leer_fuente_flexible import leer_archivo_flexible
from utils.stock_carga import construir_fechas_oc_cobertura
from models.detalle import construir_tabla_detalle
from models.pedidos import construir_tabla_pedidos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos


# ==========================================================
# FUENTES BASE DEL MODULO PEDIDOS
# ==========================================================

@st.cache_data(
    show_spinner="Cargando datos operativos..."
)
def cargar_datos_base():
    return {
        # WMS
        "pedidos": leer_archivo(
            CARPETA_WMS,
            "Pedidos DIGIP",
            cache=False,
        ),

        # ERP
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

        # MAESTROS
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


# ==========================================================
# FUENTES DE COBERTURA
# ==========================================================

@st.cache_data(
    show_spinner="Cargando fuentes de cobertura..."
)
def cargar_datos_cobertura():
    return {
        # WMS
        "disponible_digip": leer_archivo_flexible(
            CARPETA_WMS,
            [
                "Disponible DIGIP",
                "Disponible Digip",
                "disponible_digip",
            ],
            cache=False,
        )[0],

        # ERP
        "stock_total_erp": leer_archivo_flexible(
            CARPETA_ERP,
            [
                "info stock total",
                "Info Stock Total",
                "stock total erp",
            ],
            cache=False,
        )[0],

        # Esta función se mantiene por ahora.
        # Su implementación vive en utils.stock_carga
        # y será revisada en la siguiente etapa.
        "fechas_oc": construir_fechas_oc_cobertura(),
    }


# ==========================================================
# TABLAS BASE CACHEADAS
# ==========================================================

@st.cache_data(
    show_spinner="Preparando tablas de pedidos..."
)
def construir_tablas_base_cacheadas(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes,
    df_volumetria,
    df_transmisiones,
    df_expresos,
    df_pendientes_erp,
):
    detalle = construir_tabla_detalle(
        df_detalle,
        df_articulos,
        df_volumetria,
    )

    pedidos = construir_tabla_pedidos(
        df_pedidos,
        df_detalle,
        df_articulos,
        df_clientes,
        df_volumetria,
        tabla_detalle_preparada=detalle,
    )

    return {
        "detalle": detalle,
        "pedidos": pedidos,
        "transmisiones": construir_tabla_transmisiones(
            df_transmisiones
        ),
        "expresos": construir_tabla_expresos(
            df_expresos
        ),
        "clientes": construir_tabla_clientes(
            df_clientes
        ),
        "pendientes_erp": construir_tabla_pendientes(
            df_pendientes_erp
        ),
    }


# ==========================================================
# INVALIDAR CACHE
# ==========================================================

def limpiar_cache_pedidos() -> None:
    cargar_datos_base.clear()
    cargar_datos_cobertura.clear()
    construir_fechas_oc_cobertura.clear()
    construir_tablas_base_cacheadas.clear()
