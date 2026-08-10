from __future__ import annotations

import pandas as pd
import streamlit as st

from models.stock.pallets_parciales import construir_pallets_parciales
from utils.stock.helpers import dataframe_a_csv, dataframe_para_streamlit, formato_entero


@st.cache_data(
    max_entries=6,
    show_spinner="Analizando pallets parciales y destinos...",
)
def _construir_base(
    tabla_stock_detallado: pd.DataFrame,
    tabla_max_min: pd.DataFrame,
    tabla_maestro_ubicaciones: pd.DataFrame,
    umbral_parcial_pct: float,
    areas_incluidas: tuple[str, ...],
) -> tuple[pd.DataFrame, dict]:
    return construir_pallets_parciales(
        tabla_stock_detallado=tabla_stock_detallado,
        tabla_max_min=tabla_max_min,
        tabla_maestro_ubicaciones=tabla_maestro_ubicaciones,
        umbral_parcial_pct=umbral_parcial_pct,
        areas_incluidas=areas_incluidas,
    )


def _metricas(tabla: pd.DataFrame, metadata: dict) -> None:
    columnas = st.columns(6)
    columnas[0].metric("Pallets analizados", formato_entero(metadata.get("pallets_analizados", 0)))
    columnas[1].metric("Candidatos", formato_entero(metadata.get("pallets_candidatos", 0)))
    columnas[2].metric("Liberables", formato_entero(metadata.get("pallets_liberables", 0)))
    columnas[3].metric("Pallets mixtos", formato_entero(metadata.get("pallets_mixtos", 0)))
    columnas[4].metric("Unid. a Picking", formato_entero(metadata.get("unidades_a_picking", 0)))
    columnas[5].metric("Unid. a unificar", formato_entero(metadata.get("unidades_a_unificar", 0)))


