from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    CARPETA_MAESTROS,
    ES_STREAMLIT_CLOUD,
)
from models.maestros.resumen import (
    diagnosticar_maestro_clientes,
)
from models.sincronizar_clientes import (
    actualizar_maestro_clientes,
    validar_maestro_clientes,
)
from utils.maestros.carga import (
    cargar_crudos_clientes,
    limpiar_cache_maestros,
)
from utils.maestros.descargas import (
    dataframe_a_csv,
)


def _limpiar_estado_clientes() -> None:
    for clave in (
        "validacion_clientes_resultado",
        "clientes_seleccionados_actualizacion",
        "confirmar_actualizacion_maestro_clientes",
    ):
        st.session_state.pop(
            clave,
            None,
        )


def render_clientes() -> None:
    st.subheader(
        "👥 Actualización del Maestro Clientes"
    )
    st.caption(
        "Detecta códigos logísticos nuevos, propone "
        "su planificación y permite incorporarlos "
        "al archivo XLSM con respaldo previo."
    )

    mensaje = st.session_state.pop(
        "mensaje_actualizacion_clientes",
        None,
    )

    if mensaje:
        st.success(mensaje)

    with st.spinner(
        "Cargando fuentes necesarias..."
    ):
        datos = cargar_crudos_clientes()

    tabla_clientes = datos["clientes"]
    tabla_pendientes = datos["pendientes_erp"]
    pedidos_digip = datos["pedidos"]

    diagnostico = diagnosticar_maestro_clientes(
        tabla_clientes
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Clientes registrados",
        diagnostico["registros"],
    )
    k2.metric(
        "Duplicados",
        diagnostico["duplicados"],
    )
    k3.metric(
        "Sin entrega",
        diagnostico["sin_entrega"],
    )
    k4.metric(
        "Sin preparación",
        diagnostico["sin_preparacion"],
    )

    fuentes_vacias = [
        nombre
        for nombre, dataframe in {
            "Maestro Clientes": tabla_clientes,
            "Pedidos Pendientes ERP": tabla_pendientes,
            "Pedidos DIGIP": pedidos_digip,
        }.items()
        if dataframe is None or dataframe.empty
    ]

    if fuentes_vacias:
        st.error(
            "No se puede ejecutar la validación. "
            "Faltan datos en: "
            + ", ".join(fuentes_vacias)
        )
        return

    col_validar, col_limpiar = st.columns(
        [3, 1]
    )

    with col_validar:
        validar = st.button(
            "🔍 Validar nuevos clientes",
            type="primary",
            width="stretch",
            key="validar_actualizacion_clientes",
        )

    with col_limpiar:
        if st.button(
            "🧹 Limpiar",
            width="stretch",
            key="limpiar_validacion_clientes",
        ):
            _limpiar_estado_clientes()
            st.rerun()

    if validar:
        with st.spinner(
            "Analizando códigos y planificación..."
        ):
            try:
                resultado = validar_maestro_clientes(
                    tabla_clientes=tabla_clientes,
                    tabla_pendientes=tabla_pendientes,
                    df_pedidos_digip=pedidos_digip,
                )
                st.session_state[
                    "validacion_clientes_resultado"
                ] = resultado
            except Exception as error:
                st.session_state[
                    "validacion_clientes_resultado"
                ] = None
                st.exception(error)

    resultado = st.session_state.get(
        "validacion_clientes_resultado"
    )

    if not isinstance(
        resultado,
        pd.DataFrame,
    ):
        st.info(
            "Ejecutá la validación para buscar "
            "códigos logísticos nuevos."
        )
        return

    if resultado.empty:
        st.success(
            "El Maestro Clientes está actualizado."
        )
        return

    cantidad_total = len(resultado)
    cantidad_listos = int(
        resultado["ListoParaAlta"]
        .fillna(False)
        .sum()
    )
    cantidad_revision = (
        cantidad_total - cantidad_listos
    )
    sin_despacho = int(
        resultado["Estado"]
        .eq("SIN_CODIGO_DESPACHO")
        .sum()
    )

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Clientes nuevos", cantidad_total)
    r2.metric("Listos para alta", cantidad_listos)
    r3.metric("Requieren revisión", cantidad_revision)
    r4.metric("Sin código despacho", sin_despacho)

    columnas_vista = [
        "Estado",
        "ListoParaAlta",
        "CodigoLogistico",
        "CodigoCliente",
        "Cliente",
        "Distribuidor",
        "PedidoReferencia",
        "CodigoDespacho",
        "Zona",
        "EntregaPropuesta",
        "PreparacionPropuesta",
        "MetodoInferencia",
        "ConfianzaPorcentaje",
        "ObservacionValidacion",
    ]

    columnas_vista = [
        columna
        for columna in columnas_vista
        if columna in resultado.columns
    ]

    st.dataframe(
        resultado[columnas_vista],
        hide_index=True,
        width="stretch",
        height=450,
        column_config={
            "ListoParaAlta": (
                st.column_config.CheckboxColumn(
                    "Listo",
                    disabled=True,
                )
            ),
            "ConfianzaPorcentaje": (
                st.column_config.ProgressColumn(
                    "Confianza",
                    min_value=0,
                    max_value=100,
                    format="%.1f %%",
                )
            ),
        },
    )

    st.download_button(
        "⬇️ Descargar validación",
        data=dataframe_a_csv(resultado),
        file_name=(
            "Validacion_Nuevos_Clientes.csv"
        ),
        mime="text/csv",
        width="stretch",
    )

    listos = resultado.loc[
        resultado["ListoParaAlta"]
        .fillna(False)
    ].copy()

    if listos.empty:
        st.warning(
            "No hay registros habilitados para alta."
        )
        return

    opciones = listos[
        "CodigoLogistico"
    ].astype(str).tolist()

    descripcion = {
        str(fila["CodigoLogistico"]): (
            f"{fila['CodigoLogistico']} — "
            f"{fila['Cliente']} — "
            f"Entrega {fila['EntregaPropuesta']} / "
            f"Preparación {fila['PreparacionPropuesta']}"
        )
        for _, fila in listos.iterrows()
    }

    seleccionados = st.multiselect(
        "Clientes a incorporar",
        options=opciones,
        default=opciones,
        format_func=lambda codigo: (
            descripcion.get(codigo, codigo)
        ),
        key=(
            "clientes_seleccionados_actualizacion"
        ),
    )

    registros = listos.loc[
        listos["CodigoLogistico"]
        .astype(str)
        .isin(seleccionados)
    ].copy()

    st.caption(
        f"Se actualizarán {len(registros)} "
        f"de {len(listos)} registros listos."
    )

    confirmar = st.checkbox(
        "Confirmo que revisé la planificación "
        "de los clientes seleccionados.",
        key=(
            "confirmar_actualizacion_maestro_clientes"
        ),
    )

    if ES_STREAMLIT_CLOUD:
        st.warning(
            "La validación funciona en la nube, "
            "pero la escritura del XLSM requiere "
            "Windows + Excel de escritorio. "
            "Ejecutá esta acción desde la app local."
        )

    actualizar = st.button(
        "💾 Actualizar Maestro Clientes",
        type="primary",
        width="stretch",
        disabled=(
            registros.empty
            or not confirmar
            or ES_STREAMLIT_CLOUD
        ),
    )

    if actualizar:
        with st.spinner(
            "Creando respaldo y actualizando XLSM..."
        ):
            try:
                resumen = actualizar_maestro_clientes(
                    registros_seleccionados=registros,
                    carpeta_datos=CARPETA_MAESTROS,
                    nombre_base="Maestro Clientes",
                )

                limpiar_cache_maestros(
                    "clientes"
                )
                _limpiar_estado_clientes()

                mensaje = (
                    "Maestro Clientes actualizado: "
                    f"{resumen['cantidad_agregados']} "
                    "registro(s) agregado(s)."
                )

                if resumen[
                    "cantidad_omitidos"
                ]:
                    mensaje += (
                        f" {resumen['cantidad_omitidos']} "
                        "registro(s) ya existían."
                    )

                if resumen.get("respaldo"):
                    mensaje += (
                        " Se creó un respaldo previo."
                    )

                st.session_state[
                    "mensaje_actualizacion_clientes"
                ] = mensaje
                st.rerun()

            except Exception as error:
                st.exception(error)
