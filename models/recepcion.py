from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

try:
    from models.volumetria import construir_tabla_volumetria
except Exception:  # pragma: no cover
    construir_tabla_volumetria = None


# ==========================================================
# UTILIDADES
# ==========================================================

def _clave(texto: object) -> str:
    valor = unicodedata.normalize("NFKD", str(texto))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", valor.lower().strip())


def _columna(df: pd.DataFrame, alias: list[str]) -> str | None:
    mapa = {_clave(c): c for c in df.columns}
    for nombre in alias:
        if _clave(nombre) in mapa:
            return mapa[_clave(nombre)]
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
    tiene_coma = texto.str.contains(",", regex=False)
    texto.loc[tiene_coma] = (
        texto.loc[tiene_coma]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(texto, errors="coerce").fillna(0)


def _texto(df: pd.DataFrame, alias: list[str], default: str = "") -> pd.Series:
    c = _columna(df, alias)
    if c is None:
        return pd.Series(default, index=df.index, dtype="object")
    return df[c].fillna(default).astype(str).str.strip()


def _numerico(df: pd.DataFrame, alias: list[str]) -> pd.Series:
    c = _columna(df, alias)
    if c is None:
        return pd.Series(0.0, index=df.index)
    return _numero(df[c])


def _fecha(df: pd.DataFrame, alias: list[str]) -> pd.Series:
    c = _columna(df, alias)
    if c is None:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    return pd.to_datetime(df[c], errors="coerce", dayfirst=True)


# ==========================================================
# MAESTROS DE ENRIQUECIMIENTO
# ==========================================================

def _maestro_articulos(df_articulos: pd.DataFrame) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo", "DescripcionMaestro", "Familia", "Familia2",
        "Sectorizacion", "Origen", "Marca", "Tipo",
    ]
    if df_articulos is None or df_articulos.empty:
        return pd.DataFrame(columns=columnas)

    origen = df_articulos.copy()
    salida = pd.DataFrame(index=origen.index)
    salida["ArticuloCodigo"] = _codigo(_texto(origen, [
        "COD_ART", "CodigoArticulo", "ArticuloCodigo", "Codigo", "Código"
    ]))
    salida["DescripcionMaestro"] = _texto(origen, ["DESCRIP", "Descripcion", "Descripción"])
    salida["Familia"] = _texto(origen, ["Familia"])
    salida["Familia2"] = _texto(origen, ["Familia_2", "Familia2"])
    salida["Sectorizacion"] = _texto(origen, ["Sectorizacion", "Sectorización", "Sector"])
    salida["Origen"] = _texto(origen, ["Origen"])
    salida["Marca"] = _texto(origen, ["Marca"])
    salida["Tipo"] = _texto(origen, ["Tipo"])
    return salida.loc[salida["ArticuloCodigo"].ne("")].drop_duplicates("ArticuloCodigo")


def _maestro_volumetria(df_volumetria: pd.DataFrame) -> pd.DataFrame:
    columnas = ["ArticuloCodigo", "PesoKg", "VolumenM3", "AltoMM", "AnchoMM", "ProfundoMM"]
    if df_volumetria is None or df_volumetria.empty:
        return pd.DataFrame(columns=columnas)

    origen = df_volumetria.copy()
    if construir_tabla_volumetria is not None:
        try:
            origen = construir_tabla_volumetria(origen)
        except Exception:
            pass

    salida = pd.DataFrame(index=origen.index)
    salida["ArticuloCodigo"] = _codigo(_texto(origen, [
        "CodigoArticulo", "ArticuloCodigo", "Codigo", "Código", "COD_ART"
    ]))
    salida["PesoKg"] = _numerico(origen, ["PesoKg", "Kg", "Peso", "peso_kg"])
    salida["VolumenM3"] = _numerico(origen, ["VolumenM3", "M3", "Volumen", "volumen_m3"])
    salida["AltoMM"] = _numerico(origen, ["AltoMM", "Alto", "Alt"])
    salida["AnchoMM"] = _numerico(origen, ["AnchoMM", "Ancho", "Anc"])
    salida["ProfundoMM"] = _numerico(origen, ["ProfundoMM", "Profundo", "Prof"])
    return salida.loc[salida["ArticuloCodigo"].ne("")].drop_duplicates("ArticuloCodigo")


