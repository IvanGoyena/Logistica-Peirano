from __future__ import annotations

import pandas as pd
import streamlit as st

from models.inventario.conteos import (
    consolidar_resultado_articulos,
)
from utils.inventario.importacion_conteos import (
    calcular_hash_archivo,
    leer_archivo_conteo,
    normalizar_archivo_conteo,
    validar_contra_plan,
)
from utils.inventario.persistencia import (
    actualizar_estado_plan,
    archivo_ya_importado,
    guardar_conteo,
    guardar_importacion_conteos,
    iniciar_plan,
    leer_conteos,
    leer_items,
    leer_planes,
)


def _seleccionar_plan() -> tuple[
    str | None,
    pd.DataFrame,
]:
    planes = leer_planes()

    if planes.empty:
        st.info(
            "Todavía no existen planes guardados."
        )
        return None, pd.DataFrame()

    disponibles = planes.loc[
        planes["Estado"].isin(
            [
                "Planificado",
                "En conteo",
            ]
        )
    ].copy()

    if disponibles.empty:
        st.info(
            "No hay planes disponibles para ejecutar."
        )
        return None, pd.DataFrame()

    inventario_id = st.selectbox(
        "Plan",
        options=disponibles[
            "InventarioID"
        ].astype(str).tolist(),
        format_func=lambda valor: (
            f"{valor} · "
            f"{disponibles.loc[
                disponibles['InventarioID']
                .astype(str).eq(valor),
                'ResponsableNombre'
            ].iloc[0]}"
        ),
    )

    return inventario_id, disponibles


def _estado_plan_post_conteo(
    inventario_id: str,
    items_plan: pd.DataFrame,
    conteos_plan: pd.DataFrame,
) -> None:
    ids_contados = set(
        conteos_plan[
            "ItemID"
        ].astype(str)
    )

    pendientes = items_plan.loc[
        ~items_plan[
            "ItemID"
        ].astype(str).isin(ids_contados)
    ]

    total = len(items_plan)
    completados = total - len(pendientes)

    st.progress(
        completados / total
        if total
        else 0,
        text=(
            f"{completados} de {total} "
            "ubicaciones cargadas"
        ),
    )

    if not pendientes.empty:
        return

    resumen = consolidar_resultado_articulos(
        items_plan,
        conteos_plan,
    )

    requiere_reconteo = bool(
        resumen[
            "EstadoResultado"
        ].eq("Requiere reconteo").any()
    )

    estado = (
        "Requiere reconteo"
        if requiere_reconteo
        else "Cerrado"
    )

    actualizar_estado_plan(
        inventario_id,
        estado,
        finalizar=not requiere_reconteo,
    )

    st.success(
        "El conteo inicial está completo."
    )
    st.dataframe(
        resumen,
        hide_index=True,
        width="stretch",
    )


def _render_importacion(
    inventario_id: str,
    items_plan: pd.DataFrame,
    conteos_plan: pd.DataFrame,
) -> None:
    st.markdown("### 📤 Importar conteo DIGIP")
    st.caption(
        "Cargá el Excel generado por el módulo "
        "de inventarios del WMS."
    )

    archivo = st.file_uploader(
        "Archivo de conteo",
        type=["xlsx", "xls"],
        key=f"archivo_conteo_{inventario_id}",
    )

    if archivo is None:
        st.info(
            "El archivo se validará antes de guardar "
            "cualquier registro."
        )
        return

    contenido = archivo.getvalue()
    hash_archivo = calcular_hash_archivo(
        contenido
    )

    if archivo_ya_importado(
        inventario_id=inventario_id,
        hash_archivo=hash_archivo,
    ):
        st.error(
            "Este mismo archivo ya fue importado "
            "para el plan seleccionado."
        )
        return

    try:
        crudo = leer_archivo_conteo(
            contenido
        )
        normalizado = (
            normalizar_archivo_conteo(
                crudo
            )
        )
    except Exception as error:
        st.exception(error)
        return

    claves_guardadas = set(
        conteos_plan.get(
            "ClaveImportacion",
            pd.Series(dtype=str),
        )
        .fillna("")
        .astype(str)
        .loc[lambda serie: serie.ne("")]
    )

    validacion, resumen = validar_contra_plan(
        normalizado,
        items_plan,
        claves_ya_guardadas=claves_guardadas,
    )

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Registros",
        resumen.registros_originales,
    )
    k2.metric(
        "Válidos",
        resumen.registros_validos,
    )
    k3.metric(
        "Duplicados",
        resumen.duplicados_archivo,
    )
    k4.metric(
        "Fuera del plan",
        resumen.fuera_del_plan,
    )
    k5.metric(
        "Ambiguos / errores",
        resumen.ambiguos + resumen.errores,
    )

    estados = (
        validacion[
            "EstadoValidacion"
        ]
        .value_counts()
        .rename_axis("Estado")
        .reset_index(name="Registros")
    )

    st.dataframe(
        estados,
        hide_index=True,
        width="stretch",
    )

    columnas_vista = [
        "FilaArchivo",
        "ArticuloCodigo",
        "Ubicacion",
        "CantidadFotoUnidades",
        "CantidadRelevadaUnidades",
        "DiferenciaArchivo",
        "UsuarioRelevamiento",
        "FechaRelevamiento",
        "FotoPertenece",
        "EstadoValidacion",
        "ItemID",
    ]

    st.dataframe(
        validacion[
            [
                columna
                for columna in columnas_vista
                if columna in validacion.columns
            ]
        ],
        hide_index=True,
        width="stretch",
        height=460,
    )

    validos = validacion.loc[
        validacion[
            "EstadoValidacion"
        ].eq("Válido")
    ]

    confirmar = st.checkbox(
        (
            f"Confirmo la importación de "
            f"{len(validos)} registros válidos."
        ),
        key=f"confirmar_import_{inventario_id}",
    )

    if st.button(
        "✅ Confirmar importación",
        type="primary",
        width="stretch",
        disabled=(
            validos.empty
            or not confirmar
        ),
        key=f"guardar_import_{inventario_id}",
    ):
        with st.spinner(
            "Guardando conteos..."
        ):
            importacion_id = (
                guardar_importacion_conteos(
                    inventario_id=inventario_id,
                    nombre_archivo=archivo.name,
                    hash_archivo=hash_archivo,
                    validacion=validacion,
                    resumen=resumen,
                )
            )

        st.success(
            f"Importación {importacion_id} guardada."
        )
        st.rerun()


