from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    CARPETA_DATOS,
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_fuente_flexible import leer_archivo_flexible
from models.stock.existencia import (
    preparar_tabla_stock,
    preparar_max_min,
    construir_stock_total_detallado,
    construir_stock_total_por_articulo,
)
from models.recepcion import (
    construir_pendientes_oc,
    construir_recepcion_agrupada,
)
from models.stock.ocupacion import (
    preparar_maestro_ubicaciones,
    construir_ocupacion_deposito,
)
from models.stock.calidad import (
    preparar_stock_calidad,
    construir_ocupacion_calidad,
    resumir_stock_calidad,
)
from utils.confirmaciones_oc import (
    leer_confirmaciones_oc,
    aplicar_confirmaciones_oc,
)
from models.base_historica_metricas import (
    firma_base_historica_metricas,
)


# ==========================================================
# FUENTES DEL MODULO STOCK
# ==========================================================

FUENTES_DINAMICAS_STOCK = {
    "stock_recepcion": {
        "carpeta": CARPETA_WMS,
        "nombres": [
            "Stock Recepcion",
            "Stock Recepción",
            "stock_recepcion",
            "Stock_Recepcion",
        ],
    },
    "disponible": {
        "carpeta": CARPETA_WMS,
        "nombres": [
            "Stock Disponible",
            "Stock_Disponible",
            "stock_disponible",
            "Disponible DIGIP",
            "Disponible Digip",
            "Disponible_Digip",
            "disponible_digip",
        ],
    },
    "detalle_pendientes": {
        "carpeta": CARPETA_ERP,
        "nombres": [
            "Detalle Pendientes",
            "Detalle_Pendientes",
            "detalle pendientes",
            "detalle_pendientes",
        ],
    },
    "stock_detallado": {
        "carpeta": CARPETA_WMS,
        "nombres": [
            "Stock DIGIP",
            "Stock Digip",
            "Stock_Digip",
            "stock_digip",
            "stock_detallado",
            "Stock_Detallado",
            "Stock Detallado",
        ],
    },
    "calidad": {
        "carpeta": CARPETA_WMS,
        "nombres": [
            "Stock Calidad Laboratorio",
            "Stock_Calidad_Laboratorio",
            "stock_calidad_laboratorio",
            "Calidad Laboratorio",
        ],
    },
}


FUENTES_MAESTRAS_STOCK = {
    "pendientes_oc": {
        "carpeta": CARPETA_ERP,
        "nombres": [
            "Pendientes OC",
            "Pendientes_OC",
            "pendientes oc",
            "pendientes_oc",
        ],
    },
    "max_min": {
        "carpeta": CARPETA_MAESTROS,
        "nombres": [
            "Max & Min",
            "Max_Min",
            "max_min",
        ],
    },
    "articulos": {
        "carpeta": CARPETA_MAESTROS,
        "nombres": [
            "Maestro Articulo",
            "Maestro Artículos",
            "Maestro Articulos",
        ],
    },
    "volumetria": {
        "carpeta": CARPETA_MAESTROS,
        "nombres": [
            "Maestro Volumetria",
            "Maestro Volumetría",
        ],
    },
    "ubicaciones": {
        "carpeta": CARPETA_MAESTROS,
        "nombres": [
            "Maestro Ubicaciones",
            "Maestro_Ubicaciones",
            "maestro ubicaciones",
            "maestro_ubicaciones",
        ],
    },
}


FUENTES_STOCK = {
    **FUENTES_DINAMICAS_STOCK,
    **FUENTES_MAESTRAS_STOCK,
}


# ==========================================================
# FIRMA FISICA DE FUENTES
# ==========================================================

