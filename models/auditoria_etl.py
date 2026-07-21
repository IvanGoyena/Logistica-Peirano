"""
==========================================================
AUDITORÍA DE ETL - MÉTRICAS

Objetivo:
- Comparar los crudos contra la ETL y el enriquecimiento.
- Detectar pérdidas, duplicaciones o cambios de granularidad.
- Auditar Preparación y Control por archivo/mes.
- Separar Preparación de Reposición.
- Conservar varias interpretaciones posibles de unidades.

Este módulo no modifica datos.
==========================================================
"""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd


MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


# ==========================================================
# AUXILIARES
# ==========================================================

def normalizar_texto(valor: object) -> str:
    """Normaliza un texto para comparaciones."""

    texto = str(valor).strip().upper()

    return "".join(
        caracter
        for caracter in unicodedata.normalize(
            "NFD",
            texto,
        )
        if unicodedata.category(caracter) != "Mn"
    )


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    """Normaliza identificadores y códigos."""

    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def convertir_numero(serie: pd.Series) -> pd.Series:
    """Convierte una serie a número sin lanzar error."""

    return pd.to_numeric(
        serie,
        errors="coerce",
    )


def asegurar_columnas(
    dataframe: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    """Agrega las columnas faltantes como NA."""

    resultado = dataframe.copy()

    for columna in columnas:
        if columna not in resultado.columns:
            resultado[columna] = pd.NA

    return resultado


def extraer_periodo_archivo(
    serie_archivo: pd.Series,
) -> pd.DataFrame:
    """
    Extrae mes y año desde nombres como:

        Preparacion Junio 2026.csv
        Control Abril 2026.csv
    """

    archivos = (
        serie_archivo
        .fillna("")
        .astype(str)
        .str.strip()
    )

    registros = []

    for archivo in archivos:

        texto = normalizar_texto(
            Path(archivo).stem
        )

        mes_nombre = ""
        mes_numero = pd.NA
        anio = pd.NA

        for nombre_mes, numero_mes in MESES.items():

            if re.search(
                rf"\b{nombre_mes}\b",
                texto,
            ):
                mes_nombre = nombre_mes.title()
                mes_numero = numero_mes
                break

        coincidencia_anio = re.search(
            r"\b(20\d{2})\b",
            texto,
        )

        if coincidencia_anio:
            anio = int(
                coincidencia_anio.group(1)
            )

        registros.append(
            {
                "MesArchivo": mes_nombre,
                "MesNumeroArchivo": mes_numero,
                "AnioArchivo": anio,
            }
        )

    return pd.DataFrame(
        registros,
        index=serie_archivo.index,
    )


def agregar_periodo_archivo(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega las variables de período tomadas del archivo."""

    resultado = asegurar_columnas(
        dataframe,
        ["ArchivoOrigen"],
    )

    periodo = extraer_periodo_archivo(
        resultado["ArchivoOrigen"]
    )

    for columna in periodo.columns:
        resultado[columna] = periodo[columna]

    resultado["PeriodoArchivo"] = (
        resultado["AnioArchivo"]
        .astype("Int64")
        .astype(str)
        + "-"
        + resultado["MesNumeroArchivo"]
        .astype("Int64")
        .astype(str)
        .str.zfill(2)
    )

    resultado.loc[
        resultado["AnioArchivo"].isna()
        | resultado["MesNumeroArchivo"].isna(),
        "PeriodoArchivo",
    ] = ""

    return resultado


def primera_por_tarea(
    dataframe: pd.DataFrame,
    id_columna: str,
) -> pd.DataFrame:
    """
    Conserva una fila por tarea dentro de cada archivo.

    La clave incluye ArchivoOrigen para evitar colisiones
    entre meses.
    """

    base = asegurar_columnas(
        dataframe,
        [
            "ArchivoOrigen",
            id_columna,
        ],
    ).copy()

    base[id_columna] = normalizar_codigo(
        base[id_columna]
    )

    return (
        base
        .sort_values(
            [
                "ArchivoOrigen",
                id_columna,
            ]
        )
        .drop_duplicates(
            subset=[
                "ArchivoOrigen",
                id_columna,
            ],
            keep="first",
        )
        .reset_index(drop=True)
    )


def sumar_columna(
    dataframe: pd.DataFrame,
    columna: str,
) -> float:
    """Suma una columna numérica de manera segura."""

    if columna not in dataframe.columns:
        return 0.0

    return float(
        convertir_numero(
            dataframe[columna]
        )
        .fillna(0)
        .sum()
    )


def contar_unicos(
    dataframe: pd.DataFrame,
    columna: str,
) -> int:
    """Cuenta valores únicos no vacíos."""

    if columna not in dataframe.columns:
        return 0

    serie = normalizar_codigo(
        dataframe[columna]
    )

    return int(
        serie[
            serie.ne("")
        ].nunique()
    )


def contar_estado(
    dataframe: pd.DataFrame,
    columna: str,
    valor: str,
) -> int:
    """Cuenta un estado textual normalizado."""

    if columna not in dataframe.columns:
        return 0

    esperado = normalizar_texto(valor)

    serie = (
        dataframe[columna]
        .fillna("")
        .astype(str)
        .map(normalizar_texto)
    )

    return int(
        serie.eq(esperado).sum()
    )


# ==========================================================
# AUDITORÍA DEL CRUDO DE PREPARACIÓN
# ==========================================================

def auditar_preparacion_cruda(
    df_preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """
    Audita Preparación por archivo mensual.

    Devuelve múltiples criterios de unidades:

    - UnidadesCabeceraTodosTipos:
      UnidadesTarea tomada una sola vez por TareaId.

    - UnidadesDetalleTodosTipos:
      suma de UnidadesDetalle, incluyendo Preparación
      y Reposición.

    - UnidadesDetallePreparacion:
      suma de UnidadesDetalle únicamente Tipo=Preparacion.

    - UnidadesDetalleReposicion:
      suma de UnidadesDetalle únicamente Tipo=Reposicion.

    Esto permite identificar qué criterio replica el WMS.
    """

    if df_preparacion is None or df_preparacion.empty:
        return pd.DataFrame()

    base = agregar_periodo_archivo(
        df_preparacion.copy()
    )

    base = asegurar_columnas(
        base,
        [
            "TareaId",
            "Tipo",
            "Usuario",
            "TiempoEstimadoSegundos",
            "TiempoRealSegundos",
            "TiempoEntreTareasSegundos",
            "CumplioTiempo",
            "UnidadesTarea",
            "UnidadesDetalle",
            "Articulos",
            "CodigoArticulo",
            "ArchivoOrigen",
        ],
    )

    base["TareaId"] = normalizar_codigo(
        base["TareaId"]
    )

    base["TipoNormalizado"] = (
        base["Tipo"]
        .fillna("")
        .astype(str)
        .map(normalizar_texto)
    )

    for columna in [
        "TiempoEstimadoSegundos",
        "TiempoRealSegundos",
        "TiempoEntreTareasSegundos",
        "UnidadesTarea",
        "UnidadesDetalle",
        "Articulos",
    ]:
        base[columna] = (
            convertir_numero(
                base[columna]
            )
            .fillna(0)
        )

    cabeceras = primera_por_tarea(
        base,
        "TareaId",
    )

    registros = []

    for archivo, bloque in base.groupby(
        "ArchivoOrigen",
        dropna=False,
        sort=True,
    ):

        cabecera_archivo = cabeceras[
            cabeceras["ArchivoOrigen"].eq(
                archivo
            )
        ].copy()

        detalle_preparacion = bloque[
            bloque["TipoNormalizado"].eq(
                "PREPARACION"
            )
        ]

        detalle_reposicion = bloque[
            bloque["TipoNormalizado"].eq(
                "REPOSICION"
            )
        ]

        cabecera_preparacion = (
            cabecera_archivo[
                cabecera_archivo[
                    "TipoNormalizado"
                ].eq("PREPARACION")
            ]
        )

        cabecera_reposicion = (
            cabecera_archivo[
                cabecera_archivo[
                    "TipoNormalizado"
                ].eq("REPOSICION")
            ]
        )

        fila_periodo = bloque.iloc[0]

        registros.append(
            {
                "Proceso": "PREPARACION",
                "ArchivoOrigen": archivo,
                "PeriodoArchivo": (
                    fila_periodo[
                        "PeriodoArchivo"
                    ]
                ),
                "Mes": fila_periodo[
                    "MesArchivo"
                ],
                "Anio": fila_periodo[
                    "AnioArchivo"
                ],
                "FilasCrudo": len(bloque),
                "TareasUnicasTodosTipos": (
                    cabecera_archivo[
                        "TareaId"
                    ].nunique()
                ),
                "TareasUnicasPreparacion": (
                    cabecera_preparacion[
                        "TareaId"
                    ].nunique()
                ),
                "TareasUnicasReposicion": (
                    cabecera_reposicion[
                        "TareaId"
                    ].nunique()
                ),
                "UsuariosUnicos": contar_unicos(
                    cabecera_archivo,
                    "Usuario",
                ),
                "UnidadesCabeceraTodosTipos": (
                    sumar_columna(
                        cabecera_archivo,
                        "UnidadesTarea",
                    )
                ),
                "UnidadesCabeceraPreparacion": (
                    sumar_columna(
                        cabecera_preparacion,
                        "UnidadesTarea",
                    )
                ),
                "UnidadesCabeceraReposicion": (
                    sumar_columna(
                        cabecera_reposicion,
                        "UnidadesTarea",
                    )
                ),
                "UnidadesDetalleTodosTipos": (
                    sumar_columna(
                        bloque,
                        "UnidadesDetalle",
                    )
                ),
                "UnidadesDetallePreparacion": (
                    sumar_columna(
                        detalle_preparacion,
                        "UnidadesDetalle",
                    )
                ),
                "UnidadesDetalleReposicion": (
                    sumar_columna(
                        detalle_reposicion,
                        "UnidadesDetalle",
                    )
                ),
                "TiempoEstimadoSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoEstimadoSegundos",
                    )
                ),
                "TiempoRealSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoRealSegundos",
                    )
                ),
                "TiempoEntreTareasSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoEntreTareasSegundos",
                    )
                ),
                "EnTiempo": contar_estado(
                    cabecera_archivo,
                    "CumplioTiempo",
                    "En Tiempo",
                ),
                "FueraDeTiempo": contar_estado(
                    cabecera_archivo,
                    "CumplioTiempo",
                    "Fuera de Tiempo",
                ),
                "ArticulosUnicos": contar_unicos(
                    bloque,
                    "CodigoArticulo",
                ),
            }
        )

    resultado = pd.DataFrame(
        registros
    )

    resultado["DiferenciaCabeceraVsDetalle"] = (
        resultado[
            "UnidadesCabeceraTodosTipos"
        ]
        - resultado[
            "UnidadesDetalleTodosTipos"
        ]
    )

    resultado[
        "DiferenciaPreparacionVsTotal"
    ] = (
        resultado[
            "UnidadesDetalleTodosTipos"
        ]
        - resultado[
            "UnidadesDetallePreparacion"
        ]
    )

    return resultado.sort_values(
        [
            "Anio",
            "PeriodoArchivo",
        ]
    ).reset_index(drop=True)


# ==========================================================
# AUDITORÍA DEL CRUDO DE CONTROL
# ==========================================================

def auditar_control_crudo(
    df_control: pd.DataFrame,
) -> pd.DataFrame:
    """
    Audita Control por archivo mensual.

    En el reporte del WMS, la cantidad de controles suele
    corresponder a filas/líneas controladas, mientras que
    ControlContenedorId identifica el contenedor/tarea.
    Se conservan ambas cantidades.
    """

    if df_control is None or df_control.empty:
        return pd.DataFrame()

    base = agregar_periodo_archivo(
        df_control.copy()
    )

    base = asegurar_columnas(
        base,
        [
            "ControlContenedorId",
            "Usuario",
            "TiempoEstimadoSegundos",
            "TiempoRealSegundos",
            "TiempoEntreTareasSegundos",
            "CumplioTiempo",
            "Unidades",
            "UnidadesDetalle",
            "Articulos",
            "CodigoArticulo",
            "ArchivoOrigen",
        ],
    )

    base["ControlContenedorId"] = (
        normalizar_codigo(
            base["ControlContenedorId"]
        )
    )

    for columna in [
        "TiempoEstimadoSegundos",
        "TiempoRealSegundos",
        "TiempoEntreTareasSegundos",
        "Unidades",
        "UnidadesDetalle",
        "Articulos",
    ]:
        base[columna] = (
            convertir_numero(
                base[columna]
            )
            .fillna(0)
        )

    cabeceras = primera_por_tarea(
        base,
        "ControlContenedorId",
    )

    registros = []

    for archivo, bloque in base.groupby(
        "ArchivoOrigen",
        dropna=False,
        sort=True,
    ):

        cabecera_archivo = cabeceras[
            cabeceras["ArchivoOrigen"].eq(
                archivo
            )
        ].copy()

        fila_periodo = bloque.iloc[0]

        registros.append(
            {
                "Proceso": "CONTROL",
                "ArchivoOrigen": archivo,
                "PeriodoArchivo": (
                    fila_periodo[
                        "PeriodoArchivo"
                    ]
                ),
                "Mes": fila_periodo[
                    "MesArchivo"
                ],
                "Anio": fila_periodo[
                    "AnioArchivo"
                ],
                "FilasCrudo_ControlesSistema": (
                    len(bloque)
                ),
                "ContenedoresUnicos": (
                    cabecera_archivo[
                        "ControlContenedorId"
                    ].nunique()
                ),
                "UsuariosUnicos": contar_unicos(
                    cabecera_archivo,
                    "Usuario",
                ),
                "UnidadesSistema": sumar_columna(
                    bloque,
                    "Unidades",
                ),
                "UnidadesDetalle": sumar_columna(
                    bloque,
                    "UnidadesDetalle",
                ),
                "TiempoEstimadoSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoEstimadoSegundos",
                    )
                ),
                "TiempoRealSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoRealSegundos",
                    )
                ),
                "TiempoEntreTareasSegundos": (
                    sumar_columna(
                        cabecera_archivo,
                        "TiempoEntreTareasSegundos",
                    )
                ),
                "EnTiempo": contar_estado(
                    bloque,
                    "CumplioTiempo",
                    "En Tiempo",
                ),
                "FueraDeTiempo": contar_estado(
                    bloque,
                    "CumplioTiempo",
                    "Fuera de Tiempo",
                ),
                "ArticulosSistema": sumar_columna(
                    bloque,
                    "Articulos",
                ),
                "ArticulosUnicos": contar_unicos(
                    bloque,
                    "CodigoArticulo",
                ),
            }
        )

    resultado = pd.DataFrame(
        registros
    )

    resultado[
        "DiferenciaUnidadesSistemaVsDetalle"
    ] = (
        resultado["UnidadesSistema"]
        - resultado["UnidadesDetalle"]
    )

    return resultado.sort_values(
        [
            "Anio",
            "PeriodoArchivo",
        ]
    ).reset_index(drop=True)


# ==========================================================
# CONSISTENCIA INTERNA DE TAREAS
# ==========================================================

def auditar_consistencia_preparacion(
    df_preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """
    Detecta tareas de Preparación donde los datos de cabecera
    cambian entre líneas del mismo TareaId.
    """

    if df_preparacion is None or df_preparacion.empty:
        return pd.DataFrame()

    base = asegurar_columnas(
        df_preparacion.copy(),
        [
            "ArchivoOrigen",
            "TareaId",
            "Tipo",
            "UnidadesTarea",
            "TiempoRealSegundos",
            "TiempoEstimadoSegundos",
            "Usuario",
        ],
    )

    base["TareaId"] = normalizar_codigo(
        base["TareaId"]
    )

    agrupado = (
        base
        .groupby(
            [
                "ArchivoOrigen",
                "TareaId",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Filas=("TareaId", "size"),
            ValoresUnidadesTarea=(
                "UnidadesTarea",
                "nunique",
            ),
            ValoresTiempoReal=(
                "TiempoRealSegundos",
                "nunique",
            ),
            ValoresTiempoEstimado=(
                "TiempoEstimadoSegundos",
                "nunique",
            ),
            ValoresUsuario=(
                "Usuario",
                "nunique",
            ),
            ValoresTipo=(
                "Tipo",
                "nunique",
            ),
            UnidadesCabeceraPrimera=(
                "UnidadesTarea",
                "first",
            ),
            UnidadesDetalleSumadas=(
                "UnidadesDetalle",
                "sum",
            ),
        )
    )

    agrupado["CabeceraInconsistente"] = (
        agrupado[
            [
                "ValoresUnidadesTarea",
                "ValoresTiempoReal",
                "ValoresTiempoEstimado",
                "ValoresUsuario",
                "ValoresTipo",
            ]
        ]
        .gt(1)
        .any(axis=1)
    )

    agrupado["DiferenciaUnidades"] = (
        convertir_numero(
            agrupado[
                "UnidadesCabeceraPrimera"
            ]
        )
        .fillna(0)
        - convertir_numero(
            agrupado[
                "UnidadesDetalleSumadas"
            ]
        )
        .fillna(0)
    )

    return agrupado.sort_values(
        [
            "CabeceraInconsistente",
            "DiferenciaUnidades",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)


def auditar_consistencia_control(
    df_control: pd.DataFrame,
) -> pd.DataFrame:
    """
    Detecta controles donde los campos de cabecera cambian
    entre líneas del mismo ControlContenedorId.
    """

    if df_control is None or df_control.empty:
        return pd.DataFrame()

    base = asegurar_columnas(
        df_control.copy(),
        [
            "ArchivoOrigen",
            "ControlContenedorId",
            "TiempoRealSegundos",
            "TiempoEstimadoSegundos",
            "Usuario",
            "Articulos",
        ],
    )

    base["ControlContenedorId"] = (
        normalizar_codigo(
            base["ControlContenedorId"]
        )
    )

    agrupado = (
        base
        .groupby(
            [
                "ArchivoOrigen",
                "ControlContenedorId",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Filas=("ControlContenedorId", "size"),
            ValoresTiempoReal=(
                "TiempoRealSegundos",
                "nunique",
            ),
            ValoresTiempoEstimado=(
                "TiempoEstimadoSegundos",
                "nunique",
            ),
            ValoresUsuario=(
                "Usuario",
                "nunique",
            ),
            ValoresArticulos=(
                "Articulos",
                "nunique",
            ),
            UnidadesSistema=(
                "Unidades",
                "sum",
            ),
            UnidadesDetalle=(
                "UnidadesDetalle",
                "sum",
            ),
        )
    )

    agrupado["CabeceraInconsistente"] = (
        agrupado[
            [
                "ValoresTiempoReal",
                "ValoresTiempoEstimado",
                "ValoresUsuario",
                "ValoresArticulos",
            ]
        ]
        .gt(1)
        .any(axis=1)
    )

    agrupado["DiferenciaUnidades"] = (
        convertir_numero(
            agrupado["UnidadesSistema"]
        )
        .fillna(0)
        - convertir_numero(
            agrupado["UnidadesDetalle"]
        )
        .fillna(0)
    )

    return agrupado.sort_values(
        [
            "CabeceraInconsistente",
            "DiferenciaUnidades",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)


# ==========================================================
# AUDITORÍA ENTRE ETAPAS
# ==========================================================

def resumir_etapa_tareas(
    dataframe: pd.DataFrame,
    etapa: str,
) -> pd.DataFrame:
    """
    Resume una tabla de tareas limpia o enriquecida
    por proceso y archivo.
    """

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    base = agregar_periodo_archivo(
        dataframe.copy()
    )

    base = asegurar_columnas(
        base,
        [
            "Proceso",
            "ArchivoOrigen",
            "ClaveTarea",
            "TareaId",
            "UnidadesTarea",
            "UnidadesDetalleTotal",
            "UnidadesAnalisis",
            "TiempoRealSegundos",
            "TiempoEstimadoSegundos",
            "VolumenTotalM3",
            "PesoTotalKg",
        ],
    )

    if base["ClaveTarea"].isna().all():

        base["ClaveTarea"] = (
            normalizar_codigo(
                base["Proceso"]
            )
            + "|"
            + normalizar_codigo(
                base["ArchivoOrigen"]
            )
            + "|"
            + normalizar_codigo(
                base["TareaId"]
            )
        )

    resumen = (
        base
        .groupby(
            [
                "Proceso",
                "ArchivoOrigen",
                "PeriodoArchivo",
                "MesArchivo",
                "AnioArchivo",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Tareas=("ClaveTarea", "nunique"),
            UnidadesTarea=(
                "UnidadesTarea",
                "sum",
            ),
            UnidadesDetalleTotal=(
                "UnidadesDetalleTotal",
                "sum",
            ),
            UnidadesAnalisis=(
                "UnidadesAnalisis",
                "sum",
            ),
            TiempoRealSegundos=(
                "TiempoRealSegundos",
                "sum",
            ),
            TiempoEstimadoSegundos=(
                "TiempoEstimadoSegundos",
                "sum",
            ),
            VolumenTotalM3=(
                "VolumenTotalM3",
                "sum",
            ),
            PesoTotalKg=(
                "PesoTotalKg",
                "sum",
            ),
        )
    )

    resumen["Etapa"] = etapa

    return resumen.rename(
        columns={
            "MesArchivo": "Mes",
            "AnioArchivo": "Anio",
        }
    )


def construir_comparacion_etapas(
    auditoria_preparacion: pd.DataFrame,
    auditoria_control: pd.DataFrame,
    tareas_limpias: pd.DataFrame | None = None,
    tareas_enriquecidas: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Construye una tabla larga para comparar crudo, ETL
    y enriquecimiento.
    """

    filas = []

    if not auditoria_preparacion.empty:

        for _, fila in auditoria_preparacion.iterrows():

            filas.append(
                {
                    "Proceso": "PREPARACION",
                    "ArchivoOrigen": fila[
                        "ArchivoOrigen"
                    ],
                    "PeriodoArchivo": fila[
                        "PeriodoArchivo"
                    ],
                    "Mes": fila["Mes"],
                    "Anio": fila["Anio"],
                    "Etapa": "CRUDO",
                    "Tareas": fila[
                        "TareasUnicasPreparacion"
                    ],
                    "UnidadesSistema": fila[
                        "UnidadesDetallePreparacion"
                    ],
                    "UnidadesTodosTipos": fila[
                        "UnidadesDetalleTodosTipos"
                    ],
                    "TiempoRealSegundos": fila[
                        "TiempoRealSegundos"
                    ],
                    "TiempoEstimadoSegundos": fila[
                        "TiempoEstimadoSegundos"
                    ],
                }
            )

    if not auditoria_control.empty:

        for _, fila in auditoria_control.iterrows():

            filas.append(
                {
                    "Proceso": "CONTROL",
                    "ArchivoOrigen": fila[
                        "ArchivoOrigen"
                    ],
                    "PeriodoArchivo": fila[
                        "PeriodoArchivo"
                    ],
                    "Mes": fila["Mes"],
                    "Anio": fila["Anio"],
                    "Etapa": "CRUDO",
                    "Tareas": fila[
                        "ContenedoresUnicos"
                    ],
                    "UnidadesSistema": fila[
                        "UnidadesSistema"
                    ],
                    "UnidadesTodosTipos": fila[
                        "UnidadesSistema"
                    ],
                    "TiempoRealSegundos": fila[
                        "TiempoRealSegundos"
                    ],
                    "TiempoEstimadoSegundos": fila[
                        "TiempoEstimadoSegundos"
                    ],
                }
            )

    crudo = pd.DataFrame(
        filas
    )

    etapas = [crudo]

    if tareas_limpias is not None:

        limpio = resumir_etapa_tareas(
            tareas_limpias,
            "ETL_LIMPIA",
        )

        if not limpio.empty:

            limpio["UnidadesSistema"] = np.where(
                limpio["Proceso"].eq(
                    "PREPARACION"
                ),
                limpio["UnidadesTarea"],
                limpio["UnidadesDetalleTotal"],
            )

            limpio["UnidadesTodosTipos"] = (
                limpio["UnidadesAnalisis"]
            )

            etapas.append(limpio)

    if tareas_enriquecidas is not None:

        enriquecido = resumir_etapa_tareas(
            tareas_enriquecidas,
            "ENRIQUECIDA",
        )

        if not enriquecido.empty:

            enriquecido[
                "UnidadesSistema"
            ] = enriquecido[
                "UnidadesAnalisis"
            ]

            enriquecido[
                "UnidadesTodosTipos"
            ] = enriquecido[
                "UnidadesAnalisis"
            ]

            etapas.append(enriquecido)

    resultado = pd.concat(
        etapas,
        ignore_index=True,
        sort=False,
    )

    return resultado.sort_values(
        [
            "Proceso",
            "PeriodoArchivo",
            "Etapa",
        ]
    ).reset_index(drop=True)


def construir_diferencias_etl(
    comparacion_etapas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compara cada etapa contra el crudo del mismo proceso
    y archivo.
    """

    if comparacion_etapas.empty:
        return pd.DataFrame()

    claves = [
        "Proceso",
        "ArchivoOrigen",
        "PeriodoArchivo",
        "Mes",
        "Anio",
    ]

    crudo = (
        comparacion_etapas[
            comparacion_etapas["Etapa"].eq(
                "CRUDO"
            )
        ]
        [
            claves
            + [
                "Tareas",
                "UnidadesSistema",
                "TiempoRealSegundos",
                "TiempoEstimadoSegundos",
            ]
        ]
        .rename(
            columns={
                "Tareas": "TareasCrudo",
                "UnidadesSistema": (
                    "UnidadesCrudo"
                ),
                "TiempoRealSegundos": (
                    "TiempoRealCrudo"
                ),
                "TiempoEstimadoSegundos": (
                    "TiempoEstimadoCrudo"
                ),
            }
        )
    )

    otras = comparacion_etapas[
        ~comparacion_etapas["Etapa"].eq(
            "CRUDO"
        )
    ].copy()

    if otras.empty:
        return pd.DataFrame()

    resultado = otras.merge(
        crudo,
        on=claves,
        how="left",
        validate="many_to_one",
    )

    resultado["DiferenciaTareas"] = (
        resultado["Tareas"]
        - resultado["TareasCrudo"]
    )

    resultado["DiferenciaUnidades"] = (
        resultado["UnidadesSistema"]
        - resultado["UnidadesCrudo"]
    )

    resultado["DiferenciaTiempoReal"] = (
        resultado["TiempoRealSegundos"]
        - resultado["TiempoRealCrudo"]
    )

    resultado[
        "DiferenciaTiempoEstimado"
    ] = (
        resultado[
            "TiempoEstimadoSegundos"
        ]
        - resultado[
            "TiempoEstimadoCrudo"
        ]
    )

    resultado["VariacionUnidadesPct"] = (
        resultado["DiferenciaUnidades"]
        / resultado["UnidadesCrudo"].replace(
            0,
            np.nan,
        )
        * 100
    ).round(2)

    resultado["EstadoAuditoria"] = np.select(
        [
            (
                resultado["DiferenciaTareas"].eq(0)
                & resultado[
                    "DiferenciaUnidades"
                ].abs().le(0.001)
                & resultado[
                    "DiferenciaTiempoReal"
                ].abs().le(0.001)
            ),
            resultado[
                "DiferenciaUnidades"
            ].abs().le(0.001),
        ],
        [
            "OK",
            "REVISAR TAREAS/TIEMPOS",
        ],
        default="REVISAR UNIDADES",
    )

    columnas_salida = (
        claves
        + [
            "Etapa",
            "TareasCrudo",
            "Tareas",
            "DiferenciaTareas",
            "UnidadesCrudo",
            "UnidadesSistema",
            "DiferenciaUnidades",
            "VariacionUnidadesPct",
            "TiempoRealCrudo",
            "TiempoRealSegundos",
            "DiferenciaTiempoReal",
            "TiempoEstimadoCrudo",
            "TiempoEstimadoSegundos",
            "DiferenciaTiempoEstimado",
            "EstadoAuditoria",
        ]
    )

    return resultado[
        columnas_salida
    ].sort_values(
        [
            "Proceso",
            "PeriodoArchivo",
            "Etapa",
        ]
    ).reset_index(drop=True)


# ==========================================================
# FUNCIÓN PRINCIPAL
# ==========================================================

def ejecutar_auditoria_etl(
    df_control: pd.DataFrame,
    df_preparacion: pd.DataFrame,
    tareas_limpias: pd.DataFrame | None = None,
    tareas_enriquecidas: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Ejecuta la auditoría completa.

    Parámetros opcionales:
    - tareas_limpias: etl["tareas"]
    - tareas_enriquecidas:
      enriquecimiento["tareas_enriquecidas"]

    Devuelve:
        auditoria_preparacion
        auditoria_control
        consistencia_preparacion
        consistencia_control
        comparacion_etapas
        diferencias_etl
    """

    auditoria_preparacion = (
        auditar_preparacion_cruda(
            df_preparacion
        )
    )

    auditoria_control = (
        auditar_control_crudo(
            df_control
        )
    )

    consistencia_preparacion = (
        auditar_consistencia_preparacion(
            df_preparacion
        )
    )

    consistencia_control = (
        auditar_consistencia_control(
            df_control
        )
    )

    comparacion_etapas = (
        construir_comparacion_etapas(
            auditoria_preparacion=(
                auditoria_preparacion
            ),
            auditoria_control=(
                auditoria_control
            ),
            tareas_limpias=tareas_limpias,
            tareas_enriquecidas=(
                tareas_enriquecidas
            ),
        )
    )

    diferencias_etl = (
        construir_diferencias_etl(
            comparacion_etapas
        )
    )

    return {
        "auditoria_preparacion": (
            auditoria_preparacion
        ),
        "auditoria_control": (
            auditoria_control
        ),
        "consistencia_preparacion": (
            consistencia_preparacion
        ),
        "consistencia_control": (
            consistencia_control
        ),
        "comparacion_etapas": (
            comparacion_etapas
        ),
        "diferencias_etl": (
            diferencias_etl
        ),
    }
