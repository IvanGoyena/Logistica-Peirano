from __future__ import annotations

import streamlit as st

from models.maestros.catalogo import (
    FUENTES_MAESTROS,
    GRUPOS_FUENTES,
)
from models.maestros.resumen import (
    calcular_resumen_fuentes,
)
from utils.maestros.carga import (
    cargar_fuente_maestros,
    limpiar_cache_maestros,
)
from views.maestros.componentes import (
    mostrar_tarjeta_fuente,
)


def render_fuentes() -> None:
    cabecera, accion = st.columns(
        [5, 1],
        vertical_alignment="center",
    )

    with cabecera:
        st.subheader(
            "📂 Estado y descarga de fuentes"
        )
        st.caption(
            "Cada grupo se carga únicamente cuando "
            "se abre su pestaña."
        )

    with accion:
        if st.button(
            "🔄 Actualizar",
            key="actualizar_fuentes_maestros",
            width="stretch",
        ):
            limpiar_cache_maestros()
            st.rerun()

    grupo = st.segmented_control(
        "Grupo",
        options=list(GRUPOS_FUENTES),
        default="Dinámicas",
        label_visibility="collapsed",
        key="grupo_fuentes_maestros",
    )

    fuentes = [
        fuente
        for fuente in FUENTES_MAESTROS
        if fuente.grupo == grupo
    ]

    with st.spinner(
        f"Cargando fuentes de {grupo.lower()}..."
    ):
        resultados = [
            cargar_fuente_maestros(
                fuente.clave
            )
            for fuente in fuentes
        ]

    resumen = calcular_resumen_fuentes(
        resultados
    )

    k1, k2, k3 = st.columns(3)
    k1.metric(
        "Fuentes disponibles",
        f"{resumen['disponibles']}/{resumen['total']}",
    )
    k2.metric(
        "Registros",
        f"{resumen['registros']:,}".replace(",", "."),
    )
    k3.metric(
        "Con errores",
        resumen["con_error"],
    )

    columnas = st.columns(
        min(3, max(1, len(fuentes)))
    )

    for indice, (fuente, resultado) in enumerate(
        zip(fuentes, resultados)
    ):
        with columnas[indice % len(columnas)]:
            mostrar_tarjeta_fuente(
                fuente,
                resultado,
            )