def firma_fuente_stock(
    clave: str,
) -> tuple:
    """
    Genera una firma del archivo físico usado por una
    fuente de Stock.

    La carpeta se resuelve según el origen real de la fuente:
    Data_WMS, Data_ERP o Data_Maestros.

    La firma cambia cuando el archivo se reemplaza o modifica,
    por lo que Streamlit invalida automáticamente el contexto
    cacheado correspondiente.
    """

    configuracion = FUENTES_STOCK.get(
        clave
    )

    if configuracion is None:
        return (
            clave,
            None,
            None,
            None,
        )

    nombres = configuracion["nombres"]
    carpeta = Path(
        configuracion["carpeta"]
    )

    extensiones = (
        ".xlsx",
        ".xlsm",
        ".xls",
        ".csv",
        ".parquet",
    )

    candidatos: list[Path] = []

    for nombre in nombres:
        for extension in extensiones:
            ruta = (
                carpeta
                / f"{nombre}{extension}"
            )

            if (
                ruta.exists()
                and ruta.is_file()
            ):
                candidatos.append(
                    ruta
                )

    # Respaldo tolerante a diferencias de mayúsculas,
    # guiones bajos y subcarpetas.
    if (
        not candidatos
        and carpeta.exists()
    ):
        nombres_normalizados = {
            str(nombre)
            .strip()
            .lower()
            .replace("_", " ")
            for nombre in nombres
        }

        for ruta in carpeta.rglob("*"):
            if (
                not ruta.is_file()
                or ruta.suffix.lower()
                not in extensiones
            ):
                continue

            nombre_normalizado = (
                ruta.stem
                .strip()
                .lower()
                .replace("_", " ")
            )

            if (
                nombre_normalizado
                in nombres_normalizados
            ):
                candidatos.append(
                    ruta
                )

    if not candidatos:
        return (
            clave,
            None,
            None,
            None,
        )

    ruta_actual = max(
        candidatos,
        key=lambda ruta: (
            ruta.stat().st_mtime_ns
        ),
    )

    estado = ruta_actual.stat()

    return (
        str(
            ruta_actual.resolve()
        ),
        estado.st_mtime_ns,
        estado.st_size,
        (
            estado.st_ino
            if hasattr(
                estado,
                "st_ino",
            )
            else None
        ),
    )


# ==========================================================
# LECTURA GENERICA DE FUENTES
# ==========================================================

def _leer_fuente(
    clave: str,
    configuracion: dict,
    usar_cache: bool,
) -> dict:
    if clave not in configuracion:
        raise KeyError(
            "Fuente de Stock desconocida: "
            f"{clave}"
        )

    fuente = configuracion[
        clave
    ]

    carpeta = fuente[
        "carpeta"
    ]

    nombres = fuente[
        "nombres"
    ]

    dataframe, nombre_resuelto = (
        leer_archivo_flexible(
            carpeta,
            nombres,
            cache=usar_cache,
        )
    )

    return {
        "df": (
            dataframe
            if dataframe is not None
            else pd.DataFrame()
        ),
        "nombre_resuelto": (
            nombre_resuelto
        ),
        "carpeta": str(
            carpeta
        ),
    }


@st.cache_data(
    ttl=120,
    max_entries=8,
    show_spinner=False,
)
def cargar_fuente_dinamica_stock(
    clave: str,
) -> dict:
    """
    Lee solamente el reporte operativo solicitado.
    """

    return _leer_fuente(
        clave,
        FUENTES_DINAMICAS_STOCK,
        usar_cache=False,
    )


@st.cache_data(
    ttl=3600,
    max_entries=10,
    show_spinner=False,
)
def cargar_fuente_maestra_stock(
    clave: str,
) -> dict:
    """
    Lee solamente la fuente maestra solicitada,
    con caché prolongada.
    """

    return _leer_fuente(
        clave,
        FUENTES_MAESTRAS_STOCK,
        usar_cache=True,
    )


