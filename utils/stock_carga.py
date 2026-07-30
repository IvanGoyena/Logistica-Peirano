from __future__ import annotations

from config import CARPETA_DATOS
import pandas as pd
import streamlit as st

from utils.leer_fuente_flexible import leer_archivo_flexible
from models.stock import (
    preparar_tabla_stock,
    preparar_max_min,
    construir_stock_total_detallado,
    construir_stock_total_por_articulo,
)
from models.recepcion import construir_pendientes_oc, construir_recepcion_agrupada
from models.stock_ocupacion import preparar_maestro_ubicaciones, construir_ocupacion_deposito
from utils.confirmaciones_oc import leer_confirmaciones_oc, aplicar_confirmaciones_oc


# =====================================================
# FUENTES DEL MÓDULO
# =====================================================
# Estas cuatro fuentes cambian durante el día y se vuelven a leer con el botón
# "Actualizar stock".
FUENTES_DINAMICAS_STOCK = {
    "stock_recepcion": [
        "Stock Recepcion", "Stock Recepción", "stock_recepcion",
        "Stock_Recepcion", "Stock Recepcion",
    ],
    "disponible": [
        "Stock Disponible", "Stock_Disponible", "stock_disponible",
        "Disponible Digip", "Disponible_Digip", "disponible_digip",
    ],
    "stock_detallado": [
        "Stock Digip", "Stock DIGIP", "Stock_Digip", "stock_digip",
        "stock_detallado", "Stock_Detallado", "Stock Detallado",
    ],
    "calidad": [
        "Stock Calidad Laboratorio", "Stock_Calidad_Laboratorio",
        "stock_calidad_laboratorio", "Calidad Laboratorio",
    ],
}

# El resto se trata como información maestra o de referencia. Se conserva en
# caché durante más tiempo y no se invalida al actualizar el stock operativo.
FUENTES_MAESTRAS_STOCK = {
    "pendientes_oc": [
        "Pendientes OC", "Pendientes_OC", "pendientes oc", "pendientes_oc",
    ],
    "max_min": ["Max & Min", "Max_Min", "max_min"],
    "articulos": ["Maestro Articulo", "Maestro Artículos", "Maestro Articulos"],
    "volumetria": ["Maestro Volumetria", "Maestro Volumetría"],
    "ubicaciones": [
        "Maestro Ubicaciones", "Maestro_Ubicaciones",
        "maestro ubicaciones", "maestro_ubicaciones",
    ],
}

# Compatibilidad con cualquier import anterior que consulte este diccionario.
FUENTES_STOCK = {**FUENTES_DINAMICAS_STOCK, **FUENTES_MAESTRAS_STOCK}


def _leer_grupo_fuentes(
    configuracion: dict[str, list[str]],
    *,
    usar_cache_lector: bool,
) -> dict[str, dict]:
    resultado: dict[str, dict] = {}
    for clave, nombres in configuracion.items():
        dataframe, nombre_resuelto = leer_archivo_flexible(
            CARPETA_DATOS,
            nombres,
            cache=usar_cache_lector,
        )
        resultado[clave] = {
            "df": dataframe if dataframe is not None else pd.DataFrame(),
            "nombre_resuelto": nombre_resuelto,
        }
    return resultado


@st.cache_data(
    ttl=120,
    max_entries=4,
    show_spinner="Actualizando Stock Recepción, Disponible, DIGIP y Calidad...",
)
def cargar_fuentes_dinamicas_stock() -> dict[str, dict]:
    """Lee únicamente las cuatro fuentes operativas que cambian durante el día."""
    return _leer_grupo_fuentes(
        FUENTES_DINAMICAS_STOCK,
        usar_cache_lector=False,
    )


@st.cache_data(
    ttl=3600,
    max_entries=2,
    show_spinner="Cargando maestros del módulo de Stock...",
)
def cargar_maestros_stock() -> dict[str, dict]:
    """Lee maestros y referencias compartidas, con una caché más prolongada."""
    return _leer_grupo_fuentes(
        FUENTES_MAESTRAS_STOCK,
        usar_cache_lector=True,
    )


def cargar_fuentes_stock() -> dict[str, dict]:
    """Compatibilidad: devuelve dinámicas y maestros dentro de un único diccionario."""
    return {
        **cargar_fuentes_dinamicas_stock(),
        **cargar_maestros_stock(),
    }


def limpiar_cache_fuentes_dinamicas_stock() -> None:
    """Invalida solamente los cuatro reportes operativos del módulo."""
    cargar_fuentes_dinamicas_stock.clear()


