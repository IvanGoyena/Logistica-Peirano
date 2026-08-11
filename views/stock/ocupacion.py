import pandas as pd
import altair as alt
import streamlit as st

from utils.stock.helpers import dataframe_a_csv, dataframe_para_streamlit
from models.stock.ocupacion import resumir_ocupacion, mostrar_tarjeta_donut
from models.stock.mapa import mostrar_mapa_visual_deposito


def render(contexto: dict) -> None:
    tabla_maestro_ubicaciones = contexto["tabla_maestro_ubicaciones"]
    tabla_ocupacion = contexto["tabla_ocupacion"]
    tabla_stock_total_detallado = contexto.get(
        "tabla_stock_total_detallado",
        pd.DataFrame(),
    )
    resumen_global_calidad = contexto.get(
        "resumen_global_calidad",
        {},
    )

    st.subheader("🗺️ Ocupación del depósito")
    st.caption("Visión general de ocupación por sectores, pasillos y ubicaciones.")

    if tabla_maestro_ubicaciones.empty:
        st.error("No se encontró `Maestro Ubicaciones` dentro de la carpeta de datos.")
        return

    st.markdown(
        """
        <div style="display:flex;justify-content:flex-end;margin:0 0 .7rem 0;">
          <div style="border:1px solid #334155;border-radius:10px;padding:.55rem .8rem;">
            <div style="display:flex;gap:1rem;flex-wrap:wrap;font-size:.82rem">
              <span><b style="color:#3B82F6">●</b> Almacenamiento</span>
              <span><b style="color:#8B5CF6">●</b> Picking</span>
              <span><b style="color:#65A30D">●</b> Estanterías</span>
              <span><b style="color:#F59E0B">●</b> Pisos</span>
              <span><b style="color:#DC2626">●</b> Calidad / No apto</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- ALMACENAMIENTO ----------------
    st.markdown("### 🏭 ALMACENAMIENTO")
    st.markdown("<hr style='border-color:#2563EB;margin-top:-.55rem'>", unsafe_allow_html=True)
    fila_almacen = st.columns(4)
    tarjetas_almacen = [
        ("General", "Global", "#3B82F6", "#DBEAFE", "🏭"),
        ("Almacén Rack", "Almacén", "#3B82F6", "#DBEAFE", "🏗️"),
        ("Pasillo", "Pasillo", "#3B82F6", "#DBEAFE", "🚶"),
        ("Estanterías", "Estanterías", "#65A30D", "#DCFCE7", "🪜"),
    ]
    for indice, (titulo, grupo, color, libre, icono) in enumerate(tarjetas_almacen):
        with fila_almacen[indice]:
            mostrar_tarjeta_donut(
                titulo,
                resumir_ocupacion(tabla_ocupacion, grupo),
                key=f"donut_almacen_{indice}",
                color_ocupado=color,
                color_libre=libre,
                icono=icono,
            )

    # ---------------- PICKING ----------------
    st.markdown("### 🛒 PICKING")
    st.markdown("<hr style='border-color:#7C3AED;margin-top:-.55rem'>", unsafe_allow_html=True)
    fila_picking = st.columns([1, 1, 1.25])
    with fila_picking[0]:
        mostrar_tarjeta_donut(
            "Picking Rack",
            resumir_ocupacion(tabla_ocupacion, "Picking Rack"),
            key="donut_picking_rack",
            color_ocupado="#8B5CF6",
            color_libre="#EDE9FE",
            icono="🛒",
        )
    with fila_picking[1]:
        mostrar_tarjeta_donut(
            "Cajones (Pasillo 20)",
            resumir_ocupacion(tabla_ocupacion, "Cajones"),
            key="donut_cajones",
            color_ocupado="#A855F7",
            color_libre="#F3E8FF",
            icono="🗃️",
        )
    with fila_picking[2]:
        with st.container(border=True):
            st.markdown("#### ℹ️ Sobre Picking")
            st.markdown(
                """
                **Picking Rack:** ubicaciones en racks tradicionales, divididas por áreas operativas.  
                **Cajones (Pasillo 20):** sistema independiente de almacenamiento en cajones.
                """
            )

    # ---------------- PISOS ----------------
    st.markdown("### 🟧 PISOS (CAPACIDAD EN PALLETS)")
    st.markdown("<hr style='border-color:#F59E0B;margin-top:-.55rem'>", unsafe_allow_html=True)
    fila_pisos = st.columns([1, 1, 1.25])
    with fila_pisos[0]:
        mostrar_tarjeta_donut(
            "Aceituna (Loza)",
            resumir_ocupacion(tabla_ocupacion, "Aceituna"),
            key="donut_aceituna",
            color_ocupado="#F59E0B",
            color_libre="#FFEDD5",
            icono="🫒",
        )
    with fila_pisos[1]:
        mostrar_tarjeta_donut(
            "Entrepiso",
            resumir_ocupacion(tabla_ocupacion, "Entrepiso"),
            key="donut_entrepiso",
            color_ocupado="#F59E0B",
            color_libre="#FFEDD5",
            icono="🏢",
        )
    with fila_pisos[2]:
        with st.container(border=True):
            st.markdown("#### ℹ️ Metodología de pisos")
            st.markdown(
                """
                **Ocupados:** cantidad de contenedores distintos almacenados.  
                **Capacidad:** pallets disponibles según el maestro.  
                **Libres:** capacidad menos contenedores ocupados.
                """
            )

    # ---------------- CALIDAD / NO APTO ----------------
    st.markdown(
        "### 🧪 CALIDAD Y REPROCESO"
    )
    st.markdown(
        "<hr style='border-color:#DC2626;margin-top:-.55rem'>",
        unsafe_allow_html=True,
    )

    resumen_calidad_global = {
        "capacidad": float(
            resumen_global_calidad.get(
                "capacidad_total",
                0,
            )
        ),
        "ocupado": float(
            resumen_global_calidad.get(
                "ocupado_total",
                0,
            )
        ),
        "libre": float(
            resumen_global_calidad.get(
                "libre_total",
                0,
            )
        ),
        "porcentaje": float(
            resumen_global_calidad.get(
                "porcentaje_total",
                0,
            )
        ),
        "ubicaciones": 0,
        "unidad": "contenedores",
    }

    calidad_resumen_col, calidad_info_col = (
        st.columns(
            [1, 2],
            vertical_alignment="top",
        )
    )

    with calidad_resumen_col:
        mostrar_tarjeta_donut(
            "Calidad consolidada",
            resumen_calidad_global,
            key="donut_calidad_global_ocupacion",
            color_ocupado="#DC2626",
            color_libre="#FEE2E2",
            icono="🧪",
        )

    with calidad_info_col:
        with st.container(
            border=True
        ):
            st.markdown(
                "#### ⚠️ Mercadería no apta para la venta"
            )
            st.markdown(
                """
                La ocupación consolidada incluye **Laboratorio**,
                **Mercadería de segunda**, **Reproceso pendiente**
                y **Racks de Calidad**.

                El análisis por condición, artículos, contenedores,
                antigüedad y detalle operativo se encuentra en la
                pestaña **🧪 Calidad y Reproceso**.
                """
            )

    # ---------------- DETALLES ----------------
    st.markdown("---")
    picking = tabla_ocupacion.loc[
        tabla_ocupacion["GrupoOcupacion"].eq("Picking")
        & tabla_ocupacion["Disponible"]
    ].copy()
    if not picking.empty:
        mascara_cajones = (
            picking["Pasillo"].astype("string").str.strip().str.lstrip("0").eq("20")
            | picking["Tercio"].astype("string").str.upper().str.strip().eq("CAJONES")
        )
        picking_rack = picking.loc[~mascara_cajones].copy()
        picking_rack["AreaAnalisis"] = picking_rack["Area"].astype("string").fillna("").replace("", "SIN ÁREA")
        detalle_area = (
            picking_rack.groupby("AreaAnalisis", dropna=False)
            .agg(Capacidad=("ClaveUbicacion", "nunique"), Ocupado=("Ocupada", "sum"))
            .reset_index().rename(columns={"AreaAnalisis": "Área"})
        )
        detalle_area["Libre"] = (detalle_area["Capacidad"] - detalle_area["Ocupado"]).clip(lower=0)
        detalle_area["% Ocupación"] = (
            detalle_area["Ocupado"].div(detalle_area["Capacidad"].replace(0, pd.NA)).mul(100).fillna(0)
        )
        detalle_area = detalle_area.sort_values("% Ocupación", ascending=False)

        col_detalle_1, col_detalle_2 = st.columns([1, 1.35])
        with col_detalle_1:
            st.markdown("#### 🛒 Picking por área (sin Cajones)")
            grafico_area = (
                alt.Chart(detalle_area)
                .mark_bar(cornerRadiusEnd=5, color="#8B5CF6")
                .encode(
                    y=alt.Y("Área:N", sort="-x", title=None),
                    x=alt.X("% Ocupación:Q", title="% de ocupación", scale=alt.Scale(domain=[0, 100])),
                    tooltip=[
                        alt.Tooltip("Área:N"),
                        alt.Tooltip("% Ocupación:Q", format=".1f"),
                        alt.Tooltip("Ocupado:Q", format=",.0f"),
                        alt.Tooltip("Libre:Q", format=",.0f"),
                        alt.Tooltip("Capacidad:Q", format=",.0f"),
                    ],
                ).properties(height=max(260, len(detalle_area) * 38))
            )
            st.altair_chart(grafico_area, width="stretch", key="grafico_picking_area_final")
            st.dataframe(
                dataframe_para_streamlit(detalle_area),
                hide_index=True,
                width="stretch",
                height=300,
                column_config={
                    "% Ocupación": st.column_config.ProgressColumn("% Ocupación", min_value=0, max_value=100, format="%.1f%%")
                },
            )

        with col_detalle_2:
            st.markdown("#### 📋 Resumen por grupo")
            filas_resumen = []
            for nombre, grupo, tipo in [
                ("Almacén Rack", "Almacén", "Ubicaciones"),
                ("Pasillo", "Pasillo", "Ubicaciones"),
                ("Picking Rack", "Picking Rack", "Ubicaciones"),
                ("Cajones (Pasillo 20)", "Cajones", "Ubicaciones"),
                ("Estanterías", "Estanterías", "Ubicaciones"),
                ("Aceituna (Loza)", "Aceituna", "Pallets"),
                ("Entrepiso", "Entrepiso", "Pallets"),
            ]:
                r = resumir_ocupacion(tabla_ocupacion, grupo)
                filas_resumen.append({
                    "Grupo": nombre,
                    "Tipo": tipo,
                    "Total": r["capacidad"],
                    "Ocupadas": r["ocupado"],
                    "Vacías / Libres": r["libre"],
                    "% Ocupación": r["porcentaje"],
                })
            filas_resumen.append({
                "Grupo": "Calidad y Reproceso",
                "Tipo": "Espacio consolidado",
                "Total": resumen_calidad_global["capacidad"],
                "Ocupadas": resumen_calidad_global["ocupado"],
                "Vacías / Libres": resumen_calidad_global["libre"],
                "% Ocupación": resumen_calidad_global["porcentaje"],
            })

            resumen_grupos = pd.DataFrame(filas_resumen)
            st.dataframe(
                dataframe_para_streamlit(resumen_grupos),
                hide_index=True,
                width="stretch",
                height=430,
                column_config={
                    "% Ocupación": st.column_config.ProgressColumn("% Ocupación", min_value=0, max_value=100, format="%.1f%%"),
                    "Total": st.column_config.NumberColumn(format="%.0f"),
                    "Ocupadas": st.column_config.NumberColumn(format="%.0f"),
                    "Vacías / Libres": st.column_config.NumberColumn(format="%.0f"),
                },
            )



    # ---------------- UBICACIONES VACÍAS DE ALMACÉN ----------------
    st.markdown("---")
    st.markdown("### 📍 Ubicaciones vacías de Almacén")
    st.caption(
        "Listado operativo de ubicaciones disponibles para guardado. "
        "Incluye ubicaciones de Almacén y Pasillo; "
        "Picking queda excluido de esta tabla y de la descarga."
    )

    ubicaciones_vacias = tabla_ocupacion.loc[
        tabla_ocupacion["GrupoOcupacion"].isin(
            ["Almacén", "Pasillo"]
        )
        & tabla_ocupacion["Disponible"].fillna(False)
        & ~tabla_ocupacion["Ocupada"].fillna(False)
    ].copy()

    if ubicaciones_vacias.empty:
        st.info(
            "No hay ubicaciones vacías disponibles en Almacén."
        )
    else:
        ubicaciones_vacias["Area"] = (
            ubicaciones_vacias["Area"]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        ubicaciones_vacias["Tercio"] = (
            ubicaciones_vacias["Tercio"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        areas_disponibles = sorted(
            valor
            for valor in ubicaciones_vacias[
                "Area"
            ].unique().tolist()
            if valor
        )
        pasillos_disponibles = sorted(
            valor
            for valor in ubicaciones_vacias[
                "Pasillo"
            ].fillna("")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
            if valor
        )
        tercios_disponibles = sorted(
            valor
            for valor in ubicaciones_vacias[
                "Tercio"
            ].unique().tolist()
            if valor
        )

        filtro_area, filtro_pasillo, filtro_tercio = (
            st.columns(3)
        )

        with filtro_area:
            areas_seleccionadas = st.multiselect(
                "Área",
                options=areas_disponibles,
                key="ocupacion_vacias_area",
                placeholder="Todas las áreas",
            )

        with filtro_pasillo:
            pasillos_seleccionados = st.multiselect(
                "Pasillo",
                options=pasillos_disponibles,
                key="ocupacion_vacias_pasillo",
                placeholder="Todos los pasillos",
            )

        with filtro_tercio:
            tercios_seleccionados = st.multiselect(
                "Tercio",
                options=tercios_disponibles,
                key="ocupacion_vacias_tercio",
                placeholder="Todos los tercios",
            )

        vista_vacias = ubicaciones_vacias.copy()

        if areas_seleccionadas:
            vista_vacias = vista_vacias.loc[
                vista_vacias["Area"].isin(
                    areas_seleccionadas
                )
            ].copy()

        if pasillos_seleccionados:
            vista_vacias = vista_vacias.loc[
                vista_vacias["Pasillo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .isin(pasillos_seleccionados)
            ].copy()

        if tercios_seleccionados:
            vista_vacias = vista_vacias.loc[
                vista_vacias["Tercio"].isin(
                    tercios_seleccionados
                )
            ].copy()

        columnas_vacias = [
            columna
            for columna in [
                "Area",
                "Tercio",
                "Pasillo",
                "Posicion",
                "Nivel",
                "CodigoVerificador",
                "Tipo",
                "ClaveUbicacion",
            ]
            if columna in vista_vacias.columns
        ]

        vista_vacias = (
            vista_vacias[
                columnas_vacias
            ]
            .drop_duplicates()
            .sort_values(
                [
                    columna
                    for columna in [
                        "Area",
                        "Tercio",
                        "Pasillo",
                        "Posicion",
                        "Nivel",
                    ]
                    if columna in columnas_vacias
                ],
                na_position="last",
            )
            .reset_index(drop=True)
        )

        total_vacias = len(vista_vacias)

        kpi_vacias, descarga_vacias = st.columns(
            [1, 3],
            vertical_alignment="bottom",
        )

        with kpi_vacias:
            st.metric(
                "Ubicaciones vacías",
                f"{total_vacias:,}".replace(",", "."),
            )

        with descarga_vacias:
            st.download_button(
                "⬇️ Descargar ubicaciones vacías",
                data=dataframe_a_csv(
                    vista_vacias
                ),
                file_name="Ubicaciones_Vacias_Almacen_y_Pasillo.csv",
                mime="text/csv",
                key="descargar_ubicaciones_vacias_almacen",
                width="stretch",
            )

        st.dataframe(
            dataframe_para_streamlit(
                vista_vacias
            ),
            hide_index=True,
            width="stretch",
            height=min(
                520,
                90 + max(
                    len(vista_vacias),
                    1,
                ) * 34,
            ),
            column_config={
                "Area": st.column_config.TextColumn(
                    "Área"
                ),
                "Tercio": st.column_config.TextColumn(
                    "Tercio"
                ),
                "Pasillo": st.column_config.TextColumn(
                    "Pasillo"
                ),
                "Posicion": st.column_config.TextColumn(
                    "Posición"
                ),
                "Nivel": st.column_config.TextColumn(
                    "Nivel"
                ),
                "CodigoVerificador":
                    st.column_config.TextColumn(
                        "Código verificador"
                    ),
                "ClaveUbicacion":
                    st.column_config.TextColumn(
                        "Ubicación"
                    ),
            },
        )

    # ---------------- MAPA VISUAL ----------------
    mostrar_mapa_visual_deposito(
        tabla_ocupacion,
        tabla_stock_total_detallado=tabla_stock_total_detallado,
    )

    st.caption("ℹ️ Los datos se actualizan según la última extracción del stock y el Maestro Ubicaciones.")

