import streamlit as st


from utils.autenticacion import requerir_roles


requerir_roles(
    "admin",
    "gerencia"
)




import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from config import CARPETA_DATOS

from utils.leer_datos import (
    leer_archivo,
)

from models.metricas import (
    construir_fuentes_metricas,
)

from models.limpieza_metricas import (
    ejecutar_etl_metricas,
)

from models.volumetria import (
    construir_tabla_volumetria,
)

from models.enriquecimiento_metricas import (
    ejecutar_enriquecimiento_metricas,
)


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

st.set_page_config(
    page_title="Métricas",
    page_icon="📈",
    layout="wide",
)


# ==========================================================
# CONSTANTES
# ==========================================================

ORDEN_DIAS = [
    "LUNES",
    "MARTES",
    "MIERCOLES",
    "JUEVES",
    "VIERNES",
    "SABADO",
    "DOMINGO",
]

MESES_CORTOS = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


# ==========================================================
# CARGA Y PROCESAMIENTO
# ==========================================================

@st.cache_data(
    show_spinner=(
        "Leyendo, limpiando y enriqueciendo históricos..."
    ),
    max_entries=1,
)
def cargar_metricas():

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

    return {
        "fuentes": fuentes,
        "etl": etl,
        "df_articulos": df_articulos,
        "tabla_volumetria": tabla_volumetria,
        "enriquecimiento": enriquecimiento,
    }


# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def formatear_entero(valor) -> str:

    return f"{float(valor):,.0f}".replace(",", ".")


