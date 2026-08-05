
from __future__ import annotations

import math
import re
import unicodedata

import numpy as np
import pandas as pd

from utils.stock.slotting_config import (
    DISTANCIA_CRITICA,
    DISTANCIA_REVISION,
    RADIO_PASILLOS_CERCANOS,
    UMBRAL_PASILLOS_ALTO,
    UMBRAL_PASILLOS_NORMAL,
    tabla_bloques_pasillos,
)


DIAS_VENCIMIENTO_DEFAULT = 2000
DIAS_NUEVO_INGRESO = 90

ORDEN_ROTACION = [
    "🔥 Caliente",
    "🟡 Intermedio",
    "❄️ Frío",
    "🆕 Nuevo ingreso",
    "⚫ Sin movimiento",
]

ORDEN_ACCIONES = [
    "Crear picking",
    "Aumentar capacidad",
    "Reducir capacidad",
    "Evaluar discontinuos",
    "Avisar Comercial",
    "Revisar configuración",
    "Monitorear nuevo ingreso",
    "Configuración correcta",
]


def _clave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return re.sub(
        r"[^a-z0-9]+",
        "",
        texto.lower().strip(),
    )


def _buscar_columna(
    dataframe: pd.DataFrame,
    candidatos: list[str],
) -> str | None:
    if dataframe is None or dataframe.empty:
        return None

    mapa = {
        _clave(columna): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        encontrada = mapa.get(
            _clave(candidato)
        )
        if encontrada is not None:
            return encontrada

    return None


def _serie(
    dataframe: pd.DataFrame,
    candidatos: list[str],
    default=0,
) -> pd.Series:
    columna = _buscar_columna(
        dataframe,
        candidatos,
    )

    if columna is None:
        return pd.Series(
            default,
            index=dataframe.index,
        )

    return dataframe[columna]


def _codigo(serie: pd.Series) -> pd.Series:
    return (
        serie
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


def _texto(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )


def _numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(
            serie,
            errors="coerce",
        ).fillna(0)

    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            "\u00a0",
            "",
            regex=False,
        )
        .str.replace(
            " ",
            "",
            regex=False,
        )
    )

    con_coma = texto.str.contains(
        ",",
        regex=False,
    )

    texto.loc[con_coma] = (
        texto.loc[con_coma]
        .str.replace(
            ".",
            "",
            regex=False,
        )
        .str.replace(
            ",",
            ".",
            regex=False,
        )
    )

    return pd.to_numeric(
        texto,
        errors="coerce",
    ).fillna(0)


def _primero_no_vacio(
    serie: pd.Series,
) -> str:
    for valor in serie:
        texto = str(valor).strip()
        if texto and texto.lower() != "nan":
            return texto
    return ""


def preparar_maestro_articulos_slotting(
    tabla_articulos: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Origen",
    ]

    if tabla_articulos is None or tabla_articulos.empty:
        return pd.DataFrame(
            columns=columnas
        )

    origen = tabla_articulos.copy()

    codigo_col = _buscar_columna(
        origen,
        [
            "COD_ART",
            "CodigoArticulo",
            "ArticuloCodigo",
            "Codigo",
            "Código",
        ],
    )

    if codigo_col is None:
        return pd.DataFrame(
            columns=columnas
        )

    salida = pd.DataFrame(
        index=origen.index
    )
    salida["ArticuloCodigo"] = _codigo(
        origen[codigo_col]
    )

    mapeo = {
        "ArticuloDescripcion": [
            "DESCRIP",
            "Descripcion",
            "Descripción",
            "ArticuloDescripcion",
        ],
        "Familia": [
            "Familia",
            "FamiliaPrincipal",
            "Familia_1",
            "Familia1",
        ],
        "Familia2": [
            "Familia_2",
            "Familia2",
            "Familia 2",
            "Familia Secundaria",
            "FamiliaSecundaria",
        ],
        "Sectorizacion": [
            "Sectorizacion",
            "Sectorización",
            "Sector",
        ],
        "Origen": [
            "Origen",
        ],
    }

    for destino, candidatos in mapeo.items():
        salida[destino] = _texto(
            _serie(
                origen,
                candidatos,
                "",
            )
        )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    return (
        salida
        .drop_duplicates(
            "ArticuloCodigo",
            keep="first",
        )
        [columnas]
        .reset_index(drop=True)
    )


def preparar_max_min_slotting(
    tabla_max_min: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "ArticuloConfigurado",
        "AreaPicking",
        "UbicacionPicking",
        "StockPickingActual",
        "StockPickingConfigurado",
        "StockMinimoActual",
        "StockMaximoActual",
        "StockMaximoPreparar",
    ]

    if tabla_max_min is None or tabla_max_min.empty:
        return pd.DataFrame(
            columns=columnas
        )

    origen = tabla_max_min.copy()

    codigo = _serie(
        origen,
        [
            "codigo_articulo",
            "CodigoArticulo",
            "ArticuloCodigo",
            "Codigo",
            "articulo_codigo",
        ],
        "",
    )

    salida = pd.DataFrame(
        index=origen.index
    )
    salida["ArticuloCodigo"] = _codigo(
        codigo
    )
    salida["ArticuloConfigurado"] = _texto(
        _serie(
            origen,
            [
                "articulo",
                "Articulo",
                "Producto",
            ],
            "",
        )
    )
    salida["AreaPicking"] = _texto(
        _serie(
            origen,
            [
                "area",
                "Area",
                "AREA",
                "AreaPicking",
                "area_picking",
                "AreaDescripcion",
                "area_descripcion",
                "Área",
            ],
            "",
        )
    ).str.upper()
    salida["UbicacionPicking"] = _texto(
        _serie(
            origen,
            [
                "ubicacion",
                "Ubicacion",
                "Ubicación",
                "UBICACION",
                "UbicacionPicking",
                "ubicacion_picking",
                "CodigoUbicacion",
                "codigo_ubicacion",
            ],
            "",
        )
    ).str.upper()
    salida["StockPickingActual"] = _numero(
        _serie(
            origen,
            [
                "unidades_disponibles",
                "UnidadesDisponibles",
                "StockPicking",
                "DisponiblePicking",
            ],
            0,
        )
    )
    salida["StockMinimoActual"] = _numero(
        _serie(
            origen,
            [
                "stock_minimo",
                "StockMinimo",
                "Minimo",
                "Mínimo",
            ],
            0,
        )
    )
    salida["StockMaximoActual"] = _numero(
        _serie(
            origen,
            [
                "stock_maximo",
                "StockMaximo",
                "Maximo",
                "Máximo",
            ],
            0,
        )
    )
    salida["StockMaximoPreparar"] = _numero(
        _serie(
            origen,
            [
                "stock_maximo_Preparar",
                "StockMaximoPreparar",
                "MaximoPreparar",
            ],
            0,
        )
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    # Un artículo puede compartir más de una ubicación de picking.
    # Se conserva el total configurado y se concatenan las ubicaciones.
    return (
        salida
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            ArticuloConfigurado=(
                "ArticuloConfigurado",
                _primero_no_vacio,
            ),
            AreaPicking=(
                "AreaPicking",
                lambda serie: " | ".join(
                    sorted({
                        str(valor).strip()
                        for valor in serie
                        if str(valor).strip()
                    })
                ),
            ),
            UbicacionPicking=(
                "UbicacionPicking",
                lambda serie: " | ".join(
                    sorted({
                        str(valor).strip()
                        for valor in serie
                        if str(valor).strip()
                    })
                ),
            ),
            StockPickingActual=(
                "StockPickingActual",
                "sum",
            ),
            StockMinimoActual=(
                "StockMinimoActual",
                "sum",
            ),
            StockMaximoActual=(
                "StockMaximoActual",
                "sum",
            ),
            StockMaximoPreparar=(
                "StockMaximoPreparar",
                "sum",
            ),
        )
    )


