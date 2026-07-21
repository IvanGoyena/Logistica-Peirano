import streamlit as st


from utils.autenticacion import requerir_roles


requerir_roles(
    "admin",
)

import pandas as pd

from config import CARPETA_DATOS
from utils.leer_datos import leer_archivo

from models.metricas import construir_fuentes_metricas
from models.limpieza_metricas import ejecutar_etl_metricas
from models.volumetria import construir_tabla_volumetria
from models.enriquecimiento_metricas import ejecutar_enriquecimiento_metricas
from models.auditoria_etl import ejecutar_auditoria_etl


st.set_page_config(
    page_title="Auditoría ETL",
    page_icon="🧪",
    layout="wide",
)


@st.cache_data(
    show_spinner="Ejecutando auditoría ETL...",
    max_entries=1,
)
def cargar_auditoria():

    fuentes = construir_fuentes_metricas(
        CARPETA_DATOS
    )

    etl = ejecutar_etl_metricas(
        df_control=fuentes["control"],
        df_preparacion=fuentes["preparacion"],
    )

    df_articulos = leer_archivo(
        CARPETA_DATOS,
        "Maestro Articulo",
        cache=True,
    )

    df_volumetria = leer_archivo(
        CARPETA_DATOS,
        "Maestro Volumetria",
        cache=True,
    )

    tabla_volumetria = construir_tabla_volumetria(
        df_volumetria
    )

    enriquecimiento = ejecutar_enriquecimiento_metricas(
        df_tareas=etl["tareas"],
        df_detalle=etl["detalle"],
        df_articulos=df_articulos,
        tabla_volumetria=tabla_volumetria,
    )

    auditoria = ejecutar_auditoria_etl(
        df_control=fuentes["control"],
        df_preparacion=fuentes["preparacion"],
        tareas_limpias=etl["tareas"],
        tareas_enriquecidas=(
            enriquecimiento["tareas_enriquecidas"]
        ),
    )

    return auditoria


col_titulo, col_boton = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with col_titulo:

    st.title("🧪 Auditoría ETL")

    st.caption(
        "Comparación entre los reportes originales, "
        "la ETL limpia y la base enriquecida."
    )

with col_boton:

    actualizar = st.button(
        "🔄 Ejecutar",
        type="primary",
        width="stretch",
    )


if actualizar:

    cargar_auditoria.clear()
    st.rerun()


try:

    auditoria = cargar_auditoria()

except Exception as error:

    st.error(
        "No se pudo ejecutar la auditoría."
    )

    st.exception(error)
    st.stop()


df_diferencias = auditoria["diferencias_etl"]
df_preparacion = auditoria["auditoria_preparacion"]
df_control = auditoria["auditoria_control"]
df_etapas = auditoria["comparacion_etapas"]
df_consistencia_preparacion = auditoria[
    "consistencia_preparacion"
]
df_consistencia_control = auditoria[
    "consistencia_control"
]


# ==========================================================
# RESUMEN
# ==========================================================

total_comparaciones = len(
    df_diferencias
)

if (
    not df_diferencias.empty
    and "EstadoAuditoria"
    in df_diferencias.columns
):

    cantidad_ok = int(
        df_diferencias[
            "EstadoAuditoria"
        ].eq("OK").sum()
    )

    revisar_unidades = int(
        df_diferencias[
            "EstadoAuditoria"
        ].eq(
            "REVISAR UNIDADES"
        ).sum()
    )

else:

    cantidad_ok = 0
    revisar_unidades = 0


kpi1, kpi2, kpi3 = st.columns(3)

kpi1.metric(
    "Comparaciones",
    total_comparaciones,
)

kpi2.metric(
    "Resultados OK",
    cantidad_ok,
)

kpi3.metric(
    "Revisar unidades",
    revisar_unidades,
)


if revisar_unidades > 0:

    st.warning(
        "Hay diferencias de unidades entre el crudo "
        "y las etapas procesadas."
    )

elif total_comparaciones > 0:

    st.success(
        "No se detectaron diferencias de unidades "
        "en las comparaciones disponibles."
    )


st.divider()


# ==========================================================
# PESTAÑAS
# ==========================================================

(
    tab_diferencias,
    tab_preparacion,
    tab_control,
    tab_etapas,
    tab_consistencia,
) = st.tabs(
    [
        "🚨 Diferencias ETL",
        "📦 Preparación",
        "✅ Control",
        "🔄 Etapas",
        "🔍 Consistencia",
    ]
)