def formatear_decimal(
    valor,
    decimales=1,
) -> str:

    texto = f"{float(valor):,.{decimales}f}"

    return (
        texto
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def formatear_peso(
    valor,
) -> str:
    """
    Muestra siempre el peso total en kilogramos.
    """

    return (
        formatear_entero(valor)
        + " kg"
    )


def calcular_variacion(
    actual: float,
    anterior: float,
):

    if pd.isna(anterior) or anterior == 0:
        return None

    return (
        (actual - anterior)
        / abs(anterior)
        * 100
    )


def texto_delta(
    variacion,
) -> str | None:
    """
    Devuelve una comparación breve pero informativa.
    """

    if variacion is None or pd.isna(variacion):
        return None

    signo = "+" if variacion >= 0 else ""

    return (
        f"{signo}{variacion:.1f}% "
        "vs período anterior"
    )


def metricas_periodo(
    tareas: pd.DataFrame,
) -> dict:

    if tareas.empty:

        return {
            "Tareas": 0,
            "Unidades": 0,
            "Lineas": 0,
            "VolumenM3": 0,
            "PesoKg": 0,
            "Horas": 0,
            "UnidadesHora": 0,
            "UsuariosActivos": 0,
            "PromedioUnidadesLinea": 0,
        }

    horas = (
        pd.to_numeric(
            tareas["TiempoRealSegundos"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
        / 3600
    )

    unidades = (
        pd.to_numeric(
            tareas["UnidadesAnalisis"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    lineas = (
        pd.to_numeric(
            tareas["LineasDetalle"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    # ======================================================
    # USUARIOS ACTIVOS
    # ======================================================
    #
    # Un usuario se considera activo cuando las horas
    # registradas en tareas representan más del 60 % de las
    # horas de turno de los días en que tuvo actividad.
    #
    # Turnos utilizados:
    # - Lunes a viernes: 9 horas.
    # - Sábado: 6 horas.
    # - Domingo: no se computa.
    #
    # El usuario se identifica por UsuarioId y, cuando falta,
    # por el nombre estandarizado.
    # ======================================================

    base_usuarios = tareas.copy()

    usuario_id = (
        base_usuarios["UsuarioId"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            r"\\.0$",
            "",
            regex=True,
        )
    )

    usuario_nombre = (
        base_usuarios["Usuario"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    base_usuarios["ClaveUsuario"] = usuario_id.where(
        usuario_id.ne(""),
        "NOMBRE|" + usuario_nombre,
    )

    base_usuarios["FechaActividad"] = pd.to_datetime(
        base_usuarios["Fecha"],
        errors="coerce",
    ).dt.normalize()

    base_usuarios["HorasTarea"] = (
        pd.to_numeric(
            base_usuarios["TiempoRealSegundos"],
            errors="coerce",
        )
        .fillna(0)
        / 3600
    )

    base_usuarios["DiaSemanaNumero"] = (
        base_usuarios["FechaActividad"].dt.dayofweek
    )

    base_usuarios["HorasTurnoDia"] = np.select(
        [
            base_usuarios[
                "DiaSemanaNumero"
            ].between(0, 4),
            base_usuarios[
                "DiaSemanaNumero"
            ].eq(5),
        ],
        [
            9.0,
            6.0,
        ],
        default=0.0,
    )

    base_usuarios = base_usuarios[
        base_usuarios["ClaveUsuario"].ne("")
        & base_usuarios["ClaveUsuario"].ne(
            "NOMBRE|"
        )
        & base_usuarios["FechaActividad"].notna()
        & base_usuarios["HorasTurnoDia"].gt(0)
    ].copy()

    if base_usuarios.empty:

        usuarios_activos = 0

    else:

        # Primero consolidar todas las tareas de una persona
        # dentro del mismo día.
        usuarios_por_dia = (
            base_usuarios
            .groupby(
                [
                    "ClaveUsuario",
                    "FechaActividad",
                ],
                as_index=False,
            )
            .agg(
                HorasTarea=(
                    "HorasTarea",
                    "sum",
                ),
                HorasTurnoDia=(
                    "HorasTurnoDia",
                    "first",
                ),
            )
        )

        # Luego evaluar el porcentaje acumulado del período.
        usuarios_periodo = (
            usuarios_por_dia
            .groupby(
                "ClaveUsuario",
                as_index=False,
            )
            .agg(
                HorasTarea=(
                    "HorasTarea",
                    "sum",
                ),
                HorasTurno=(
                    "HorasTurnoDia",
                    "sum",
                ),
            )
        )

        usuarios_periodo["OcupacionTareasPct"] = (
            usuarios_periodo["HorasTarea"]
            / usuarios_periodo[
                "HorasTurno"
            ].replace(
                0,
                np.nan,
            )
            * 100
        )

        usuarios_activos = int(
            usuarios_periodo[
                "OcupacionTareasPct"
            ].gt(30)
            .sum()
        )

    return {
        "Tareas": tareas["ClaveTarea"].nunique(),
        "Unidades": unidades,
        "Lineas": lineas,
        "UsuariosActivos": usuarios_activos,
        "PromedioUnidadesLinea": (
            unidades / lineas
            if lineas > 0
            else 0
        ),
        "VolumenM3": (
            pd.to_numeric(
                tareas["VolumenTotalM3"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        ),
        "PesoKg": (
            pd.to_numeric(
                tareas["PesoTotalKg"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        ),
        "Horas": horas,
        "UnidadesHora": (
            unidades / horas
            if horas > 0
            else 0
        ),
    }


def aplicar_filtros(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
    fecha_desde,
    fecha_hasta,
    procesos,
    familias,
    sectorizaciones,
    usuarios,
    tipos,
):

    tareas_filtradas = tareas.copy()

    tareas_filtradas["Fecha"] = pd.to_datetime(
        tareas_filtradas["Fecha"],
        errors="coerce",
    )

    tareas_filtradas = tareas_filtradas[
        tareas_filtradas["Fecha"].between(
            pd.Timestamp(fecha_desde),
            pd.Timestamp(fecha_hasta),
            inclusive="both",
        )
    ]

    if procesos:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Proceso"].isin(
                procesos
            )
        ]

    if familias:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas[
                "FamiliaPrincipal"
            ].fillna("").isin(
                familias
            )
        ]

    if sectorizaciones:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas[
                "SectorizacionPrincipal"
            ].fillna("").isin(
                sectorizaciones
            )
        ]

    if usuarios:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Usuario"].isin(
                usuarios
            )
        ]

    if tipos:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Tipo"].isin(
                tipos
            )
        ]

    claves = set(
        tareas_filtradas["ClaveTarea"]
        .dropna()
        .astype(str)
    )

    detalle_filtrado = detalle[
        detalle["ClaveTarea"]
        .astype(str)
        .isin(claves)
    ].copy()

    return tareas_filtradas, detalle_filtrado


def construir_insights(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
    indicadores_actuales: dict,
    indicadores_anteriores: dict,
) -> list[dict]:

    insights = []

    variacion_productividad = calcular_variacion(
        indicadores_actuales["UnidadesHora"],
        indicadores_anteriores["UnidadesHora"],
    )

    if variacion_productividad is not None:

        direccion = (
            "aumentó"
            if variacion_productividad >= 0
            else "disminuyó"
        )

        insights.append(
            {
                "tipo": (
                    "positivo"
                    if variacion_productividad >= 0
                    else "alerta"
                ),
                "titulo": "Productividad",
                "texto": (
                    f"La productividad {direccion} "
                    f"{abs(variacion_productividad):.1f}% "
                    "frente al período anterior."
                ),
            }
        )

    if not tareas.empty:

        familia = (
            tareas
            .groupby(
                "FamiliaPrincipal",
                dropna=False,
            )["UnidadesAnalisis"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        if not familia.empty:

            nombre_familia = str(
                familia.index[0]
            )

            unidades_familia = float(
                familia.iloc[0]
            )

            participacion = (
                unidades_familia
                / max(
                    indicadores_actuales["Unidades"],
                    1,
                )
                * 100
            )

            insights.append(
                {
                    "tipo": "informativo",
                    "titulo": "Familia dominante",
                    "texto": (
                        f"{nombre_familia} concentra "
                        f"{participacion:.1f}% de las unidades "
                        "del período."
                    ),
                }
            )

        productividad_dia = (
            tareas
            .groupby(
                "DiaSemana",
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
        )

        productividad_dia["UnidadesHora"] = (
            productividad_dia["Unidades"]
            / (
                productividad_dia["Segundos"]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        productividad_dia = (
            productividad_dia
            .dropna(
                subset=["UnidadesHora"]
            )
            .sort_values(
                "UnidadesHora"
            )
        )

        if not productividad_dia.empty:

            peor = productividad_dia.iloc[0]

            insights.append(
                {
                    "tipo": "alerta",
                    "titulo": "Día de menor rendimiento",
                    "texto": (
                        f"{peor['DiaSemana']} presenta la "
                        f"menor productividad: "
                        f"{peor['UnidadesHora']:.1f} unidades/hora."
                    ),
                }
            )

    if not detalle.empty:

        top_articulo = (
            detalle
            .groupby(
                [
                    "CodigoArticulo",
                    "DescripcionFinal",
                ],
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
        )

        if not top_articulo.empty:

            fila = top_articulo.iloc[0]

            insights.append(
                {
                    "tipo": "informativo",
                    "titulo": "Artículo más movilizado",
                    "texto": (
                        f"{fila['CodigoArticulo']} — "
                        f"{fila['DescripcionFinal']} lidera con "
                        f"{fila['UnidadesDetalle']:,.0f} unidades."
                    ),
                }
            )

    return insights[:5]


def limitar_previsualizacion(
    dataframe: pd.DataFrame,
    limite: int = 5000,
) -> pd.DataFrame:
    """
    Evita enviar cientos de miles de filas al navegador.
    La base completa sigue disponible en memoria.
    """

    if len(dataframe) <= limite:
        return dataframe

    return dataframe.head(limite)


def mostrar_insight(
    insight: dict,
):

    iconos = {
        "positivo": "📈",
        "alerta": "⚠️",
        "informativo": "💡",
    }

    icono = iconos.get(
        insight["tipo"],
        "💡",
    )

    st.markdown(
        f"""
        <div class="insight-card">
            <div class="insight-icon">{icono}</div>
            <div>
                <div class="insight-title">
                    {insight["titulo"]}
                </div>
                <div class="insight-text">
                    {insight["texto"]}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==========================================================
# ESTILO
# ==========================================================

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }

    [data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 14px;
        padding: 0.82rem 0.88rem;
        background: rgba(128, 128, 128, 0.04);
        min-height: 122px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.62rem;
    }

    [data-testid="stMetricDelta"] {
        font-size: 0.76rem;
        white-space: normal;
    }

    [data-testid="stMetricLabel"] {
        font-weight: 600;
    }

    .insight-card {
        display: flex;
        gap: 0.8rem;
        align-items: flex-start;
        padding: 0.9rem;
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 12px;
        margin-bottom: 0.65rem;
        background: rgba(128, 128, 128, 0.04);
    }

    .insight-icon {
        font-size: 1.25rem;
        line-height: 1.3;
    }

    .insight-title {
        font-weight: 700;
        margin-bottom: 0.18rem;
    }

    .insight-text {
        opacity: 0.84;
        font-size: 0.92rem;
    }

    .section-caption {
        opacity: 0.72;
        margin-top: -0.45rem;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================================
# ENCABEZADO Y ACTUALIZACIÓN
# ==========================================================

titulo_col, actualizar_col = st.columns(
    [5, 1],
    vertical_alignment="center",
)

with titulo_col:

    st.title("📊 Dashboard Gerencial")

    st.caption(
        "Análisis histórico de Preparación y Control, "
        "enriquecido con artículos, volumen y peso."
    )

with actualizar_col:

    actualizar = st.button(
        "🔄 Actualizar",
        width="stretch",
        type="primary",
    )


if actualizar:

    cargar_metricas.clear()

    st.toast(
        "Datos actualizados correctamente.",
        icon="✅",
    )

    st.rerun()


# ==========================================================
# EJECUTAR CARGA
# ==========================================================

try:

    datos = cargar_metricas()

except Exception as error:

    st.error(
        "No se pudieron procesar las métricas."
    )

    st.exception(error)

    st.stop()


fuentes = datos["fuentes"]
etl = datos["etl"]
enriquecimiento = datos["enriquecimiento"]

df_tareas = enriquecimiento[
    "tareas_enriquecidas"
].copy()

df_detalle = enriquecimiento[
    "detalle_enriquecido"
].copy()

df_calidad_enriquecimiento = enriquecimiento[
    "calidad_enriquecimiento"
]


# ==========================================================
# EXCLUSIÓN DE PEDIDOS INTERNOS
# ==========================================================
#
# Los registros sin sectorización o con Sectorización
# "NO APLICA" corresponden a movimientos/pedidos internos
# que no deben impactar el tablero operativo.
#
# Se excluyen únicamente de la base analítica del dashboard.
# Los datos crudos y la Auditoría ETL continúan conservándolos.
# ==========================================================

sectorizacion_tareas = (
    df_tareas["SectorizacionPrincipal"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

mascara_tareas_operativas = (
    sectorizacion_tareas.ne("")
    & sectorizacion_tareas.ne("NO APLICA")
)

df_tareas = df_tareas[
    mascara_tareas_operativas
].copy()


sectorizacion_detalle = (
    df_detalle["Sectorizacion"]
    .fillna("")
    .astype(str)
    .str.strip()
    .str.upper()
)

mascara_detalle_operativo = (
    sectorizacion_detalle.ne("")
    & sectorizacion_detalle.ne("NO APLICA")
)

df_detalle = df_detalle[
    mascara_detalle_operativo
].copy()


if df_tareas.empty:

    st.warning(
        "No existen tareas enriquecidas para mostrar."
    )

    st.stop()


df_tareas["Fecha"] = pd.to_datetime(
    df_tareas["Fecha"],
    errors="coerce",
)

fecha_minima = df_tareas["Fecha"].min()
fecha_maxima = df_tareas["Fecha"].max()


# ==========================================================
# FILTROS
# ==========================================================

st.markdown("### 🔎 Filtros")

with st.container(
    border=True
):

    (
        filtro1,
        filtro2,
        filtro3,
        filtro4,
        filtro5,
    ) = st.columns(
        [
            1.30,
            1.10,
            1.15,
            1.10,
            1.10,
        ]
    )

    with filtro1:

        rango_fechas = st.date_input(
            "Período",
            value=(
                fecha_minima.date(),
                fecha_maxima.date(),
            ),
            min_value=fecha_minima.date(),
            max_value=fecha_maxima.date(),
        )

    with filtro2:

        familias_disponibles = sorted(
            df_tareas["FamiliaPrincipal"]
            .fillna("")
            .astype(str)
            .loc[
                lambda serie:
                serie.str.strip().ne("")
            ]
            .unique()
            .tolist()
        )

        filtro_familias = st.multiselect(
            "Familia",
            options=familias_disponibles,
            default=[],
            placeholder="Todas",
        )

    with filtro3:

        sectorizaciones_disponibles = sorted(
            df_tareas["SectorizacionPrincipal"]
            .fillna("")
            .astype(str)
            .loc[
                lambda serie:
                serie.str.strip().ne("")
            ]
            .unique()
            .tolist()
        )

        filtro_sectorizaciones = st.multiselect(
            "Sectorización",
            options=sectorizaciones_disponibles,
            default=[],
            placeholder="Todas",
        )

    with filtro4:

        usuarios_disponibles = sorted(
            df_tareas["Usuario"]
            .fillna("")
            .astype(str)
            .loc[
                lambda serie:
                serie.str.strip().ne("")
            ]
            .unique()
            .tolist()
        )

        filtro_usuarios = st.multiselect(
            "Usuario",
            options=usuarios_disponibles,
            default=[],
            placeholder="Todos",
        )

    with filtro5:

        tipos_disponibles = sorted(
            df_tareas["Tipo"]
            .fillna("")
            .astype(str)
            .loc[
                lambda serie:
                serie.str.strip().ne("")
            ]
            .unique()
            .tolist()
        )

        filtro_tipos = st.multiselect(
            "Tipo",
            options=tipos_disponibles,
            default=[],
            placeholder="Todos",
        )


if len(rango_fechas) == 2:

    fecha_desde = rango_fechas[0]
    fecha_hasta = rango_fechas[1]

else:

    fecha_desde = fecha_minima.date()
    fecha_hasta = fecha_maxima.date()


# El proceso ya no se muestra como filtro.
# Se incluyen todos los procesos y el recorte operativo
# se realiza mediante Tipo.
procesos_disponibles = sorted(
    df_tareas["Proceso"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)


tareas_filtradas, detalle_filtrado = aplicar_filtros(
    tareas=df_tareas,
    detalle=df_detalle,
    fecha_desde=fecha_desde,
    fecha_hasta=fecha_hasta,
    procesos=procesos_disponibles,
    familias=filtro_familias,
    sectorizaciones=filtro_sectorizaciones,
    usuarios=filtro_usuarios,
    tipos=filtro_tipos,
)


if tareas_filtradas.empty:

    st.warning(
        "No existen datos para la combinación de filtros seleccionada."
    )

    st.stop()


# ==========================================================
# PERÍODO ANTERIOR
# ==========================================================

cantidad_dias = (
    pd.Timestamp(fecha_hasta)
    - pd.Timestamp(fecha_desde)
).days + 1

fecha_anterior_hasta = (
    pd.Timestamp(fecha_desde)
    - pd.Timedelta(days=1)
)

fecha_anterior_desde = (
    fecha_anterior_hasta
    - pd.Timedelta(
        days=cantidad_dias - 1
    )
)

tareas_anteriores, _ = aplicar_filtros(
    tareas=df_tareas,
    detalle=df_detalle,
    fecha_desde=fecha_anterior_desde.date(),
    fecha_hasta=fecha_anterior_hasta.date(),
    procesos=procesos_disponibles,
    familias=filtro_familias,
    sectorizaciones=filtro_sectorizaciones,
    usuarios=filtro_usuarios,
    tipos=filtro_tipos,
)

actual = metricas_periodo(
    tareas_filtradas
)

anterior = metricas_periodo(
    tareas_anteriores
)


# Base específica para Evolución mensual:
# respeta Familia, Sectorización, Usuario y Tipo,
# pero ignora Período.
tareas_evolucion, detalle_evolucion = aplicar_filtros(
    tareas=df_tareas,
    detalle=df_detalle,
    fecha_desde=fecha_minima.date(),
    fecha_hasta=fecha_maxima.date(),
    procesos=procesos_disponibles,
    familias=filtro_familias,
    sectorizaciones=filtro_sectorizaciones,
    usuarios=filtro_usuarios,
    tipos=filtro_tipos,
)


# ==========================================================
# KPIs
# ==========================================================

st.markdown("### Actividad")

(
    kpi1,
    kpi2,
    kpi3,
    kpi4,
    kpi5,
    kpi6,
    kpi7,
    kpi8,
) = st.columns(8)

with kpi1:

    st.metric(
        "📋 Tareas",
        formatear_entero(
            actual["Tareas"]
        ),
        texto_delta(
            calcular_variacion(
                actual["Tareas"],
                anterior["Tareas"],
            )
        ),
    )

with kpi2:

    st.metric(
        "📦 Unidades",
        formatear_entero(
            actual["Unidades"]
        ),
        texto_delta(
            calcular_variacion(
                actual["Unidades"],
                anterior["Unidades"],
            )
        ),
    )

with kpi3:

    st.metric(
        "🧾 Líneas",
        formatear_entero(
            actual["Lineas"]
        ),
        texto_delta(
            calcular_variacion(
                actual["Lineas"],
                anterior["Lineas"],
            )
        ),
    )

with kpi4:

    st.metric(
        "📐 Volumen",
        (
            formatear_entero(
                actual["VolumenM3"]
            )
            + " m³"
        ),
        texto_delta(
            calcular_variacion(
                actual["VolumenM3"],
                anterior["VolumenM3"],
            )
        ),
    )

with kpi5:

    st.metric(
        "⚖️ Peso",
        formatear_peso(
            actual["PesoKg"]
        ),
        texto_delta(
            calcular_variacion(
                actual["PesoKg"],
                anterior["PesoKg"],
            )
        ),
    )

with kpi6:

    st.metric(
        "⚡ Unid./hora",
        formatear_entero(
            actual["UnidadesHora"]
        ),
        texto_delta(
            calcular_variacion(
                actual["UnidadesHora"],
                anterior["UnidadesHora"],
            )
        ),
    )

with kpi7:

    st.metric(
        "👥 Usuarios",
        formatear_entero(
            actual["UsuariosActivos"]
        ),
        texto_delta(
            calcular_variacion(
                actual["UsuariosActivos"],
                anterior["UsuariosActivos"],
            )
        ),
    )

with kpi8:

    st.metric(
        "📏 Unid./línea",
        formatear_decimal(
            actual["PromedioUnidadesLinea"],
            2,
        ),
        texto_delta(
            calcular_variacion(
                actual["PromedioUnidadesLinea"],
                anterior["PromedioUnidadesLinea"],
            )
        ),
    )

st.divider()


# ==========================================================
# PESTAÑAS PRINCIPALES
# ==========================================================

vista_principal = st.radio(
    "Vista",
    options=[
        "🏠 Resumen",
        "⚡ Productividad",
        "📦 Productos",
        "💡 Insights",
    ],
    horizontal=True,
    label_visibility="collapsed",
    key="vista_metricas",
)


# ==========================================================
# DASHBOARD
# ==========================================================

if vista_principal == "🏠 Resumen":

    fila1_col1, fila1_col2, fila1_col3 = (
        st.columns(
            [
                1.35,
                1,
                1,
            ]
        )
    )

    with fila1_col1:

        st.markdown(
            "#### Evolución mensual"
        )

        metrica_evolucion = st.selectbox(
            "Métrica",
            options=[
                "Unidades",
                "Tareas",
                "Volumen m³",
                "Peso kg",
                "Horas",
            ],
            label_visibility="collapsed",
            key="metrica_evolucion",
        )

        evolucion = (
            tareas_evolucion
            .assign(
                Periodo=lambda tabla: (
                    tabla["Fecha"]
                    .dt.to_period("M")
                    .dt.to_timestamp()
                )
            )
            .groupby(
                [
                    "Periodo",
                    "Proceso",
                ],
                as_index=False,
            )
            .agg(
                Tareas=("ClaveTarea", "nunique"),
                Unidades=(
                    "UnidadesAnalisis",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenTotalM3",
                    "sum",
                ),
                PesoKg=(
                    "PesoTotalKg",
                    "sum",
                ),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
        )

        evolucion["Horas"] = (
            evolucion["Segundos"]
            / 3600
        )

        mapa_metricas = {
            "Unidades": "Unidades",
            "Tareas": "Tareas",
            "Volumen m³": "VolumenM3",
            "Peso kg": "PesoKg",
            "Horas": "Horas",
        }

        columna_metrica = mapa_metricas[
            metrica_evolucion
        ]

        evolucion["Mes"] = (
            evolucion["Periodo"]
            .dt.month
            .map(MESES_CORTOS)
            + " "
            + evolucion["Periodo"]
            .dt.year
            .astype(str)
        )

        fig_evolucion = px.line(
            evolucion,
            x="Mes",
            y=columna_metrica,
            color="Proceso",
            markers=True,
            labels={
                columna_metrica: metrica_evolucion,
                "Mes": "",
                "Proceso": "Proceso",
            },
        )

        fig_evolucion.update_traces(
            line_width=3,
            marker_size=8,
            textposition="top center",
        )

        fig_evolucion.update_layout(
            height=360,
            margin=dict(
                l=10,
                r=10,
                t=20,
                b=10,
            ),
            legend_title_text="",
            hovermode="x unified",
            xaxis_title="",
            yaxis_title=metrica_evolucion,
        )

        fig_evolucion.update_yaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        st.plotly_chart(
            fig_evolucion,
            width="stretch",
        )

    with fila1_col2:

        st.markdown(
            "#### Mix de categorías"
        )

        categoria_mix = st.selectbox(
            label="",
            options=["Familia", "Sector"],
            index=1,
            key="categoria_mix",
            label_visibility="collapsed",
        )

        if categoria_mix == "Sector":

            columna_mix = "Sectorizacion"
            valor_sin_categoria = "SIN SECTORIZACIÓN"

        else:

            columna_mix = "FamiliaFinal"
            valor_sin_categoria = "SIN FAMILIA"

        mix_categorias = (
            detalle_filtrado
            .assign(
                CategoriaMix=lambda tabla: (
                    tabla[columna_mix]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        valor_sin_categoria,
                    )
                )
            )
            .groupby(
                "CategoriaMix",
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
        )

        if len(mix_categorias) > 7:

            principales = mix_categorias.head(6)

            otros = pd.DataFrame(
                {
                    "CategoriaMix": ["OTROS"],
                    "UnidadesDetalle": [
                        mix_categorias.iloc[
                            6:
                        ]["UnidadesDetalle"].sum()
                    ],
                }
            )

            mix_categorias = pd.concat(
                [
                    principales,
                    otros,
                ],
                ignore_index=True,
            )

        fig_mix = px.pie(
            mix_categorias,
            names="CategoriaMix",
            values="UnidadesDetalle",
            hole=0.55,
        )

        fig_mix.update_traces(
            textposition="inside",
            textinfo="percent",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Unidades: %{value:,.0f}<br>"
                "Participación: %{percent}"
                "<extra></extra>"
            ),
        )

        fig_mix.update_layout(
            height=360,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            legend_title_text="",
            legend=dict(
                orientation="v",
                x=1.02,
                y=0.5,
            ),
        )

        st.plotly_chart(
            fig_mix,
            width="stretch",
        )

    with fila1_col3:

        st.markdown(
            "#### Insights automáticos"
        )

        insights = construir_insights(
            tareas=tareas_filtradas,
            detalle=detalle_filtrado,
            indicadores_actuales=actual,
            indicadores_anteriores=anterior,
        )

        for insight in insights[:4]:

            mostrar_insight(
                insight
            )

    fila2_col1, fila2_col2, fila2_col3 = (
        st.columns(
            [
                1.2,
                1,
                1,
            ]
        )
    )

    with fila2_col1:

        # Sin filtro de familia, el ranking principal
        # muestra únicamente artículos de Grifería.
        if filtro_familias:

            detalle_top = detalle_filtrado.copy()

            titulo_top = (
                "Top 15 artículos — "
                + ", ".join(filtro_familias)
            )

        else:

            detalle_top = detalle_filtrado[
                detalle_filtrado["FamiliaFinal"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("GRIFERIA")
            ].copy()

            titulo_top = "Top 15 artículos — Grifería"

        st.markdown(
            f"#### {titulo_top}"
        )

        top_articulos = (
            detalle_top
            .groupby(
                [
                    "CodigoArticulo",
                    "DescripcionFinal",
                ],
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
            .head(15)
        )

        top_articulos["Articulo"] = (
            top_articulos["CodigoArticulo"]
            + " · "
            + top_articulos[
                "DescripcionFinal"
            ].str.slice(
                0,
                32,
            )
        )

        fig_top = px.bar(
            top_articulos.sort_values(
                "UnidadesDetalle"
            ),
            x="UnidadesDetalle",
            y="Articulo",
            orientation="h",
            labels={
                "UnidadesDetalle": "Unidades",
                "Articulo": "",
            },
        )

        fig_top.update_traces(
            texttemplate="%{x:,.0f}",
            textposition="outside",
            cliponaxis=False,
        )

        fig_top.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=35,
                t=15,
                b=10,
            ),
            showlegend=False,
            xaxis_title="Unidades",
            yaxis_title="",
        )

        fig_top.update_xaxes(
            gridcolor="rgba(128,128,128,0.18)",
        )

        st.plotly_chart(
            fig_top,
            width="stretch",
        )

    with fila2_col2:

        st.markdown(
            "#### Carga operativa por día"
        )

        metrica_dia = st.selectbox(
            "Métrica",
            options=[
                "Promedio de unidades",
                "Promedio de horas",
                "Unidades/hora",
            ],
            label_visibility="collapsed",
            key="metrica_carga_dia",
        )

        base_dia = tareas_filtradas.copy()

        base_dia["FechaDia"] = pd.to_datetime(
            base_dia["Fecha"],
            errors="coerce",
        ).dt.normalize()

        resumen_fecha = (
            base_dia
            .groupby(
                [
                    "FechaDia",
                    "DiaSemana",
                ],
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=("TiempoRealSegundos", "sum"),
            )
        )

        resumen_fecha["Horas"] = (
            resumen_fecha["Segundos"]
            / 3600
        )

        resumen_fecha["UnidadesHora"] = (
            resumen_fecha["Unidades"]
            / resumen_fecha["Horas"].replace(
                0,
                np.nan,
            )
        )

        carga_dia = (
            resumen_fecha
            .groupby(
                "DiaSemana",
                as_index=False,
            )
            .agg(
                PromedioUnidades=("Unidades", "mean"),
                PromedioHoras=("Horas", "mean"),
                UnidadesHora=("UnidadesHora", "mean"),
            )
        )

        carga_dia["DiaSemana"] = pd.Categorical(
            carga_dia["DiaSemana"],
            categories=ORDEN_DIAS,
            ordered=True,
        )

        carga_dia = carga_dia.sort_values(
            "DiaSemana"
        )

        mapa_dia = {
            "Promedio de unidades": (
                "PromedioUnidades",
                "Unidades promedio",
            ),
            "Promedio de horas": (
                "PromedioHoras",
                "Horas promedio",
            ),
            "Unidades/hora": (
                "UnidadesHora",
                "Unidades/hora",
            ),
        }

        columna_dia, etiqueta_dia = mapa_dia[
            metrica_dia
        ]

        fig_carga = px.bar(
            carga_dia,
            x="DiaSemana",
            y=columna_dia,
            text_auto=".1f",
            labels={
                "DiaSemana": "",
                columna_dia: etiqueta_dia,
            },
        )

        fig_carga.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig_carga.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
            yaxis_title=etiqueta_dia,
            xaxis_title="",
        )

        fig_carga.update_yaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        st.plotly_chart(
            fig_carga,
            width="stretch",
        )


    with fila2_col3:

        st.markdown(
            "#### Productividad por familia"
        )

        productividad_familia = (
            tareas_filtradas
            .assign(
                Familia=lambda tabla: (
                    tabla["FamiliaPrincipal"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        "SIN FAMILIA",
                    )
                )
            )
            .groupby(
                "Familia",
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=("TiempoRealSegundos", "sum"),
                Tareas=("ClaveTarea", "nunique"),
            )
        )

        productividad_familia["Horas"] = (
            productividad_familia["Segundos"]
            / 3600
        )

        productividad_familia["UnidadesHora"] = (
            productividad_familia["Unidades"]
            / productividad_familia["Horas"].replace(
                0,
                np.nan,
            )
        )

        productividad_familia = (
            productividad_familia
            .dropna(
                subset=["UnidadesHora"]
            )
            .sort_values(
                "UnidadesHora",
                ascending=False,
            )
            .head(10)
        )

        fig_prod_familia = px.bar(
            productividad_familia.sort_values(
                "UnidadesHora"
            ),
            x="UnidadesHora",
            y="Familia",
            orientation="h",
            text_auto=".1f",
            labels={
                "UnidadesHora": "Unidades/hora",
                "Familia": "",
            },
        )

        fig_prod_familia.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig_prod_familia.update_layout(
            height=460,
            margin=dict(
                l=10,
                r=35,
                t=15,
                b=10,
            ),
            showlegend=False,
            xaxis_title="Unidades/hora",
            yaxis_title="",
        )

        fig_prod_familia.update_xaxes(
            rangemode="tozero",
            gridcolor="rgba(128,128,128,0.18)",
        )

        st.plotly_chart(
            fig_prod_familia,
            width="stretch",
        )


# ==========================================================
# PRODUCTIVIDAD
# ==========================================================

if vista_principal == "⚡ Productividad":

    prod1, prod2 = st.columns(2)

    with prod1:

        st.markdown(
            "#### Productividad por proceso"
        )

        productividad_proceso = (
            tareas_filtradas
            .groupby(
                "Proceso",
                as_index=False,
            )
            .agg(
                Unidades=(
                    "UnidadesAnalisis",
                    "sum",
                ),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenTotalM3",
                    "sum",
                ),
            )
        )

        productividad_proceso[
            "UnidadesHora"
        ] = (
            productividad_proceso[
                "Unidades"
            ]
            / (
                productividad_proceso[
                    "Segundos"
                ]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        productividad_proceso[
            "M3Hora"
        ] = (
            productividad_proceso[
                "VolumenM3"
            ]
            / (
                productividad_proceso[
                    "Segundos"
                ]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        fig_prod_proceso = px.bar(
            productividad_proceso,
            x="Proceso",
            y="UnidadesHora",
            text_auto=".1f",
            labels={
                "Proceso": "",
                "UnidadesHora": "Unidades/hora",
            },
        )

        fig_prod_proceso.update_layout(
            height=340,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        st.plotly_chart(
            fig_prod_proceso,
            width="stretch",
        )

    with prod2:

        st.markdown(
            "#### Tiempo promedio por proceso"
        )

        tiempo_proceso = (
            tareas_filtradas
            .groupby(
                "Proceso",
                as_index=False,
            )
            .agg(
                TiempoPromedioSegundos=(
                    "TiempoRealSegundos",
                    "mean",
                ),
            )
        )

        tiempo_proceso[
            "TiempoPromedioMinutos"
        ] = (
            tiempo_proceso[
                "TiempoPromedioSegundos"
            ]
            / 60
        )

        fig_tiempo = px.bar(
            tiempo_proceso,
            x="Proceso",
            y="TiempoPromedioMinutos",
            text_auto=".1f",
            labels={
                "Proceso": "",
                "TiempoPromedioMinutos": (
                    "Minutos promedio"
                ),
            },
        )

        fig_tiempo.update_layout(
            height=340,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        st.plotly_chart(
            fig_tiempo,
            width="stretch",
        )

    st.markdown(
        "#### Ranking de productividad por usuario"
    )

    ranking_usuario = (
        tareas_filtradas
        .groupby(
            [
                "Proceso",
                "Usuario",
            ],
            as_index=False,
        )
        .agg(
            Tareas=("ClaveTarea", "nunique"),
            Unidades=(
                "UnidadesAnalisis",
                "sum",
            ),
            VolumenM3=(
                "VolumenTotalM3",
                "sum",
            ),
            Segundos=(
                "TiempoRealSegundos",
                "sum",
            ),
        )
    )

    ranking_usuario["Horas"] = (
        ranking_usuario["Segundos"]
        / 3600
    )

    ranking_usuario["UnidadesHora"] = (
        ranking_usuario["Unidades"]
        / ranking_usuario["Horas"].replace(
            0,
            np.nan,
        )
    )

    ranking_usuario["M3Hora"] = (
        ranking_usuario["VolumenM3"]
        / ranking_usuario["Horas"].replace(
            0,
            np.nan,
        )
    )

    ranking_usuario = ranking_usuario.sort_values(
        "UnidadesHora",
        ascending=False,
    )

    st.dataframe(
        ranking_usuario,
        width="stretch",
        hide_index=True,
        column_config={
            "Horas": (
                st.column_config.NumberColumn(
                    "Horas",
                    format="%.2f",
                )
            ),
            "UnidadesHora": (
                st.column_config.ProgressColumn(
                    "Unidades/hora",
                    min_value=0,
                    max_value=max(
                        float(
                            ranking_usuario[
                                "UnidadesHora"
                            ].max()
                        ),
                        1,
                    ),
                    format="%.1f",
                )
            ),
            "M3Hora": (
                st.column_config.NumberColumn(
                    "m³/hora",
                    format="%.3f",
                )
            ),
        },
    )

    st.markdown(
        "#### Productividad por hora del día"
    )

    productividad_hora = (
        tareas_filtradas
        .assign(
            Hora=lambda tabla: (
                pd.to_datetime(
                    tabla["HoraInicio"],
                    format="%H:%M:%S",
                    errors="coerce",
                ).dt.hour
            )
        )
        .dropna(
            subset=["Hora"]
        )
        .groupby(
            [
                "Hora",
                "Proceso",
            ],
            as_index=False,
        )
        .agg(
            Unidades=(
                "UnidadesAnalisis",
                "sum",
            ),
            Segundos=(
                "TiempoRealSegundos",
                "sum",
            ),
        )
    )

    productividad_hora[
        "UnidadesHora"
    ] = (
        productividad_hora[
            "Unidades"
        ]
        / (
            productividad_hora[
                "Segundos"
            ]
            / 3600
        ).replace(
            0,
            np.nan,
        )
    )

    fig_hora = px.line(
        productividad_hora,
        x="Hora",
        y="UnidadesHora",
        color="Proceso",
        markers=True,
        labels={
            "Hora": "Hora del día",
            "UnidadesHora": "Unidades/hora",
            "Proceso": "Proceso",
        },
    )

    fig_hora.update_layout(
        height=380,
        margin=dict(
            l=10,
            r=10,
            t=15,
            b=10,
        ),
        legend_title_text="",
    )

    st.plotly_chart(
        fig_hora,
        width="stretch",
    )


# ==========================================================
# PRODUCTOS
# ==========================================================

if vista_principal == "📦 Productos":

    producto1, producto2 = st.columns(2)

    with producto1:

        st.markdown(
            "#### Familias por unidades"
        )

        familias = (
            detalle_filtrado
            .assign(
                Familia=lambda tabla: (
                    tabla["FamiliaFinal"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        "SIN FAMILIA",
                    )
                )
            )
            .groupby(
                "Familia",
                as_index=False,
            )
            .agg(
                Unidades=(
                    "UnidadesDetalle",
                    "sum",
                ),
                VolumenM3=(
                    "VolumenLineaM3",
                    "sum",
                ),
                PesoKg=(
                    "PesoLineaKg",
                    "sum",
                ),
            )
            .sort_values(
                "Unidades",
                ascending=False,
            )
        )

        fig_familias = px.bar(
            familias.head(15).sort_values(
                "Unidades"
            ),
            x="Unidades",
            y="Familia",
            orientation="h",
            labels={
                "Familia": "",
                "Unidades": "Unidades",
            },
        )

        fig_familias.update_layout(
            height=450,
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        st.plotly_chart(
            fig_familias,
            width="stretch",
        )

    with producto2:

        st.markdown(
            "#### Curva ABC por unidades"
        )

        abc = (
            detalle_filtrado
            .groupby(
                [
                    "CodigoArticulo",
                    "DescripcionFinal",
                ],
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
            .reset_index(drop=True)
        )

        total_abc = abc[
            "UnidadesDetalle"
        ].sum()

        abc["AcumuladoPct"] = (
            abc["UnidadesDetalle"]
            .cumsum()
            / max(
                total_abc,
                1,
            )
            * 100
        )

        abc["ArticuloPct"] = (
            (
                np.arange(
                    1,
                    len(abc) + 1,
                )
                / max(
                    len(abc),
                    1,
                )
            )
            * 100
        )

        abc["ClaseABC"] = np.select(
            [
                abc["AcumuladoPct"] <= 80,
                abc["AcumuladoPct"] <= 95,
            ],
            [
                "A",
                "B",
            ],
            default="C",
        )

        fig_abc = go.Figure()

        fig_abc.add_trace(
            go.Scatter(
                x=abc["ArticuloPct"],
                y=abc["AcumuladoPct"],
                mode="lines",
                name="% acumulado",
            )
        )

        fig_abc.add_hline(
            y=80,
            line_dash="dash",
        )

        fig_abc.add_hline(
            y=95,
            line_dash="dash",
        )

        fig_abc.update_layout(
            height=450,
            xaxis_title="% de artículos",
            yaxis_title="% acumulado de unidades",
            margin=dict(
                l=10,
                r=10,
                t=15,
                b=10,
            ),
            showlegend=False,
        )

        st.plotly_chart(
            fig_abc,
            width="stretch",
        )

    st.markdown(
        "#### Ranking de artículos"
    )

    ranking_articulos = (
        detalle_filtrado
        .groupby(
            [
                "CodigoArticulo",
                "DescripcionFinal",
                "FamiliaFinal",
            ],
            as_index=False,
        )
        .agg(
            Unidades=("UnidadesDetalle", "sum"),
            VolumenM3=(
                "VolumenLineaM3",
                "sum",
            ),
            PesoKg=(
                "PesoLineaKg",
                "sum",
            ),
            Tareas=("ClaveTarea", "nunique"),
        )
        .sort_values(
            "Unidades",
            ascending=False,
        )
    )

    st.dataframe(
        ranking_articulos,
        width="stretch",
        hide_index=True,
        column_config={
            "VolumenM3": (
                st.column_config.NumberColumn(
                    "Volumen m³",
                    format="%.3f",
                )
            ),
            "PesoKg": (
                st.column_config.NumberColumn(
                    "Peso kg",
                    format="%.2f",
                )
            ),
        },
    )


# ==========================================================
# INSIGHTS
# ==========================================================

if vista_principal == "💡 Insights":

    st.subheader(
        "💡 Insights automáticos"
    )

    st.caption(
        "Conclusiones calculadas sobre los datos filtrados. "
        "Esta será la base del futuro analista con IA."
    )

    insights = construir_insights(
        tareas=tareas_filtradas,
        detalle=detalle_filtrado,
        indicadores_actuales=actual,
        indicadores_anteriores=anterior,
    )

    insight_col1, insight_col2 = st.columns(2)

    for indice, insight in enumerate(
        insights
    ):

        with (
            insight_col1
            if indice % 2 == 0
            else insight_col2
        ):

            mostrar_insight(
                insight
            )

    st.markdown(
        "#### Tareas fuera de comportamiento"
    )

    tareas_anomalias = (
        tareas_filtradas[
            [
                "Proceso",
                "TareaId",
                "Fecha",
                "Usuario",
                "FamiliaPrincipal",
                "UnidadesAnalisis",
                "TiempoRealSegundos",
                "SegundosPorUnidad",
                "NivelComplejidad",
                "VolumenTotalM3",
                "ArchivoOrigen",
            ]
        ]
        .copy()
    )

    mediana = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .median()
    )

    q3 = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .quantile(0.75)
    )

    q1 = (
        tareas_anomalias[
            "SegundosPorUnidad"
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan,
        )
        .quantile(0.25)
    )

    limite_anomalia = (
        q3
        + 1.5
        * (q3 - q1)
    )

    tareas_anomalias["Motivo"] = np.where(
        tareas_anomalias[
            "SegundosPorUnidad"
        ] > limite_anomalia,
        "Tiempo por unidad fuera de rango",
        "",
    )

    tareas_anomalias = (
        tareas_anomalias[
            tareas_anomalias[
                "Motivo"
            ].ne("")
        ]
        .sort_values(
            "SegundosPorUnidad",
            ascending=False,
        )
        .head(100)
    )

    st.caption(
        f"Mediana: {mediana:.2f} s/unidad · "
        f"Límite estadístico: {limite_anomalia:.2f} s/unidad"
    )

    st.dataframe(
        tareas_anomalias,
        width="stretch",
        hide_index=True,
    )

# ==========================================================
# DATOS, TABLAS Y CONTROLES TÉCNICOS
# ==========================================================

st.divider()

mostrar_datos_tecnicos = st.toggle(
    "🧪 Cargar datos, tablas y controles de calidad",
    value=False,
    help=(
        "Activalo únicamente cuando necesites revisar "
        "las tablas detalladas. Esto evita procesar miles "
        "de registros durante la navegación normal."
    ),
)

if mostrar_datos_tecnicos:

    st.caption(
        "El tablero excluye registros sin sectorización y "
        "registros con Sectorización = NO APLICA."
    )

    st.caption(
        "Esta sección conserva la información técnica utilizada "
        "para validar el tablero, revisar los cruces y analizar "
        "los datos a nivel de registro."
    )

    (
        sub_tareas,
        sub_detalle,
        sub_resumen,
        sub_calidad,
        sub_cobertura,
        sub_crudos,
    ) = st.tabs(
        [
            "📋 Tareas enriquecidas",
            "📦 Detalle enriquecido",
            "📊 Resúmenes",
            "🧪 Calidad ETL",
            "📚 Cobertura de maestros",
            "🗂️ Fuentes crudas",
        ]
    )

    # ------------------------------------------------------
    # TAREAS ENRIQUECIDAS
    # ------------------------------------------------------

    with sub_tareas:

        st.markdown(
            "#### Una fila por tarea"
        )

        st.caption(
            f"{len(tareas_filtradas):,} tareas según los filtros "
            "aplicados."
        )

        columnas_tareas_tabla = [
            "Proceso",
            "TareaId",
            "Fecha",
            "Usuario",
            "Tipo",
            "UnidadesAnalisis",
            "ArticulosDetalle",
            "LineasDetalle",
            "FamiliaPrincipal",
            "Familia2Principal",
            "SectorizacionPrincipal",
            "VolumenTotalM3",
            "PesoTotalKg",
            "TiempoEstimadoSegundos",
            "TiempoRealSegundos",
            "UnidadesPorHora",
            "ArticulosPorHora",
            "LineasPorHora",
            "M3PorHora",
            "KgPorHora",
            "SegundosPorUnidad",
            "SegundosPorArticulo",
            "NivelComplejidad",
            "CoberturaMaestroPct",
            "CoberturaVolumetriaPct",
            "ArchivoOrigen",
        ]

        columnas_tareas_tabla = [
            columna
            for columna in columnas_tareas_tabla
            if columna in tareas_filtradas.columns
        ]

        st.dataframe(
            limitar_previsualizacion(
                tareas_filtradas[
                    columnas_tareas_tabla
                ],
                limite=5000,
            ),
            width="stretch",
            hide_index=True,
            column_config={
                "VolumenTotalM3": (
                    st.column_config.NumberColumn(
                        "Volumen total m³",
                        format="%.3f",
                    )
                ),
                "PesoTotalKg": (
                    st.column_config.NumberColumn(
                        "Peso total kg",
                        format="%.2f",
                    )
                ),
                "UnidadesPorHora": (
                    st.column_config.NumberColumn(
                        "Unidades/hora",
                        format="%.2f",
                    )
                ),
                "M3PorHora": (
                    st.column_config.NumberColumn(
                        "m³/hora",
                        format="%.3f",
                    )
                ),
                "KgPorHora": (
                    st.column_config.NumberColumn(
                        "kg/hora",
                        format="%.2f",
                    )
                ),
                "CoberturaMaestroPct": (
                    st.column_config.ProgressColumn(
                        "Cobertura artículos",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    )
                ),
                "CoberturaVolumetriaPct": (
                    st.column_config.ProgressColumn(
                        "Cobertura volumetría",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    )
                ),
            },
        )

    # ------------------------------------------------------
    # DETALLE ENRIQUECIDO
    # ------------------------------------------------------

    with sub_detalle:

        st.markdown(
            "#### Una fila por artículo dentro de cada tarea"
        )

        st.caption(
            f"{len(detalle_filtrado):,} líneas según los filtros "
            "aplicados."
        )

        columnas_detalle_tabla = [
            "Proceso",
            "TareaId",
            "Fecha",
            "Usuario",
            "CodigoArticulo",
            "DescripcionFinal",
            "UnidadesDetalle",
            "FamiliaFinal",
            "Familia2",
            "Rubro",
            "Marca",
            "Origen",
            "Gama",
            "Sector",
            "Sectorizacion",
            "Ubicacion",
            "VolumenM3",
            "PesoKg",
            "VolumenLineaM3",
            "PesoLineaKg",
            "SegundosEnPickear",
            "SegundosPorUnidadLinea",
            "TieneMaestroArticulo",
            "TieneVolumetria",
            "ArchivoOrigen",
        ]

        columnas_detalle_tabla = [
            columna
            for columna in columnas_detalle_tabla
            if columna in detalle_filtrado.columns
        ]

        st.dataframe(
            limitar_previsualizacion(
                detalle_filtrado[
                    columnas_detalle_tabla
                ],
                limite=5000,
            ),
            width="stretch",
            hide_index=True,
            column_config={
                "VolumenM3": (
                    st.column_config.NumberColumn(
                        "Volumen unitario m³",
                        format="%.6f",
                    )
                ),
                "PesoKg": (
                    st.column_config.NumberColumn(
                        "Peso unitario kg",
                        format="%.3f",
                    )
                ),
                "VolumenLineaM3": (
                    st.column_config.NumberColumn(
                        "Volumen línea m³",
                        format="%.6f",
                    )
                ),
                "PesoLineaKg": (
                    st.column_config.NumberColumn(
                        "Peso línea kg",
                        format="%.3f",
                    )
                ),
            },
        )

    # ------------------------------------------------------
    # RESÚMENES TÉCNICOS
    # ------------------------------------------------------

    with sub_resumen:

        st.markdown(
            "#### Resumen por proceso"
        )

        resumen_tecnico_proceso = (
            tareas_filtradas
            .groupby(
                "Proceso",
                as_index=False,
                dropna=False,
            )
            .agg(
                Tareas=("ClaveTarea", "nunique"),
                Usuarios=("Usuario", "nunique"),
                Unidades=("UnidadesAnalisis", "sum"),
                Articulos=("ArticulosDetalle", "sum"),
                Lineas=("LineasDetalle", "sum"),
                VolumenM3=("VolumenTotalM3", "sum"),
                PesoKg=("PesoTotalKg", "sum"),
                TiempoRealSegundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
        )

        resumen_tecnico_proceso["HorasReales"] = (
            resumen_tecnico_proceso[
                "TiempoRealSegundos"
            ]
            / 3600
        ).round(2)

        resumen_tecnico_proceso["UnidadesHora"] = (
            resumen_tecnico_proceso["Unidades"]
            / resumen_tecnico_proceso[
                "HorasReales"
            ].replace(0, np.nan)
        ).round(2)

        resumen_tecnico_proceso["M3Hora"] = (
            resumen_tecnico_proceso["VolumenM3"]
            / resumen_tecnico_proceso[
                "HorasReales"
            ].replace(0, np.nan)
        ).round(3)

        st.dataframe(
            resumen_tecnico_proceso,
            width="stretch",
            hide_index=True,
        )

        st.markdown(
            "#### Resumen por familia principal"
        )

        resumen_tecnico_familia = (
            tareas_filtradas
            .assign(
                FamiliaPrincipal=lambda tabla: (
                    tabla["FamiliaPrincipal"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace("", "SIN FAMILIA")
                )
            )
            .groupby(
                [
                    "Proceso",
                    "FamiliaPrincipal",
                ],
                as_index=False,
            )
            .agg(
                Tareas=("ClaveTarea", "nunique"),
                Unidades=("UnidadesAnalisis", "sum"),
                VolumenM3=("VolumenTotalM3", "sum"),
                PesoKg=("PesoTotalKg", "sum"),
                TiempoRealSegundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
            .sort_values(
                [
                    "Proceso",
                    "Unidades",
                ],
                ascending=[
                    True,
                    False,
                ],
            )
        )

        resumen_tecnico_familia["HorasReales"] = (
            resumen_tecnico_familia[
                "TiempoRealSegundos"
            ]
            / 3600
        ).round(2)

        st.dataframe(
            resumen_tecnico_familia,
            width="stretch",
            hide_index=True,
        )

        st.markdown(
            "#### Resumen por nivel de complejidad"
        )

        resumen_tecnico_complejidad = (
            tareas_filtradas
            .groupby(
                [
                    "Proceso",
                    "NivelComplejidad",
                ],
                as_index=False,
                dropna=False,
            )
            .agg(
                Tareas=("ClaveTarea", "nunique"),
                Unidades=("UnidadesAnalisis", "sum"),
                VolumenM3=("VolumenTotalM3", "sum"),
                Horas=(
                    "TiempoRealSegundos",
                    lambda serie: serie.sum() / 3600,
                ),
            )
        )

        st.dataframe(
            resumen_tecnico_complejidad,
            width="stretch",
            hide_index=True,
        )

    # ------------------------------------------------------
    # CALIDAD ETL
    # ------------------------------------------------------

    with sub_calidad:

        st.markdown(
            "#### Controles de limpieza y homologación"
        )

        st.dataframe(
            etl["calidad"],
            width="stretch",
            hide_index=True,
        )

        st.markdown(
            "#### Diferencias de unidades por tarea"
        )

        diferencias_unidades = (
            tareas_filtradas[
                [
                    "Proceso",
                    "TareaId",
                    "UnidadesTarea",
                    "UnidadesDetalleTotal",
                    "UnidadesAnalisis",
                    "ArchivoOrigen",
                ]
            ]
            .copy()
        )

        diferencias_unidades[
            "DiferenciaUnidades"
        ] = (
            pd.to_numeric(
                diferencias_unidades[
                    "UnidadesTarea"
                ],
                errors="coerce",
            )
            .fillna(0)
            - pd.to_numeric(
                diferencias_unidades[
                    "UnidadesDetalleTotal"
                ],
                errors="coerce",
            )
            .fillna(0)
        )

        diferencias_unidades = (
            diferencias_unidades[
                diferencias_unidades[
                    "DiferenciaUnidades"
                ].abs() > 0.001
            ]
            .sort_values(
                "DiferenciaUnidades",
                key=lambda serie: serie.abs(),
                ascending=False,
            )
        )

        st.dataframe(
            diferencias_unidades,
            width="stretch",
            hide_index=True,
        )

    # ------------------------------------------------------
    # COBERTURA DE MAESTROS
    # ------------------------------------------------------

    with sub_cobertura:

        st.markdown(
            "#### Indicadores de cobertura"
        )

        st.dataframe(
            df_calidad_enriquecimiento,
            width="stretch",
            hide_index=True,
        )

        cobertura_col1, cobertura_col2 = (
            st.columns(2)
        )

        with cobertura_col1:

            st.markdown(
                "#### Artículos sin Maestro Artículo"
            )

            sin_maestro = (
                detalle_filtrado[
                    ~detalle_filtrado[
                        "TieneMaestroArticulo"
                    ]
                ]
                [
                    [
                        "CodigoArticulo",
                        "DescripcionArticulo",
                        "Proceso",
                        "ArchivoOrigen",
                    ]
                ]
                .drop_duplicates()
                .sort_values(
                    "CodigoArticulo"
                )
            )

            st.dataframe(
                sin_maestro,
                width="stretch",
                hide_index=True,
            )

        with cobertura_col2:

            st.markdown(
                "#### Artículos sin volumetría"
            )

            sin_volumetria = (
                detalle_filtrado[
                    ~detalle_filtrado[
                        "TieneVolumetria"
                    ]
                ]
                [
                    [
                        "CodigoArticulo",
                        "DescripcionFinal",
                        "FamiliaFinal",
                        "Proceso",
                        "ArchivoOrigen",
                    ]
                ]
                .drop_duplicates()
                .sort_values(
                    "CodigoArticulo"
                )
            )

            st.dataframe(
                sin_volumetria,
                width="stretch",
                hide_index=True,
            )

    # ------------------------------------------------------
    # FUENTES CRUDAS
    # ------------------------------------------------------

    with sub_crudos:

        (
            crudo_control,
            crudo_preparacion,
            crudo_articulos,
            crudo_volumetria,
        ) = st.tabs(
            [
                "✅ Control",
                "📦 Preparación",
                "📚 Maestro Artículo",
                "📐 Maestro Volumetría",
            ]
        )

        with crudo_control:

            st.caption(
                f"{len(fuentes['control']):,} registros · "
                f"{len(fuentes['control'].columns):,} columnas"
            )

            st.dataframe(
                limitar_previsualizacion(
                    fuentes["control"],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
            )

        with crudo_preparacion:

            st.caption(
                f"{len(fuentes['preparacion']):,} registros · "
                f"{len(fuentes['preparacion'].columns):,} columnas"
            )

            st.dataframe(
                limitar_previsualizacion(
                    fuentes["preparacion"],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
            )

        with crudo_articulos:

            st.caption(
                f"{len(datos['df_articulos']):,} registros · "
                f"{len(datos['df_articulos'].columns):,} columnas"
            )

            st.dataframe(
                limitar_previsualizacion(
                    datos["df_articulos"],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
            )

        with crudo_volumetria:

            st.caption(
                f"{len(datos['tabla_volumetria']):,} artículos"
            )

            st.dataframe(
                limitar_previsualizacion(
                    datos["tabla_volumetria"],
                    limite=5000,
                ),
                width="stretch",
                hide_index=True,
            )
