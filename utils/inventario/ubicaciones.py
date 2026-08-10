from __future__ import annotations

import re
import unicodedata
import pandas as pd


def _norm(texto: object) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or ""))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", valor.upper())


def _buscar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None
    mapa = {_norm(c): c for c in df.columns}
    for candidato in candidatos:
        if _norm(candidato) in mapa:
            return mapa[_norm(candidato)]
    return None


def normalizar_ubicacion(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    return str(valor).strip().upper()


def clasificar_por_codigo(ubicacion: object) -> str:
    codigo = normalizar_ubicacion(ubicacion)
    prefijo = codigo.split("-", 1)[0]
    if prefijo in {"PCK", "PIC", "PKG", "PICK"}:
        return "Picking"
    if prefijo in {"ALM", "NAC", "IMP", "RES", "RACK"}:
        return "Almacén"
    if prefijo.startswith("REC"):
        return "Recepción"
    return "Sin clasificar"


def preparar_maestro_ubicaciones_inventario(df: pd.DataFrame) -> pd.DataFrame:
    columnas = ["Ubicacion", "TipoUbicacion", "AreaUbicacion", "PasilloUbicacion"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columnas)

    ubicacion = _buscar_columna(df, ["ClaveUbicacion", "Ubicacion", "Ubicación", "CodigoVerificador"])
    tipo = _buscar_columna(df, ["GrupoOcupacion", "Tipo", "TipoUbicacion", "Tipo Ubicacion"])
    area = _buscar_columna(df, ["Area", "Área", "AreaDescripcion"])
    pasillo = _buscar_columna(df, ["Pasillo"])
    ab = _buscar_columna(df, ["Ab"])
    posicion = _buscar_columna(df, ["Posicion", "Posición"])
    nivel = _buscar_columna(df, ["Nivel"])

    if ubicacion:
        codigos = df[ubicacion].map(normalizar_ubicacion)
    elif all([ab, pasillo, posicion, nivel]):
        codigos = (
            df[ab].astype(str).str.strip().str.upper() + "-" +
            df[pasillo].astype(str).str.strip().str.zfill(3) + "-" +
            df[posicion].astype(str).str.strip().str.zfill(3) + "-" +
            df[nivel].astype(str).str.strip().str.zfill(3)
        )
    else:
        return pd.DataFrame(columns=columnas)

    salida = pd.DataFrame({"Ubicacion": codigos})
    salida["TipoUbicacion"] = (
        df[tipo].fillna("").astype(str).str.strip().str.title()
        if tipo else salida["Ubicacion"].map(clasificar_por_codigo)
    )
    mapa_tipo = {
        "Picking": "Picking", "Almacen": "Almacén", "Almacén": "Almacén",
        "Reserva": "Almacén", "Estanterias": "Almacén", "Estanterías": "Almacén",
    }
    salida["TipoUbicacion"] = salida["TipoUbicacion"].map(
        lambda x: mapa_tipo.get(str(x).strip(), str(x).strip() or "Sin clasificar")
    )
    salida["AreaUbicacion"] = df[area].fillna("").astype(str).str.strip() if area else ""
    salida["PasilloUbicacion"] = df[pasillo].fillna("").astype(str).str.strip() if pasillo else ""
    salida = salida.loc[salida["Ubicacion"].ne("")].drop_duplicates("Ubicacion", keep="first")
    return salida[columnas].reset_index(drop=True)


def enriquecer_detalle_ubicaciones(
    detalle: pd.DataFrame,
    maestro: pd.DataFrame | None,
    ubicaciones_picking: set[str] | None = None,
) -> pd.DataFrame:
    """
    Clasifica ubicaciones respetando esta prioridad:

    1. Ubicación presente en la configuración de Picking.
    2. Clasificación explícita del maestro de ubicaciones.
    3. Prefijo de la ubicación como respaldo.

    Esto evita que posiciones con prefijo ALM/NAC/IMP configuradas
    operativamente como Picking se analicen como Almacén.
    """

    salida = detalle.copy()
    salida["Ubicacion"] = (
        salida["Ubicacion"]
        .map(normalizar_ubicacion)
    )

    preparado = preparar_maestro_ubicaciones_inventario(
        maestro
        if maestro is not None
        else pd.DataFrame()
    )

    if not preparado.empty:
        salida = salida.merge(
            preparado,
            on="Ubicacion",
            how="left",
        )

    for col in [
        "TipoUbicacion",
        "AreaUbicacion",
        "PasilloUbicacion",
    ]:
        if col not in salida.columns:
            salida[col] = ""

    fallback = salida["Ubicacion"].map(
        clasificar_por_codigo
    )

    salida["TipoUbicacion"] = (
        salida["TipoUbicacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    salida["TipoUbicacion"] = (
        salida["TipoUbicacion"]
        .where(
            salida["TipoUbicacion"].ne(""),
            fallback,
        )
    )

    picking_normalizadas = {
        normalizar_ubicacion(ubicacion)
        for ubicacion in (
            ubicaciones_picking or set()
        )
        if normalizar_ubicacion(ubicacion)
    }

    if picking_normalizadas:
        es_picking_configurado = (
            salida["Ubicacion"].isin(
                picking_normalizadas
            )
        )

        salida.loc[
            es_picking_configurado,
            "TipoUbicacion",
        ] = "Picking"

        salida["OrigenClasificacionUbicacion"] = (
            "Prefijo / Maestro"
        )
        salida.loc[
            es_picking_configurado,
            "OrigenClasificacionUbicacion",
        ] = "Configuración Picking"
    else:
        salida["OrigenClasificacionUbicacion"] = (
            "Prefijo / Maestro"
        )

    return salida
