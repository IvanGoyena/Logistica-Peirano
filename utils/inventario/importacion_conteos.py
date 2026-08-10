from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import re
import unicodedata

import pandas as pd


COLUMNAS_ARCHIVO_CONTEO = {
    "articulo": (
        "Artículo",
        "Articulo",
        "CodigoArticulo",
        "ArticuloCodigo",
    ),
    "ubicacion": (
        "Ubicación",
        "Ubicacion",
    ),
    "foto_unidades": (
        "Cantidad Foto (Unidades)",
        "Cantidad Foto Unidades",
    ),
    "foto_cajas": (
        "Cantidad Foto (Cajas)",
        "Cantidad Foto Cajas",
    ),
    "relevada_unidades": (
        "Cantidad Relevada (Unidades)",
        "Cantidad Relevada Unidades",
    ),
    "relevada_cajas": (
        "Cantidad Relevada (Cajas)",
        "Cantidad Relevada Cajas",
    ),
    "diferencia": (
        "Diferencia",
    ),
    "usuario": (
        "Usuario Relevamiento",
        "Usuario",
    ),
    "fecha": (
        "Fecha Relevamiento",
        "Fecha",
    ),
    "foto_pertenece": (
        "Foto Stock (Pertenece)",
        "Foto Pertenece",
    ),
}


@dataclass(frozen=True)
class ResumenImportacion:
    registros_originales: int
    registros_validos: int
    duplicados_archivo: int
    fuera_del_plan: int
    ambiguos: int
    errores: int


def _normalizar_nombre(valor: object) -> str:
    texto = unicodedata.normalize(
        "NFKD",
        str(valor or ""),
    )
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(
            caracter
        )
    )
    return re.sub(
        r"[^a-z0-9]",
        "",
        texto.lower(),
    )


