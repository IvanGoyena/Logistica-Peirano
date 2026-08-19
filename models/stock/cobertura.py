from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st

from utils.inventario.exclusiones import filtrar_articulos_fuera_inventario



# ==========================================================
# UTILIDADES
# ==========================================================

def _clave(texto: object) -> str:
    valor = unicodedata.normalize("NFKD", str(texto))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", valor.lower().strip())


def _buscar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None
    mapa = {_clave(columna): columna for columna in df.columns}
    for candidato in candidatos:
        encontrada = mapa.get(_clave(candidato))
        if encontrada is not None:
            return encontrada
    return None


def _codigo(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def _numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0)
    texto = (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
    )
    con_coma = texto.str.contains(",", regex=False)
    texto.loc[con_coma] = (
        texto.loc[con_coma]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(texto, errors="coerce").fillna(0)


def _serie(df: pd.DataFrame, candidatos: list[str], default=0) -> pd.Series:
    columna = _buscar_columna(df, candidatos)
    if columna is None:
        return pd.Series(default, index=df.index)
    return df[columna]


# ==========================================================
# HISTÓRICO DE MÉTRICAS
# ==========================================================

@st.cache_data(
    max_entries=3,
    persist="disk",
    show_spinner="Leyendo base histórica para cobertura...",
)
def cargar_historico_ventas_stock(
    firma_base_historica: tuple,
) -> pd.DataFrame:
    """
    Consume la base Parquet publicada por el módulo de Métricas.

    Stock ya no lee archivos mensuales, no ejecuta la ETL y no vuelve
    a enriquecer todo el histórico. La firma del Parquet forma parte
    de la clave de caché y fuerza la recarga solamente cuando Métricas
    publica una nueva versión.
    """

    _ = firma_base_historica

    from models.base_historica_metricas import (
        leer_base_historica_metricas,
    )

    columnas_detalle = [
        "Proceso",
        "ClaveTarea",
        "TareaId",
        "TareaID",
        "Fecha",
        "FechaInicio",
        "FechaPickeo",
        "CodigoArticulo",
        "ArticuloCodigo",
        "Código Artículo",
        "Codigo",
        "UnidadesDetalle",
        "Cantidad",
        "Unidades",
        "CantidadPreparada",
        "DescripcionFinal",
        "ArticuloDescripcion",
        "Descripcion",
        "Descripción",
        "FamiliaFinal",
        "Familia",
        "FamiliaPrincipal",
        "Sectorizacion",
        "Sectorización",
        "SectorizacionPrincipal",
    ]

    columnas_tareas = [
        "Proceso",
        "ClaveTarea",
        "TareaId",
        "TareaID",
        "Fecha",
        "FechaInicio",
    ]

    base = leer_base_historica_metricas(
        columnas_detalle=columnas_detalle,
        columnas_tareas=columnas_tareas,
        incluir_detalle=True,
        incluir_tareas=True,
    )

    detalle = base.get(
        "detalle",
        pd.DataFrame(),
    ).copy()

    tareas = base.get(
        "tareas",
        pd.DataFrame(),
    ).copy()

    if detalle.empty:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
                "UnidadesVendidas",
            ]
        )

    proceso_detalle = _buscar_columna(
        detalle,
        ["Proceso", "TipoProceso"],
    )

    if proceso_detalle is not None:
        procesos = (
            detalle[proceso_detalle]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
        )
        mascara_preparacion = procesos.str.contains(
            "PREPAR",
            na=False,
        )
        if mascara_preparacion.any():
            detalle = detalle.loc[
                mascara_preparacion
            ].copy()

    fecha_col = _buscar_columna(
        detalle,
        ["Fecha", "FechaInicio", "FechaPickeo"],
    )

    # Compatibilidad con bases antiguas donde la fecha se encontraba
    # únicamente en la tabla de tareas.
    if fecha_col is None and not tareas.empty:
        clave_tarea = _buscar_columna(
            tareas,
            ["ClaveTarea", "TareaId", "TareaID"],
        )
        clave_detalle = _buscar_columna(
            detalle,
            ["ClaveTarea", "TareaId", "TareaID"],
        )
        fecha_tarea = _buscar_columna(
            tareas,
            ["Fecha", "FechaInicio"],
        )
        proceso_tarea = _buscar_columna(
            tareas,
            ["Proceso", "TipoProceso"],
        )

        if (
            clave_tarea is not None
            and clave_detalle is not None
            and fecha_tarea is not None
        ):
            tareas["_ClaveTareaCobertura"] = (
                tareas[clave_tarea]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            tareas["_FechaCobertura"] = pd.to_datetime(
                tareas[fecha_tarea],
                errors="coerce",
            ).dt.normalize()

            if proceso_tarea is not None:
                procesos = (
                    tareas[proceso_tarea]
                    .fillna("")
                    .astype(str)
                    .str.upper()
                    .str.strip()
                )
                mascara_preparacion = procesos.str.contains(
                    "PREPAR",
                    na=False,
                )
                if mascara_preparacion.any():
                    tareas = tareas.loc[
                        mascara_preparacion
                    ].copy()

            fechas = (
                tareas.loc[
                    tareas["_ClaveTareaCobertura"].ne("")
                    & tareas["_FechaCobertura"].notna(),
                    [
                        "_ClaveTareaCobertura",
                        "_FechaCobertura",
                    ],
                ]
                .drop_duplicates(
                    "_ClaveTareaCobertura",
                    keep="last",
                )
            )

            detalle["_ClaveTareaCobertura"] = (
                detalle[clave_detalle]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            detalle = detalle.merge(
                fechas,
                on="_ClaveTareaCobertura",
                how="inner",
                validate="many_to_one",
            )
            fecha_col = "_FechaCobertura"

    if fecha_col is None:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
                "UnidadesVendidas",
            ]
        )

    codigo_col = _buscar_columna(
        detalle,
        [
            "CodigoArticulo",
            "ArticuloCodigo",
            "Código Artículo",
            "Codigo",
        ],
    )
    unidades_col = _buscar_columna(
        detalle,
        [
            "UnidadesDetalle",
            "Cantidad",
            "Unidades",
            "CantidadPreparada",
        ],
    )
    descripcion_col = _buscar_columna(
        detalle,
        [
            "DescripcionFinal",
            "ArticuloDescripcion",
            "Descripcion",
            "Descripción",
        ],
    )
    familia_col = _buscar_columna(
        detalle,
        [
            "FamiliaFinal",
            "Familia",
            "FamiliaPrincipal",
        ],
    )
    sector_col = _buscar_columna(
        detalle,
        [
            "Sectorizacion",
            "Sectorización",
            "SectorizacionPrincipal",
        ],
    )

    if codigo_col is None or unidades_col is None:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
                "UnidadesVendidas",
            ]
        )

    salida = pd.DataFrame(index=detalle.index)
    salida["Fecha"] = pd.to_datetime(
        detalle[fecha_col],
        errors="coerce",
    ).dt.normalize()
    salida["ArticuloCodigo"] = _codigo(
        detalle[codigo_col]
    )
    salida["ArticuloDescripcion"] = (
        detalle[descripcion_col]
        .fillna("")
        .astype(str)
        .str.strip()
        if descripcion_col is not None
        else ""
    )
    salida["Familia"] = (
        detalle[familia_col]
        .fillna("")
        .astype(str)
        .str.strip()
        if familia_col is not None
        else ""
    )
    salida["Sectorizacion"] = (
        detalle[sector_col]
        .fillna("")
        .astype(str)
        .str.strip()
        if sector_col is not None
        else ""
    )
    salida["UnidadesVendidas"] = _numero(
        detalle[unidades_col]
    ).clip(lower=0)

    salida = salida.loc[
        salida["Fecha"].notna()
        & salida["ArticuloCodigo"].ne("")
        & salida["UnidadesVendidas"].gt(0)
    ].copy()

    return (
        salida
        .groupby(
            [
                "Fecha",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
            ],
            as_index=False,
            dropna=False,
        )["UnidadesVendidas"]
        .sum()
        .sort_values(
            ["Fecha", "ArticuloCodigo"]
        )
        .reset_index(drop=True)
    )


