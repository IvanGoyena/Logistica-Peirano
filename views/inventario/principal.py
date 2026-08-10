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

    barra_1, barra_2 = st.columns(
        [5, 1],
        vertical_alignment="center",
    )

    with barra_1:
        st.caption(
            "Etapa 1 · Diagnóstico general, "
            "integridad del WMS y diferencias entre sistemas."
        )

    with barra_2:
        if st.button(
            "🔄 Actualizar datos",
            key="actualizar_inventario",
            width="stretch",
            help=(
                "Vuelve a leer ERP, WMS y maestros. "
                "Los filtros no actualizan las fuentes."
            ),
        ):
            limpiar_cache_inventario()
            limpiar_snapshot_inventario()
            limpiar_cache_ciclicos()
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

    (
        datos_snapshot,
        nombres,
        errores,
        fecha_snapshot,
    ) = obtener_snapshot_fuentes()

    if datos_snapshot is None:
        with st.spinner(
            "Actualizando fuentes de Inventario..."
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

    datos = datos_snapshot or {}

    if fecha_snapshot:
        st.caption(
            "🕒 Datos cargados: "
            f"{fecha_snapshot} · "
            "Los filtros trabajan sobre esta lectura."
        )

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
