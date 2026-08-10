from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd


# ==========================================================
# UTILIDADES
# ==========================================================


def _clave(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", texto.lower().strip())


def _buscar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or len(df.columns) == 0:
        return None
    mapa = {_clave(c): c for c in df.columns}
    for candidato in candidatos:
        encontrada = mapa.get(_clave(candidato))
        if encontrada is not None:
            return encontrada
    return None


def _texto(serie: pd.Series) -> pd.Series:
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


def _serie(df: pd.DataFrame, candidatos: list[str], default="") -> pd.Series:
    columna = _buscar_columna(df, candidatos)
    if columna is None:
        return pd.Series(default, index=df.index)
    return df[columna]


# ==========================================================
# PREPARACIÓN DE FUENTES
# ==========================================================


def preparar_configuracion_picking(df_max_min: pd.DataFrame) -> pd.DataFrame:
    """Normaliza Max & Min sin depender del parser general de Stock."""
    columnas_salida = [
        "ArticuloCodigo",
        "UbicacionPicking",
        "AreaPicking",
        "StockMinimoUbicacion",
        "StockMaximoUbicacion",
        "StockPickingUbicacion",
        "CapacidadLibreUbicacion",
    ]
    if df_max_min is None or df_max_min.empty:
        return pd.DataFrame(columns=columnas_salida)

    origen = df_max_min.copy()
    tabla = pd.DataFrame(index=origen.index)
    tabla["ArticuloCodigo"] = _texto(
        _serie(origen, ["Articulo", "ArticuloCodigo", "CodigoArticulo", "codigo_articulo"])
    )
    tabla["UbicacionPicking"] = _texto(
        _serie(origen, ["Ubicacion", "Ubicación", "UbicacionPicking"])
    )
    tabla["AreaPicking"] = _texto(_serie(origen, ["Area", "Área", "AreaPicking"]))
    tabla["StockMinimoUbicacion"] = _numero(
        _serie(origen, ["Unidades Minimas", "Unidades Mínimas", "stock_minimo", "StockMinimo"])
    )
    tabla["StockMaximoUbicacion"] = _numero(
        _serie(origen, ["Unidades Maximas", "Unidades Máximas", "stock_maximo", "StockMaximo"])
    )
    tabla["StockPickingUbicacion"] = _numero(
        _serie(origen, ["Unidades en ubicacion", "Unidades en ubicación", "unidades_disponibles", "StockPickingActual"])
    )
    tabla = tabla.loc[tabla["ArticuloCodigo"].ne("")].copy()
    tabla["CapacidadLibreUbicacion"] = (
        tabla["StockMaximoUbicacion"] - tabla["StockPickingUbicacion"]
    ).clip(lower=0)
    return tabla[columnas_salida].reset_index(drop=True)


def preparar_stock_pallets(df_stock: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "AreaOrigen",
        "UbicacionOrigen",
        "ContenedorNumero",
        "Cantidad",
    ]
    if df_stock is None or df_stock.empty:
        return pd.DataFrame(columns=columnas_salida)

    origen = df_stock.copy()
    tabla = pd.DataFrame(index=origen.index)
    tabla["ArticuloCodigo"] = _texto(
        _serie(origen, ["ArticuloCodigo", "CodigoArticulo", "codigo_articulo", "Articulo"])
    )
    tabla["ArticuloDescripcion"] = (
        _serie(origen, ["ArticuloDescripcion", "Descripcion", "Descripción"])
        .fillna("")
        .astype(str)
        .str.strip()
    )
    tabla["AreaOrigen"] = _texto(
        _serie(origen, ["AreaDescripcion", "Area", "Área"])
    )
    tabla["UbicacionOrigen"] = _texto(
        _serie(origen, ["Ubicacion", "Ubicación", "CodigoUbicacion"])
    )
    tabla["ContenedorNumero"] = _texto(
        _serie(origen, ["ContenedorNumero", "Contenedor", "NumeroContenedor"])
    )
    tabla["Cantidad"] = _numero(
        _serie(origen, ["Cantidad", "UnidadesSueltas", "Unidades", "Stock"])
    )
    tabla = tabla.loc[
        tabla["ArticuloCodigo"].ne("")
        & tabla["ContenedorNumero"].ne("")
        & tabla["Cantidad"].gt(0)
    ].copy()
    return tabla[columnas_salida].reset_index(drop=True)


def obtener_ubicaciones_picking(
    tabla_maestro_ubicaciones: pd.DataFrame,
    configuracion_picking: pd.DataFrame,
) -> set[str]:
    ubicaciones: set[str] = set()

    if configuracion_picking is not None and not configuracion_picking.empty:
        ubicaciones.update(
            configuracion_picking["UbicacionPicking"].dropna().astype(str).str.upper().str.strip()
        )

    if tabla_maestro_ubicaciones is not None and not tabla_maestro_ubicaciones.empty:
        maestro = tabla_maestro_ubicaciones.copy()
        col_tipo = _buscar_columna(maestro, ["Tipo"])
        col_clave = _buscar_columna(
            maestro,
            ["ClaveUbicacion", "Ubicacion", "Ubicación", "CodigoUbicacion"],
        )
        if col_tipo is not None and col_clave is not None:
            mascara = maestro[col_tipo].fillna("").astype(str).str.upper().str.contains("PICKING", na=False)
            ubicaciones.update(
                maestro.loc[mascara, col_clave].fillna("").astype(str).str.upper().str.strip()
            )
    return {u for u in ubicaciones if u}


# ==========================================================
# MOTOR DE CONSOLIDACIÓN
# ==========================================================


def _plan_destinos_picking(
    config_sku: pd.DataFrame,
    unidades: float,
) -> tuple[str, str]:
    if config_sku.empty or unidades <= 0:
        return "", ""

    destino = config_sku.loc[config_sku["CapacidadLibreUbicacion"].gt(0)].copy()
    if destino.empty:
        return "", ""

    destino = destino.sort_values(
        ["CapacidadLibreUbicacion", "StockPickingUbicacion"],
        ascending=[False, True],
    )

    restante = float(unidades)
    partes: list[str] = []
    primera = ""
    for _, fila in destino.iterrows():
        if restante <= 0:
            break
        capacidad = float(fila["CapacidadLibreUbicacion"] or 0)
        if capacidad <= 0:
            continue
        mover = min(restante, capacidad)
        ubicacion = str(fila["UbicacionPicking"] or "").strip()
        if not primera:
            primera = ubicacion
        partes.append(f"{ubicacion} (+{mover:,.0f})")
        restante -= mover

    return primera, " | ".join(partes)


def _estandar_por_sku(pallets: pd.DataFrame, config: pd.DataFrame) -> dict[str, dict]:
    """
    Define el estándar físico por pallet.

    Regla principal:
    - Si Max & Min tiene mínimo > 0, ese mínimo representa las unidades de UN pallet físico.
      Ej.: mínimo 150 / máximo 300 => pallet = 150 u. y capacidad = 2 pallets.
      Ej.: mínimo 200 / máximo 600 => pallet = 200 u. y capacidad = 3 pallets.
    - Si no existe mínimo válido, se usa como respaldo la distribución real de pallets
      observados fuera de Picking.
    """
    estandares: dict[str, dict] = {}
    codigos = set(pallets["ArticuloCodigo"].dropna().astype(str))
    if config is not None and not config.empty:
        codigos.update(config["ArticuloCodigo"].dropna().astype(str))

    for codigo in codigos:
        cfg = config.loc[config["ArticuloCodigo"].eq(codigo)].copy() if config is not None else pd.DataFrame()

        minimo_config = 0.0
        pallets_fisicos_picking = 0.0
        if not cfg.empty:
            minimos = pd.to_numeric(cfg["StockMinimoUbicacion"], errors="coerce").fillna(0)
            maximos = pd.to_numeric(cfg["StockMaximoUbicacion"], errors="coerce").fillna(0)
            minimos_validos = minimos.loc[minimos.gt(0)]

            if not minimos_validos.empty:
                # Si hay varias ubicaciones, normalmente comparten el mismo estándar.
                # La mediana evita que una configuración excepcional distorsione el SKU.
                minimo_config = float(minimos_validos.median())
                ratios = maximos.div(minimos.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
                pallets_fisicos_picking = float(ratios.fillna(0).clip(lower=0).sum())

        grupo = pallets.loc[pallets["ArticuloCodigo"].eq(codigo)]
        cantidades = pd.to_numeric(grupo.get("CantidadPallet", pd.Series(dtype=float)), errors="coerce").dropna()
        cantidades = cantidades.loc[cantidades.gt(0)]
        if len(cantidades) >= 3:
            referencia_fisica = float(cantidades.quantile(0.90))
        elif not cantidades.empty:
            referencia_fisica = float(cantidades.max())
        else:
            referencia_fisica = 0.0

        if minimo_config > 0:
            estandar = minimo_config
            fuente = "Mínimo Picking"
        else:
            estandar = max(referencia_fisica, 1.0)
            fuente = "Pallets físicos observados"

        estandares[codigo] = {
            "estandar": estandar,
            "fuente": fuente,
            "pallets_fisicos_picking": pallets_fisicos_picking,
        }

    return estandares


def construir_pallets_parciales(
    tabla_stock_detallado: pd.DataFrame,
    tabla_max_min: pd.DataFrame,
    tabla_maestro_ubicaciones: pd.DataFrame,
    umbral_parcial_pct: float = 80.0,
    areas_incluidas: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Construye una fila por contenedor físico fuera de Picking y asigna una
    acción operativa. No modifica ninguna fuente ni depende de Recepción.
    """
    stock = preparar_stock_pallets(tabla_stock_detallado)
    config = preparar_configuracion_picking(tabla_max_min)

    columnas_salida = [
        "Prioridad",
        "AccionSugerida",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "ContenedorOrigen",
        "UbicacionOrigen",
        "AreaOrigen",
        "CantidadPallet",
        "EstandarPalletEstimado",
        "FuenteEstandarPallet",
        "PalletsFisicosPicking",
        "PorcentajePallet",
        "StockPickingActual",
        "StockMinimoPicking",
        "StockMaximoPicking",
        "FaltanteMinimo",
        "CapacidadHastaMaximo",
        "UnidadesAPicking",
        "UnidadesAUnificar",
        "UbicacionPickingDestino",
        "PlanDestinoPicking",
        "ContenedorDestinoUnificacion",
        "UbicacionDestinoUnificacion",
        "PalletLiberable",
        "EsPalletMixto",
        "ArticulosEnPallet",
        "Motivo",
    ]

    if stock.empty:
        return pd.DataFrame(columns=columnas_salida), {
            "pallets_analizados": 0,
            "pallets_candidatos": 0,
            "pallets_liberables": 0,
        }

    ubicaciones_picking = obtener_ubicaciones_picking(tabla_maestro_ubicaciones, config)
    stock["EsPicking"] = stock["UbicacionOrigen"].isin(ubicaciones_picking)

    # El origen del análisis es exclusivamente stock físico fuera del Picking.
    almacen = stock.loc[~stock["EsPicking"]].copy()
    almacen = almacen.loc[
        ~almacen["AreaOrigen"].str.contains(
            r"RECEPC|CALIDAD|LABORATOR|NO APTO",
            regex=True,
            na=False,
        )
    ].copy()

    if areas_incluidas:
        areas_norm = {str(a).strip().upper() for a in areas_incluidas if str(a).strip()}
        almacen = almacen.loc[almacen["AreaOrigen"].isin(areas_norm)].copy()

    if almacen.empty:
        return pd.DataFrame(columns=columnas_salida), {
            "pallets_analizados": 0,
            "pallets_candidatos": 0,
            "pallets_liberables": 0,
        }

    # Diagnóstico del contenedor completo antes de separar por artículo.
    detalle_contenedor = (
        almacen.groupby("ContenedorNumero", as_index=False)
        .agg(
            CantidadTotalContenedor=("Cantidad", "sum"),
            ArticulosEnPallet=("ArticuloCodigo", "nunique"),
            ListaArticulos=("ArticuloCodigo", lambda s: " | ".join(sorted(set(s)))),
        )
    )

    # Una fila operativa por Contenedor + Artículo + ubicación.
    pallets = (
        almacen.groupby(
            ["ContenedorNumero", "ArticuloCodigo", "UbicacionOrigen", "AreaOrigen"],
            as_index=False,
        )
        .agg(
            CantidadPallet=("Cantidad", "sum"),
            ArticuloDescripcion=("ArticuloDescripcion", lambda s: next((x for x in s if str(x).strip()), "")),
        )
        .merge(detalle_contenedor, on="ContenedorNumero", how="left", validate="many_to_one")
    )
    pallets["EsPalletMixto"] = pallets["ArticulosEnPallet"].gt(1)

    # Para los mixtos mostramos una sola fila por contenedor para evitar duplicar la acción.
    mixtos = pallets.loc[pallets["EsPalletMixto"]].copy()
    if not mixtos.empty:
        mixtos = (
            mixtos.sort_values("CantidadPallet", ascending=False)
            .drop_duplicates("ContenedorNumero", keep="first")
            .copy()
        )
        mixtos["ArticuloCodigo"] = mixtos["ListaArticulos"]
        mixtos["ArticuloDescripcion"] = "Pallet con múltiples artículos"
        mixtos["CantidadPallet"] = mixtos["CantidadTotalContenedor"]

    simples = pallets.loc[~pallets["EsPalletMixto"]].copy()
    estandares = _estandar_por_sku(simples, config)

    # Resumen de la configuración por SKU.
    if config.empty:
        cfg_sku = pd.DataFrame(columns=[
            "ArticuloCodigo", "StockMinimoPicking", "StockMaximoPicking", "StockPickingActual"
        ])
    else:
        cfg_sku = (
            config.groupby("ArticuloCodigo", as_index=False)
            .agg(
                StockMinimoPicking=("StockMinimoUbicacion", "sum"),
                StockMaximoPicking=("StockMaximoUbicacion", "sum"),
                StockPickingActual=("StockPickingUbicacion", "sum"),
            )
        )

    simples = simples.merge(cfg_sku, on="ArticuloCodigo", how="left", validate="many_to_one")
    for c in ["StockMinimoPicking", "StockMaximoPicking", "StockPickingActual"]:
        simples[c] = pd.to_numeric(simples[c], errors="coerce").fillna(0)

    simples["EstandarPalletEstimado"] = simples["ArticuloCodigo"].map(
        lambda codigo: estandares.get(codigo, {}).get("estandar", 1.0)
    ).fillna(1.0)
    simples["FuenteEstandarPallet"] = simples["ArticuloCodigo"].map(
        lambda codigo: estandares.get(codigo, {}).get("fuente", "")
    ).fillna("")
    simples["PalletsFisicosPicking"] = simples["ArticuloCodigo"].map(
        lambda codigo: estandares.get(codigo, {}).get("pallets_fisicos_picking", 0.0)
    ).fillna(0.0)
    simples["PorcentajePallet"] = (
        simples["CantidadPallet"] / simples["EstandarPalletEstimado"].replace(0, np.nan) * 100
    ).fillna(0).clip(lower=0)
    simples["FaltanteMinimo"] = (
        simples["StockMinimoPicking"] - simples["StockPickingActual"]
    ).clip(lower=0)
    simples["CapacidadHastaMaximo"] = (
        simples["StockMaximoPicking"] - simples["StockPickingActual"]
    ).clip(lower=0)

    # Índice de pallets simples del mismo SKU para proponer unificación real.
    grupos = {
        codigo: grupo.copy()
        for codigo, grupo in simples.groupby("ArticuloCodigo")
    }

    registros: list[dict] = []

    for _, fila in simples.iterrows():
        codigo = str(fila["ArticuloCodigo"])
        cantidad = float(fila["CantidadPallet"] or 0)
        estandar = float(fila["EstandarPalletEstimado"] or 1)
        pct = float(fila["PorcentajePallet"] or 0)
        stock_pick = float(fila["StockPickingActual"] or 0)
        minimo = float(fila["StockMinimoPicking"] or 0)
        maximo = float(fila["StockMaximoPicking"] or 0)
        faltante_min = float(fila["FaltanteMinimo"] or 0)
        libre_max = float(fila["CapacidadHastaMaximo"] or 0)
        tiene_config = maximo > 0

        otros = grupos[codigo].loc[
            grupos[codigo]["ContenedorNumero"].ne(fila["ContenedorNumero"])
        ].copy()
        destino_contenedor = ""
        destino_ubicacion = ""
        capacidad_destino = 0.0
        puede_unificar_completo = False

        if not otros.empty:
            otros["CapacidadDestino"] = (estandar - otros["CantidadPallet"]).clip(lower=0)
            completos = otros.loc[otros["CapacidadDestino"].ge(cantidad)].copy()
            if not completos.empty:
                # Elegir el pallet más lleno que todavía absorbe todo el origen.
                destino = completos.sort_values("CantidadPallet", ascending=False).iloc[0]
                puede_unificar_completo = True
            else:
                destino = otros.sort_values("CapacidadDestino", ascending=False).iloc[0]
            destino_contenedor = str(destino["ContenedorNumero"])
            destino_ubicacion = str(destino["UbicacionOrigen"])
            capacidad_destino = float(destino["CapacidadDestino"] or 0)

        unidades_picking = min(cantidad, libre_max) if tiene_config else 0.0
        remanente = max(cantidad - unidades_picking, 0.0)
        ubic_pick, plan_pick = _plan_destinos_picking(
            config.loc[config["ArticuloCodigo"].eq(codigo)],
            unidades_picking,
        )

        parcial = pct < float(umbral_parcial_pct)
        liberable = False
        prioridad = 9
        accion = "✅ Mantener en almacén"
        motivo = "El pallet no presenta una oportunidad clara de reducción con las reglas actuales."
        unidades_unificar = 0.0

        if not tiene_config:
            prioridad = 8
            accion = "⚠️ Sin configuración de Picking"
            motivo = "El artículo no tiene máximo de Picking identificable en Max & Min."
        elif faltante_min > 0 and cantidad <= libre_max:
            prioridad = 1
            accion = "🔴 Llevar a Picking - prioridad"
            motivo = "Picking está debajo del mínimo y el pallet completo entra sin superar el máximo."
            liberable = True
        elif faltante_min > 0 and libre_max > 0:
            prioridad = 2
            if remanente > 0 and destino_contenedor:
                accion = "🟠 Completar Picking + consolidar remanente"
                unidades_unificar = min(remanente, capacidad_destino) if capacidad_destino > 0 else remanente
                liberable = unidades_unificar >= remanente - 1e-9
                motivo = "Picking está debajo del mínimo; el excedente se direcciona a otro pallet del mismo artículo."
            else:
                accion = "🟠 Completar Picking parcial"
                motivo = "Picking está debajo del mínimo, pero el pallet excede la capacidad disponible y no hay consolidación completa posible."
        elif libre_max > 0 and cantidad <= libre_max:
            prioridad = 3
            accion = "🟢 Llevar a Picking"
            motivo = "El pallet completo puede absorberse en Picking sin superar el máximo."
            liberable = True
        elif libre_max > 0 and parcial:
            prioridad = 4
            if remanente > 0 and destino_contenedor:
                accion = "🟡 Completar Picking + consolidar remanente"
                unidades_unificar = min(remanente, capacidad_destino) if capacidad_destino > 0 else remanente
                liberable = unidades_unificar >= remanente - 1e-9
                motivo = "Parte del pallet puede ir a Picking y el resto tiene un pallet destino sugerido."
            else:
                accion = "🟡 Completar Picking parcial"
                motivo = "Existe capacidad en Picking, aunque no alcanza para liberar por completo el pallet."
        elif parcial and puede_unificar_completo and destino_contenedor:
            prioridad = 5
            accion = "🔗 Unificar con otro pallet"
            unidades_unificar = cantidad
            liberable = True
            motivo = "Picking no requiere reposición inmediata y otro pallet del mismo artículo puede absorber todo el remanente."
        elif parcial and destino_contenedor and capacidad_destino > 0:
            prioridad = 6
            accion = "🔗 Consolidar parcialmente"
            unidades_unificar = min(cantidad, capacidad_destino)
            motivo = "Hay otro pallet del mismo artículo con capacidad, aunque no alcanza para liberar completamente el origen."
        elif parcial:
            prioridad = 7
            accion = "⏸️ Pallet parcial sin destino"
            motivo = "El pallet es parcial, pero Picking está completo y no existe otro pallet con capacidad suficiente."

        # Para la vista principal solo necesitamos candidatos parciales o acciones que liberen pallet.
        es_candidato = parcial or liberable or faltante_min > 0 or libre_max > 0 and cantidad <= libre_max
        if not es_candidato:
            continue

        registros.append({
            "Prioridad": prioridad,
            "AccionSugerida": accion,
            "ArticuloCodigo": codigo,
            "ArticuloDescripcion": fila["ArticuloDescripcion"],
            "ContenedorOrigen": fila["ContenedorNumero"],
            "UbicacionOrigen": fila["UbicacionOrigen"],
            "AreaOrigen": fila["AreaOrigen"],
            "CantidadPallet": cantidad,
            "EstandarPalletEstimado": estandar,
            "FuenteEstandarPallet": fila.get("FuenteEstandarPallet", ""),
            "PalletsFisicosPicking": float(fila.get("PalletsFisicosPicking", 0) or 0),
            "PorcentajePallet": round(pct, 1),
            "StockPickingActual": stock_pick,
            "StockMinimoPicking": minimo,
            "StockMaximoPicking": maximo,
            "FaltanteMinimo": faltante_min,
            "CapacidadHastaMaximo": libre_max,
            "UnidadesAPicking": unidades_picking,
            "UnidadesAUnificar": unidades_unificar,
            "UbicacionPickingDestino": ubic_pick,
            "PlanDestinoPicking": plan_pick,
            "ContenedorDestinoUnificacion": destino_contenedor,
            "UbicacionDestinoUnificacion": destino_ubicacion,
            "PalletLiberable": bool(liberable),
            "EsPalletMixto": False,
            "ArticulosEnPallet": 1,
            "Motivo": motivo,
        })

    # Pallets mixtos: siempre se muestran como revisión operativa.
    for _, fila in mixtos.iterrows():
        registros.append({
            "Prioridad": 0,
            "AccionSugerida": "⚠️ Revisar / separar pallet mixto",
            "ArticuloCodigo": fila["ArticuloCodigo"],
            "ArticuloDescripcion": fila["ArticuloDescripcion"],
            "ContenedorOrigen": fila["ContenedorNumero"],
            "UbicacionOrigen": fila["UbicacionOrigen"],
            "AreaOrigen": fila["AreaOrigen"],
            "CantidadPallet": float(fila["CantidadPallet"] or 0),
            "EstandarPalletEstimado": 0.0,
            "FuenteEstandarPallet": "",
            "PalletsFisicosPicking": 0.0,
            "PorcentajePallet": 0.0,
            "StockPickingActual": 0.0,
            "StockMinimoPicking": 0.0,
            "StockMaximoPicking": 0.0,
            "FaltanteMinimo": 0.0,
            "CapacidadHastaMaximo": 0.0,
            "UnidadesAPicking": 0.0,
            "UnidadesAUnificar": 0.0,
            "UbicacionPickingDestino": "",
            "PlanDestinoPicking": "",
            "ContenedorDestinoUnificacion": "",
            "UbicacionDestinoUnificacion": "",
            "PalletLiberable": False,
            "EsPalletMixto": True,
            "ArticulosEnPallet": int(fila["ArticulosEnPallet"] or 0),
            "Motivo": "El contenedor contiene más de un código; debe separarse antes de proponer reposición o consolidación.",
        })

    resultado = pd.DataFrame(registros, columns=columnas_salida)
    if not resultado.empty:
        resultado = resultado.sort_values(
            ["Prioridad", "PalletLiberable", "PorcentajePallet", "AreaOrigen", "UbicacionOrigen"],
            ascending=[True, False, True, True, True],
        ).reset_index(drop=True)

    metadata = {
        "pallets_analizados": int(almacen["ContenedorNumero"].nunique()),
        "pallets_candidatos": int(resultado["ContenedorOrigen"].nunique()) if not resultado.empty else 0,
        "pallets_liberables": int(resultado.loc[resultado["PalletLiberable"], "ContenedorOrigen"].nunique()) if not resultado.empty else 0,
        "pallets_mixtos": int(detalle_contenedor["ArticulosEnPallet"].gt(1).sum()),
        "unidades_a_picking": float(resultado["UnidadesAPicking"].sum()) if not resultado.empty else 0.0,
        "unidades_a_unificar": float(resultado["UnidadesAUnificar"].sum()) if not resultado.empty else 0.0,
        "articulos_configurados": int(config["ArticuloCodigo"].nunique()) if not config.empty else 0,
        "ubicaciones_picking": len(ubicaciones_picking),
        "umbral_parcial_pct": float(umbral_parcial_pct),
        "areas_incluidas": list(areas_incluidas or []),
    }
    return resultado, metadata
