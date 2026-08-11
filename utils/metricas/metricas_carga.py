from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo
from models.metricas.metricas import (
    construir_fuentes_metricas,
    firma_fuentes_metricas,
    limpiar_cache_mes_actual_metricas,
)
from models.metricas.limpieza_metricas import ejecutar_etl_metricas
from models.metricas.volumetria import construir_tabla_volumetria
from models.metricas.enriquecimiento_metricas import ejecutar_enriquecimiento_metricas
from models.metricas.base_historica_metricas import publicar_base_historica_metricas
from models.cumplimiento.base_analitica_pedidos import construir_ciclo_vida_pedidos
from models.cumplimiento.base_fillrate import construir_base_fillrate
from models.cumplimiento.planificacion_servicio import (
    enriquecer_ciclo_con_planificacion,
    firma_maestro_clientes,
)
from models.cumplimiento.vinculacion_cuentas_pedidos import asignar_hr_pedidos_cuenta_2
from models.cumplimiento.universo_servicio import construir_universo_servicio
from models.cumplimiento.historico_proceso_pedidos import (
    firma_archivos_proceso,
    cargar_historico_proceso,
    enriquecer_metricas_con_pedido,
    limpiar_cache_historico_proceso,
)
from models.metricas.metricas_dashboard import preparar_base_analitica


@st.cache_data(
    show_spinner="Leyendo, limpiando y enriqueciendo históricos...",
    max_entries=2,
    persist="disk",
)
def cargar_base_metricas(
    firma_historicos: tuple,
    firma_proceso: tuple,
) -> dict:
    _ = firma_historicos, firma_proceso

    # Históricos operativos de Control y Preparación.
    fuentes = construir_fuentes_metricas(
        CARPETA_WMS
    )

    etl = ejecutar_etl_metricas(
        df_control=fuentes["control"],
        df_preparacion=fuentes["preparacion"],
    )

    # Filtrar Preparación [mes/año] también vive en Data_WMS.
    historico_proceso = cargar_historico_proceso(
        CARPETA_WMS
    )

    (
        tareas_con_pedido,
        detalle_con_pedido,
        diagnostico_pedidos,
    ) = enriquecer_metricas_con_pedido(
        etl["tareas"],
        etl["detalle"],
        historico_proceso["detalle"],
    )

    etl["tareas"] = tareas_con_pedido
    etl["detalle"] = detalle_con_pedido

    # Maestros.
    df_articulos = leer_archivo(
        CARPETA_MAESTROS,
        "Maestro Articulo",
        cache=True,
    )

    df_volumetria = leer_archivo(
        CARPETA_MAESTROS,
        "Maestro Volumetria",
        cache=True,
    )

    tabla_volumetria = construir_tabla_volumetria(
        df_volumetria
    )

    enriquecimiento = ejecutar_enriquecimiento_metricas(
        df_tareas=etl["tareas"],
        df_detalle=etl["detalle"],
        df_articulos=df_articulos,
        tabla_volumetria=tabla_volumetria,
    )

    tareas, detalle = preparar_base_analitica(
        enriquecimiento["tareas_enriquecidas"],
        enriquecimiento["detalle_enriquecido"],
    )

    return {
        "fuentes": fuentes,
        "etl": etl,
        "df_articulos": df_articulos,
        "tabla_volumetria": tabla_volumetria,
        "enriquecimiento": enriquecimiento,
        "historico_proceso": historico_proceso,
        "diagnostico_pedidos_proceso": diagnostico_pedidos,
        "df_tareas": tareas,
        "df_detalle": detalle,
    }