@st.cache_data(
    max_entries=10,
    show_spinner=False,
)
def cargar_fuente_maestra_versionada_stock(
    clave: str,
    firma_fuente: tuple,
) -> dict:
    """
    Lee un maestro usando la firma física del archivo
    como parte de la clave de caché.

    Se usa especialmente en Configuración/Slotting para
    Max & Min y Maestro Ubicaciones. Si alguno de esos
    archivos se reemplaza manteniendo el mismo nombre,
    la firma cambia y Streamlit reconstruye únicamente
    esa fuente.

    La lectura interna se hace sin caché del lector para
    evitar reutilizar una versión anterior.
    """

    _ = firma_fuente

    return _leer_fuente(
        clave,
        FUENTES_MAESTRAS_STOCK,
        usar_cache=False,
    )


# ==========================================================
# COMPATIBILIDAD
# ==========================================================

def cargar_fuentes_dinamicas_stock() -> dict[str, dict]:
    """
    Compatibilidad para código anterior.
    """

    return {
        clave: cargar_fuente_dinamica_stock(
            clave
        )
        for clave
        in FUENTES_DINAMICAS_STOCK
    }


def cargar_maestros_stock() -> dict[str, dict]:
    """
    Compatibilidad para código anterior.
    """

    return {
        clave: cargar_fuente_maestra_stock(
            clave
        )
        for clave
        in FUENTES_MAESTRAS_STOCK
    }


def cargar_fuentes_stock() -> dict[str, dict]:
    return {
        **cargar_fuentes_dinamicas_stock(),
        **cargar_maestros_stock(),
    }


# ==========================================================
# RECEPCION
# ==========================================================

def _asegurar_fechas_recepcion(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    resultado = tabla.copy()

    for columna in [
        "FechaIngresoEstimada",
        "FechaConfirmadaIngreso",
        "FechaOperativaIngreso",
    ]:
        if columna not in resultado.columns:
            resultado[
                columna
            ] = pd.NaT

        resultado[
            columna
        ] = pd.to_datetime(
            resultado[columna],
            errors="coerce",
        )

    for columna in [
        "TipoFechaIngreso",
        "EstadoFechaIngreso",
    ]:
        if columna not in resultado.columns:
            resultado[
                columna
            ] = ""

    resultado[
        "FechaOperativaIngreso"
    ] = (
        resultado[
            "FechaConfirmadaIngreso"
        ]
        .combine_first(
            resultado[
                "FechaIngresoEstimada"
            ]
        )
    )

    return resultado


@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner=(
        "Preparando Recepción "
        "y existencia física..."
    ),
)
def construir_contexto_existencia() -> dict:
    stock_recepcion = (
        cargar_fuente_dinamica_stock(
            "stock_recepcion"
        )
    )

    stock_detallado = (
        cargar_fuente_dinamica_stock(
            "stock_detallado"
        )
    )

    disponible = (
        cargar_fuente_dinamica_stock(
            "disponible"
        )
    )

    pendientes = (
        cargar_fuente_maestra_stock(
            "pendientes_oc"
        )
    )

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    volumetria = (
        cargar_fuente_maestra_stock(
            "volumetria"
        )
    )

    max_min = (
        cargar_fuente_maestra_stock(
            "max_min"
        )
    )

    stock_recepcion_crudo = (
        stock_recepcion[
            "df"
        ].copy()
    )

    stock_detallado_crudo = (
        stock_detallado[
            "df"
        ].copy()
    )

    tabla_articulos = (
        articulos[
            "df"
        ].copy()
    )

    tabla_volumetria = (
        volumetria[
            "df"
        ].copy()
    )

    tabla_max_min = (
        preparar_max_min(
            max_min[
                "df"
            ]
        )
    )

    tabla_pendientes_oc = (
        construir_pendientes_oc(
            pendientes[
                "df"
            ].copy(),
            tabla_articulos,
            tabla_volumetria,
            tabla_max_min,
            disponible[
                "df"
            ],
        )
    )

    # ConfirmacionesIngresoOC permanece en Google Sheets.
    confirmaciones_oc = (
        leer_confirmaciones_oc()
    )

    tabla_pendientes_oc = (
        aplicar_confirmaciones_oc(
            tabla_pendientes_oc,
            confirmaciones_oc,
        )
    )

    tabla_pendientes_oc = (
        _asegurar_fechas_recepcion(
            tabla_pendientes_oc
        )
    )

    tabla_recepcion_agrupada = (
        construir_recepcion_agrupada(
            stock_recepcion_crudo,
            tabla_articulos,
            tabla_volumetria,
            tabla_max_min,
        )
    )

    tabla_stock_total_detallado = (
        construir_stock_total_detallado(
            stock_detallado_crudo,
            stock_recepcion_crudo,
        )
    )

    tabla_stock_total_articulo = (
        construir_stock_total_por_articulo(
            tabla_stock_total_detallado
        )
    )

    return {
        "tabla_pendientes_oc":
            tabla_pendientes_oc,
        "confirmaciones_oc":
            confirmaciones_oc,
        "tabla_recepcion_agrupada":
            tabla_recepcion_agrupada,
        "tabla_stock_recepcion":
            preparar_tabla_stock(
                stock_recepcion_crudo,
                "Stock Recepción",
            ),
        "tabla_stock_total_detallado":
            tabla_stock_total_detallado,
        "tabla_stock_total_articulo":
            tabla_stock_total_articulo,
        "tabla_articulos":
            tabla_articulos,
        "tabla_volumetria":
            tabla_volumetria,
        "tabla_max_min":
            tabla_max_min,
    }


