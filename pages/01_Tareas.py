# =====================================================
# PARTE 1
#======================================================
import pandas as pd

from config import *

import streamlit as st
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
    obtener_tabla_operativa,
    obtener_resumen_operativo,
    obtener_avance_despachos,
    obtener_carros_criticos,
    obtener_pendiente_pick
)

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
    "Maestro Articulo",
    cache=True
)

# =====================================================
# TABLA PEDIDOS
# =====================================================

tabla_pedidos = construir_tabla_pedidos(

    df_pedidos,

    df_detalle,

    df_articulos,

    df_clientes

)

# =====================================================
# TABLA TAREAS
# =====================================================

tabla_tareas = construir_tabla_tareas(

    df_tareas,

    tabla_pedidos,

    df_clientes

)

tabla_operativa = obtener_tabla_operativa(

    tabla_tareas

)


tabla_operativa = tabla_operativa[
    [
        "Prioridad",
        "Carro",
        "Cliente",
        "Unidades",
        "SKUs",
        "Familias",
        "Despacho",
        "Hora",
        "Usuario",
        "Estado",
        "Categoria",
        "Preparacion"
        
    ]
]


# =====================================================
# KPIs PEDIDOS
# =====================================================

pedidos_sin_preparacion = tabla_pedidos[

    tabla_pedidos["PreparacionID"].isna()

].copy()

pedidos_pendientes = len(

    pedidos_sin_preparacion

)

unidades_pendientes = int(

    pedidos_sin_preparacion["TotalUnidades"]

    .fillna(0)

    .sum()

)

# =====================================================
# KPIs CARROS
# =====================================================

unidades_preparacion = tabla_pedidos[

    [

        "PreparacionID",

        "TotalUnidades"

    ]

]

tareas_unidades = tabla_tareas.merge(

    unidades_preparacion,

    left_on="Preparacion",

    right_on="PreparacionID",

    how="left"

)

unidades_carros_curso = (

    tareas_unidades[

        tareas_unidades["Categoria"]=="En Curso"

    ]

    .drop_duplicates("Preparacion")

    ["TotalUnidades"]

    .fillna(0)

    .sum()

)

unidades_carros_finalizados = (

    tareas_unidades[

        tareas_unidades["Categoria"]=="Finalizado"

    ]

    .drop_duplicates("Preparacion")

    ["TotalUnidades"]

    .fillna(0)

    .sum()

)

# =====================================================
# RESUMEN
# =====================================================

resumen = obtener_resumen_operativo(

    tabla_tareas,

    df_pedidos

)

avance_despachos, despachos_sin_iniciar = obtener_avance_despachos(
    tabla_tareas,
)

carros_criticos = obtener_carros_criticos(

    tabla_operativa,

    avance_despachos

)

pendiente_pick = obtener_pendiente_pick(

    tabla_tareas,

    tabla_pedidos

)


# =====================================================
# PARTE 2
# =====================================================

st.title("📋 Gestión de Tareas")

st.caption("Centro de Control Operativo")

st.markdown("---")

# =====================================================
# RESUMEN OPERATIVO
# =====================================================

st.subheader("📊 Resumen Operativo")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)


# -----------------------------------------------------
# PEDIDOS
# -----------------------------------------------------

with kpi1:

    st.metric(

        "📦 Pedidos Pendientes",

        pedidos_pendientes,

        delta=f"{unidades_pendientes:,} Unidades".replace(",", ".")

    )



# -----------------------------------------------------
# PENDIENTE DE PICKEAR
# -----------------------------------------------------

with kpi2:

    st.metric(

        "📦 Pendiente de Pickear",

        pendiente_pick["Preparaciones"],

        delta=f"{pendiente_pick['Unidades']:,} Unidades".replace(",", ".")

    )

# -----------------------------------------------------
# CARROS EN CURSO
# -----------------------------------------------------

with kpi3:

    st.metric(

        "🛒 Carros en Curso",

        resumen["CarrosEnCurso"],

        delta=f"{int(unidades_carros_curso):,} Unidades".replace(",", ".")

    )

# -----------------------------------------------------
# CARROS FINALIZADOS
# -----------------------------------------------------

with kpi4:

    st.metric(

        "✅ Carros Finalizados",

        resumen["CarrosFinalizados"],

        delta=(

            f'Hoy: {resumen["CarrosFinalizadosHoy"]}'

            f' | '

            f'Ayer: {resumen["CarrosFinalizadosAyer"]}'

        )

    )

st.markdown("---")

# =====================================================
# INDICADORES
# =====================================================

st.subheader("📈 Indicadores Operativos")

col1, col2, col3 = st.columns(
    [1.0, 1.3, 1.0]
)

# =====================================================
# AVANCE DESPACHOS
# =====================================================

