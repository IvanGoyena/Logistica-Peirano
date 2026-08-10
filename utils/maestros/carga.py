from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from config import CARPETA_DATOS
from models.clientes import construir_tabla_clientes
from models.expresos import construir_tabla_expresos
from models.pendiente import construir_tabla_pendientes
from models.transmisiones import construir_tabla_transmisiones
from models.volumetria import construir_tabla_volumetria
from models.maestros.catalogo import FUENTES_POR_CLAVE
from utils.leer_fuente_flexible import (
    fecha_archivo_flexible,
    leer_archivo_flexible,
)


@dataclass
class ResultadoFuente:
    clave: str
    dataframe: pd.DataFrame
    nombre_resuelto: str | None
    fecha: str
    error: str = ""

    @property
    def disponible(self) -> bool:
        return (
            isinstance(self.dataframe, pd.DataFrame)
            and not self.dataframe.empty
        )


def _transformar(
    clave: str,
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    if tabla is None or tabla.empty:
        return pd.DataFrame()

    tipo = FUENTES_POR_CLAVE[clave].tipo

    if tipo == "pendientes":
        return construir_tabla_pendientes(tabla)

    if tipo == "transmisiones":
        return construir_tabla_transmisiones(tabla)

    if tipo == "clientes":
        return construir_tabla_clientes(tabla)

    if tipo == "expresos":
        return construir_tabla_expresos(tabla)

    if tipo == "volumetria":
        return construir_tabla_volumetria(tabla)

    return tabla.copy()


@st.cache_data(
    ttl=300,
    max_entries=30,
    show_spinner=False,
)
def cargar_fuente_maestros(
    clave: str,
) -> ResultadoFuente:
    fuente = FUENTES_POR_CLAVE[clave]

    try:
        tabla, nombre = leer_archivo_flexible(
            CARPETA_DATOS,
            fuente.nombres,
            cache=fuente.cache,
        )

        tabla = _transformar(
            clave,
            tabla,
        )

        fecha = fecha_archivo_flexible(
            CARPETA_DATOS,
            nombre,
            fuente.nombres,
        )

        return ResultadoFuente(
            clave=clave,
            dataframe=tabla,
            nombre_resuelto=nombre,
            fecha=fecha,
        )

    except Exception as error:
        return ResultadoFuente(
            clave=clave,
            dataframe=pd.DataFrame(),
            nombre_resuelto=None,
            fecha="--",
            error=f"{type(error).__name__}: {error}",
        )


@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def cargar_crudos_clientes() -> dict[str, pd.DataFrame]:
    """
    Carga las fuentes con el nivel de detalle que necesita
    el actualizador del Maestro Clientes.

    Importante:
    - Maestro Clientes se entrega normalizado.
    - Pedidos DIGIP se entrega crudo.
    - Pedidos Pendientes ERP se entrega crudo, porque
      sincronizar_clientes necesita cod_cli, cod_dist,
      nombre y nro_com para reconstruir ClienteCodigoERP.
    """

    fuente_clientes = FUENTES_POR_CLAVE["clientes"]
    clientes_crudo, _ = leer_archivo_flexible(
        CARPETA_DATOS,
        fuente_clientes.nombres,
        cache=fuente_clientes.cache,
    )

    fuente_pendientes = FUENTES_POR_CLAVE["pendientes_erp"]
    pendientes_crudo, _ = leer_archivo_flexible(
        CARPETA_DATOS,
        fuente_pendientes.nombres,
        cache=False,
    )

    fuente_pedidos = FUENTES_POR_CLAVE["pedidos"]
    pedidos_crudo, _ = leer_archivo_flexible(
        CARPETA_DATOS,
        fuente_pedidos.nombres,
        cache=False,
    )

    return {
        "clientes": construir_tabla_clientes(
            clientes_crudo
        ),
        "pendientes_erp": (
            pendientes_crudo.copy()
            if isinstance(
                pendientes_crudo,
                pd.DataFrame,
            )
            else pd.DataFrame()
        ),
        "pedidos": (
            pedidos_crudo.copy()
            if isinstance(
                pedidos_crudo,
                pd.DataFrame,
            )
            else pd.DataFrame()
        ),
    }


def limpiar_cache_maestros(
    clave: str | None = None,
) -> None:
    if clave is None:
        cargar_fuente_maestros.clear()
        cargar_crudos_clientes.clear()
        return

    # Streamlit no invalida una entrada individual de forma
    # portable entre versiones; se limpia solamente la capa
    # liviana de este módulo.
    cargar_fuente_maestros.clear()

    if clave in {
        "clientes",
        "pendientes_erp",
        "pedidos",
    }:
        cargar_crudos_clientes.clear()
