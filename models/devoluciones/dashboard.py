from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


COLUMNAS_FECHA = [
    "FechaSolicitud",
    "FechaEnvioWhatsApp",
    "FechaInicioGestion",
    "FechaConfirmacion",
    "FechaIR",
    "FechaReingreso",
    "FechaCierre",
    "UltimaActualizacion",
]


@dataclass(frozen=True)
class MetricasDevoluciones:
    total: int
    hoy: int
    periodo: int
    pendientes: int
    finalizadas: int
    porcentaje_detenidas: float
    porcentaje_despachadas: float
    tiempo_promedio_cierre_horas: float
    tiempo_promedio_ir_horas: float


def preparar_datos_devoluciones(tabla: pd.DataFrame) -> pd.DataFrame:
    df = tabla.copy()

    for columna in COLUMNAS_FECHA:
        if columna not in df.columns:
            df[columna] = pd.NaT
        df[columna] = pd.to_datetime(df[columna], errors="coerce")

    columnas_texto = [
        "EstadoCancelacion",
        "ResultadoOperativo",
        "Motivo",
        "Cliente",
        "ResponsableGestion",
        "UsuarioSolicitante",
        "Remito",
    ]
    for columna in columnas_texto:
        if columna not in df.columns:
            df[columna] = ""
        df[columna] = df[columna].fillna("").astype(str).str.strip()

    df["CantidadRemitos"] = (
        df["Remito"]
        .str.replace(",", "|", regex=False)
        .str.split("|")
        .apply(lambda valores: len([v for v in valores if str(v).strip()]))
    )

    df["HorasHastaEnvio"] = (
        df["FechaEnvioWhatsApp"] - df["FechaSolicitud"]
    ).dt.total_seconds() / 3600
    df["HorasHastaConfirmacion"] = (
        df["FechaConfirmacion"] - df["FechaSolicitud"]
    ).dt.total_seconds() / 3600
    df["HorasHastaIR"] = (
        df["FechaIR"] - df["FechaSolicitud"]
    ).dt.total_seconds() / 3600
    df["HorasHastaReingreso"] = (
        df["FechaReingreso"] - df["FechaSolicitud"]
    ).dt.total_seconds() / 3600
    df["HorasResolucion"] = (
        df["FechaCierre"] - df["FechaSolicitud"]
    ).dt.total_seconds() / 3600

    df["FechaDia"] = df["FechaSolicitud"].dt.floor("D")
    df["Mes"] = df["FechaSolicitud"].dt.to_period("M").astype(str)
    df["DiaSemana"] = df["FechaSolicitud"].dt.day_name(locale=None)
    mapa_dias = {
        "Monday": "Lunes",
        "Tuesday": "Martes",
        "Wednesday": "Miércoles",
        "Thursday": "Jueves",
        "Friday": "Viernes",
        "Saturday": "Sábado",
        "Sunday": "Domingo",
    }
    df["DiaSemana"] = df["DiaSemana"].replace(mapa_dias)
    df["HoraSolicitud"] = df["FechaSolicitud"].dt.hour

    return df


def aplicar_filtros_dashboard(
    df: pd.DataFrame,
    fecha_desde,
    fecha_hasta,
    motivos: list[str] | None = None,
    clientes: list[str] | None = None,
    responsables: list[str] | None = None,
) -> pd.DataFrame:
    resultado = df.copy()

    if "FechaSolicitud" in resultado.columns:
        mascara_fecha = resultado["FechaSolicitud"].dt.date.between(
            fecha_desde,
            fecha_hasta,
            inclusive="both",
        )
        resultado = resultado.loc[mascara_fecha]

    if motivos:
        resultado = resultado.loc[resultado["Motivo"].isin(motivos)]
    if clientes:
        resultado = resultado.loc[resultado["Cliente"].isin(clientes)]
    if responsables:
        resultado = resultado.loc[
            resultado["ResponsableGestion"].isin(responsables)
        ]

    return resultado.reset_index(drop=True)


def _promedio_valido(serie: pd.Series) -> float:
    valores = pd.to_numeric(serie, errors="coerce")
    valores = valores[(valores >= 0) & valores.notna()]
    return float(valores.mean()) if not valores.empty else 0.0


def calcular_metricas(
    df: pd.DataFrame,
    fecha_desde,
    fecha_hasta,
) -> MetricasDevoluciones:
    total = len(df)
    hoy = int((df["FechaSolicitud"].dt.date == pd.Timestamp.today().date()).sum())

    estados = df["EstadoCancelacion"].str.upper()
    resultados = df["ResultadoOperativo"].str.upper()

    finalizadas = int(estados.eq("FINALIZADA").sum())
    pendientes = int(
        (~estados.isin({"FINALIZADA", "CANCELADA"})).sum()
    )

    base_resultados = resultados.isin(
        {"ENTREGA DETENIDA", "YA DESPACHADO", "CANCELADA"}
    )
    cantidad_resultados = int(base_resultados.sum())

    detenidas = int(resultados.eq("ENTREGA DETENIDA").sum())
    despachadas = int(resultados.eq("YA DESPACHADO").sum())

    porcentaje_detenidas = (
        detenidas / cantidad_resultados * 100 if cantidad_resultados else 0.0
    )
    porcentaje_despachadas = (
        despachadas / cantidad_resultados * 100 if cantidad_resultados else 0.0
    )

    return MetricasDevoluciones(
        total=total,
        hoy=hoy,
        periodo=total,
        pendientes=pendientes,
        finalizadas=finalizadas,
        porcentaje_detenidas=porcentaje_detenidas,
        porcentaje_despachadas=porcentaje_despachadas,
        tiempo_promedio_cierre_horas=_promedio_valido(df["HorasResolucion"]),
        tiempo_promedio_ir_horas=_promedio_valido(df["HorasHastaIR"]),
    )