def _render_manual(
    inventario_id: str,
    items_plan: pd.DataFrame,
    conteos_plan: pd.DataFrame,
) -> None:
    ids_contados = set(
        conteos_plan[
            "ItemID"
        ].astype(str).tolist()
    )

    pendientes = items_plan.loc[
        ~items_plan[
            "ItemID"
        ].astype(str).isin(ids_contados)
    ].copy()

    if pendientes.empty:
        st.success(
            "No quedan ubicaciones pendientes."
        )
        return

    pendientes["OrdenConteo"] = pd.to_numeric(
        pendientes["OrdenConteo"],
        errors="coerce",
    ).fillna(999999)

    actual = pendientes.sort_values(
        "OrdenConteo"
    ).iloc[0]

    st.warning(
        "Usá esta opción únicamente para excepciones "
        "o ubicaciones que no estén en el archivo."
    )

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
        "Cantidad contada",
        min_value=0.0,
        step=1.0,
        key=f"cantidad_{actual['ItemID']}",
    )

    observacion = st.text_area(
        "Observación",
        key=f"obs_{actual['ItemID']}",
    )

    confirmar = st.checkbox(
        "Confirmo el conteo de esta ubicación.",
        key=f"confirmar_{actual['ItemID']}",
    )

    if st.button(
        "✅ Guardar carga manual",
        type="primary",
        width="stretch",
        disabled=not confirmar,
    ):
        guardar_conteo(
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


def render_ejecucion() -> None:
    st.subheader("📲 Ejecutar inventario")
    st.caption(
        "Flujo principal: importar el archivo "
        "generado por DIGIP."
    )

    inventario_id, planes = (
        _seleccionar_plan()
    )

    if inventario_id is None:
        return

    plan = planes.loc[
        planes[
            "InventarioID"
        ].astype(str).eq(inventario_id)
    ].iloc[0]

    if str(plan["Estado"]) == "Planificado":
        if st.button(
            "▶️ Iniciar inventario",
            type="primary",
            width="stretch",
        ):
            iniciar_plan(inventario_id)
            st.rerun()

        st.info(
            "Iniciá el plan para habilitar "
            "la importación del conteo."
        )
        return

    items = leer_items()
    conteos = leer_conteos()

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

    _estado_plan_post_conteo(
        inventario_id,
        items_plan,
        conteos_plan,
    )

    modo = st.segmented_control(
        "Modo de carga",
        options=[
            "📤 Importar archivo DIGIP",
            "✍️ Carga manual",
        ],
        default="📤 Importar archivo DIGIP",
        label_visibility="collapsed",
        key=f"modo_ejecucion_{inventario_id}",
    )

    if modo == "📤 Importar archivo DIGIP":
        _render_importacion(
            inventario_id,
            items_plan,
            conteos_plan,
        )
    else:
        _render_manual(
            inventario_id,
            items_plan,
            conteos_plan,
        )