def _maestro_max_min(df_max_min: pd.DataFrame) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo", "StockMinimoPicking", "StockMaximoPicking",
        "MaximoPreparar", "UbicacionesPickingConfiguradas",
    ]
    if df_max_min is None or df_max_min.empty:
        return pd.DataFrame(columns=columnas)

    origen = df_max_min.copy()
    tabla = pd.DataFrame(index=origen.index)
    tabla["ArticuloCodigo"] = _codigo(_texto(origen, [
        "codigo_articulo", "CodigoArticulo", "ArticuloCodigo"
    ]))
    tabla["StockMinimoPicking"] = _numerico(origen, ["stock_minimo", "StockMinimo", "Minimo"])
    tabla["StockMaximoPicking"] = _numerico(origen, ["stock_maximo", "StockMaximo", "Maximo"])
    tabla["MaximoPreparar"] = _numerico(origen, [
        "stock_maximo_Preparar", "stock_maximo_preparar", "MaximoPreparar"
    ])
    tabla["UbicacionPicking"] = _texto(origen, ["ubicacion", "Ubicacion", "Ubicación"])
    tabla = tabla.loc[tabla["ArticuloCodigo"].ne("")].copy()

    return (
        tabla.groupby("ArticuloCodigo", as_index=False)
        .agg(
            StockMinimoPicking=("StockMinimoPicking", "sum"),
            StockMaximoPicking=("StockMaximoPicking", "sum"),
            MaximoPreparar=("MaximoPreparar", "sum"),
            UbicacionesPickingConfiguradas=(
                "UbicacionPicking",
                lambda s: s.loc[s.ne("")].nunique(),
            ),
        )
    )


