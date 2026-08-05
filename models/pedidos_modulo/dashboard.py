from __future__ import annotations

import pandas as pd


ESTADOS_GESTION_CERRADOS = {
    "FINALIZADA",
    "RESUELTO",
    "RECHAZADO",
    "CANCELADA",
}


def preparar_datos_dashboard(
    tabla: pd.DataFrame,
) -> pd.DataFrame:
    """Normaliza la tabla consolidada para análisis visual."""
    if tabla is None or tabla.empty:
        return pd.DataFrame()

    datos = tabla.copy()

    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "DespachoDescripcion",
        "Planificacion",
        "DetalleFamilias",
    ]
    for columna in columnas_texto:
        if columna not in datos.columns:
            datos[columna] = ""
        datos[columna] = (
            datos[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    columnas_numericas = [
        "TotalUnidades",
        "TotalM3",
        "TotalSKUs",
        "ImporteERP",
    ]
    for columna in columnas_numericas:
        if columna not in datos.columns:
            datos[columna] = 0
        datos[columna] = pd.to_numeric(
            datos[columna],
            errors="coerce",
        ).fillna(0)

    if "FechaTransmisionERP" not in datos.columns:
        datos["FechaTransmisionERP"] = pd.NaT

    datos["FechaTransmisionERP"] = pd.to_datetime(
        datos["FechaTransmisionERP"],
        errors="coerce",
    )

    # El dashboard analiza la fecha real de transmisión al WMS.
    # No se utiliza la fecha de creación del pedido.
    datos["FechaAnalisis"] = datos["FechaTransmisionERP"]
    datos["FechaDia"] = (
        datos["FechaAnalisis"].dt.normalize()
    )
    datos["AntiguedadDias"] = (
        pd.Timestamp.now().normalize()
        - datos["FechaDia"]
    ).dt.days.clip(lower=0)

    preparacion = (
        datos["PreparacionEstado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    datos["CategoriaPreparacion"] = "Sin preparación"
    datos.loc[
        preparacion.isin(
            {
                "PREPARACION",
                "PREPARACIÓN",
                "EN CURSO",
                "INICIADA",
                "INICIADO",
            }
        ),
        "CategoriaPreparacion",
    ] = "En preparación"
    datos.loc[
        preparacion.isin(
            {
                "FINALIZADA",
                "FINALIZADO",
                "COMPLETA",
                "COMPLETO",
                "PREPARADA",
                "PREPARADO",
            }
        ),
        "CategoriaPreparacion",
    ] = "Preparado"

    datos["ClienteVisible"] = (
        datos["ClienteCodigo"].where(
            datos["ClienteCodigo"].ne(""),
            "Sin código",
        )
        + " - "
        + datos["ClienteDescripcion"].where(
            datos["ClienteDescripcion"].ne(""),
            "Cliente sin identificar",
        )
    )

    datos["PlanificacionVisible"] = datos[
        "Planificacion"
    ].replace("", "Sin planificación")

    datos["DespachoVisible"] = datos[
        "DespachoDescripcion"
    ].where(
        datos["DespachoDescripcion"].ne(""),
        datos["CodigoDespacho"],
    ).replace("", "Sin despacho")

    datos["RangoAntiguedad"] = pd.cut(
        datos["AntiguedadDias"],
        bins=[-1, 0, 1, 2, 5, float("inf")],
        labels=[
            "Hoy",
            "1 día",
            "2 días",
            "3 a 5 días",
            "Más de 5 días",
        ],
    ).astype(str)

    return datos


def aplicar_filtros_dashboard(
    datos: pd.DataFrame,
    fecha_desde=None,
    fecha_hasta=None,
    estados: list[str] | None = None,
    preparaciones: list[str] | None = None,
    planificaciones: list[str] | None = None,
    clientes: list[str] | None = None,
    incluir_cencosud: bool = True,
) -> pd.DataFrame:
    if datos is None or datos.empty:
        return pd.DataFrame()

    filtrados = datos.copy()

    if fecha_desde is not None:
        filtrados = filtrados[
            filtrados["FechaDia"]
            >= pd.Timestamp(fecha_desde)
        ]
    if fecha_hasta is not None:
        filtrados = filtrados[
            filtrados["FechaDia"]
            <= pd.Timestamp(fecha_hasta)
        ]
    if estados:
        filtrados = filtrados[
            filtrados["Estado"].isin(estados)
        ]
    if preparaciones:
        filtrados = filtrados[
            filtrados["CategoriaPreparacion"].isin(
                preparaciones
            )
        ]
    if planificaciones:
        filtrados = filtrados[
            filtrados["PlanificacionVisible"].isin(
                planificaciones
            )
        ]
    if clientes:
        filtrados = filtrados[
            filtrados["ClienteVisible"].isin(clientes)
        ]

    if not incluir_cencosud:
        mascara_cencosud = (
            filtrados["ClienteDescripcion"]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.contains(
                "CENCOSUD",
                na=False,
                regex=False,
            )
        )
        filtrados = filtrados.loc[
            ~mascara_cencosud
        ].copy()

    return filtrados.copy()


def calcular_kpis(datos: pd.DataFrame) -> dict:
    if datos is None or datos.empty:
        return {
            "pedidos": 0,
            "unidades": 0,
            "importe": 0.0,
            "volumen": 0.0,
            "clientes": 0,
            "antiguedad_promedio": 0.0,
            "pedidos_criticos": 0,
            "planificaciones": 0,
        }

    antiguedad = pd.to_numeric(
        datos["AntiguedadDias"],
        errors="coerce",
    ).fillna(0)

    # Criterio ejecutivo inicial: más de 5 días o una carga
    # excepcionalmente grande respecto del conjunto filtrado.
    limite_unidades = float(
        datos["TotalUnidades"].quantile(0.90)
    )
    limite_volumen = float(
        datos["TotalM3"].quantile(0.90)
    )

    mascara_criticos = (
        antiguedad.gt(5)
        | datos["TotalUnidades"].ge(limite_unidades)
        | datos["TotalM3"].ge(limite_volumen)
    )

    return {
        "pedidos": int(datos["Pedido"].nunique()),
        "unidades": int(datos["TotalUnidades"].sum()),
        "importe": float(datos["ImporteERP"].sum()),
        "volumen": float(datos["TotalM3"].sum()),
        "clientes": int(datos["ClienteVisible"].nunique()),
        "antiguedad_promedio": float(antiguedad.mean()),
        "pedidos_criticos": int(
            datos.loc[mascara_criticos, "Pedido"].nunique()
        ),
        "planificaciones": int(
            datos["PlanificacionVisible"]
            .loc[
                datos["PlanificacionVisible"].ne(
                    "Sin planificación"
                )
            ]
            .nunique()
        ),
    }


def resumen_evolucion(datos: pd.DataFrame) -> pd.DataFrame:
    """
    Resume la evolución diaria por cantidad de unidades pendientes.
    """
    if datos.empty:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "FechaEtiqueta",
                "FechaVisible",
                "Unidades",
            ]
        )

    resumen = (
        datos.dropna(subset=["FechaDia"])
        .groupby("FechaDia", as_index=False)
        .agg(Unidades=("TotalUnidades", "sum"))
        .rename(columns={"FechaDia": "Fecha"})
        .sort_values("Fecha")
        .reset_index(drop=True)
    )

    resumen["Unidades"] = (
        pd.to_numeric(
            resumen["Unidades"],
            errors="coerce",
        )
        .fillna(0)
        .round(0)
        .astype(int)
    )

    meses = {
        1: "ene",
        2: "feb",
        3: "mar",
        4: "abr",
        5: "may",
        6: "jun",
        7: "jul",
        8: "ago",
        9: "sep",
        10: "oct",
        11: "nov",
        12: "dic",
    }

    resumen["FechaEtiqueta"] = resumen["Fecha"].apply(
        lambda fecha: (
            f"{fecha.day:02d} "
            f"{meses.get(fecha.month, '')}"
        )
    )
    resumen["FechaVisible"] = resumen["Fecha"].dt.strftime(
        "%d/%m/%Y"
    )

    return resumen


def resumen_categoria(
    datos: pd.DataFrame,
    columna: str,
    nombre_categoria: str,
    top: int | None = None,
    medida: str = "Pedidos",
) -> pd.DataFrame:
    if datos.empty or columna not in datos.columns:
        return pd.DataFrame(
            columns=[nombre_categoria, medida]
        )

    if medida == "Unidades":
        resumen = (
            datos.groupby(columna, as_index=False)
            .agg(Unidades=("TotalUnidades", "sum"))
        )
    elif medida == "Volumen":
        resumen = (
            datos.groupby(columna, as_index=False)
            .agg(Volumen=("TotalM3", "sum"))
        )
    else:
        resumen = (
            datos.groupby(columna, as_index=False)
            .agg(Pedidos=("Pedido", "nunique"))
        )

    resumen = resumen.rename(
        columns={columna: nombre_categoria}
    ).sort_values(
        medida,
        ascending=False,
    )

    if top:
        resumen = resumen.head(top)

    return resumen.reset_index(drop=True)

def resumen_composicion_detalle(
    detalle: pd.DataFrame,
    pedidos: list[str] | set[str],
    dimension: str = "Sectorizacion",
    top: int = 5,
) -> pd.DataFrame:
    """
    Resume unidades por Sectorización o Familia usando el detalle
    enriquecido con el Maestro de Artículos.

    Conserva las categorías principales y agrupa el remanente
    bajo la categoría 'Otros' para mantener legible el donut.
    """
    nombre_visible = {
        "Sectorizacion": "Sectorización",
        "Familia": "Familia",
    }.get(dimension, dimension)

    if (
        detalle is None
        or detalle.empty
        or "Pedido" not in detalle.columns
        or dimension not in detalle.columns
    ):
        return pd.DataFrame(
            columns=[nombre_visible, "Unidades"]
        )

    pedidos_normalizados = {
        str(pedido).strip().replace(".0", "")
        for pedido in pedidos
        if str(pedido).strip()
    }

    datos = detalle.copy()
    datos["Pedido"] = (
        datos["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    datos = datos[
        datos["Pedido"].isin(pedidos_normalizados)
    ].copy()

    if datos.empty:
        return pd.DataFrame(
            columns=[nombre_visible, "Unidades"]
        )

    datos[dimension] = (
        datos[dimension]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Sin clasificar")
    )

    datos["Cantidad"] = pd.to_numeric(
        datos.get("Cantidad", 0),
        errors="coerce",
    ).fillna(0)

    resumen_completo = (
        datos.groupby(dimension, as_index=False)
        .agg(Unidades=("Cantidad", "sum"))
        .rename(columns={dimension: nombre_visible})
        .sort_values("Unidades", ascending=False)
        .reset_index(drop=True)
    )

    if len(resumen_completo) > top:
        principales = resumen_completo.head(top).copy()
        unidades_otros = resumen_completo.iloc[top:][
            "Unidades"
        ].sum()

        if unidades_otros > 0:
            otros = pd.DataFrame(
                {
                    nombre_visible: ["Otros"],
                    "Unidades": [unidades_otros],
                }
            )
            resumen = pd.concat(
                [principales, otros],
                ignore_index=True,
            )
        else:
            resumen = principales
    else:
        resumen = resumen_completo

    resumen["Unidades"] = (
        resumen["Unidades"]
        .round(0)
        .astype(int)
    )

    return resumen

def resumen_periodo(
    datos: pd.DataFrame,
) -> dict:
    """
    Indicadores que ayudan a interpretar la evolución temporal.
    """
    evolucion = resumen_evolucion(datos)

    if evolucion.empty:
        return {
            "fecha_maxima": "Sin dato",
            "unidades_maximas": 0,
            "promedio_diario": 0.0,
            "total_unidades": 0,
            "pedidos_transmitidos": 0,
            "variacion_ultima_fecha": None,
        }

    fila_maxima = evolucion.loc[
        evolucion["Unidades"].idxmax()
    ]

    variacion = None
    if len(evolucion) >= 2:
        valor_anterior = float(
            evolucion.iloc[-2]["Unidades"]
        )
        valor_actual = float(
            evolucion.iloc[-1]["Unidades"]
        )

        if valor_anterior > 0:
            variacion = (
                (valor_actual - valor_anterior)
                / valor_anterior
                * 100
            )

    return {
        "fecha_maxima": fila_maxima["Fecha"].strftime(
            "%d/%m/%Y"
        ),
        "unidades_maximas": int(
            fila_maxima["Unidades"]
        ),
        "promedio_diario": float(
            evolucion["Unidades"].mean()
        ),
        "total_unidades": int(
            datos["TotalUnidades"].sum()
        ),
        "pedidos_transmitidos": int(
            datos["Pedido"].nunique()
        ),
        "variacion_ultima_fecha": variacion,
    }


def indicadores_inteligencia(
    datos: pd.DataFrame,
) -> dict:
    """
    Calcula indicadores de concentración, tendencia y carga.
    """
    if datos is None or datos.empty:
        return {
            "unidades_promedio_pedido": 0.0,
            "volumen_promedio_pedido": 0.0,
            "concentracion_top_5": 0.0,
            "cliente_principal": "Sin dato",
            "participacion_cliente_principal": 0.0,
            "pedidos_mas_5_dias": 0,
            "unidades_mas_5_dias": 0,
            "tendencia_reciente": None,
        }

    pedidos = max(
        int(datos["Pedido"].nunique()),
        1,
    )

    clientes = (
        datos.groupby(
            "ClienteVisible",
            as_index=False,
        )
        .agg(Unidades=("TotalUnidades", "sum"))
        .sort_values(
            "Unidades",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    total_unidades = float(
        datos["TotalUnidades"].sum()
    )

    concentracion_top_5 = (
        clientes.head(5)["Unidades"].sum()
        / total_unidades
        * 100
        if total_unidades > 0
        else 0
    )

    cliente_principal = (
        str(clientes.iloc[0]["ClienteVisible"])
        if not clientes.empty
        else "Sin dato"
    )

    participacion_principal = (
        float(clientes.iloc[0]["Unidades"])
        / total_unidades
        * 100
        if not clientes.empty
        and total_unidades > 0
        else 0
    )

    antiguos = datos[
        datos["AntiguedadDias"] > 5
    ]

    evolucion = resumen_evolucion(datos)
    tendencia = None

    if len(evolucion) >= 4:
        cantidad = min(3, len(evolucion) // 2)
        promedio_actual = float(
            evolucion.tail(cantidad)[
                "Unidades"
            ].mean()
        )
        promedio_previo = float(
            evolucion.iloc[
                -cantidad * 2:-cantidad
            ]["Unidades"].mean()
        )

        if promedio_previo > 0:
            tendencia = (
                (promedio_actual - promedio_previo)
                / promedio_previo
                * 100
            )

    return {
        "unidades_promedio_pedido": (
            total_unidades / pedidos
        ),
        "volumen_promedio_pedido": (
            float(datos["TotalM3"].sum())
            / pedidos
        ),
        "concentracion_top_5": float(
            concentracion_top_5
        ),
        "cliente_principal": cliente_principal,
        "participacion_cliente_principal": float(
            participacion_principal
        ),
        "pedidos_mas_5_dias": int(
            antiguos["Pedido"].nunique()
        ),
        "unidades_mas_5_dias": int(
            antiguos["TotalUnidades"].sum()
        ),
        "tendencia_reciente": tendencia,
    }


def resumen_clientes_analitico(
    datos: pd.DataFrame,
    top: int = 12,
) -> pd.DataFrame:
    """
    Ranking de clientes con participación acumulada tipo Pareto.
    """
    if datos is None or datos.empty:
        return pd.DataFrame(
            columns=[
                "Cliente",
                "Pedidos",
                "Unidades",
                "Volumen",
                "Participacion",
                "Acumulado",
            ]
        )

    resumen = (
        datos.groupby(
            "ClienteVisible",
            as_index=False,
        )
        .agg(
            Pedidos=("Pedido", "nunique"),
            Unidades=("TotalUnidades", "sum"),
            Volumen=("TotalM3", "sum"),
        )
        .rename(
            columns={"ClienteVisible": "Cliente"}
        )
        .sort_values(
            "Unidades",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    total = float(resumen["Unidades"].sum())

    resumen["Participacion"] = (
        resumen["Unidades"] / total * 100
        if total > 0
        else 0
    )
    resumen["Acumulado"] = (
        resumen["Participacion"].cumsum()
    )

    resumen["Volumen"] = resumen[
        "Volumen"
    ].round(2)
    resumen["Participacion"] = resumen[
        "Participacion"
    ].round(1)
    resumen["Acumulado"] = resumen[
        "Acumulado"
    ].round(1)

    return resumen.head(top).reset_index(drop=True)


def resumen_planificacion_analitico(
    datos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Productividad y dimensión media de los pedidos por planificación.
    """
    if datos is None or datos.empty:
        return pd.DataFrame(
            columns=[
                "Planificación",
                "Pedidos",
                "Unidades",
                "Volumen",
                "Unidades por pedido",
                "M3 por pedido",
            ]
        )

    resumen = (
        datos.groupby(
            "PlanificacionVisible",
            as_index=False,
        )
        .agg(
            Pedidos=("Pedido", "nunique"),
            Unidades=("TotalUnidades", "sum"),
            Volumen=("TotalM3", "sum"),
        )
        .rename(
            columns={
                "PlanificacionVisible": "Planificación"
            }
        )
    )

    resumen["Unidades por pedido"] = (
        resumen["Unidades"]
        / resumen["Pedidos"].replace(0, pd.NA)
    ).fillna(0).round(1)

    resumen["M3 por pedido"] = (
        resumen["Volumen"]
        / resumen["Pedidos"].replace(0, pd.NA)
    ).fillna(0).round(2)

    resumen["Volumen"] = resumen[
        "Volumen"
    ].round(2)

    return (
        resumen.sort_values(
            "Volumen",
            ascending=False,
        )
        .reset_index(drop=True)
    )


def pedidos_criticos(
    datos: pd.DataFrame,
    limite: int = 15,
) -> pd.DataFrame:
    """
    Pedidos que requieren atención por antigüedad y dimensión.
    """
    if datos is None or datos.empty:
        return pd.DataFrame()

    columnas = [
        "Pedido",
        "ClienteVisible",
        "FechaAnalisis",
        "AntiguedadDias",
        "TotalUnidades",
        "TotalM3",
        "PlanificacionVisible",
        "CategoriaPreparacion",
    ]

    disponibles = [
        columna
        for columna in columnas
        if columna in datos.columns
    ]

    criticos = datos[disponibles].copy()

    criticos["PuntajeCriticidad"] = (
        criticos["AntiguedadDias"].fillna(0) * 10
        + pd.to_numeric(
            criticos["TotalUnidades"],
            errors="coerce",
        ).fillna(0) / 50
        + pd.to_numeric(
            criticos["TotalM3"],
            errors="coerce",
        ).fillna(0) * 2
    )

    criticos["Fecha transmisión"] = (
        pd.to_datetime(
            criticos["FechaAnalisis"],
            errors="coerce",
        )
        .dt.strftime("%d/%m/%Y")
        .fillna("Sin dato")
    )

    criticos = (
        criticos.sort_values(
            [
                "PuntajeCriticidad",
                "AntiguedadDias",
            ],
            ascending=False,
        )
        .head(limite)
        .rename(
            columns={
                "ClienteVisible": "Cliente",
                "AntiguedadDias": "Días",
                "TotalUnidades": "Unidades",
                "TotalM3": "M3",
                "PlanificacionVisible": "Planificación",
                "CategoriaPreparacion": "Preparación",
            }
        )
    )

    return criticos[
        [
            "Pedido",
            "Cliente",
            "Fecha transmisión",
            "Días",
            "Unidades",
            "M3",
            "Planificación",
            "Preparación",
        ]
    ].reset_index(drop=True)

def formatear_importe_compacto(valor: float) -> str:
    """Formato ejecutivo con convención visual argentina."""
    numero = float(valor or 0)

    if abs(numero) >= 1_000_000_000:
        texto = f"$ {numero / 1_000_000_000:,.1f} mil M"
    elif abs(numero) >= 1_000_000:
        texto = f"$ {numero / 1_000_000:,.1f} M"
    elif abs(numero) >= 1_000:
        texto = f"$ {numero / 1_000:,.1f} mil"
    else:
        texto = f"$ {numero:,.0f}"

    return (
        texto
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def resumen_abc_detalle(
    detalle: pd.DataFrame,
    pedidos: list[str] | set[str],
    dimension: str = "Familia",
) -> pd.DataFrame:
    """
    Análisis ABC sobre unidades y volumen.

    El importe no se distribuye por familia porque el detalle actual
    no contiene valor monetario por línea/artículo.
    """
    nombre = {
        "Familia": "Familia",
        "Sectorizacion": "Sectorización",
    }.get(dimension, dimension)

    columnas_salida = [
        nombre,
        "Unidades",
        "Volumen",
        "Participación",
        "Acumulado",
        "ClaseABC",
    ]

    if (
        detalle is None
        or detalle.empty
        or dimension not in detalle.columns
        or "Pedido" not in detalle.columns
    ):
        return pd.DataFrame(columns=columnas_salida)

    pedidos_validos = {
        str(pedido).strip().replace(".0", "")
        for pedido in pedidos
        if str(pedido).strip()
    }

    datos = detalle.copy()
    datos["Pedido"] = (
        datos["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    datos = datos[
        datos["Pedido"].isin(pedidos_validos)
    ].copy()

    if datos.empty:
        return pd.DataFrame(columns=columnas_salida)

    datos[dimension] = (
        datos[dimension]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "Sin clasificar")
    )
    datos["Cantidad"] = pd.to_numeric(
        datos.get("Cantidad", 0),
        errors="coerce",
    ).fillna(0)
    datos["VolumenLineaM3"] = pd.to_numeric(
        datos.get("VolumenLineaM3", 0),
        errors="coerce",
    ).fillna(0)

    resumen = (
        datos.groupby(dimension, as_index=False)
        .agg(
            Unidades=("Cantidad", "sum"),
            Volumen=("VolumenLineaM3", "sum"),
        )
        .rename(columns={dimension: nombre})
        .sort_values("Unidades", ascending=False)
        .reset_index(drop=True)
    )

    total = float(resumen["Unidades"].sum())
    resumen["Participación"] = (
        resumen["Unidades"] / total * 100
        if total > 0
        else 0
    )
    resumen["Acumulado"] = resumen[
        "Participación"
    ].cumsum()

    resumen["ClaseABC"] = "C"
    resumen.loc[
        resumen["Acumulado"].le(80),
        "ClaseABC",
    ] = "A"
    resumen.loc[
        resumen["Acumulado"].gt(80)
        & resumen["Acumulado"].le(95),
        "ClaseABC",
    ] = "B"

    resumen["Unidades"] = resumen[
        "Unidades"
    ].round(0).astype(int)
    resumen["Volumen"] = resumen[
        "Volumen"
    ].round(2)
    resumen["Participación"] = resumen[
        "Participación"
    ].round(1)
    resumen["Acumulado"] = resumen[
        "Acumulado"
    ].round(1)

    return resumen[columnas_salida]


def resumen_clientes_impacto(
    datos: pd.DataFrame,
    top: int = 12,
) -> pd.DataFrame:
    """
    Ranking de clientes por impacto operativo combinado.

    Score:
    - 35% unidades
    - 25% volumen
    - 25% importe
    - 15% antigüedad promedio
    """
    columnas = [
        "Cliente",
        "Pedidos",
        "Unidades",
        "Volumen",
        "Importe",
        "Antigüedad",
        "Impacto",
    ]
    if datos is None or datos.empty:
        return pd.DataFrame(columns=columnas)

    resumen = (
        datos.groupby("ClienteVisible", as_index=False)
        .agg(
            Pedidos=("Pedido", "nunique"),
            Unidades=("TotalUnidades", "sum"),
            Volumen=("TotalM3", "sum"),
            Importe=("ImporteERP", "sum"),
            Antigüedad=("AntiguedadDias", "mean"),
        )
        .rename(columns={"ClienteVisible": "Cliente"})
    )

    def normalizar(serie: pd.Series) -> pd.Series:
        maximo = float(serie.max())
        if maximo <= 0:
            return pd.Series(0.0, index=serie.index)
        return serie / maximo

    resumen["Impacto"] = (
        normalizar(resumen["Unidades"]) * 35
        + normalizar(resumen["Volumen"]) * 25
        + normalizar(resumen["Importe"]) * 25
        + normalizar(resumen["Antigüedad"]) * 15
    ).round(1)

    resumen["Volumen"] = resumen["Volumen"].round(2)
    resumen["Antigüedad"] = resumen[
        "Antigüedad"
    ].round(1)

    return (
        resumen.sort_values("Impacto", ascending=False)
        .head(top)
        .reset_index(drop=True)[columnas]
    )


def evaluar_riesgo_operativo(
    datos: pd.DataFrame,
    inteligencia: dict,
) -> dict:
    """Genera un nivel de riesgo explicado por reglas visibles."""
    if datos is None or datos.empty:
        return {
            "nivel": "Sin datos",
            "puntaje": 0,
            "motivos": [],
        }

    puntos = 0
    motivos: list[str] = []

    concentracion = float(
        inteligencia.get("concentracion_top_5", 0)
    )
    if concentracion >= 70:
        puntos += 3
        motivos.append(
            f"El Top 5 concentra {concentracion:.1f}% de las unidades."
        )
    elif concentracion >= 55:
        puntos += 2
        motivos.append(
            f"El Top 5 concentra {concentracion:.1f}% de las unidades."
        )

    total_unidades = float(datos["TotalUnidades"].sum())
    unidades_antiguas = float(
        datos.loc[
            datos["AntiguedadDias"].gt(5),
            "TotalUnidades",
        ].sum()
    )
    porcentaje_antiguo = (
        unidades_antiguas / total_unidades * 100
        if total_unidades > 0
        else 0
    )
    if porcentaje_antiguo >= 25:
        puntos += 3
        motivos.append(
            f"{porcentaje_antiguo:.1f}% de las unidades supera 5 días."
        )
    elif porcentaje_antiguo >= 10:
        puntos += 1
        motivos.append(
            f"{porcentaje_antiguo:.1f}% de las unidades supera 5 días."
        )

    tendencia = inteligencia.get("tendencia_reciente")
    if tendencia is not None and tendencia >= 25:
        puntos += 2
        motivos.append(
            f"La carga reciente creció {tendencia:.1f}%."
        )
    elif tendencia is not None and tendencia >= 10:
        puntos += 1
        motivos.append(
            f"La carga reciente creció {tendencia:.1f}%."
        )

    cliente = (
        datos["ClienteDescripcion"]
        .fillna("")
        .astype(str)
        .str.upper()
    )
    unidades_cencosud = float(
        datos.loc[
            cliente.str.contains(
                "CENCOSUD",
                na=False,
                regex=False,
            ),
            "TotalUnidades",
        ].sum()
    )
    participacion_cencosud = (
        unidades_cencosud / total_unidades * 100
        if total_unidades > 0
        else 0
    )
    if participacion_cencosud >= 45:
        puntos += 2
        motivos.append(
            f"Cencosud representa {participacion_cencosud:.1f}% de las unidades."
        )
    elif participacion_cencosud >= 25:
        puntos += 1
        motivos.append(
            f"Cencosud representa {participacion_cencosud:.1f}% de las unidades."
        )

    if puntos >= 7:
        nivel = "Alto"
    elif puntos >= 4:
        nivel = "Medio"
    else:
        nivel = "Bajo"

    if not motivos:
        motivos.append(
            "No se detectaron concentraciones o atrasos relevantes."
        )

    return {
        "nivel": nivel,
        "puntaje": puntos,
        "motivos": motivos,
        "porcentaje_antiguo": porcentaje_antiguo,
        "participacion_cencosud": participacion_cencosud,
    }


def indice_complejidad_pedidos(
    datos: pd.DataFrame,
    detalle: pd.DataFrame,
    limite: int = 20,
) -> pd.DataFrame:
    """
    Prioriza pedidos mediante un índice de complejidad 0-100.

    Componentes:
    - antigüedad: 25 puntos
    - unidades: 20 puntos
    - volumen: 15 puntos
    - SKU: 15 puntos
    - diversidad de familias: 15 puntos
    - importe: 10 puntos
    """
    salida = [
        "Prioridad",
        "Pedido",
        "Cliente",
        "Puntaje",
        "Días",
        "Unidades",
        "SKU",
        "Familias",
        "M3",
        "Importe",
        "Planificación",
        "Motivos",
    ]
    if datos is None or datos.empty:
        return pd.DataFrame(columns=salida)

    base = datos.drop_duplicates(
        subset=["Pedido"],
        keep="first",
    ).copy()

    familias = pd.DataFrame(
        columns=["Pedido", "Familias"]
    )
    if (
        detalle is not None
        and not detalle.empty
        and "Pedido" in detalle.columns
        and "Familia" in detalle.columns
    ):
        det = detalle.copy()
        det["Pedido"] = (
            det["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )
        familias = (
            det.groupby("Pedido", as_index=False)
            .agg(
                Familias=(
                    "Familia",
                    lambda serie: serie.fillna("")
                    .astype(str)
                    .str.strip()
                    .loc[lambda s: s.ne("")]
                    .nunique(),
                )
            )
        )

    base = base.merge(
        familias,
        on="Pedido",
        how="left",
    )
    base["Familias"] = pd.to_numeric(
        base["Familias"],
        errors="coerce",
    ).fillna(0)

    componentes = {
        "AntiguedadDias": 25,
        "TotalUnidades": 20,
        "TotalM3": 15,
        "TotalSKUs": 15,
        "Familias": 15,
        "ImporteERP": 10,
    }

    puntaje = pd.Series(0.0, index=base.index)
    for columna, peso in componentes.items():
        valores = pd.to_numeric(
            base[columna],
            errors="coerce",
        ).fillna(0)
        # Ranking percentil evita que un pedido extremo distorsione todo.
        percentil = valores.rank(
            pct=True,
            method="average",
        )
        puntaje += percentil * peso

    base["Puntaje"] = puntaje.round(1)

    def explicar(fila: pd.Series) -> str:
        motivos = []
        if float(fila["AntiguedadDias"]) > 5:
            motivos.append(
                f"{int(fila['AntiguedadDias'])} días"
            )
        if float(fila["TotalUnidades"]) >= base[
            "TotalUnidades"
        ].quantile(0.75):
            motivos.append("muchas unidades")
        if float(fila["TotalM3"]) >= base[
            "TotalM3"
        ].quantile(0.75):
            motivos.append("alto volumen")
        if float(fila["TotalSKUs"]) >= base[
            "TotalSKUs"
        ].quantile(0.75):
            motivos.append("muchos SKU")
        if float(fila["Familias"]) >= 3:
            motivos.append(
                f"{int(fila['Familias'])} familias"
            )
        if float(fila["ImporteERP"]) >= base[
            "ImporteERP"
        ].quantile(0.75):
            motivos.append("importe alto")
        return ", ".join(motivos) or "carga equilibrada"

    base["Motivos"] = base.apply(
        explicar,
        axis=1,
    )

    base = (
        base.sort_values(
            ["Puntaje", "AntiguedadDias"],
            ascending=False,
        )
        .head(limite)
        .reset_index(drop=True)
    )
    base["Prioridad"] = (
        base.index + 1
    )
    base["Importe"] = base["ImporteERP"].round(0)
    base["M3"] = base["TotalM3"].round(2)

    return base.rename(
        columns={
            "ClienteVisible": "Cliente",
            "AntiguedadDias": "Días",
            "TotalUnidades": "Unidades",
            "TotalSKUs": "SKU",
            "PlanificacionVisible": "Planificación",
        }
    )[salida]

