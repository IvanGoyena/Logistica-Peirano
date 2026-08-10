from __future__ import annotations

import pandas as pd
import streamlit as st

from models.inventario.conteos import (
    consolidar_resultado_articulos,
)
from utils.inventario.persistencia import (
    actualizar_estado_plan,
    guardar_reconteo,
    leer_conteos,
    leer_items,
    leer_planes,
    leer_reconteos,
)


def render_reconteos() -> None:
    st.subheader("🔁 Reconteos")
    st.caption(
        "El segundo conteo también es ciego."
    )

    planes = leer_planes()

    if planes.empty:
        st.info("No hay planes.")
        return

    planes = planes.loc[
        planes["Estado"].eq(
            "Requiere reconteo"
        )
    ].copy()

    if planes.empty:
        st.success(
            "No existen planes pendientes de reconteo."
        )
        return

    inventario_id = st.selectbox(
        "Plan para recontar",
        planes[
            "InventarioID"
        ].astype(str).tolist(),
    )

    items = leer_items()
    conteos = leer_conteos()
    reconteos = leer_reconteos()

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

    resumen = consolidar_resultado_articulos(
        items_plan,
        conteos_plan,
        reconteos_plan,
    )

    articulos_diferencia = set(
        resumen.loc[
            resumen[
                "EstadoResultado"
            ].eq("Requiere reconteo"),
            "ArticuloCodigo",
        ].astype(str)
    )

    items_reconteo = items_plan.loc[
        items_plan[
            "ArticuloCodigo"
        ].astype(str).isin(
            articulos_diferencia
        )
    ].copy()

    ids_recontados = set(
        reconteos_plan[
            "ItemID"
        ].astype(str).tolist()
    )

    pendientes = items_reconteo.loc[
        ~items_reconteo[
            "ItemID"
        ].astype(str).isin(
            ids_recontados
        )
    ].copy()

    if pendientes.empty:
        resultado_final = (
            consolidar_resultado_articulos(
                items_plan,
                conteos_plan,
                reconteos_plan,
            )
        )

        aun_diferencias = bool(
            (
                resultado_final["DiferenciaVsERP"]
                .ne(0)
                | resultado_final[
                    "DiferenciaVsWMS"
                ].ne(0)
            ).any()
        )

        estado = (
            "Pendiente de análisis"
            if aun_diferencias
            else "Cerrado"
        )

        actualizar_estado_plan(
            inventario_id,
            estado,
            finalizar=True,
        )

        st.success(
            f"Reconteo completado. Estado: {estado}."
        )
        st.dataframe(
            resultado_final,
            hide_index=True,
            width="stretch",
        )
        return

    pendientes["OrdenConteo"] = pd.to_numeric(
        pendientes["OrdenConteo"],
        errors="coerce",
    ).fillna(999999)

    actual = pendientes.sort_values(
        "OrdenConteo"
    ).iloc[0]

    with st.container(border=True):
        st.markdown(
            f"### {actual['ArticuloCodigo']}"
        )
        st.write(
            actual["ArticuloDescripcion"]
        )
        c1, c2 = st.columns(2)
        c1.metric(
            "Ubicación",
            actual["Ubicacion"],
        )
        c2.metric(
            "Contenedor",
            actual["Contenedor"]
            or "Sin contenedor",
        )

    cantidad = st.number_input(
        "Cantidad recontada",
        min_value=0.0,
        step=1.0,
        key=f"reconteo_{actual['ItemID']}",
    )

    observacion = st.text_area(
        "Observación del reconteo",
        key=f"obs_reconteo_{actual['ItemID']}",
    )

    confirmar = st.checkbox(
        "Confirmo el reconteo de esta ubicación.",
        key=f"confirmar_reconteo_{actual['ItemID']}",
    )

    if st.button(
        "✅ Guardar reconteo",
        type="primary",
        width="stretch",
        disabled=not confirmar,
    ):
        guardar_reconteo(
            inventario_id=inventario_id,
            item_id=str(actual["ItemID"]),
            articulo_codigo=str(
                actual["ArticuloCodigo"]
            ),
            ubicacion=str(actual["Ubicacion"]),
            contenedor=str(
                actual["Contenedor"]
            ),
            cantidad=cantidad,
            observacion=observacion,
        )
        st.rerun()
