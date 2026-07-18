import streamlit as st

from utils.autenticacion import requerir_roles


requerir_roles(
    "admin",
    "gerencia"
)


from config import *

from utils.leer_datos import (
    leer_archivo
)

from models.detalle import (
    construir_tabla_detalle,
    construir_resumen_pedidos
)

from models.pedidos import (
    construir_tabla_pedidos,
)

from models.pendiente import (
    construir_tabla_pendientes
)

from models.transmisiones import (
    construir_tabla_transmisiones
)

from models.clientes import (
    construir_tabla_clientes
)

from models.expresos import (
    construir_tabla_expresos
)

import pandas as pd

# =====================================================
# CONFIGURACIÓN
# =====================================================

st.set_page_config(

    page_title="Pedidos",

    page_icon="📦",

    layout="wide"

)

# =====================================================
# CARGA
# =====================================================

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

df_articulos = leer_archivo(
    CARPETA_DATOS,
    "Maestro Articulo",
    cache=True
)

df_clientes = leer_archivo(
    CARPETA_DATOS,
    "Maestro Clientes",
    cache=True
)

df_pendientes_erp = leer_archivo(
    CARPETA_DATOS,
    "Pedidos Pendientes",
    cache=False
)

df_transmisiones = leer_archivo(
    CARPETA_DATOS,
    "Pedidos Transmicion",
    cache=False
)

df_expresos = leer_archivo(
    CARPETA_DATOS,
    "Datos Expresos",
    cache=True
)

df_volumetria = leer_archivo(
    CARPETA_DATOS,
    "Maestro Volumetria",
    cache=True
)


# =====================================================
# CONSTRUIR TABLA PRINCIAL
# =====================================================

tabla = construir_tabla_pedidos(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes,
    df_volumetria
)

# =====================================================
# CONSTRUIR TABLAS SATÉLITES
# =====================================================

tabla_transmisiones = construir_tabla_transmisiones(
    df_transmisiones
)

tabla_expresos = construir_tabla_expresos(
    df_expresos
)

tabla_clientes = construir_tabla_clientes(
    df_clientes
)

tabla_pendientes_erp = construir_tabla_pendientes(
    df_pendientes_erp
)


# =====================================================
# NORMALIZAR CLAVE PEDIDO
# =====================================================

