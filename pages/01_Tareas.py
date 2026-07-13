from config import *

import plotly.graph_objects as go

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

from models.pedidos import (
    construir_tabla_pedidos
)

from models.tareas import (
    construir_tabla_tareas,
    obtener_resumen_operativo,
    obtener_tabla_operativa,
    obtener_avance_despachos
)

import streamlit as st

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(
    page_title="Gestión de Tareas",
    page_icon="📋",
    layout="wide"
)

# =====================================================
# CARGA DE DATOS
# =====================================================

df_tareas = leer_archivo(
    CARPETA_DATOS,
    "Informe Tareas",
    cache=False
)

df_pedidos = leer_archivo(
    CARPETA_DATOS,
    "Pedidos DIGIP",
    cache=False
)

df_detalle = leer_archivo(
    CARPETA_DATOS,
    "Detalle Pendientes",
    cache=False
)

df_clientes = leer_archivo(
    CARPETA_DATOS,
    "Maestro Clientes",
    cache=True
)

df_articulos = leer_archivo(
    CARPETA_DATOS,
    "Maestro Articulos",
    cache=True
)

tabla_pedidos = construir_tabla_pedidos(

    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes

)

# =====================================================
# KPIs PEDIDOS
# =====================================================

pedidos_pendientes = len(tabla_pedidos)

unidades_pendientes = int(

    tabla_pedidos["TotalUnidades"]

    .fillna(0)

    .sum()

)


# =====================================================
# TABLA OPERATIVA
# =====================================================

tabla_tareas = construir_tabla_tareas(

    df_tareas,
    df_pedidos,
    df_clientes

)

tabla_operativa = obtener_tabla_operativa(
    tabla_tareas
)
avance_despachos = obtener_avance_despachos(
    tabla_tareas
)

# =====================================================
# UNIDADES POR PREPARACION
# =====================================================

unidades_preparacion = tabla_pedidos[

    [

        "PreparacionID",

        "TotalUnidades"

    ]

].copy()

resumen = obtener_resumen_operativo(
    tabla_tareas,
    df_pedidos
)
# =====================================================
# UNIDADES CARROS
# =====================================================

unidades_preparacion = tabla_pedidos[

    [

        "PreparacionID",
        "TotalUnidades"

    ]

].copy()

tareas_unidades = tabla_tareas.merge(

    unidades_preparacion,

    left_on="Preparacion",

    right_on="PreparacionID",

    how="left"

)

# -----------------------------------------------------
# CARROS EN CURSO
# -----------------------------------------------------

unidades_carros_curso = (

    tareas_unidades[

        tareas_unidades["Categoria"] == "En Curso"

    ]

    .drop_duplicates("Preparacion")

    ["TotalUnidades"]

    .fillna(0)

    .sum()

)

# -----------------------------------------------------
# CARROS FINALIZADOS
# -----------------------------------------------------

unidades_carros_finalizados = (

    tareas_unidades[

        tareas_unidades["Categoria"] == "Finalizado"

    ]

    .drop_duplicates("Preparacion")

    ["TotalUnidades"]

    .fillna(0)

    .sum()

)


# =====================================================
# CABECERA
# =====================================================

st.title("📋 Gestión de Tareas")

st.caption("Centro de Control Operativo")

st.markdown("---")

# =====================================================
# RESUMEN OPERATIVO
# =====================================================

st.subheader("📊 Resumen Operativo")

col1, col2, col3 = st.columns(3)

# ---------------------------------------
# PEDIDOS PENDIENTES
# ---------------------------------------

with col1:

    st.metric(

    "📦 Pedidos Pendientes",

    pedidos_pendientes,

    delta=f"{unidades_pendientes:,} Unidades".replace(",", ".")

)
# ---------------------------------------
# CARROS EN CURSO
# ---------------------------------------

with col2:

    st.metric(

    "🛒 Carros en Curso",

    resumen["CarrosEnCurso"],

    delta=f"{int(unidades_carros_curso):,} Unidades".replace(",", ".")

)
    
# ---------------------------------------
# CARROS FINALIZADOS
# ---------------------------------------

with col3:

    st.metric(

        "✅ Carros Finalizados",

        resumen["CarrosFinalizados"]

    )
# =====================================================
# GRÁFICOS
# =====================================================

# ---------------------------------------
# GRAFICO AVANCE DESPACHOS
# ---------------------------------------

st.subheader("📈 Indicadores Operativos")

col1, col2, col3 = st.columns(3)

with col1:

    st.caption("📦 Avance de Despachos")

    cols = st.columns(3)

    for i, (_, fila) in enumerate(avance_despachos.iterrows()):

        with cols[i % 3]:

            avance = int(fila["Avance"])
            cerrados = int(fila["PreparacionesFinalizadas"])
            total = int(fila["TotalPreparaciones"])

            if avance <= 30:
                color = "#D32F2F"

            elif avance <= 70:
                color = "#F57C00"

            else:
                color = "#2E7D32"

            fig = go.Figure()

            fig.add_trace(

                go.Pie(

                    values=[

                        avance,

                        max(100 - avance, 0)

                    ],

                    hole=0.72,

                    sort=False,

                    direction="clockwise",

                    textinfo="none",

                    showlegend=False,

                    marker=dict(

                        colors=[

                            color,

                            "#3A3A3A"

                        ],

                        line=dict(

                            color="#202020",

                            width=2

                        )

                    )

                )

            )

            fig.update_layout(

                annotations=[

                    dict(

                        text=f"<b>{avance}%</b>",

                        x=0.5,

                        y=0.55,

                        showarrow=False,

                        font=dict(

                            size=22,

                            color="white"

                        )

                    ),

                    dict(

                        text=f"{cerrados} / {total}",

                        x=0.5,

                        y=0.36,

                        showarrow=False,

                        font=dict(

                            size=12,

                            color="#A0A0A0"

                        )

                    )

                ],

                title=dict(

    text=f"<b>{fila['Despacho']}</b>",

    x=0.5,

    xanchor="center",

    y=0.97,

    yanchor="top",

    font=dict(

        size=12,

        color="white"

    )

),

                height=180,

                margin=dict(

                    l=5,

                    r=5,

                    t=35,

                    b=5

                ),

                paper_bgcolor="rgba(0,0,0,0)",

                plot_bgcolor="rgba(0,0,0,0)",

                font=dict(color="white")

            )

            st.plotly_chart(

                fig,

                use_container_width=True,

                config={

                    "displayModeBar": False

                }

            )

with col2:

    st.info("Próximamente")

with col3:

    st.info("Próximamente")

st.markdown("---")


st.subheader("📋 Operación en Curso")

st.caption(
    f"{len(tabla_operativa)} registros"
)


def resaltar_carro(fila):

    estilos = [""] * len(fila)

    if fila["Prioridad"] == "🔴":

        indice = fila.index.get_loc("Carro")

        estilos[indice] = (
            "background-color:#C62828;"
            "color:white;"
            "font-weight:bold;"
        )

    return estilos

st.dataframe(

    tabla_operativa
        .style
        .apply(resaltar_carro, axis=1),

    use_container_width=True,

    hide_index=True,

    height=600

)

# =====================================================
# BOTÓN
# =====================================================

if st.button("🏠 Volver al Inicio"):

    st.switch_page("app.py")






