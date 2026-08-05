from __future__ import annotations

import re
import unicodedata

import pandas as pd


# =====================================================
# UTILIDADES GENERALES
# =====================================================

def limpiar_nombres_columnas(df: pd.DataFrame) -> pd.DataFrame:
    tabla = df.copy()
    tabla.columns = [str(columna).strip() for columna in tabla.columns]
    return tabla


def _texto_clave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = texto.strip().lower()
    return re.sub(r"[^a-z0-9]+", "", texto)


def _buscar_columna(df: pd.DataFrame, alias: list[str]) -> str | None:
    mapa = {_texto_clave(columna): columna for columna in df.columns}

    for nombre in alias:
        encontrada = mapa.get(_texto_clave(nombre))
        if encontrada is not None:
            return encontrada

    return None


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def convertir_numero(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(serie):
        return pd.to_numeric(serie, errors="coerce").fillna(0)

    texto = (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.replace("\u00a0", "", regex=False)
        .str.replace(" ", "", regex=False)
    )

    # Formato habitual español: 1.234,50
    tiene_coma = texto.str.contains(",", regex=False)
    texto.loc[tiene_coma] = (
        texto.loc[tiene_coma]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    return pd.to_numeric(texto, errors="coerce").fillna(0)


# =====================================================
# ESTANDARIZACIÓN DE FUENTES FÍSICAS
# =====================================================

ALIAS_COLUMNAS = {
    "AreaDescripcion": [
        "AreaDescripcion", "Area Descripcion", "Área Descripción", "Area", "Área",
    ],
    "Ubicacion": [
        "Ubicacion", "Ubicación", "CodigoUbicacion", "UbicacionCodigo",
    ],
    "Fabricante": ["Fabricante"],
    "ArticuloCodigo": [
        "ArticuloCodigo", "Articulo Codigo", "Artículo Código", "CodigoArticulo",
        "codigo_articulo", "CodArticulo", "Codigo", "Código", "Articulo",
    ],
    "ArticuloDescripcion": [
        "ArticuloDescripcion", "Articulo Descripcion", "Artículo Descripción",
        "DescripcionArticulo", "Descripción Artículo", "Descripcion", "Descripción",
    ],
    "Lote": ["Lote"],
    "FechaVencimiento": [
        "FechaVencimiento", "Fecha Vencimiento", "Vencimiento",
    ],
    "DiasAlVencimiento": [
        "DiasAlVencimiento", "Días al vencimiento", "Dias al vencimiento",
    ],
    "Cantidad": [
        "Cantidad", "Unidades", "Stock", "CantidadStock", "UnidadesSueltas",
    ],
    "ContenedorNumero": [
        "ContenedorNumero", "Contenedor Numero", "NumeroContenedor", "Contenedor",
    ],
    "EstadoDescripcion": [
        "EstadoDescripcion", "Estado Descripcion", "Estado", "EstadoStock",
    ],
    "Bultos": ["Bultos"],
    "UnidadesSueltas": [
        "UnidadesSueltas", "Unidades Sueltas",
    ],
    "Critico": ["Critico", "Crítico"],
}

COLUMNAS_ESTANDAR = [
    "FuenteStock",
    "AreaDescripcion",
    "Ubicacion",
    "Fabricante",
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "Lote",
    "FechaVencimiento",
    "DiasAlVencimiento",
    "Cantidad",
    "ContenedorNumero",
    "EstadoDescripcion",
    "Bultos",
    "UnidadesSueltas",
    "Critico",
]


def estandarizar_stock_fisico(
    df: pd.DataFrame,
    fuente: str,
) -> pd.DataFrame:
    """Normaliza una fuente física sin perder sus columnas originales."""
    tabla_origen = limpiar_nombres_columnas(df)

    if len(tabla_origen.columns) == 0:
        return pd.DataFrame(columns=COLUMNAS_ESTANDAR)

    tabla = pd.DataFrame(index=tabla_origen.index)
    tabla["FuenteStock"] = fuente

    for columna_destino, alias in ALIAS_COLUMNAS.items():
        columna_origen = _buscar_columna(tabla_origen, alias)

        if columna_origen is None:
            tabla[columna_destino] = pd.NA
        else:
            tabla[columna_destino] = tabla_origen[columna_origen]

    tabla["ArticuloCodigo"] = normalizar_codigo(tabla["ArticuloCodigo"])

    for columna in ["AreaDescripcion", "Ubicacion", "ArticuloDescripcion", "EstadoDescripcion"]:
        tabla[columna] = tabla[columna].fillna("").astype(str).str.strip()

    # En algunos reportes Cantidad puede faltar, pero sí existir UnidadesSueltas.
    cantidad = convertir_numero(tabla["Cantidad"])
    unidades_sueltas = convertir_numero(tabla["UnidadesSueltas"])
    tabla["Cantidad"] = cantidad.where(cantidad.ne(0), unidades_sueltas)

    tabla["Bultos"] = convertir_numero(tabla["Bultos"])
    tabla["UnidadesSueltas"] = unidades_sueltas
    tabla["DiasAlVencimiento"] = convertir_numero(tabla["DiasAlVencimiento"])

    tabla["FechaVencimiento"] = pd.to_datetime(
        tabla["FechaVencimiento"],
        errors="coerce",
        dayfirst=True,
    )

    # Filas sin código no pueden participar del consolidado por artículo.
    tabla = tabla.loc[tabla["ArticuloCodigo"].ne("")].copy()

    return tabla[COLUMNAS_ESTANDAR].reset_index(drop=True)


def construir_stock_total_detallado(
    df_stock_detallado: pd.DataFrame,
    df_stock_recepcion: pd.DataFrame,
) -> pd.DataFrame:
    """Une Almacén/Picking con Recepción en una sola existencia física."""
    almacen = estandarizar_stock_fisico(
        df_stock_detallado,
        fuente="Almacén / Picking",
    )
    recepcion = estandarizar_stock_fisico(
        df_stock_recepcion,
        fuente="Recepción",
    )

    tabla = pd.concat(
        [almacen, recepcion],
        ignore_index=True,
        sort=False,
    )

    if tabla.empty:
        return pd.DataFrame(columns=COLUMNAS_ESTANDAR)

    tabla["Cantidad"] = convertir_numero(tabla["Cantidad"])

    return tabla.sort_values(
        ["ArticuloCodigo", "FuenteStock", "AreaDescripcion", "Ubicacion"],
        na_position="last",
    ).reset_index(drop=True)


def construir_stock_total_por_articulo(
    tabla_stock_total_detallado: pd.DataFrame,
) -> pd.DataFrame:
    """Resume la existencia física por artículo y por fuente."""
    columnas_salida = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "StockAlmacenPicking",
        "StockRecepcion",
        "StockFisicoTotal",
        "CantidadUbicaciones",
        "CantidadContenedores",
        "CantidadAreas",
    ]

    if tabla_stock_total_detallado.empty:
        return pd.DataFrame(columns=columnas_salida)

    tabla = tabla_stock_total_detallado.copy()
    tabla["Cantidad"] = convertir_numero(tabla["Cantidad"])

    descripcion = (
        tabla.loc[tabla["ArticuloDescripcion"].ne("")]
        .drop_duplicates("ArticuloCodigo", keep="first")
        [["ArticuloCodigo", "ArticuloDescripcion"]]
    )

    por_fuente = (
        tabla.groupby(["ArticuloCodigo", "FuenteStock"], as_index=False)
        .agg(Cantidad=("Cantidad", "sum"))
        .pivot(index="ArticuloCodigo", columns="FuenteStock", values="Cantidad")
        .fillna(0)
        .reset_index()
    )
    por_fuente.columns.name = None

    por_fuente = por_fuente.rename(columns={
        "Almacén / Picking": "StockAlmacenPicking",
        "Recepción": "StockRecepcion",
    })

    for columna in ["StockAlmacenPicking", "StockRecepcion"]:
        if columna not in por_fuente.columns:
            por_fuente[columna] = 0

    dimensiones = (
        tabla.groupby("ArticuloCodigo", as_index=False)
        .agg(
            CantidadUbicaciones=("Ubicacion", lambda serie: serie.loc[serie.ne("")].nunique()),
            CantidadContenedores=("ContenedorNumero", lambda serie: serie.dropna().astype(str).loc[lambda x: x.ne("")].nunique()),
            CantidadAreas=("AreaDescripcion", lambda serie: serie.loc[serie.ne("")].nunique()),
        )
    )

    resumen = (
        por_fuente
        .merge(descripcion, on="ArticuloCodigo", how="left", validate="one_to_one")
        .merge(dimensiones, on="ArticuloCodigo", how="left", validate="one_to_one")
    )

    resumen["ArticuloDescripcion"] = resumen["ArticuloDescripcion"].fillna("")
    resumen["StockFisicoTotal"] = (
        resumen["StockAlmacenPicking"] + resumen["StockRecepcion"]
    )

    columnas_numericas = [
        "StockAlmacenPicking", "StockRecepcion", "StockFisicoTotal",
        "CantidadUbicaciones", "CantidadContenedores", "CantidadAreas",
    ]
    for columna in columnas_numericas:
        resumen[columna] = pd.to_numeric(resumen[columna], errors="coerce").fillna(0)

    return resumen[columnas_salida].sort_values(
        ["StockFisicoTotal", "ArticuloCodigo"],
        ascending=[False, True],
    ).reset_index(drop=True)


# =====================================================
# PREPARACIONES EXISTENTES
# =====================================================

def preparar_tabla_stock(df: pd.DataFrame, nombre_fuente: str) -> pd.DataFrame:
    tabla = limpiar_nombres_columnas(df)

    if len(tabla.columns) == 0:
        return tabla

    columna_codigo = _buscar_columna(
        tabla,
        ALIAS_COLUMNAS["ArticuloCodigo"],
    )

    if columna_codigo:
        tabla[columna_codigo] = normalizar_codigo(tabla[columna_codigo])

    tabla.insert(0, "FuenteStock", nombre_fuente)
    return tabla


def preparar_max_min(df: pd.DataFrame) -> pd.DataFrame:
    tabla = limpiar_nombres_columnas(df)

    if len(tabla.columns) == 0:
        return tabla

    columna_codigo = _buscar_columna(
        tabla,
        ["codigo_articulo", "CodigoArticulo", "ArticuloCodigo"],
    )

    if columna_codigo:
        tabla[columna_codigo] = normalizar_codigo(tabla[columna_codigo])

    for nombre in [
        "unidades_disponibles",
        "stock_minimo",
        "stock_maximo",
        "stock_maximo_Preparar",
    ]:
        columna = _buscar_columna(tabla, [nombre])
        if columna:
            tabla[columna] = convertir_numero(tabla[columna])

    return tabla