def _preparar_ingresos_por_articulo(
    stock_detallado: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Estima primer y último ingreso por artículo usando:

    1. FechaIngreso directa, cuando existe.
    2. FechaVencimiento - 2.000 días.
    3. Fecha actual - (2.000 - Días al vencimiento).

    La agregación se realiza sobre todos los contenedores actualmente
    presentes en el stock detallado.
    """
    columnas = [
        "ArticuloCodigo",
        "PrimerIngresoStockActual",
        "UltimoIngresoStockActual",
        "ContenedoresStockActual",
    ]

    if (
        stock_detallado is None
        or stock_detallado.empty
    ):
        return pd.DataFrame(columns=columnas)

    origen = stock_detallado.copy()

    codigo_col = _buscar_columna(
        origen,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "Código Artículo",
            "Codigo",
            "Artículo",
        ],
    )
    fecha_ingreso_col = _buscar_columna(
        origen,
        [
            "FechaIngreso",
            "FechaAlta",
            "Fecha Alta",
            "FechaIngresoStock",
            "Fecha de ingreso",
        ],
    )
    vencimiento_col = _buscar_columna(
        origen,
        [
            "FechaVencimiento",
            "Fecha Vencimiento",
            "Vencimiento",
        ],
    )
    dias_col = _buscar_columna(
        origen,
        [
            "DiasAlVencimiento",
            "Días al vencimiento",
            "DiasVencimiento",
            "Días vencimiento",
            "Dias",
            "Días",
        ],
    )
    contenedor_col = _buscar_columna(
        origen,
        [
            "Contenedor",
            "ContenedorNumero",
            "NumeroContenedor",
            "NroContenedor",
            "CodigoContenedor",
            "LPN",
            "SSCC",
        ],
    )

    if codigo_col is None:
        return pd.DataFrame(columns=columnas)

    detalle = pd.DataFrame(index=origen.index)
    detalle["ArticuloCodigo"] = _codigo(
        origen[codigo_col]
    )

    fecha_ingreso = (
        pd.to_datetime(
            origen[fecha_ingreso_col],
            errors="coerce",
            dayfirst=True,
        ).dt.normalize()
        if fecha_ingreso_col is not None
        else pd.Series(
            pd.NaT,
            index=origen.index,
            dtype="datetime64[ns]",
        )
    )

    if vencimiento_col is not None:
        fecha_vencimiento = pd.to_datetime(
            origen[vencimiento_col],
            errors="coerce",
            dayfirst=True,
        ).dt.normalize()

        fecha_por_vencimiento = (
            fecha_vencimiento
            - pd.to_timedelta(
                2000,
                unit="D",
            )
        )

        fecha_ingreso = fecha_ingreso.where(
            fecha_ingreso.notna(),
            fecha_por_vencimiento,
        )

    if dias_col is not None:
        dias_restantes = _numero(
            origen[dias_col]
        )
        fecha_por_dias = (
            pd.Timestamp.today().normalize()
            - pd.to_timedelta(
                (
                    2000
                    - dias_restantes
                ).clip(lower=0),
                unit="D",
            )
        )

        fecha_ingreso = fecha_ingreso.where(
            fecha_ingreso.notna(),
            fecha_por_dias,
        )

    detalle["FechaIngresoEstimada"] = (
        fecha_ingreso
    )

    detalle["Contenedor"] = (
        origen[contenedor_col]
        .fillna("")
        .astype(str)
        .str.strip()
        if contenedor_col is not None
        else ""
    )

    detalle = detalle.loc[
        detalle["ArticuloCodigo"].ne("")
    ].copy()

    if detalle.empty:
        return pd.DataFrame(columns=columnas)

    return (
        detalle.groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            PrimerIngresoStockActual=(
                "FechaIngresoEstimada",
                "min",
            ),
            UltimoIngresoStockActual=(
                "FechaIngresoEstimada",
                "max",
            ),
            ContenedoresStockActual=(
                "Contenedor",
                lambda serie: int(
                    serie.loc[
                        serie.astype(str).str.strip().ne("")
                    ].nunique()
                ),
            ),
        )
    )


def _clasificar_estado_ingreso(
    fila: pd.Series,
    dias_producto_nuevo: int = 30,
    dias_ingreso_reciente: int = 30,
) -> str:
    """
    Clasifica el artículo por antigüedad real de su evidencia.

    Producto nuevo NO depende de seguir estando en Recepción.
    Se considera nuevo únicamente durante los primeros N días
    desde su primera evidencia conocida.
    """
    dias_primera = fila.get(
        "DiasDesdePrimeraEvidencia",
        np.nan,
    )
    dias_ultimo = fila.get(
        "DiasDesdeUltimoIngreso",
        np.nan,
    )

    if (
        pd.notna(dias_primera)
        and 0 <= float(dias_primera)
        <= dias_producto_nuevo
    ):
        return "🆕 Producto nuevo"

    if (
        pd.notna(dias_ultimo)
        and 0 <= float(dias_ultimo)
        <= dias_ingreso_reciente
    ):
        return "📥 Reposición reciente"

    if (
        pd.notna(dias_primera)
        or pd.notna(dias_ultimo)
    ):
        return "📦 Producto existente"

    return "❓ Sin fecha de ingreso"



# ==========================================================
# DISPONIBLE + COBERTURA
# ==========================================================

def preparar_disponible_articulo(tabla_disponible: pd.DataFrame) -> pd.DataFrame:
    """Normaliza Stock Disponible y devuelve una sola fila por artículo."""
    columnas = [
        "ArticuloCodigo", "ArticuloDescripcion", "Recepcion", "Bloqueados",
        "Pedidas", "Reservado", "Disponible", "Transito", "Preparacion",
        "Despacho", "Vencidas", "Scrap", "Inconsistencia",
    ]
    if tabla_disponible is None or tabla_disponible.empty:
        return pd.DataFrame(columns=columnas)

    origen = tabla_disponible.copy()
    salida = pd.DataFrame(index=origen.index)
    salida["ArticuloCodigo"] = _codigo(_serie(origen, ["Codigo", "ArticuloCodigo", "Código"]))
    salida["ArticuloDescripcion"] = (
        _serie(origen, ["Descripcion", "ArticuloDescripcion", "Descripción"], "")
        .fillna("").astype(str).str.strip()
    )

    aliases = {
        "Recepcion": ["Recepcion", "Recepción"],
        "Bloqueados": ["Bloqueados", "Bloqueado"],
        "Pedidas": ["Pedidas", "Pedidos", "Pedido"],
        "Reservado": ["Reservado", "Reservada"],
        "Disponible": ["Disponible"],
        "Transito": ["Transito", "Tránsito"],
        "Preparacion": ["Preparacion", "Preparación"],
        "Despacho": ["Despacho", "Preparado"],
        "Vencidas": ["Vencidas", "Vencido"],
        "Scrap": ["Scrap"],
        "Inconsistencia": ["Inconsistencia", "Inconsistencias"],
    }
    for destino, candidatos in aliases.items():
        salida[destino] = _numero(_serie(origen, candidatos, 0))

    salida = salida.loc[salida["ArticuloCodigo"].ne("")].copy()
    if salida.empty:
        return pd.DataFrame(columns=columnas)

    descripcion = (
        salida.loc[salida["ArticuloDescripcion"].ne("")]
        .drop_duplicates("ArticuloCodigo", keep="first")
        [["ArticuloCodigo", "ArticuloDescripcion"]]
    )
    numericas = [columna for columna in columnas if columna not in {"ArticuloCodigo", "ArticuloDescripcion"}]
    agregado = salida.groupby("ArticuloCodigo", as_index=False)[numericas].sum()
    return agregado.merge(descripcion, on="ArticuloCodigo", how="left")[columnas]



def preparar_pendiente_erp_articulo(
    tabla_detalle_pendientes: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Resume el saldo pendiente real ERP por artículo.

    Es importante que esta fuente pueda aportar artículos que NO existen
    en Stock Disponible DIGIP. Por eso devuelve una tabla independiente
    que luego se incorpora al universo mediante outer merge.
    """
    columnas = [
        "ArticuloCodigo",
        "PendienteERP",
        "DescripcionPendienteERP",
    ]

    if (
        tabla_detalle_pendientes is None
        or tabla_detalle_pendientes.empty
    ):
        return pd.DataFrame(columns=columnas)

    origen = tabla_detalle_pendientes.copy()

    codigo_col = _buscar_columna(
        origen,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "Codigo Articulo",
            "Código Artículo",
            "cod_art",
            "Codigo",
            "Artículo",
        ],
    )
    if codigo_col is None:
        return pd.DataFrame(columns=columnas)

    # En distintos reportes ERP el faltante puede venir como Pendiente,
    # CantidadPendiente o FaltaLinea.
    pendiente_col = _buscar_columna(
        origen,
        [
            "CantidadPendiente",
            "Pendiente",
            "can_pen",
            "FaltaLinea",
            "Falta Linea",
            "CantidadFaltante",
            "Faltante",
            "Falta",
        ],
    )
    original_col = _buscar_columna(
        origen,
        [
            "can_art",
            "CantidadArticulo",
            "CantidadOriginal",
            "Cantidad",
            "Unidades",
        ],
    )
    remitida_col = _buscar_columna(
        origen,
        [
            "can_rem",
            "CantidadRemitida",
            "Remitido",
            "UnidadesRemitidas",
        ],
    )
    descripcion_col = _buscar_columna(
        origen,
        [
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "Descripcion",
            "Descripción",
            "descrip",
        ],
    )

    salida = pd.DataFrame(index=origen.index)
    salida["ArticuloCodigo"] = _codigo(
        origen[codigo_col]
    )

    if pendiente_col is not None:
        pendiente = _numero(
            origen[pendiente_col]
        )
    elif original_col is not None:
        original = _numero(
            origen[original_col]
        )
        remitida = (
            _numero(origen[remitida_col])
            if remitida_col is not None
            else pd.Series(
                0,
                index=origen.index,
                dtype=float,
            )
        )
        pendiente = (
            original - remitida
        ).clip(lower=0)
    else:
        return pd.DataFrame(columns=columnas)

    salida["PendienteERP"] = pendiente.clip(
        lower=0
    )
    salida["DescripcionPendienteERP"] = (
        origen[descripcion_col]
        .fillna("")
        .astype(str)
        .str.strip()
        if descripcion_col is not None
        else ""
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
        & salida["PendienteERP"].gt(0)
    ].copy()

    if salida.empty:
        return pd.DataFrame(columns=columnas)

    descripcion = (
        salida.loc[
            salida["DescripcionPendienteERP"].ne("")
        ]
        .drop_duplicates(
            "ArticuloCodigo",
            keep="first",
        )[
            [
                "ArticuloCodigo",
                "DescripcionPendienteERP",
            ]
        ]
    )

    resumen = (
        salida.groupby(
            "ArticuloCodigo",
            as_index=False,
        )["PendienteERP"]
        .sum()
    )

    return (
        resumen.merge(
            descripcion,
            on="ArticuloCodigo",
            how="left",
        )
        .sort_values("ArticuloCodigo")
        .reset_index(drop=True)
    )



