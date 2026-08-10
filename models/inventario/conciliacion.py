from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from utils.inventario.normalizacion import (
    buscar_columna,
    convertir_numero,
    normalizar_codigo,
    primer_texto_no_vacio,
)


COLUMNAS_ESTADO_WMS = [
    "Recepcion",
    "Bloqueados",
    "Pedidas",
    "Reservado",
    "Disponible",
    "Transito",
    "Preparacion",
    "Despacho",
    "Vencidas",
    "Scrap",
    "Inconsistencia",
]

# Estados que representan existencia física dentro del WMS.
# Pedidas es demanda, no existencia.
# Tránsito todavía no ingresó físicamente al depósito.
ESTADOS_FISICOS_WMS = [
    "Disponible",
    "Bloqueados",
    "Recepcion",
]


PREFIJOS_INSUMOS = ("A", "S", "F", "R", "U")


def clasificar_grupo_inventario(codigo: object) -> str:
    """Clasifica el código como Insumos o Producto terminado."""

    codigo_normalizado = str(codigo or "").strip().upper()

    if codigo_normalizado.startswith(PREFIJOS_INSUMOS):
        return "Insumos"

    return "Producto terminado"


@dataclass(frozen=True)
class ConfiguracionComparacion:
    columnas_stock_erp: tuple[str, ...] = (
        "est_1",
        "est_8",
    )
    incluir_erp_sanitarios: bool = True
    columnas_stock_erp_sanitarios: tuple[str, ...] = (
        "est_1",
        "est_8",
    )
    incluir_estados_wms: tuple[str, ...] = tuple(
        ESTADOS_FISICOS_WMS
    )

    def como_dict(self) -> dict[str, Any]:
        return asdict(self)