def _enriquecer(
    tabla: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_volumetria: pd.DataFrame,
    df_max_min: pd.DataFrame,
) -> pd.DataFrame:
    resultado = tabla.copy()

    maestro_articulos = _maestro_articulos(df_articulos)
    codigos_maestro = set(
        maestro_articulos["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .loc[lambda serie: serie.ne("")]
        .tolist()
    )

    resultado["ExisteEnMaestroArticulo"] = (
        resultado["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(codigos_maestro)
    )

    resultado = resultado.merge(
        maestro_articulos,
        on="ArticuloCodigo", how="left", validate="many_to_one",
    )
    resultado = resultado.merge(
        _maestro_volumetria(df_volumetria),
        on="ArticuloCodigo", how="left", validate="many_to_one",
    )
    resultado = resultado.merge(
        _maestro_max_min(df_max_min),
        on="ArticuloCodigo", how="left", validate="many_to_one",
    )

    for c in [
        "DescripcionMaestro", "Familia", "Familia2", "Sectorizacion",
        "Origen", "Marca", "Tipo",
    ]:
        if c not in resultado:
            resultado[c] = ""
        resultado[c] = resultado[c].fillna("")

    for c in [
        "PesoKg", "VolumenM3", "AltoMM", "AnchoMM", "ProfundoMM",
        "StockMinimoPicking", "StockMaximoPicking", "MaximoPreparar",
        "UbicacionesPickingConfiguradas",
    ]:
        if c not in resultado:
            resultado[c] = 0
        resultado[c] = pd.to_numeric(resultado[c], errors="coerce").fillna(0)

    if "ArticuloDescripcion" in resultado:
        resultado["ArticuloDescripcion"] = (
            resultado["ArticuloDescripcion"].fillna("").astype(str).str.strip()
        )
        resultado["ArticuloDescripcion"] = resultado["ArticuloDescripcion"].where(
            resultado["ArticuloDescripcion"].ne(""),
            resultado["DescripcionMaestro"],
        )
    else:
        resultado["ArticuloDescripcion"] = resultado["DescripcionMaestro"]

    resultado["ExisteEnMaestroArticulo"] = (
        resultado["ExisteEnMaestroArticulo"]
        .fillna(False)
        .astype(bool)
    )
    resultado["EsProductoNuevo"] = (
        ~resultado["ExisteEnMaestroArticulo"]
    )

    return resultado



# ==========================================================
# DISPONIBILIDAD DIGIP
# ==========================================================

def construir_disponible_por_articulo(
    df_disponible: pd.DataFrame | None,
) -> pd.DataFrame:
    """Construye una fila por artículo con el disponible actual de DIGIP."""
    columnas = ["ArticuloCodigo", "StockDisponibleActual"]
    if df_disponible is None or df_disponible.empty:
        return pd.DataFrame(columns=columnas)

    origen = df_disponible.copy()
    codigo = _columna(origen, [
        "CodigoArticulo", "ArticuloCodigo", "codigo_articulo",
        "Código artículo", "Codigo", "Código", "Articulo", "Artículo",
        "CodArticulo",
    ])
    disponible = _columna(origen, [
        "Disponible", "StockDisponible", "Stock Disponible",
        "UnidadesDisponibles", "Unidades Disponibles",
        "unidades_disponibles", "CantidadDisponible",
    ])

    if codigo is None or disponible is None:
        return pd.DataFrame(columns=columnas)

    tabla = pd.DataFrame({
        "ArticuloCodigo": _codigo(origen[codigo]),
        "StockDisponibleActual": _numero(origen[disponible]),
    })
    tabla = tabla.loc[tabla["ArticuloCodigo"].ne("")].copy()

    return (
        tabla.groupby("ArticuloCodigo", as_index=False)
        .agg(StockDisponibleActual=("StockDisponibleActual", "sum"))
    )


# ==========================================================
# PENDIENTES DE OC
# ==========================================================

def construir_pendientes_oc(
    df_oc: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_volumetria: pd.DataFrame,
    df_max_min: pd.DataFrame,
    df_disponible: pd.DataFrame | None = None,
    dias_aduana: int = 7,
) -> pd.DataFrame:
    columnas_salida = [
        "OrdenCompra", "Proforma", "EstadoOC", "ArticuloCodigo",
        "ArticuloDescripcion", "Familia", "Sectorizacion", "Origen",
        "CantidadPendiente", "FechaPuertoBuenosAires", "FechaIngresoEstimada",
        "FechaIngresoInformada", "DiasHastaIngreso", "EstadoIngreso",
        "PesoUnitarioKg", "PesoTotalKg", "VolumenUnitarioM3", "VolumenTotalM3",
        "StockMinimoPicking", "StockMaximoPicking", "MaximoPreparar",
        "StockDisponibleActual", "PorcentajeSobreStockActual",
        "PorcentajeSobreTotal", "SemaforoIngreso", "AccionRecomendada",
        "ExisteEnMaestroArticulo", "EsProductoNuevo",
        "ResuelveSinStock", "AlertaIngreso", "PrioridadIngreso",
    ]
    if df_oc is None or df_oc.empty:
        return pd.DataFrame(columns=columnas_salida)

    origen = df_oc.copy()
    tabla = pd.DataFrame(index=origen.index)
    tabla["OrdenCompra"] = _codigo(_texto(origen, ["nro_com", "OC", "OrdenCompra"]))
    tabla["ArticuloCodigo"] = _codigo(_texto(origen, ["cod_art", "ArticuloCodigo", "CodigoArticulo"]))
    tabla["ArticuloDescripcion"] = _texto(origen, ["descrip", "Descripcion", "Artículo"])
    tabla["CantidadPendiente"] = _numerico(origen, ["Cantidad", "CantidadPendiente", "can_art"])
    tabla["Proforma"] = _texto(origen, ["Proforma"])
    tabla["EstadoOC"] = _texto(origen, ["Estado", "EstadoOC"]).str.upper()
    tabla["FechaPuertoBuenosAires"] = _fecha(origen, ["Puerto Bs.As.", "Puerto Bs As", "FechaPuerto"])
    tabla["FechaIngresoInformada"] = _fecha(origen, ["Ingreso", "FechaIngreso"])
    tabla["FechaIngresoEstimada"] = (
        tabla["FechaPuertoBuenosAires"]
        + pd.Timedelta(days=int(dias_aduana))
    )

    tabla = tabla.loc[
        tabla["OrdenCompra"].ne("")
        & tabla["ArticuloCodigo"].ne("")
        & tabla["CantidadPendiente"].gt(0)
        # Una fecha de ingreso informada indica que la línea ya fue recibida.
        & tabla["FechaIngresoInformada"].isna()
    ].copy()

    # SKU operativo ajeno al depósito. Se excluye desde el modelo para que
    # no impacte en indicadores, gráficos, filtros ni tablas.
    tabla = tabla.loc[
        ~tabla["ArticuloCodigo"].str.upper().eq("MAQUINA")
    ].copy()

    claves = [
        "OrdenCompra", "Proforma", "EstadoOC", "ArticuloCodigo",
        "ArticuloDescripcion", "FechaPuertoBuenosAires", "FechaIngresoEstimada",
        "FechaIngresoInformada",
    ]
    tabla = (
        tabla.groupby(claves, as_index=False, dropna=False)
        .agg(CantidadPendiente=("CantidadPendiente", "sum"))
    )

    tabla = _enriquecer(tabla, df_articulos, df_volumetria, df_max_min)

    disponible_articulo = construir_disponible_por_articulo(df_disponible)
    tabla = tabla.merge(
        disponible_articulo,
        on="ArticuloCodigo",
        how="left",
        validate="many_to_one",
    )
    tabla["StockDisponibleActual"] = pd.to_numeric(
        tabla.get("StockDisponibleActual", 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    tabla["PorcentajeSobreStockActual"] = (
        tabla["CantidadPendiente"]
        / tabla["StockDisponibleActual"].replace(0, pd.NA)
        * 100
    ).fillna(0).round(1)

    tabla["PorcentajeSobreTotal"] = (
        tabla["CantidadPendiente"]
        / (tabla["CantidadPendiente"] + tabla["StockDisponibleActual"]).replace(0, pd.NA)
        * 100
    ).fillna(0).round(1)

    def clasificar_impacto(fila: pd.Series) -> tuple[str, str]:
        stock = float(fila["StockDisponibleActual"] or 0)
        porcentaje = float(fila["PorcentajeSobreStockActual"] or 0)
        if stock <= 0:
            return "Sin stock", "Prioridad máxima"
        if porcentaje >= 100:
            return "Crítico", "Revisar capacidad urgente"
        if porcentaje >= 50:
            return "Alto", "Planificar ubicación"
        if porcentaje >= 25:
            return "Medio", "Ingreso controlado"
        return "Bajo", "Sin impacto"

    clasificaciones = tabla.apply(clasificar_impacto, axis=1)
    tabla["SemaforoIngreso"] = [valor[0] for valor in clasificaciones]
    tabla["AccionRecomendada"] = [valor[1] for valor in clasificaciones]

    tabla["EsProductoNuevo"] = (
        tabla.get(
            "EsProductoNuevo",
            pd.Series(False, index=tabla.index),
        )
        .fillna(False)
        .astype(bool)
    )
    tabla["ExisteEnMaestroArticulo"] = (
        ~tabla["EsProductoNuevo"]
    )
    tabla["ResuelveSinStock"] = (
        tabla["StockDisponibleActual"].le(0)
        & tabla["CantidadPendiente"].gt(0)
        & ~tabla["EsProductoNuevo"]
    )

    def clasificar_alerta_ingreso(fila: pd.Series) -> tuple[str, str]:
        if bool(fila["ResuelveSinStock"]):
            return "🔴 Resuelve sin stock", "P1 - Urgente"
        if bool(fila["EsProductoNuevo"]):
            return "🆕 Producto nuevo", "P2 - Alta"
        if str(fila["SemaforoIngreso"]) == "Crítico":
            return "🟠 Impacto crítico", "P3 - Media alta"
        if str(fila["SemaforoIngreso"]) == "Alto":
            return "🟡 Impacto alto", "P4 - Media"
        return "⚪ Normal", "P5 - Normal"

    alertas = tabla.apply(
        clasificar_alerta_ingreso,
        axis=1,
    )
    tabla["AlertaIngreso"] = [
        valor[0] for valor in alertas
    ]
    tabla["PrioridadIngreso"] = [
        valor[1] for valor in alertas
    ]

    hoy = pd.Timestamp(date.today())
    tabla["DiasHastaIngreso"] = (
        tabla["FechaIngresoEstimada"].dt.normalize() - hoy
    ).dt.days

    def estado_ingreso(dias: object, fecha: object) -> str:
        if pd.isna(fecha):
            return "Sin fecha de puerto"
        if pd.isna(dias):
            return "Sin estimación"
        dias = int(dias)
        if dias < 0:
            return "Atrasado"
        if dias <= 7:
            return "Esta semana"
        if dias <= 14:
            return "Próxima semana"
        return "Futuro"

    tabla["EstadoIngreso"] = [
        estado_ingreso(d, f)
        for d, f in zip(tabla["DiasHastaIngreso"], tabla["FechaIngresoEstimada"])
    ]
    tabla["PesoUnitarioKg"] = tabla["PesoKg"]
    tabla["PesoTotalKg"] = tabla["CantidadPendiente"] * tabla["PesoUnitarioKg"]
    tabla["VolumenUnitarioM3"] = tabla["VolumenM3"]
    tabla["VolumenTotalM3"] = tabla["CantidadPendiente"] * tabla["VolumenUnitarioM3"]

    for c in ["CantidadPendiente", "PesoTotalKg", "VolumenTotalM3"]:
        tabla[c] = pd.to_numeric(tabla[c], errors="coerce").fillna(0)
    tabla["PesoTotalKg"] = tabla["PesoTotalKg"].round(2)
    tabla["VolumenTotalM3"] = tabla["VolumenTotalM3"].round(3)

    for c in columnas_salida:
        if c not in tabla:
            tabla[c] = pd.NA

    orden_prioridad = {
        "P1 - Urgente": 0,
        "P2 - Alta": 1,
        "P3 - Media alta": 2,
        "P4 - Media": 3,
        "P5 - Normal": 4,
    }
    tabla["_OrdenPrioridad"] = (
        tabla["PrioridadIngreso"]
        .map(orden_prioridad)
        .fillna(5)
    )
    tabla = tabla.sort_values(
        ["_OrdenPrioridad", "FechaIngresoEstimada", "OrdenCompra", "ArticuloCodigo"],
        na_position="last",
    ).drop(columns="_OrdenPrioridad")

    return tabla[columnas_salida].reset_index(drop=True)


# ==========================================================
# STOCK EN RECEPCIÓN AGRUPADO
# ==========================================================

def construir_recepcion_agrupada(
    df_recepcion: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_volumetria: pd.DataFrame,
    df_max_min: pd.DataFrame,
    df_disponible: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columnas_salida = [
        "ArticuloCodigo", "ArticuloDescripcion", "Familia", "Sectorizacion",
        "Origen", "UnidadesRecepcion", "Contenedores", "Ubicaciones", "Lotes",
        "VencimientoMasProximo", "DiasAlVencimiento", "PesoUnitarioKg",
        "PesoTotalKg", "VolumenUnitarioM3", "VolumenTotalM3",
        "StockMinimoPicking", "StockMaximoPicking", "MaximoPreparar",
        "CoberturaMaximoPickingPorcentaje", "EstadoAbastecimientoPicking",
        "ExisteEnMaestroArticulo", "EsProductoNuevo",
        "StockDisponibleActual", "ResuelveSinStock",
        "PrioridadGuardado", "MotivoPrioridadGuardado",
    ]
    if df_recepcion is None or df_recepcion.empty:
        return pd.DataFrame(columns=columnas_salida)

    origen = df_recepcion.copy()
    tabla = pd.DataFrame(index=origen.index)
    tabla["ArticuloCodigo"] = _codigo(_texto(origen, [
        "ArticuloCodigo", "CodigoArticulo", "codigo_articulo", "Codigo", "cod_art"
    ]))
    tabla["ArticuloDescripcion"] = _texto(origen, [
        "ArticuloDescripcion", "Descripcion", "descrip"
    ])
    tabla["Cantidad"] = _numerico(origen, ["Cantidad", "UnidadesSueltas", "Stock", "Unidades"])
    tabla["ContenedorNumero"] = _texto(origen, ["ContenedorNumero", "Contenedor", "NumeroContenedor"])
    tabla["Ubicacion"] = _texto(origen, ["Ubicacion", "Ubicación"])
    tabla["Lote"] = _texto(origen, ["Lote"])
    tabla["FechaVencimiento"] = _fecha(origen, ["FechaVencimiento", "Fecha Vencimiento", "Vencimiento"])

    tabla = tabla.loc[tabla["ArticuloCodigo"].ne("") & tabla["Cantidad"].gt(0)].copy()

    descripcion = (
        tabla.loc[tabla["ArticuloDescripcion"].ne("")]
        .drop_duplicates("ArticuloCodigo")
        [["ArticuloCodigo", "ArticuloDescripcion"]]
    )
    resumen = (
        tabla.groupby("ArticuloCodigo", as_index=False)
        .agg(
            UnidadesRecepcion=("Cantidad", "sum"),
            Contenedores=("ContenedorNumero", lambda s: s.loc[s.ne("")].nunique()),
            Ubicaciones=("Ubicacion", lambda s: s.loc[s.ne("")].nunique()),
            Lotes=("Lote", lambda s: s.loc[s.ne("")].nunique()),
            VencimientoMasProximo=("FechaVencimiento", "min"),
        )
        .merge(descripcion, on="ArticuloCodigo", how="left", validate="one_to_one")
    )
    resumen = _enriquecer(
        resumen,
        df_articulos,
        df_volumetria,
        df_max_min,
    )

    disponible_articulo = construir_disponible_por_articulo(
        df_disponible
    )
    resumen = resumen.merge(
        disponible_articulo,
        on="ArticuloCodigo",
        how="left",
        validate="many_to_one",
    )
    resumen["StockDisponibleActual"] = pd.to_numeric(
        resumen.get("StockDisponibleActual", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    resumen["EsProductoNuevo"] = (
        resumen.get(
            "EsProductoNuevo",
            pd.Series(False, index=resumen.index),
        )
        .fillna(False)
        .astype(bool)
    )
    resumen["ExisteEnMaestroArticulo"] = (
        ~resumen["EsProductoNuevo"]
    )
    resumen["ResuelveSinStock"] = (
        resumen["StockDisponibleActual"].le(0)
        & resumen["UnidadesRecepcion"].gt(0)
        & ~resumen["EsProductoNuevo"]
    )

    def prioridad_guardado(fila: pd.Series) -> tuple[str, str]:
        if bool(fila["ResuelveSinStock"]):
            return (
                "🔴 P1 - Urgente",
                "El ingreso resuelve un artículo actualmente sin stock disponible.",
            )
        if bool(fila["EsProductoNuevo"]):
            return (
                "🟣 P2 - Producto nuevo",
                "El artículo no existe todavía en Maestro Artículo.",
            )
        minimo = float(fila.get("StockMinimoPicking", 0) or 0)
        disponible = float(fila.get("StockDisponibleActual", 0) or 0)
        if minimo > 0 and disponible < minimo:
            return (
                "🟠 P3 - Bajo mínimo",
                "El stock disponible está por debajo del mínimo configurado.",
            )
        if str(fila.get("EstadoAbastecimientoPicking", "")) == "Cubre mínimo":
            return (
                "🟡 P4 - Reposición",
                "La recepción permite cubrir el mínimo de Picking.",
            )
        return (
            "⚪ P5 - Normal",
            "Guardado sin alerta operativa prioritaria.",
        )

    prioridades = resumen.apply(
        prioridad_guardado,
        axis=1,
    )
    resumen["PrioridadGuardado"] = [
        valor[0] for valor in prioridades
    ]
    resumen["MotivoPrioridadGuardado"] = [
        valor[1] for valor in prioridades
    ]

    resumen["DiasAlVencimiento"] = (
        resumen["VencimientoMasProximo"].dt.normalize() - pd.Timestamp(date.today())
    ).dt.days
    resumen["PesoUnitarioKg"] = resumen["PesoKg"]
    resumen["PesoTotalKg"] = resumen["UnidadesRecepcion"] * resumen["PesoUnitarioKg"]
    resumen["VolumenUnitarioM3"] = resumen["VolumenM3"]
    resumen["VolumenTotalM3"] = resumen["UnidadesRecepcion"] * resumen["VolumenUnitarioM3"]
    resumen["CoberturaMaximoPickingPorcentaje"] = (
        resumen["UnidadesRecepcion"]
        / resumen["StockMaximoPicking"].replace(0, pd.NA)
        * 100
    ).fillna(0).round(1)

    def estado(row: pd.Series) -> str:
        if row["StockMaximoPicking"] <= 0:
            return "Sin configuración"
        if row["UnidadesRecepcion"] >= row["StockMaximoPicking"]:
            return "Cubre máximo"
        if row["UnidadesRecepcion"] >= row["StockMinimoPicking"] > 0:
            return "Cubre mínimo"
        return "No cubre mínimo"

    resumen["EstadoAbastecimientoPicking"] = resumen.apply(estado, axis=1)
    resumen["PesoTotalKg"] = resumen["PesoTotalKg"].round(2)
    resumen["VolumenTotalM3"] = resumen["VolumenTotalM3"].round(3)

    for c in columnas_salida:
        if c not in resumen:
            resumen[c] = pd.NA

    orden_guardado = {
        "🔴 P1 - Urgente": 0,
        "🟣 P2 - Producto nuevo": 1,
        "🟠 P3 - Bajo mínimo": 2,
        "🟡 P4 - Reposición": 3,
        "⚪ P5 - Normal": 4,
    }
    resumen["_OrdenGuardado"] = (
        resumen["PrioridadGuardado"]
        .map(orden_guardado)
        .fillna(5)
    )

    return (
        resumen.sort_values(
            [
                "_OrdenGuardado",
                "UnidadesRecepcion",
                "ArticuloCodigo",
            ],
            ascending=[True, False, True],
        )
        .drop(columns="_OrdenGuardado")
        [columnas_salida]
        .reset_index(drop=True)
    )
