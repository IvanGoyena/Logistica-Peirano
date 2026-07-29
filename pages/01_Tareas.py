import streamlit as st


from utils.autenticacion import requerir_roles

requerir_roles(
    "admin",
    "gerencia",
    "logistica",
    "supervisor",
)

with st.sidebar:
    st.toggle(
        "Diagnóstico de rendimiento",
        key="debug_rendimiento",
    )

import pandas as pd
from config import *
from datetime import datetime
import plotly.graph_objects as go

from utils.leer_datos import (
    leer_archivo,
    fecha_archivo
)

from utils.rendimiento import (
    medir_tiempo,
    mostrar_info_dataframe,
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
# CONSERVAR SESSION STATE
# =====================================================

def cargar_archivo_seguro(
    nombre,
    cache,
    clave_session,
):
    """
    Lee un archivo y conserva en Session State
    la última versión válida.

    Si la nueva lectura falla o llega vacía,
    devuelve la última versión correcta.
    """

    try:

        dataframe = leer_archivo(
            CARPETA_DATOS,
            nombre,
            cache=cache,
        )

        if dataframe is None or dataframe.empty:

            if clave_session in st.session_state:

                return (
                    st.session_state[clave_session].copy(),
                    False,
                    f"{nombre}: se conserva la última versión válida.",
                )

            return (
                pd.DataFrame(),
                False,
                f"{nombre}: el archivo está vacío y no existe una versión anterior.",
            )

        st.session_state[clave_session] = dataframe.copy()

        return dataframe, True, None

    except Exception as error:

        if clave_session in st.session_state:

            return (
                st.session_state[clave_session].copy(),
                False,
                (
                    f"{nombre}: no se pudo actualizar. "
                    "Se conserva la última versión válida."
                ),
            )

        return (
            pd.DataFrame(),
            False,
            f"{nombre}: error de carga: {type(error).__name__}",
        )



# =====================================================
# ACTUALIZACIÓN AUTOMÁTICA
# =====================================================

@st.fragment(run_every="5m")
def modulo_tareas():

    hora_actualizacion = datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )

    st.title("📋 Gestión de Tareas")
    st.caption("Centro de Control Operativo")

    # =====================================================
    # CARGA SEGURA DE DATOS
    # =====================================================

    mensajes_carga = []

    df_tareas, tareas_actualizadas, mensaje = cargar_archivo_seguro(
        nombre="Informe Tareas",
        cache=False,
        clave_session="tareas_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    df_pedidos, pedidos_actualizados, mensaje = cargar_archivo_seguro(
        nombre="Pedidos DIGIP",
        cache=False,
        clave_session="pedidos_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    df_detalle, detalle_actualizado, mensaje = cargar_archivo_seguro(
        nombre="Detalle Pendientes",
        cache=False,
        clave_session="detalle_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    df_clientes, clientes_actualizados, mensaje = cargar_archivo_seguro(
        nombre="Maestro Clientes",
        cache=True,
        clave_session="clientes_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    df_articulos, articulos_actualizados, mensaje = cargar_archivo_seguro(
        nombre="Maestro Articulo",
        cache=True,
        clave_session="articulos_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    df_volumetria, volumetria_actualizada, mensaje = cargar_archivo_seguro(
        nombre="Maestro Volumetria",
        cache=True,
        clave_session="volumetria_ultimo_valido",
    )

    if mensaje:
        mensajes_carga.append(mensaje)

    # =====================================================
    # VALIDACIÓN DE ARCHIVOS
    # =====================================================

    archivos_criticos = {
        "Informe Tareas": df_tareas,
        "Pedidos DIGIP": df_pedidos,
        "Detalle Pendientes": df_detalle,
        "Maestro Clientes": df_clientes,
        "Maestro Articulo": df_articulos,
        "Maestro Volumetria": df_volumetria,
    }

    archivos_no_disponibles = [
        nombre
        for nombre, dataframe in archivos_criticos.items()
        if dataframe is None or dataframe.empty
    ]

    if archivos_no_disponibles:

        st.caption(
            f"⚠️ Intento de actualización: {hora_actualizacion}"
        )

        st.error(
            "No es posible construir el tablero porque faltan datos de: "
            + ", ".join(archivos_no_disponibles)
        )

        st.info(
            "El sistema volverá a intentar la carga automáticamente "
            "en la próxima actualización."
        )

        return

    # =====================================================
    # ESTADO DE ACTUALIZACIÓN
    # =====================================================

    actualizacion_completa = all(
        [
            tareas_actualizadas,
            pedidos_actualizados,
            detalle_actualizado,
            clientes_actualizados,
            articulos_actualizados,
            volumetria_actualizada,
        ]
    )

    if actualizacion_completa:

        st.caption(
            f"✅ Datos actualizados: {hora_actualizacion} "
            "— actualización automática cada 5 minutos"
        )

    else:

        st.caption(
            f"⚠️ Intento de actualización: {hora_actualizacion} "
            "— mostrando la última información válida"
        )

    st.markdown("---")

    # =====================================================
    # ADVERTENCIAS DE CARGA
    # =====================================================

    if mensajes_carga:

        st.warning(
            "La última actualización tuvo inconvenientes. "
            "El tablero continúa mostrando la información válida anterior.",
            icon="⚠️",
        )

        for mensaje in mensajes_carga:
            st.caption(f"• {mensaje}")


    with medir_tiempo("Construir tabla pedidos"):
        tabla_pedidos = construir_tabla_pedidos(
            df_pedidos,
            df_detalle,
            df_articulos,
            df_clientes,
            df_volumetria,
        )

    mostrar_info_dataframe(
        "Tabla pedidos",
        tabla_pedidos,
    )


    with medir_tiempo("Construir tabla tareas"):
        tabla_tareas = construir_tabla_tareas(
            df_tareas,
            tabla_pedidos,
            df_clientes,
        )

    mostrar_info_dataframe(
        "Tabla tareas",
        tabla_tareas,
    )


    with medir_tiempo("Construir tabla operativa"):
        tabla_operativa = obtener_tabla_operativa(
            tabla_tareas
        )

    mostrar_info_dataframe(
        "Tabla operativa",
        tabla_operativa,
    )


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

                    annotations=[

                        # Título centrado
                        dict(
                            text=f"<b>{fila['Despacho']}</b>",
                            x=0.5,
                            y=1.08,
                            xref="paper",
                            yref="paper",
                            xanchor="center",
                            yanchor="bottom",
                            showarrow=False,
                            font=dict(
                                size=12,
                                color="white"
                            )
                        ),

                        # Porcentaje
                        dict(
                            text=f"<b>{avance}%</b>",
                            x=0.5,
                            y=0.56,
                            xref="paper",
                            yref="paper",
                            xanchor="center",
                            showarrow=False,
                            font=dict(
                                size=22,
                                color="white"
                            )
                        ),

                        # Preparaciones
                        dict(
                            text=f"{cerrados}/{total}",
                            x=0.5,
                            y=0.36,
                            xref="paper",
                            yref="paper",
                            xanchor="center",
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
                        t=45,
                        b=5
                    ),

                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="white")
                )

                st.plotly_chart(
                    fig,
                    width="stretch",
                    config={
                        "displayModeBar": False
                    }
                )

    # =====================================================
    # CARROS CRÍTICOS
    # =====================================================

    with col2:

        st.caption("🚨 Carros que cierran despachos")
        carros_criticos_visual = carros_criticos.copy()

        columnas_texto_criticos = [
            "Despacho",
            "Carro",
            "Cliente",
        ]

        for columna in columnas_texto_criticos:

            if columna in carros_criticos_visual.columns:

                carros_criticos_visual[columna] = (
                    carros_criticos_visual[columna]
                    .fillna("")
                    .astype(str)
                )

        if "Unidades" in carros_criticos_visual.columns:

            carros_criticos_visual["Unidades"] = (
                pd.to_numeric(
                    carros_criticos_visual["Unidades"],
                    errors="coerce",
                )
                .fillna(0)
                .astype("int64")
            )


        st.dataframe(

            carros_criticos,

            width="stretch",

            hide_index=True,

            height=430

        )

    # =====================================================
    # RESERVADO
    # =====================================================
    # =====================================================
    # SECTORIZACIONES EN OPERACIÓN
    # =====================================================

    sectorizaciones = [
        c
        for c in [
            "IMPORTADO",
            "Importado",
            "NACIONAL",
            "Nacional",
            "BACHAS",
            "Bachas",
            "BLISTER",
            "Blister",
            "SANITARIOS",
            "Sanitarios",
            "REPUESTOS",
            "Repuestos",
            "FLEXIBLES",
            "Flexibles",
            "ACCESORIOS",
            "Accesorios",
            "VARIOS",
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
        ][sectorizaciones]

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

        st.caption("📦 Sector en preparación")

        fig = go.Figure(

            go.Pie(

                labels=[
        f"{sector} — {int(unidades):,} u.".replace(",", ".")
        for sector, unidades in zip(
            familias_operativas.index,
            familias_operativas.values
        )
        ],

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

            width="stretch",

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
    # NORMALIZACIÓN PARA STREAMLIT / PYARROW
    # =====================================================

    columnas_numericas = [
        "Unidades",
        "SKUs",
    ]

    columnas_texto = [
        "Prioridad",
        "Carro",
        "Cliente",
        "Despacho",
        "Hora",
        "Usuario",
        "Estado",
        "Familias",
    ]

    for columna in columnas_numericas:

        if columna in tabla_visual.columns:

            tabla_visual[columna] = (
                pd.to_numeric(
                    tabla_visual[columna],
                    errors="coerce",
                )
                .fillna(0)
                .astype("int64")
            )

    for columna in columnas_texto:

        if columna in tabla_visual.columns:

            tabla_visual[columna] = (
                tabla_visual[columna]
                .fillna("")
                .astype(str)
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
            "Familias",
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
        width="stretch",
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

modulo_tareas()