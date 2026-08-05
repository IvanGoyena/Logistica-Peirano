from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from models.stock.cobertura import construir_tabla_cobertura
from utils.stock.helpers import aplicar_busqueda, dataframe_a_csv, dataframe_para_streamlit, formato_entero
from utils.estilo_graficos import aplicar_formato_visual_plotly


ORDEN_ESTADOS = [
    "Quiebre",
    "Crítico",
    "Bajo",
    "Controlado",
    "Cubierto",
    "Nuevo ingreso",
    "Sin movimiento",
]
ORDEN_CATEGORIAS_VENTA = [
    "🔥 Caliente",
    "🟡 Intermedio",
    "❄️ Frío",
    "🆕 Producto nuevo",
    "⚫ Sin movimiento",
]
COLORES_ESTADOS = {
    "Quiebre": "#DC2626",
    "Crítico": "#EF4444",
    "Bajo": "#F59E0B",
    "Controlado": "#3B82F6",
    "Cubierto": "#16A34A",
    "Nuevo ingreso": "#8B5CF6",
    "Sin movimiento": "#64748B",
}


def _formato_decimal(valor: float, decimales: int = 1) -> str:
    if pd.isna(valor) or not np.isfinite(float(valor)):
        return "—"
    texto = f"{float(valor):,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _preparar_tabla_operativa(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara la tabla visual sin alterar los cálculos originales.
    """
    salida = tabla.copy()

    columnas_enteras = [
        "Disponible",
        "StockComprometido",
        "Bloqueados",
        "Recepcion",
        "Transito",
        "UnidadesPeriodo",
        "StockMinimo",
        "StockMaximo",
    ]

    columnas_decimales = [
        "PorcentajeDisponible",
        "VentaPromedioMensual",
        "VentaPromedioDiaria",
        "FrecuenciaVentaPct",
        "CoberturaDias",
        "CoberturaMeses",
    ]

    for columna in columnas_enteras:
        if columna in salida.columns:
            salida[columna] = (
                pd.to_numeric(
                    salida[columna],
                    errors="coerce",
                )
                .fillna(0)
                .round(0)
            )

    for columna in columnas_decimales:
        if columna in salida.columns:
            salida[columna] = (
                pd.to_numeric(
                    salida[columna],
                    errors="coerce",
                )
                .round(2)
            )

    if "EstadoCobertura" in salida.columns:
        iconos_estado = {
            "Quiebre": "🔴 Quiebre",
            "Crítico": "🟥 Crítico",
            "Bajo": "🟠 Bajo",
            "Controlado": "🔵 Controlado",
            "Cubierto": "🟢 Cubierto",
            "Sin movimiento": "⚪ Sin movimiento",
        }

        salida["EstadoVisual"] = (
            salida["EstadoCobertura"]
            .map(iconos_estado)
            .fillna(
                salida["EstadoCobertura"]
            )
        )

    return salida


def _csv_analisis_cobertura(
    tabla: pd.DataFrame,
) -> bytes:
    """
    Genera un CSV compatible con Excel en configuración regional
    argentina: punto y coma como separador y coma decimal.
    """
    exportacion = _preparar_tabla_operativa(
        tabla
    )

    return exportacion.to_csv(
        index=False,
        sep=";",
        decimal=",",
        encoding="utf-8-sig",
        lineterminator="\n",
    ).encode("utf-8-sig")


def _grafico_plotly(
    figura,
    altura: int = 390,
    *,
    mostrar_valores: bool = True,
) -> None:
    aplicar_formato_visual_plotly(
        figura,
        mostrar_valores=mostrar_valores,
        altura=altura,
    )
    st.plotly_chart(
        figura,
        width="stretch",
        config={"displaylogo": False},
    )


def render(contexto: dict) -> None:
    tabla_disponible = contexto.get("tabla_disponible", pd.DataFrame())
    historico_ventas = contexto.get("historico_ventas_stock", pd.DataFrame())
    tabla_articulos = contexto.get("tabla_articulos", pd.DataFrame())
    tabla_max_min = contexto.get("tabla_max_min", pd.DataFrame())
    tabla_stock_detallado = contexto.get(
        "tabla_stock_detallado",
        pd.DataFrame(),
    )

    st.subheader("📦 Disponible y Cobertura")
    st.caption(
        "Stock disponible actual comparado contra el consumo histórico de Preparación. "
        "Permite detectar quiebres, artículos críticos y meses de cobertura."
    )

    if tabla_disponible.empty:
        st.error("No se encontró la fuente `Stock Disponible`.")
        return

    # ------------------------------------------------------
    # CONFIGURACIÓN DEL ANÁLISIS
    # ------------------------------------------------------
    with st.container(border=True):
        f1, f2, f3, f4, f5, f6, f7 = st.columns(
            [
                0.70,
                1.00,
                1.00,
                1.00,
                1.15,
                1.35,
                0.80,
            ],
            vertical_alignment="bottom",
        )

        with f1:
            meses_analisis = st.selectbox(
                "Histórico",
                options=[3, 6, 12],
                index=0,
                format_func=lambda valor: f"{valor} meses",
                key="cobertura_meses_analisis",
            )

        tabla_cobertura, metadata = construir_tabla_cobertura(
            tabla_disponible=tabla_disponible,
            historico_ventas=historico_ventas,
            tabla_articulos=tabla_articulos,
            tabla_max_min=tabla_max_min,
            tabla_stock_detallado=tabla_stock_detallado,
            meses_analisis=int(meses_analisis),
            dias_producto_nuevo=90,
            dias_ingreso_reciente=30,
        )

        familias = sorted(
            tabla_cobertura.get(
                "Familia",
                pd.Series(dtype=str),
            )
            .fillna("")
            .astype(str)
            .str.strip()
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )

        sectores = sorted(
            tabla_cobertura.get(
                "Sectorizacion",
                pd.Series(dtype=str),
            )
            .fillna("")
            .astype(str)
            .str.strip()
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )

        estados_presentes = [
            estado
            for estado in ORDEN_ESTADOS
            if estado
            in tabla_cobertura.get(
                "EstadoCobertura",
                pd.Series(dtype=str),
            ).unique()
        ]

        categorias_venta_presentes = [
            categoria
            for categoria in ORDEN_CATEGORIAS_VENTA
            if categoria
            in tabla_cobertura.get(
                "CategoriaVenta",
                pd.Series(dtype=str),
            ).unique()
        ]

        with f2:
            filtro_familia = st.multiselect(
                "Familia",
                familias,
                placeholder="Todas",
                key="cobertura_familia",
            )

        with f3:
            filtro_sector = st.multiselect(
                "Sectorización",
                sectores,
                placeholder="Todas",
                key="cobertura_sector",
            )

        with f4:
            filtro_estado = st.multiselect(
                "Estado",
                estados_presentes,
                placeholder="Todos",
                key="cobertura_estado",
            )

        with f5:
            filtro_categoria_venta = st.multiselect(
                "Categoría de venta",
                categorias_venta_presentes,
                placeholder="Todas",
                key="cobertura_categoria_venta",
                help=(
                    "Clasifica los productos según su venta promedio "
                    "mensual dentro del período seleccionado: top 15% "
                    "Caliente, siguiente 35% Intermedio y resto Frío."
                ),
            )

        with f6:
            busqueda = st.text_input(
                "Buscar producto",
                placeholder="Código o descripción...",
                key="cobertura_busqueda",
            )

        with f7:
            ver_repuestos = st.toggle(
                "Ver repuestos y partes",
                value=False,
                key="cobertura_ver_repuestos",
                help=(
                    "Incluye o excluye Repuestos y Partes y piezas. "
                    "También identifica artículos sin maestro cuyos códigos "
                    "comienzan con R, A, U, S o F."
                ),
            )

        estados_ingreso_presentes = [
            estado
            for estado in [
                "🆕 Producto nuevo",
                "📥 Reposición reciente",
                "📦 Producto existente",
                "❓ Sin fecha de ingreso",
            ]
            if estado
            in tabla_cobertura.get(
                "EstadoIngreso",
                pd.Series(dtype=str),
            ).unique()
        ]

        g1, g2, _ = st.columns(
            [1.25, 1.0, 4.75],
            vertical_alignment="bottom",
        )

        with g1:
            filtro_estado_ingreso = st.multiselect(
                "Estado de ingreso",
                estados_ingreso_presentes,
                placeholder="Todos",
                key="cobertura_estado_ingreso",
                help=(
                    "Producto nuevo usa la primera evidencia conocida "
                    "del artículo, no solamente el último contenedor."
                ),
            )

        with g2:
            incluir_nuevos = st.toggle(
                "Incluir nuevos en análisis",
                value=False,
                key="cobertura_incluir_nuevos",
                help=(
                    "Apagado: los productos nuevos quedan fuera de KPIs "
                    "y gráficos de cobertura, pero pueden consultarse "
                    "seleccionando Producto nuevo en Estado de ingreso."
                ),
            )

    vista = tabla_cobertura.copy()

    if not ver_repuestos:
        columna_familia_secundaria = (
            "Familia2"
            if "Familia2" in vista.columns
            else "Familia"
        )

        familia_secundaria = (
            vista[columna_familia_secundaria]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        codigo_articulo = (
            vista["ArticuloCodigo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        # Criterio 1: clasificación del Maestro de Artículos.
        excluir_por_familia = (
            familia_secundaria.str.contains(
                "REPUEST",
                na=False,
            )
            | familia_secundaria.str.contains(
                r"PARTES?\s*(Y|E|&)?\s*PIEZAS?",
                na=False,
                regex=True,
            )
        )

        # Criterio 2: artículos sin clasificación en el maestro.
        # R = Repuestos
        # A / U = Partes y piezas
        excluir_por_codigo = codigo_articulo.str.startswith(
            ("R","A","U","S","F",),
            na=False,
        )

        excluir_repuestos_partes = (
            excluir_por_familia
            | excluir_por_codigo
        )

        vista = vista.loc[
            ~excluir_repuestos_partes
        ].copy()

    if filtro_familia:
        vista = vista.loc[
            vista["Familia"].isin(filtro_familia)
        ].copy()

    if filtro_sector:
        vista = vista.loc[
            vista["Sectorizacion"].isin(filtro_sector)
        ].copy()

    if filtro_estado:
        vista = vista.loc[
            vista["EstadoCobertura"].isin(filtro_estado)
        ].copy()

    if filtro_categoria_venta:
        vista = vista.loc[
            vista["CategoriaVenta"].isin(
                filtro_categoria_venta
            )
        ].copy()

    if filtro_estado_ingreso:
        vista = vista.loc[
            vista["EstadoIngreso"].isin(
                filtro_estado_ingreso
            )
        ].copy()
    elif not incluir_nuevos:
        vista = vista.loc[
            ~vista["EsProductoNuevo"].fillna(False)
        ].copy()

    vista = aplicar_busqueda(
        vista,
        busqueda,
    )

    if vista.empty:
        st.warning("No existen artículos para la combinación de filtros seleccionada.")
        return

    # ------------------------------------------------------
    # KPIs
    # ------------------------------------------------------
    articulos = int(vista["ArticuloCodigo"].nunique())
    unidades_disponibles = float(vista["Disponible"].sum())
    quiebres = int(vista["EstadoCobertura"].eq("Quiebre").sum())
    criticos = int(vista["EstadoCobertura"].isin(["Quiebre", "Crítico"]).sum())
    comprometido = float(vista["StockComprometido"].sum())
    con_consumo = vista.loc[vista["VentaPromedioDiaria"].gt(0)].copy()
    cobertura_promedio = float(
        np.average(
            con_consumo["CoberturaDias"].clip(upper=365),
            weights=con_consumo["VentaPromedioDiaria"],
        )
    ) if not con_consumo.empty and con_consumo["VentaPromedioDiaria"].sum() > 0 else np.nan

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Artículos analizados", formato_entero(articulos))
    k2.metric("Unidades disponibles", formato_entero(unidades_disponibles))
    k3.metric("En quiebre", formato_entero(quiebres))
    k4.metric("Quiebre + críticos", formato_entero(criticos))
    k5.metric("Stock comprometido", formato_entero(comprometido))
    k6.metric("Cobertura promedio", f"{_formato_decimal(cobertura_promedio, 0)} días")

    if pd.notna(metadata.get("fecha_hasta")):
        st.caption(
            "Histórico utilizado: "
            f"{pd.Timestamp(metadata['fecha_desde']).strftime('%d/%m/%Y')} al "
            f"{pd.Timestamp(metadata['fecha_hasta']).strftime('%d/%m/%Y')} · "
            f"{formato_entero(metadata.get('unidades_historicas', 0))} unidades movilizadas."
        )
    else:
        st.warning("El histórico de Métricas no devolvió fechas válidas. Se muestra el disponible, pero no podrá calcularse cobertura.")

    st.divider()

    # ------------------------------------------------------
    # VISUALES
    # ------------------------------------------------------
    graf1, graf2 = st.columns(
        [0.85, 1.35]
    )

    with graf1:
        st.markdown("#### Estado de cobertura")
        st.caption(
            "Cantidad de artículos según los días de stock disponibles."
        )

        resumen_estado = (
            vista
            .groupby(
                "EstadoCobertura",
                as_index=False,
            )
            .agg(
                Articulos=(
                    "ArticuloCodigo",
                    "nunique",
                )
            )
        )

        resumen_estado["EstadoCobertura"] = pd.Categorical(
            resumen_estado["EstadoCobertura"],
            categories=ORDEN_ESTADOS,
            ordered=True,
        )

        resumen_estado = resumen_estado.sort_values(
            "EstadoCobertura"
        )

        fig_estado = px.bar(
            resumen_estado,
            x="EstadoCobertura",
            y="Articulos",
            color="EstadoCobertura",
            color_discrete_map=COLORES_ESTADOS,
            text="Articulos",
            labels={
                "EstadoCobertura": "",
                "Articulos": "Artículos",
            },
        )

        fig_estado.update_traces(
            texttemplate="%{y:,.0f}",
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Artículos: %{y:,.0f}"
                "<extra></extra>"
            ),
        )

        fig_estado.update_layout(
            showlegend=False,
        )

        _grafico_plotly(
            fig_estado,
            390,
        )

    with graf2:
        st.markdown("#### Mayor necesidad de reposición")
        st.caption(
            "Ranking de artículos según las unidades faltantes "
            "para alcanzar 30 días de cobertura."
        )

        riesgo = vista.loc[
            vista["VentaPromedioDiaria"].gt(0)
        ].copy()

        riesgo["Necesidad30Dias"] = (
            riesgo["VentaPromedioDiaria"]
            * 30
        )

        riesgo["Faltante30Dias"] = (
            riesgo["Necesidad30Dias"]
            - riesgo["Disponible"]
        ).clip(lower=0)

        riesgo = (
            riesgo.loc[
                riesgo["Faltante30Dias"].gt(0)
            ]
            .sort_values(
                [
                    "Faltante30Dias",
                    "CoberturaDias",
                ],
                ascending=[
                    False,
                    True,
                ],
            )
            .head(15)
            .copy()
        )

        if riesgo.empty:
            st.success(
                "Los productos con consumo histórico alcanzan "
                "los 30 días de cobertura."
            )
        else:
            riesgo["Producto"] = (
                riesgo["ArticuloCodigo"]
                + " · "
                + riesgo["ArticuloDescripcion"]
                .fillna("")
                .astype(str)
                .str.slice(0, 42)
            )

            fig_riesgo = px.bar(
                riesgo.sort_values(
                    "Faltante30Dias"
                ),
                x="Faltante30Dias",
                y="Producto",
                orientation="h",
                color="EstadoCobertura",
                color_discrete_map=COLORES_ESTADOS,
                text="Faltante30Dias",
                custom_data=[
                    "ArticuloCodigo",
                    "ArticuloDescripcion",
                    "Familia",
                    "Disponible",
                    "VentaPromedioMensual",
                    "CoberturaDias",
                    "EstadoCobertura",
                    "Necesidad30Dias",
                ],
                labels={
                    "Faltante30Dias": (
                        "Unidades faltantes para 30 días"
                    ),
                    "Producto": "",
                },
            )

            fig_riesgo.update_traces(
                texttemplate="%{x:,.0f}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]}<br>"
                    "Familia: %{customdata[2]}<br>"
                    "Disponible: %{customdata[3]:,.0f}<br>"
                    "Consumo mensual: %{customdata[4]:,.1f}<br>"
                    "Cobertura actual: %{customdata[5]:,.1f} días<br>"
                    "Estado: %{customdata[6]}<br>"
                    "Necesidad 30 días: %{customdata[7]:,.0f}<br>"
                    "<b>Faltante: %{x:,.0f}</b>"
                    "<extra></extra>"
                ),
            )

            fig_riesgo.update_layout(
                legend_title_text="",
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )

            _grafico_plotly(
                fig_riesgo,
                470,
            )

    graf3, graf4 = st.columns(2)

    with graf3:
        st.markdown("#### Cobertura ponderada por familia")
        st.caption(
            "Stock total de la familia dividido por su consumo "
            "diario total. No es un promedio simple de artículos."
        )

        familia = vista.loc[
            vista["VentaPromedioDiaria"].gt(0)
        ].copy()

        if familia.empty:
            st.info(
                "No hay consumo histórico para calcular "
                "cobertura por familia."
            )
        else:
            familia["FamiliaAnalisis"] = (
                familia["Familia"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace(
                    "",
                    "SIN FAMILIA",
                )
            )

            familia = (
                familia
                .groupby(
                    "FamiliaAnalisis",
                    as_index=False,
                )
                .agg(
                    Disponible=(
                        "Disponible",
                        "sum",
                    ),
                    VentaDiaria=(
                        "VentaPromedioDiaria",
                        "sum",
                    ),
                    VentaMensual=(
                        "VentaPromedioMensual",
                        "sum",
                    ),
                    Articulos=(
                        "ArticuloCodigo",
                        "nunique",
                    ),
                )
            )

            familia["CoberturaDias"] = np.where(
                familia["VentaDiaria"].gt(0),
                familia["Disponible"]
                / familia["VentaDiaria"],
                np.nan,
            )

            familia = (
                familia
                .dropna(
                    subset=["CoberturaDias"]
                )
                .sort_values(
                    "CoberturaDias"
                )
                .head(15)
            )

            fig_familia = px.bar(
                familia.sort_values(
                    "CoberturaDias",
                    ascending=False,
                ),
                x="CoberturaDias",
                y="FamiliaAnalisis",
                orientation="h",
                text="CoberturaDias",
                custom_data=[
                    "Disponible",
                    "VentaMensual",
                    "Articulos",
                ],
                labels={
                    "CoberturaDias": "Días de cobertura",
                    "FamiliaAnalisis": "",
                },
            )

            fig_familia.update_traces(
                texttemplate="%{x:,.0f} días",
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Cobertura: %{x:,.1f} días<br>"
                    "Disponible: %{customdata[0]:,.0f}<br>"
                    "Consumo mensual: %{customdata[1]:,.1f}<br>"
                    "Artículos: %{customdata[2]:,.0f}"
                    "<extra></extra>"
                ),
            )

            for valor, etiqueta, color in [
                (15, "Crítico", "#EF4444"),
                (30, "Bajo", "#F59E0B"),
                (60, "Controlado", "#3B82F6"),
            ]:
                fig_familia.add_vline(
                    x=valor,
                    line_width=1,
                    line_dash="dot",
                    line_color=color,
                    annotation_text=etiqueta,
                    annotation_position="top",
                    annotation_font_color=color,
                )

            _grafico_plotly(
                fig_familia,
                440,
            )

    with graf4:
        st.markdown(
            "#### Stock disponible vs consumo mensual"
        )
        st.caption(
            "Compara la existencia actual con el ritmo mensual "
            "de salida de cada familia."
        )

        comparacion = vista.loc[
            vista["VentaPromedioMensual"].gt(0)
        ].copy()

        if comparacion.empty:
            st.info(
                "No hay consumo histórico para comparar "
                "stock y movimiento."
            )
        else:
            comparacion["FamiliaAnalisis"] = (
                comparacion["Familia"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace(
                    "",
                    "SIN FAMILIA",
                )
            )

            comparacion = (
                comparacion
                .groupby(
                    "FamiliaAnalisis",
                    as_index=False,
                )
                .agg(
                    Disponible=(
                        "Disponible",
                        "sum",
                    ),
                    ConsumoMensual=(
                        "VentaPromedioMensual",
                        "sum",
                    ),
                )
            )

            comparacion["Impacto"] = (
                comparacion["Disponible"]
                + comparacion["ConsumoMensual"]
            )

            comparacion = (
                comparacion
                .sort_values(
                    "Impacto",
                    ascending=False,
                )
                .head(12)
                .sort_values(
                    "Impacto"
                )
            )

            comparacion_larga = comparacion.melt(
                id_vars=["FamiliaAnalisis"],
                value_vars=[
                    "Disponible",
                    "ConsumoMensual",
                ],
                var_name="Métrica",
                value_name="Unidades",
            )

            comparacion_larga["Métrica"] = (
                comparacion_larga["Métrica"]
                .replace(
                    {
                        "Disponible": "Stock disponible",
                        "ConsumoMensual": "Consumo mensual",
                    }
                )
            )

            fig_comparacion = px.bar(
                comparacion_larga,
                x="Unidades",
                y="FamiliaAnalisis",
                color="Métrica",
                orientation="h",
                barmode="group",
                text="Unidades",
                labels={
                    "FamiliaAnalisis": "",
                    "Unidades": "Unidades",
                    "Métrica": "",
                },
                custom_data=[
                    "Métrica",
                ],
            )

            fig_comparacion.update_traces(
                texttemplate="%{x:,.0f}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "%{customdata[0]}: %{x:,.0f}"
                    "<extra></extra>"
                ),
            )

            fig_comparacion.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
            )

            _grafico_plotly(
                fig_comparacion,
                440,
            )

    st.divider()

    # ------------------------------------------------------
    # TABLA OPERATIVA
    # ------------------------------------------------------
    titulo_tabla, descargar_tabla = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )

    with titulo_tabla:
        st.markdown("### Detalle por artículo")
        st.caption(
            "Ordenado por urgencia de cobertura. "
            "Los filtros superiores afectan toda la pantalla."
        )

    columnas_vista = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "CategoriaVenta",
        "EstadoIngreso",
        "FrecuenciaVentaPct",
        "Disponible",
        "Recepcion",
        "Reservado",
        "Bloqueados",
        "Transito",
        "StockComprometido",
        "PorcentajeDisponible",
        "UnidadesPeriodo",
        "VentaPromedioMensual",
        "VentaPromedioDiaria",
        "CoberturaDias",
        "CoberturaMeses",
        "EstadoCobertura",
        "StockMinimo",
        "StockMaximo",
        "AccionRecomendada",
    ]

    columnas_vista = [
        columna
        for columna in columnas_vista
        if columna in vista.columns
    ]

    tabla_final = _preparar_tabla_operativa(
        vista[columnas_vista]
    )

    columnas_exportacion = [
        columna
        for columna in [
            "ArticuloCodigo",
            "ArticuloDescripcion",
            "Familia",
            "Familia2",
            "Sectorizacion",
            "CategoriaVenta",
            "EstadoIngreso",
            "PrimeraEvidenciaArticulo",
            "UltimoIngresoStockActual",
            "DiasDesdePrimeraEvidencia",
            "DiasDesdeUltimoIngreso",
            "ContenedoresStockActual",
            "FrecuenciaVentaPct",
            "Disponible",
            "Recepcion",
            "Reservado",
            "Bloqueados",
            "Transito",
            "StockComprometido",
            "StockOperativoTotal",
            "PorcentajeDisponible",
            "UnidadesPeriodo",
            "VentaPromedioMensual",
            "VentaPromedioDiaria",
            "CoberturaDias",
            "CoberturaMeses",
            "EstadoCobertura",
            "StockMinimo",
            "StockMaximo",
            "AccionRecomendada",
        ]
        if columna in vista.columns
    ]

    tabla_exportacion = vista[
        columnas_exportacion
    ].copy()

    with descargar_tabla:
        st.download_button(
            "⬇️ Descargar análisis",
            data=_csv_analisis_cobertura(
                tabla_exportacion
            ),
            file_name=(
                f"disponible_cobertura_"
                f"{meses_analisis}_meses.csv"
            ),
            mime="text/csv",
            width="stretch",
            key="descargar_disponible_cobertura",
        )

    columnas_mostradas = [
        columna
        for columna in [
            "ArticuloCodigo",
            "ArticuloDescripcion",
            "Familia",
            "Familia2",
            "Sectorizacion",
            "CategoriaVenta",
            "EstadoIngreso",
            "FrecuenciaVentaPct",
            "Disponible",
            "Recepcion",
            "Reservado",
            "Bloqueados",
            "Transito",
            "StockComprometido",
            "PorcentajeDisponible",
            "UnidadesPeriodo",
            "VentaPromedioMensual",
            "VentaPromedioDiaria",
            "CoberturaDias",
            "CoberturaMeses",
            "EstadoVisual",
            "StockMinimo",
            "StockMaximo",
            "AccionRecomendada",
        ]
        if columna in tabla_final.columns
    ]

    st.dataframe(
        dataframe_para_streamlit(
            tabla_final[
                columnas_mostradas
            ]
        ),
        hide_index=True,
        width="stretch",
        height=600,
        column_config={
            "ArticuloCodigo":
                st.column_config.TextColumn(
                    "Código",
                    width="small",
                ),
            "ArticuloDescripcion":
                st.column_config.TextColumn(
                    "Descripción",
                    width="large",
                ),
            "Familia":
                st.column_config.TextColumn(
                    "Familia",
                ),
            "Familia2":
                st.column_config.TextColumn(
                    "Familia 2",
                ),
            "Sectorizacion":
                st.column_config.TextColumn(
                    "Sectorización",
                ),
            "CategoriaVenta":
                st.column_config.TextColumn(
                    "Categoría de venta",
                    width="medium",
                ),
            "EstadoIngreso":
                st.column_config.TextColumn(
                    "Estado de ingreso",
                    width="medium",
                ),
            "FrecuenciaVentaPct":
                st.column_config.ProgressColumn(
                    "Frecuencia de venta",
                    min_value=0,
                    max_value=100,
                    format="%.2f %%",
                    width="medium",
                    help=(
                        "Porcentaje de meses del período en los que "
                        "el artículo registró al menos una venta."
                    ),
                ),
            "Disponible":
                st.column_config.NumberColumn(
                    "Disponible",
                    format="%.0f",
                ),
            "Recepcion":
                st.column_config.NumberColumn(
                    "Recepción",
                    format="%.0f",
                ),
            "Reservado":
                st.column_config.NumberColumn(
                    "Reservado",
                    format="%.0f",
                ),
            "Bloqueados":
                st.column_config.NumberColumn(
                    "Bloqueados",
                    format="%.0f",
                ),
            "Transito":
                st.column_config.NumberColumn(
                    "Tránsito",
                    format="%.0f",
                ),
            "StockComprometido":
                st.column_config.NumberColumn(
                    "Comprometido",
                    format="%.0f",
                ),
            "PorcentajeDisponible":
                st.column_config.ProgressColumn(
                    "% disponible",
                    min_value=0,
                    max_value=100,
                    format="%.2f %%",
                    width="medium",
                ),
            "UnidadesPeriodo":
                st.column_config.NumberColumn(
                    f"Venta {meses_analisis} meses",
                    format="%.0f",
                ),
            "VentaPromedioMensual":
                st.column_config.NumberColumn(
                    "Venta mensual",
                    format="%.2f",
                ),
            "VentaPromedioDiaria":
                st.column_config.NumberColumn(
                    "Venta diaria",
                    format="%.2f",
                ),
            "CoberturaDias":
                st.column_config.ProgressColumn(
                    "Cobertura días",
                    min_value=0,
                    max_value=60,
                    format="%.2f días",
                    width="medium",
                ),
            "CoberturaMeses":
                st.column_config.NumberColumn(
                    "Cobertura meses",
                    format="%.2f",
                ),
            "EstadoVisual":
                st.column_config.TextColumn(
                    "Estado",
                    width="medium",
                ),
            "StockMinimo":
                st.column_config.NumberColumn(
                    "Mín.",
                    format="%.0f",
                ),
            "StockMaximo":
                st.column_config.NumberColumn(
                    "Máx.",
                    format="%.0f",
                ),
            "AccionRecomendada":
                st.column_config.TextColumn(
                    "Acción",
                    width="medium",
                ),
        },
    )

