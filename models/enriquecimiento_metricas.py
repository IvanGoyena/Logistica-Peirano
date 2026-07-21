"""
==========================================================
ENRIQUECIMIENTO DE MÉTRICAS

Este módulo recibe:

- Tabla de tareas homologadas.
- Tabla de detalle homologada.
- Maestro Artículo crudo.
- Maestro Volumetría ya procesado.

Y genera:

- Detalle enriquecido por artículo.
- Resumen enriquecido por tarea.
- Indicadores de cobertura de maestros.

No lee archivos directamente.
No modifica los DataFrames originales.
==========================================================
"""

import unicodedata

import numpy as np
import pandas as pd


# ==========================================================
# COLUMNAS DEL MAESTRO ARTÍCULO
# ==========================================================

COLUMNAS_MAESTRO_ARTICULO = [
    "CodigoArticulo",
    "DescripcionMaestro",
    "CodigoRubro",
    "CodigoMarca",
    "Rubro",
    "Marca",
    "Terminacion",
    "TipoArticulo",
    "Origen",
    "Gama",
    "Familia",
    "Sector",
    "Familia2",
    "Sectorizacion",
]


# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def normalizar_codigo(
    serie: pd.Series,
) -> pd.Series:
    """
    Normaliza códigos para realizar cruces confiables.
    """

    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def limpiar_texto(
    serie: pd.Series,
    mayusculas: bool = False,
) -> pd.Series:
    """
    Limpia espacios y valores nulos.
    """

    resultado = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if mayusculas:
        resultado = resultado.str.upper()

    return resultado


def normalizar_nombre_columna(
    valor: object,
) -> str:
    """
    Normaliza nombres de columnas para comparaciones.
    """

    texto = str(valor).strip()

    texto = "".join(
        caracter
        for caracter in unicodedata.normalize(
            "NFD",
            texto,
        )
        if unicodedata.category(caracter) != "Mn"
    )

    return texto.upper()