def _asignar_categoria_venta(
    tabla: pd.DataFrame,
) -> pd.Series:
    """
    Clasifica los artículos por volumen de venta promedio mensual.

    - Caliente: top 15% de los artículos con ventas.
    - Intermedio: siguiente 35%.
    - Frío: resto de los artículos con ventas.
    - Sin movimiento: venta promedio mensual igual a cero.
    """
    categorias = pd.Series(
        "⚫ Sin movimiento",
        index=tabla.index,
        dtype="object",
    )

    ventas = pd.to_numeric(
        tabla.get(
            "VentaPromedioMensual",
            pd.Series(0, index=tabla.index),
        ),
        errors="coerce",
    ).fillna(0)

    mascara_con_venta = ventas.gt(0)

    if not mascara_con_venta.any():
        return categorias

    ranking_percentil = ventas.loc[
        mascara_con_venta
    ].rank(
        method="average",
        pct=True,
        ascending=True,
    )

    categorias.loc[
        ranking_percentil.index[
            ranking_percentil.ge(0.85)
        ]
    ] = "🔥 Caliente"

    categorias.loc[
        ranking_percentil.index[
            ranking_percentil.ge(0.50)
            & ranking_percentil.lt(0.85)
        ]
    ] = "🟡 Intermedio"

    categorias.loc[
        ranking_percentil.index[
            ranking_percentil.lt(0.50)
        ]
    ] = "❄️ Frío"

    return categorias