def preparar_volumetria_slotting(
    tabla_volumetria: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "UnidadesPorPallet",
    ]

    if tabla_volumetria is None or tabla_volumetria.empty:
        return pd.DataFrame(
            columns=columnas
        )

    origen = tabla_volumetria.copy()

    codigo_col = _buscar_columna(
        origen,
        [
            "Codigo",
            "Código",
            "CodigoArticulo",
            "ArticuloCodigo",
            "COD_ART",
        ],
    )

    if codigo_col is None:
        return pd.DataFrame(
            columns=columnas
        )

    unidades_col = _buscar_columna(
        origen,
        [
            "UnidadesPorPallet",
            "Unidades Pallet",
            "Unidades x Pallet",
            "Estandarizacion",
            "Estandarización",
            "CantidadPallet",
            "UnidadesEmpaque",
            "Unidades por pallet",
            "Pallet",
        ],
    )

    salida = pd.DataFrame(
        index=origen.index
    )
    salida["ArticuloCodigo"] = _codigo(
        origen[codigo_col]
    )
    salida["UnidadesPorPallet"] = (
        _numero(origen[unidades_col])
        if unidades_col is not None
        else 0
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    return (
        salida
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )["UnidadesPorPallet"]
        .max()
    )




def _normalizar_ubicacion_slotting(valor) -> str:
    texto = str(valor or "").strip().upper()
    texto = re.sub(r"[\s_/]+", "-", texto)
    texto = re.sub(r"-+", "-", texto)
    return texto.strip("-")


def preparar_maestro_ubicaciones_slotting(
    tabla_maestro_ubicaciones: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "UbicacionMaestro",
        "AreaMaestro",
        "TipoUbicacionMaestro",
    ]

    if (
        tabla_maestro_ubicaciones is None
        or tabla_maestro_ubicaciones.empty
    ):
        return pd.DataFrame(columns=columnas)

    origen = tabla_maestro_ubicaciones.copy()

    ubicacion_col = _buscar_columna(
        origen,
        [
            "Ubicacion",
            "Ubicación",
            "CodigoUbicacion",
            "UbicacionCodigo",
        ],
    )
    area_col = _buscar_columna(
        origen,
        [
            "Area",
            "Área",
            "AreaDescripcion",
            "Sector",
        ],
    )
    tipo_col = _buscar_columna(
        origen,
        [
            "Tipo",
            "TipoUbicacion",
            "Tipo Ubicacion",
        ],
    )
    ab_col = _buscar_columna(
        origen,
        ["Ab", "Abreviatura", "Prefijo"],
    )
    pasillo_col = _buscar_columna(
        origen,
        ["Pasillo"],
    )
    posicion_col = _buscar_columna(
        origen,
        ["Posicion", "Posición"],
    )
    nivel_col = _buscar_columna(
        origen,
        ["Nivel"],
    )

    salida = pd.DataFrame(index=origen.index)

    if ubicacion_col is not None:
        salida["UbicacionMaestro"] = (
            origen[ubicacion_col]
            .apply(_normalizar_ubicacion_slotting)
        )
    elif all(
        columna is not None
        for columna in [
            ab_col,
            pasillo_col,
            posicion_col,
            nivel_col,
        ]
    ):
        ab = _texto(origen[ab_col]).str.upper()
        pasillo = pd.to_numeric(
            origen[pasillo_col],
            errors="coerce",
        )
        posicion = pd.to_numeric(
            origen[posicion_col],
            errors="coerce",
        )
        nivel = pd.to_numeric(
            origen[nivel_col],
            errors="coerce",
        )

        salida["UbicacionMaestro"] = [
            (
                f"{prefijo}-{int(p):03d}-{int(pos):03d}-{int(niv):03d}"
                if (
                    str(prefijo).strip()
                    and pd.notna(p)
                    and pd.notna(pos)
                    and pd.notna(niv)
                )
                else ""
            )
            for prefijo, p, pos, niv in zip(
                ab,
                pasillo,
                posicion,
                nivel,
            )
        ]
    else:
        return pd.DataFrame(columns=columnas)

    salida["AreaMaestro"] = (
        _texto(origen[area_col]).str.upper()
        if area_col is not None
        else ""
    )
    salida["TipoUbicacionMaestro"] = (
        _texto(origen[tipo_col]).str.upper()
        if tipo_col is not None
        else ""
    )

    salida = salida.loc[
        salida["UbicacionMaestro"].ne("")
    ].copy()

    return (
        salida
        .drop_duplicates(
            "UbicacionMaestro",
            keep="first",
        )
        [columnas]
        .reset_index(drop=True)
    )


def _inferir_estandar_pallet(
    cantidades: pd.Series,
) -> tuple[float, str]:
    valores = (
        pd.to_numeric(
            cantidades,
            errors="coerce",
        )
        .dropna()
    )
    valores = valores.loc[valores.gt(0)]

    if valores.empty:
        return 0.0, "Sin datos"

    valores = valores.astype(float)

    if len(valores) <= 2:
        return float(valores.max()), "Máximo por pocos pallets"

    conteos = valores.round(6).value_counts()
    moda = float(conteos.index[0])
    frecuencia_moda = int(conteos.iloc[0])

    if frecuencia_moda >= 2:
        return moda, "Moda de pallets cerrados"

    mediana = float(valores.median())
    pallets_completos = valores.loc[
        valores.ge(mediana)
    ]

    if pallets_completos.empty:
        pallets_completos = valores

    estandar = float(
        pallets_completos.median()
    )

    return estandar, "Mediana de pallets más completos"


def _resumir_pallets_almacen(
    stock: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "CantidadPalletsAlmacen",
        "UnidadesPorPalletInferidas",
        "MetodoEstandarizacion",
        "AreaAlmacenPrincipal",
    ]

    if stock.empty:
        return pd.DataFrame(columns=columnas)

    almacen = stock.loc[
        ~stock["EsPicking"]
        & stock["Cantidad"].gt(0)
    ].copy()

    if almacen.empty:
        return pd.DataFrame(columns=columnas)

    almacen["ClavePallet"] = (
        almacen["Contenedor"]
        .where(
            almacen["Contenedor"].ne(""),
            almacen["Ubicacion"],
        )
    )

    almacen = (
        almacen
        .groupby(
            [
                "ArticuloCodigo",
                "ClavePallet",
                "AreaStock",
            ],
            as_index=False,
            dropna=False,
        )["Cantidad"]
        .sum()
    )

    filas = []

    for codigo, grupo in almacen.groupby(
        "ArticuloCodigo",
        sort=False,
    ):
        estandar, metodo = _inferir_estandar_pallet(
            grupo["Cantidad"]
        )

        areas = (
            grupo.groupby(
                "AreaStock",
                dropna=False,
            )["Cantidad"]
            .sum()
            .sort_values(ascending=False)
        )
        area_principal = (
            str(areas.index[0]).strip()
            if len(areas)
            else ""
        )

        filas.append(
            {
                "ArticuloCodigo": codigo,
                "CantidadPalletsAlmacen": int(
                    grupo["ClavePallet"].nunique()
                ),
                "UnidadesPorPalletInferidas": estandar,
                "MetodoEstandarizacion": metodo,
                "AreaAlmacenPrincipal": area_principal,
            }
        )

    return pd.DataFrame(
        filas,
        columns=columnas,
    )


def _extraer_pasillo(
    serie: pd.Series,
) -> pd.Series:
    texto = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Se prioriza el formato habitual área-pasillo-posición-nivel.
    extraido = texto.str.extract(
        r"(?:^|[-_ /])(\d{1,3})(?=[-_ /]|$)",
        expand=False,
    )

    return (
        pd.to_numeric(
            extraido,
            errors="coerce",
        )
    )


