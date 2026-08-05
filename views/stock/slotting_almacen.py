from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from models.stock.slotting_almacen import (
    construir_analisis_almacen,
    obtener_detalle_almacen,
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
        "almacen_aplicado_meses": 6,
        "almacen_aplicado_caliente": 15,
        "almacen_aplicado_intermedio": 10,
        "almacen_aplicado_frio": 5,
        "almacen_aplicado_sector": [],
        "almacen_aplicado_rotacion": [],
        "almacen_aplicado_busqueda": "",
        "almacen_aplicado_repuestos": False,
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

    st.markdown("### 🗺️ Slotting de Almacén")
    st.caption(
        "Distribución física, dispersión, distancia al picking "
        "y oportunidades de relocalización."
    )

    with st.form(
        "form_filtros_slotting_almacen",
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
                    "almacen_aplicado_meses"
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
                    "almacen_aplicado_caliente"
                ]
            ),
        )
        dias_intermedio = columnas[2].number_input(
            "Días intermedio",
            min_value=1,
            max_value=30,
            value=int(
                st.session_state[
                    "almacen_aplicado_intermedio"
                ]
            ),
        )
        dias_frio = columnas[3].number_input(
            "Días frío",
            min_value=1,
            max_value=20,
            value=int(
                st.session_state[
                    "almacen_aplicado_frio"
                ]
            ),
        )

        resumen_base, detalle_base, pasillos_base, metadata = (
            construir_analisis_almacen(
                tabla_articulos,
                tabla_volumetria,
                tabla_max_min,
                tabla_stock,
                tabla_ubicaciones,
                historico,
                int(
                    st.session_state[
                        "almacen_aplicado_meses"
                    ]
                ),
                int(
                    st.session_state[
                        "almacen_aplicado_caliente"
                    ]
                ),
                int(
                    st.session_state[
                        "almacen_aplicado_intermedio"
                    ]
                ),
                int(
                    st.session_state[
                        "almacen_aplicado_frio"
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
                    "almacen_aplicado_sector"
                ]
                if valor in sectores
            ],
        )
        rotacion = columnas[5].multiselect(
            "Rotación",
            ORDEN_ROTACION,
            default=st.session_state[
                "almacen_aplicado_rotacion"
            ],
        )
        busqueda = columnas[6].text_input(
            "Buscar producto",
            value=st.session_state[
                "almacen_aplicado_busqueda"
            ],
            placeholder="Código o descripción...",
        )
        ver_repuestos = columnas[7].toggle(
            "Ver repuestos",
            value=bool(
                st.session_state[
                    "almacen_aplicado_repuestos"
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
            "almacen_codigo_detalle",
            None,
        )
        st.rerun()

    if aplicar_filtros:
        st.session_state[
            "almacen_aplicado_meses"
        ] = int(meses)
        st.session_state[
            "almacen_aplicado_caliente"
        ] = int(dias_caliente)
        st.session_state[
            "almacen_aplicado_intermedio"
        ] = int(dias_intermedio)
        st.session_state[
            "almacen_aplicado_frio"
        ] = int(dias_frio)
        st.session_state[
            "almacen_aplicado_sector"
        ] = sector
        st.session_state[
            "almacen_aplicado_rotacion"
        ] = rotacion
        st.session_state[
            "almacen_aplicado_busqueda"
        ] = busqueda
        st.session_state[
            "almacen_aplicado_repuestos"
        ] = bool(ver_repuestos)
        st.session_state.pop(
            "almacen_codigo_detalle",
            None,
        )
        st.rerun()

    resumen, detalle, resumen_pasillos, metadata = (
        construir_analisis_almacen(
            tabla_articulos,
            tabla_volumetria,
            tabla_max_min,
            tabla_stock,
            tabla_ubicaciones,
            historico,
            int(
                st.session_state[
                    "almacen_aplicado_meses"
                ]
            ),
            int(
                st.session_state[
                    "almacen_aplicado_caliente"
                ]
            ),
            int(
                st.session_state[
                    "almacen_aplicado_intermedio"
                ]
            ),
            int(
                st.session_state[
                    "almacen_aplicado_frio"
                ]
            ),
        )
    )

    vista = resumen.copy()
    detalle_filtrado = detalle.copy()

    if not st.session_state[
        "almacen_aplicado_repuestos"
    ]:
        vista = _excluir_repuestos(vista)
        detalle_filtrado = _excluir_repuestos(
            detalle_filtrado
        )

    sectores_aplicados = st.session_state[
        "almacen_aplicado_sector"
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
        "almacen_aplicado_rotacion"
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
        "almacen_aplicado_busqueda"
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

    stock_total = pd.to_numeric(
        detalle_filtrado.get(
            "StockFisico",
            0,
        ),
        errors="coerce",
    ).fillna(0).sum()
    stock_cercano = (
        pd.to_numeric(
            detalle_filtrado.get(
                "StockCercano",
                0,
            ),
            errors="coerce",
        ).fillna(0).sum()
    )
    stock_fuera = (
        pd.to_numeric(
            detalle_filtrado.get(
                "StockFueraBloque",
                0,
            ),
            errors="coerce",
        ).fillna(0).sum()
    )

    kpis = st.columns(7)
    kpis[0].metric(
        "📦 SKU en almacén",
        formato_entero(
            vista["ArticuloCodigo"].nunique()
        ),
    )
    kpis[1].metric(
        "🧭 Dispersos",
        formato_entero(
            pd.to_numeric(
                vista.get(
                    "CantidadPasillos",
                    0,
                ),
                errors="coerce",
            ).fillna(0).ge(3).sum()
        ),
    )
    kpis[2].metric(
        "🔥 Calientes lejos",
        formato_entero(
            (
                vista["CategoriaRotacion"]
                .eq("🔥 Caliente")
                & pd.to_numeric(
                    vista.get(
                        "DistanciaPromedioPonderada",
                        0,
                    ),
                    errors="coerce",
                ).fillna(0).ge(4)
            ).sum()
        ),
    )
    kpis[3].metric(
        "🟢 Stock cercano",
        (
            f"{stock_cercano / stock_total * 100:.1f}%"
            if stock_total > 0
            else "—"
        ),
    )
    kpis[4].metric(
        "🔴 Fuera de bloque",
        (
            f"{stock_fuera / stock_total * 100:.1f}%"
            if stock_total > 0
            else "—"
        ),
    )
    kpis[5].metric(
        "🚨 Críticos",
        formato_entero(
            vista.get(
                "EstadoDistribucion",
                pd.Series(dtype=str),
            )
            .fillna("")
            .isin(
                [
                    "Alta dispersión",
                    "Stock muy lejano",
                    "Mayoría fuera de bloque",
                ]
            )
            .sum()
        ),
    )
    kpis[6].metric(
        "🧱 Pallets",
        formato_entero(
            pd.to_numeric(
                vista.get(
                    "CantidadPalletsAlmacen",
                    0,
                ),
                errors="coerce",
            ).fillna(0).sum()
        ),
    )

    mapa, ranking = st.columns(
        [1.25, 1]
    )

    with mapa:
        st.markdown(
            "#### Diagnóstico por pasillo"
        )
        if (
            resumen_pasillos is None
            or resumen_pasillos.empty
        ):
            st.info(
                "No se pudo construir el resumen por pasillos."
            )
        else:
            pasillos = resumen_pasillos.copy()
            pasillos["PasilloTexto"] = (
                "Pasillo "
                + pd.to_numeric(
                    pasillos["Pasillo"],
                    errors="coerce",
                )
                .fillna(0)
                .astype(int)
                .astype(str)
            )
            figura = px.bar(
                pasillos.sort_values("Pasillo"),
                x="PasilloTexto",
                y="StockTotal",
                color="EstadoPasillo",
                text="StockTotal",
                color_discrete_map={
                    "Correcto": "#16A34A",
                    "Revisar": "#F59E0B",
                    "Crítico": "#DC2626",
                },
                labels={
                    "PasilloTexto": "",
                    "StockTotal": "Unidades",
                    "EstadoPasillo": "",
                },
            )
            _render_figura(figura, 440)

    with ranking:
        st.markdown(
            "#### Prioridades de relocalización"
        )
        top = (
            vista.sort_values(
                "PrioridadDistribucion",
                ascending=False,
            )
            .head(15)
            .copy()
        )
        top["Producto"] = (
            top["ArticuloCodigo"]
            + " · "
            + top["ArticuloDescripcion"]
            .fillna("")
            .astype(str)
            .str.slice(0, 34)
        )
        figura_ranking = px.bar(
            top.sort_values(
                "PrioridadDistribucion"
            ),
            x="PrioridadDistribucion",
            y="Producto",
            orientation="h",
            color="CategoriaRotacion",
            text="PrioridadDistribucion",
            labels={
                "Producto": "",
                "PrioridadDistribucion":
                    "Prioridad",
                "CategoriaRotacion": "",
            },
        )
        _render_figura(
            figura_ranking,
            440,
        )

    st.divider()

    encabezado, descarga = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    encabezado.markdown(
        "### Tabla resumen de Almacén"
    )
    encabezado.caption(
        "Resume dónde está distribuido cada SKU y qué tan lejos "
        "se encuentra de su picking."
    )
    descarga.download_button(
        "⬇️ Descargar resumen",
        data=dataframe_a_csv(vista),
        file_name="resumen_slotting_almacen.csv",
        mime="text/csv",
        width="stretch",
    )

    st.dataframe(
        dataframe_para_streamlit(vista),
        hide_index=True,
        width="stretch",
        height=480,
        column_config={
            "PrioridadDistribucion":
                st.column_config.ProgressColumn(
                    "Prioridad",
                    min_value=0,
                    max_value=100,
                    format="%.0f",
                ),
            "ArticuloDescripcion":
                st.column_config.TextColumn(
                    "Descripción",
                    width="large",
                ),
            "CantidadPalletsAlmacen":
                st.column_config.NumberColumn(
                    "Pallets",
                    format="%.0f",
                ),
            "DistanciaPromedioPonderada":
                st.column_config.NumberColumn(
                    "Distancia promedio",
                    format="%.1f",
                ),
            "StockCercanoPct":
                st.column_config.ProgressColumn(
                    "Stock cercano",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
                ),
            "StockFueraBloquePct":
                st.column_config.ProgressColumn(
                    "Fuera de bloque",
                    min_value=0,
                    max_value=100,
                    format="%.1f%%",
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
        key="almacen_selector_detalle",
    )
    ver_detalle = boton.button(
        "🔎 Ver detalle",
        type="primary",
        width="stretch",
        key="almacen_boton_detalle",
    )

    if ver_detalle:
        st.session_state[
            "almacen_codigo_detalle"
        ] = mapa_codigo[etiqueta]

    codigo_detalle = st.session_state.get(
        "almacen_codigo_detalle"
    )

    if codigo_detalle:
        detalle_articulo = obtener_detalle_almacen(
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
                height=280,
            )