def preparar_erp(
    dataframe: pd.DataFrame,
    *,
    columnas_stock: list[str] | tuple[str, ...],
    prefijo_desglose: str = "ERP",
) -> pd.DataFrame:
    """Suma las columnas ERP seleccionadas y conserva su desglose."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    codigo = buscar_columna(
        dataframe,
        [
            "cod_art",
            "CodigoArticulo",
            "ArticuloCodigo",
            "Codigo",
        ],
        obligatoria=True,
    )

    descripcion = buscar_columna(
        dataframe,
        [
            "des_art",
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "Descripcion",
        ],
    )

    columnas_validas = []

    for columna in columnas_stock:
        if columna in dataframe.columns:
            columnas_validas.append(columna)
        else:
            detectada = buscar_columna(
                dataframe,
                [columna],
            )
            if detectada:
                columnas_validas.append(detectada)

    if not columnas_validas:
        raise ValueError(
            "No se encontró ninguna columna ERP seleccionada: "
            + ", ".join(columnas_stock)
        )

    salida = pd.DataFrame({
        "ArticuloCodigo": normalizar_codigo(
            dataframe[codigo]
        ),
        "DescripcionERP": (
            dataframe[descripcion]
            .fillna("")
            .astype(str)
            .str.strip()
            if descripcion
            else ""
        ),
    })

    columnas_desglose = []

    for columna in columnas_validas:
        nombre = f"{prefijo_desglose}_{str(columna).strip()}"
        salida[nombre] = convertir_numero(
            dataframe[columna]
        )
        columnas_desglose.append(nombre)

    salida["StockERP"] = (
        salida[columnas_desglose].sum(axis=1)
    )

    columnas_extra = {
        "StockFisicoERPInformativo": "stk_fis",
        "StockComprometidoERP": "stk_com",
        "StockReservadoERP": "stk_res",
        "StockPendienteERP": "stk_pen",
        "StockDisponibleERP": "stk_dis",
        "EstadoAprobadoERP": "est_1",
        "EstadoTransitoERP": "est_8",
    }

    for destino, origen in columnas_extra.items():
        salida[destino] = (
            convertir_numero(dataframe[origen])
            if origen in dataframe.columns
            else 0.0
        )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    agregaciones = {
        "DescripcionERP": (
            "DescripcionERP",
            primer_texto_no_vacio,
        ),
        "StockERP": ("StockERP", "sum"),
        "StockFisicoERPInformativo": (
            "StockFisicoERPInformativo",
            "sum",
        ),
        "StockComprometidoERP": (
            "StockComprometidoERP",
            "sum",
        ),
        "StockReservadoERP": (
            "StockReservadoERP",
            "sum",
        ),
        "StockPendienteERP": (
            "StockPendienteERP",
            "sum",
        ),
        "StockDisponibleERP": (
            "StockDisponibleERP",
            "sum",
        ),
        "EstadoAprobadoERP": (
            "EstadoAprobadoERP",
            "sum",
        ),
        "EstadoTransitoERP": (
            "EstadoTransitoERP",
            "sum",
        ),
    }

    for columna in columnas_desglose:
        agregaciones[columna] = (
            columna,
            "sum",
        )

    return (
        salida
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(**agregaciones)
    )


def _preparar_lineas_detalle(
    dataframe: pd.DataFrame,
    *,
    nombre_fuente: str,
) -> pd.DataFrame:
    """
    Normaliza un reporte físico por ubicación sin agregarlo.

    La clave de deduplicación conserva artículo, ubicación,
    contenedor y cantidad. Esto evita duplicar una misma línea
    cuando dos fuentes contienen el mismo registro físico.
    """

    columnas_salida = [
        "ArticuloCodigo",
        "ArticuloDescripcionWMS",
        "Cantidad",
        "Area",
        "Ubicacion",
        "Contenedor",
        "EstadoWMS",
        "FuenteDetalle",
    ]

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=columnas_salida)

    codigo = buscar_columna(
        dataframe,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "Articulo",
            "Codigo",
        ],
        obligatoria=True,
    )
    cantidad = buscar_columna(
        dataframe,
        [
            "Cantidad",
            "Unidades",
            "Stock",
        ],
        obligatoria=True,
    )
    descripcion = buscar_columna(
        dataframe,
        [
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "Descripcion",
        ],
    )
    area = buscar_columna(
        dataframe,
        [
            "AreaDescripcion",
            "Area",
        ],
    )
    ubicacion = buscar_columna(
        dataframe,
        [
            "Ubicacion",
            "Ubicación",
        ],
    )
    contenedor = buscar_columna(
        dataframe,
        [
            "ContenedorNumero",
            "Contenedor",
        ],
    )
    estado = buscar_columna(
        dataframe,
        [
            "EstadoDescripcion",
            "Estado",
        ],
    )

    salida = pd.DataFrame({
        "ArticuloCodigo": normalizar_codigo(
            dataframe[codigo]
        ),
        "ArticuloDescripcionWMS": (
            dataframe[descripcion]
            .fillna("")
            .astype(str)
            .str.strip()
            if descripcion
            else ""
        ),
        "Cantidad": convertir_numero(
            dataframe[cantidad]
        ),
        "Area": (
            dataframe[area]
            .fillna("")
            .astype(str)
            .str.strip()
            if area
            else ""
        ),
        "Ubicacion": (
            dataframe[ubicacion]
            .fillna("")
            .astype(str)
            .str.strip()
            if ubicacion
            else ""
        ),
        "Contenedor": (
            dataframe[contenedor]
            .fillna("")
            .astype(str)
            .str.strip()
            if contenedor
            else ""
        ),
        "EstadoWMS": (
            dataframe[estado]
            .fillna("")
            .astype(str)
            .str.strip()
            if estado
            else ""
        ),
        "FuenteDetalle": nombre_fuente,
    })

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    # Quitar filas completamente vacías o sin unidades.
    salida = salida.loc[
        salida["Cantidad"].ne(0)
        | salida["Ubicacion"].ne("")
        | salida["Contenedor"].ne("")
    ].copy()

    return salida.reset_index(drop=True)


def _resumir_detalle(
    detalle: pd.DataFrame,
    *,
    nombre_stock: str,
) -> pd.DataFrame:
    if detalle is None or detalle.empty:
        return pd.DataFrame(columns=[
            "ArticuloCodigo",
            "DescripcionWMSDetalle",
            nombre_stock,
            "CantidadUbicaciones",
            "CantidadContenedores",
            "CantidadLineasFisicas",
        ])

    return (
        detalle
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            DescripcionWMSDetalle=(
                "ArticuloDescripcionWMS",
                primer_texto_no_vacio,
            ),
            **{
                nombre_stock: ("Cantidad", "sum"),
            },
            CantidadUbicaciones=(
                "Ubicacion",
                lambda serie: int(
                    serie.loc[
                        serie.astype(str).str.strip().ne("")
                    ].nunique()
                ),
            ),
            CantidadContenedores=(
                "Contenedor",
                lambda serie: int(
                    serie.loc[
                        serie.astype(str).str.strip().ne("")
                    ].nunique()
                ),
            ),
            CantidadLineasFisicas=(
                "ArticuloCodigo",
                "size",
            ),
        )
    )


def preparar_detalle_comparable_wms(
    df_stock_digip: pd.DataFrame,
    df_recepcion: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Construye el detalle comparable contra Disponible DIGIP.

    Fuentes:
    - Stock DIGIP: detalle del stock disponible/bloqueado.
    - Stock Recepción: detalle físico todavía ubicado en recepción.

    No utiliza `stock_detallado` porque ese reporte puede pertenecer
    a otra captura, filtro o momento y generaría falsas diferencias.
    """

    stock = _preparar_lineas_detalle(
        df_stock_digip,
        nombre_fuente="Stock DIGIP",
    )
    recepcion = _preparar_lineas_detalle(
        df_recepcion,
        nombre_fuente="Stock Recepción",
    )

    # Evitar doble conteo: si Stock DIGIP ya contiene líneas de
    # Recepción, se eliminan de esa fuente y prevalece el reporte
    # específico de recepción.
    if not stock.empty and not recepcion.empty:
        es_recepcion = (
            stock["Area"].str.upper().str.contains(
                "RECEPC",
                na=False,
            )
            | stock["Ubicacion"].str.upper().str.startswith(
                "REC-",
                na=False,
            )
        )
        stock = stock.loc[~es_recepcion].copy()

    detalle = pd.concat(
        [stock, recepcion],
        ignore_index=True,
    )

    if not detalle.empty:
        detalle["_ClaveFisica"] = (
            detalle["ArticuloCodigo"].astype(str)
            + "|"
            + detalle["Ubicacion"].astype(str)
            + "|"
            + detalle["Contenedor"].astype(str)
            + "|"
            + detalle["Cantidad"].astype(str)
        )
        detalle = (
            detalle
            .drop_duplicates(
                "_ClaveFisica",
                keep="last",
            )
            .drop(columns="_ClaveFisica")
            .reset_index(drop=True)
        )

    resumen = _resumir_detalle(
        detalle,
        nombre_stock="StockWMSDetalleComparable",
    )

    return detalle, resumen