with col1:

    st.caption("📦 Avance de Despachos")

    # -------------------------------------------------
    # DESPACHOS SIN INICIAR
    # -------------------------------------------------

    if despachos_sin_iniciar:

        st.caption(
            f"🚛 Sin iniciar ({len(despachos_sin_iniciar)})"
        )

        st.markdown(
            "<div style='font-size:12px;color:#BDBDBD;margin-bottom:10px'>"
            + " • ".join(despachos_sin_iniciar)
            + "</div>",
            unsafe_allow_html=True
        )

    # -------------------------------------------------
    # DONAS
    # -------------------------------------------------

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

                    textinfo="none",

                    showlegend=False,

                    marker=dict(

                        colors=[
                            color,
                            "#3A3A3A"
                        ]

                    )

                )

            )

            fig.update_layout(

                title=dict(

                    text=f"<b>{fila['Despacho']}</b>",

                    x=0.5,

                    font=dict(
                        size=12,
                        color="white"
                    )

                ),

                annotations=[

                    dict(

                        text=f"<b>{avance}%</b>",

                        x=0.5,
                        y=0.56,

                        showarrow=False,

                        font=dict(
                            size=22,
                            color="white"
                        )

                    ),

                    dict(

                        text=f"{cerrados}/{total}",

                        x=0.5,
                        y=0.36,

                        showarrow=False,

                        font=dict(
                            size=12,
                            color="#BDBDBD"
                        )

                    )

                ],

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

# =====================================================
# CARROS CRÍTICOS
# =====================================================

with col2:

    st.caption("🚨 Carros que cierran despachos")

    st.dataframe(

        carros_criticos,

        use_container_width=True,

        hide_index=True,

        height=430

    )

# =====================================================
# RESERVADO
# =====================================================
# =====================================================
# FAMILIAS EN OPERACIÓN
# =====================================================

familias = [

    c
    for c in [
        "Accesorios",
        "Bachas",
        "Duchones",
        "Flexibles",
        "Grifería",
        "Griferia",
        "Grifería Lago",
        "Griferia Lago",
        "Pisos de ducha",
        "Repuestos",
        "Sanitarios",
        "Varios",
    ]
    if c in tabla_pedidos.columns

]

# Preparaciones activas
preparaciones_activas = tabla_tareas[
    tabla_tareas["Categoria"].isin(
        [
            "Pendiente",
            "En Curso"
        ]
    )
]["Preparacion"].unique()

# Total por familia
familias_operativas = (

    tabla_pedidos[
        tabla_pedidos["PreparacionID"].isin(
            preparaciones_activas
        )
    ][familias]

    .sum()

    .sort_values(
        ascending=False
    )

)

familias_operativas = familias_operativas[
    familias_operativas > 0
]

# =====================================================
# GRAFICO
# =====================================================

with col3:

    st.caption("📦 Familias en preparación")

    fig = go.Figure(

        go.Pie(

            labels=familias_operativas.index,

            values=familias_operativas.values,

            hole=0.72,

            textinfo="none",

            sort=False,

            marker=dict(
                line=dict(
                    color="#111111",
                    width=2
                )
            )

        )

    )

    fig.update_layout(

        height=430,

        margin=dict(
            l=5,
            r=5,
            t=20,
            b=5
        ),

        annotations=[

            dict(

                text=(
                    f"<b>{int(familias_operativas.sum()):,}</b>"
                    "<br>"
                    "<span style='font-size:16px'>Unidades</span>"
                ).replace(",", "."),

                x=0.50,
                y=0.50,

                showarrow=False,

                font=dict(
                    size=28,
                    color="white"
                )

            )

        ],

        legend=dict(

            orientation="v",

            x=1.02,

            y=0.95,

            font=dict(

                size=14,

                color="white"

            )

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
# =====================================================
# TABLA OPERATIVA
# =====================================================

st.subheader("📋 Operación en Curso")

st.caption(

    f"{len(tabla_operativa)} registros"

)

# -----------------------------------------------------
# TABLA
# -----------------------------------------------------

tabla_visual = tabla_operativa.copy()

# =====================================================
# FORMATOS VISUALES
# =====================================================

tabla_visual["Unidades"] = (
    pd.to_numeric(
        tabla_visual["Unidades"],
        errors="coerce"
    )
    .fillna(0)
    .astype(int)
)

tabla_visual["SKUs"] = (
    pd.to_numeric(
        tabla_visual["SKUs"],
        errors="coerce"
    )
    .fillna(0)
    .astype(int)
)


tabla_visual = tabla_visual[
    [
        "Prioridad",
        "Carro",
        "Cliente",
        "Unidades",
        "SKUs",
        "Despacho",
        "Hora",
        "Usuario",
        "Estado",
        "Familias"
    ]
]

# -----------------------------------------------------
# ESTILOS
# -----------------------------------------------------

def resaltar_carro(fila):

    estilos = [""] * len(fila)

    indice = fila.index.get_loc("Carro")

    if fila["Prioridad"] == "🔴":

        estilos[indice] = (

            "background-color:#C62828;"

            "color:white;"

            "font-weight:bold;"

        )

    elif fila["Prioridad"] == "🟠":

        estilos[indice] = (

            "background-color:#EF6C00;"

            "color:white;"

            "font-weight:bold;"

        )

    return estilos

st.dataframe(
    tabla_visual
        .style
        .format({
            "Unidades": "{:.0f}",
            "SKUs": "{:.0f}",
        })
        .apply(
            resaltar_carro,
            axis=1
        ),
    use_container_width=True,
    hide_index=True,
    height=620
)

st.markdown("---")

# =====================================================
# BOTÓN
# =====================================================

if st.button(

    "🏠 Volver al Inicio"

):

    st.switch_page(

        "app.py"

    )