@st.cache_data(
    show_spinner="Preparando base analítica de pedidos...",
    max_entries=2,
    persist="disk",
)
def cargar_ciclo_pedidos(
    firma_historicos: tuple,
    firma_proceso: tuple,
    firma_clientes: tuple,
    tareas: pd.DataFrame,
    detalle_proceso: pd.DataFrame,
    momento_evaluacion: str,
) -> dict:
    _ = (
        firma_historicos,
        firma_proceso,
        firma_clientes,
        momento_evaluacion,
    )

    try:
        pedidos = leer_archivo(
            CARPETA_WMS,
            "Pedidos DIGIP",
            cache=False,
        )
    except Exception:
        pedidos = pd.DataFrame()

    try:
        hojas = leer_archivo(
            CARPETA_ERP,
            "Hojas de Ruta",
            cache=False,
        )
    except Exception:
        hojas = pd.DataFrame()

    try:
        clientes = leer_archivo(
            CARPETA_MAESTROS,
            "Maestro Clientes",
            cache=True,
        )
    except Exception:
        clientes = pd.DataFrame()

    try:
        base_fillrate, diagnostico_fillrate = construir_base_fillrate(
            df_pedidos=pedidos,
            df_proceso_pedidos=detalle_proceso,
            df_clientes=clientes,
        )

        ciclo, diagnostico = construir_ciclo_vida_pedidos(
            df_pedidos=pedidos,
            df_tareas=tareas,
            df_hojas_ruta=hojas,
            df_proceso_pedidos=detalle_proceso,
        )

        ciclo, diagnostico_planificacion = enriquecer_ciclo_con_planificacion(
            ciclo,
            clientes,
        )

        ciclo, diagnostico_vinculacion = asignar_hr_pedidos_cuenta_2(
            ciclo,
            ventana_maxima_horas=72,
            ventana_cliente_dias=7,
        )

        ciclo, diagnostico_planificacion_final = enriquecer_ciclo_con_planificacion(
            ciclo,
            clientes,
        )

        ciclo_activo, ciclo_excluido, diagnostico_universo = (
            construir_universo_servicio(
                ciclo,
                momento_evaluacion=momento_evaluacion,
                ventana_maduracion_horas=48,
            )
        )

        diagnostico = {
            **diagnostico,
            **{
                f"fillrate_{clave}": valor
                for clave, valor in diagnostico_fillrate.items()
            },
            **{
                f"planificacion_{clave}": valor
                for clave, valor in diagnostico_planificacion_final.items()
            },
            **{
                f"vinculacion_{clave}": valor
                for clave, valor in diagnostico_vinculacion.items()
            },
            **{
                f"universo_{clave}": valor
                for clave, valor in diagnostico_universo.items()
            },
        }

        ciclo = ciclo_activo
        error = None

    except Exception as exc:
        ciclo = pd.DataFrame()
        ciclo_excluido = pd.DataFrame()
        base_fillrate = pd.DataFrame()
        diagnostico = {}
        error = exc

    return {
        "df_ciclo_pedidos": ciclo,
        "df_fillrate_pedidos": base_fillrate,
        "df_ciclo_excluidos": ciclo_excluido,
        "diagnostico_ciclo": diagnostico,
        "error_ciclo_pedidos": error,
    }


def construir_contexto_base_metricas() -> dict:
    # Cada firma apunta ahora a su origen real.
    firma = firma_fuentes_metricas(
        CARPETA_WMS
    )

    firma_proceso = firma_archivos_proceso(
        CARPETA_WMS
    )

    firma_clientes = firma_maestro_clientes(
        CARPETA_MAESTROS
    )

    datos = cargar_base_metricas(
        firma,
        firma_proceso,
    )

    try:
        estado_publicacion = publicar_base_historica_metricas(
            tareas=datos["df_tareas"],
            detalle=datos["df_detalle"],
            firma_historicos=firma,
            carpeta_datos=CARPETA_WMS,
            publicar_github=True,
        )
        error_publicacion = None

    except Exception as exc:
        estado_publicacion = {}
        error_publicacion = exc

    return {
        **datos,
        "firma_historicos": firma,
        "firma_proceso_pedidos": firma_proceso,
        "firma_maestro_clientes": firma_clientes,
        "estado_publicacion": estado_publicacion,
        "error_publicacion": error_publicacion,
        "df_calidad_enriquecimiento": datos[
            "enriquecimiento"
        ]["calidad_enriquecimiento"],
    }


def completar_contexto_vista(
    vista: str,
    contexto: dict,
) -> dict:
    """Completa solamente los datos pesados requeridos por la vista activa."""

    nombre_vista = str(
        vista or ""
    ).strip().upper()

    es_vista_cumplimiento = (
        "CUMPLIMIENTO" in nombre_vista
        or "CICLO" in nombre_vista
        or "PEDIDOS" in nombre_vista
    )

    if es_vista_cumplimiento:
        return {
            **contexto,
            **cargar_ciclo_pedidos(
                contexto["firma_historicos"],
                contexto["firma_proceso_pedidos"],
                contexto["firma_maestro_clientes"],
                contexto["df_tareas"],
                contexto.get(
                    "historico_proceso",
                    {},
                ).get(
                    "detalle",
                    pd.DataFrame(),
                ),
                pd.Timestamp.now(
                    tz="America/Argentina/Buenos_Aires"
                ).floor("h").isoformat(),
            ),
        }

    return contexto


def limpiar_cache_metricas_completa() -> None:
    limpiar_cache_mes_actual_metricas()
    limpiar_cache_historico_proceso()
    cargar_base_metricas.clear()
    cargar_ciclo_pedidos.clear()
