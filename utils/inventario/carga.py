from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_fuente_flexible import (
    leer_archivo_flexible,
)
from utils.inventario.normalizacion import (
    expandir_archivo_separado_por_punto_y_coma,
)


@dataclass(frozen=True)
class FuenteInventario:
    clave: str
    titulo: str
    carpeta: Path
    candidatos: tuple[str, ...]
    cache_maestro: bool = False
    obligatoria: bool = True


FUENTES = {
    # ======================================================
    # ERP
    # ======================================================
    "erp": FuenteInventario(
        clave="erp",
        titulo="Stock ERP",
        carpeta=CARPETA_ERP,
        candidatos=(
            "info stock total",
            "Info Stock Total",
            "INFO STOCK TOTAL",
        ),
    ),
    "erp_sanitarios": FuenteInventario(
        clave="erp_sanitarios",
        titulo="Stock ERP Sanitarios",
        carpeta=CARPETA_ERP,
        candidatos=(
            "Informe Stock Sanitarios",
            "informe stock sanitarios",
            "Stock Sanitarios",
            "stock sanitarios",
        ),
        obligatoria=False,
    ),

    # ======================================================
    # WMS
    # ======================================================
    "wms_stock_digip": FuenteInventario(
        clave="wms_stock_digip",
        titulo="Stock DIGIP comparable",
        carpeta=CARPETA_WMS,
        candidatos=(
            "Stock DIGIP",
            "Stock Digip",
            "stock digip",
            "Stock_DIGIP",
            "stock_digip",
        ),
    ),
    "wms_detalle_auxiliar": FuenteInventario(
        clave="wms_detalle_auxiliar",
        titulo="Stock detallado auxiliar WMS",
        carpeta=CARPETA_WMS,
        candidatos=(
            "Stock Detallado",
            "stock_detallado",
            "stock detallado",
            "Stock DIGIP",
            "Stock Digip",
        ),
        obligatoria=False,
    ),
    "wms_recepcion": FuenteInventario(
        clave="wms_recepcion",
        titulo="Stock Recepción WMS",
        carpeta=CARPETA_WMS,
        candidatos=(
            "Stock Recepcion",
            "Stock Recepción",
            "stock_recepcion",
            "stock recepcion",
        ),
        obligatoria=False,
    ),
    "wms_disponible": FuenteInventario(
        clave="wms_disponible",
        titulo="Disponible DIGIP",
        carpeta=CARPETA_WMS,
        candidatos=(
            "Stock Disponible",
            "Stock_Disponible",
            "stock_disponible",
            "Disponible DIGIP",
            "Disponible Digip",
            "disponible_digip",
            "disponible digip",
        ),
    ),

    # ======================================================
    # MAESTROS
    # ======================================================
    "articulos": FuenteInventario(
        clave="articulos",
        titulo="Maestro de artículos",
        carpeta=CARPETA_MAESTROS,
        candidatos=(
            "Maestro Articulo",
            "Maestro Artículos",
            "Maestro Articulos",
            "maestro articulo",
        ),
        cache_maestro=True,
        obligatoria=False,
    ),
    "ubicaciones": FuenteInventario(
        clave="ubicaciones",
        titulo="Maestro de ubicaciones",
        carpeta=CARPETA_MAESTROS,
        candidatos=(
            "Maestro Ubicaciones",
            "Maestro_Ubicaciones",
            "maestro ubicaciones",
            "maestro_ubicaciones",
        ),
        cache_maestro=True,
        obligatoria=False,
    ),
    "picking_config": FuenteInventario(
        clave="picking_config",
        titulo="Configuración Picking Max & Min",
        carpeta=CARPETA_MAESTROS,
        candidatos=(
            "Max & Min",
            "Max_Min",
            "max_min",
            "Max y Min",
            "UbicacionArticulo",
            "Ubicacion Articulo",
            "Configuracion Picking",
            "Configuración Picking",
        ),
        cache_maestro=True,
        obligatoria=False,
    ),
}


@st.cache_data(
    ttl=300,
    max_entries=16,
    show_spinner=False,
)
def _leer_fuente(
    carpeta: str,
    candidatos: tuple[str, ...],
    cache: bool,
) -> tuple[pd.DataFrame, str]:
    """
    Lee una fuente de Inventario desde su carpeta real
    dentro del repositorio.

    `carpeta` forma parte de la clave de caché para que
    fuentes con nombres similares no compartan entradas.
    """

    tabla, nombre = leer_archivo_flexible(
        Path(carpeta),
        list(candidatos),
        cache=cache,
    )

    if tabla is None:
        tabla = pd.DataFrame()

    tabla = expandir_archivo_separado_por_punto_y_coma(
        tabla
    )

    return (
        tabla,
        str(nombre or ""),
    )


def cargar_fuentes_inventario() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, str],
    list[str],
]:
    """
    Carga las fuentes del módulo desde:

    - Data_ERP
    - Data_WMS
    - Data_Maestros

    Inventario deja de depender de CARPETA_DATOS / Google Drive
    para sus reportes operativos y maestros.
    """

    datos: dict[str, pd.DataFrame] = {}
    nombres: dict[str, str] = {}
    errores: list[str] = []

    for clave, fuente in FUENTES.items():
        try:
            tabla, nombre = _leer_fuente(
                str(fuente.carpeta),
                fuente.candidatos,
                cache=fuente.cache_maestro,
            )

            datos[clave] = tabla.copy()
            nombres[clave] = nombre

            if (
                fuente.obligatoria
                and tabla.empty
            ):
                errores.append(
                    f"{fuente.titulo}: "
                    "la fuente está vacía."
                )

        except Exception as error:
            datos[clave] = pd.DataFrame()
            nombres[clave] = ""

            if fuente.obligatoria:
                errores.append(
                    f"{fuente.titulo}: {error}"
                )

    return datos, nombres, errores


def limpiar_cache_inventario() -> None:
    """
    Limpia únicamente la lectura de fuentes de Inventario.
    El snapshot y la base de cíclicos se limpian desde
    views.inventario.principal.
    """

    _leer_fuente.clear()
