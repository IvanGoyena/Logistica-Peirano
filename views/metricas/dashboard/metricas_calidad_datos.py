from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from utils.metricas.metricas_helpers import limitar_previsualizacion

def render(contexto: dict) -> None:
    datos = contexto["datos"]
    detalle_filtrado = contexto["detalle_filtrado"]
    df_calidad_enriquecimiento = contexto["df_calidad_enriquecimiento"]
    etl = contexto["etl"]
    fuentes = contexto["fuentes"]
    tareas_filtradas = contexto["tareas_filtradas"]
    # ==========================================================
    # DATOS, TABLAS Y CONTROLES TÉCNICOS
    # ==========================================================

    st.divider()

    mostrar_datos_tecnicos = st.toggle(
        "🧪 Cargar datos, tablas y controles de calidad",
        value=False,
        help=(
            "Activalo únicamente cuando necesites revisar "
            "las tablas detalladas. Esto evita procesar miles "
            "de registros durante la navegación normal."
        ),
    )

    if mostrar_datos_tecnicos:

        st.caption(
            "El tablero conserva todos los registros. Los datos sin clasificación "
            "se muestran como SIN FAMILIA o SIN SECTORIZACIÓN para facilitar su control."
        )

        st.caption(
            "Esta sección conserva la información técnica utilizada "
            "para validar el tablero, revisar los cruces y analizar "
            "los datos a nivel de registro."
        )

        (
            sub_tareas,
            sub_detalle,
            sub_resumen,
            sub_calidad,
            sub_cobertura,
            sub_crudos,
        ) = st.tabs(
            [
                "📋 Tareas enriquecidas",
                "📦 Detalle enriquecido",
                "📊 Resúmenes",
                "🧪 Calidad ETL",
                "📚 Cobertura de maestros",
                "🗂️ Fuentes crudas",
            ]
        )

        # ------------------------------------------------------
        # TAREAS ENRIQUECIDAS
        # ------------------------------------------------------

        with sub_tareas:

            st.markdown(
                "#### Una fila por tarea"
            )

            st.caption(
                f"{len(tareas_filtradas):,} tareas según los filtros "
                "aplicados."
            )

            columnas_tareas_tabla = [
                "Proceso",
                "TareaId",
                "Pedido",
                "PedidoOriginalProceso",
                "Fecha",
                "Usuario",
                "Tipo",
                "UnidadesAnalisis",
                "ArticulosDetalle",
                "LineasDetalle",
                "FamiliaPrincipal",
                "Familia2Principal",
                "SectorizacionPrincipal",
                "VolumenTotalM3",
                "PesoTotalKg",
                "TiempoEstimadoSegundos",
                "TiempoRealSegundos",
                "UnidadesPorHora",
                "ArticulosPorHora",
                "LineasPorHora",
                "M3PorHora",
                "KgPorHora",
                "SegundosPorUnidad",
                "SegundosPorArticulo",
                "NivelComplejidad",
                "CoberturaMaestroPct",
                "CoberturaVolumetriaPct",
                "ArchivoOrigen",
            ]

            columnas_tareas_tabla = [
                columna
                for columna in columnas_tareas_tabla
                if columna in tareas_filtradas.columns
            ]

            st.dataframe(
                limitar_previsualizacion(
                    tareas_filtradas[
                        columnas_tareas_tabla
                    ],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
                column_config={
                    "VolumenTotalM3": (
                        st.column_config.NumberColumn(
                            "Volumen total m³",
                            format="%.3f",
                        )
                    ),
                    "PesoTotalKg": (
                        st.column_config.NumberColumn(
                            "Peso total kg",
                            format="%.2f",
                        )
                    ),
                    "UnidadesPorHora": (
                        st.column_config.NumberColumn(
                            "Unidades/hora",
                            format="%.2f",
                        )
                    ),
                    "M3PorHora": (
                        st.column_config.NumberColumn(
                            "m³/hora",
                            format="%.3f",
                        )
                    ),
                    "KgPorHora": (
                        st.column_config.NumberColumn(
                            "kg/hora",
                            format="%.2f",
                        )
                    ),
                    "CoberturaMaestroPct": (
                        st.column_config.ProgressColumn(
                            "Cobertura artículos",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        )
                    ),
                    "CoberturaVolumetriaPct": (
                        st.column_config.ProgressColumn(
                            "Cobertura volumetría",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        )
                    ),
                },
            )

        # ------------------------------------------------------
        # DETALLE ENRIQUECIDO
        # ------------------------------------------------------

        with sub_detalle:

            st.markdown(
                "#### Una fila por artículo dentro de cada tarea"
            )

            st.caption(
                f"{len(detalle_filtrado):,} líneas según los filtros "
                "aplicados."
            )

            columnas_detalle_tabla = [
                "Proceso",
                "TareaId",
                "Pedido",
                "PedidoOriginalProceso",
                "Fecha",
                "Usuario",
                "CodigoArticulo",
                "DescripcionFinal",
                "UnidadesDetalle",
                "FamiliaFinal",
                "Familia2",
                "Rubro",
                "Marca",
                "Origen",
                "Gama",
                "Sector",
                "Sectorizacion",
                "Ubicacion",
                "VolumenM3",
                "PesoKg",
                "VolumenLineaM3",
                "PesoLineaKg",
                "SegundosEnPickear",
                "SegundosPorUnidadLinea",
                "TieneMaestroArticulo",
                "TieneVolumetria",
                "ArchivoOrigen",
            ]

            columnas_detalle_tabla = [
                columna
                for columna in columnas_detalle_tabla
                if columna in detalle_filtrado.columns
            ]

            st.dataframe(
                limitar_previsualizacion(
                    detalle_filtrado[
                        columnas_detalle_tabla
                    ],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
                column_config={
                    "VolumenM3": (
                        st.column_config.NumberColumn(
                            "Volumen unitario m³",
                            format="%.6f",
                        )
                    ),
                    "PesoKg": (
                        st.column_config.NumberColumn(
                            "Peso unitario kg",
                            format="%.3f",
                        )
                    ),
                    "VolumenLineaM3": (
                        st.column_config.NumberColumn(
                            "Volumen línea m³",
                            format="%.6f",
                        )
                    ),
                    "PesoLineaKg": (
                        st.column_config.NumberColumn(
                            "Peso línea kg",
                            format="%.3f",
                        )
                    ),
                },
            )

        # ------------------------------------------------------
        # RESÚMENES TÉCNICOS
        # ------------------------------------------------------

        with sub_resumen:

            st.markdown(
                "#### Resumen por proceso"
            )

            resumen_tecnico_proceso = (
                tareas_filtradas
                .groupby(
                    "Proceso",
                    as_index=False,
                    dropna=False,
                )
                .agg(
                    Tareas=("ClaveTarea", "nunique"),
                    Usuarios=("Usuario", "nunique"),
                    Unidades=("UnidadesAnalisis", "sum"),
                    Articulos=("ArticulosDetalle", "sum"),
                    Lineas=("LineasDetalle", "sum"),
                    VolumenM3=("VolumenTotalM3", "sum"),
                    PesoKg=("PesoTotalKg", "sum"),
                    TiempoRealSegundos=(
                        "TiempoRealSegundos",
                        "sum",
                    ),
                )
            )

            resumen_tecnico_proceso["HorasReales"] = (
                resumen_tecnico_proceso[
                    "TiempoRealSegundos"
                ]
                / 3600
            ).round(2)

            resumen_tecnico_proceso["UnidadesHora"] = (
                resumen_tecnico_proceso["Unidades"]
                / resumen_tecnico_proceso[
                    "HorasReales"
                ].replace(0, np.nan)
            ).round(2)

            resumen_tecnico_proceso["M3Hora"] = (
                resumen_tecnico_proceso["VolumenM3"]
                / resumen_tecnico_proceso[
                    "HorasReales"
                ].replace(0, np.nan)
            ).round(3)

            st.dataframe(
                resumen_tecnico_proceso,
                width="stretch",
                hide_index=True,
            )

            st.markdown(
                "#### Resumen por familia principal"
            )

            resumen_tecnico_familia = (
                tareas_filtradas
                .assign(
                    FamiliaPrincipal=lambda tabla: (
                        tabla["FamiliaPrincipal"]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .replace("", "SIN FAMILIA")
                    )
                )
                .groupby(
                    [
                        "Proceso",
                        "FamiliaPrincipal",
                    ],
                    as_index=False,
                )
                .agg(
                    Tareas=("ClaveTarea", "nunique"),
                    Unidades=("UnidadesAnalisis", "sum"),
                    VolumenM3=("VolumenTotalM3", "sum"),
                    PesoKg=("PesoTotalKg", "sum"),
                    TiempoRealSegundos=(
                        "TiempoRealSegundos",
                        "sum",
                    ),
                )
                .sort_values(
                    [
                        "Proceso",
                        "Unidades",
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )
            )

            resumen_tecnico_familia["HorasReales"] = (
                resumen_tecnico_familia[
                    "TiempoRealSegundos"
                ]
                / 3600
            ).round(2)

            st.dataframe(
                resumen_tecnico_familia,
                width="stretch",
                hide_index=True,
            )

            st.markdown(
                "#### Resumen por nivel de complejidad"
            )

            resumen_tecnico_complejidad = (
                tareas_filtradas
                .groupby(
                    [
                        "Proceso",
                        "NivelComplejidad",
                    ],
                    as_index=False,
                    dropna=False,
                )
                .agg(
                    Tareas=("ClaveTarea", "nunique"),
                    Unidades=("UnidadesAnalisis", "sum"),
                    VolumenM3=("VolumenTotalM3", "sum"),
                    Horas=(
                        "TiempoRealSegundos",
                        lambda serie: serie.sum() / 3600,
                    ),
                )
            )

            st.dataframe(
                resumen_tecnico_complejidad,
                width="stretch",
                hide_index=True,
            )

        # ------------------------------------------------------
        # CALIDAD ETL
        # ------------------------------------------------------

        with sub_calidad:

            st.markdown(
                "#### Controles de limpieza y homologación"
            )

            st.dataframe(
                etl["calidad"],
                width="stretch",
                hide_index=True,
            )

            st.markdown(
                "#### Diferencias de unidades por tarea"
            )

            diferencias_unidades = (
                tareas_filtradas[
                    [
                        "Proceso",
                        "TareaId",
                        "UnidadesTarea",
                        "UnidadesDetalleTotal",
                        "UnidadesAnalisis",
                        "ArchivoOrigen",
                    ]
                ]
                .copy()
            )

            diferencias_unidades[
                "DiferenciaUnidades"
            ] = (
                pd.to_numeric(
                    diferencias_unidades[
                        "UnidadesTarea"
                    ],
                    errors="coerce",
                )
                .fillna(0)
                - pd.to_numeric(
                    diferencias_unidades[
                        "UnidadesDetalleTotal"
                    ],
                    errors="coerce",
                )
                .fillna(0)
            )

            diferencias_unidades = (
                diferencias_unidades[
                    diferencias_unidades[
                        "DiferenciaUnidades"
                    ].abs() > 0.001
                ]
                .sort_values(
                    "DiferenciaUnidades",
                    key=lambda serie: serie.abs(),
                    ascending=False,
                )
            )

            st.dataframe(
                diferencias_unidades,
                width="stretch",
                hide_index=True,
            )

        # ------------------------------------------------------
        # COBERTURA DE MAESTROS
        # ------------------------------------------------------

        with sub_cobertura:

            st.markdown(
                "#### Indicadores de cobertura"
            )

            st.dataframe(
                df_calidad_enriquecimiento,
                width="stretch",
                hide_index=True,
            )

            cobertura_col1, cobertura_col2 = (
                st.columns(2)
            )

            with cobertura_col1:

                st.markdown(
                    "#### Artículos sin Maestro Artículo"
                )

                sin_maestro = (
                    detalle_filtrado[
                        ~detalle_filtrado[
                            "TieneMaestroArticulo"
                        ]
                    ]
                    [
                        [
                            "CodigoArticulo",
                            "DescripcionArticulo",
                            "Proceso",
                            "ArchivoOrigen",
                        ]
                    ]
                    .drop_duplicates()
                    .sort_values(
                        "CodigoArticulo"
                    )
                )

                st.dataframe(
                    sin_maestro,
                    width="stretch",
                    hide_index=True,
                )

            with cobertura_col2:

                st.markdown(
                    "#### Artículos sin volumetría"
                )

                sin_volumetria = (
                    detalle_filtrado[
                        ~detalle_filtrado[
                            "TieneVolumetria"
                        ]
                    ]
                    [
                        [
                            "CodigoArticulo",
                            "DescripcionFinal",
                            "FamiliaFinal",
                            "Proceso",
                            "ArchivoOrigen",
                        ]
                    ]
                    .drop_duplicates()
                    .sort_values(
                        "CodigoArticulo"
                    )
                )

                st.dataframe(
                    sin_volumetria,
                    width="stretch",
                    hide_index=True,
                )

        # ------------------------------------------------------
        # FUENTES CRUDAS
        # ------------------------------------------------------

        with sub_crudos:

            (
                crudo_control,
                crudo_preparacion,
                crudo_articulos,
                crudo_volumetria,
            ) = st.tabs(
                [
                    "✅ Control",
                    "📦 Preparación",
                    "📚 Maestro Artículo",
                    "📐 Maestro Volumetría",
                ]
            )

            with crudo_control:

                st.caption(
                    f"{len(fuentes['control']):,} registros · "
                    f"{len(fuentes['control'].columns):,} columnas"
                )

                st.dataframe(
                    limitar_previsualizacion(
                        fuentes["control"],
                        limite=5000,
                    ),
                    width="stretch",
                    hide_index=True,
                )

            with crudo_preparacion:

                st.caption(
                    f"{len(fuentes['preparacion']):,} registros · "
                    f"{len(fuentes['preparacion'].columns):,} columnas"
                )

                st.dataframe(
                    limitar_previsualizacion(
                        fuentes["preparacion"],
                        limite=5000,
                    ),
                    width="stretch",
                    hide_index=True,
                )

            with crudo_articulos:

                st.caption(
                    f"{len(datos['df_articulos']):,} registros · "
                    f"{len(datos['df_articulos'].columns):,} columnas"
                )

                st.dataframe(
                    limitar_previsualizacion(
                        datos["df_articulos"],
                        limite=5000,
                    ),
                    width="stretch",
                    hide_index=True,
                )

            with crudo_volumetria:

                st.caption(
                    f"{len(datos['tabla_volumetria']):,} artículos"
                )

                st.dataframe(
                    limitar_previsualizacion(
                        datos["tabla_volumetria"],
                        limite=5000,
                    ),
                    width="stretch",
                    hide_index=True,
                )
