from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.inventario.carga import (
    cargar_fuentes_inventario,
    limpiar_cache_inventario,
)
from utils.inventario.estilo import (
    aplicar_estilo_inventario,
)
from utils.inventario.snapshot import (
    corte_inventario_activo,
    guardar_snapshot_fuentes,
    limpiar_snapshot_inventario,
    obtener_snapshot_fuentes,
)
from utils.inventario.ciclicos_datos import (
    limpiar_cache_ciclicos,
)
from views.inventario.conciliacion import (
    render_conciliacion,
)
from views.inventario.ciclicos import (
    render_ciclicos,
)


def render_inventario() -> None:
    aplicar_estilo_inventario()

    st.title("🧮 Inventario")

    st.caption(
        "Conciliación ERP vs WMS y base para "
        "la administración de inventarios cíclicos."
    )

    (
        datos_snapshot,
        nombres,
        errores,
        fecha_snapshot,
    ) = obtener_snapshot_fuentes()

    # Si todavía no existe un corte, se genera uno inicial.
    # A partir de ese momento queda congelado hasta que el usuario
    # solicite explícitamente un nuevo corte.
    if datos_snapshot is None:
        with st.spinner(
            "Generando corte inicial de Inventario..."
        ):
            datos, nombres, errores = (
                cargar_fuentes_inventario()
            )

        guardar_snapshot_fuentes(
            datos,
            nombres,
            errores,
        )

        (
            datos_snapshot,
            nombres,
            errores,
            fecha_snapshot,
        ) = obtener_snapshot_fuentes()

    corte_activo = corte_inventario_activo()

    barra_1, barra_2 = st.columns(
        [4.4, 1.6],
        vertical_alignment="center",
    )

    with barra_1:
        if corte_activo:
            st.success(
                "🧊 Corte de inventario activo · "
                f"{fecha_snapshot}. "
                "ERP y WMS permanecen congelados hasta generar un nuevo corte."
            )
        else:
            st.warning(
                "No hay un corte de inventario activo."
            )

    with barra_2:
        if st.button(
            "🔄 Generar nuevo corte",
            key="generar_nuevo_corte_inventario",
            type="primary",
            width="stretch",
            help=(
                "Vuelve a leer simultáneamente ERP, WMS y maestros, "
                "incluido Stock Preparación, y reemplaza el corte actual."
            ),
        ):
            limpiar_cache_inventario()
            limpiar_snapshot_inventario()
            limpiar_cache_ciclicos()

            with st.spinner(
                "Generando nuevo corte ERP + WMS..."
            ):
                datos_nuevos, nombres_nuevos, errores_nuevos = (
                    cargar_fuentes_inventario()
                )

            guardar_snapshot_fuentes(
                datos_nuevos,
                nombres_nuevos,
                errores_nuevos,
            )
            st.rerun()

    vista = st.segmented_control(
        "Vista",
        options=[
            "🔍 Conciliación ERP vs WMS",
            "📍 Detalle por ubicaciones",
            "📋 Inventarios cíclicos",
        ],
        default="🔍 Conciliación ERP vs WMS",
        label_visibility="collapsed",
    )

    datos = datos_snapshot or {}

    if errores:
        with st.expander(
            "⚠️ Inconvenientes de carga",
            expanded=True,
        ):
            for error in errores:
                st.warning(error)

    if vista in {
        "🔍 Conciliación ERP vs WMS",
        "📍 Detalle por ubicaciones",
    }:
        render_conciliacion(
            datos,
            nombres,
            vista=vista,
        )

    else:
        render_ciclicos(
            datos=datos,
            nombres=nombres,
        )