def _buscar_columna(
    dataframe: pd.DataFrame,
    candidatos: tuple[str, ...],
    *,
    obligatoria: bool = True,
) -> str | None:
    mapa = {
        _normalizar_nombre(columna): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        clave = _normalizar_nombre(candidato)
        if clave in mapa:
            return mapa[clave]

    if obligatoria:
        raise ValueError(
            "No se encontró la columna requerida: "
            + " / ".join(candidatos)
        )

    return None


def normalizar_codigo(valor: object) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip().upper()

    if texto.endswith(".0"):
        sin_decimal = texto[:-2]
        if sin_decimal.replace("-", "").isdigit():
            texto = sin_decimal

    return texto


def normalizar_ubicacion(valor: object) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    return str(valor).strip().upper()


def _convertir_fecha(valor: object) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(valor, (int, float)):
        fecha = pd.to_datetime(
            valor,
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )
    else:
        fecha = pd.to_datetime(
            valor,
            dayfirst=True,
            errors="coerce",
        )

    if pd.isna(fecha):
        return str(valor).strip()

    return fecha.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def calcular_hash_archivo(
    contenido: bytes,
) -> str:
    return sha256(contenido).hexdigest()


def leer_archivo_conteo(
    contenido: bytes,
) -> pd.DataFrame:
    """
    Lee el Excel generado por Inventarios DIGIP.

    Prioriza la hoja `Detalle`. Si no existe, utiliza
    la primera hoja disponible.
    """

    libro = pd.ExcelFile(
        BytesIO(contenido)
    )

    hoja = (
        "Detalle"
        if "Detalle" in libro.sheet_names
        else libro.sheet_names[0]
    )

    dataframe = pd.read_excel(
        BytesIO(contenido),
        sheet_name=hoja,
    )

    dataframe = dataframe.dropna(
        how="all"
    ).reset_index(drop=True)

    return dataframe


def normalizar_archivo_conteo(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    columnas = {
        clave: _buscar_columna(
            dataframe,
            candidatos,
            obligatoria=clave in {
                "articulo",
                "ubicacion",
                "relevada_unidades",
            },
        )
        for clave, candidatos
        in COLUMNAS_ARCHIVO_CONTEO.items()
    }

    salida = pd.DataFrame({
        "ArticuloCodigo": (
            dataframe[columnas["articulo"]]
            .map(normalizar_codigo)
        ),
        "Ubicacion": (
            dataframe[columnas["ubicacion"]]
            .map(normalizar_ubicacion)
        ),
        "CantidadFotoUnidades": (
            pd.to_numeric(
                dataframe[
                    columnas["foto_unidades"]
                ],
                errors="coerce",
            )
            if columnas["foto_unidades"]
            else 0
        ),
        "CantidadFotoCajas": (
            pd.to_numeric(
                dataframe[
                    columnas["foto_cajas"]
                ],
                errors="coerce",
            )
            if columnas["foto_cajas"]
            else 0
        ),
        "CantidadRelevadaUnidades": (
            pd.to_numeric(
                dataframe[
                    columnas[
                        "relevada_unidades"
                    ]
                ],
                errors="coerce",
            )
        ),
        "CantidadRelevadaCajas": (
            pd.to_numeric(
                dataframe[
                    columnas["relevada_cajas"]
                ],
                errors="coerce",
            )
            if columnas["relevada_cajas"]
            else 0
        ),
        "DiferenciaArchivo": (
            pd.to_numeric(
                dataframe[
                    columnas["diferencia"]
                ],
                errors="coerce",
            )
            if columnas["diferencia"]
            else pd.NA
        ),
        "UsuarioRelevamiento": (
            dataframe[columnas["usuario"]]
            .fillna("")
            .astype(str)
            .str.strip()
            if columnas["usuario"]
            else ""
        ),
        "FechaRelevamiento": (
            dataframe[columnas["fecha"]]
            .map(_convertir_fecha)
            if columnas["fecha"]
            else ""
        ),
        "FotoPertenece": (
            dataframe[
                columnas["foto_pertenece"]
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            if columnas["foto_pertenece"]
            else ""
        ),
    })

    salida["FilaArchivo"] = (
        salida.index + 2
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
        & salida["Ubicacion"].ne("")
    ].copy()

    salida["CantidadFotoUnidades"] = (
        salida["CantidadFotoUnidades"]
        .fillna(0)
    )
    salida["CantidadFotoCajas"] = (
        salida["CantidadFotoCajas"]
        .fillna(0)
    )
    salida["CantidadRelevadaCajas"] = (
        salida["CantidadRelevadaCajas"]
        .fillna(0)
    )

    salida["ClaveDuplicadoArchivo"] = (
        salida["ArticuloCodigo"]
        + "|"
        + salida["Ubicacion"]
        + "|"
        + salida[
            "CantidadFotoUnidades"
        ].astype(str)
        + "|"
        + salida[
            "CantidadRelevadaUnidades"
        ].astype(str)
        + "|"
        + salida[
            "UsuarioRelevamiento"
        ].astype(str)
        + "|"
        + salida[
            "FechaRelevamiento"
        ].astype(str)
    )

    salida["EsDuplicadoArchivo"] = (
        salida[
            "ClaveDuplicadoArchivo"
        ].duplicated(keep="first")
    )

    salida["ClavePlan"] = (
        salida["ArticuloCodigo"]
        + "|"
        + salida["Ubicacion"]
    )

    return salida.reset_index(drop=True)


def validar_contra_plan(
    conteos: pd.DataFrame,
    items_plan: pd.DataFrame,
    claves_ya_guardadas: set[str] | None = None,
) -> tuple[pd.DataFrame, ResumenImportacion]:
    """
    Relaciona cada fila por Artículo + Ubicación.

    Si el plan contiene más de un ItemID para esa clave,
    la fila queda Ambigua y no se guarda automáticamente.
    """

    claves_ya_guardadas = (
        claves_ya_guardadas or set()
    )

    items = items_plan.copy()

    items["ArticuloCodigo"] = (
        items["ArticuloCodigo"]
        .map(normalizar_codigo)
    )
    items["Ubicacion"] = (
        items["Ubicacion"]
        .map(normalizar_ubicacion)
    )
    items["ClavePlan"] = (
        items["ArticuloCodigo"]
        + "|"
        + items["Ubicacion"]
    )

    conteo_items = (
        items.groupby(
            "ClavePlan"
        )["ItemID"]
        .nunique()
    )

    item_unico = (
        items.drop_duplicates(
            "ClavePlan",
            keep="first",
        )[
            [
                "ClavePlan",
                "ItemID",
                "Contenedor",
                "ArticuloDescripcion",
            ]
        ]
    )

    salida = conteos.merge(
        item_unico,
        on="ClavePlan",
        how="left",
    )

    salida["CantidadItemsPlan"] = (
        salida["ClavePlan"]
        .map(conteo_items)
        .fillna(0)
        .astype(int)
    )

    salida["EstadoValidacion"] = "Válido"

    salida.loc[
        salida["EsDuplicadoArchivo"],
        "EstadoValidacion",
    ] = "Duplicado en archivo"

    salida.loc[
        salida["CantidadItemsPlan"].eq(0),
        "EstadoValidacion",
    ] = "Fuera del plan"

    salida.loc[
        salida["CantidadItemsPlan"].gt(1),
        "EstadoValidacion",
    ] = "Coincidencia ambigua"

    salida.loc[
        salida[
            "CantidadRelevadaUnidades"
        ].isna(),
        "EstadoValidacion",
    ] = "Cantidad inválida"

    salida.loc[
        salida["FotoPertenece"].isin(
            ["NO", "N", "FALSE", "0"]
        ),
        "EstadoValidacion",
    ] = "Foto no pertenece"

    salida["ClaveImportacion"] = (
        salida["ClavePlan"]
        + "|"
        + salida[
            "FechaRelevamiento"
        ].astype(str)
        + "|"
        + salida[
            "CantidadRelevadaUnidades"
        ].astype(str)
    )

    salida.loc[
        salida[
            "ClaveImportacion"
        ].isin(claves_ya_guardadas),
        "EstadoValidacion",
    ] = "Ya importado"

    validos = int(
        salida["EstadoValidacion"]
        .eq("Válido")
        .sum()
    )

    resumen = ResumenImportacion(
        registros_originales=len(conteos),
        registros_validos=validos,
        duplicados_archivo=int(
            salida["EstadoValidacion"]
            .eq("Duplicado en archivo")
            .sum()
        ),
        fuera_del_plan=int(
            salida["EstadoValidacion"]
            .eq("Fuera del plan")
            .sum()
        ),
        ambiguos=int(
            salida["EstadoValidacion"]
            .eq("Coincidencia ambigua")
            .sum()
        ),
        errores=int(
            salida["EstadoValidacion"]
            .isin(
                [
                    "Cantidad inválida",
                    "Foto no pertenece",
                    "Ya importado",
                ]
            )
            .sum()
        ),
    )

    return salida, resumen