def resumen_evolucion_diaria(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "Fecha",
                "FechaEtiqueta",
                "FechaVisible",
                "Gestiones",
            ]
        )

    resumen = (
        df.dropna(subset=["FechaDia"])
        .groupby("FechaDia", as_index=False)
        .size()
        .rename(
            columns={
                "FechaDia": "Fecha",
                "size": "Gestiones",
            }
        )
        .sort_values("Fecha")
        .reset_index(drop=True)
    )

    meses_es = {
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
            f"{meses_es.get(fecha.month, '')}"
        )
    )
    resumen["FechaVisible"] = resumen["Fecha"].dt.strftime(
        "%d/%m/%Y"
    )

    return resumen


def resumen_categoria(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    if df.empty or columna not in df.columns:
        return pd.DataFrame(columns=[columna, "Gestiones"])
    serie = df[columna].replace("", "Sin dato")
    return (
        serie.value_counts(dropna=False)
        .rename_axis(columna)
        .reset_index(name="Gestiones")
    )


def top_clientes(df: pd.DataFrame, limite: int = 10) -> pd.DataFrame:
    return resumen_categoria(df, "Cliente").head(limite)


def ranking_responsables(df: pd.DataFrame, limite: int = 10) -> pd.DataFrame:
    base = df.copy()
    base["ResponsableGestion"] = base["ResponsableGestion"].replace(
        "", "Sin asignar"
    )
    agrupado = (
        base.groupby("ResponsableGestion", as_index=False)
        .agg(
            Gestiones=("CancelacionEntregaID", "count"),
            TiempoPromedioHoras=("HorasResolucion", "mean"),
        )
        .sort_values("Gestiones", ascending=False)
        .head(limite)
    )
    agrupado["TiempoPromedioHoras"] = agrupado[
        "TiempoPromedioHoras"
    ].fillna(0).round(2)
    return agrupado


def distribucion_tiempos(df: pd.DataFrame) -> pd.DataFrame:
    valores = pd.to_numeric(df["HorasResolucion"], errors="coerce")
    categorias = pd.cut(
        valores,
        bins=[-0.001, 1, 2, 4, 8, float("inf")],
        labels=["Hasta 1 h", "1 a 2 h", "2 a 4 h", "4 a 8 h", "Más de 8 h"],
    )
    return (
        categorias.value_counts(sort=False)
        .rename_axis("Rango")
        .reset_index(name="Gestiones")
    )


def embudo_gestion(df: pd.DataFrame) -> pd.DataFrame:
    total = len(df)
    etapas = [
        ("Registradas", total),
        ("Alerta enviada", int(df["FechaEnvioWhatsApp"].notna().sum())),
        ("Tomadas por Logística", int(df["FechaInicioGestion"].notna().sum())),
        ("Entrega detenida", int(df["ResultadoOperativo"].eq("Entrega detenida").sum())),
        ("IR generado", int(df["FechaIR"].notna().sum())),
        ("Reingresadas", int(df["FechaReingreso"].notna().sum())),
        ("Finalizadas", int(df["EstadoCancelacion"].eq("Finalizada").sum())),
    ]
    return pd.DataFrame(etapas, columns=["Etapa", "Gestiones"])


def tiempos_por_etapa(df: pd.DataFrame) -> pd.DataFrame:
    etapas = [
        ("Aviso WhatsApp", _promedio_valido(df["HorasHastaEnvio"])),
        ("Confirmación", _promedio_valido(df["HorasHastaConfirmacion"])),
        ("Generación IR", _promedio_valido(df["HorasHastaIR"])),
        ("Reingreso", _promedio_valido(df["HorasHastaReingreso"])),
        ("Cierre total", _promedio_valido(df["HorasResolucion"])),
    ]
    return pd.DataFrame(etapas, columns=["Etapa", "HorasPromedio"])


def solicitudes_por_dia_semana(df: pd.DataFrame) -> pd.DataFrame:
    orden = [
        "Lunes",
        "Martes",
        "Miércoles",
        "Jueves",
        "Viernes",
        "Sábado",
        "Domingo",
    ]
    resumen = resumen_categoria(df, "DiaSemana")
    resumen["DiaSemana"] = pd.Categorical(
        resumen["DiaSemana"], categories=orden, ordered=True
    )
    return resumen.sort_values("DiaSemana")


def solicitudes_por_hora(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["HoraSolicitud", "Gestiones"])
    return (
        df.dropna(subset=["HoraSolicitud"])
        .groupby("HoraSolicitud", as_index=False)
        .size()
        .rename(columns={"size": "Gestiones"})
        .sort_values("HoraSolicitud")
    )