def construir_contexto_stock() -> dict:
    """Construye todas las tablas que consumen las vistas del módulo de Stock."""
    fuentes_dinamicas = cargar_fuentes_dinamicas_stock()
    fuentes_maestras = cargar_maestros_stock()
    fuentes = {**fuentes_dinamicas, **fuentes_maestras}

    pendientes_oc_crudo = fuentes["pendientes_oc"]["df"].copy()
    stock_detallado_crudo = fuentes["stock_detallado"]["df"].copy()
    stock_recepcion_crudo = fuentes["stock_recepcion"]["df"].copy()

    tabla_stock_detallado = preparar_tabla_stock(
        stock_detallado_crudo,
        "Stock DIGIP",
    )
    tabla_stock_recepcion = preparar_tabla_stock(
        stock_recepcion_crudo,
        "Stock Recepción",
    )
    tabla_disponible = preparar_tabla_stock(
        fuentes["disponible"]["df"],
        "Stock Disponible",
    )
    tabla_calidad = preparar_tabla_stock(
        fuentes["calidad"]["df"],
        "Stock Calidad / Laboratorio",
    )

    tabla_max_min = preparar_max_min(fuentes["max_min"]["df"])
    tabla_articulos = fuentes["articulos"]["df"].copy()
    tabla_volumetria = fuentes["volumetria"]["df"].copy()
    tabla_maestro_ubicaciones = preparar_maestro_ubicaciones(
        fuentes["ubicaciones"]["df"]
    )

    tabla_ocupacion, diagnostico_ocupacion = construir_ocupacion_deposito(
        fuentes["ubicaciones"]["df"],
        stock_detallado_crudo,
    )

    tabla_pendientes_oc = construir_pendientes_oc(
        pendientes_oc_crudo,
        tabla_articulos,
        tabla_volumetria,
        tabla_max_min,
        fuentes["disponible"]["df"],
    )

    confirmaciones_oc = leer_confirmaciones_oc(CARPETA_DATOS)
    tabla_pendientes_oc = aplicar_confirmaciones_oc(
        tabla_pendientes_oc,
        confirmaciones_oc,
    )

    # Esquema defensivo para despliegues donde Pendientes OC esté vacío o aún
    # no tenga todas las columnas calculadas.
    columnas_fecha = [
        "FechaIngresoEstimada",
        "FechaConfirmadaIngreso",
        "FechaOperativaIngreso",
    ]
    for columna in columnas_fecha:
        if columna not in tabla_pendientes_oc.columns:
            tabla_pendientes_oc[columna] = pd.NaT
        tabla_pendientes_oc[columna] = pd.to_datetime(
            tabla_pendientes_oc[columna],
            errors="coerce",
        )
    for columna in ["TipoFechaIngreso", "EstadoFechaIngreso"]:
        if columna not in tabla_pendientes_oc.columns:
            tabla_pendientes_oc[columna] = ""

    tabla_pendientes_oc["FechaOperativaIngreso"] = (
        tabla_pendientes_oc["FechaConfirmadaIngreso"]
        .combine_first(tabla_pendientes_oc["FechaIngresoEstimada"])
    )

    tabla_recepcion_agrupada = construir_recepcion_agrupada(
        stock_recepcion_crudo,
        tabla_articulos,
        tabla_volumetria,
        tabla_max_min,
    )

    tabla_stock_total_detallado = construir_stock_total_detallado(
        stock_detallado_crudo,
        stock_recepcion_crudo,
    )
    tabla_stock_total_articulo = construir_stock_total_por_articulo(
        tabla_stock_total_detallado
    )

    articulos_stock = (
        tabla_stock_total_articulo.loc[
            tabla_stock_total_articulo["StockFisicoTotal"].gt(0),
            "ArticuloCodigo",
        ].nunique()
        if not tabla_stock_total_articulo.empty
        else 0
    )

    return {
        "fuentes": fuentes,
        "fuentes_dinamicas": fuentes_dinamicas,
        "fuentes_maestras": fuentes_maestras,
        "pendientes_oc_crudo": pendientes_oc_crudo,
        "stock_detallado_crudo": stock_detallado_crudo,
        "stock_recepcion_crudo": stock_recepcion_crudo,
        "tabla_stock_detallado": tabla_stock_detallado,
        "tabla_stock_recepcion": tabla_stock_recepcion,
        "tabla_disponible": tabla_disponible,
        "tabla_calidad": tabla_calidad,
        "tabla_max_min": tabla_max_min,
        "tabla_articulos": tabla_articulos,
        "tabla_volumetria": tabla_volumetria,
        "tabla_maestro_ubicaciones": tabla_maestro_ubicaciones,
        "tabla_ocupacion": tabla_ocupacion,
        "diagnostico_ocupacion": diagnostico_ocupacion,
        "tabla_pendientes_oc": tabla_pendientes_oc,
        "confirmaciones_oc": confirmaciones_oc,
        "tabla_recepcion_agrupada": tabla_recepcion_agrupada,
        "tabla_stock_total_detallado": tabla_stock_total_detallado,
        "tabla_stock_total_articulo": tabla_stock_total_articulo,
        "articulos_stock": articulos_stock,
    }