def asegurar_columnas(
    dataframe: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    """
    Agrega las columnas faltantes con valores vacíos.
    """

    resultado = dataframe.copy()

    for columna in columnas:

        if columna not in resultado.columns:

            resultado[columna] = pd.NA

    return resultado


def construir_clave_tarea(
    dataframe: pd.DataFrame,
) -> pd.Series:
    """
    Construye una clave única para evitar colisiones entre:

    - Procesos.
    - Meses.
    - Archivos.
    - Identificadores de tarea.
    """

    proceso = limpiar_texto(
        dataframe["Proceso"],
        mayusculas=True,
    )

    archivo = limpiar_texto(
        dataframe["ArchivoOrigen"],
        mayusculas=True,
    )

    tarea = normalizar_codigo(
        dataframe["TareaId"]
    )

    return (
        proceso
        + "|"
        + archivo
        + "|"
        + tarea
    )


def valor_principal_ponderado(
    dataframe: pd.DataFrame,
    columna_categoria: str,
    columna_peso: str,
) -> pd.DataFrame:
    """
    Obtiene la categoría principal de cada tarea,
    ponderada por unidades.

    Devuelve:
        ClaveTarea
        ValorPrincipal
    """

    base = dataframe[
        [
            "ClaveTarea",
            columna_categoria,
            columna_peso,
        ]
    ].copy()

    base[columna_categoria] = limpiar_texto(
        base[columna_categoria]
    )

    base[columna_peso] = (
        pd.to_numeric(
            base[columna_peso],
            errors="coerce",
        )
        .fillna(0)
    )

    base = base[
        base[columna_categoria].ne("")
    ].copy()

    if base.empty:

        return pd.DataFrame(
            columns=[
                "ClaveTarea",
                "ValorPrincipal",
            ]
        )

    agrupado = (
        base
        .groupby(
            [
                "ClaveTarea",
                columna_categoria,
            ],
            as_index=False,
            dropna=False,
        )[columna_peso]
        .sum()
    )

    agrupado = agrupado.sort_values(
        by=[
            "ClaveTarea",
            columna_peso,
            columna_categoria,
        ],
        ascending=[
            True,
            False,
            True,
        ],
    )

    principal = (
        agrupado
        .drop_duplicates(
            subset=["ClaveTarea"],
            keep="first",
        )
        [
            [
                "ClaveTarea",
                columna_categoria,
            ]
        ]
        .rename(
            columns={
                columna_categoria: "ValorPrincipal",
            }
        )
        .reset_index(drop=True)
    )

    return principal


# ==========================================================
# MAESTRO ARTÍCULO
# ==========================================================

def construir_maestro_articulos_metricas(
    df_articulos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Selecciona y normaliza únicamente las columnas necesarias
    del Maestro Artículo crudo.

    No requiere un models/articulos.py independiente.
    """

    if df_articulos is None or df_articulos.empty:

        return pd.DataFrame(
            columns=COLUMNAS_MAESTRO_ARTICULO
        )

    tabla = df_articulos.copy()

    tabla.columns = [
        str(columna).strip()
        for columna in tabla.columns
    ]

    mapa_columnas_normalizadas = {
        normalizar_nombre_columna(columna): columna
        for columna in tabla.columns
    }

    columnas_requeridas = {
        "COD_ART": "CodigoArticulo",
        "DESCRIP": "DescripcionMaestro",
    }

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in mapa_columnas_normalizadas
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas obligatorias en Maestro Artículo: "
            f"{columnas_faltantes}"
        )

    renombres = {}

    mapa_renombres = {
        "COD_ART": "CodigoArticulo",
        "DESCRIP": "DescripcionMaestro",
        "COD_RUB": "CodigoRubro",
        "COD_MAR": "CodigoMarca",
        "RUBRO": "Rubro",
        "MARCA": "Marca",
        "TERMINACION": "Terminacion",
        "TIPO": "TipoArticulo",
        "ORIGEN": "Origen",
        "GAMA": "Gama",
        "FAMILIA": "Familia",
        "SECTOR": "Sector",
        "FAMILIA_2": "Familia2",
        "SECTORIZACION": "Sectorizacion",
    }

    for nombre_normalizado, nombre_final in (
        mapa_renombres.items()
    ):

        nombre_original = mapa_columnas_normalizadas.get(
            nombre_normalizado
        )

        if nombre_original is not None:

            renombres[nombre_original] = nombre_final

    tabla = tabla.rename(
        columns=renombres
    )

    tabla = asegurar_columnas(
        tabla,
        COLUMNAS_MAESTRO_ARTICULO,
    )

    tabla["CodigoArticulo"] = normalizar_codigo(
        tabla["CodigoArticulo"]
    )

    columnas_texto = [
        "DescripcionMaestro",
        "CodigoRubro",
        "CodigoMarca",
        "Rubro",
        "Marca",
        "Terminacion",
        "TipoArticulo",
        "Origen",
        "Gama",
        "Familia",
        "Sector",
        "Familia2",
        "Sectorizacion",
    ]

    for columna in columnas_texto:

        tabla[columna] = limpiar_texto(
            tabla[columna]
        )

    tabla = tabla[
        tabla["CodigoArticulo"].ne("")
    ].copy()

    tabla = (
        tabla
        .sort_values(
            [
                "CodigoArticulo",
                "DescripcionMaestro",
            ]
        )
        .drop_duplicates(
            subset=["CodigoArticulo"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return tabla[
        COLUMNAS_MAESTRO_ARTICULO
    ].copy()


# ==========================================================
# MAESTRO VOLUMETRÍA
# ==========================================================

def preparar_volumetria_metricas(
    tabla_volumetria: pd.DataFrame,
) -> pd.DataFrame:
    """
    Valida y normaliza la salida de construir_tabla_volumetria.
    """

    columnas_volumetria = [
        "CodigoArticulo",
        "ArticuloDescripcion",
        "Familia",
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
        "PesoKg",
        "UnidadVenta",
        "VolumenM3",
        "VolumenUnidadVentaM3",
    ]

    if (
        tabla_volumetria is None
        or tabla_volumetria.empty
    ):

        return pd.DataFrame(
            columns=columnas_volumetria
        )

    tabla = asegurar_columnas(
        tabla_volumetria.copy(),
        columnas_volumetria,
    )

    tabla["CodigoArticulo"] = normalizar_codigo(
        tabla["CodigoArticulo"]
    )

    for columna in [
        "ArticuloDescripcion",
        "Familia",
    ]:

        tabla[columna] = limpiar_texto(
            tabla[columna]
        )

    for columna in [
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
        "PesoKg",
        "UnidadVenta",
        "VolumenM3",
        "VolumenUnidadVentaM3",
    ]:

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce",
            )
            .fillna(0)
        )

    tabla = tabla[
        tabla["CodigoArticulo"].ne("")
    ].copy()

    tabla = (
        tabla
        .drop_duplicates(
            subset=["CodigoArticulo"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return tabla[
        columnas_volumetria
    ].copy()


# ==========================================================
# ENRIQUECIMIENTO DEL DETALLE
# ==========================================================

def enriquecer_detalle_metricas(
    df_detalle: pd.DataFrame,
    df_articulos: pd.DataFrame,
    tabla_volumetria: pd.DataFrame,
) -> pd.DataFrame:
    """
    Enriquece cada línea de tarea con información del artículo
    y de volumetría.
    """

    if df_detalle is None or df_detalle.empty:

        return pd.DataFrame()

    detalle = df_detalle.copy()

    detalle = asegurar_columnas(
        detalle,
        [
            "Proceso",
            "TareaId",
            "ArchivoOrigen",
            "CodigoArticulo",
            "DescripcionArticulo",
            "UnidadesDetalle",
            "CantidadConversionDetalle",
            "Ubicacion",
            "SegundosEnPickear",
        ],
    )

    detalle["CodigoArticulo"] = normalizar_codigo(
        detalle["CodigoArticulo"]
    )

    detalle["DescripcionArticulo"] = limpiar_texto(
        detalle["DescripcionArticulo"]
    )

    detalle["UnidadesDetalle"] = (
        pd.to_numeric(
            detalle["UnidadesDetalle"],
            errors="coerce",
        )
        .fillna(0)
    )

    detalle["CantidadConversionDetalle"] = (
        pd.to_numeric(
            detalle["CantidadConversionDetalle"],
            errors="coerce",
        )
        .fillna(0)
    )

    detalle["SegundosEnPickear"] = (
        pd.to_numeric(
            detalle["SegundosEnPickear"],
            errors="coerce",
        )
    )

    detalle["Ubicacion"] = limpiar_texto(
        detalle["Ubicacion"]
    )

    detalle["ClaveTarea"] = construir_clave_tarea(
        detalle
    )

    maestro_articulos = (
        construir_maestro_articulos_metricas(
            df_articulos
        )
    )

    volumetria = preparar_volumetria_metricas(
        tabla_volumetria
    )

    # Evitar conflictos entre la Familia de ambos maestros.
    volumetria = volumetria.rename(
        columns={
            "ArticuloDescripcion": (
                "DescripcionVolumetria"
            ),
            "Familia": "FamiliaVolumetria",
        }
    )

    detalle = detalle.merge(
        maestro_articulos,
        on="CodigoArticulo",
        how="left",
        validate="many_to_one",
    )

    detalle = detalle.merge(
        volumetria,
        on="CodigoArticulo",
        how="left",
        validate="many_to_one",
    )

    columnas_texto_enriquecidas = [
        "DescripcionMaestro",
        "DescripcionVolumetria",
        "CodigoRubro",
        "CodigoMarca",
        "Rubro",
        "Marca",
        "Terminacion",
        "TipoArticulo",
        "Origen",
        "Gama",
        "Familia",
        "FamiliaVolumetria",
        "Sector",
        "Familia2",
        "Sectorizacion",
    ]

    for columna in columnas_texto_enriquecidas:

        detalle[columna] = limpiar_texto(
            detalle[columna]
        )

    # Prioridad de descripción:
    # Maestro Artículo -> Histórico -> Volumetría
    detalle["DescripcionFinal"] = (
        detalle["DescripcionMaestro"]
        .where(
            detalle["DescripcionMaestro"].ne(""),
            detalle["DescripcionArticulo"],
        )
        .where(
            lambda serie: serie.ne(""),
            detalle["DescripcionVolumetria"],
        )
    )

    # Prioridad de familia:
    # Maestro Artículo -> Volumetría
    detalle["FamiliaFinal"] = (
        detalle["Familia"]
        .where(
            detalle["Familia"].ne(""),
            detalle["FamiliaVolumetria"],
        )
    )

    columnas_numericas_volumetria = [
        "AltoMM",
        "AnchoMM",
        "ProfundoMM",
        "PesoKg",
        "UnidadVenta",
        "VolumenM3",
        "VolumenUnidadVentaM3",
    ]

    for columna in columnas_numericas_volumetria:

        detalle[columna] = (
            pd.to_numeric(
                detalle[columna],
                errors="coerce",
            )
            .fillna(0)
        )

    detalle["TieneMaestroArticulo"] = (
        detalle["DescripcionMaestro"].ne("")
        | detalle["Familia"].ne("")
    )

    detalle["TieneVolumetria"] = (
        detalle["VolumenM3"].gt(0)
        | detalle["PesoKg"].gt(0)
    )

    detalle["VolumenLineaM3"] = (
        detalle["UnidadesDetalle"]
        * detalle["VolumenM3"]
    ).round(6)

    detalle["PesoLineaKg"] = (
        detalle["UnidadesDetalle"]
        * detalle["PesoKg"]
    ).round(3)

    detalle["VolumenConversionM3"] = (
        detalle["CantidadConversionDetalle"]
        * detalle["VolumenM3"]
    ).round(6)

    detalle["PesoConversionKg"] = (
        detalle["CantidadConversionDetalle"]
        * detalle["PesoKg"]
    ).round(3)

    detalle["SegundosPorUnidadLinea"] = np.where(
        (
            detalle["SegundosEnPickear"].notna()
            & detalle["UnidadesDetalle"].gt(0)
        ),
        (
            detalle["SegundosEnPickear"]
            / detalle["UnidadesDetalle"]
        ),
        np.nan,
    )

    detalle["VolumenPorUnidadM3"] = (
        detalle["VolumenM3"]
    )

    detalle["PesoPorUnidadKg"] = (
        detalle["PesoKg"]
    )

    return detalle


# ==========================================================
# RESUMEN POR TAREA
# ==========================================================

def resumir_detalle_por_tarea(
    detalle_enriquecido: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resume el detalle enriquecido a una fila por tarea.
    """

    if (
        detalle_enriquecido is None
        or detalle_enriquecido.empty
    ):

        return pd.DataFrame()

    detalle = detalle_enriquecido.copy()

    resumen = (
        detalle
        .groupby(
            "ClaveTarea",
            as_index=False,
            dropna=False,
        )
        .agg(
            ArticulosDetalle=(
                "CodigoArticulo",
                lambda serie: serie[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            LineasDetalle=(
                "CodigoArticulo",
                "size",
            ),
            FamiliasCantidad=(
                "FamiliaFinal",
                lambda serie: serie[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            Familias2Cantidad=(
                "Familia2",
                lambda serie: serie[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            UbicacionesCantidad=(
                "Ubicacion",
                lambda serie: serie[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            UnidadesDetalleTotal=(
                "UnidadesDetalle",
                "sum",
            ),
            CantidadConversionDetalleTotal=(
                "CantidadConversionDetalle",
                "sum",
            ),
            VolumenTotalM3=(
                "VolumenLineaM3",
                "sum",
            ),
            PesoTotalKg=(
                "PesoLineaKg",
                "sum",
            ),
            VolumenConversionTotalM3=(
                "VolumenConversionM3",
                "sum",
            ),
            PesoConversionTotalKg=(
                "PesoConversionKg",
                "sum",
            ),
            ArticulosConMaestro=(
                "TieneMaestroArticulo",
                "sum",
            ),
            ArticulosConVolumetria=(
                "TieneVolumetria",
                "sum",
            ),
            SegundosPickeoDetalle=(
                "SegundosEnPickear",
                "sum",
            ),
        )
    )

    principales = {
        "FamiliaPrincipal": "FamiliaFinal",
        "Familia2Principal": "Familia2",
        "SectorizacionPrincipal": "Sectorizacion",
        "RubroPrincipal": "Rubro",
        "OrigenPrincipal": "Origen",
        "MarcaPrincipal": "Marca",
        "GamaPrincipal": "Gama",
    }

    for nombre_resultado, columna_categoria in (
        principales.items()
    ):

        tabla_principal = valor_principal_ponderado(
            dataframe=detalle,
            columna_categoria=columna_categoria,
            columna_peso="UnidadesDetalle",
        ).rename(
            columns={
                "ValorPrincipal": nombre_resultado,
            }
        )

        resumen = resumen.merge(
            tabla_principal,
            on="ClaveTarea",
            how="left",
            validate="one_to_one",
        )

    resumen["CoberturaMaestroPct"] = np.where(
        resumen["LineasDetalle"].gt(0),
        (
            resumen["ArticulosConMaestro"]
            / resumen["LineasDetalle"]
            * 100
        ),
        0,
    ).round(2)

    resumen["CoberturaVolumetriaPct"] = np.where(
        resumen["LineasDetalle"].gt(0),
        (
            resumen["ArticulosConVolumetria"]
            / resumen["LineasDetalle"]
            * 100
        ),
        0,
    ).round(2)

    resumen["VolumenTotalM3"] = (
        resumen["VolumenTotalM3"].round(3)
    )

    resumen["PesoTotalKg"] = (
        resumen["PesoTotalKg"].round(2)
    )

    return resumen


# ==========================================================
# ENRIQUECIMIENTO DE TAREAS
# ==========================================================

def enriquecer_tareas_metricas(
    df_tareas: pd.DataFrame,
    detalle_enriquecido: pd.DataFrame,
) -> pd.DataFrame:
    """
    Agrega a la tabla de tareas los indicadores calculados
    desde el detalle enriquecido.
    """

    if df_tareas is None or df_tareas.empty:

        return pd.DataFrame()

    tareas = df_tareas.copy()

    tareas = asegurar_columnas(
        tareas,
        [
            "Proceso",
            "TareaId",
            "ArchivoOrigen",
            "TiempoRealSegundos",
            "UnidadesTarea",
        ],
    )

    tareas["ClaveTarea"] = construir_clave_tarea(
        tareas
    )

    resumen_detalle = resumir_detalle_por_tarea(
        detalle_enriquecido
    )

    tareas = tareas.merge(
        resumen_detalle,
        on="ClaveTarea",
        how="left",
        validate="one_to_one",
    )

    columnas_numericas = [
        "ArticulosDetalle",
        "LineasDetalle",
        "FamiliasCantidad",
        "Familias2Cantidad",
        "UbicacionesCantidad",
        "UnidadesDetalleTotal",
        "CantidadConversionDetalleTotal",
        "VolumenTotalM3",
        "PesoTotalKg",
        "VolumenConversionTotalM3",
        "PesoConversionTotalKg",
        "ArticulosConMaestro",
        "ArticulosConVolumetria",
        "SegundosPickeoDetalle",
        "CoberturaMaestroPct",
        "CoberturaVolumetriaPct",
    ]

    for columna in columnas_numericas:

        if columna in tareas.columns:

            tareas[columna] = (
                pd.to_numeric(
                    tareas[columna],
                    errors="coerce",
                )
                .fillna(0)
            )

    tiempo_horas = (
        pd.to_numeric(
            tareas["TiempoRealSegundos"],
            errors="coerce",
        )
        / 3600
    )

    tiempo_horas = tiempo_horas.where(
        tiempo_horas > 0
    )

    unidades_base = (
        pd.to_numeric(
            tareas["UnidadesTarea"],
            errors="coerce",
        )
        .fillna(0)
    )

    unidades_detalle = (
        pd.to_numeric(
            tareas["UnidadesDetalleTotal"],
            errors="coerce",
        )
        .fillna(0)
    )

    tareas["UnidadesAnalisis"] = (
        unidades_base.where(
            unidades_base.gt(0),
            unidades_detalle,
        )
    )

    tareas["UnidadesPorHora"] = (
        tareas["UnidadesAnalisis"]
        / tiempo_horas
    ).round(2)

    tareas["ArticulosPorHora"] = (
        tareas["ArticulosDetalle"]
        / tiempo_horas
    ).round(2)

    tareas["LineasPorHora"] = (
        tareas["LineasDetalle"]
        / tiempo_horas
    ).round(2)

    tareas["M3PorHora"] = (
        tareas["VolumenTotalM3"]
        / tiempo_horas
    ).round(3)

    tareas["KgPorHora"] = (
        tareas["PesoTotalKg"]
        / tiempo_horas
    ).round(2)

    tareas["SegundosPorUnidad"] = np.where(
        tareas["UnidadesAnalisis"].gt(0),
        (
            tareas["TiempoRealSegundos"]
            / tareas["UnidadesAnalisis"]
        ),
        np.nan,
    )

    tareas["SegundosPorArticulo"] = np.where(
        tareas["ArticulosDetalle"].gt(0),
        (
            tareas["TiempoRealSegundos"]
            / tareas["ArticulosDetalle"]
        ),
        np.nan,
    )

    tareas["ComplejidadBase"] = (
        tareas["ArticulosDetalle"]
        + tareas["FamiliasCantidad"] * 2
        + tareas["UbicacionesCantidad"]
        + tareas["VolumenTotalM3"] * 5
    ).round(2)

    tareas["NivelComplejidad"] = pd.cut(
        tareas["ComplejidadBase"],
        bins=[
            -np.inf,
            5,
            12,
            25,
            np.inf,
        ],
        labels=[
            "BAJA",
            "MEDIA",
            "ALTA",
            "CRITICA",
        ],
    ).astype(str)

    tareas.loc[
        tareas["NivelComplejidad"].eq("nan"),
        "NivelComplejidad",
    ] = "SIN DATOS"

    return tareas


# ==========================================================
# CALIDAD DEL ENRIQUECIMIENTO
# ==========================================================

def construir_calidad_enriquecimiento(
    detalle_enriquecido: pd.DataFrame,
    tareas_enriquecidas: pd.DataFrame,
) -> pd.DataFrame:
    """
    Genera indicadores de cobertura del enriquecimiento.
    """

    if detalle_enriquecido.empty:

        return pd.DataFrame(
            columns=[
                "Indicador",
                "Valor",
            ]
        )

    total_lineas = len(
        detalle_enriquecido
    )

    con_articulo = int(
        detalle_enriquecido[
            "TieneMaestroArticulo"
        ].sum()
    )

    con_volumetria = int(
        detalle_enriquecido[
            "TieneVolumetria"
        ].sum()
    )

    return pd.DataFrame(
        [
            {
                "Indicador": "Líneas de detalle",
                "Valor": total_lineas,
            },
            {
                "Indicador": (
                    "Líneas encontradas en Maestro Artículo"
                ),
                "Valor": con_articulo,
            },
            {
                "Indicador": (
                    "Cobertura Maestro Artículo %"
                ),
                "Valor": round(
                    con_articulo
                    / total_lineas
                    * 100,
                    2,
                ),
            },
            {
                "Indicador": (
                    "Líneas con volumetría"
                ),
                "Valor": con_volumetria,
            },
            {
                "Indicador": (
                    "Cobertura Volumetría %"
                ),
                "Valor": round(
                    con_volumetria
                    / total_lineas
                    * 100,
                    2,
                ),
            },
            {
                "Indicador": "Tareas enriquecidas",
                "Valor": len(tareas_enriquecidas),
            },
            {
                "Indicador": "Volumen total m³",
                "Valor": round(
                    detalle_enriquecido[
                        "VolumenLineaM3"
                    ].sum(),
                    3,
                ),
            },
            {
                "Indicador": "Peso total kg",
                "Valor": round(
                    detalle_enriquecido[
                        "PesoLineaKg"
                    ].sum(),
                    2,
                ),
            },
        ]
    )


# ==========================================================
# FUNCIÓN PRINCIPAL
# ==========================================================

def ejecutar_enriquecimiento_metricas(
    df_tareas: pd.DataFrame,
    df_detalle: pd.DataFrame,
    df_articulos: pd.DataFrame,
    tabla_volumetria: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Ejecuta todo el enriquecimiento del módulo de métricas.

    Devuelve:
        {
            "maestro_articulos": ...,
            "volumetria": ...,
            "detalle_enriquecido": ...,
            "resumen_detalle": ...,
            "tareas_enriquecidas": ...,
            "calidad_enriquecimiento": ...,
        }
    """

    maestro_articulos = (
        construir_maestro_articulos_metricas(
            df_articulos
        )
    )

    volumetria = preparar_volumetria_metricas(
        tabla_volumetria
    )

    detalle_enriquecido = (
        enriquecer_detalle_metricas(
            df_detalle=df_detalle,

            # Se envía el Maestro Artículo crudo.
            # La función enriquecer_detalle_metricas se encarga
            # de normalizarlo una única vez.
            df_articulos=df_articulos,

            # La volumetría puede recibirse ya normalizada.
            tabla_volumetria=volumetria,
        )
    )

    resumen_detalle = resumir_detalle_por_tarea(
        detalle_enriquecido
    )

    tareas_enriquecidas = (
        enriquecer_tareas_metricas(
            df_tareas=df_tareas,
            detalle_enriquecido=(
                detalle_enriquecido
            ),
        )
    )

    calidad = construir_calidad_enriquecimiento(
        detalle_enriquecido=detalle_enriquecido,
        tareas_enriquecidas=tareas_enriquecidas,
    )

    return {
        "maestro_articulos": maestro_articulos,
        "volumetria": volumetria,
        "detalle_enriquecido": detalle_enriquecido,
        "resumen_detalle": resumen_detalle,
        "tareas_enriquecidas": tareas_enriquecidas,
        "calidad_enriquecimiento": calidad,
    }
