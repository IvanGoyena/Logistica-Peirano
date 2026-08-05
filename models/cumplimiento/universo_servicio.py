from __future__ import annotations

import re

import numpy as np
import pandas as pd


VENTANA_MADURACION_HORAS = 48
PREFIJOS_PEDIDOS_INTERNOS = ("TR", "RM")


def _serie_texto(tabla: pd.DataFrame, columna: str) -> pd.Series:
    if columna not in tabla.columns:
        return pd.Series("", index=tabla.index, dtype="object")
    return tabla[columna].fillna("").astype(str).str.strip()


def _serie_fecha(tabla: pd.DataFrame, columna: str) -> pd.Series:
    if columna not in tabla.columns:
        return pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]")

    serie = pd.to_datetime(tabla[columna], errors="coerce")
    try:
        if getattr(serie.dt, "tz", None) is not None:
            serie = serie.dt.tz_convert(
                "America/Argentina/Buenos_Aires"
            ).dt.tz_localize(None)
    except (AttributeError, TypeError):
        pass
    return serie


def _normalizar_momento(valor: object | None = None) -> pd.Timestamp:
    if valor is None or str(valor).strip() == "":
        momento = pd.Timestamp.now(tz="America/Argentina/Buenos_Aires")
    else:
        momento = pd.Timestamp(valor)
        if momento.tzinfo is None:
            momento = momento.tz_localize("America/Argentina/Buenos_Aires")
        else:
            momento = momento.tz_convert("America/Argentina/Buenos_Aires")

    return momento.tz_localize(None)


def _pedido_para_regla(tabla: pd.DataFrame) -> pd.Series:
    candidatos = [
        "Pedido",
        "PedidoOriginal",
        "PedidoHojaRuta",
        "ClavePedido",
    ]
    resultado = pd.Series("", index=tabla.index, dtype="object")
    for columna in candidatos:
        if columna not in tabla.columns:
            continue
        serie = _serie_texto(tabla, columna)
        resultado = resultado.where(resultado.ne(""), serie)
    return resultado.str.upper()


def construir_universo_servicio(
    df_ciclo: pd.DataFrame,
    momento_evaluacion: object | None = None,
    ventana_maduracion_horas: int = VENTANA_MADURACION_HORAS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Define el universo válido del dashboard de cumplimiento.

    Reglas, en orden de prioridad:
    1. Excluye pedidos internos cuyos códigos comienzan con TR o RM.
    2. Excluye pedidos DIGIP cerrados sin cierre de Preparación ni Control.
       Se consideran anulados operativos y no incumplimientos de servicio.
    3. Mantiene en maduración los pedidos controlados durante las últimas
       ``ventana_maduracion_horas`` horas. Todavía pueden recibir HR o formar
       parte de la próxima entrega y no deben afectar los indicadores.

    Devuelve:
    - universo_activo: pedidos listos para análisis;
    - universo_excluido: pedidos apartados con motivo auditable;
    - diagnostico: contadores de cada regla.
    """
    if df_ciclo is None or df_ciclo.empty:
        vacio = pd.DataFrame() if df_ciclo is None else df_ciclo.copy()
        return vacio, vacio.copy(), {
            "pedidos_entrada": 0,
            "pedidos_activos": 0,
            "pedidos_excluidos": 0,
            "pedidos_internos": 0,
            "pedidos_anulados_operativos": 0,
            "pedidos_en_maduracion_48h": 0,
        }

    tabla = df_ciclo.copy()
    ahora = _normalizar_momento(momento_evaluacion)
    ventana = max(int(ventana_maduracion_horas), 0)

    pedido_regla = _pedido_para_regla(tabla)
    patron_interno = rf"^\s*(?:{'|'.join(map(re.escape, PREFIJOS_PEDIDOS_INTERNOS))})(?:\b|[_\-\s])"
    tabla["EsPedidoInterno"] = pedido_regla.str.contains(
        patron_interno,
        regex=True,
        na=False,
    )

    inicio_preparacion = _serie_fecha(tabla, "FechaHoraInicioPreparacion")
    fin_preparacion = _serie_fecha(tabla, "FechaHoraFinPreparacion")
    inicio_control = _serie_fecha(tabla, "FechaHoraInicioControl")
    fin_control = _serie_fecha(tabla, "FechaHoraFinControl")

    # El pedido está cerrado en DIGIP porque el universo anterior ya fue
    # filtrado por estado. Sin cierre de Preparación ni Control se interpreta
    # como anulación operativa, no como incumplimiento.
    tabla["EsAnuladoOperativo"] = (
        fin_preparacion.isna()
        & fin_control.isna()
    )

    horas_desde_control = (
        ahora - fin_control
    ).dt.total_seconds().div(3600)
    tabla["HorasDesdeFinControl"] = horas_desde_control.round(2)
    tabla["FechaDisponibleAnalisis"] = (
        fin_control + pd.Timedelta(hours=ventana)
    )
    tabla["EnMaduracion48h"] = (
        fin_control.notna()
        & horas_desde_control.ge(0)
        & horas_desde_control.lt(ventana)
    )

    # Las reglas son mutuamente excluyentes y respetan prioridad.
    condiciones = [
        tabla["EsPedidoInterno"],
        ~tabla["EsPedidoInterno"] & tabla["EsAnuladoOperativo"],
        ~tabla["EsPedidoInterno"]
        & ~tabla["EsAnuladoOperativo"]
        & tabla["EnMaduracion48h"],
    ]
    motivos = [
        "PEDIDO INTERNO TR/RM",
        "ANULADO OPERATIVO",
        "EN MADURACION 48H",
    ]
    tabla["MotivoExclusionServicio"] = np.select(
        condiciones,
        motivos,
        default="",
    )
    tabla["IncluidoUniversoServicio"] = tabla[
        "MotivoExclusionServicio"
    ].eq("")
    tabla["EstadoUniversoServicio"] = np.where(
        tabla["IncluidoUniversoServicio"],
        "ACTIVO PARA ANALISIS",
        tabla["MotivoExclusionServicio"],
    )

    activos = tabla.loc[
        tabla["IncluidoUniversoServicio"]
    ].copy()
    excluidos = tabla.loc[
        ~tabla["IncluidoUniversoServicio"]
    ].copy()

    diagnostico = {
        "pedidos_entrada": int(len(tabla)),
        "pedidos_activos": int(len(activos)),
        "pedidos_excluidos": int(len(excluidos)),
        "pedidos_internos": int(
            tabla["MotivoExclusionServicio"].eq(
                "PEDIDO INTERNO TR/RM"
            ).sum()
        ),
        "pedidos_anulados_operativos": int(
            tabla["MotivoExclusionServicio"].eq(
                "ANULADO OPERATIVO"
            ).sum()
        ),
        "pedidos_en_maduracion_48h": int(
            tabla["MotivoExclusionServicio"].eq(
                "EN MADURACION 48H"
            ).sum()
        ),
        "momento_evaluacion": ahora.isoformat(),
        "ventana_maduracion_horas": ventana,
    }

    return (
        activos.reset_index(drop=True),
        excluidos.reset_index(drop=True),
        diagnostico,
    )
