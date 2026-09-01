from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from models.inventario.conciliacion import (
    COLUMNAS_ESTADO_WMS,
    ESTADOS_FISICOS_WMS,
    clasificar_grupo_inventario,
)
from models.inventario.indicadores import (
    calcular_kpis_inventario,
    resumen_por_categoria,
)
from utils.inventario.formatos import (
    decimal,
    entero,
)
from utils.inventario.exclusiones import (
    filtrar_articulos_fuera_inventario,
    tabla_articulos_fuera_inventario,
)

from utils.exportaciones import dataframe_a_csv_limpio

from utils.inventario.snapshot import (
    procesar_inventario_cacheado,
)


def _render_kpis(
    kpis: dict,
) -> None:
    tarjetas = [
        (
            "🎯 Exactitud por códigos",
            f"{kpis['exactitud_codigos']:.1f}%",
            (
                f"{entero(kpis['conciliados'])} "
                f"de {entero(kpis['codigos'])} códigos"
            ),
            (
                "inv-ok"
                if kpis["exactitud_codigos"] >= 95
                else "inv-warn"
            ),
        ),
        (
            "📦 Exactitud por unidades",
            f"{kpis['exactitud_unidades']:.1f}%",
            (
                f"{entero(kpis['diferencia_absoluta'])} "
                "unidades de diferencia absoluta"
            ),
            (
                "inv-ok"
                if kpis["exactitud_unidades"] >= 98
                else "inv-bad"
            ),
        ),
        (
            "⚖️ Diferencia neta",
            entero(kpis["diferencia_neta"]),
            (
                "Positivo: sobra en WMS · "
                "Negativo: sobra en ERP"
            ),
            "inv-info",
        ),
        (
            "🧩 Integridad del WMS",
            f"{kpis['integridad_wms']:.1f}%",
            (
                f"{entero(kpis['codigos_integridad_wms'])} "
                "códigos a revisar entre resumen y ubicaciones"
            ),
            (
                "inv-ok"
                if kpis["integridad_wms"] >= 98
                else "inv-warn"
            ),
        ),
    ]

    html = '<div class="inv-kpi-grid">'

    for titulo, valor, detalle, clase in tarjetas:
        html += (
            f'<div class="inv-kpi {clase}">'
            f'<div class="inv-label">{titulo}</div>'
            f'<div class="inv-value">{valor}</div>'
            f'<div class="inv-detail">{detalle}</div>'
            "</div>"
        )

    html += "</div>"

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def render_conciliacion(
    datos: dict[str, pd.DataFrame],
    nombres: dict[str, str],
    *,
    vista: str,
) -> None:
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
            "No se puede construir el módulo porque "
            "faltan una o más fuentes obligatorias."
        )

        st.write(
            {
                "Fuentes faltantes": faltantes,
                "Fuentes detectadas": nombres,
            }
        )

        return

    df_erp = datos["erp"]
    df_erp_sanitarios = datos.get(
        "erp_sanitarios",
        pd.DataFrame(),
    )
    df_wms_stock_digip = datos["wms_stock_digip"]
    df_wms_recepcion = datos.get(
        "wms_recepcion",
        pd.DataFrame(),
    )
    df_wms_preparacion = datos.get(
        "wms_preparacion",
        pd.DataFrame(),
    )
    df_wms_detalle_auxiliar = datos.get(
        "wms_detalle_auxiliar",
        pd.DataFrame(),
    )
    df_wms_disponible = datos["wms_disponible"]
    df_articulos = datos.get(
        "articulos",
        pd.DataFrame(),
    )

    if df_wms_recepcion.empty:
        st.info(
            "ℹ️ Recepción WMS sin stock activo: "
            "se considera 0 unidades en Recepción y "
            "la conciliación continúa normalmente."
        )
    df_ubicaciones = datos.get(
        "ubicaciones",
        pd.DataFrame(),
    )
    df_picking_config = datos.get(
        "picking_config",
        pd.DataFrame(),
    )

    with st.expander(
        "⚙️ Criterio de comparación",
        expanded=False,
    ):
        st.caption(
            "ERP configurable por suma de estados. "
            "Valor recomendado: est_1 + est_8. "
            "WMS comparable: Disponible + Bloqueados + Recepción + Preparación."
        )

        columnas_erp = [
            columna
            for columna in [
                "stk_fis",
                "stk_dis",
                "stk_com",
                "stk_res",
                "stk_pen",
                "est_1",
                "est_8",
            ]
            if columna in df_erp.columns
        ]

        config_erp_1, config_erp_2 = st.columns(2)

        with config_erp_1:
            columnas_stock_erp = st.multiselect(
                "Estados incluidos en ERP principal",
                options=columnas_erp,
                default=[
                    columna
                    for columna in [
                        "est_1",
                        "est_8",
                    ]
                    if columna in columnas_erp
                ],
                help=(
                    "El stock ERP principal será la suma "
                    "de las columnas seleccionadas."
                ),
            )

        tiene_sanitarios = (
            df_erp_sanitarios is not None
            and not df_erp_sanitarios.empty
        )

        with config_erp_2:
            incluir_erp_sanitarios = st.toggle(
                "Sumar Informe Stock Sanitarios",
                value=tiene_sanitarios,
                disabled=not tiene_sanitarios,
                key="inventario_incluir_erp_sanitarios",
                help=(
                    "Suma por código el stock del depósito virtual "
                    "de Sanitarios al stock físico del ERP."
                ),
            )

        columnas_erp_sanitarios = [
            columna
            for columna in [
                "stk_fis",
                "stk_dis",
                "stk_com",
                "stk_res",
                "stk_pen",
                "est_1",
                "est_8",
            ]
            if columna in df_erp_sanitarios.columns
        ]

        columnas_stock_erp_sanitarios = (
            st.multiselect(
                "Estados incluidos en Informe Sanitarios",
                options=columnas_erp_sanitarios,
                default=[
                    columna
                    for columna in [
                        "est_1",
                        "est_8",
                    ]
                    if columna
                    in columnas_erp_sanitarios
                ],
                disabled=not incluir_erp_sanitarios,
                help=(
                    "El stock de Sanitarios será la suma "
                    "de las columnas seleccionadas."
                ),
            )
            if columnas_erp_sanitarios
            else []
        )

        if not tiene_sanitarios:
            st.info(
                "No se encontró `Informe Stock Sanitarios`. "
                "La conciliación continuará solamente con "
                "`Info Stock Total`."
            )

        estados_wms = st.multiselect(
            "Estados físicos incluidos en el WMS",
            options=COLUMNAS_ESTADO_WMS,
            default=[
                estado
                for estado in ESTADOS_FISICOS_WMS
                if estado in df_wms_disponible.columns
            ],
            help=(
                "La comparación operativa utiliza únicamente "
                "Disponible, Bloqueados, Recepción y Preparación. "
                "El resto de los estados no participa por defecto."
            ),
        )

        tol_1, tol_2 = st.columns(2)

        with tol_1:
            tolerancia_unidades = st.number_input(
                "Tolerancia en unidades",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

        with tol_2:
            tolerancia_porcentaje = st.number_input(
                "Tolerancia porcentual",
                min_value=0.0,
                value=0.0,
                step=0.1,
            )

        st.caption(
            f"ERP base: {nombres.get('erp', '')} · "
            f"ERP Sanitarios: {nombres.get('erp_sanitarios', 'No detectado') or 'No detectado'} · "
            f"Detalle comparable: {nombres.get('wms_stock_digip', '')} · "
            f"Recepción: {nombres.get('wms_recepcion', '') or 'Sin stock'} · "
            f"Preparación: {nombres.get('wms_preparacion', '') or 'No detectado'} · "
            f"Resumen: {nombres.get('wms_disponible', '')}"
        )

    formula_erp_base = " + ".join(
        columnas_stock_erp
    )
    formula_erp_sanitarios = " + ".join(
        columnas_stock_erp_sanitarios
    )

    if incluir_erp_sanitarios:
        st.caption(
            "🧮 Stock ERP consolidado = "
            f"ERP Base ({formula_erp_base}) + "
            f"ERP Sanitarios ({formula_erp_sanitarios})."
        )
    else:
        st.caption(
            "🧮 Stock ERP consolidado = "
            f"ERP Base ({formula_erp_base})."
        )

    if not columnas_stock_erp:
        st.error(
            "Seleccioná al menos una columna "
            "para el ERP principal."
        )
        return

    if (
        incluir_erp_sanitarios
        and not columnas_stock_erp_sanitarios
    ):
        st.error(
            "Seleccioná al menos una columna "
            "del Informe Stock Sanitarios."
        )
        return

    try:
        with st.spinner(
            "Procesando conciliación y diagnóstico..."
        ):
            (
                tabla,
                detalle_ubicaciones,
                config,
            ) = procesar_inventario_cacheado(
                df_erp,
                df_erp_sanitarios,
                df_wms_stock_digip,
                df_wms_recepcion,
                df_wms_preparacion,
                df_wms_detalle_auxiliar,
                df_wms_disponible,
                df_articulos,
                df_ubicaciones,
                df_picking_config,
                columnas_stock_erp=tuple(
                    columnas_stock_erp
                ),
                incluir_erp_sanitarios=(
                    incluir_erp_sanitarios
                ),
                columnas_stock_erp_sanitarios=tuple(
                    columnas_stock_erp_sanitarios
                ),
                estados_wms=tuple(
                    estados_wms
                ),
                tolerancia_unidades=float(
                    tolerancia_unidades
                ),
                tolerancia_porcentaje=float(
                    tolerancia_porcentaje
                ),
            )

    except Exception as error:
        st.exception(error)
        return

    tabla_original = tabla.copy()
    detalle_original = detalle_ubicaciones.copy()
    tabla_exclusiones = tabla_articulos_fuera_inventario()

    st.markdown("### Filtros rápidos")

    control_1, control_2, control_3, control_4 = st.columns(
        [1.15, 1.75, 1.15, 1.35],
        vertical_alignment="center",
    )

    with control_1:
        ocultar_fuera_inventario = st.toggle(
            "Ocultar fuera del inventario",
            value=True,
            key="inventario_ocultar_no_aplica",
            help=(
                "Excluye los códigos no aplicables "
                "sin eliminarlos de las fuentes."
            ),
        )

    with control_2:
        grupo_inventario = st.segmented_control(
            "Grupo de inventario",
            options=[
                "📦 Producto terminado",
                "🔩 Insumos",
                "📊 Todos",
            ],
            default="📦 Producto terminado",
            key="inventario_grupo_analisis",
            label_visibility="collapsed",
        )

    with control_3:
        solo_diferencias_global = st.toggle(
            "Solo diferencias",
            value=False,
            key="inventario_solo_diferencias_global",
        )

    with control_4:
        solo_prioridad_global = st.toggle(
            "Solo Alta / Crítica",
            value=False,
            key="inventario_solo_prioridad_global",
        )

    tabla = filtrar_articulos_fuera_inventario(
        tabla,
        ocultar=ocultar_fuera_inventario,
    )
    detalle_ubicaciones = filtrar_articulos_fuera_inventario(
        detalle_ubicaciones,
        ocultar=ocultar_fuera_inventario,
    )

    if "GrupoInventario" not in tabla.columns:
        tabla["GrupoInventario"] = (
            tabla["ArticuloCodigo"]
            .map(clasificar_grupo_inventario)
        )

    if "GrupoInventario" not in detalle_ubicaciones.columns:
        detalle_ubicaciones["GrupoInventario"] = (
            detalle_ubicaciones["ArticuloCodigo"]
            .map(clasificar_grupo_inventario)
        )

    if grupo_inventario == "📦 Producto terminado":
        tabla = tabla.loc[
            tabla["GrupoInventario"].eq("Producto terminado")
        ].copy()
        detalle_ubicaciones = detalle_ubicaciones.loc[
            detalle_ubicaciones["GrupoInventario"].eq(
                "Producto terminado"
            )
        ].copy()

    elif grupo_inventario == "🔩 Insumos":
        tabla = tabla.loc[
            tabla["GrupoInventario"].eq("Insumos")
        ].copy()
        detalle_ubicaciones = detalle_ubicaciones.loc[
            detalle_ubicaciones["GrupoInventario"].eq(
                "Insumos"
            )
        ].copy()

    if solo_diferencias_global:
        tabla = tabla.loc[
            tabla["EstadoConciliacion"].ne("Conciliado")
        ].copy()

    if solo_prioridad_global:
        tabla = tabla.loc[
            tabla["PrioridadInventario"].isin(
                ["Alta", "Crítica"]
            )
        ].copy()

    grupos_originales = (
        tabla_original["ArticuloCodigo"]
        .map(clasificar_grupo_inventario)
    )

    codigos_producto_terminado = int(
        grupos_originales.eq("Producto terminado").sum()
    )
    codigos_insumos = int(
        grupos_originales.eq("Insumos").sum()
    )

    resumen_1, resumen_2, resumen_3 = st.columns(3)
    resumen_1.caption(
        f"📦 Producto terminado: {entero(codigos_producto_terminado)} códigos"
    )
    resumen_2.caption(
        f"🔩 Insumos: {entero(codigos_insumos)} códigos"
    )
    resumen_3.caption(
        f"👁️ Universo visible: {entero(len(tabla))} códigos"
    )

    if ocultar_fuera_inventario:
        tabla_sin_exclusiones = filtrar_articulos_fuera_inventario(
            tabla_original,
            ocultar=True,
        )
        cantidad_no_aplica = (
            len(tabla_original)
            - len(tabla_sin_exclusiones)
        )
        if cantidad_no_aplica:
            st.caption(
                f"🚫 {cantidad_no_aplica} códigos fuera del inventario "
                "fueron excluidos."
            )

    with st.expander(
        f"🚫 Artículos fuera del inventario ({len(tabla_exclusiones)})",
        expanded=False,
    ):
        st.caption(
            "Estos artículos se conservan para auditoría."
        )
        st.dataframe(
            tabla_exclusiones,
            width="stretch",
            hide_index=True,
            height=300,
        )
        st.download_button(
            "⬇️ Descargar artículos fuera del inventario",
            data=dataframe_a_csv_limpio(
                tabla_exclusiones
            ),
            file_name="articulos_fuera_del_inventario.csv",
            mime="text/csv",
            key="descargar_articulos_fuera_inventario",
        )

    if tabla.empty:
        st.warning(
            "No hay artículos para mostrar con la combinación "
            "actual de filtros."
        )
        return

    if vista == "📍 Detalle por ubicaciones":
        st.subheader(
            "📍 Detalle físico del WMS por ubicación"
        )

        st.caption(
            "Detalle comparable construido con Stock DIGIP + Stock Recepción + Stock Preparación."
        )

        f1, f2, f3, f4 = st.columns(4)

        with f1:
            articulos = st.multiselect(
                "Artículo",
                options=sorted(
                    detalle_ubicaciones[
                        "ArticuloCodigo"
                    ]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
            )

        with f2:
            areas = st.multiselect(
                "Área",
                options=sorted(
                    detalle_ubicaciones["Area"]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
            )

        with f3:
            fuentes = st.multiselect(
                "Fuente",
                options=sorted(
                    detalle_ubicaciones[
                        "FuenteDetalle"
                    ]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
            )

        with f4:
            tipos_ubicacion = st.multiselect(
                "Tipo de ubicación",
                options=sorted(
                    detalle_ubicaciones[
                        "TipoUbicacion"
                    ]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                ),
            )

        detalle_filtrado = (
            detalle_ubicaciones.copy()
        )

        if articulos:
            detalle_filtrado = (
                detalle_filtrado.loc[
                    detalle_filtrado[
                        "ArticuloCodigo"
                    ].isin(articulos)
                ]
            )

        if areas:
            detalle_filtrado = (
                detalle_filtrado.loc[
                    detalle_filtrado[
                        "Area"
                    ].isin(areas)
                ]
            )

        if fuentes:
            detalle_filtrado = (
                detalle_filtrado.loc[
                    detalle_filtrado[
                        "FuenteDetalle"
                    ].isin(fuentes)
                ]
            )

        if tipos_ubicacion:
            detalle_filtrado = (
                detalle_filtrado.loc[
                    detalle_filtrado[
                        "TipoUbicacion"
                    ].isin(tipos_ubicacion)
                ]
            )

        st.caption(
            f"{len(detalle_filtrado):,} registros · "
            f"{entero(detalle_filtrado['Cantidad'].sum())} unidades"
        )

        st.dataframe(
            detalle_filtrado,
            width="stretch",
            hide_index=True,
            height=680,
        )

        st.download_button(
            "⬇️ Descargar detalle de ubicaciones",
            data=dataframe_a_csv_limpio(
                detalle_filtrado
            ),
            file_name=(
                "inventario_detalle_ubicaciones_wms.csv"
            ),
            mime="text/csv",
            width="stretch",
        )

        return

    kpis = calcular_kpis_inventario(
        tabla
    )

    _render_kpis(kpis)

    st.info(
        """
        **Cómo se calcula la integridad del WMS**

        `StockWMSResumen` se compara contra
        `StockWMSDetalleComparable`, construido con
        **Stock DIGIP + Stock Recepción + Stock Preparación**.

        `StockWMSDetalleAuxiliar` proviene de `stock_detallado`
        y queda solamente para auditoría. No modifica KPIs,
        estados ni prioridades porque puede corresponder a otro
        momento o filtro de descarga.
        """
    )

    with st.expander(
        "🧩 Configuración aplicada",
        expanded=False,
    ):
        st.json(config)

    st.markdown(
        "### 🧠 Diagnóstico preventivo del inventario"
    )
    st.caption(
        "El análisis combina la diferencia ERP–WMS, "
        "la configuración de Picking y la distribución "
        "estadística de pallets y contenedores en Almacén. "
        "Picking bajo mínimo no se considera error; "
        "solo se alerta cuando supera el máximo."
    )

    diagnosticos_activos = tabla.loc[
        tabla["TipoConteoSugerido"].ne("Sin conteo")
    ].copy()

    diag_1, diag_2, diag_3, diag_4, diag_5 = st.columns(5)

    diag_1.metric(
        "Riesgo alto",
        entero(
            tabla[
                "ScoreRiesgoPreventivo"
            ].ge(70).sum()
        ),
    )
    diag_2.metric(
        "Picking excedido",
        entero(
            tabla[
                "PickingSobreMaximo"
            ].sum()
        ),
        "sobre máximo",
    )
    diag_3.metric(
        "Revisar Almacén",
        entero(
            tabla[
                "TipoConteoSugerido"
            ].eq("Almacén").sum()
        ),
    )
    diag_4.metric(
        "Sobre estándar",
        entero(
            tabla[
                "ContenedoresSobreEstandar"
            ].sum()
        ),
        "contenedores",
    )
    diag_5.metric(
        "Pallets parciales",
        entero(
            (
                tabla["PalletsParciales"]
                + tabla[
                    "ContenedoresResiduales"
                ]
            ).sum()
        ),
    )

    with st.expander(
        "📐 Cómo se infiere el pallet estándar",
        expanded=False,
    ):
        st.markdown(
            """
            - Se utilizan solamente ubicaciones clasificadas como **Almacén**.
            - No se usa el promedio.
            - Se busca la cantidad que concentra más contenedores dentro de una tolerancia de ±5 %.
            - Los pallets completos, parciales, residuales y sobre estándar se clasifican contra ese valor.
            - `ConfianzaEstandar` indica qué proporción de las líneas de Almacén respalda el estándar inferido.
            """
        )

    # Señales operativas independientes del diagnóstico textual.
    tabla["TieneAnomaliaAlmacen"] = (
        tabla["ContenedoresSobreEstandar"].gt(0)
        | tabla["PalletsParciales"].gt(0)
        | tabla["ContenedoresResiduales"].gt(0)
        | (
            tabla["ConfianzaEstandar"].gt(0)
            & tabla["ConfianzaEstandar"].lt(50)
        )
    )

    tabla["TieneAnomaliaPicking"] = (
        tabla["PickingSobreMaximo"]
    )

    tabla["TieneDiferenciaERPvsWMS"] = (
        tabla["DiferenciaAbsoluta"].gt(0)
    )

    tabla["SinPatronConcluyente"] = (
        tabla["OrigenProbableInicial"]
        .astype(str)
        .str.contains(
            "Sin patrón|Sin diagnostico|Sin diagnóstico",
            case=False,
            na=False,
            regex=True,
        )
    )

    opciones_anomalia = [
        "Diferencia ERP–WMS",
        "Contenedor sobre estándar",
        "Pallet parcial",
        "Contenedor residual",
        "Almacén fragmentado",
        "Baja confianza del estándar",
        "Picking excedido",
        "Sin patrón concluyente",
        "Conciliado con anomalía física",
    ]

    fa1, fa2, fa3 = st.columns(
        [1.7, 1.2, 1.1]
    )

    with fa1:
        tipos_anomalia = st.multiselect(
            "Anomalías a revisar",
            options=opciones_anomalia,
            default=[],
            placeholder=(
                "Elegí una o varias señales"
            ),
            help=(
                "Estos filtros se aplican sobre los datos físicos, "
                "sin depender del origen probable asignado."
            ),
        )

    with fa2:
        alcance_fisico = st.segmented_control(
            "Área física",
            options=[
                "Todos",
                "Almacén",
                "Picking",
            ],
            default="Todos",
            key="inventario_alcance_fisico",
        )

    with fa3:
        mostrar = st.selectbox(
            "Universo",
            options=[
                "Todos los artículos",
                "Solo con diferencia ERP–WMS",
                "Solo con anomalía física",
                "Solo conciliados con anomalía",
            ],
            index=0,
            key="inventario_universo_diagnostico",
        )

    fb1, fb2, fb3, fb4 = st.columns(4)

    with fb1:
        origen_diagnostico = st.multiselect(
            "Origen probable",
            options=sorted(
                diagnosticos_activos[
                    "OrigenProbableInicial"
                ].dropna().unique()
            ),
            default=[],
        )

    with fb2:
        tipo_conteo_diagnostico = st.multiselect(
            "Conteo sugerido",
            options=sorted(
                tabla[
                    "TipoConteoSugerido"
                ]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            ),
            default=[],
        )

    with fb3:
        riesgo_minimo = st.slider(
            "Score mínimo",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
        )

    with fb4:
        confianza_maxima = st.slider(
            "Confianza máxima del estándar",
            min_value=0,
            max_value=100,
            value=100,
            step=5,
            help=(
                "Bajalo para encontrar estándares poco confiables. "
                "100 no aplica filtro."
            ),
        )

    diagnostico_visual = tabla.loc[
        tabla["ScoreRiesgoPreventivo"].ge(
            riesgo_minimo
        )
    ].copy()

    if alcance_fisico == "Almacén":
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "TieneAnomaliaAlmacen"
                ]
                | diagnostico_visual[
                    "StockAlmacen"
                ].gt(0)
            ]
        )
    elif alcance_fisico == "Picking":
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "TieneAnomaliaPicking"
                ]
                | diagnostico_visual[
                    "StockPicking"
                ].gt(0)
            ]
        )

    if mostrar == "Solo con diferencia ERP–WMS":
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "TieneDiferenciaERPvsWMS"
                ]
            ]
        )
    elif mostrar == "Solo con anomalía física":
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "TieneAnomaliaAlmacen"
                ]
                | diagnostico_visual[
                    "TieneAnomaliaPicking"
                ]
            ]
        )
    elif mostrar == "Solo conciliados con anomalía":
        diagnostico_visual = (
            diagnostico_visual.loc[
                ~diagnostico_visual[
                    "TieneDiferenciaERPvsWMS"
                ]
                & (
                    diagnostico_visual[
                        "TieneAnomaliaAlmacen"
                    ]
                    | diagnostico_visual[
                        "TieneAnomaliaPicking"
                    ]
                )
            ]
        )

    if confianza_maxima < 100:
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "ConfianzaEstandar"
                ].le(confianza_maxima)
            ]
        )

    if tipos_anomalia:
        mascara_anomalia = pd.Series(
            False,
            index=diagnostico_visual.index,
        )

        for tipo in tipos_anomalia:
            if tipo == "Diferencia ERP–WMS":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "TieneDiferenciaERPvsWMS"
                    ]
                )
            elif tipo == "Contenedor sobre estándar":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "ContenedoresSobreEstandar"
                    ].gt(0)
                )
            elif tipo == "Pallet parcial":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "PalletsParciales"
                    ].gt(0)
                )
            elif tipo == "Contenedor residual":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "ContenedoresResiduales"
                    ].gt(0)
                )
            elif tipo == "Almacén fragmentado":
                mascara_anomalia |= (
                    (
                        diagnostico_visual[
                            "PalletsParciales"
                        ]
                        + diagnostico_visual[
                            "ContenedoresResiduales"
                        ]
                    ).ge(2)
                )
            elif tipo == "Baja confianza del estándar":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "ConfianzaEstandar"
                    ].gt(0)
                    & diagnostico_visual[
                        "ConfianzaEstandar"
                    ].lt(50)
                )
            elif tipo == "Picking excedido":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "PickingSobreMaximo"
                    ]
                )
            elif tipo == "Sin patrón concluyente":
                mascara_anomalia |= (
                    diagnostico_visual[
                        "SinPatronConcluyente"
                    ]
                )
            elif tipo == "Conciliado con anomalía física":
                mascara_anomalia |= (
                    ~diagnostico_visual[
                        "TieneDiferenciaERPvsWMS"
                    ]
                    & (
                        diagnostico_visual[
                            "TieneAnomaliaAlmacen"
                        ]
                        | diagnostico_visual[
                            "TieneAnomaliaPicking"
                        ]
                    )
                )

        diagnostico_visual = (
            diagnostico_visual.loc[
                mascara_anomalia
            ]
        )

    if origen_diagnostico:
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "OrigenProbableInicial"
                ].isin(origen_diagnostico)
            ]
        )

    if tipo_conteo_diagnostico:
        diagnostico_visual = (
            diagnostico_visual.loc[
                diagnostico_visual[
                    "TipoConteoSugerido"
                ].isin(tipo_conteo_diagnostico)
            ]
        )

    r1, r2, r3, r4 = st.columns(4)
    r1.metric(
        "Artículos visibles",
        entero(len(diagnostico_visual)),
    )
    r2.metric(
        "Con anomalía en Almacén",
        entero(
            diagnostico_visual[
                "TieneAnomaliaAlmacen"
            ].sum()
        ),
    )
    r3.metric(
        "Con Picking excedido",
        entero(
            diagnostico_visual[
                "TieneAnomaliaPicking"
            ].sum()
        ),
    )
    r4.metric(
        "ERP ≠ WMS",
        entero(
            diagnostico_visual[
                "TieneDiferenciaERPvsWMS"
            ].sum()
        ),
    )

    if diagnostico_visual.empty:
        st.warning(
            "No hay artículos con esta combinación de filtros. "
            "Probá dejar el score en 0, Universo en Todos y "
            "seleccionar directamente una anomalía física."
        )

    columnas_diagnostico = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "StockERP",
        "StockWMSResumen",
        "DiferenciaERPvsWMS",
        "StockPicking",
        "PickingMinimoConfigurado",
        "PickingMaximoConfigurado",
        "StockAlmacen",
        "PalletEstandarInferido",
        "ConfianzaEstandar",
        "PalletsCompletos",
        "PalletsParciales",
        "ContenedoresResiduales",
        "ContenedoresSobreEstandar",
        "ScoreRiesgoPreventivo",
        "OrigenProbableInicial",
        "TipoConteoSugerido",
        "DiagnosticoInicial",
        "AccionInicialSugerida",
        "UbicacionesSugeridas",
        "TieneDiferenciaERPvsWMS",
        "TieneAnomaliaAlmacen",
        "TieneAnomaliaPicking",
        "SinPatronConcluyente",
    ]

    st.dataframe(
        diagnostico_visual[
            [
                columna
                for columna in columnas_diagnostico
                if columna
                in diagnostico_visual.columns
            ]
        ],
        hide_index=True,
        width="stretch",
        height=460,
        column_config={
            "ScoreRiesgoPreventivo": (
                st.column_config.ProgressColumn(
                    "Riesgo",
                    min_value=0,
                    max_value=100,
                    format="%.1f",
                )
            ),
            "ConfianzaEstandar": (
                st.column_config.ProgressColumn(
                    "Confianza estándar",
                    min_value=0,
                    max_value=100,
                    format="%.1f %%",
                )
            ),
        },
    )

    if not diagnostico_visual.empty:
        articulo_diagnostico = st.selectbox(
            "Abrir diagnóstico del artículo",
            options=diagnostico_visual[
                "ArticuloCodigo"
            ].astype(str).tolist(),
            format_func=lambda codigo: (
                f"{codigo} — "
                f"{diagnostico_visual.loc[
                    diagnostico_visual[
                        'ArticuloCodigo'
                    ].astype(str).eq(codigo),
                    'ArticuloDescripcion'
                ].iloc[0]}"
            ),
            key="inventario_articulo_diagnostico",
        )

        ficha_diag = diagnostico_visual.loc[
            diagnostico_visual[
                "ArticuloCodigo"
            ].astype(str).eq(
                articulo_diagnostico
            )
        ].iloc[0]

        with st.container(border=True):
            st.markdown(
                f"#### {articulo_diagnostico} · "
                f"{ficha_diag['OrigenProbableInicial']}"
            )

            fd1, fd2, fd3, fd4, fd5 = st.columns(5)
            fd1.metric(
                "ERP",
                entero(ficha_diag["StockERP"]),
            )
            fd2.metric(
                "WMS",
                entero(
                    ficha_diag[
                        "StockWMSResumen"
                    ]
                ),
            )
            fd3.metric(
                "Picking",
                entero(
                    ficha_diag["StockPicking"]
                ),
            )
            fd4.metric(
                "Almacén",
                entero(
                    ficha_diag["StockAlmacen"]
                ),
            )
            fd5.metric(
                "Pallet estándar",
                entero(
                    ficha_diag[
                        "PalletEstandarInferido"
                    ]
                ),
                (
                    f"{ficha_diag['ConfianzaEstandar']:.1f}% "
                    "de confianza"
                ),
            )

            st.info(
                str(
                    ficha_diag[
                        "DiagnosticoInicial"
                    ]
                )
            )
            st.success(
                "Acción sugerida: "
                + str(
                    ficha_diag[
                        "AccionInicialSugerida"
                    ]
                )
            )

            st.markdown(
                "**Ubicaciones concretas sugeridas**"
            )
            st.write(
                ficha_diag[
                    "UbicacionesSugeridas"
                ]
                or "No hay ubicaciones sugeridas."
            )

            detalle_articulo_diag = (
                detalle_ubicaciones.loc[
                    detalle_ubicaciones[
                        "ArticuloCodigo"
                    ].astype(str).eq(
                        articulo_diagnostico
                    )
                ].copy()
            )

            columnas_detalle_diag = [
                "TipoUbicacion",
                "OrigenClasificacionUbicacion",
                "Ubicacion",
                "Contenedor",
                "Cantidad",
                "PalletEstandarInferido",
                "PorcentajeDelEstandar",
                "ClasificacionContenedor",
                "AreaUbicacion",
                "PasilloUbicacion",
            ]

            st.dataframe(
                detalle_articulo_diag[
                    [
                        columna
                        for columna
                        in columnas_detalle_diag
                        if columna
                        in detalle_articulo_diag.columns
                    ]
                ],
                hide_index=True,
                width="stretch",
                height=320,
            )

        preseleccion = st.multiselect(
            "Artículos para enviar al Planificador",
            options=diagnostico_visual[
                "ArticuloCodigo"
            ].astype(str).tolist(),
            default=diagnostico_visual.head(
                min(
                    len(diagnostico_visual),
                    10,
                )
            )[
                "ArticuloCodigo"
            ].astype(str).tolist(),
            key="inventario_preseleccion_diagnostico",
        )

        boton_1, boton_2 = st.columns(2)

        with boton_1:
            if st.button(
                "🎯 Enviar selección al Planificador",
                type="primary",
                width="stretch",
                disabled=not preseleccion,
            ):
                seleccion = diagnostico_visual.loc[
                    diagnostico_visual[
                        "ArticuloCodigo"
                    ].astype(str).isin(
                        preseleccion
                    )
                ].copy()

                tipos = (
                    seleccion[
                        "TipoConteoSugerido"
                    ]
                    .value_counts()
                )

                tipo_sugerido = (
                    tipos.index[0]
                    if not tipos.empty
                    else "General"
                )

                st.session_state[
                    "inventario_codigos_sugeridos"
                ] = preseleccion
                st.session_state[
                    "inventario_tipo_sugerido"
                ] = tipo_sugerido

                st.success(
                    f"{len(preseleccion)} artículos "
                    f"enviados al Planificador. "
                    f"Tipo sugerido: {tipo_sugerido}."
                )

        with boton_2:
            st.download_button(
                "⬇️ Descargar diagnóstico preventivo",
                data=dataframe_a_csv_limpio(
                    diagnostico_visual
                ),
                file_name=(
                    "inventario_diagnostico_preventivo.csv"
                ),
                mime="text/csv",
                width="stretch",
            )

    st.markdown(
        "### Análisis de diferencias"
    )

    g1, g2 = st.columns(2)

    estados = (
        tabla
        .groupby(
            "EstadoConciliacion",
            as_index=False,
        )
        .agg(
            Codigos=(
                "ArticuloCodigo",
                "nunique",
            )
        )
    )

    total_codigos_estado = int(
        estados["Codigos"].sum()
    )

    estados["Porcentaje"] = (
        estados["Codigos"]
        .div(total_codigos_estado or 1)
        .mul(100)
    )

    estados["Etiqueta"] = (
        estados["Codigos"]
        .map(entero)
        + " · "
        + estados["Porcentaje"]
        .map(lambda valor: f"{valor:.1f}%")
    )

    with g1:
        st.markdown(
            "#### Conciliación ERP vs WMS"
        )

        base_estado = alt.Chart(estados).encode(
            theta=alt.Theta(
                "Codigos:Q",
                stack=True,
            ),
            color=alt.Color(
                "EstadoConciliacion:N",
                title=None,
            ),
        )

        arcos_estado = base_estado.mark_arc(
            innerRadius=70,
            outerRadius=115,
            stroke="#111827",
            strokeWidth=2,
        ).encode(
            tooltip=[
                alt.Tooltip(
                    "EstadoConciliacion:N",
                    title="Estado",
                ),
                alt.Tooltip(
                    "Codigos:Q",
                    title="Códigos",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "Porcentaje:Q",
                    title="Participación",
                    format=".1f",
                ),
            ],
        )

        etiquetas_estado = base_estado.mark_text(
            radius=142,
            fontSize=12,
            fontWeight=700,
            color="#F8FAFC",
        ).encode(
            text="Etiqueta:N",
        )

        centro_estado = (
            alt.Chart(
                pd.DataFrame({
                    "Total": [total_codigos_estado],
                    "Texto": [
                        f"{entero(total_codigos_estado)}\nCódigos"
                    ],
                })
            )
            .mark_text(
                align="center",
                baseline="middle",
                fontSize=17,
                fontWeight=700,
                color="#F8FAFC",
                lineBreak="\n",
            )
            .encode(text="Texto:N")
        )

        grafico_estado = (
            arcos_estado
            + etiquetas_estado
            + centro_estado
        ).properties(height=340)

        st.altair_chart(
            grafico_estado,
            width="stretch",
        )

    familia = resumen_por_categoria(
        tabla,
        "Familia2",
        top=10,
    )

    with g2:
        st.markdown(
            "#### Diferencia absoluta por familia"
        )

        if familia.empty:
            st.info(
                "No hay familias disponibles."
            )

        else:
            familia = familia.copy()
            familia["EtiquetaValor"] = (
                familia["DiferenciaAbsoluta"]
                .map(entero)
                + " u."
            )

            max_familia = float(
                familia["DiferenciaAbsoluta"].max()
            )

            base_familia = alt.Chart(familia).encode(
                y=alt.Y(
                    "Familia2:N",
                    sort="-x",
                    title=None,
                ),
            )

            barras_familia = base_familia.mark_bar(
                cornerRadiusEnd=5
            ).encode(
                x=alt.X(
                    "DiferenciaAbsoluta:Q",
                    title="Unidades",
                    scale=alt.Scale(
                        domain=[
                            0,
                            max_familia * 1.18
                            if max_familia > 0
                            else 1,
                        ]
                    ),
                ),
                tooltip=[
                    alt.Tooltip(
                        "Familia2:N",
                        title="Familia",
                    ),
                    alt.Tooltip(
                        "DiferenciaAbsoluta:Q",
                        title="Diferencia absoluta",
                        format=",.0f",
                    ),
                    alt.Tooltip(
                        "CodigosConDiferencia:Q",
                        title="Códigos afectados",
                        format=",.0f",
                    ),
                ],
            )

            etiquetas_familia = base_familia.mark_text(
                align="left",
                baseline="middle",
                dx=7,
                fontSize=11,
                fontWeight=700,
                color="#F8FAFC",
            ).encode(
                x="DiferenciaAbsoluta:Q",
                text="EtiquetaValor:N",
            )

            grafico_familia = (
                barras_familia
                + etiquetas_familia
            ).properties(height=320)

            st.altair_chart(
                grafico_familia,
                width="stretch",
            )

    # El gráfico operativo muestra todos los artículos críticos con
    # diferencia ERP vs WMS, ordenados de mayor a menor diferencia.
    top = (
        tabla.loc[
            tabla["PrioridadInventario"].eq("Crítica")
            & tabla["EstadoConciliacion"].ne("Conciliado")
        ]
        .sort_values(
            "DiferenciaAbsoluta",
            ascending=False,
        )
        .copy()
    )

    st.markdown(
        "#### 🚨 Artículos críticos con diferencia ERP vs WMS"
    )

    if top.empty:
        st.success(
            "No se detectaron artículos críticos con diferencia "
            "ERP vs WMS con la configuración actual."
        )

    else:
        top["EtiquetaValor"] = (
            top["DiferenciaAbsoluta"]
            .map(entero)
            + " u."
        )

        max_top = float(
            top["DiferenciaAbsoluta"].max()
        )

        base_top = alt.Chart(top).encode(
            y=alt.Y(
                "ArticuloCodigo:N",
                sort="-x",
                title=None,
            ),
        )

        barras_top = base_top.mark_bar(
            cornerRadiusEnd=5
        ).encode(
            x=alt.X(
                "DiferenciaAbsoluta:Q",
                title="Diferencia absoluta",
                scale=alt.Scale(
                    domain=[
                        0,
                        max_top * 1.12
                        if max_top > 0
                        else 1,
                    ]
                ),
            ),
            color=alt.Color(
                "SentidoDiferencia:N",
                title=None,
            ),
            tooltip=[
                alt.Tooltip(
                    "ArticuloCodigo:N",
                    title="Artículo",
                ),
                alt.Tooltip(
                    "ArticuloDescripcion:N",
                    title="Descripción",
                ),
                alt.Tooltip(
                    "StockERP:Q",
                    title="ERP",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "StockWMSResumen:Q",
                    title="WMS resumen",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "StockWMSDetalle:Q",
                    title="WMS detalle comparable",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "DiferenciaERPvsWMS:Q",
                    title="WMS - ERP",
                    format=",.0f",
                ),
            ],
        )

        etiquetas_top = base_top.mark_text(
            align="left",
            baseline="middle",
            dx=7,
            fontSize=11,
            fontWeight=700,
            color="#F8FAFC",
        ).encode(
            x="DiferenciaAbsoluta:Q",
            text="EtiquetaValor:N",
        )

        grafico_top = (
            barras_top
            + etiquetas_top
        ).properties(
            height=max(
                420,
                len(top) * 27,
            )
        )

        st.altair_chart(
            grafico_top,
            width="stretch",
        )

    st.markdown(
        "### Detalle de conciliación"
    )

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        estados_filtro = st.multiselect(
            "Estado",
            sorted(
                tabla[
                    "EstadoConciliacion"
                ].unique()
            ),
            default=[],
        )

    with f2:
        prioridades = st.multiselect(
            "Prioridad",
            sorted(
                tabla[
                    "PrioridadInventario"
                ].unique()
            ),
            default=[],
        )

    with f3:
        familias = st.multiselect(
            "Familia",
            sorted(
                tabla["Familia2"].unique()
            ),
            default=[],
        )

    with f4:
        solo_diferencias = st.toggle(
            "Solo diferencias en la tabla",
            value=solo_diferencias_global,
            key="inventario_solo_diferencias_detalle",
        )

    filtrada = tabla.copy()

    if estados_filtro:
        filtrada = filtrada.loc[
            filtrada[
                "EstadoConciliacion"
            ].isin(estados_filtro)
        ]

    if prioridades:
        filtrada = filtrada.loc[
            filtrada[
                "PrioridadInventario"
            ].isin(prioridades)
        ]

    if familias:
        filtrada = filtrada.loc[
            filtrada[
                "Familia2"
            ].isin(familias)
        ]

    if solo_diferencias:
        filtrada = filtrada.loc[
            filtrada[
                "EstadoConciliacion"
            ].ne("Conciliado")
        ]

    visual = filtrada.copy()

    columnas_redondeo = [
        "StockERP",
        "StockWMSResumen",
        "Disponible",
        "Bloqueados",
        "Recepcion",
        "Preparacion",
        "StockWMSDetalleComparable",
        "StockWMSDetalleAuxiliar",
        "DiferenciaERPvsWMS",
        "DiferenciaAbsoluta",
        "DiferenciaIntegridadWMS",
    ]

    for columna in columnas_redondeo:
        visual[columna] = (
            visual[columna].round(2)
        )

    visual["DiferenciaPorcentaje"] = (
        visual["DiferenciaPorcentaje"]
        .round(1)
    )

    st.caption(
        f"{len(visual):,} registros"
        .replace(",", ".")
    )

    st.dataframe(
        visual,
        width="stretch",
        hide_index=True,
        height=620,
        column_config={
            "DiferenciaPorcentaje": (
                st.column_config.NumberColumn(
                    "Diferencia %",
                    format="%.1f%%",
                )
            ),
        },
    )

    columnas_resumen = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "GrupoInventario",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "StockERPBase",
        "StockERPSanitarios",
        "StockERP",
        "StockWMSResumen",
        "StockWMSDetalleComparable",
        "DiferenciaERPvsWMS",
        "DiferenciaAbsoluta",
        "DiferenciaPorcentaje",
        "EstadoConciliacion",
        "SentidoDiferencia",
        "PrioridadInventario",
        "CantidadUbicaciones",
        "CantidadContenedores",
        "StockPicking",
        "StockAlmacen",
        "PickingMinimoConfigurado",
        "PickingMaximoConfigurado",
        "PalletEstandarInferido",
        "ConfianzaEstandar",
        "PalletsCompletos",
        "PalletsParciales",
        "ContenedoresResiduales",
        "ContenedoresSobreEstandar",
        "ScoreRiesgoPreventivo",
        "OrigenProbableInicial",
        "TipoConteoSugerido",
        "DiagnosticoInicial",
        "AccionInicialSugerida",
        "UbicacionesSugeridas",
    ]

    columnas_resumen = [
        columna
        for columna in columnas_resumen
        if columna in visual.columns
    ]

    resumen_descarga = visual[
        columnas_resumen
    ].copy()

    descarga_1, descarga_2 = st.columns(2)

    with descarga_1:
        st.download_button(
            "⬇️ Descargar resumen",
            data=dataframe_a_csv_limpio(
                resumen_descarga
            ),
            file_name=(
                "inventario_resumen_erp_wms.csv"
            ),
            mime="text/csv",
            width="stretch",
            key="descargar_inventario_resumen",
            help=(
                "Descarga una fila por artículo con las "
                "columnas principales de análisis."
            ),
        )

    with descarga_2:
        st.download_button(
            "⬇️ Descargar consolidado total",
            data=dataframe_a_csv_limpio(
                visual
            ),
            file_name=(
                "inventario_consolidado_total_erp_wms.csv"
            ),
            mime="text/csv",
            width="stretch",
            key="descargar_inventario_consolidado",
            help=(
                "Descarga todas las columnas disponibles "
                "de la conciliación."
            ),
        )