def preparar_detalle_auxiliar_wms(
    df_detalle_auxiliar: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resume `stock_detallado` como fuente auxiliar.

    Esta cifra se conserva para auditoría, pero NO participa en
    Integridad WMS ni en la conciliación ERP vs WMS.
    """

    detalle = _preparar_lineas_detalle(
        df_detalle_auxiliar,
        nombre_fuente="Stock detallado auxiliar",
    )

    resumen = _resumir_detalle(
        detalle,
        nombre_stock="StockWMSDetalleAuxiliar",
    )

    columnas = [
        "ArticuloCodigo",
        "StockWMSDetalleAuxiliar",
    ]
    return resumen[columnas].copy() if not resumen.empty else pd.DataFrame(
        columns=columnas
    )


def preparar_disponible_wms(
    dataframe: pd.DataFrame,
    *,
    estados_fisicos: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    codigo = buscar_columna(
        dataframe,
        [
            "Codigo",
            "CodigoArticulo",
            "ArticuloCodigo",
        ],
        obligatoria=True,
    )

    descripcion = buscar_columna(
        dataframe,
        [
            "Descripcion",
            "ArticuloDescripcion",
        ],
    )

    salida = pd.DataFrame({
        "ArticuloCodigo": normalizar_codigo(
            dataframe[codigo]
        ),
        "DescripcionWMSResumen": (
            dataframe[descripcion]
            .fillna("")
            .astype(str)
            .str.strip()
            if descripcion
            else ""
        ),
    })

    for columna in COLUMNAS_ESTADO_WMS:
        origen = buscar_columna(
            dataframe,
            [columna],
        )

        salida[columna] = (
            convertir_numero(dataframe[origen])
            if origen
            else 0.0
        )

    estados_validos = [
        columna
        for columna in estados_fisicos
        if columna in salida.columns
    ]

    salida["StockWMSResumen"] = (
        salida[estados_validos].sum(axis=1)
        if estados_validos
        else 0.0
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
    ].copy()

    agregaciones = {
        "DescripcionWMSResumen": (
            "DescripcionWMSResumen",
            primer_texto_no_vacio,
        ),
        "StockWMSResumen": (
            "StockWMSResumen",
            "sum",
        ),
    }

    for columna in COLUMNAS_ESTADO_WMS:
        agregaciones[columna] = (
            columna,
            "sum",
        )

    return (
        salida
        .groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(**agregaciones)
    )


def preparar_maestro_articulos(
    dataframe: pd.DataFrame | None,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "DescripcionMaestro",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Marca",
        "Origen",
    ]

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=columnas)

    codigo = buscar_columna(
        dataframe,
        [
            "COD_ART",
            "CodigoArticulo",
            "ArticuloCodigo",
            "Codigo",
        ],
    )

    if not codigo:
        return pd.DataFrame(columns=columnas)

    candidatos = {
        "DescripcionMaestro": [
            "DESCRIP",
            "ArticuloDescripcion",
            "Descripcion",
        ],
        "Familia": [
            "Familia",
        ],
        "Familia2": [
            "Familia_2",
            "Familia2",
        ],
        "Sectorizacion": [
            "Sectorizacion",
            "Sectorización",
            "Sector",
        ],
        "Marca": [
            "Marca",
        ],
        "Origen": [
            "Origen",
        ],
    }

    salida = pd.DataFrame({
        "ArticuloCodigo": normalizar_codigo(
            dataframe[codigo]
        ),
    })

    for destino, opciones in candidatos.items():
        origen = buscar_columna(
            dataframe,
            opciones,
        )

        salida[destino] = (
            dataframe[origen]
            .fillna("")
            .astype(str)
            .str.strip()
            if origen
            else ""
        )

    return (
        salida
        .loc[
            salida["ArticuloCodigo"].ne("")
        ]
        .drop_duplicates(
            "ArticuloCodigo",
            keep="first",
        )
        .reset_index(drop=True)
    )


def construir_conciliacion(
    df_erp: pd.DataFrame,
    df_erp_sanitarios: pd.DataFrame,
    df_wms_stock_digip: pd.DataFrame,
    df_wms_recepcion: pd.DataFrame,
    df_wms_detalle_auxiliar: pd.DataFrame,
    df_wms_disponible: pd.DataFrame,
    df_articulos: pd.DataFrame | None = None,
    *,
    configuracion: ConfiguracionComparacion | None = None,
    tolerancia_unidades: float = 0.0,
    tolerancia_porcentaje: float = 0.0,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    config = configuracion or ConfiguracionComparacion()

    erp_base = preparar_erp(
        df_erp,
        columnas_stock=list(
            config.columnas_stock_erp
        ),
        prefijo_desglose="ERPBase",
    ).rename(
        columns={
            "StockERP": "StockERPBase",
            "DescripcionERP": "DescripcionERPBase",
        }
    )

    if (
        config.incluir_erp_sanitarios
        and df_erp_sanitarios is not None
        and not df_erp_sanitarios.empty
    ):
        erp_sanitarios = preparar_erp(
            df_erp_sanitarios,
            columnas_stock=list(
                config.columnas_stock_erp_sanitarios
            ),
            prefijo_desglose="ERPSanitarios",
        ).rename(
            columns={
                "StockERP": "StockERPSanitarios",
                "DescripcionERP": "DescripcionERPSanitarios",
            }
        )

        # En el reporte de Sanitarios solo se suma el stock físico.
        # Los restantes estados ERP continúan tomándose del reporte base.
        columnas_sanitarios = [
            columna
            for columna in erp_sanitarios.columns
            if (
                columna in {
                    "ArticuloCodigo",
                    "DescripcionERPSanitarios",
                    "StockERPSanitarios",
                }
                or columna.startswith(
                    "ERPSanitarios_"
                )
            )
        ]
        erp_sanitarios = erp_sanitarios[
            columnas_sanitarios
        ].copy()
    else:
        erp_sanitarios = pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "DescripcionERPSanitarios",
                "StockERPSanitarios",
            ]
        )

    erp = erp_base.merge(
        erp_sanitarios,
        on="ArticuloCodigo",
        how="outer",
        validate="one_to_one",
    )

    for columna in [
        "StockERPBase",
        "StockERPSanitarios",
    ]:
        if columna not in erp.columns:
            erp[columna] = 0.0

        erp[columna] = pd.to_numeric(
            erp[columna],
            errors="coerce",
        ).fillna(0.0)

    erp["StockERP"] = (
        erp["StockERPBase"]
        + erp["StockERPSanitarios"]
    )

    erp["DescripcionERP"] = (
        erp.get(
            "DescripcionERPBase",
            pd.Series("", index=erp.index),
        )
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "DescripcionERPSanitarios" in erp.columns:
        descripcion_sanitarios = (
            erp["DescripcionERPSanitarios"]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        erp["DescripcionERP"] = erp[
            "DescripcionERP"
        ].where(
            erp["DescripcionERP"].ne(""),
            descripcion_sanitarios,
        )

    detalle_ubicaciones, resumen_detalle = (
        preparar_detalle_comparable_wms(
            df_wms_stock_digip,
            df_wms_recepcion,
        )
    )

    resumen_detalle_auxiliar = (
        preparar_detalle_auxiliar_wms(
            df_wms_detalle_auxiliar
        )
    )

    resumen_wms = preparar_disponible_wms(
        df_wms_disponible,
        estados_fisicos=list(
            config.incluir_estados_wms
        ),
    )

    maestro = preparar_maestro_articulos(
        df_articulos
    )

    tabla = erp.merge(
        resumen_detalle,
        on="ArticuloCodigo",
        how="outer",
        validate="one_to_one",
    )

    tabla = tabla.merge(
        resumen_wms,
        on="ArticuloCodigo",
        how="outer",
        validate="one_to_one",
    )

    if not resumen_detalle_auxiliar.empty:
        tabla = tabla.merge(
            resumen_detalle_auxiliar,
            on="ArticuloCodigo",
            how="left",
            validate="one_to_one",
        )

    if not maestro.empty:
        tabla = tabla.merge(
            maestro,
            on="ArticuloCodigo",
            how="left",
            validate="one_to_one",
        )

    def combinar_texto(
        columnas: list[str],
        default: str,
    ) -> pd.Series:
        resultado = pd.Series(
            "",
            index=tabla.index,
            dtype="object",
        )

        for columna in columnas:
            if columna not in tabla.columns:
                continue

            valores = (
                tabla[columna]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            resultado = resultado.where(
                resultado.ne(""),
                valores,
            )

        return resultado.replace("", default)

    tabla["ArticuloDescripcion"] = combinar_texto(
        [
            "DescripcionMaestro",
            "DescripcionERP",
            "DescripcionWMSResumen",
            "DescripcionWMSDetalle",
        ],
        "Sin descripción",
    )

    tabla["GrupoInventario"] = (
        tabla["ArticuloCodigo"]
        .map(clasificar_grupo_inventario)
    )

    for columna in [
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Marca",
        "Origen",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "Sin definir")
        )

    columnas_numericas = [
        "StockERP",
        "StockERPBase",
        "StockERPSanitarios",
        "StockWMSDetalleComparable",
        "StockWMSDetalleAuxiliar",
        "StockWMSResumen",
        "CantidadUbicaciones",
        "CantidadContenedores",
        "CantidadLineasFisicas",
        "StockFisicoERPInformativo",
        "StockComprometidoERP",
        "StockReservadoERP",
        "StockPendienteERP",
        "StockDisponibleERP",
        "EstadoAprobadoERP",
        "EstadoTransitoERP",
        *COLUMNAS_ESTADO_WMS,
    ]

    for columna in columnas_numericas:
        if columna not in tabla.columns:
            tabla[columna] = 0.0

        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0.0)

    columnas_desglose_erp = [
        columna
        for columna in tabla.columns
        if (
            columna.startswith("ERPBase_")
            or columna.startswith(
                "ERPSanitarios_"
            )
        )
    ]

    for columna in columnas_desglose_erp:
        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0.0)

    tabla["DiferenciaERPvsWMS"] = (
        tabla["StockWMSResumen"]
        - tabla["StockERP"]
    )

    tabla["DiferenciaAbsoluta"] = (
        tabla["DiferenciaERPvsWMS"].abs()
    )

    referencia = (
        tabla[
            [
                "StockERP",
                "StockWMSResumen",
            ]
        ]
        .abs()
        .max(axis=1)
    )

    tabla["DiferenciaPorcentaje"] = (
        tabla["DiferenciaAbsoluta"]
        .div(
            referencia.where(
                referencia.ne(0)
            )
        )
        .mul(100)
        .fillna(0)
    )

    tabla["DiferenciaIntegridadWMS"] = (
        tabla["StockWMSResumen"]
        - tabla["StockWMSDetalleComparable"]
    )

    tabla["DiferenciaFuenteAuxiliar"] = (
        tabla["StockWMSDetalleAuxiliar"]
        - tabla["StockWMSDetalleComparable"]
    )

    tabla["UsoDetalleAuxiliar"] = (
        "Solo auditoría - no participa en KPIs"
    )

    tabla["IntegridadWMS"] = "Coincide"

    tabla.loc[
        tabla["DiferenciaIntegridadWMS"].abs().gt(
            float(tolerancia_unidades)
        ),
        "IntegridadWMS",
    ] = "Revisar detalle WMS"

    dentro_tolerancia = (
        tabla["DiferenciaAbsoluta"].le(
            float(tolerancia_unidades)
        )
        | tabla["DiferenciaPorcentaje"].le(
            float(tolerancia_porcentaje)
        )
    )

    tabla["EstadoConciliacion"] = "Diferencia"

    tabla.loc[
        tabla["DiferenciaAbsoluta"].eq(0)
        | dentro_tolerancia,
        "EstadoConciliacion",
    ] = "Conciliado"

    tabla["SentidoDiferencia"] = "Igual"

    tabla.loc[
        tabla["DiferenciaERPvsWMS"].gt(0),
        "SentidoDiferencia",
    ] = "Sobra en WMS"

    tabla.loc[
        tabla["DiferenciaERPvsWMS"].lt(0),
        "SentidoDiferencia",
    ] = "Sobra en ERP"

    q80 = (
        float(
            tabla["DiferenciaAbsoluta"].quantile(
                0.80
            )
        )
        if not tabla.empty
        else 0
    )

    q95 = (
        float(
            tabla["DiferenciaAbsoluta"].quantile(
                0.95
            )
        )
        if not tabla.empty
        else 0
    )

    tabla["PrioridadInventario"] = "Baja"

    tabla.loc[
        tabla["DiferenciaAbsoluta"].gt(0),
        "PrioridadInventario",
    ] = "Media"

    tabla.loc[
        tabla["DiferenciaAbsoluta"].ge(q80),
        "PrioridadInventario",
    ] = "Alta"

    tabla.loc[
        tabla["DiferenciaAbsoluta"].ge(q95),
        "PrioridadInventario",
    ] = "Crítica"

    tabla.loc[
        tabla["EstadoConciliacion"].eq(
            "Conciliado"
        ),
        "PrioridadInventario",
    ] = "Sin acción"

    tabla = tabla.sort_values(
        by=[
            "DiferenciaAbsoluta",
            "DiferenciaIntegridadWMS",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)

    columnas_finales = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "GrupoInventario",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "Marca",
        "Origen",
        "StockERPBase",
        "StockERPSanitarios",
        "StockERP",
        "StockWMSResumen",
        "StockWMSDetalleComparable",
        "StockWMSDetalleAuxiliar",
        "DiferenciaERPvsWMS",
        "DiferenciaAbsoluta",
        "DiferenciaPorcentaje",
        "DiferenciaIntegridadWMS",
        "DiferenciaFuenteAuxiliar",
        "UsoDetalleAuxiliar",
        "IntegridadWMS",
        "EstadoConciliacion",
        "SentidoDiferencia",
        "PrioridadInventario",
        "CantidadUbicaciones",
        "CantidadContenedores",
        "StockComprometidoERP",
        "StockReservadoERP",
        "StockPendienteERP",
        "StockDisponibleERP",
        "EstadoAprobadoERP",
        "EstadoTransitoERP",
        *COLUMNAS_ESTADO_WMS,
    ]

    columnas_desglose_erp = [
        columna
        for columna in tabla.columns
        if (
            columna.startswith("ERPBase_")
            or columna.startswith(
                "ERPSanitarios_"
            )
        )
    ]

    columnas_finales = (
        columnas_finales
        + [
            columna
            for columna in columnas_desglose_erp
            if columna not in columnas_finales
        ]
    )

    return (
        tabla[columnas_finales].copy(),
        detalle_ubicaciones,
        config.como_dict(),
    )
