from __future__ import annotations

import pandas as pd
import streamlit as st

from models.inventario.conteos import (
    consolidar_resultado_articulos,
)
from utils.exportaciones import (
    dataframe_a_csv_limpio,
)
from utils.inventario.persistencia import (
    leer_conteos,
    leer_historial,
    leer_importaciones,
    leer_items,
    leer_planes,
    leer_reconteos,
)


def render_historial() -> None:
    st.subheader("📚 Historial de inventarios")

    planes = leer_planes()

    if planes.empty:
        st.info(
            "Todavía no existen inventarios."
        )
        return

    estados = st.multiselect(
        "Estado",
        options=sorted(
            planes["Estado"]
            .dropna()
            .unique()
        ),
    )

    visual_planes = planes.copy()

    if estados:
        visual_planes = visual_planes.loc[
            visual_planes[
                "Estado"
            ].isin(estados)
        ]

    st.dataframe(
        visual_planes,
        hide_index=True,
        width="stretch",
        height=320,
    )

    inventario_id = st.selectbox(
        "Ver detalle del plan",
        options=visual_planes[
            "InventarioID"
        ].astype(str).tolist(),
    )

    items = leer_items()
    conteos = leer_conteos()
    reconteos = leer_reconteos()
    historial = leer_historial()
    importaciones = leer_importaciones()

    items_plan = items.loc[
        items[
            "InventarioID"
        ].astype(str).eq(inventario_id)
    ].copy()
    conteos_plan = conteos.loc[
        conteos[
            "InventarioID"
        ].astype(str).eq(inventario_id)
    ].copy()
    reconteos_plan = reconteos.loc[
        reconteos[
            "InventarioID"
        ].astype(str).eq(inventario_id)
    ].copy()
    historial_plan = historial.loc[
        historial[
            "InventarioID"
        ].astype(str).eq(inventario_id)
    ].copy()

    resumen = consolidar_resultado_articulos(
        items_plan,
        conteos_plan,
        reconteos_plan,
    )

    pestaña = st.segmented_control(
        "Detalle",
        [
            "Resumen",
            "Ubicaciones",
            "Importaciones",
            "Auditoría",
        ],
        default="Resumen",
        label_visibility="collapsed",
    )

    if pestaña == "Resumen":
        st.dataframe(
            resumen,
            hide_index=True,
            width="stretch",
        )
    elif pestaña == "Ubicaciones":
        detalle = items_plan.merge(
            conteos_plan[
                [
                    "ItemID",
                    "CantidadContada",
                    "UsuarioConteoNombre",
                    "FechaConteo",
                ]
            ],
            on="ItemID",
            how="left",
        )

        if not reconteos_plan.empty:
            detalle = detalle.merge(
                reconteos_plan[
                    [
                        "ItemID",
                        "CantidadRecontada",
                        "UsuarioReconteoNombre",
                        "FechaReconteo",
                    ]
                ],
                on="ItemID",
                how="left",
            )

        st.dataframe(
            detalle,
            hide_index=True,
            width="stretch",
            height=520,
        )
    elif pestaña == "Importaciones":
        importaciones_plan = (
            importaciones.loc[
                importaciones[
                    "InventarioID"
                ]
                .astype(str)
                .eq(inventario_id)
            ]
            .copy()
        )

        st.dataframe(
            importaciones_plan,
            hide_index=True,
            width="stretch",
            height=420,
        )
    else:
        st.dataframe(
            historial_plan,
            hide_index=True,
            width="stretch",
            height=420,
        )

    d1, d2 = st.columns(2)

    with d1:
        st.download_button(
            "⬇️ Descargar resumen",
            data=dataframe_a_csv_limpio(
                resumen
            ),
            file_name=(
                f"{inventario_id}_resumen.csv"
            ),
            mime="text/csv",
            width="stretch",
        )

    with d2:
        st.download_button(
            "⬇️ Descargar items",
            data=dataframe_a_csv_limpio(
                items_plan
            ),
            file_name=(
                f"{inventario_id}_items.csv"
            ),
            mime="text/csv",
            width="stretch",
        )