def preparar_stock_slotting(
    tabla_stock_detallado: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve:
    - resumen por artículo;
    - distribución detallada por artículo/pasillo.

    La distribución por pasillos es la base de la V2.
    """

    columnas_resumen = [
        "ArticuloCodigo",
        "StockFisico",
        "StockPickingDetectado",
        "StockAlmacenDetectado",
        "CantidadUbicaciones",
        "CantidadPasillos",
        "PasillosStock",
        "PasilloStockPrincipal",
        "CantidadPalletsAlmacen",
        "UnidadesPorPalletInferidas",
        "MetodoEstandarizacion",
        "AreaAlmacenPrincipal",
        "FechaPrimerIngresoStock",
        "DiasDesdeIngresoStock",
        "EsNuevoIngreso",
    ]

    columnas_detalle = [
        "ArticuloCodigo",
        "AreaStock",
        "Ubicacion",
        "PasilloStock",
        "Cantidad",
        "EsPicking",
        "Contenedor",
        "FechaIngresoInferida",
    ]

    if (
        tabla_stock_detallado is None
        or tabla_stock_detallado.empty
    ):
        return (
            pd.DataFrame(columns=columnas_resumen),
            pd.DataFrame(columns=columnas_detalle),
        )

    origen = tabla_stock_detallado.copy()

    codigo_col = _buscar_columna(
        origen,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "Código Artículo",
            "Codigo",
        ],
    )
    cantidad_col = _buscar_columna(
        origen,
        [
            "Cantidad",
            "Unidades",
            "Stock",
            "CantidadStock",
        ],
    )
    area_col = _buscar_columna(
        origen,
        [
            "AreaDescripcion",
            "Area",
            "Área",
            "Zona",
        ],
    )
    ubicacion_col = _buscar_columna(
        origen,
        [
            "Ubicacion",
            "Ubicación",
            "CodigoUbicacion",
        ],
    )
    contenedor_col = _buscar_columna(
        origen,
        [
            "Contenedor",
            "CodigoContenedor",
            "ContenedorCodigo",
            "NroContenedor",
            "NumeroContenedor",
            "LPN",
        ],
    )
    vencimiento_col = _buscar_columna(
        origen,
        [
            "Vencimiento",
            "FechaVencimiento",
            "Fecha Vencimiento",
        ],
    )
    dias_vencimiento_col = _buscar_columna(
        origen,
        [
            "Dias",
            "Días",
            "DiasVencimiento",
            "Días vencimiento",
            "Dias vencimiento",
        ],
    )

    if codigo_col is None:
        return (
            pd.DataFrame(columns=columnas_resumen),
            pd.DataFrame(columns=columnas_detalle),
        )

    stock = pd.DataFrame(index=origen.index)
    stock["ArticuloCodigo"] = _codigo(
        origen[codigo_col]
    )
    stock["Cantidad"] = (
        _numero(origen[cantidad_col])
        if cantidad_col is not None
        else 0
    )
    stock["AreaStock"] = (
        _texto(origen[area_col]).str.upper()
        if area_col is not None
        else ""
    )
    stock["Ubicacion"] = (
        _texto(origen[ubicacion_col]).str.upper()
        if ubicacion_col is not None
        else ""
    )
    stock["Contenedor"] = (
        _texto(origen[contenedor_col]).str.upper()
        if contenedor_col is not None
        else ""
    )

    fecha_hoy = pd.Timestamp.today().normalize()

    vencimiento = (
        pd.to_datetime(
            origen[vencimiento_col],
            errors="coerce",
            dayfirst=True,
        )
        if vencimiento_col is not None
        else pd.Series(pd.NaT, index=origen.index)
    )

    dias_restantes = (
        pd.to_numeric(
            origen[dias_vencimiento_col]
            .astype(str)
            .str.extract(r"(-?\d+)", expand=False),
            errors="coerce",
        )
        if dias_vencimiento_col is not None
        else pd.Series(np.nan, index=origen.index)
    )

    fecha_desde_vencimiento = (
        vencimiento
        - pd.to_timedelta(
            DIAS_VENCIMIENTO_DEFAULT,
            unit="D",
        )
    )

    antiguedad_desde_dias = (
        DIAS_VENCIMIENTO_DEFAULT
        - dias_restantes
    ).clip(lower=0)

    fecha_desde_dias = (
        fecha_hoy
        - pd.to_timedelta(
            antiguedad_desde_dias,
            unit="D",
        )
    )

    stock["FechaIngresoInferida"] = (
        fecha_desde_vencimiento.combine_first(
            fecha_desde_dias
        )
    )

    stock = stock.loc[
        stock["ArticuloCodigo"].ne("")
        & stock["Cantidad"].gt(0)
    ].copy()

    if stock.empty:
        return (
            pd.DataFrame(columns=columnas_resumen),
            pd.DataFrame(columns=columnas_detalle),
        )

    stock["EsPicking"] = (
        stock["AreaStock"].str.contains(
            "PICK|PCK",
            regex=True,
            na=False,
        )
        | stock["Ubicacion"].str.startswith(
            "PCK",
            na=False,
        )
    )

    stock["PasilloStock"] = _extraer_pasillo(
        stock["Ubicacion"]
    )

    stock["StockPicking"] = np.where(
        stock["EsPicking"],
        stock["Cantidad"],
        0,
    )
    stock["StockAlmacen"] = np.where(
        ~stock["EsPicking"],
        stock["Cantidad"],
        0,
    )

    detalle_pasillos = (
        stock
        .groupby(
            [
                "ArticuloCodigo",
                "AreaStock",
                "Ubicacion",
                "PasilloStock",
                "EsPicking",
                "Contenedor",
                "FechaIngresoInferida",
            ],
            as_index=False,
            dropna=False,
        )["Cantidad"]
        .sum()
    )

    distribucion_pasillo = (
        stock.loc[
            stock["PasilloStock"].notna()
        ]
        .groupby(
            [
                "ArticuloCodigo",
                "PasilloStock",
            ],
            as_index=False,
        )["Cantidad"]
        .sum()
    )

    pasillo_principal = (
        distribucion_pasillo
        .sort_values(
            [
                "ArticuloCodigo",
                "Cantidad",
                "PasilloStock",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .drop_duplicates(
            "ArticuloCodigo",
            keep="first",
        )
        [["ArticuloCodigo", "PasilloStock"]]
        .rename(
            columns={
                "PasilloStock": "PasilloStockPrincipal",
            }
        )
    )

    pasillos_texto = (
        distribucion_pasillo
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )["PasilloStock"]
        .agg(
            lambda serie: ", ".join(
                str(int(valor))
                for valor in sorted(
                    set(
                        pd.to_numeric(
                            serie,
                            errors="coerce",
                        ).dropna()
                    )
                )
            )
        )
        .rename(
            columns={
                "PasilloStock": "PasillosStock",
            }
        )
    )

    resumen = (
        stock
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            StockFisico=(
                "Cantidad",
                "sum",
            ),
            StockPickingDetectado=(
                "StockPicking",
                "sum",
            ),
            StockAlmacenDetectado=(
                "StockAlmacen",
                "sum",
            ),
            CantidadUbicaciones=(
                "Ubicacion",
                lambda serie: serie.loc[
                    serie.ne("")
                ].nunique(),
            ),
            CantidadPasillos=(
                "PasilloStock",
                lambda serie: pd.to_numeric(
                    serie,
                    errors="coerce",
                ).dropna().nunique(),
            ),
            FechaPrimerIngresoStock=(
                "FechaIngresoInferida",
                "min",
            ),
        )
        .merge(
            pasillos_texto,
            on="ArticuloCodigo",
            how="left",
        )
        .merge(
            pasillo_principal,
            on="ArticuloCodigo",
            how="left",
        )
    )

    resumen["PasillosStock"] = (
        resumen["PasillosStock"]
        .fillna("")
    )

    resumen["FechaPrimerIngresoStock"] = pd.to_datetime(
        resumen["FechaPrimerIngresoStock"],
        errors="coerce",
    )
    resumen["DiasDesdeIngresoStock"] = (
        pd.Timestamp.today().normalize()
        - resumen["FechaPrimerIngresoStock"]
    ).dt.days
    resumen["EsNuevoIngreso"] = (
        resumen["DiasDesdeIngresoStock"]
        .between(0, DIAS_NUEVO_INGRESO, inclusive="both")
    )

    pallets_almacen = _resumir_pallets_almacen(
        stock
    )

    if not pallets_almacen.empty:
        resumen = resumen.merge(
            pallets_almacen,
            on="ArticuloCodigo",
            how="left",
        )

    for columna, valor_default in {
        "CantidadPalletsAlmacen": 0,
        "UnidadesPorPalletInferidas": 0,
        "MetodoEstandarizacion": "",
        "AreaAlmacenPrincipal": "",
        "DiasDesdeIngresoStock": np.nan,
        "EsNuevoIngreso": False,
    }.items():
        if columna not in resumen:
            resumen[columna] = valor_default
        resumen[columna] = resumen[columna].fillna(
            valor_default
        )

    return (
        resumen[columnas_resumen],
        detalle_pasillos[columnas_detalle],
    )


def _pasillo_picking_desde_texto(
    ubicacion: pd.Series,
) -> pd.Series:
    return _extraer_pasillo(
        ubicacion
    )


def _bloque_esperado(
    area_picking: str,
    pasillo: float | int | None,
) -> tuple[int | None, int | None, str]:
    bloques = tabla_bloques_pasillos()

    area = str(
        area_picking or ""
    ).strip().upper()

    if bloques.empty or not area:
        return None, None, ""

    coincidencias = bloques.loc[
        bloques["AreaPicking"].eq(area)
    ].copy()

    if coincidencias.empty:
        # Coincidencia flexible.
        coincidencias = bloques.loc[
            bloques["AreaPicking"].apply(
                lambda valor: (
                    valor in area
                    or area in valor
                )
            )
        ].copy()

    if coincidencias.empty:
        return None, None, ""

    if pasillo is not None and pd.notna(pasillo):
        contiene = coincidencias.loc[
            coincidencias["PasilloDesde"].le(int(pasillo))
            & coincidencias["PasilloHasta"].ge(int(pasillo))
        ]
        if not contiene.empty:
            fila = contiene.iloc[0]
            return (
                int(fila["PasilloDesde"]),
                int(fila["PasilloHasta"]),
                str(fila["Bloque"]),
            )

    fila = coincidencias.iloc[0]
    return (
        int(fila["PasilloDesde"]),
        int(fila["PasilloHasta"]),
        str(fila["Bloque"]),
    )


def construir_distribucion_slotting(
    tabla_articulos: pd.DataFrame,
    detalle_pasillos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calcula distribución por SKU y diagnóstico agregado por pasillo.
    """

    columnas_sku = [
        "ArticuloCodigo",
        "PasilloPicking",
        "PasillosStock",
        "PasilloStockPrincipal",
        "CantidadPasillos",
        "DistanciaPromedioPonderada",
        "DistanciaMaxima",
        "StockCercano",
        "StockLejano",
        "StockCercanoPct",
        "StockFueraBloque",
        "StockFueraBloquePct",
        "BloqueEsperado",
        "EstadoDistribucion",
    ]

    columnas_pasillo = [
        "Pasillo",
        "StockTotal",
        "Articulos",
        "ArticulosCalientes",
        "ArticulosFrios",
        "ArticulosSinMovimiento",
        "StockFueraBloque",
        "StockFueraBloquePct",
        "ScorePasillo",
        "EstadoPasillo",
    ]

    if tabla_articulos is None or tabla_articulos.empty:
        return (
            pd.DataFrame(columns=columnas_sku),
            pd.DataFrame(columns=columnas_pasillo),
        )

    base = tabla_articulos[
        [
            "ArticuloCodigo",
            "UbicacionPicking",
            "AreaPicking",
            "CategoriaRotacion",
        ]
    ].copy()

    base["PasilloPicking"] = _pasillo_picking_desde_texto(
        base["UbicacionPicking"]
    )

    if detalle_pasillos is None or detalle_pasillos.empty:
        for columna in columnas_sku:
            if columna not in base:
                base[columna] = np.nan
        return (
            base[columnas_sku],
            pd.DataFrame(columns=columnas_pasillo),
        )

    detalle = detalle_pasillos.copy()
    detalle["PasilloStock"] = pd.to_numeric(
        detalle["PasilloStock"],
        errors="coerce",
    )
    detalle["Cantidad"] = pd.to_numeric(
        detalle["Cantidad"],
        errors="coerce",
    ).fillna(0)

    detalle = detalle.merge(
        base,
        on="ArticuloCodigo",
        how="left",
    )

    detalle["DistanciaPasillos"] = (
        detalle["PasilloStock"]
        - detalle["PasilloPicking"]
    ).abs()

    detalle["EsCercano"] = (
        detalle["DistanciaPasillos"].le(
            RADIO_PASILLOS_CERCANOS
        )
    )

    bloque_info = detalle.apply(
        lambda fila: _bloque_esperado(
            fila.get("AreaPicking", ""),
            fila.get("PasilloPicking"),
        ),
        axis=1,
        result_type="expand",
    )
    bloque_info.columns = [
        "PasilloBloqueDesde",
        "PasilloBloqueHasta",
        "BloqueEsperado",
    ]
    detalle = pd.concat(
        [
            detalle,
            bloque_info,
        ],
        axis=1,
    )

    # Pandas puede conservar estas columnas como string/Arrow
    # después del apply. Se normalizan explícitamente antes de
    # realizar comparaciones numéricas.
    for columna_numerica in [
        "PasilloStock",
        "PasilloPicking",
        "PasilloBloqueDesde",
        "PasilloBloqueHasta",
    ]:
        detalle[columna_numerica] = pd.to_numeric(
            detalle[columna_numerica],
            errors="coerce",
        )

    tiene_bloque = (
        detalle["PasilloStock"].notna()
        & detalle["PasilloBloqueDesde"].notna()
        & detalle["PasilloBloqueHasta"].notna()
    )

    dentro_bloque = (
        detalle["PasilloStock"].ge(
            detalle["PasilloBloqueDesde"]
        )
        & detalle["PasilloStock"].le(
            detalle["PasilloBloqueHasta"]
        )
    )

    detalle["EsFueraBloque"] = (
        tiene_bloque
        & ~dentro_bloque
    )

    detalle["CantidadDistancia"] = (
        detalle["Cantidad"]
        * detalle["DistanciaPasillos"].fillna(0)
    )
    detalle["StockCercano"] = np.where(
        detalle["EsCercano"],
        detalle["Cantidad"],
        0,
    )
    detalle["StockLejano"] = np.where(
        ~detalle["EsCercano"],
        detalle["Cantidad"],
        0,
    )
    detalle["StockFueraBloque"] = np.where(
        detalle["EsFueraBloque"],
        detalle["Cantidad"],
        0,
    )

    resumen = (
        detalle
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            PasilloPicking=(
                "PasilloPicking",
                "first",
            ),
            PasilloStockPrincipal=(
                "PasilloStock",
                lambda serie: (
                    detalle.loc[
                        serie.index
                    ]
                    .sort_values(
                        "Cantidad",
                        ascending=False,
                    )["PasilloStock"]
                    .iloc[0]
                    if len(serie) > 0
                    else np.nan
                ),
            ),
            PasillosStock=(
                "PasilloStock",
                lambda serie: ", ".join(
                    str(int(valor))
                    for valor in sorted(
                        set(
                            pd.to_numeric(
                                serie,
                                errors="coerce",
                            ).dropna()
                        )
                    )
                ),
            ),
            CantidadPasillos=(
                "PasilloStock",
                lambda serie: pd.to_numeric(
                    serie,
                    errors="coerce",
                ).dropna().nunique(),
            ),
            CantidadTotal=(
                "Cantidad",
                "sum",
            ),
            CantidadDistancia=(
                "CantidadDistancia",
                "sum",
            ),
            DistanciaMaxima=(
                "DistanciaPasillos",
                "max",
            ),
            StockCercano=(
                "StockCercano",
                "sum",
            ),
            StockLejano=(
                "StockLejano",
                "sum",
            ),
            StockFueraBloque=(
                "StockFueraBloque",
                "sum",
            ),
            BloqueEsperado=(
                "BloqueEsperado",
                lambda serie: next(
                    (
                        str(valor)
                        for valor in serie
                        if str(valor).strip()
                    ),
                    "",
                ),
            ),
        )
    )

    resumen["DistanciaPromedioPonderada"] = np.where(
        resumen["CantidadTotal"].gt(0),
        resumen["CantidadDistancia"]
        / resumen["CantidadTotal"],
        np.nan,
    )
    resumen["StockCercanoPct"] = np.where(
        resumen["CantidadTotal"].gt(0),
        resumen["StockCercano"]
        / resumen["CantidadTotal"]
        * 100,
        0,
    )
    resumen["StockFueraBloquePct"] = np.where(
        resumen["CantidadTotal"].gt(0),
        resumen["StockFueraBloque"]
        / resumen["CantidadTotal"]
        * 100,
        0,
    )

    resumen["EstadoDistribucion"] = np.select(
        [
            resumen["PasilloPicking"].isna(),
            resumen["CantidadPasillos"].ge(
                UMBRAL_PASILLOS_ALTO
            ),
            resumen["DistanciaPromedioPonderada"].ge(
                DISTANCIA_CRITICA
            ),
            resumen["StockFueraBloquePct"].ge(50),
            resumen["DistanciaPromedioPonderada"].ge(
                DISTANCIA_REVISION
            ),
            resumen["CantidadPasillos"].ge(
                UMBRAL_PASILLOS_NORMAL
            ),
        ],
        [
            "Sin pasillo de picking",
            "Alta dispersión",
            "Stock muy lejano",
            "Mayoría fuera de bloque",
            "Revisar cercanía",
            "Distribución dispersa",
        ],
        default="Distribución correcta",
    )

    resumen = resumen.merge(
        base[
            [
                "ArticuloCodigo",
                "CategoriaRotacion",
            ]
        ],
        on="ArticuloCodigo",
        how="left",
    )

    # Diagnóstico por pasillo físico.
    detalle_pasillo = detalle.merge(
        base[
            [
                "ArticuloCodigo",
                "CategoriaRotacion",
            ]
        ].drop_duplicates(
            "ArticuloCodigo"
        ),
        on="ArticuloCodigo",
        how="left",
        suffixes=("", "_Base"),
    )

    detalle_pasillo["CategoriaFinal"] = (
        detalle_pasillo.get(
            "CategoriaRotacion_Base",
            detalle_pasillo.get(
                "CategoriaRotacion",
                "",
            ),
        )
        .fillna("")
        .astype(str)
    )

    resumen_pasillo = (
        detalle_pasillo.loc[
            detalle_pasillo["PasilloStock"].notna()
        ]
        .groupby(
            "PasilloStock",
            as_index=False,
        )
        .agg(
            StockTotal=(
                "Cantidad",
                "sum",
            ),
            Articulos=(
                "ArticuloCodigo",
                "nunique",
            ),
            ArticulosCalientes=(
                "ArticuloCodigo",
                lambda serie: detalle_pasillo.loc[
                    serie.index
                ].loc[
                    detalle_pasillo.loc[
                        serie.index,
                        "CategoriaFinal",
                    ].eq("🔥 Caliente"),
                    "ArticuloCodigo",
                ].nunique(),
            ),
            ArticulosFrios=(
                "ArticuloCodigo",
                lambda serie: detalle_pasillo.loc[
                    serie.index
                ].loc[
                    detalle_pasillo.loc[
                        serie.index,
                        "CategoriaFinal",
                    ].eq("❄️ Frío"),
                    "ArticuloCodigo",
                ].nunique(),
            ),
            ArticulosSinMovimiento=(
                "ArticuloCodigo",
                lambda serie: detalle_pasillo.loc[
                    serie.index
                ].loc[
                    detalle_pasillo.loc[
                        serie.index,
                        "CategoriaFinal",
                    ].eq("⚫ Sin movimiento"),
                    "ArticuloCodigo",
                ].nunique(),
            ),
            StockFueraBloque=(
                "StockFueraBloque",
                "sum",
            ),
        )
        .rename(
            columns={
                "PasilloStock": "Pasillo",
            }
        )
    )

    resumen_pasillo["StockFueraBloquePct"] = np.where(
        resumen_pasillo["StockTotal"].gt(0),
        resumen_pasillo["StockFueraBloque"]
        / resumen_pasillo["StockTotal"]
        * 100,
        0,
    )

    resumen_pasillo["ScorePasillo"] = (
        resumen_pasillo["StockFueraBloquePct"] * 0.65
        + np.minimum(
            resumen_pasillo["ArticulosSinMovimiento"] * 2,
            20,
        )
        + np.minimum(
            resumen_pasillo["ArticulosFrios"],
            15,
        )
    ).clip(0, 100)

    resumen_pasillo["EstadoPasillo"] = pd.cut(
        resumen_pasillo["ScorePasillo"],
        bins=[
            -0.1,
            29,
            59,
            100,
        ],
        labels=[
            "Correcto",
            "Revisar",
            "Crítico",
        ],
    ).astype(str)

    return (
        resumen[columnas_sku],
        resumen_pasillo[columnas_pasillo],
    )