with tab_diferencias:

    st.subheader(
        "Diferencias contra el crudo"
    )

    if df_diferencias.empty:

        st.info(
            "No hay comparaciones disponibles."
        )

    else:

        procesos = sorted(
            df_diferencias[
                "Proceso"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        estados = sorted(
            df_diferencias[
                "EstadoAuditoria"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        filtro1, filtro2 = st.columns(2)

        with filtro1:

            filtro_proceso = st.multiselect(
                "Proceso",
                procesos,
                default=procesos,
            )

        with filtro2:

            filtro_estado = st.multiselect(
                "Estado",
                estados,
                default=estados,
            )

        tabla = df_diferencias.copy()

        if filtro_proceso:

            tabla = tabla[
                tabla["Proceso"].isin(
                    filtro_proceso
                )
            ]

        if filtro_estado:

            tabla = tabla[
                tabla[
                    "EstadoAuditoria"
                ].isin(
                    filtro_estado
                )
            ]

        st.dataframe(
            tabla,
            width="stretch",
            hide_index=True,
        )


with tab_preparacion:

    st.subheader(
        "Auditoría de Preparación"
    )

    st.info(
        "Separa Preparación y Reposición y compara "
        "las unidades de cabecera contra las del detalle."
    )

    st.dataframe(
        df_preparacion,
        width="stretch",
        hide_index=True,
    )

    if not df_preparacion.empty:

        columnas = [
            "UnidadesCabeceraPreparacion",
            "UnidadesDetallePreparacion",
            "UnidadesDetalleReposicion",
            "UnidadesDetalleTodosTipos",
        ]

        resumen = pd.DataFrame(
            [
                {
                    "Criterio": columna,
                    "Total": df_preparacion[
                        columna
                    ].sum(),
                }
                for columna in columnas
                if columna
                in df_preparacion.columns
            ]
        )

        st.markdown(
            "#### Totales por criterio"
        )

        st.dataframe(
            resumen,
            width="stretch",
            hide_index=True,
        )


with tab_control:

    st.subheader(
        "Auditoría de Control"
    )

    st.info(
        "Conserva la cantidad de filas del reporte, "
        "los contenedores únicos y las unidades."
    )

    st.dataframe(
        df_control,
        width="stretch",
        hide_index=True,
    )


with tab_etapas:

    st.subheader(
        "Crudo → ETL limpia → Base enriquecida"
    )

    st.dataframe(
        df_etapas,
        width="stretch",
        hide_index=True,
    )


with tab_consistencia:

    sub_preparacion, sub_control = st.tabs(
        [
            "Preparación",
            "Control",
        ]
    )

    with sub_preparacion:

        if df_consistencia_preparacion.empty:

            st.info(
                "No hay registros para revisar."
            )

        else:

            tabla_preparacion = (
                df_consistencia_preparacion[
                    df_consistencia_preparacion[
                        "CabeceraInconsistente"
                    ].fillna(False)
                    | df_consistencia_preparacion[
                        "DiferenciaUnidades"
                    ].fillna(0).abs().gt(0.001)
                ]
            )

            st.metric(
                "Tareas a revisar",
                len(tabla_preparacion),
            )

            st.dataframe(
                tabla_preparacion.head(5000),
                width="stretch"
                ,
                hide_index=True,
            )

    with sub_control:

        if df_consistencia_control.empty:

            st.info(
                "No hay registros para revisar."
            )

        else:

            tabla_control = (
                df_consistencia_control[
                    df_consistencia_control[
                        "CabeceraInconsistente"
                    ].fillna(False)
                    | df_consistencia_control[
                        "DiferenciaUnidades"
                    ].fillna(0).abs().gt(0.001)
                ]
            )

            st.metric(
                "Controles a revisar",
                len(tabla_control),
            )

            st.dataframe(
                tabla_control.head(5000),
                width="stretch",
                hide_index=True,
            )


with st.expander(
    "ℹ️ Cómo interpretar la auditoría",
    expanded=False,
):

    st.markdown(
        """
        - **CRUDO:** valor calculado directamente desde el WMS.
        - **ETL_LIMPIA:** resultado de `limpieza_metricas.py`.
        - **ENRIQUECIDA:** resultado luego de agregar artículos y volumetría.

        El enriquecimiento no debería modificar tareas,
        unidades ni tiempos. Solamente debe agregar atributos.
        """
    )
