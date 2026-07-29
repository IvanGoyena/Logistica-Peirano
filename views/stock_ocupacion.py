import pandas as pd
import altair as alt
import streamlit as st

from utils.stock_helpers import dataframe_para_streamlit
from models.stock_ocupacion import resumir_ocupacion, mostrar_tarjeta_donut
from models.stock_mapa import mostrar_mapa_visual_deposito


def render(contexto: dict) -> None:
    tabla_maestro_ubicaciones = contexto["tabla_maestro_ubicaciones"]
    tabla_ocupacion = contexto["tabla_ocupacion"]

    st.subheader("🗺️ Ocupación del depósito")
    st.caption("Ocupación real por ubicación y capacidad operativa del depósito.")

    if tabla_maestro_ubicaciones.empty:
        st.error("No se encontró `Maestro Ubicaciones` dentro de la carpeta de datos.")
        return

    st.markdown(
        """
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;margin:0 0 1rem 0;">
          <div>
            <h2 style="margin:0">📊 Ocupación del depósito</h2>
            <div style="color:#94A3B8;margin-top:.2rem">Visión general de ocupación por sectores</div>
          </div>
          <div style="border:1px solid #334155;border-radius:10px;padding:.65rem .9rem;min-width:390px;">
            <div style="font-weight:700;margin-bottom:.35rem">Referencias de colores</div>
            <div style="display:flex;gap:1rem;flex-wrap:wrap;font-size:.82rem">
              <span><b style="color:#3B82F6">●</b> Almacenamiento</span>
              <span><b style="color:#8B5CF6">●</b> Picking</span>
              <span><b style="color:#65A30D">●</b> Estanterías</span>
              <span><b style="color:#F59E0B">●</b> Pisos</span>
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



    # ---------------- MAPA VISUAL ----------------
    mostrar_mapa_visual_deposito(tabla_ocupacion)

    st.caption("ℹ️ Los datos se actualizan según la última extracción del stock y el Maestro Ubicaciones.")

