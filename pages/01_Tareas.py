from config import *

import plotly.graph_objects as go

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
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
    CARPETA_TAREAS,
    "Informe Tareas"
)

df_pedidos = leer_archivo(
    CARPETA_PEDIDOS,
    "Pedidos DIGIP"
)

df_clientes = leer_archivo(
    CARPETA_CLIENTES,
    "Maestro Clientes"
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

resumen = obtener_resumen_operativo(
    tabla_tareas,
    df_pedidos
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

pedidos_pendientes = len(

    df_pedidos[
        df_pedidos["Estado"]
        .fillna("")
        .str.upper()
        != "COMPLETO"
    ]

)

with col1:

    st.metric(

        "📦 Pedidos Pendientes",

        pedidos_pendientes

    )

# ---------------------------------------
# CARROS EN CURSO
# ---------------------------------------

with col2:

    st.metric(

        "🛒 Carros en Curso",

        resumen["CarrosEnCurso"]

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
# ESTADO DEL SISTEMA
# =====================================================

st.subheader("⚙ Estado del Sistema")

col1, col2, col3 = st.columns(3)

with col1:

    st.success("Informe Tareas")

    st.metric(
        "Registros",
        len(df_tareas)
    )

    st.caption(
        fecha_archivo(
            CARPETA_TAREAS,
            "Informe Tareas"
        )
    )

with col2:

    st.success("Pedidos DIGIP")

    st.metric(
        "Registros",
        len(df_pedidos)
    )

    st.caption(
        fecha_archivo(
            CARPETA_PEDIDOS,
            "Pedidos DIGIP"
        )
    )

with col3:

    st.success("Maestro Clientes")

    st.metric(
        "Registros",
        len(df_clientes)
    )

    st.caption(
        fecha_archivo(
            CARPETA_CLIENTES,
            "Maestro Clientes"
        )
    )

st.markdown("---")

# =====================================================
# BOTÓN
# =====================================================

if st.button("🏠 Volver al Inicio"):

    st.switch_page("app.py")

    