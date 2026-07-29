from config import CARPETA_DATOS
import streamlit as st

from utils.leer_fuente_flexible import leer_archivo_flexible
from models.stock import (
    preparar_tabla_stock, preparar_max_min, construir_stock_total_detallado,
    construir_stock_total_por_articulo,
)
from models.recepcion import construir_pendientes_oc, construir_recepcion_agrupada
from models.stock_ocupacion import preparar_maestro_ubicaciones, construir_ocupacion_deposito
from utils.confirmaciones_oc import leer_confirmaciones_oc, aplicar_confirmaciones_oc

FUENTES_STOCK = {
    "pendientes_oc": ["Pendientes OC", "Pendientes_OC", "pendientes oc", "pendientes_oc"],
    "stock_detallado": ["stock_detallado", "Stock_Detallado", "Stock Detallado"],
    "stock_recepcion": ["stock_recepcion", "Stock_Recepcion", "Stock Recepcion"],
    "disponible": ["Disponible Digip", "Disponible_Digip", "disponible_digip"],
    "calidad": ["stock_calidad_laboratorio", "Stock_Calidad_Laboratorio"],
    "max_min": ["Max & Min", "Max_Min", "max_min"],
    "articulos": ["Maestro Articulo"],
    "volumetria": ["Maestro Volumetria"],
    "ubicaciones": ["Maestro Ubicaciones", "Maestro_Ubicaciones", "maestro ubicaciones", "maestro_ubicaciones"],
}

@st.cache_data(show_spinner="Cargando información de stock desde Drive...")
def cargar_fuentes_stock() -> dict[str, dict]:
    resultado = {}
    for clave, nombres in FUENTES_STOCK.items():
        df, nombre_resuelto = leer_archivo_flexible(
            CARPETA_DATOS, nombres, cache=clave in {"max_min", "articulos", "volumetria"}
        )
        resultado[clave] = {"df": df, "nombre_resuelto": nombre_resuelto}
    return resultado


def construir_contexto_stock() -> dict:
    fuentes = cargar_fuentes_stock()
    pendientes_oc_crudo = fuentes["pendientes_oc"]["df"].copy()
    stock_detallado_crudo = fuentes["stock_detallado"]["df"].copy()
    stock_recepcion_crudo = fuentes["stock_recepcion"]["df"].copy()

    tabla_stock_detallado = preparar_tabla_stock(stock_detallado_crudo, "Stock detallado")
    tabla_stock_recepcion = preparar_tabla_stock(stock_recepcion_crudo, "Recepción")
    tabla_disponible = preparar_tabla_stock(fuentes["disponible"]["df"], "Disponible DIGIP")
    tabla_calidad = preparar_tabla_stock(fuentes["calidad"]["df"], "Calidad / Laboratorio")
    tabla_max_min = preparar_max_min(fuentes["max_min"]["df"])
    tabla_articulos = fuentes["articulos"]["df"].copy()
    tabla_volumetria = fuentes["volumetria"]["df"].copy()
    tabla_maestro_ubicaciones = preparar_maestro_ubicaciones(fuentes["ubicaciones"]["df"])
    tabla_ocupacion, diagnostico_ocupacion = construir_ocupacion_deposito(
        fuentes["ubicaciones"]["df"], stock_detallado_crudo
    )

    tabla_pendientes_oc = construir_pendientes_oc(
        pendientes_oc_crudo, tabla_articulos, tabla_volumetria, tabla_max_min, fuentes["disponible"]["df"]
    )
    confirmaciones_oc = leer_confirmaciones_oc(CARPETA_DATOS)
    tabla_pendientes_oc = aplicar_confirmaciones_oc(
        tabla_pendientes_oc, confirmaciones_oc
    )
    tabla_recepcion_agrupada = construir_recepcion_agrupada(
        stock_recepcion_crudo, tabla_articulos, tabla_volumetria, tabla_max_min
    )
    tabla_stock_total_detallado = construir_stock_total_detallado(stock_detallado_crudo, stock_recepcion_crudo)
    tabla_stock_total_articulo = construir_stock_total_por_articulo(tabla_stock_total_detallado)
    articulos_stock = (
        tabla_stock_total_articulo.loc[tabla_stock_total_articulo["StockFisicoTotal"].gt(0), "ArticuloCodigo"].nunique()
        if not tabla_stock_total_articulo.empty else 0
    )
    return locals()
