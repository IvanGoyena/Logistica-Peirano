from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from models.stock.picking_config import (
    construir_analisis_picking,
    obtener_detalle_picking,
)
from utils.estilo_graficos import aplicar_formato_visual_plotly
from utils.stock.helpers import (
    aplicar_busqueda,
    dataframe_a_csv,
    dataframe_para_streamlit,
    formato_entero,
)


ORDEN_ROTACION = [
    "🔥 Caliente",
    "🟡 Intermedio",
    "❄️ Frío",
    "🆕 Nuevo ingreso",
    "⚫ Sin movimiento",
]


def _excluir_repuestos(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    if tabla.empty:
        return tabla

    familia2 = (
        tabla.get(
            "Familia2",
            tabla.get(
                "Familia",
                pd.Series("", index=tabla.index),
            ),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )
    codigo = (
        tabla["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    mascara = (
        familia2.str.contains("REPUEST", na=False)
        | familia2.str.contains(
            r"PARTES?\s*(Y|E|&)?\s*PIEZAS?",
            na=False,
            regex=True,
        )
        | codigo.str.startswith(
            ("R", "A", "U"),
            na=False,
        )
    )

    return tabla.loc[~mascara].copy()


def _render_figura(
    figura,
    altura: int,
) -> None:
    aplicar_formato_visual_plotly(
        figura,
        altura=altura,
    )
    st.plotly_chart(
        figura,
        width="stretch",
        config={"displaylogo": False},
    )


def _estado_formulario() -> dict:
    defaults = {
        "picking_aplicado_meses": 6,
        "picking_aplicado_caliente": 15,
        "picking_aplicado_intermedio": 10,
        "picking_aplicado_frio": 5,
        "picking_aplicado_sector": [],
        "picking_aplicado_rotacion": [],
        "picking_aplicado_busqueda": "",
        "picking_aplicado_repuestos": False,
    }

    for clave, valor in defaults.items():
        if clave not in st.session_state:
            st.session_state[clave] = valor

    return defaults


def render(
    contexto: dict,
) -> None:
    defaults = _estado_formulario()

    tabla_articulos = contexto.get(
        "tabla_articulos",
        pd.DataFrame(),
    )
    tabla_volumetria = contexto.get(
        "tabla_volumetria",
        pd.DataFrame(),
    )
    tabla_max_min = contexto.get(
        "tabla_max_min",
        pd.DataFrame(),
    )
    tabla_stock = contexto.get(
        "tabla_stock_detallado",
        pd.DataFrame(),
    )
    tabla_ubicaciones = contexto.get(
        "tabla_maestro_ubicaciones",
        pd.DataFrame(),
    )
    historico = contexto.get(
        "historico_ventas_stock",
        pd.DataFrame(),
    )

    st.markdown("### 📦 Configuración de Picking")
    st.caption(
        "Mínimos, máximos, estandarización, cobertura y capacidad "
        "recomendada del picking."
    )

    with st.form(
        "form_filtros_configuracion_picking",
        clear_on_submit=False,
        border=True,
    ):
        columnas = st.columns(
            [0.8, 0.8, 0.8, 0.8, 1.15, 1.15, 1.4, 0.85]
        )

        meses = columnas[0].selectbox(
            "Histórico",
            [3, 6, 12],
            index=[3, 6, 12].index(
                st.session_state[
                    "picking_aplicado_meses"
                ]
            ),
            format_func=lambda valor: f"{valor} meses",
        )
        dias_caliente = columnas[1].number_input(
            "Días caliente",
            min_value=1,
            max_value=45,
            value=int(
                st.session_state[
                    "picking_aplicado_caliente"
                ]
            ),
        )
        dias_intermedio = columnas[2].number_input(
            "Días intermedio",
            min_value=1,
            max_value=30,
            value=int(
                st.session_state[
                    "picking_aplicado_intermedio"
                ]
            ),
        )
        dias_frio = columnas[3].number_input(
            "Días frío",
            min_value=1,
            max_value=20,
            value=int(
                st.session_state[
                    "picking_aplicado_frio"
                ]
            ),
        )

        # Primera construcción para obtener sectores disponibles.
        resumen_base, detalle_base, metadata = (
            construir_analisis_picking(
                tabla_articulos,
                tabla_volumetria,
                tabla_max_min,
                tabla_stock,
                tabla_ubicaciones,
                historico,
                int(
                    st.session_state[
                        "picking_aplicado_meses"
                    ]
                ),
                int(
                    st.session_state[
                        "picking_aplicado_caliente"
                    ]
                ),
                int(
                    st.session_state[
                        "picking_aplicado_intermedio"
                    ]
                ),
                int(
                    st.session_state[
                        "picking_aplicado_frio"
                    ]
                ),
            )
        )

        sectores = sorted(
            resumen_base.get(
                "Sectorizacion",
                pd.Series(dtype=str),
            )
            .fillna("")
            .astype(str)
            .loc[lambda serie: serie.ne("")]
            .unique()
            .tolist()
        )

        sector = columnas[4].multiselect(
            "Sectorización",
            sectores,
            default=[
                valor
                for valor in st.session_state[
                    "picking_aplicado_sector"
                ]
                if valor in sectores
            ],
        )
        rotacion = columnas[5].multiselect(
            "Rotación",
            ORDEN_ROTACION,
            default=st.session_state[
                "picking_aplicado_rotacion"
            ],
        )
        busqueda = columnas[6].text_input(
            "Buscar producto",
            value=st.session_state[
                "picking_aplicado_busqueda"
            ],
            placeholder="Código o descripción...",
        )
        ver_repuestos = columnas[7].toggle(
            "Ver repuestos",
            value=bool(
                st.session_state[
                    "picking_aplicado_repuestos"
                ]
            ),
        )

        aplicar, quitar, _ = st.columns(
            [1, 1, 5]
        )
        aplicar_filtros = aplicar.form_submit_button(
            "✅ Aplicar filtros",
            type="primary",
            width="stretch",
        )
        quitar_filtros = quitar.form_submit_button(
            "🧹 Quitar filtros",
            width="stretch",
        )

    if quitar_filtros:
        for clave, valor in defaults.items():
            st.session_state[clave] = valor
        st.session_state.pop(
            "picking_codigo_detalle",
            None,
        )
        st.rerun()

    if aplicar_filtros:
        st.session_state[
            "picking_aplicado_meses"
        ] = int(meses)
        st.session_state[
            "picking_aplicado_caliente"
        ] = int(dias_caliente)
        st.session_state[
            "picking_aplicado_intermedio"
        ] = int(dias_intermedio)
        st.session_state[
            "picking_aplicado_frio"
        ] = int(dias_frio)
        st.session_state[
            "picking_aplicado_sector"
        ] = sector
        st.session_state[
            "picking_aplicado_rotacion"
        ] = rotacion
        st.session_state[
            "picking_aplicado_busqueda"
        ] = busqueda
        st.session_state[
            "picking_aplicado_repuestos"
        ] = bool(ver_repuestos)
        st.session_state.pop(
            "picking_codigo_detalle",
            None,
        )
        st.rerun()

    resumen, detalle, metadata = construir_analisis_picking(
        tabla_articulos,
        tabla_volumetria,
        tabla_max_min,
        tabla_stock,
        tabla_ubicaciones,
        historico,
        int(
            st.session_state[
                "picking_aplicado_meses"
            ]
        ),
        int(
            st.session_state[
                "picking_aplicado_caliente"
            ]
        ),
        int(
            st.session_state[
                "picking_aplicado_intermedio"
            ]
        ),
        int(
            st.session_state[
                "picking_aplicado_frio"
            ]
        ),
    )

    vista = resumen.copy()
    detalle_filtrado = detalle.copy()

    if not st.session_state[
        "picking_aplicado_repuestos"
    ]:
        vista = _excluir_repuestos(vista)
        detalle_filtrado = _excluir_repuestos(
            detalle_filtrado
        )

    sectores_aplicados = st.session_state[
        "picking_aplicado_sector"
    ]
    if sectores_aplicados:
        vista = vista.loc[
            vista["Sectorizacion"].isin(
                sectores_aplicados
            )
        ].copy()
        detalle_filtrado = detalle_filtrado.loc[
            detalle_filtrado[
                "Sectorizacion"
            ].isin(sectores_aplicados)
        ].copy()

    rotacion_aplicada = st.session_state[
        "picking_aplicado_rotacion"
    ]
    if rotacion_aplicada:
        vista = vista.loc[
            vista[
                "CategoriaRotacion"
            ].isin(rotacion_aplicada)
        ].copy()
        detalle_filtrado = detalle_filtrado.loc[
            detalle_filtrado[
                "CategoriaRotacion"
            ].isin(rotacion_aplicada)
        ].copy()

    busqueda_aplicada = st.session_state[
        "picking_aplicado_busqueda"
    ]
    vista = aplicar_busqueda(
        vista,
        busqueda_aplicada,
    )
    detalle_filtrado = aplicar_busqueda(
        detalle_filtrado,
        busqueda_aplicada,
    )

    if vista.empty:
        st.warning(
            "No hay artículos para los filtros aplicados."
        )
        return

    kpis = st.columns(7)
    kpis[0].metric(
        "📍 Configurados",
        formato_entero(
            vista.get(
                "UbicacionPicking",
                pd.Series(dtype=str),
            )
            .fillna("")
            .astype(str)
            .ne("")
            .sum()
        ),
    )
    kpis[1].metric(
        "✅ Correctos",
        formato_entero(
            vista["AccionSugerida"]
            .eq("Configuración correcta")
            .sum()
        ),
    )
    kpis[2].metric(
        "🔥 Aumentar",
        formato_entero(
            vista["AccionSugerida"]
            .eq("Aumentar capacidad")
            .sum()
        ),
    )
    kpis[3].metric(
        "📦 Reducir",
        formato_entero(
            vista["AccionSugerida"]
            .eq("Reducir capacidad")
            .sum()
        ),
    )
    kpis[4].metric(
        "➕ Crear picking",
        formato_entero(
            vista["AccionSugerida"]
            .eq("Crear picking")
            .sum()
        ),
    )
    kpis[5].metric(
        "⚠️ Revisar",
        formato_entero(
            vista["AccionSugerida"]
            .eq("Revisar configuración")
            .sum()
        ),
    )
    kpis[6].metric(
        "🔥 Calientes",
        formato_entero(
            vista["CategoriaRotacion"]
            .eq("🔥 Caliente")
            .sum()
        ),
    )

    grafico, resumen_acciones = st.columns(
        [1.35, 0.85]
    )

    with grafico:
        st.markdown(
            "#### Máximo actual vs máximo sugerido"
        )
        comparacion = (
            vista.loc[
                vista["AccionSugerida"].isin(
                    [
                        "Aumentar capacidad",
                        "Reducir capacidad",
                        "Crear picking",
                    ]
                )
            ]
            .sort_values(
                "ScoreSlotting",
                ascending=False,
            )
            .head(12)
            .copy()
        )

        if comparacion.empty:
            st.info(
                "No hay cambios prioritarios de capacidad."
            )
        else:
            comparacion["Producto"] = (
                comparacion["ArticuloCodigo"]
                + " · "
                + comparacion[
                    "ArticuloDescripcion"
                ]
                .fillna("")
                .astype(str)
                .str.slice(0, 34)
            )
            larga = comparacion.melt(
                id_vars=["Producto"],
                value_vars=[
                    "StockMaximoActual",
                    "StockMaximoSugerido",
                ],
                var_name="Configuración",
                value_name="Unidades",
            )
            larga["Configuración"] = (
                larga["Configuración"].replace(
                    {
                        "StockMaximoActual":
                            "Máximo actual",
                        "StockMaximoSugerido":
                            "Máximo sugerido",
                    }
                )
            )
            figura = px.bar(
                larga,
                x="Unidades",
                y="Producto",
                color="Configuración",
                orientation="h",
                barmode="group",
                text="Unidades",
                labels={
                    "Producto": "",
                    "Unidades": "Unidades",
                    "Configuración": "",
                },
            )
            _render_figura(figura, 470)

    with resumen_acciones:
        st.markdown("#### Acciones detectadas")
        acciones = (
            vista.groupby(
                "AccionSugerida",
                as_index=False,
            )
            .agg(
                Articulos=(
                    "ArticuloCodigo",
                    "nunique",
                )
            )
            .sort_values(
                "Articulos",
                ascending=False,
            )
        )
        figura_acciones = px.bar(
            acciones,
            x="Articulos",
            y="AccionSugerida",
            orientation="h",
            text="Articulos",
            labels={
                "AccionSugerida": "",
                "Articulos": "Artículos",
            },
        )
        _render_figura(
            figura_acciones,
            470,
        )

    st.divider()

    encabezado, descarga = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    encabezado.markdown(
        "### Tabla resumen de Picking"
    )
    encabezado.caption(
        "Solo contiene las variables necesarias para decidir "
        "si la configuración debe mantenerse, aumentarse o reducirse."
    )
    descarga.download_button(
        "⬇️ Descargar resumen",
        data=dataframe_a_csv(vista),
        file_name="resumen_configuracion_picking.csv",
        mime="text/csv",
        width="stretch",
    )

    st.dataframe(
        dataframe_para_streamlit(vista),
        hide_index=True,
        width="stretch",
        height=480,
        column_config={
            "ScoreSlotting":
                st.column_config.ProgressColumn(
                    "Score",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                ),
            "ArticuloCodigo":
                st.column_config.TextColumn(
                    "Código",
                ),
            "ArticuloDescripcion":
                st.column_config.TextColumn(
                    "Descripción",
                    width="large",
                ),
            "StockPickingActual":
                st.column_config.NumberColumn(
                    "Stock picking",
                    format="%.0f",
                ),
            "StockMinimoActual":
                st.column_config.NumberColumn(
                    "Mín. actual",
                    format="%.0f",
                ),
            "StockMaximoActual":
                st.column_config.NumberColumn(
                    "Máx. actual",
                    format="%.0f",
                ),
            "StockMaximoSugerido":
                st.column_config.NumberColumn(
                    "Máx. sugerido",
                    format="%.0f",
                ),
            "PalletsActuales":
                st.column_config.NumberColumn(
                    "Pallets almacén",
                    format="%.0f",
                ),
            "PalletsSugeridos":
                st.column_config.NumberColumn(
                    "Pallets sugeridos",
                    format="%.1f",
                ),
        },
    )

    st.markdown("### 🔎 Detalle por artículo")
    opciones = (
        vista[
            [
                "ArticuloCodigo",
                "ArticuloDescripcion",
            ]
        ]
        .drop_duplicates(
            "ArticuloCodigo"
        )
        .copy()
    )
    opciones["Etiqueta"] = (
        opciones["ArticuloCodigo"]
        + " · "
        + opciones[
            "ArticuloDescripcion"
        ].fillna("")
    )
    mapa_codigo = dict(
        zip(
            opciones["Etiqueta"],
            opciones["ArticuloCodigo"],
        )
    )

    selector, boton = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    etiqueta = selector.selectbox(
        "Artículo",
        options=opciones["Etiqueta"].tolist(),
        key="picking_selector_detalle",
    )
    ver_detalle = boton.button(
        "🔎 Ver detalle",
        type="primary",
        width="stretch",
        key="picking_boton_detalle",
    )

    if ver_detalle:
        st.session_state[
            "picking_codigo_detalle"
        ] = mapa_codigo[etiqueta]

    codigo_detalle = st.session_state.get(
        "picking_codigo_detalle"
    )

    if codigo_detalle:
        detalle_articulo = obtener_detalle_picking(
            detalle_filtrado,
            codigo_detalle,
        )
        if not detalle_articulo.empty:
            st.dataframe(
                dataframe_para_streamlit(
                    detalle_articulo
                ),
                hide_index=True,
                width="stretch",
                height=250,
            )