tabla["Pedido"] = (
    tabla["Pedido"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)

tabla_pendientes_erp["Pedido"] = (
    tabla_pendientes_erp["Pedido"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.replace(r"\.0$", "", regex=True)
)


# =====================================================
# 1. MERGE PEDIDOS DIGIP + PENDIENTES ERP
# =====================================================

pendientes_planificacion = (
    tabla_pendientes_erp[
        [
            "Pedido",
            "CodigoSucursal",
            "CodigoExpreso",
            "ImporteERP"
        ]
    ]
    .drop_duplicates(
        subset=["Pedido"],
        keep="first"
    )
    .copy()
)

tabla = tabla.merge(
    pendientes_planificacion,
    on="Pedido",
    how="left",
    validate="many_to_one"
)


# =====================================================
# NORMALIZAR CLAVES DE PLANIFICACIÓN
# =====================================================

tabla["CodigoSucursal"] = (
    tabla["CodigoSucursal"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

tabla["CodigoExpreso"] = (
    tabla["CodigoExpreso"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

tabla_clientes["CodigoSucursal"] = (
    tabla_clientes["CodigoSucursal"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

tabla_expresos["CodigoExpreso"] = (
    tabla_expresos["CodigoExpreso"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)


# =====================================================
# 2. MERGE CON MAESTRO CLIENTES
# =====================================================

clientes_planificacion = (
    tabla_clientes[
        [
            "CodigoSucursal",
            "FrecuenciaPreparacion",
            "FrecuenciaEntrega",
        ]
    ]
    .drop_duplicates(
        subset=["CodigoSucursal"],
        keep="first"
    )
    .copy()
)

tabla = tabla.merge(
    clientes_planificacion,
    on="CodigoSucursal",
    how="left",
    validate="many_to_one"
)


# =====================================================
# 3. MERGE CON MAESTRO EXPRESOS
# =====================================================

expresos_planificacion = (
    tabla_expresos[
        [
            "CodigoExpreso",
            "LocalidadExpreso",
            "ZonaAgrupadorExpreso",
        ]
    ]
    .drop_duplicates(
        subset=["CodigoExpreso"],
        keep="first"
    )
    .copy()
)

tabla = tabla.merge(
    expresos_planificacion,
    on="CodigoExpreso",
    how="left",
    validate="many_to_one"
)


# =====================================================
# LIMPIAR CAMPOS DE PLANIFICACIÓN
# =====================================================

columnas_planificacion = [
    "FrecuenciaPreparacion",
    "FrecuenciaEntrega",
    "LocalidadExpreso",
    "ZonaAgrupadorExpreso",
]

for columna in columnas_planificacion:

        tabla[columna] = (
        tabla[columna]
        .fillna("")
        .astype(str)
        .str.strip()
    )


# =====================================================
# COLUMNA FINAL DE PLANIFICACIÓN
# =====================================================

agrupador = (
    tabla["ZonaAgrupadorExpreso"]
    .fillna("")
    .astype(str)
    .str.strip()
)

frecuencia_entrega = (
    tabla["FrecuenciaEntrega"]
    .fillna("")
    .astype(str)
    .str.strip()
)

tabla["Planificacion"] = agrupador.where(
    agrupador.ne(""),
    frecuencia_entrega
)

# =====================================================
# TIPOS DE DATOS DE LA TABLA OPERATIVA
# =====================================================

# -----------------------------------------------------
# TEXTOS
# -----------------------------------------------------

columnas_texto = [
    "Pedido",
    "ClienteCodigo",
    "ClienteDescripcion",
    "Estado",
    "PreparacionEstado",
    "PreparacionID",
    "CodigoDespacho",
    "Planificacion",
    "DetalleFamilias",
]

for columna in columnas_texto:

    if columna in tabla.columns:

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )


# -----------------------------------------------------
# FECHA
# -----------------------------------------------------

tabla["Fecha"] = pd.to_datetime(
    tabla["Fecha"],
    errors="coerce",
    utc=True
).dt.tz_localize(None)


# -----------------------------------------------------
# ENTEROS
# -----------------------------------------------------

columnas_enteras = [
    "TotalUnidades",
    "TotalSKUs",
    "ImporteERP"
]

for columna in columnas_enteras:

    tabla[columna] = (
        pd.to_numeric(
            tabla[columna],
            errors="coerce"
        )
        .fillna(0)
        .astype(int)
    )

# -----------------------------------------------------
# DECIMALES
# -----------------------------------------------------

    tabla["TotalM3"] = (
         pd.to_numeric(
         tabla["TotalM3"],
         errors="coerce"
    )
    .fillna(0)
    .round(3)
)

# =====================================================
# SELECCIÓN FINAL Y ORDEN DE COLUMNAS
# =====================================================

columnas_finales = [
    "Pedido",
    "Fecha",
    "ClienteCodigo",
    "ClienteDescripcion",
    "Estado",
    "PreparacionEstado",
    "PreparacionID",
    "CodigoDespacho",
    "DespachoDescripcion",
    "Planificacion",
    "TotalUnidades",
    "TotalM3",
    "TotalSKUs",
    "DetalleFamilias",
    "ImporteERP",
]

columnas_faltantes = [
    columna
    for columna in columnas_finales
    if columna not in tabla.columns
]

if columnas_faltantes:

    st.error(
        "Faltan columnas en la tabla operativa: "
        f"{columnas_faltantes}"
    )

    st.stop()

# Selección estricta:
# todo lo que no está en la lista queda eliminado
tabla = tabla[columnas_finales].copy()


# =====================================================
# VISUALIZACIÓN
# =====================================================

st.title("📦 Gestión de Pedidos")

st.caption(
    "Tabla operativa consolidada de pedidos DIGIP"
)

st.markdown("---")


# =====================================================
# CONTENEDOR DE KPIs
# Se crea acá para que aparezca arriba de los filtros
# =====================================================

contenedor_kpis = st.container()

st.markdown("---")

# =====================================================
# OPCIONES DISPONIBLES PARA LOS FILTROS
# =====================================================

opciones_estado = sorted(
    tabla["Estado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_preparacion = sorted(
    tabla["PreparacionEstado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_planificacion = sorted(
    tabla["Planificacion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

opciones_despacho = sorted(
    tabla["DespachoDescripcion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

fecha_minima = tabla["Fecha"].min()
fecha_maxima = tabla["Fecha"].max()


# =====================================================
# ESTADO INICIAL DE LOS FILTROS
# =====================================================

if "filtros_pedidos" not in st.session_state:

    st.session_state["filtros_pedidos"] = {
        "estados": [],
        "preparaciones": [],
        "planificaciones": [],
        "despachos": [],
        "fecha_desde": (
            fecha_minima.date()
            if pd.notna(fecha_minima)
            else None
        ),
        "fecha_hasta": (
            fecha_maxima.date()
            if pd.notna(fecha_maxima)
            else None
        ),
        "busqueda": ""
    }


filtros_aplicados = st.session_state["filtros_pedidos"]


# =====================================================
# FORMULARIO DE FILTROS
# No recarga hasta presionar Aplicar filtros
# =====================================================

st.subheader("🔎 Filtros")

with st.form(
    key="formulario_filtros_pedidos",
    clear_on_submit=False
):

    filtro1, filtro2, filtro3, filtro4 = st.columns(4)

    with filtro1:

        estados_form = st.multiselect(
            "Estado",
            options=opciones_estado,
            default=filtros_aplicados["estados"]
        )

    with filtro2:

        preparaciones_form = st.multiselect(
            "Estado preparación",
            options=opciones_preparacion,
            default=filtros_aplicados["preparaciones"]
        )

    with filtro3:

        planificaciones_form = st.multiselect(
            "Planificación",
            options=opciones_planificacion,
            default=filtros_aplicados["planificaciones"]
        )

    with filtro4:

        despachos_form = st.multiselect(
            "Despacho",
            options=opciones_despacho,
            default=filtros_aplicados["despachos"]
        )

    filtro5, filtro6 = st.columns([1, 2])

    with filtro5:

        if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

            rango_fechas_form = st.date_input(
                "Rango de fechas",
                value=(
                    filtros_aplicados["fecha_desde"],
                    filtros_aplicados["fecha_hasta"]
                ),
                min_value=fecha_minima.date(),
                max_value=fecha_maxima.date()
            )

        else:

            rango_fechas_form = None

    with filtro6:

        busqueda_form = st.text_input(
            "Buscar pedido o cliente",
            value=filtros_aplicados["busqueda"],
            placeholder=(
                "Número de pedido, código "
                "o nombre del cliente..."
            )
        )

        boton1, boton2 = st.columns(2)

        with boton1:

            aplicar_filtros = st.form_submit_button(
              "🔎 Aplicar filtros",
             use_container_width=True,
              type="primary"
    )

        with boton2:

            quitar_filtros = st.form_submit_button(
        "🧹 Quitar filtros",
        use_container_width=True
        )



# =====================================================
# GUARDAR O QUITAR FILTROS
# =====================================================

if quitar_filtros:

    st.session_state["filtros_pedidos"] = {
        "estados": [],
        "preparaciones": [],
        "planificaciones": [],
        "despachos": [],
        "fecha_desde": (
            fecha_minima.date()
            if pd.notna(fecha_minima)
            else None
        ),
        "fecha_hasta": (
            fecha_maxima.date()
            if pd.notna(fecha_maxima)
            else None
        ),
        "busqueda": ""
    }

    st.rerun()


if aplicar_filtros:

    if (
        rango_fechas_form
        and len(rango_fechas_form) == 2
    ):

        fecha_desde_form = rango_fechas_form[0]
        fecha_hasta_form = rango_fechas_form[1]

    else:

        fecha_desde_form = None
        fecha_hasta_form = None

    st.session_state["filtros_pedidos"] = {
        "estados": estados_form,
        "preparaciones": preparaciones_form,
        "planificaciones": planificaciones_form,
        "despachos": despachos_form,
        "fecha_desde": fecha_desde_form,
        "fecha_hasta": fecha_hasta_form,
        "busqueda": busqueda_form.strip()
    }

    filtros_aplicados = st.session_state[
        "filtros_pedidos"
    ]

# =====================================================
# APLICAR LOS FILTROS GUARDADOS
# =====================================================

tabla_filtrada = tabla.copy()

if filtros_aplicados["estados"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Estado"].isin(
            filtros_aplicados["estados"]
        )
    ]

if filtros_aplicados["preparaciones"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["PreparacionEstado"].isin(
            filtros_aplicados["preparaciones"]
        )
    ]

if filtros_aplicados["planificaciones"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Planificacion"].isin(
            filtros_aplicados["planificaciones"]
        )
    ]

if filtros_aplicados["despachos"]:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["DespachoDescripcion"].isin(
            filtros_aplicados["despachos"]
        )
    ]

fecha_desde = filtros_aplicados["fecha_desde"]
fecha_hasta = filtros_aplicados["fecha_hasta"]

if fecha_desde is not None:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Fecha"].ge(
            pd.Timestamp(fecha_desde)
        )
    ]

if fecha_hasta is not None:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Fecha"].lt(
            pd.Timestamp(fecha_hasta)
            + pd.Timedelta(days=1)
        )
    ]

texto_busqueda = filtros_aplicados["busqueda"]

if texto_busqueda:

    mascara_busqueda = (
        tabla_filtrada["Pedido"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteCodigo"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteDescripcion"]
        .astype(str)
        .str.contains(
            texto_busqueda,
            case=False,
            na=False
        )
    )

    tabla_filtrada = tabla_filtrada[
        mascara_busqueda
    ]


# =====================================================
# BASE ÚNICA PARA KPIs
# =====================================================

tabla_kpis = (
    tabla_filtrada
    .drop_duplicates(
        subset=["Pedido"],
        keep="first"
    )
    .copy()
)


# =====================================================
# CÁLCULO DE KPIs
# =====================================================

total_pedidos = tabla_kpis["Pedido"].nunique()

total_unidades = int(
    tabla_kpis["TotalUnidades"].sum()
)

total_volumetria = float(
    tabla_kpis["TotalM3"].sum()
)

total_importe = float(
    tabla_kpis["ImporteERP"].sum()
)

pedidos_en_preparacion = int(
    tabla_kpis["PreparacionEstado"]
    .fillna("")
    .astype(str)
    .str.strip()
    .ne("")
    .sum()
)


# =====================================================
# MOSTRAR KPIs ARRIBA DE LOS FILTROS
# =====================================================

with contenedor_kpis:

    st.subheader("📊 Resumen Operativo")

    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    with kpi1:

        st.metric(
            "📦 Pedidos",
            f"{total_pedidos:,}".replace(",", ".")
        )

    with kpi2:

        st.metric(
            "🔢 Unidades",
            f"{total_unidades:,}".replace(",", ".")
        )

    with kpi3:

        st.metric(
            "📐 Volumen total",
            f"{total_volumetria:,.3f} m³"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )

    with kpi4:

        st.metric(
            "🛒 Con preparación",
            f"{pedidos_en_preparacion:,}"
            .replace(",", ".")
        )

    with kpi5:

        st.metric(
            "💰 Importe",
            f"$ {total_importe:,.0f}"
            .replace(",", ".")
        )



# =====================================================
# DESCARGA
# =====================================================

csv_tabla_operativa = (
    tabla_filtrada.to_csv(
        index=False,
        sep=";",
        encoding="utf-8-sig",
        date_format="%d/%m/%Y"
    )
    .encode("utf-8-sig")
)

st.download_button(
    label="⬇️ Descargar tabla operativa",
    data=csv_tabla_operativa,
    file_name="Tabla_Operativa_Pedidos.csv",
    mime="text/csv",
    use_container_width=False
)


# =====================================================
# TABLA
# =====================================================

st.subheader("📋 Tabla Operativa")

st.caption(
    f"{len(tabla_filtrada):,} registros visibles · "
    f"{tabla_filtrada['Pedido'].nunique():,} pedidos únicos · "
    f"{len(tabla):,} registros totales"
    .replace(",", ".")
)

st.dataframe(
    tabla_filtrada,
    width="stretch",
    hide_index=True,
    height=750,
    column_config={

        "Fecha": st.column_config.DateColumn(
            "Fecha",
            format="DD/MM/YYYY"
        ),

        "TotalUnidades": st.column_config.NumberColumn(
            "Unidades",
            format="%d"
        ),
        "TotalM3": st.column_config.NumberColumn(
         "M³",
        format="%.3f"
        ),

        "TotalSKUs": st.column_config.NumberColumn(
            "SKUs",
            format="%d"
        ),

        "ImporteERP": st.column_config.NumberColumn(
            "Importe ERP",
            format="$ %.0f"
        ),
    }
)