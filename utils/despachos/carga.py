from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo

from models.pedidos import construir_tabla_pedidos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos
from models.despachos.base_operativa import (
    construir_tabla_operativa_despachos,
)


# ==========================================================
# HISTORICO FILTRAR PREPARACION
# ==========================================================

@st.cache_data(
    ttl=270,
    show_spinner=False,
)
def _leer_historico_preparaciones() -> pd.DataFrame:
    """
    Consolida los archivos mensuales de Filtrar Preparacion
    disponibles dentro de Data_WMS.

    Replica la lógica ya utilizada por el módulo Tareas para
    no depender de un nombre fijo por mes.
    """

    carpeta = Path(CARPETA_WMS)

    if not carpeta.exists():
        return pd.DataFrame()

    rutas = sorted(
        {
            ruta.resolve()
            for patron in (
                "Filtrar Preparacion*.csv",
                "Filtrar Preparación*.csv",
                "Filtrar Preparacion*.xlsx",
                "Filtrar Preparación*.xlsx",
            )
            for ruta in carpeta.glob(patron)
            if ruta.is_file()
        }
    )

    tablas: list[pd.DataFrame] = []

    for ruta in rutas:
        try:
            if ruta.suffix.lower() == ".csv":
                tabla = pd.read_csv(
                    ruta,
                    sep=None,
                    engine="python",
                    encoding="utf-8-sig",
                )
            else:
                tabla = pd.read_excel(ruta)

            if tabla is not None and not tabla.empty:
                tabla = tabla.copy()
                tabla["ArchivoOrigenPreparacion"] = ruta.name
                tablas.append(tabla)

        except Exception:
            continue

    if not tablas:
        return pd.DataFrame()

    total = pd.concat(
        tablas,
        ignore_index=True,
        sort=False,
    )

    claves = [
        columna
        for columna in (
            "Id",
            "ContenedorDetalleId",
            "TareaId",
            "ControlContenedorId",
        )
        if columna in total.columns
    ]

    if claves:
        total = total.drop_duplicates(
            subset=claves,
            keep="last",
        )

    return total.reset_index(drop=True)


@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner="Cargando fuentes de Despachos...",
)
def cargar_fuentes_despachos() -> dict[str, pd.DataFrame]:
    """
    Lee cada fuente desde su origen real dentro del repositorio.

    WMS:
        Pedidos DIGIP

    ERP:
        Detalle Pendientes
        Pedidos Pendientes
        Pedidos Transmicion

    Maestros:
        Maestro Articulo
        Maestro Clientes
        Datos Expresos
        Maestro Volumetria
    """

    return {
        "pedidos": leer_archivo(
            CARPETA_WMS,
            "Pedidos DIGIP",
            cache=False,
        ),
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
        "informe_tareas": leer_archivo(
            CARPETA_WMS,
            "Informe Tareas",
            cache=False,
        ),
        "filtrar_preparacion": _leer_historico_preparaciones(),
    }


@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner="Preparando tablas de Despachos...",
)
def construir_contexto_despachos() -> dict:
    """
    Construye el contexto completo una sola vez por versión de caché.

    Las vistas reciben tablas ya listas y no conocen rutas de archivos.
    """

    datos = cargar_fuentes_despachos()

    df_pedidos = datos["pedidos"].copy()
    df_detalle = datos["detalle"].copy()
    df_articulos = datos["articulos"].copy()
    df_clientes = datos["clientes"].copy()
    df_pendientes_erp = datos["pendientes_erp"].copy()
    df_transmisiones = datos["transmisiones"].copy()
    df_expresos = datos["expresos"].copy()
    df_volumetria = datos["volumetria"].copy()
    df_informe_tareas = datos["informe_tareas"].copy()
    df_filtrar_preparacion = datos["filtrar_preparacion"].copy()

    tabla_pedidos = construir_tabla_pedidos(
        df_pedidos,
        df_detalle,
        df_articulos,
        df_clientes,
        df_volumetria,
    )

    tabla_transmisiones = construir_tabla_transmisiones(
        df_transmisiones
    )

    tabla_expresos = construir_tabla_expresos(
        df_expresos
    )

    tabla_clientes = construir_tabla_clientes(
        df_clientes
    )

    tabla_pendientes_erp = construir_tabla_pendientes(
        df_pendientes_erp
    )

    tabla_operativa = construir_tabla_operativa_despachos(
        tabla_pedidos=tabla_pedidos,
        tabla_transmisiones=tabla_transmisiones,
        tabla_pendientes_erp=tabla_pendientes_erp,
        tabla_clientes=tabla_clientes,
        tabla_expresos=tabla_expresos,
    )

    return {
        "df_pedidos": df_pedidos,
        "df_detalle": df_detalle,
        "df_articulos": df_articulos,
        "df_clientes": df_clientes,
        "df_pendientes_erp": df_pendientes_erp,
        "df_transmisiones": df_transmisiones,
        "df_expresos": df_expresos,
        "df_volumetria": df_volumetria,
        "df_informe_tareas": df_informe_tareas,
        "df_filtrar_preparacion": df_filtrar_preparacion,
        "tabla": tabla_operativa,
    }


def limpiar_cache_despachos() -> None:
    """
    Limpia solamente las cachés propias de Despachos.
    Evita usar st.cache_data.clear(), que invalida toda la aplicación.
    """

    cargar_fuentes_despachos.clear()
    construir_contexto_despachos.clear()
    _leer_historico_preparaciones.clear()