def calcular_stock_picking_configurado(
    base_articulos: pd.DataFrame,
    detalle_stock: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calcula el stock real existente en las ubicaciones de picking
    configuradas para cada artículo.

    No depende del prefijo de la ubicación. Una ubicación IMP, NAC,
    BCH, SAN o PCK se considera picking cuando está declarada como
    UbicacionPicking para ese mismo SKU.
    """
    columnas_salida = [
        "ArticuloCodigo",
        "StockPickingConfigurado",
        "UbicacionesPickingConStock",
    ]

    if (
        base_articulos is None
        or base_articulos.empty
        or detalle_stock is None
        or detalle_stock.empty
        or "UbicacionPicking" not in base_articulos.columns
    ):
        return pd.DataFrame(columns=columnas_salida)

    configuraciones = []

    for fila in base_articulos[
        [
            "ArticuloCodigo",
            "UbicacionPicking",
        ]
    ].itertuples(index=False):
        codigo = str(
            fila.ArticuloCodigo or ""
        ).strip().upper()

        ubicaciones = str(
            fila.UbicacionPicking or ""
        ).split("|")

        for ubicacion in ubicaciones:
            clave = _normalizar_ubicacion_slotting(
                ubicacion
            )

            if codigo and clave:
                configuraciones.append(
                    {
                        "ArticuloCodigo": codigo,
                        "ClaveUbicacionPicking": clave,
                    }
                )

    if not configuraciones:
        return pd.DataFrame(columns=columnas_salida)

    tabla_config = (
        pd.DataFrame(configuraciones)
        .drop_duplicates(
            [
                "ArticuloCodigo",
                "ClaveUbicacionPicking",
            ]
        )
    )

    stock = detalle_stock.copy()
    stock["ArticuloCodigo"] = _codigo(
        stock["ArticuloCodigo"]
    )
    stock["ClaveUbicacionPicking"] = (
        stock["Ubicacion"]
        .fillna("")
        .astype(str)
        .apply(
            _normalizar_ubicacion_slotting
        )
    )
    stock["Cantidad"] = pd.to_numeric(
        stock["Cantidad"],
        errors="coerce",
    ).fillna(0)

    coincidencias = stock.merge(
        tabla_config,
        on=[
            "ArticuloCodigo",
            "ClaveUbicacionPicking",
        ],
        how="inner",
        validate="many_to_one",
    )

    if coincidencias.empty:
        return pd.DataFrame(columns=columnas_salida)

    resumen = (
        coincidencias
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            StockPickingConfigurado=(
                "Cantidad",
                "sum",
            ),
            UbicacionesPickingConStock=(
                "ClaveUbicacionPicking",
                lambda serie: " | ".join(
                    sorted(
                        set(
                            str(valor)
                            for valor in serie
                            if str(valor).strip()
                        )
                    )
                ),
            ),
        )
    )

    return resumen[columnas_salida]



def resumir_historico_slotting(
    historico_ventas: pd.DataFrame,
    meses_analisis: int,
) -> tuple[pd.DataFrame, dict]:
    columnas = [
        "ArticuloCodigo",
        "UnidadesPeriodo",
        "VentaPromedioMensual",
        "VentaPromedioDiaria",
        "DiasConMovimiento",
        "MesesConMovimiento",
        "UltimaVenta",
        "DiasSinVenta",
    ]

    if historico_ventas is None or historico_ventas.empty:
        return (
            pd.DataFrame(
                columns=columnas
            ),
            {
                "fecha_desde": pd.NaT,
                "fecha_hasta": pd.NaT,
                "dias_periodo": 0,
            },
        )

    historico = historico_ventas.copy()
    historico["ArticuloCodigo"] = _codigo(
        _serie(
            historico,
            [
                "ArticuloCodigo",
                "CodigoArticulo",
            ],
            "",
        )
    )
    historico["Fecha"] = pd.to_datetime(
        _serie(
            historico,
            [
                "Fecha",
                "FechaInicio",
            ],
            pd.NaT,
        ),
        errors="coerce",
    ).dt.normalize()
    historico["UnidadesVendidas"] = _numero(
        _serie(
            historico,
            [
                "UnidadesVendidas",
                "UnidadesDetalle",
                "Cantidad",
            ],
            0,
        )
    )

    historico = historico.loc[
        historico["ArticuloCodigo"].ne("")
        & historico["Fecha"].notna()
        & historico["UnidadesVendidas"].gt(0)
    ].copy()

    if historico.empty:
        return (
            pd.DataFrame(
                columns=columnas
            ),
            {
                "fecha_desde": pd.NaT,
                "fecha_hasta": pd.NaT,
                "dias_periodo": 0,
            },
        )

    fecha_hasta = historico["Fecha"].max()
    meses = max(
        int(meses_analisis),
        1,
    )
    fecha_desde = (
        fecha_hasta.to_period("M")
        - (meses - 1)
    ).start_time

    periodo = historico.loc[
        historico["Fecha"].between(
            fecha_desde,
            fecha_hasta,
            inclusive="both",
        )
    ].copy()

    dias_periodo = max(
        int(
            (
                fecha_hasta
                - fecha_desde
            ).days
        )
        + 1,
        1,
    )

    periodo["Mes"] = periodo[
        "Fecha"
    ].dt.to_period("M")

    resumen = (
        periodo
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            UnidadesPeriodo=(
                "UnidadesVendidas",
                "sum",
            ),
            DiasConMovimiento=(
                "Fecha",
                "nunique",
            ),
            MesesConMovimiento=(
                "Mes",
                "nunique",
            ),
            UltimaVenta=(
                "Fecha",
                "max",
            ),
        )
    )

    resumen["VentaPromedioMensual"] = (
        resumen["UnidadesPeriodo"]
        / meses
    )
    resumen["VentaPromedioDiaria"] = (
        resumen["UnidadesPeriodo"]
        / dias_periodo
    )
    resumen["DiasSinVenta"] = (
        fecha_hasta
        - resumen["UltimaVenta"]
    ).dt.days

    return (
        resumen[columnas],
        {
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "dias_periodo": dias_periodo,
        },
    )


def _clasificar_abc(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    resultado = tabla.copy()
    resultado["CategoriaRotacion"] = (
        "⚫ Sin movimiento"
    )
    resultado["ParticipacionVentaPct"] = 0.0
    resultado["ParticipacionAcumuladaPct"] = 0.0

    con_venta = resultado.loc[
        resultado[
            "UnidadesPeriodo"
        ].gt(0)
    ].copy()

    if con_venta.empty:
        return resultado

    con_venta = con_venta.sort_values(
        [
            "UnidadesPeriodo",
            "DiasConMovimiento",
        ],
        ascending=[
            False,
            False,
        ],
    )

    total = float(
        con_venta[
            "UnidadesPeriodo"
        ].sum()
    )

    con_venta[
        "ParticipacionVentaPct"
    ] = (
        con_venta["UnidadesPeriodo"]
        / total
        * 100
        if total > 0
        else 0
    )
    con_venta[
        "ParticipacionAcumuladaPct"
    ] = con_venta[
        "ParticipacionVentaPct"
    ].cumsum()

    # El artículo que atraviesa el umbral permanece dentro
    # de la categoría que ayudó a completar.
    acumulada_anterior = (
        con_venta[
            "ParticipacionAcumuladaPct"
        ]
        - con_venta[
            "ParticipacionVentaPct"
        ]
    )

    con_venta[
        "CategoriaRotacion"
    ] = np.select(
        [
            acumulada_anterior.lt(80),
            acumulada_anterior.lt(95),
        ],
        [
            "🔥 Caliente",
            "🟡 Intermedio",
        ],
        default="❄️ Frío",
    )

    resultado = resultado.drop(
        columns=[
            "ParticipacionVentaPct",
            "ParticipacionAcumuladaPct",
            "CategoriaRotacion",
        ]
    ).merge(
        con_venta[
            [
                "ArticuloCodigo",
                "ParticipacionVentaPct",
                "ParticipacionAcumuladaPct",
                "CategoriaRotacion",
            ]
        ],
        on="ArticuloCodigo",
        how="left",
    )

    resultado[
        "ParticipacionVentaPct"
    ] = resultado[
        "ParticipacionVentaPct"
    ].fillna(0)
    resultado[
        "ParticipacionAcumuladaPct"
    ] = resultado[
        "ParticipacionAcumuladaPct"
    ].fillna(0)
    resultado[
        "CategoriaRotacion"
    ] = resultado[
        "CategoriaRotacion"
    ].fillna(
        "⚫ Sin movimiento"
    )

    return resultado


def _metodo_reposicion(
    fila: pd.Series,
) -> str:
    unidades_pallet = float(
        fila.get(
            "UnidadesPorPallet",
            0,
        )
        or 0
    )
    maximo = float(
        fila.get(
            "StockMaximoActual",
            0,
        )
        or 0
    )

    if unidades_pallet <= 0 or maximo <= 0:
        return "Sin determinar"

    pallets = maximo / unidades_pallet
    cercano_entero = abs(
        pallets
        - round(pallets)
    ) <= 0.12

    if pallets >= 0.8 and cercano_entero:
        return "Reposición por pallet"

    return "Reposición por quiebre"


def _accion_y_motivo(
    fila: pd.Series,
) -> tuple[str, str, float]:
    categoria = str(
        fila.get(
            "CategoriaRotacion",
            "",
        )
    )
    tiene_picking = bool(
        fila.get(
            "TienePicking",
            False,
        )
    )
    actual = float(
        fila.get(
            "StockMaximoActual",
            0,
        )
        or 0
    )
    sugerido = float(
        fila.get(
            "StockMaximoSugerido",
            0,
        )
        or 0
    )
    minimo = float(
        fila.get(
            "StockMinimoActual",
            0,
        )
        or 0
    )
    stock = float(
        fila.get(
            "StockFisico",
            0,
        )
        or 0
    )
    dias_sin_venta = float(
        fila.get(
            "DiasSinVenta",
            9999,
        )
        if pd.notna(
            fila.get(
                "DiasSinVenta",
                np.nan,
            )
        )
        else 9999
    )
    presion = float(
        fila.get(
            "PresionPickingPct",
            0,
        )
        if pd.notna(
            fila.get(
                "PresionPickingPct",
                np.nan,
            )
        )
        else 0
    )

    if minimo > actual and actual >= 0:
        return (
            "Revisar configuración",
            "El mínimo configurado es mayor que el máximo.",
            95,
        )

    if actual <= 0 and minimo > 0:
        return (
            "Revisar configuración",
            "Tiene mínimo configurado pero el máximo es cero.",
            92,
        )

    if categoria == "🆕 Nuevo ingreso":
        dias_ingreso = fila.get(
            "DiasDesdeIngresoStock",
            np.nan,
        )
        texto_dias = (
            f"Hace aproximadamente {int(dias_ingreso)} días."
            if pd.notna(dias_ingreso)
            else "Ingreso reciente detectado."
        )
        return (
            "Monitorear nuevo ingreso",
            (
                "Producto sin ventas históricas, pero con ingreso "
                f"reciente al stock. {texto_dias}"
            ),
            30,
        )

    if categoria == "⚫ Sin movimiento":
        if tiene_picking:
            return (
                "Evaluar discontinuos",
                (
                    f"Sin movimientos en el período y mantiene "
                    f"{actual:,.0f} unidades de máximo en picking."
                ),
                88,
            )

        if stock > 0:
            return (
                "Avisar Comercial",
                (
                    f"Tiene {stock:,.0f} unidades físicas y no registró "
                    "movimiento en el período."
                ),
                82,
            )

        return (
            "Configuración correcta",
            "Sin movimiento y sin capacidad relevante asignada.",
            20,
        )

    if not tiene_picking and categoria in {
        "🔥 Caliente",
        "🟡 Intermedio",
    }:
        return (
            "Crear picking",
            (
                f"Producto {categoria.split()[-1].lower()} con "
                f"{fila.get('VentaPromedioMensual', 0):,.1f} unidades/mes "
                "y sin ubicación de picking configurada."
            ),
            98 if categoria == "🔥 Caliente" else 82,
        )

    if sugerido > 0 and actual < sugerido * 0.80:
        return (
            "Aumentar capacidad",
            (
                f"El máximo actual ({actual:,.0f}) cubre menos del "
                f"80% del objetivo sugerido ({sugerido:,.0f})."
            ),
            min(
                100,
                65 + max(
                    presion - 100,
                    0,
                ) * 0.18,
            ),
        )

    if (
        categoria in {
            "❄️ Frío",
            "🟡 Intermedio",
        }
        and sugerido >= 0
        and actual > max(
            sugerido * 1.80,
            sugerido + 10,
        )
    ):
        return (
            "Reducir capacidad",
            (
                f"El máximo actual ({actual:,.0f}) supera ampliamente "
                f"el objetivo estimado ({sugerido:,.0f})."
            ),
            72 if categoria == "❄️ Frío" else 58,
        )

    if (
        dias_sin_venta >= 90
        and stock > 0
    ):
        return (
            "Avisar Comercial",
            (
                f"Registra {dias_sin_venta:,.0f} días sin movimiento "
                f"y conserva {stock:,.0f} unidades físicas."
            ),
            78,
        )

    return (
        "Configuración correcta",
        "La capacidad actual se encuentra dentro del rango inicial esperado.",
        25,
    )


def construir_diagnostico_slotting(
    tabla_articulos: pd.DataFrame,
    tabla_volumetria: pd.DataFrame,
    tabla_max_min: pd.DataFrame,
    tabla_stock_detallado: pd.DataFrame,
    tabla_maestro_ubicaciones: pd.DataFrame,
    historico_ventas: pd.DataFrame,
    meses_analisis: int = 6,
    dias_caliente: int = 15,
    dias_intermedio: int = 10,
    dias_frio: int = 5,
) -> tuple[pd.DataFrame, dict]:
    """
    Construye la V1 del diagnóstico de slotting.

    Las recomendaciones son analíticas y deben validarse contra
    capacidad física, políticas del WMS y criterios operativos.
    """

    maestro = preparar_maestro_articulos_slotting(
        tabla_articulos
    )
    max_min = preparar_max_min_slotting(
        tabla_max_min
    )
    volumetria = preparar_volumetria_slotting(
        tabla_volumetria
    )
    stock, detalle_pasillos = preparar_stock_slotting(
        tabla_stock_detallado
    )
    maestro_ubicaciones = (
        preparar_maestro_ubicaciones_slotting(
            tabla_maestro_ubicaciones
        )
    )
    ventas, metadata = resumir_historico_slotting(
        historico_ventas,
        meses_analisis,
    )

    codigos = set()

    for tabla in [
        maestro,
        max_min,
        volumetria,
        stock,
        ventas,
    ]:
        if (
            tabla is not None
            and not tabla.empty
            and "ArticuloCodigo"
            in tabla.columns
        ):
            codigos.update(
                tabla[
                    "ArticuloCodigo"
                ]
                .dropna()
                .astype(str)
                .loc[
                    lambda serie:
                    serie.str.strip().ne("")
                ]
                .tolist()
            )

    base = pd.DataFrame(
        {
            "ArticuloCodigo": sorted(
                codigos
            )
        }
    )

    for tabla in [
        maestro,
        max_min,
        volumetria,
        stock,
        ventas,
    ]:
        if (
            tabla is not None
            and not tabla.empty
        ):
            base = base.merge(
                tabla,
                on="ArticuloCodigo",
                how="left",
            )

    columnas_texto = [
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Origen",
        "ArticuloConfigurado",
        "AreaPicking",
        "UbicacionPicking",
        "UbicacionesPickingConStock",
        "MetodoEstandarizacion",
        "AreaAlmacenPrincipal",
    ]

    for columna in columnas_texto:
        if columna not in base:
            base[columna] = ""
        base[columna] = (
            base[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    base["ArticuloDescripcion"] = (
        base["ArticuloDescripcion"]
        .where(
            base[
                "ArticuloDescripcion"
            ].ne(""),
            base["ArticuloConfigurado"],
        )
    )


    # Stock real del picking según la ubicación configurada para
    # cada artículo. Esto reconoce ubicaciones IMP, NAC, BCH, SAN,
    # PCK u otros prefijos sin depender del nombre del área.
    stock_picking_configurado = (
        calcular_stock_picking_configurado(
            base,
            detalle_pasillos,
        )
    )

    if not stock_picking_configurado.empty:
        base = base.merge(
            stock_picking_configurado,
            on="ArticuloCodigo",
            how="left",
            validate="one_to_one",
        )
    else:
        base["StockPickingConfigurado"] = np.nan
        base["UbicacionesPickingConStock"] = ""


    if not maestro_ubicaciones.empty:
        mapa_area = dict(
            zip(
                maestro_ubicaciones["UbicacionMaestro"],
                maestro_ubicaciones["AreaMaestro"],
            )
        )

        def resolver_area_ubicaciones(
            ubicaciones: str,
        ) -> str:
            areas = []
            for ubicacion in str(
                ubicaciones or ""
            ).split("|"):
                clave = _normalizar_ubicacion_slotting(
                    ubicacion
                )
                area = str(
                    mapa_area.get(clave, "")
                ).strip()
                if area and area not in areas:
                    areas.append(area)
            return " | ".join(areas)

        area_desde_maestro = (
            base["UbicacionPicking"]
            .apply(resolver_area_ubicaciones)
        )

        base["AreaPicking"] = (
            area_desde_maestro.where(
                area_desde_maestro.ne(""),
                base["AreaPicking"],
            )
        )

    columnas_numericas = [
        "StockPickingActual",
        "StockMinimoActual",
        "StockMaximoActual",
        "StockMaximoPreparar",
        "UnidadesPorPallet",
        "StockFisico",
        "StockPickingDetectado",
        "StockAlmacenDetectado",
        "CantidadUbicaciones",
        "CantidadPasillos",
        "UnidadesPeriodo",
        "VentaPromedioMensual",
        "VentaPromedioDiaria",
        "DiasConMovimiento",
        "MesesConMovimiento",
        "DiasSinVenta",
    ]

    for columna in columnas_numericas:
        if columna not in base:
            base[columna] = 0
        base[columna] = pd.to_numeric(
            base[columna],
            errors="coerce",
        ).fillna(0)

    base["UltimaVenta"] = pd.to_datetime(
        base.get(
            "UltimaVenta",
            pd.NaT,
        ),
        errors="coerce",
    )
    base["FechaPrimerIngresoStock"] = pd.to_datetime(
        base.get(
            "FechaPrimerIngresoStock",
            pd.NaT,
        ),
        errors="coerce",
    )
    if "EsNuevoIngreso" not in base.columns:
        base["EsNuevoIngreso"] = pd.Series(
            False,
            index=base.index,
            dtype="bool",
        )
    else:
        base["EsNuevoIngreso"] = (
            base["EsNuevoIngreso"]
            .fillna(False)
            .astype(bool)
        )

    # El diagnóstico de Slotting analiza únicamente artículos
    # que actualmente tienen existencia física en el depósito.
    #
    # Se excluyen códigos presentes solo en maestros, históricos
    # o configuraciones de Max & Min sin stock real.
    base = base.loc[
        base["StockFisico"].gt(0)
    ].copy()

    if base.empty:
        metadata = {
            **metadata,
            "meses_analisis": int(meses_analisis),
            "articulos": 0,
        }
        return base.reset_index(drop=True), metadata

    base = _clasificar_abc(
        base
    )

    nuevo_sin_venta = (
        base["CategoriaRotacion"].eq("⚫ Sin movimiento")
        & base["EsNuevoIngreso"]
        & base["StockFisico"].gt(0)
    )
    base.loc[
        nuevo_sin_venta,
        "CategoriaRotacion",
    ] = "🆕 Nuevo ingreso"

    dias_objetivo = {
        "🔥 Caliente": max(
            int(dias_caliente),
            1,
        ),
        "🟡 Intermedio": max(
            int(dias_intermedio),
            1,
        ),
        "❄️ Frío": max(
            int(dias_frio),
            1,
        ),
        "🆕 Nuevo ingreso": 0,
        "⚫ Sin movimiento": 0,
    }

    base["DiasObjetivoPicking"] = (
        base[
            "CategoriaRotacion"
        ].map(
            dias_objetivo
        ).fillna(0)
    )

    # Si el artículo tiene ubicaciones de picking configuradas,
    # el stock actual se toma directamente del stock detallado.
    # Cuando la ubicación existe pero está vacía, el valor correcto
    # es cero. Solo se usa Max & Min como respaldo si no existe una
    # configuración de ubicación.
    tiene_ubicacion_picking = (
        base["UbicacionPicking"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    base["StockPickingActualReporte"] = (
        base["StockPickingActual"]
    )

    base["StockPickingActual"] = np.where(
        tiene_ubicacion_picking,
        base["StockPickingConfigurado"].fillna(0),
        base["StockPickingActualReporte"],
    )

    base["StockPickingDetectado"] = np.where(
        tiene_ubicacion_picking,
        base["StockPickingConfigurado"].fillna(0),
        base["StockPickingDetectado"],
    )

    base["UnidadesPorPalletVolumetria"] = (
        base["UnidadesPorPallet"]
    )

    usar_estandar_inferido = (
        base["UnidadesPorPalletInferidas"].gt(0)
    )

    base["UnidadesPorPallet"] = (
        base["UnidadesPorPalletInferidas"].where(
            usar_estandar_inferido,
            base["UnidadesPorPalletVolumetria"],
        )
    )

    base["FuenteEstandarizacion"] = np.where(
        usar_estandar_inferido,
        "Stock de almacén",
        np.where(
            base["UnidadesPorPalletVolumetria"].gt(0),
            "Maestro de volumetría",
            "Sin estandarización",
        ),
    )

    base["TienePicking"] = (
        base["UbicacionPicking"].ne("")
        | base["AreaPicking"].ne("")
        | base["StockMaximoActual"].gt(0)
        | base["StockMinimoActual"].gt(0)
    )

    demanda_objetivo = (
        base["VentaPromedioDiaria"]
        * base["DiasObjetivoPicking"]
    )

    base["StockMaximoSugeridoBase"] = (
        np.ceil(
            demanda_objetivo
        )
    )

    # Para productos calientes configurados por pallet, el máximo
    # sugerido se redondea a pallets completos.
    usar_pallet = (
        base["CategoriaRotacion"].eq(
            "🔥 Caliente"
        )
        & base[
            "UnidadesPorPallet"
        ].gt(0)
    )

    base["StockMaximoSugerido"] = (
        base[
            "StockMaximoSugeridoBase"
        ]
    )

    base.loc[
        usar_pallet,
        "StockMaximoSugerido",
    ] = (
        np.ceil(
            base.loc[
                usar_pallet,
                "StockMaximoSugeridoBase",
            ]
            / base.loc[
                usar_pallet,
                "UnidadesPorPallet",
            ]
        )
        * base.loc[
            usar_pallet,
            "UnidadesPorPallet",
        ]
    )

    base["StockMinimoSugerido"] = np.where(
        base["StockMaximoSugerido"].gt(0),
        np.ceil(
            base[
                "StockMaximoSugerido"
            ]
            * 0.30
        ),
        0,
    )

    base["CoberturaPickingDias"] = np.where(
        base[
            "VentaPromedioDiaria"
        ].gt(0),
        base[
            "StockMaximoActual"
        ]
        / base[
            "VentaPromedioDiaria"
        ],
        np.nan,
    )

    base["PresionPickingPct"] = np.where(
        base[
            "StockMaximoActual"
        ].gt(0),
        demanda_objetivo
        / base[
            "StockMaximoActual"
        ]
        * 100,
        np.where(
            demanda_objetivo.gt(0),
            999,
            0,
        ),
    )

    base["PalletsActuales"] = (
        pd.to_numeric(
            base["CantidadPalletsAlmacen"],
            errors="coerce",
        )
        .fillna(0)
    )
    base["PalletsSugeridos"] = np.where(
        base[
            "UnidadesPorPallet"
        ].gt(0),
        base[
            "StockMaximoSugerido"
        ]
        / base[
            "UnidadesPorPallet"
        ],
        np.nan,
    )

    base["MetodoReposicionInferido"] = (
        base.apply(
            _metodo_reposicion,
            axis=1,
        )
    )

    distribucion_sku, resumen_pasillos = (
        construir_distribucion_slotting(
            base,
            detalle_pasillos,
        )
    )

    if not distribucion_sku.empty:
        base = base.merge(
            distribucion_sku,
            on="ArticuloCodigo",
            how="left",
            suffixes=("", "_Distribucion"),
        )

        for columna in [
            "PasilloPicking",
            "PasillosStock",
            "PasilloStockPrincipal",
            "CantidadPasillos",
            "DistanciaPromedioPonderada",
            "DistanciaMaxima",
            "StockCercano",
            "StockLejano",
            "StockCercanoPct",
            "StockFueraBloque",
            "StockFueraBloquePct",
            "BloqueEsperado",
            "EstadoDistribucion",
        ]:
            columna_dist = f"{columna}_Distribucion"
            if columna_dist in base.columns:
                if columna in base.columns:
                    base[columna] = base[columna_dist].where(
                        base[columna_dist].notna(),
                        base[columna],
                    )
                else:
                    base[columna] = base[columna_dist]
                base.drop(
                    columns=[columna_dist],
                    inplace=True,
                )

    decisiones = base.apply(
        _accion_y_motivo,
        axis=1,
        result_type="expand",
    )
    decisiones.columns = [
        "AccionSugerida",
        "Motivo",
        "ScoreBase",
    ]

    base = pd.concat(
        [
            base,
            decisiones,
        ],
        axis=1,
    )

    # Bonificaciones explicables para ordenar prioridades.
    bonus_rotacion = base[
        "CategoriaRotacion"
    ].map(
        {
            "🔥 Caliente": 12,
            "🟡 Intermedio": 7,
            "❄️ Frío": 3,
            "🆕 Nuevo ingreso": 2,
            "⚫ Sin movimiento": 8,
        }
    ).fillna(0)

    bonus_stock = np.select(
        [
            base["StockFisico"].ge(1000),
            base["StockFisico"].ge(250),
            base["StockFisico"].gt(0),
        ],
        [
            8,
            5,
            2,
        ],
        default=0,
    )

    bonus_distribucion = np.select(
        [
            base.get(
                "DistanciaPromedioPonderada",
                pd.Series(0, index=base.index),
            ).ge(DISTANCIA_CRITICA),
            base.get(
                "DistanciaPromedioPonderada",
                pd.Series(0, index=base.index),
            ).ge(DISTANCIA_REVISION),
            base.get(
                "CantidadPasillos",
                pd.Series(0, index=base.index),
            ).ge(UMBRAL_PASILLOS_ALTO),
            base.get(
                "StockFueraBloquePct",
                pd.Series(0, index=base.index),
            ).ge(30),
        ],
        [
            18,
            10,
            8,
            6,
        ],
        default=0,
    )

    base["ScoreSlotting"] = (
        base["ScoreBase"]
        + bonus_rotacion
        + bonus_stock
        + bonus_distribucion
    ).clip(
        lower=0,
        upper=100,
    )

    base["NivelPrioridad"] = pd.cut(
        base["ScoreSlotting"],
        bins=[
            -0.1,
            39,
            59,
            79,
            100,
        ],
        labels=[
            "Control",
            "Media",
            "Alta",
            "Crítica",
        ],
    ).astype(str)

    base["DiferenciaMaximo"] = (
        base["StockMaximoSugerido"]
        - base["StockMaximoActual"]
    )

    base["ConfiguracionValida"] = (
        base["StockMinimoActual"].le(
            base["StockMaximoActual"]
        )
        & ~(
            base["StockMinimoActual"].gt(0)
            & base["StockMaximoActual"].le(0)
        )
    )

    base = base.sort_values(
        [
            "ScoreSlotting",
            "UnidadesPeriodo",
            "ArticuloCodigo",
        ],
        ascending=[
            False,
            False,
            True,
        ],
    ).reset_index(drop=True)

    metadata = {
        **metadata,
        "meses_analisis": int(
            meses_analisis
        ),
        "dias_objetivo": dias_objetivo,
        "articulos": int(
            base[
                "ArticuloCodigo"
            ].nunique()
        ),
        "resumen_pasillos": resumen_pasillos,
        "detalle_pasillos": detalle_pasillos,
        "bloques_pasillos": tabla_bloques_pasillos(),
    }

    return base, metadata
