from __future__ import annotations

import pandas as pd
import streamlit as st

from config import ES_STREAMLIT_CLOUD
from utils.publicador_fuentes import (
    nombre_filtro_preparacion_actual,
    publicar_grupo,
    publicar_wms_manual,
    resumir_publicacion,
)


def _mostrar_resultado(
    titulo: str,
    resultados: list[dict],
) -> None:
    resumen = resumir_publicacion(
        resultados
    )

    st.markdown(
        f"#### {titulo}"
    )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Actualizados",
        resumen["actualizados"],
    )

    c2.metric(
        "Sin cambios",
        resumen["sin_cambios"],
    )

    c3.metric(
        "Errores",
        resumen["errores"],
    )

    tabla = pd.DataFrame(
        resultados
    )

    if tabla.empty:
        return

    columnas = [
        "archivo",
        "estado",
        "detalle",
        "commit",
    ]

    columnas = [
        columna
        for columna in columnas
        if columna in tabla.columns
    ]

    st.dataframe(
        tabla[columnas],
        hide_index=True,
        width="stretch",
    )


def render_publicacion() -> None:
    st.subheader(
        "⬆️ Publicación manual de fuentes"
    )

    st.caption(
        "Publica en GitHub únicamente las "
        "fuentes locales que cambiaron. "
        "Los reportes ya automatizados "
        "continúan actualizándose por sus "
        "propios scripts."
    )

    if ES_STREAMLIT_CLOUD:
        st.warning(
            "Esta herramienta debe ejecutarse "
            "desde la app local, porque utiliza "
            "los archivos de Data_Maestros, "
            "Data_ERP y Data_WMS de tu PC."
        )

    col_maestros, col_erp, col_wms = (
        st.columns(3)
    )

    # =====================================================
    # MAESTROS
    # =====================================================

    with col_maestros:
        with st.container(border=True):
            st.markdown(
                "### 📚 Maestros"
            )

            st.caption(
                "Publica los 7 maestros "
                "administrados manualmente."
            )

            st.markdown(
                """
- Datos Expresos
- Maestro Articulo
- Maestro Clientes
- Maestro Ubicaciones
- Maestro Volumetria
- Max & Min
- Stock_Estandar
                """
            )

            publicar_maestros = st.button(
                "⬆️ Publicar Maestros",
                type="primary",
                width="stretch",
                disabled=ES_STREAMLIT_CLOUD,
                key=(
                    "publicar_fuentes_maestros"
                ),
            )

    # =====================================================
    # ERP
    # =====================================================

    with col_erp:
        with st.container(border=True):
            st.markdown(
                "### 🧾 ERP manual"
            )

            st.caption(
                "Publica solamente las "
                "fuentes ERP que no tienen "
                "automatización propia."
            )

            st.markdown(
                """
- Hojas de Ruta
- info stock total
- Informe Stock Sanitarios
- Pendientes OC
                """
            )

            publicar_erp = st.button(
                "⬆️ Publicar ERP",
                type="primary",
                width="stretch",
                disabled=ES_STREAMLIT_CLOUD,
                key=(
                    "publicar_fuentes_erp"
                ),
            )

    # =====================================================
    # WMS MANUAL
    # =====================================================

    with col_wms:
        with st.container(border=True):
            st.markdown(
                "### 📦 WMS manual"
            )

            archivo_mes = (
                nombre_filtro_preparacion_actual()
            )

            st.caption(
                "Publica únicamente el "
                "Filtrar Preparación del "
                "mes actual."
            )

            st.info(
                archivo_mes
            )

            publicar_wms = st.button(
                "⬆️ Publicar WMS manual",
                type="primary",
                width="stretch",
                disabled=ES_STREAMLIT_CLOUD,
                key=(
                    "publicar_fuentes_wms_manual"
                ),
            )

    st.divider()

    # =====================================================
    # EJECUCIONES
    # =====================================================

    if publicar_maestros:
        with st.spinner(
            "Comparando y publicando Maestros..."
        ):
            resultados = publicar_grupo(
                "maestros"
            )

        st.session_state[
            "resultado_publicacion_maestros"
        ] = resultados

    if publicar_erp:
        with st.spinner(
            "Comparando y publicando ERP..."
        ):
            resultados = publicar_grupo(
                "erp"
            )

        st.session_state[
            "resultado_publicacion_erp"
        ] = resultados

    if publicar_wms:
        with st.spinner(
            "Publicando WMS manual..."
        ):
            resultados = (
                publicar_wms_manual()
            )

        st.session_state[
            "resultado_publicacion_wms"
        ] = resultados

    # =====================================================
    # RESULTADOS
    # =====================================================

    hubo_resultado = False

    resultados_maestros = (
        st.session_state.get(
            "resultado_publicacion_maestros"
        )
    )

    if resultados_maestros:
        hubo_resultado = True
        _mostrar_resultado(
            "Resultado Maestros",
            resultados_maestros,
        )

    resultados_erp = (
        st.session_state.get(
            "resultado_publicacion_erp"
        )
    )

    if resultados_erp:
        hubo_resultado = True
        _mostrar_resultado(
            "Resultado ERP",
            resultados_erp,
        )

    resultados_wms = (
        st.session_state.get(
            "resultado_publicacion_wms"
        )
    )

    if resultados_wms:
        hubo_resultado = True
        _mostrar_resultado(
            "Resultado WMS manual",
            resultados_wms,
        )

    if not hubo_resultado:
        st.info(
            "Elegí uno de los grupos para "
            "comparar los archivos locales "
            "contra GitHub y publicar "
            "solamente los cambios."
        )