# ==========================================================
# FECHAS OC PARA COBERTURA DE PEDIDOS
# ==========================================================

@st.cache_data(
    ttl=300,
    max_entries=2,
    show_spinner=(
        "Buscando próximas fechas "
        "de ingreso de OC..."
    ),
)
def construir_fechas_oc_cobertura() -> pd.DataFrame:
    """
    Devuelve una sola referencia de OC por artículo
    para la vista de cobertura.

    Prioriza la fecha operativa: confirmada cuando existe;
    en caso contrario, estimada. Si un artículo tiene varias
    OC pendientes, conserva la fecha más próxima.
    """

    pendientes = (
        cargar_fuente_maestra_stock(
            "pendientes_oc"
        )
    )

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    volumetria = (
        cargar_fuente_maestra_stock(
            "volumetria"
        )
    )

    max_min = (
        cargar_fuente_maestra_stock(
            "max_min"
        )
    )

    disponible = (
        cargar_fuente_dinamica_stock(
            "disponible"
        )
    )

    tabla = construir_pendientes_oc(
        pendientes[
            "df"
        ].copy(),
        articulos[
            "df"
        ].copy(),
        volumetria[
            "df"
        ].copy(),
        preparar_max_min(
            max_min[
                "df"
            ]
        ),
        disponible[
            "df"
        ],
    )

    if (
        tabla is None
        or tabla.empty
    ):
        return pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "OrdenCompraProxima",
                "FechaPrevistaIngresoOC",
                "TipoFechaIngresoOC",
            ]
        )

    # ConfirmacionesIngresoOC permanece en Google Sheets.
    confirmaciones_oc = (
        leer_confirmaciones_oc()
    )

    tabla = aplicar_confirmaciones_oc(
        tabla,
        confirmaciones_oc,
    )

    tabla = _asegurar_fechas_recepcion(
        tabla
    )

    salida = tabla.copy()

    salida[
        "ArticuloCodigo"
    ] = (
        salida[
            "ArticuloCodigo"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )

    salida[
        "FechaPrevistaIngresoOC"
    ] = pd.to_datetime(
        salida[
            "FechaOperativaIngreso"
        ],
        errors="coerce",
    )

    salida[
        "OrdenCompraProxima"
    ] = (
        salida[
            "OrdenCompra"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    salida[
        "TipoFechaIngresoOC"
    ] = (
        salida.get(
            "TipoFechaIngreso",
            "",
        )
        if (
            "TipoFechaIngreso"
            in salida.columns
        )
        else ""
    )

    salida = salida.loc[
        salida[
            "ArticuloCodigo"
        ].ne("")
    ].copy()

    salida[
        "_SinFecha"
    ] = (
        salida[
            "FechaPrevistaIngresoOC"
        ].isna()
    )

    salida = salida.sort_values(
        [
            "ArticuloCodigo",
            "_SinFecha",
            "FechaPrevistaIngresoOC",
            "OrdenCompraProxima",
        ],
        ascending=[
            True,
            True,
            True,
            True,
        ],
        na_position="last",
    )

    return (
        salida
        .drop_duplicates(
            "ArticuloCodigo",
            keep="first",
        )[
            [
                "ArticuloCodigo",
                "OrdenCompraProxima",
                "FechaPrevistaIngresoOC",
                "TipoFechaIngresoOC",
            ]
        ]
        .reset_index(
            drop=True
        )
    )


# ==========================================================
# OCUPACION
# ==========================================================

@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner=(
        "Preparando ocupación "
        "y mapa del depósito..."
    ),
)
def construir_contexto_ocupacion() -> dict:
    stock_detallado = (
        cargar_fuente_dinamica_stock(
            "stock_detallado"
        )
    )

    stock_calidad = (
        cargar_fuente_dinamica_stock(
            "calidad"
        )
    )

    ubicaciones = (
        cargar_fuente_maestra_stock(
            "ubicaciones"
        )
    )

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    volumetria = (
        cargar_fuente_maestra_stock(
            "volumetria"
        )
    )

    stock_detallado_crudo = (
        stock_detallado[
            "df"
        ].copy()
    )

    stock_calidad_crudo = (
        stock_calidad[
            "df"
        ].copy()
    )

    ubicaciones_crudo = (
        ubicaciones[
            "df"
        ].copy()
    )

    (
        tabla_ocupacion,
        diagnostico,
    ) = construir_ocupacion_deposito(
        ubicaciones_crudo,
        stock_detallado_crudo,
    )

    tabla_calidad_detallada = (
        preparar_stock_calidad(
            stock_calidad_crudo,
            tabla_articulos=(
                articulos[
                    "df"
                ].copy()
            ),
            tabla_volumetria=(
                volumetria[
                    "df"
                ].copy()
            ),
            maestro_ubicaciones=(
                ubicaciones_crudo
            ),
        )
    )

    (
        tabla_ocupacion_calidad,
        resumen_global_calidad,
    ) = construir_ocupacion_calidad(
        ubicaciones_crudo,
        tabla_calidad_detallada,
    )

    tabla_stock_mapa = (
        construir_stock_total_detallado(
            stock_detallado_crudo,
            pd.DataFrame(),
        )
    )

    return {
        "tabla_maestro_ubicaciones":
            preparar_maestro_ubicaciones(
                ubicaciones_crudo
            ),
        "tabla_ocupacion":
            tabla_ocupacion,
        "diagnostico_ocupacion":
            diagnostico,
        "tabla_stock_total_detallado":
            tabla_stock_mapa,
        "tabla_calidad_detallada":
            tabla_calidad_detallada,
        "tabla_ocupacion_calidad":
            tabla_ocupacion_calidad,
        "resumen_global_calidad":
            resumen_global_calidad,
    }


# ==========================================================
# CALIDAD
# ==========================================================

@st.cache_data(
    ttl=120,
    max_entries=2,
    show_spinner=(
        "Preparando Calidad y Reproceso..."
    ),
)
def construir_contexto_calidad() -> dict:
    stock_calidad = (
        cargar_fuente_dinamica_stock(
            "calidad"
        )
    )

    ubicaciones = (
        cargar_fuente_maestra_stock(
            "ubicaciones"
        )
    )

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    volumetria = (
        cargar_fuente_maestra_stock(
            "volumetria"
        )
    )

    stock_calidad_crudo = (
        stock_calidad[
            "df"
        ].copy()
    )

    ubicaciones_crudo = (
        ubicaciones[
            "df"
        ].copy()
    )

    tabla_calidad_detallada = (
        preparar_stock_calidad(
            stock_calidad_crudo,
            tabla_articulos=(
                articulos[
                    "df"
                ].copy()
            ),
            tabla_volumetria=(
                volumetria[
                    "df"
                ].copy()
            ),
            maestro_ubicaciones=(
                ubicaciones_crudo
            ),
        )
    )

    (
        tabla_ocupacion_calidad,
        resumen_global_calidad,
    ) = construir_ocupacion_calidad(
        ubicaciones_crudo,
        tabla_calidad_detallada,
    )

    tabla_calidad_resumen = (
        resumir_stock_calidad(
            tabla_calidad_detallada
        )
    )

    return {
        "tabla_calidad_detallada":
            tabla_calidad_detallada,
        "tabla_calidad_resumen":
            tabla_calidad_resumen,
        "tabla_ocupacion_calidad":
            tabla_ocupacion_calidad,
        "resumen_global_calidad":
            resumen_global_calidad,
        "tabla_maestro_ubicaciones":
            preparar_maestro_ubicaciones(
                ubicaciones_crudo
            ),
    }


# ==========================================================
# COBERTURA
# ==========================================================

@st.cache_data(
    max_entries=3,
    show_spinner=(
        "Preparando Disponible y Cobertura..."
    ),
)
def construir_contexto_cobertura(
    firma_base_historica: tuple,
) -> dict:
    # La firma forma parte de la clave de caché.
    _ = firma_base_historica

    disponible = (
        cargar_fuente_dinamica_stock(
            "disponible"
        )
    )

    detalle_pendientes = (
        cargar_fuente_dinamica_stock(
            "detalle_pendientes"
        )
    )

    stock_detallado = (
        cargar_fuente_dinamica_stock(
            "stock_detallado"
        )
    )

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    max_min = (
        cargar_fuente_maestra_stock(
            "max_min"
        )
    )

    # Import diferido: la ETL de Métricas no se importa
    # al navegar por otras vistas.
    from models.stock.cobertura import (
        cargar_historico_ventas_stock,
    )

    try:
        historico = (
            cargar_historico_ventas_stock(
                firma_base_historica
            )
        )
    except Exception as error:
        historico = pd.DataFrame()

        st.warning(
            "No se pudo leer la base histórica "
            "para cobertura. "
            "Abrí Métricas y presioná Actualizar "
            "para publicarla. "
            f"Detalle: {error}"
        )

    return {
        "tabla_disponible":
            preparar_tabla_stock(
                disponible[
                    "df"
                ],
                "Stock Disponible",
            ),
        "tabla_detalle_pendientes":
            detalle_pendientes[
                "df"
            ].copy(),
        "historico_ventas_stock":
            historico,
        "tabla_articulos":
            articulos[
                "df"
            ].copy(),
        "tabla_max_min":
            preparar_max_min(
                max_min[
                    "df"
                ]
            ),
        "tabla_stock_detallado":
            stock_detallado[
                "df"
            ].copy(),
    }


# ==========================================================
# CONFIGURACION / SLOTTING
# ==========================================================

@st.cache_data(
    max_entries=3,
    show_spinner=(
        "Preparando Centro de Slotting..."
    ),
)
def construir_contexto_configuracion(
    firma_base_historica: tuple,
    firma_max_min: tuple,
    firma_ubicaciones: tuple,
) -> dict:
    """
    Carga solamente las fuentes necesarias
    para Slotting V1.

    El histórico todavía se consume desde la
    ubicación administrada por Métricas y se
    migrará cuando trabajemos ese módulo.
    """

    _ = firma_base_historica
    _ = firma_max_min
    _ = firma_ubicaciones

    articulos = (
        cargar_fuente_maestra_stock(
            "articulos"
        )
    )

    volumetria = (
        cargar_fuente_maestra_stock(
            "volumetria"
        )
    )

    max_min = (
        cargar_fuente_maestra_versionada_stock(
            "max_min",
            firma_max_min,
        )
    )

    stock_detallado = (
        cargar_fuente_dinamica_stock(
            "stock_detallado"
        )
    )

    ubicaciones = (
        cargar_fuente_maestra_versionada_stock(
            "ubicaciones",
            firma_ubicaciones,
        )
    )

    from models.stock.cobertura import (
        cargar_historico_ventas_stock,
    )

    try:
        historico = (
            cargar_historico_ventas_stock(
                firma_base_historica
            )
        )
    except Exception as error:
        historico = pd.DataFrame()

        st.warning(
            "No se pudo leer la base histórica "
            "de Métricas para Slotting. "
            "Abrí Métricas y presioná Actualizar. "
            f"Detalle: {error}"
        )

    return {
        "tabla_articulos":
            articulos[
                "df"
            ].copy(),
        "tabla_volumetria":
            volumetria[
                "df"
            ].copy(),
        "tabla_max_min":
            preparar_max_min(
                max_min[
                    "df"
                ]
            ),
        "tabla_stock_detallado":
            stock_detallado[
                "df"
            ].copy(),
        "tabla_maestro_ubicaciones":
            ubicaciones[
                "df"
            ].copy(),
        "historico_ventas_stock":
            historico,
    }


# ==========================================================
# CONTEXTO SEGUN VISTA
# ==========================================================

def construir_contexto_stock(
    vista: str | None = None,
) -> dict:
    """
    Devuelve únicamente el contexto requerido
    por la vista seleccionada.
    """

    texto = str(
        vista or ""
    ).lower()

    if (
        "calidad" in texto
        or "reproceso" in texto
    ):
        return construir_contexto_calidad()

    if (
        "ocupación" in texto
        or "ocupacion" in texto
    ):
        return construir_contexto_ocupacion()

    if (
        "disponible" in texto
        or "cobertura" in texto
        or "situación" in texto
        or "situacion" in texto
    ):
        # TEMPORAL:
        # la base histórica de Métricas todavía no fue
        # migrada a la nueva arquitectura.
        firma_base = (
            firma_base_historica_metricas(
                CARPETA_DATOS
            )
        )

        return construir_contexto_cobertura(
            firma_base
        )

    if (
        "configuración" in texto
        or "configuracion" in texto
    ):
        # TEMPORAL:
        # la base histórica de Métricas todavía no fue
        # migrada a la nueva arquitectura.
        firma_base = (
            firma_base_historica_metricas(
                CARPETA_DATOS
            )
        )

        firma_max_min = (
            firma_fuente_stock(
                "max_min"
            )
        )

        firma_ubicaciones = (
            firma_fuente_stock(
                "ubicaciones"
            )
        )

        return (
            construir_contexto_configuracion(
                firma_base,
                firma_max_min,
                firma_ubicaciones,
            )
        )

    return construir_contexto_existencia()


# ==========================================================
# LIMPIEZA DE CACHE
# ==========================================================

def limpiar_cache_fuentes_dinamicas_stock() -> None:
    cargar_fuente_dinamica_stock.clear()
    construir_contexto_existencia.clear()
    construir_contexto_ocupacion.clear()
    construir_contexto_calidad.clear()
    construir_contexto_cobertura.clear()
    construir_fechas_oc_cobertura.clear()

    from models.stock.cobertura import (
        cargar_historico_ventas_stock,
    )

    cargar_historico_ventas_stock.clear()


def limpiar_cache_stock_completa() -> None:
    """
    Limpia las cachés propias de Stock.

    No borra la base histórica ni las cachés
    mensuales de Métricas.
    """

    cargar_fuente_dinamica_stock.clear()
    cargar_fuente_maestra_stock.clear()
    cargar_fuente_maestra_versionada_stock.clear()
    construir_contexto_existencia.clear()
    construir_contexto_ocupacion.clear()
    construir_contexto_calidad.clear()
    construir_contexto_cobertura.clear()
    construir_contexto_configuracion.clear()
    construir_fechas_oc_cobertura.clear()

    from models.stock.cobertura import (
        cargar_historico_ventas_stock,
    )

    cargar_historico_ventas_stock.clear()
