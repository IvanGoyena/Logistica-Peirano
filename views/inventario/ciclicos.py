from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.inventario.ciclicos_datos import (
    construir_base_ciclicos,
)
from utils.inventario.persistencia import (
    inicializar_hojas_inventario,
)
from views.inventario.analisis_diferencias import (
    render_analisis_diferencias,
)
from views.inventario.dashboard_ciclicos import (
    render_dashboard_ciclicos,
)
from views.inventario.diagnostico import render_diagnostico
from views.inventario.ejecucion import (
    render_ejecucion,
)
from views.inventario.historial import (
    render_historial,
)
from views.inventario.planificador import (
    render_planificador,
)
from views.inventario.reconteos import (
    render_reconteos,
)


def render_ciclicos(
    *,
    datos: dict[str, pd.DataFrame],
    nombres: dict[str, str],
) -> None:
    st.subheader("📋 Inventarios cíclicos")
    st.caption(
        "Planificación, conteo ciego, reconteo "
        "y trazabilidad completa."
    )

    try:
        inicializar_hojas_inventario()
    except Exception as error:
        mensaje = str(error)

        if "429" in mensaje or "RATE_LIMIT_EXCEEDED" in mensaje:
            st.warning(
                "Google Sheets alcanzó temporalmente el límite "
                "de lecturas. Esperá alrededor de un minuto y "
                "volvé a abrir la pestaña; la nueva versión evita "
                "repetir estas consultas en cada rerun."
            )
        else:
            st.error(
                "No se pudo inicializar la estructura "
                "de Google Sheets."
            )
            st.exception(error)
        return

    vista = st.segmented_control(
        "Gestión de cíclicos",
        options=[
            "📊 Dashboard",
            "📅 Planificador",
            "📲 Ejecutar conteo",
            "🔍 Análisis",
            "🧠 Diagnóstico y acciones",
            "🔁 Reconteos",
            "📚 Historial",
        ],
        default="📊 Dashboard",
        label_visibility="collapsed",
        key="vista_ciclicos_inventario",
    )

    if vista == "📊 Dashboard":
        render_dashboard_ciclicos()

    elif vista == "📅 Planificador":
        requeridas = [
            "erp",
            "wms_stock_digip",
            "wms_disponible",
        ]

        faltantes = [
            clave
            for clave in requeridas
            if datos.get(
                clave,
                pd.DataFrame(),
            ).empty
        ]

        if faltantes:
            st.error(
                "Faltan fuentes para construir "
                "el planificador: "
                + ", ".join(faltantes)
            )
            return

        with st.spinner(
            "Construyendo candidatos..."
        ):
            tabla, detalle = (
                construir_base_ciclicos(
                    datos["erp"],
                    datos.get(
                        "erp_sanitarios",
                        pd.DataFrame(),
                    ),
                    datos["wms_stock_digip"],
                    datos.get("wms_recepcion", pd.DataFrame()),
                    datos.get(
                        "wms_detalle_auxiliar",
                        pd.DataFrame(),
                    ),
                    datos["wms_disponible"],
                    datos.get(
                        "articulos",
                        pd.DataFrame(),
                    ),
                )
            )

        render_planificador(
            tabla,
            detalle,
            datos.get("ubicaciones", pd.DataFrame()),
        )

    elif vista == "📲 Ejecutar conteo":
        render_ejecucion()

    elif vista == "🔍 Análisis":
        render_analisis_diferencias()

    elif vista == "🧠 Diagnóstico y acciones":
        with st.spinner("Construyendo diagnóstico..."):
            tabla, detalle = construir_base_ciclicos(
                datos["erp"], datos.get("erp_sanitarios", pd.DataFrame()),
                datos["wms_stock_digip"], datos.get("wms_recepcion", pd.DataFrame()),
                datos.get("wms_detalle_auxiliar", pd.DataFrame()),
                datos["wms_disponible"], datos.get("articulos", pd.DataFrame()),
            )
        render_diagnostico(tabla, detalle, datos.get("ubicaciones", pd.DataFrame()))

    elif vista == "🔁 Reconteos":
        render_reconteos()

    else:
        render_historial()
