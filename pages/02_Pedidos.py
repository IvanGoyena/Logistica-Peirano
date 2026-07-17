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
# FILTROS
# =====================================================

st.subheader("🔎 Filtros")

filtro1, filtro2, filtro3, filtro4 = st.columns(4)

# -----------------------------------------------------
# ESTADO
# -----------------------------------------------------

opciones_estado = sorted(
    tabla["Estado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

with filtro1:

    estados_seleccionados = st.multiselect(
        "Estado",
        options=opciones_estado,
        default=[]
    )

# -----------------------------------------------------
# ESTADO DE PREPARACIÓN
# -----------------------------------------------------

opciones_preparacion = sorted(
    tabla["PreparacionEstado"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

with filtro2:

    preparaciones_seleccionadas = st.multiselect(
        "Estado preparación",
        options=opciones_preparacion,
        default=[]
    )

# -----------------------------------------------------
# PLANIFICACIÓN
# -----------------------------------------------------

opciones_planificacion = sorted(
    tabla["Planificacion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

with filtro3:

    planificaciones_seleccionadas = st.multiselect(
        "Planificación",
        options=opciones_planificacion,
        default=[]
    )

# -----------------------------------------------------
# DESPACHO
# -----------------------------------------------------

opciones_despacho = sorted(
    tabla["DespachoDescripcion"]
    .dropna()
    .astype(str)
    .loc[lambda serie: serie.str.strip().ne("")]
    .unique()
    .tolist()
)

with filtro4:

    despachos_seleccionados = st.multiselect(
        "Despacho",
        options=opciones_despacho,
        default=[]
    )

    filtro5, filtro6 = st.columns([1, 2])

# -----------------------------------------------------
# FECHA
# -----------------------------------------------------

fecha_minima = tabla["Fecha"].min()
fecha_maxima = tabla["Fecha"].max()

with filtro5:

    if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

        rango_fechas = st.date_input(
            "Rango de fechas",
            value=(
                fecha_minima.date(),
                fecha_maxima.date()
            ),
            min_value=fecha_minima.date(),
            max_value=fecha_maxima.date()
        )

    else:

        rango_fechas = None

# -----------------------------------------------------
# BÚSQUEDA
# -----------------------------------------------------

with filtro6:

    texto_busqueda = st.text_input(
        "Buscar pedido o cliente",
        placeholder="Número de pedido, código o nombre del cliente..."
    )

    # =====================================================
# APLICAR FILTROS
# =====================================================

tabla_filtrada = tabla.copy()

if estados_seleccionados:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Estado"].isin(
            estados_seleccionados
        )
    ]

if preparaciones_seleccionadas:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["PreparacionEstado"].isin(
            preparaciones_seleccionadas
        )
    ]

if planificaciones_seleccionadas:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Planificacion"].isin(
            planificaciones_seleccionadas
        )
    ]

if despachos_seleccionados:

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["DespachoDescripcion"].isin(
            despachos_seleccionados
        )
    ]

if rango_fechas and len(rango_fechas) == 2:

    fecha_desde = pd.Timestamp(
        rango_fechas[0]
    )

    fecha_hasta = pd.Timestamp(
        rango_fechas[1]
    ) + pd.Timedelta(days=1)

    tabla_filtrada = tabla_filtrada[
        tabla_filtrada["Fecha"].ge(fecha_desde)
        &
        tabla_filtrada["Fecha"].lt(fecha_hasta)
    ]

if texto_busqueda.strip():

    texto = texto_busqueda.strip()

    mascara_busqueda = (
        tabla_filtrada["Pedido"]
        .astype(str)
        .str.contains(
            texto,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteCodigo"]
        .astype(str)
        .str.contains(
            texto,
            case=False,
            na=False
        )
        |
        tabla_filtrada["ClienteDescripcion"]
        .astype(str)
        .str.contains(
            texto,
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
# TARJETAS KPI
# =====================================================

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
        f"{pedidos_en_preparacion:,}".replace(",", ".")
    )

with kpi5:

    st.metric(
        "💰 Importe",
        f"$ {total_importe:,.0f}"
        .replace(",", ".")
    )


st.markdown("---")


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