def render(contexto: dict) -> None:
    st.markdown("### ♻️ Consolidación de pallets parciales")
    st.caption(
        "Detecta pallets con remanentes fuera de Picking y propone un destino operativo: "
        "reponer Picking, consolidar con otro pallet o revisar pallets mixtos."
    )

    tabla_stock = contexto.get("tabla_stock_detallado", pd.DataFrame())
    tabla_max_min = contexto.get("tabla_max_min", pd.DataFrame())
    tabla_ubicaciones = contexto.get("tabla_maestro_ubicaciones", pd.DataFrame())

    if tabla_stock.empty:
        st.warning("No hay Stock detallado disponible para analizar.")
        return

    with st.expander("ℹ️ Cómo se decide la acción", expanded=False):
        st.markdown(
            """
- **Estándar físico:** cuando el mínimo es mayor a 0, se interpreta como las unidades de **1 pallet**. El máximo define cuántos pallets físicos admite esa ubicación.
- **Llevar a Picking - prioridad:** Picking está debajo del mínimo y el pallet completo entra sin superar el máximo.
- **Llevar a Picking:** el pallet completo puede absorberse hasta el máximo configurado.
- **Completar Picking + consolidar remanente:** una parte va a Picking y el sobrante se direcciona a otro pallet del mismo artículo.
- **Unificar con otro pallet:** Picking no necesita reposición, pero otro pallet puede absorber todo el remanente.
- **Consolidar parcialmente:** otro pallet puede absorber parte del remanente, aunque no se libera por completo el origen.
- **Revisar pallet mixto:** el mismo contenedor tiene más de un código y debe separarse antes de moverlo.
            """
        )

    # Áreas disponibles directamente desde Stock Detallado. El filtro se aplica ANTES
    # de calcular KPIs y candidatos, para que las áreas excluidas no contaminen el análisis.
    col_area_stock = None
    for candidato in ["AreaDescripcion", "Area", "Área"]:
        if candidato in tabla_stock.columns:
            col_area_stock = candidato
            break
    areas_disponibles = []
    if col_area_stock is not None:
        areas_disponibles = sorted(
            tabla_stock[col_area_stock]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .loc[lambda s: s.ne("") & ~s.str.contains(r"RECEPC|CALIDAD|LABORATOR|NO APTO", regex=True, na=False)]
            .unique()
            .tolist()
        )

    col_umbral, col_areas, col_info = st.columns([1, 2, 2], vertical_alignment="bottom")
    umbral = col_umbral.slider(
        "Máximo % para considerar pallet parcial",
        min_value=20,
        max_value=100,
        value=80,
        step=5,
        key="almacen_pallets_umbral",
        help=(
            "Se compara la cantidad del contenedor contra las unidades por pallet configuradas. "
            "Cuando existe mínimo de Picking, ese mínimo se toma como tamaño físico de 1 pallet."
        ),
    )
    areas_analisis = col_areas.multiselect(
        "Áreas a analizar",
        options=areas_disponibles,
        default=areas_disponibles,
        key="almacen_pallets_areas_analisis",
        help="Solo estas áreas participan del análisis, los KPIs y la descarga.",
    )
    col_info.caption(
        "Regla física: Mínimo Picking = unidades de 1 pallet. Ej.: mín. 150 / máx. 300 = "
        "2 pallets físicos de 150 u.; mín. 200 / máx. 600 = 3 pallets de 200 u."
    )

    base, metadata = _construir_base(
        tabla_stock,
        tabla_max_min,
        tabla_ubicaciones,
        float(umbral),
        tuple(areas_analisis),
    )

    _metricas(base, metadata)

    if base.empty:
        st.success("No se detectaron pallets parciales con las reglas actuales.")
        return

    st.divider()

    acciones = sorted(base["AccionSugerida"].dropna().astype(str).unique().tolist())
    areas = sorted(base["AreaOrigen"].dropna().astype(str).loc[lambda s: s.ne("")].unique().tolist())

    with st.form("form_pallets_parciales", clear_on_submit=False, border=True):
        c1, c2, c3, c4 = st.columns([1.45, 1.1, 1.4, 0.75])
        filtro_accion = c1.multiselect(
            "Acción",
            options=acciones,
            default=[],
            key="palletes_filtro_accion_form",
        )
        filtro_area = c2.multiselect(
            "Área origen",
            options=areas,
            default=[],
            key="palletes_filtro_area_form",
        )
        busqueda = c3.text_input(
            "Artículo / contenedor / ubicación",
            value="",
            placeholder="Ej.: 01-010, 805260..., ALM-017...",
            key="palletes_busqueda_form",
        )
        solo_liberables = c4.checkbox(
            "Solo liberables",
            value=False,
            key="palletes_liberables_form",
        )

        b1, b2, _ = st.columns([1, 1, 4])
        aplicar = b1.form_submit_button("✅ Aplicar filtros", type="primary", width="stretch")
        limpiar = b2.form_submit_button("🧹 Quitar filtros", width="stretch")

    if limpiar:
        st.session_state["palletes_filtros_aplicados"] = {
            "accion": [], "area": [], "busqueda": "", "liberables": False
        }
    elif aplicar or "palletes_filtros_aplicados" not in st.session_state:
        st.session_state["palletes_filtros_aplicados"] = {
            "accion": filtro_accion,
            "area": filtro_area,
            "busqueda": busqueda,
            "liberables": solo_liberables,
        }

    filtros = st.session_state.get("palletes_filtros_aplicados", {})
    vista = base.copy()

    if filtros.get("accion"):
        vista = vista.loc[vista["AccionSugerida"].isin(filtros["accion"])].copy()
    if filtros.get("area"):
        vista = vista.loc[vista["AreaOrigen"].isin(filtros["area"])].copy()
    if filtros.get("liberables"):
        vista = vista.loc[vista["PalletLiberable"].fillna(False)].copy()
    texto = str(filtros.get("busqueda", "") or "").strip().lower()
    if texto:
        columnas_busqueda = [
            "ArticuloCodigo", "ArticuloDescripcion", "ContenedorOrigen",
            "UbicacionOrigen", "UbicacionPickingDestino",
            "ContenedorDestinoUnificacion", "UbicacionDestinoUnificacion",
        ]
        mascara = pd.Series(False, index=vista.index)
        for columna in columnas_busqueda:
            if columna in vista.columns:
                mascara |= vista[columna].fillna("").astype(str).str.lower().str.contains(texto, regex=False)
        vista = vista.loc[mascara].copy()

    st.markdown("### 📋 Plan operativo de consolidación")
    st.caption(
        f"Mostrando {formato_entero(len(vista))} filas operativas sobre "
        f"{formato_entero(len(base))} candidatos detectados."
    )

    columnas_vista = [
        "AccionSugerida",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "ContenedorOrigen",
        "UbicacionOrigen",
        "AreaOrigen",
        "CantidadPallet",
        "EstandarPalletEstimado",
        "FuenteEstandarPallet",
        "PalletsFisicosPicking",
        "PorcentajePallet",
        "StockPickingActual",
        "StockMinimoPicking",
        "StockMaximoPicking",
        "FaltanteMinimo",
        "CapacidadHastaMaximo",
        "UnidadesAPicking",
        "UbicacionPickingDestino",
        "PlanDestinoPicking",
        "UnidadesAUnificar",
        "ContenedorDestinoUnificacion",
        "UbicacionDestinoUnificacion",
        "PalletLiberable",
        "ArticulosEnPallet",
        "Motivo",
    ]
    columnas_vista = [c for c in columnas_vista if c in vista.columns]

    st.dataframe(
        dataframe_para_streamlit(vista[columnas_vista]),
        hide_index=True,
        width="stretch",
        height=560,
        column_config={
            "CantidadPallet": st.column_config.NumberColumn("Unid. pallet", format="%.0f"),
            "EstandarPalletEstimado": st.column_config.NumberColumn("Estándar pallet", format="%.0f"),
            "FuenteEstandarPallet": st.column_config.TextColumn("Fuente estándar"),
            "PalletsFisicosPicking": st.column_config.NumberColumn("Pallets físicos Picking", format="%.1f"),
            "PorcentajePallet": st.column_config.ProgressColumn(
                "% pallet estimado", min_value=0, max_value=100, format="%.1f%%"
            ),
            "StockPickingActual": st.column_config.NumberColumn("Stock Picking", format="%.0f"),
            "StockMinimoPicking": st.column_config.NumberColumn("Mín. Picking", format="%.0f"),
            "StockMaximoPicking": st.column_config.NumberColumn("Máx. Picking", format="%.0f"),
            "FaltanteMinimo": st.column_config.NumberColumn("Faltante mín.", format="%.0f"),
            "CapacidadHastaMaximo": st.column_config.NumberColumn("Capacidad al máx.", format="%.0f"),
            "UnidadesAPicking": st.column_config.NumberColumn("A Picking", format="%.0f"),
            "UnidadesAUnificar": st.column_config.NumberColumn("A unificar", format="%.0f"),
            "PalletLiberable": st.column_config.CheckboxColumn("Libera pallet"),
            "Motivo": st.column_config.TextColumn("Motivo", width="large"),
            "PlanDestinoPicking": st.column_config.TextColumn("Plan destino Picking", width="large"),
        },
    )

    st.download_button(
        "⬇️ Descargar plan de consolidación",
        data=dataframe_a_csv(vista),
        file_name="plan_consolidacion_pallets.csv",
        mime="text/csv",
        key="descargar_plan_consolidacion_pallets",
    )

    with st.expander("📊 Resumen por acción", expanded=False):
        resumen = (
            base.groupby("AccionSugerida", as_index=False)
            .agg(
                Pallets=("ContenedorOrigen", "nunique"),
                Unidades=("CantidadPallet", "sum"),
                Liberables=("PalletLiberable", "sum"),
                UnidadesAPicking=("UnidadesAPicking", "sum"),
                UnidadesAUnificar=("UnidadesAUnificar", "sum"),
            )
            .sort_values("Pallets", ascending=False)
        )
        st.dataframe(dataframe_para_streamlit(resumen), hide_index=True, width="stretch")