def _clasificar_cobertura(fila: pd.Series) -> str:
    disponible = float(fila.get("Disponible", 0) or 0)
    venta_dia = float(fila.get("VentaPromedioDiaria", 0) or 0)
    dias = fila.get("CoberturaDias", np.nan)

    if venta_dia <= 0:
        return "Sin movimiento"
    if disponible <= 0:
        return "Quiebre"
    if pd.isna(dias):
        return "Sin movimiento"
    if dias <= 15:
        return "Crítico"
    if dias <= 30:
        return "Bajo"
    if dias <= 60:
        return "Controlado"
    return "Cubierto"


def construir_tabla_cobertura(
    tabla_disponible: pd.DataFrame,
    historico_ventas: pd.DataFrame,
    tabla_articulos: pd.DataFrame | None = None,
    tabla_max_min: pd.DataFrame | None = None,
    tabla_stock_detallado: pd.DataFrame | None = None,
    tabla_stock_recepcion: pd.DataFrame | None = None,
    tabla_detalle_pendientes: pd.DataFrame | None = None,
    tabla_oc_cobertura: pd.DataFrame | None = None,
    meses_analisis: int = 3,
    dias_producto_nuevo: int = 30,
    dias_ingreso_reciente: int = 30,
) -> tuple[pd.DataFrame, dict]:
    """Cruza stock actual contra consumo histórico y calcula cobertura."""
    disponible = preparar_disponible_articulo(tabla_disponible)
    historico = historico_ventas.copy() if historico_ventas is not None else pd.DataFrame()

    if historico.empty:
        historico = pd.DataFrame(
            columns=["Fecha", "ArticuloCodigo", "ArticuloDescripcion", "Familia", "Sectorizacion", "UnidadesVendidas"]
        )

    historico["Fecha"] = pd.to_datetime(
        historico.get("Fecha"),
        errors="coerce",
    )

    primera_venta_historica = (
        historico.loc[
            historico["Fecha"].notna()
            & historico["ArticuloCodigo"].fillna("").astype(str).str.strip().ne("")
        ]
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            PrimeraVentaHistorica=(
                "Fecha",
                "min",
            ),
        )
        if not historico.empty
        else pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "PrimeraVentaHistorica",
            ]
        )
    )

    fecha_maxima = historico["Fecha"].max() if not historico.empty else pd.NaT
    if pd.notna(fecha_maxima):
        fecha_desde = (fecha_maxima.to_period("M") - (max(int(meses_analisis), 1) - 1)).start_time
        historial_periodo = historico.loc[historico["Fecha"].between(fecha_desde, fecha_maxima, inclusive="both")].copy()
    else:
        fecha_desde = pd.NaT
        historial_periodo = historico.iloc[0:0].copy()

    dias_periodo = max((fecha_maxima - fecha_desde).days + 1, 1) if pd.notna(fecha_maxima) else 0
    meses_periodo = max(int(meses_analisis), 1)

    if historial_periodo.empty:
        ventas = pd.DataFrame(columns=[
            "ArticuloCodigo", "UnidadesPeriodo", "VentaPromedioMensual", "VentaPromedioDiaria",
            "MesesConVenta", "UltimaVenta", "FamiliaHistorica", "SectorizacionHistorica",
        ])
    else:
        historial_periodo["PeriodoMes"] = historial_periodo["Fecha"].dt.to_period("M")
        ventas = (
            historial_periodo.groupby("ArticuloCodigo", as_index=False)
            .agg(
                UnidadesPeriodo=("UnidadesVendidas", "sum"),
                MesesConVenta=("PeriodoMes", "nunique"),
                UltimaVenta=("Fecha", "max"),
                FamiliaHistorica=("Familia", lambda s: next((str(v).strip() for v in s if str(v).strip()), "")),
                SectorizacionHistorica=("Sectorizacion", lambda s: next((str(v).strip() for v in s if str(v).strip()), "")),
                DescripcionHistorica=("ArticuloDescripcion", lambda s: next((str(v).strip() for v in s if str(v).strip()), "")),
            )
        )
        ventas["VentaPromedioMensual"] = ventas["UnidadesPeriodo"] / meses_periodo
        ventas["VentaPromedioDiaria"] = ventas["UnidadesPeriodo"] / max(dias_periodo, 1)

    pendientes_erp = preparar_pendiente_erp_articulo(
        tabla_detalle_pendientes
    )

    universo = disponible.copy()

    if not pendientes_erp.empty:
        universo = universo.merge(
            pendientes_erp,
            on="ArticuloCodigo",
            how="outer",
            validate="one_to_one",
        )
    else:
        universo["PendienteERP"] = 0

    universo["PendienteERP"] = pd.to_numeric(
        universo.get("PendienteERP", pd.Series(0, index=universo.index)),
        errors="coerce",
    ).fillna(0)

    # El histórico no incorpora artículos nuevos: solo enriquece el universo.
    tabla = universo.merge(
        ventas,
        on="ArticuloCodigo",
        how="left",
        validate="one_to_one",
    )
    tabla["ArticuloCodigo"] = tabla["ArticuloCodigo"].fillna("").astype(str)

    for columna in [
        "Recepcion", "Bloqueados", "Pedidas", "Reservado", "Disponible", "Transito",
        "Preparacion", "Despacho", "Vencidas", "Scrap", "Inconsistencia",
        "PendienteERP",
        "UnidadesPeriodo", "VentaPromedioMensual", "VentaPromedioDiaria", "MesesConVenta",
    ]:
        if columna not in tabla:
            tabla[columna] = 0
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").fillna(0)

    tabla["FrecuenciaVentaPct"] = np.where(
        meses_periodo > 0,
        tabla["MesesConVenta"]
        / float(meses_periodo)
        * 100,
        0,
    ).clip(0, 100)

    ingresos = _preparar_ingresos_por_articulo(
        tabla_stock_detallado
    )

    tabla = tabla.merge(
        ingresos,
        on="ArticuloCodigo",
        how="left",
        validate="one_to_one",
    )

    # Recepción también es evidencia física del artículo.
    # Esto permite detectar como nuevo un SKU que todavía no fue
    # guardado en stock general, sin dejarlo como nuevo para siempre.
    ingresos_recepcion = _preparar_ingresos_por_articulo(
        tabla_stock_recepcion
    ).rename(
        columns={
            "PrimerIngresoStockActual":
                "PrimerIngresoRecepcion",
            "UltimoIngresoStockActual":
                "UltimoIngresoRecepcion",
            "ContenedoresStockActual":
                "ContenedoresRecepcionActual",
        }
    )

    tabla = tabla.merge(
        ingresos_recepcion,
        on="ArticuloCodigo",
        how="left",
        validate="one_to_one",
    )

    tabla = tabla.merge(
        primera_venta_historica,
        on="ArticuloCodigo",
        how="left",
        validate="one_to_one",
    )

    tabla["PrimeraEvidenciaArticulo"] = (
        tabla[
            [
                "PrimerIngresoStockActual",
                "PrimerIngresoRecepcion",
                "PrimeraVentaHistorica",
            ]
        ]
        .min(
            axis=1,
        )
    )

    hoy_analisis = pd.Timestamp.today().normalize()

    tabla["DiasDesdePrimeraEvidencia"] = (
        hoy_analisis
        - pd.to_datetime(
            tabla["PrimeraEvidenciaArticulo"],
            errors="coerce",
        ).dt.normalize()
    ).dt.days

    tabla["UltimoIngresoArticulo"] = (
        tabla[
            [
                "UltimoIngresoStockActual",
                "UltimoIngresoRecepcion",
            ]
        ]
        .max(
            axis=1,
        )
    )

    tabla["DiasDesdeUltimoIngreso"] = (
        hoy_analisis
        - pd.to_datetime(
            tabla["UltimoIngresoArticulo"],
            errors="coerce",
        ).dt.normalize()
    ).dt.days

    tabla["EstadoIngreso"] = tabla.apply(
        _clasificar_estado_ingreso,
        axis=1,
        dias_producto_nuevo=int(
            dias_producto_nuevo
        ),
        dias_ingreso_reciente=int(
            dias_ingreso_reciente
        ),
    )

    tabla["EsProductoNuevo"] = tabla[
        "EstadoIngreso"
    ].eq("🆕 Producto nuevo")

    tabla["CategoriaVenta"] = (
        _asignar_categoria_venta(
            tabla.loc[
                ~tabla["EsProductoNuevo"]
            ].copy()
        )
    )

    tabla["CategoriaVenta"] = (
        tabla["CategoriaVenta"]
        .reindex(tabla.index)
        .fillna("🆕 Producto nuevo")
    )

    # Maestro de artículos: se utiliza solo para completar clasificación y descripción.
    if tabla_articulos is not None and not tabla_articulos.empty:
        maestro = tabla_articulos.copy()
        col_codigo = _buscar_columna(maestro, ["COD_ART", "CodigoArticulo", "ArticuloCodigo", "Codigo", "Código"])
        if col_codigo is not None:
            complemento = pd.DataFrame(index=maestro.index)
            complemento["ArticuloCodigo"] = _codigo(maestro[col_codigo])
            for destino, candidatos in {
                "DescripcionMaestro": ["DESCRIP", "Descripcion", "Descripción"],
                "Familia": ["Familia", "FamiliaPrincipal", "Familia_1", "Familia1"],
                "Familia2": [
                    "Familia_2",
                    "Familia2",
                    "Familia 2",
                    "Familia Secundaria",
                    "FamiliaSecundaria",
                ],
                "Sectorizacion": ["Sectorizacion", "Sectorización", "Sector"],
                "Origen": ["Origen"],
            }.items():
                col = _buscar_columna(maestro, candidatos)
                complemento[destino] = maestro[col].fillna("").astype(str).str.strip() if col else ""
            complemento = complemento.loc[complemento["ArticuloCodigo"].ne("")].drop_duplicates("ArticuloCodigo")
            tabla = tabla.merge(complemento, on="ArticuloCodigo", how="left")

    for columna in [
        "DescripcionMaestro",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Origen",
    ]:
        if columna not in tabla:
            tabla[columna] = ""
        tabla[columna] = tabla[columna].fillna("").astype(str).str.strip()

    tabla["ArticuloDescripcion"] = (
        tabla.get("ArticuloDescripcion", pd.Series("", index=tabla.index)).fillna("").astype(str).str.strip()
    )
    tabla["DescripcionHistorica"] = (
        tabla.get("DescripcionHistorica", pd.Series("", index=tabla.index)).fillna("").astype(str).str.strip()
    )
    tabla["DescripcionPendienteERP"] = (
        tabla.get(
            "DescripcionPendienteERP",
            pd.Series("", index=tabla.index),
        )
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["ArticuloDescripcion"] = (
        tabla["ArticuloDescripcion"]
        .where(
            tabla["ArticuloDescripcion"].ne(""),
            tabla["DescripcionMaestro"],
        )
        .where(
            lambda serie: serie.ne(""),
            tabla["DescripcionHistorica"],
        )
        .where(
            lambda serie: serie.ne(""),
            tabla["DescripcionPendienteERP"],
        )
    )
    tabla["Familia"] = tabla["Familia"].where(
        tabla["Familia"].ne(""), tabla.get("FamiliaHistorica", "")
    )

    # Clasificación secundaria utilizada para separar Repuestos y
    # Partes y piezas. Si el maestro no posee Familia_2, se usa
    # Familia como respaldo para conservar compatibilidad.
    tabla["Familia2"] = (
        tabla["Familia2"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    tabla["Familia2"] = tabla["Familia2"].where(
        tabla["Familia2"].ne(""),
        tabla["Familia"],
    )
    tabla["Sectorizacion"] = tabla["Sectorizacion"].where(
        tabla["Sectorizacion"].ne(""), tabla.get("SectorizacionHistorica", "")
    )

    # ------------------------------------------------------
    # PRÓXIMO INGRESO POR OC - SOLO PRODUCTOS IMPORTADOS
    # ------------------------------------------------------
    for columna in [
        "OrdenCompraProxima",
        "FechaPrevistaIngresoOC",
        "TipoFechaIngresoOC",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = (
                pd.NaT
                if columna == "FechaPrevistaIngresoOC"
                else ""
            )

    if (
        tabla_oc_cobertura is not None
        and not tabla_oc_cobertura.empty
    ):
        oc = tabla_oc_cobertura.copy()

        if "ArticuloCodigo" in oc.columns:
            oc["ArticuloCodigo"] = _codigo(
                oc["ArticuloCodigo"]
            )

            columnas_oc = [
                columna
                for columna in [
                    "ArticuloCodigo",
                    "OrdenCompraProxima",
                    "FechaPrevistaIngresoOC",
                    "TipoFechaIngresoOC",
                ]
                if columna in oc.columns
            ]

            oc = (
                oc[columnas_oc]
                .loc[
                    oc["ArticuloCodigo"].ne("")
                ]
                .drop_duplicates(
                    "ArticuloCodigo",
                    keep="first",
                )
            )

            # Evita duplicar columnas si la función se reutiliza.
            tabla = tabla.drop(
                columns=[
                    "OrdenCompraProxima",
                    "FechaPrevistaIngresoOC",
                    "TipoFechaIngresoOC",
                ],
                errors="ignore",
            ).merge(
                oc,
                on="ArticuloCodigo",
                how="left",
                validate="one_to_one",
            )

    for columna in [
        "OrdenCompraProxima",
        "TipoFechaIngresoOC",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    if "FechaPrevistaIngresoOC" not in tabla.columns:
        tabla["FechaPrevistaIngresoOC"] = pd.NaT
    tabla["FechaPrevistaIngresoOC"] = pd.to_datetime(
        tabla["FechaPrevistaIngresoOC"],
        errors="coerce",
    )

    # La fecha de OC se muestra únicamente para artículos importados.
    mascara_importado = (
        tabla["Origen"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.contains("IMPORT", na=False)
    )

    tabla.loc[
        ~mascara_importado,
        "OrdenCompraProxima",
    ] = ""
    tabla.loc[
        ~mascara_importado,
        "TipoFechaIngresoOC",
    ] = ""
    tabla.loc[
        ~mascara_importado,
        "FechaPrevistaIngresoOC",
    ] = pd.NaT

    if tabla_max_min is not None and not tabla_max_min.empty:
        mm = tabla_max_min.copy()
        col_codigo = _buscar_columna(mm, ["ArticuloCodigo", "CodigoArticulo", "codigo_articulo"])
        if col_codigo is not None:
            mm["ArticuloCodigo"] = _codigo(mm[col_codigo])
            min_col = _buscar_columna(mm, ["StockMinimo", "stock_minimo", "Minimo"])
            max_col = _buscar_columna(mm, ["StockMaximo", "stock_maximo", "Maximo"])
            resumen_mm = pd.DataFrame({"ArticuloCodigo": mm["ArticuloCodigo"]})
            resumen_mm["StockMinimo"] = _numero(mm[min_col]) if min_col else 0
            resumen_mm["StockMaximo"] = _numero(mm[max_col]) if max_col else 0
            resumen_mm = resumen_mm.groupby("ArticuloCodigo", as_index=False)[["StockMinimo", "StockMaximo"]].sum()
            tabla = tabla.merge(resumen_mm, on="ArticuloCodigo", how="left")

    for columna in ["StockMinimo", "StockMaximo"]:
        if columna not in tabla:
            tabla[columna] = 0
        tabla[columna] = pd.to_numeric(tabla[columna], errors="coerce").fillna(0)

    tabla["StockComprometido"] = (
        tabla["Pedidas"] + tabla["Reservado"] + tabla["Preparacion"] + tabla["Despacho"]
    )
    tabla["StockOperativoTotal"] = (
        tabla["Disponible"] + tabla["StockComprometido"] + tabla["Bloqueados"]
        + tabla["Recepcion"] + tabla["Transito"]
    )
    tabla["PorcentajeDisponible"] = np.where(
        tabla["StockOperativoTotal"].gt(0),
        tabla["Disponible"] / tabla["StockOperativoTotal"] * 100,
        0,
    )
    tabla["CoberturaMeses"] = np.where(
        tabla["VentaPromedioMensual"].gt(0),
        tabla["Disponible"] / tabla["VentaPromedioMensual"],
        np.nan,
    )
    tabla["CoberturaDias"] = np.where(
        tabla["VentaPromedioDiaria"].gt(0),
        tabla["Disponible"] / tabla["VentaPromedioDiaria"],
        np.nan,
    )

    # Demanda vigente del ERP que puede existir aunque DIGIP no tenga
    # ninguna fila para ese SKU.
    tabla["VendidoSinStock"] = (
        tabla["PendienteERP"].gt(0)
        & tabla["Disponible"].le(0)
    )
    tabla["FaltanteStockActual"] = np.where(
        tabla["VendidoSinStock"],
        tabla["PendienteERP"],
        0,
    )
    for columna_decimal in [
        "VentaPromedioMensual",
        "VentaPromedioDiaria",
        "FrecuenciaVentaPct",
        "PorcentajeDisponible",
        "CoberturaMeses",
        "CoberturaDias",
    ]:
        if columna_decimal in tabla.columns:
            tabla[columna_decimal] = pd.to_numeric(
                tabla[columna_decimal],
                errors="coerce",
            ).round(2)

    tabla["EstadoCobertura"] = tabla.apply(
        _clasificar_cobertura,
        axis=1,
    )

    # Un artículo con demanda ERP vigente y Disponible = 0 debe figurar
    # como Quiebre aunque todavía no tenga histórico de preparación.
    tabla.loc[
        tabla["VendidoSinStock"],
        "EstadoCobertura",
    ] = "Quiebre"

    # Producto nuevo sólo pisa el estado cuando no existe demanda urgente.
    tabla.loc[
        tabla["EsProductoNuevo"]
        & ~tabla["VendidoSinStock"],
        "EstadoCobertura",
    ] = "Nuevo ingreso"

    tabla["AccionRecomendada"] = tabla["EstadoCobertura"].map({
        "Quiebre": "Reponer / priorizar ingreso",
        "Crítico": "Revisión inmediata",
        "Bajo": "Planificar reposición",
        "Controlado": "Monitorear",
        "Cubierto": "Sin acción inmediata",
        "Sin movimiento": "Revisar rotación",
        "Nuevo ingreso": "Monitorear lanzamiento",
    }).fillna("")

    tabla.loc[
        tabla["VendidoSinStock"],
        "AccionRecomendada",
    ] = "URGENTE: vendido ERP sin stock disponible"

    # ------------------------------------------------------
    # EXCLUSIONES OPERATIVAS
    # ------------------------------------------------------
    # Usa exactamente el mismo listado centralizado que Inventario.
    # Los artículos excluidos dejan de impactar en KPIs, alertas,
    # gráficos, filtros, tabla y descargable.
    tabla = filtrar_articulos_fuera_inventario(
        tabla,
        ocultar=True,
    )

    tabla = tabla.sort_values(
        ["EstadoCobertura", "CoberturaDias", "ArticuloCodigo"],
        key=lambda serie: (
            serie.map({
                "Quiebre": 0, "Crítico": 1, "Bajo": 2, "Controlado": 3,
                "Cubierto": 4, "Nuevo ingreso": 5, "Sin movimiento": 6,
            }).fillna(99)
            if serie.name == "EstadoCobertura"
            else serie
        ),
        na_position="last",
    ).reset_index(drop=True)

    metadata = {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_maxima,
        "meses_analisis": meses_periodo,
        "dias_periodo": dias_periodo,
        "unidades_historicas": float(historial_periodo["UnidadesVendidas"].sum()) if not historial_periodo.empty else 0,
    }
    return tabla, metadata
