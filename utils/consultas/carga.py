from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text as sql_text

from database import engine


# ==========================================================
# CONSULTAS COMERCIALES - FUENTES SQL OPTIMIZADAS
# ==========================================================


def _leer_sql(consulta: str) -> pd.DataFrame:
    with engine.connect() as conexion:
        return pd.read_sql_query(sql_text(consulta), conexion)


@st.cache_data(
    ttl=45,
    max_entries=2,
    show_spinner="Cargando pedidos comerciales...",
)
def cargar_datos_consultas() -> dict[str, pd.DataFrame]:
    """
    Carga mínima necesaria para la pantalla principal.

    Diferencias respecto de la versión anterior:
    - usa analytics.vw_consultas_comerciales como contrato propio del módulo;
    - no carga maestros de clientes/artículos al abrir el módulo;
    - Informe Tareas toma sólo el último run y sólo 4 columnas.
    """

    pedidos = _leer_sql(
        """
        SELECT
            "Pedido",
            "Fecha",
            "FechaCreacion",
            "FechaFinControl",
            "FechaTransmisionERP",
            "ClienteCodigo",
            "CodigoLogistico",
            "Cliente",
            "TotalUnidadesOperativas",
            "VolumenM3",
            "VolumetriaCompleta",
            "VolumetriaOrigen",
            "Planificacion",
            "CodigoDespacho",
            "Despacho",
            "Estado",
            "EstadoWMS",
            "EstadoPreparacion",
            "PreparacionID",
            "EstadoDatosERP",
            "PresenteWMSActual",
            "UltimaVezWMS",
            "EsMovimientoInterno",
            "NroEnvio"
        FROM analytics.vw_consultas_comerciales
        ORDER BY
            "FechaTransmisionERP" DESC NULLS LAST,
            "FechaCreacion" DESC NULLS LAST,
            "Pedido" DESC;
        """
    )

    # raw.informe_tareas se ingiere de manera periódica. Para Consultas
    # interesa el estado ACTUAL de carros, no todas las fotos históricas.
    tareas = _leer_sql(
        """
        WITH ultimo_run AS (
            SELECT run_id
            FROM raw.informe_tareas
            WHERE run_id IS NOT NULL
            ORDER BY loaded_at DESC NULLS LAST
            LIMIT 1
        )
        SELECT
            t.preparacion_id   AS "PreparacionId",
            t.contenedor_id    AS "ContenedorId",
            t.contenedor_numero AS "ContenedorNumero",
            t.tarea_estado     AS "TareaEstado"
        FROM raw.informe_tareas t
        WHERE t.run_id = (SELECT run_id FROM ultimo_run)
          AND t.preparacion_id IS NOT NULL
          AND (
                t.contenedor_numero IS NOT NULL
                OR t.contenedor_id IS NOT NULL
              );
        """
    )

    return {
        "pedidos": pedidos,
        "tareas": tareas,
    }


@st.cache_data(
    ttl=600,
    max_entries=2,
    show_spinner="Cargando maestros para el reclamo...",
)
def cargar_maestros_reclamos() -> dict[str, pd.DataFrame]:
    """
    Los maestros son pesados y sólo son necesarios si el usuario abre
    la carga de reclamos. Por eso se cargan de forma diferida.
    """

    clientes = _leer_sql(
        """
        SELECT
            codigo_cliente AS "ClienteCodigo",
            nombre         AS "ClienteDescripcion"
        FROM analytics.vw_maestro_clientes
        WHERE codigo_cliente IS NOT NULL
        ORDER BY nombre, codigo_cliente;
        """
    )

    articulos = _leer_sql(
        """
        SELECT
            codigo_articulo AS "CodigoArticulo",
            descripcion     AS "ArticuloDescripcion"
        FROM analytics.vw_maestro_articulos
        WHERE codigo_articulo IS NOT NULL
        ORDER BY codigo_articulo;
        """
    )

    return {
        "clientes": clientes,
        "articulos": articulos,
    }


def limpiar_cache_datos_consultas() -> None:
    cargar_datos_consultas.clear()


def limpiar_cache_maestros_reclamos() -> None:
    cargar_maestros_reclamos.clear()
