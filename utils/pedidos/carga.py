from __future__ import annotations

import streamlit as st

from config import CARPETA_DATOS
from utils.leer_datos import leer_archivo
from utils.leer_fuente_flexible import leer_archivo_flexible
from utils.stock_carga import construir_fechas_oc_cobertura
from models.detalle import construir_tabla_detalle
from models.pedidos import construir_tabla_pedidos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos


@st.cache_data(show_spinner="Cargando datos operativos...")
def cargar_datos_base():
    return {
        "pedidos": leer_archivo(CARPETA_DATOS, "Pedidos DIGIP", cache=False),
        "detalle": leer_archivo(CARPETA_DATOS, "Detalle Pendientes", cache=False),
        "articulos": leer_archivo(CARPETA_DATOS, "Maestro Articulo", cache=True),
        "clientes": leer_archivo(CARPETA_DATOS, "Maestro Clientes", cache=True),
        "pendientes_erp": leer_archivo(CARPETA_DATOS, "Pedidos Pendientes", cache=False),
        "transmisiones": leer_archivo(CARPETA_DATOS, "Pedidos Transmicion", cache=False),
        "expresos": leer_archivo(CARPETA_DATOS, "Datos Expresos", cache=True),
        "volumetria": leer_archivo(CARPETA_DATOS, "Maestro Volumetria", cache=True),
    }


@st.cache_data(show_spinner="Cargando fuentes de cobertura...")
def cargar_datos_cobertura():
    return {
        "disponible_digip": leer_archivo_flexible(
            CARPETA_DATOS, ["Disponible Digip", "disponible_digip"], cache=False
        )[0],
        "stock_total_erp": leer_archivo_flexible(
            CARPETA_DATOS, ["info stock total", "Info Stock Total", "stock total erp"], cache=False
        )[0],
        "fechas_oc": construir_fechas_oc_cobertura(),
    }


@st.cache_data(show_spinner="Preparando tablas de pedidos...")
def construir_tablas_base_cacheadas(
    df_pedidos, df_detalle, df_articulos, df_clientes, df_volumetria,
    df_transmisiones, df_expresos, df_pendientes_erp,
):
    detalle = construir_tabla_detalle(df_detalle, df_articulos, df_volumetria)
    pedidos = construir_tabla_pedidos(
        df_pedidos, df_detalle, df_articulos, df_clientes, df_volumetria,
        tabla_detalle_preparada=detalle,
    )
    return {
        "detalle": detalle,
        "pedidos": pedidos,
        "transmisiones": construir_tabla_transmisiones(df_transmisiones),
        "expresos": construir_tabla_expresos(df_expresos),
        "clientes": construir_tabla_clientes(df_clientes),
        "pendientes_erp": construir_tabla_pendientes(df_pendientes_erp),
    }


def limpiar_cache_pedidos() -> None:
    cargar_datos_base.clear()
    cargar_datos_cobertura.clear()
    construir_fechas_oc_cobertura.clear()
    construir_tablas_base_cacheadas.clear()
