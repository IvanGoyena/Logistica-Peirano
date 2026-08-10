from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from models.inventario.planificacion import (
    construir_items_plan,
)
from utils.inventario.persistencia import (
    guardar_plan,
)
from utils.inventario.ubicaciones import enriquecer_detalle_ubicaciones


def _usuarios_disponibles() -> list[tuple[str, str]]:
    try:
        return [
            (
                str(usuario),
                str(datos["nombre"]),
            )
            for usuario, datos in (
                st.secrets["usuarios"].items()
            )
        ]
    except Exception:
        usuario = str(
            st.session_state.get(
                "usuario",
                "",
            )
        )
        nombre = str(
            st.session_state.get(
                "nombre_usuario",
                usuario,
            )
        )
        return [(usuario, nombre)]


def render_planificador(
    tabla: pd.DataFrame,
    detalle: pd.DataFrame,
    maestro_ubicaciones: pd.DataFrame | None = None,
) -> None:
    st.subheader("📅 Planificador de cíclicos")
    st.caption(
        "Seleccioná artículos y guardá un plan "
        "de conteo por ubicación."
    )

    detalle = enriquecer_detalle_ubicaciones(detalle, maestro_ubicaciones)

    tipo_preseleccionado = st.session_state.get(
        "inventario_tipo_sugerido",
        "Picking",
    )

    if tipo_preseleccionado not in {
        "Picking",
        "Almacén",
        "General",
        "Selectivo",
    }:
        tipo_preseleccionado = "Picking"

    tipo_conteo = st.segmented_control(
        "Tipo de conteo",
        options=[
            "Picking",
            "Almacén",
            "General",
            "Selectivo",
        ],
        default=tipo_preseleccionado,
        help=(
            "Picking es la primera instancia recomendada. "
            "Almacén se utiliza cuando Picking quedó validado."
        ),
    )

    tipos_selectivos = []
    if tipo_conteo == "Selectivo":
        tipos_selectivos = st.multiselect(
            "Tipos de ubicación incluidos",
            options=sorted(detalle["TipoUbicacion"].dropna().unique()),
            default=["Picking", "Almacén"],
        )

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        grupo = st.selectbox(
            "Grupo",
            [
                "Todos",
                "Producto terminado",
                "Insumos",
            ],
        )

    with f2:
        prioridades = st.multiselect(
            "Prioridad",
            options=sorted(
                tabla[
                    "PrioridadInventario"
                ].dropna().unique()
            ),
            default=[
                valor
                for valor in [
                    "Crítica",
                    "Alta",
                ]
                if valor in set(
                    tabla[
                        "PrioridadInventario"
                    ]
                )
            ],
        )

    with f3:
        familias = st.multiselect(
            "Familia",
            options=sorted(
                tabla[
                    "Familia2"
                ].dropna().unique()
            ),
        )

    with f4:
        solo_diferencias = st.toggle(
            "Solo diferencias",
            value=True,
        )

    candidatos = tabla.copy()

    if grupo != "Todos":
        candidatos = candidatos.loc[
            candidatos[
                "GrupoInventario"
            ].eq(grupo)
        ]

    if prioridades:
        candidatos = candidatos.loc[
            candidatos[
                "PrioridadInventario"
            ].isin(prioridades)
        ]

    if familias:
        candidatos = candidatos.loc[
            candidatos["Familia2"].isin(
                familias
            )
        ]

    if solo_diferencias:
        candidatos = candidatos.loc[
            candidatos[
                "EstadoConciliacion"
            ].ne("Conciliado")
        ]

    codigos_sugeridos = [
        str(codigo)
        for codigo in st.session_state.get(
            "inventario_codigos_sugeridos",
            [],
        )
    ]

    if codigos_sugeridos:
        candidatos_sugeridos = candidatos.loc[
            candidatos[
                "ArticuloCodigo"
            ].astype(str).isin(
                codigos_sugeridos
            )
        ].copy()

        if not candidatos_sugeridos.empty:
            restantes = candidatos.loc[
                ~candidatos[
                    "ArticuloCodigo"
                ].astype(str).isin(
                    codigos_sugeridos
                )
            ].copy()

            candidatos = pd.concat(
                [
                    candidatos_sugeridos,
                    restantes,
                ],
                ignore_index=True,
            )

            st.info(
                f"Se recibieron "
                f"{len(candidatos_sugeridos)} artículos "
                "desde el diagnóstico preventivo."
            )

    limite = st.slider(
        "Cantidad máxima sugerida de artículos",
        min_value=1,
        max_value=max(
            min(len(candidatos), 100),
            1,
        ),
        value=min(
            20,
            max(len(candidatos), 1),
        ),
    )

    candidatos = (
        candidatos
        .head(limite)
        .copy()
    )

    if candidatos.empty:
        st.warning(
            "No hay artículos con los filtros seleccionados."
        )
        return

    if codigos_sugeridos:
        seleccion_inicial = (
            candidatos[
                "ArticuloCodigo"
            ].astype(str).isin(
                codigos_sugeridos
            )
        )
    else:
        seleccion_inicial = pd.Series(
            True,
            index=candidatos.index,
        )

    candidatos.insert(
        0,
        "Seleccionar",
        seleccion_inicial,
    )

    columnas_editor = [
        "Seleccionar",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "GrupoInventario",
        "Familia2",
        "StockERP",
        "StockWMSResumen",
        "DiferenciaERPvsWMS",
        "CantidadUbicaciones",
        "PrioridadInventario",
        "ScorePrioridad",
        "MotivoPrioridad",
    ]

    editada = st.data_editor(
        candidatos[columnas_editor],
        hide_index=True,
        width="stretch",
        height=480,
        disabled=[
            columna
            for columna in columnas_editor
            if columna != "Seleccionar"
        ],
        column_config={
            "Seleccionar": (
                st.column_config.CheckboxColumn(
                    "Incluir",
                )
            ),
            "ScorePrioridad": (
                st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                )
            ),
        },
        key="editor_plan_inventario",
    )

    seleccionados = editada.loc[
        editada["Seleccionar"]
        .fillna(False)
    ].copy()

    codigos = seleccionados[
        "ArticuloCodigo"
    ].astype(str).tolist()

    articulos_seleccionados = tabla.loc[
        tabla[
            "ArticuloCodigo"
        ].astype(str).isin(codigos)
    ].copy()

    detalle_plan = detalle.copy()
    if tipo_conteo in {"Picking", "Almacén"}:
        detalle_plan = detalle_plan.loc[detalle_plan["TipoUbicacion"].eq(tipo_conteo)].copy()
    elif tipo_conteo == "Selectivo" and tipos_selectivos:
        detalle_plan = detalle_plan.loc[detalle_plan["TipoUbicacion"].isin(tipos_selectivos)].copy()

    items_plan = construir_items_plan(
        articulos_seleccionados,
        detalle_plan,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric(
        "Artículos",
        int(
            items_plan[
                "ArticuloCodigo"
            ].nunique()
        ),
    )
    m2.metric(
        "Ubicaciones",
        len(items_plan),
    )
    m3.metric(
        "Unidades teóricas",
        f"{items_plan['Cantidad'].sum():,.0f}"
        .replace(",", "."),
    )

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        fecha_planificada = st.date_input(
            "Fecha planificada",
            value=date.today(),
        )

    usuarios = _usuarios_disponibles()
    etiquetas = {
        usuario: nombre
        for usuario, nombre in usuarios
    }

    with c2:
        responsable = st.selectbox(
            "Responsable del conteo",
            options=[
                usuario
                for usuario, _ in usuarios
            ],
            format_func=lambda valor: (
                f"{etiquetas.get(valor, valor)} "
                f"({valor})"
            ),
        )

    with c3:
        tipo = st.selectbox(
            "Motivo del plan",
            ["Por diferencia", "Preventivo", "Por familia", "Auditoría"],
        )

    observaciones = st.text_area(
        "Observaciones del plan",
        placeholder=(
            "Indicaciones operativas, sector, turno, etc."
        ),
    )

    confirmar = st.checkbox(
        "Confirmo la creación del plan con "
        "los artículos seleccionados."
    )

    if st.button(
        "💾 Crear plan de inventario",
        type="primary",
        width="stretch",
        disabled=(
            items_plan.empty
            or not confirmar
        ),
    ):
        with st.spinner(
            "Guardando plan y ubicaciones..."
        ):
            inventario_id = guardar_plan(
                fecha_planificada=(
                    fecha_planificada.isoformat()
                ),
                tipo_inventario=f"{tipo_conteo} · {tipo}",
                grupo_inventario=grupo,
                responsable=responsable,
                responsable_nombre=(
                    etiquetas.get(
                        responsable,
                        responsable,
                    )
                ),
                observaciones=observaciones,
                items_plan=items_plan,
            )

        st.success(
            f"Plan {inventario_id} creado correctamente."
        )
        st.session_state[
            "inventario_plan_creado"
        ] = inventario_id
