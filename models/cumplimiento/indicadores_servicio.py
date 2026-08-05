from __future__ import annotations

import numpy as np
import pandas as pd

CIRCUITOS_OTIF = ("ZONA", "EXPRESO", "RETIRA", "DIARIO")

# SLA internos para medir si la operación terminó la preparación a tiempo.
SLA_PREPARACION_HORAS = {
    "EXPRESO": 48,
    "DIARIO": 48,
    "RETIRA": 36,
}


def _serie_fecha(tabla: pd.DataFrame, *columnas: str) -> pd.Series:
    salida = pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]")
    for columna in columnas:
        if columna in tabla.columns:
            salida = salida.combine_first(
                pd.to_datetime(tabla[columna], errors="coerce")
            )
    return salida


def _fin_del_dia(serie: pd.Series) -> pd.Series:
    salida = serie.copy()
    mascara = salida.notna()
    salida.loc[mascara] = (
        salida.loc[mascara].dt.normalize()
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    )
    return salida


def calcular_indicadores_servicio(
    tabla: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    """
    Construye indicadores de cumplimiento final y de preparación.

    OTIF final:
    - ZONA: primera HR final dentro del día objetivo de entrega.
    - DIARIO: primera HR final dentro de 72 h corridas desde la creación.
    - EXPRESO: primera HR final dentro de 96 h corridas desde la creación.
    - RETIRA: Control finalizado dentro de 48 h desde la creación.

    Cumplimiento del ciclo Preparación + Control:
    - ZONA: asigna el pedido al primer ciclo cuyo corte (día hábil anterior) estaba abierto.
    - ZONA: fin de Control dentro del día de preparación programado.
    - EXPRESO: fin de Control dentro de 96 h desde la creación.
    - DIARIO: fin de Control dentro de 72 h desde la creación.
    - RETIRA: fin de Control dentro de 48 h desde la creación.
    """
    diagnostico_vacio = {
        "evaluados": 0,
        "cumplen": 0,
        "no_cumplen": 0,
        "otif_pct": 0.0,
        "lead_time_promedio_horas": 0.0,
        "atraso_promedio_horas": 0.0,
        "preparacion_evaluados": 0,
        "preparacion_cumplen": 0,
        "preparacion_no_cumplen": 0,
        "preparacion_otif_pct": 0.0,
        "preparacion_lead_time_promedio_horas": 0.0,
        "demora_posterior_preparacion": 0,
        "preparacion_tardia_recuperada": 0,
        "referencia_provisoria_inicio_preparacion": 0,
    }
    if tabla is None or tabla.empty:
        return pd.DataFrame() if tabla is None else tabla.copy(), diagnostico_vacio

    salida = tabla.copy()
    circuito = (
        salida.get("TipoCircuito", pd.Series("", index=salida.index))
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    salida["CircuitoOTIF"] = circuito

    creacion = _serie_fecha(salida, "FechaHoraCreacion")
    referencia_otif = _serie_fecha(
        salida,
        "FechaReferenciaIngresoCiclo",
        "FechaHoraTransmision",
        "FechaHoraCreacion",
    )
    objetivo_entrega = _serie_fecha(salida, "FechaObjetivoEntrega")
    objetivo_preparacion_base = _serie_fecha(
        salida,
        "FechaObjetivoPreparacion",
    )
    fin_preparacion = _serie_fecha(salida, "FechaHoraFinPreparacion")
    hr_final = _serie_fecha(
        salida,
        "FechaHoraPrimeraHojaRutaFinal",
        "FechaHoraPrimeraHojaRuta",
    )
    fin_control = _serie_fecha(salida, "FechaHoraFinControl")

    # ==========================================================
    # OTIF FINAL
    # ==========================================================
    evento_real = hr_final.copy()
    mascara_retira = circuito.eq("RETIRA")
    evento_real.loc[mascara_retira] = fin_control.loc[mascara_retira]

    objetivo_comparable = objetivo_entrega.copy()
    mascara_zona = circuito.eq("ZONA")
    objetivo_comparable.loc[mascara_zona] = _fin_del_dia(
        objetivo_entrega.loc[mascara_zona]
    )

    aplica_base = salida.get(
        "AplicaOTIFBase",
        pd.Series(False, index=salida.index),
    ).fillna(False).astype(bool)
    salida["AplicaOTIF"] = (
        aplica_base
        & circuito.isin(CIRCUITOS_OTIF)
        & referencia_otif.notna()
        & objetivo_comparable.notna()
    )

    salida["FechaEventoCumplimiento"] = evento_real
    salida["FechaObjetivoCumplimiento"] = objetivo_comparable
    salida["CumpleInFullOperativo"] = evento_real.notna() & salida["AplicaOTIF"]
    salida["CumpleOnTime"] = (
        evento_real.notna()
        & objetivo_comparable.notna()
        & evento_real.le(objetivo_comparable)
        & salida["AplicaOTIF"]
    )
    salida["CumpleOTIF"] = (
        salida["CumpleInFullOperativo"]
        & salida["CumpleOnTime"]
        & salida["AplicaOTIF"]
    )
    salida["EstadoOTIF"] = np.select(
        [~salida["AplicaOTIF"], salida["CumpleOTIF"]],
        ["SIN EVALUAR", "CUMPLE"],
        default="NO CUMPLE",
    )
    salida["DesvioOTIFHoras"] = (
        evento_real - objetivo_comparable
    ).dt.total_seconds().div(3600)
    salida.loc[evento_real.isna(), "DesvioOTIFHoras"] = np.nan
    salida["LeadTimeServicioHoras"] = (
        evento_real - referencia_otif
    ).dt.total_seconds().div(3600)
    salida.loc[salida["LeadTimeServicioHoras"].lt(0), "LeadTimeServicioHoras"] = np.nan

    salida["MotivoIncumplimientoOTIF"] = ""
    mascara_evalua = salida["AplicaOTIF"]
    salida.loc[
        mascara_evalua & mascara_retira & fin_control.isna(),
        "MotivoIncumplimientoOTIF",
    ] = "SIN CIERRE DE CONTROL"
    salida.loc[
        mascara_evalua & mascara_retira & fin_control.notna() & ~salida["CumpleOnTime"],
        "MotivoIncumplimientoOTIF",
    ] = "CONTROL FUERA DE SLA 48H"
    salida.loc[
        mascara_evalua & ~mascara_retira & hr_final.isna(),
        "MotivoIncumplimientoOTIF",
    ] = "SIN HOJA DE RUTA"
    salida.loc[
        mascara_evalua & ~mascara_retira & hr_final.notna() & ~salida["CumpleOnTime"],
        "MotivoIncumplimientoOTIF",
    ] = "HR FUERA DE FECHA OBJETIVO"
    salida.loc[salida["CumpleOTIF"], "MotivoIncumplimientoOTIF"] = "CUMPLE"

    # ==========================================================
    # CUMPLIMIENTO DEL CICLO PREPARACIÓN + CONTROL
    # ==========================================================
    inicio_preparacion = _serie_fecha(
        salida,
        "FechaHoraInicioPreparacion",
    )

    # El cierre operativo de la preparación se considera en el fin de Control.
    cierre_operativo_preparacion = fin_control.copy()

    # Diagnóstico real entre ingreso e inicio de preparación. No define por sí
    # solo el universo: para ZONA manda el corte del ciclo programado.
    fecha_ingreso_ciclo = _serie_fecha(
        salida,
        "FechaReferenciaIngresoCiclo",
        "FechaHoraTransmision",
        "FechaHoraCreacion",
    )
    fecha_corte_ingreso = _serie_fecha(
        salida,
        "FechaCorteIngresoCiclo",
    )
    salida["HorasAnticipacionInicioPreparacion"] = (
        inicio_preparacion - fecha_ingreso_ciclo
    ).dt.total_seconds().div(3600)

    cumple_corte_zona = (
        fecha_ingreso_ciclo.notna()
        & fecha_corte_ingreso.notna()
        & fecha_ingreso_ciclo.le(fecha_corte_ingreso)
    )
    salida["CumpleAnticipacionPreparacion24h"] = np.where(
        mascara_zona,
        cumple_corte_zona,
        fecha_ingreso_ciclo.notna(),
    )
    salida["CumpleCortePreparacionProgramada"] = np.where(
        mascara_zona,
        cumple_corte_zona,
        True,
    )

    objetivo_preparacion = pd.Series(
        pd.NaT,
        index=salida.index,
        dtype="datetime64[ns]",
    )

    # ZONA: el ciclo Preparación + Control debe finalizar
    # dentro del día de preparación configurado en el maestro.
    objetivo_preparacion.loc[mascara_zona] = _fin_del_dia(
        objetivo_preparacion_base.loc[mascara_zona]
    )

    # En los circuitos por SLA se utiliza el mismo compromiso
    # operativo que el OTIF final, pero con Fin de Control como evento.
    sla_ciclo_preparacion_horas = {
        "EXPRESO": 96,
        "DIARIO": 72,
        "RETIRA": 48,
    }
    for nombre_circuito, horas in sla_ciclo_preparacion_horas.items():
        mascara = circuito.eq(nombre_circuito) & referencia_otif.notna()
        objetivo_preparacion.loc[mascara] = (
            referencia_otif.loc[mascara] + pd.Timedelta(hours=horas)
        )

    salida["FechaObjetivoPreparacionOTIF"] = objetivo_preparacion
    salida["FechaRealPreparacionOTIF"] = cierre_operativo_preparacion

    salida["AplicaPreparacionOTIF"] = (
        aplica_base
        & circuito.isin(CIRCUITOS_OTIF)
        & fecha_ingreso_ciclo.notna()
        & objetivo_preparacion.notna()
        & salida["CumpleCortePreparacionProgramada"].astype(bool)
    )

    salida["CumplePreparacionOTIF"] = (
        salida["AplicaPreparacionOTIF"]
        & cierre_operativo_preparacion.notna()
        & cierre_operativo_preparacion.le(objetivo_preparacion)
    )

    salida["EstadoPreparacionOTIF"] = np.select(
        [
            ~salida["AplicaPreparacionOTIF"],
            salida["CumplePreparacionOTIF"],
        ],
        [
            "SIN EVALUAR",
            "CUMPLE",
        ],
        default="NO CUMPLE",
    )

    salida["DesvioPreparacionHoras"] = (
        cierre_operativo_preparacion - objetivo_preparacion
    ).dt.total_seconds().div(3600)
    salida.loc[
        cierre_operativo_preparacion.isna(),
        "DesvioPreparacionHoras",
    ] = np.nan

    # Duración real del proceso operativo:
    # inicio de Preparación hasta fin de Control.
    salida["LeadTimePreparacionOTIFHoras"] = (
        cierre_operativo_preparacion - inicio_preparacion
    ).dt.total_seconds().div(3600)
    salida.loc[
        salida["LeadTimePreparacionOTIFHoras"].lt(0),
        "LeadTimePreparacionOTIFHoras",
    ] = np.nan
    salida["HorasCicloPreparacionControl"] = (
        salida["LeadTimePreparacionOTIFHoras"]
    )

    salida["MotivoIncumplimientoPreparacion"] = ""
    mascara_prep_evalua = salida["AplicaPreparacionOTIF"]

    salida.loc[
        (
            mascara_zona
            & fecha_ingreso_ciclo.notna()
            & fecha_corte_ingreso.notna()
            & ~cumple_corte_zona
        ),
        "MotivoIncumplimientoPreparacion",
    ] = "PEDIDO INGRESADO DESPUES DEL CORTE DEL CICLO"

    salida.loc[
        mascara_prep_evalua & cierre_operativo_preparacion.isna(),
        "MotivoIncumplimientoPreparacion",
    ] = "SIN FIN DE CONTROL"

    salida.loc[
        (
            mascara_prep_evalua
            & cierre_operativo_preparacion.notna()
            & ~salida["CumplePreparacionOTIF"]
            & mascara_zona
        ),
        "MotivoIncumplimientoPreparacion",
    ] = "CONTROL FUERA DEL DIA DE PREPARACION"

    for nombre_circuito, horas in sla_ciclo_preparacion_horas.items():
        mascara = (
            mascara_prep_evalua
            & circuito.eq(nombre_circuito)
            & cierre_operativo_preparacion.notna()
            & ~salida["CumplePreparacionOTIF"]
        )
        salida.loc[
            mascara,
            "MotivoIncumplimientoPreparacion",
        ] = f"CONTROL FUERA DE SLA {horas}H"

    salida.loc[
        salida["CumplePreparacionOTIF"],
        "MotivoIncumplimientoPreparacion",
    ] = "CUMPLE"

    # Matriz que identifica dónde se originó o recuperó el desvío.
    ambas_evaluables = salida["AplicaOTIF"] & salida["AplicaPreparacionOTIF"]
    salida["DiagnosticoPreparacionEntrega"] = np.select(
        [
            ~ambas_evaluables,
            salida["CumplePreparacionOTIF"] & salida["CumpleOTIF"],
            salida["CumplePreparacionOTIF"] & ~salida["CumpleOTIF"],
            ~salida["CumplePreparacionOTIF"] & salida["CumpleOTIF"],
        ],
        [
            "SIN EVALUAR",
            "CUMPLE PREPARACION Y ENTREGA",
            "DEMORA POSTERIOR A PREPARACION",
            "PREPARACION TARDIA RECUPERADA",
        ],
        default="INCUMPLIMIENTO DESDE PREPARACION",
    )

    # ==========================================================
    # DIAGNÓSTICO GENERAL
    # ==========================================================
    evaluados = salida.loc[salida["AplicaOTIF"]].copy()
    cantidad_evaluados = int(len(evaluados))
    cumplen = int(evaluados["CumpleOTIF"].sum()) if cantidad_evaluados else 0
    no_cumplen = cantidad_evaluados - cumplen
    otif_pct = (cumplen / cantidad_evaluados * 100) if cantidad_evaluados else 0.0

    preparacion_evaluados = salida.loc[salida["AplicaPreparacionOTIF"]].copy()
    cantidad_prep = int(len(preparacion_evaluados))
    preparacion_cumplen = int(
        preparacion_evaluados["CumplePreparacionOTIF"].sum()
    ) if cantidad_prep else 0
    preparacion_no_cumplen = cantidad_prep - preparacion_cumplen
    preparacion_pct = (
        preparacion_cumplen / cantidad_prep * 100
        if cantidad_prep else 0.0
    )

    lead_time = pd.to_numeric(
        evaluados.get("LeadTimeServicioHoras", pd.Series(dtype=float)),
        errors="coerce",
    ).dropna()
    lead_time_prep = pd.to_numeric(
        preparacion_evaluados.get(
            "LeadTimePreparacionOTIFHoras",
            pd.Series(dtype=float),
        ),
        errors="coerce",
    ).dropna()
    atrasos = pd.to_numeric(
        evaluados.loc[~evaluados["CumpleOTIF"], "DesvioOTIFHoras"],
        errors="coerce",
    ).dropna()
    atrasos = atrasos.loc[atrasos.gt(0)]

    diagnostico = {
        "evaluados": cantidad_evaluados,
        "cumplen": cumplen,
        "no_cumplen": no_cumplen,
        "otif_pct": round(otif_pct, 2),
        "lead_time_promedio_horas": round(float(lead_time.mean()), 2)
        if not lead_time.empty else 0.0,
        "atraso_promedio_horas": round(float(atrasos.mean()), 2)
        if not atrasos.empty else 0.0,
        "preparacion_evaluados": cantidad_prep,
        "preparacion_cumplen": preparacion_cumplen,
        "preparacion_no_cumplen": preparacion_no_cumplen,
        "preparacion_otif_pct": round(preparacion_pct, 2),
        "preparacion_lead_time_promedio_horas": round(
            float(lead_time_prep.mean()), 2
        ) if not lead_time_prep.empty else 0.0,
        "demora_posterior_preparacion": int(
            salida["DiagnosticoPreparacionEntrega"]
            .eq("DEMORA POSTERIOR A PREPARACION")
            .sum()
        ),
        "preparacion_tardia_recuperada": int(
            salida["DiagnosticoPreparacionEntrega"]
            .eq("PREPARACION TARDIA RECUPERADA")
            .sum()
        ),
        "referencia_provisoria_inicio_preparacion": int(
            salida.get(
                "UsaReferenciaInicioPreparacion",
                pd.Series(False, index=salida.index),
            ).fillna(False).astype(bool).sum()
        ),
    }

    return salida, diagnostico
