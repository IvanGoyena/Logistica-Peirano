from __future__ import annotations

import pandas as pd
import streamlit as st

from models.pedidos import construir_tabla_pedidos
from models.tareas import (
    construir_tabla_tareas,
    obtener_avance_despachos,
    obtener_carros_criticos,
    obtener_pendiente_pick,
    obtener_resumen_operativo,
    obtener_tabla_operativa,
)


def _normalizar_fecha_control(serie: pd.Series) -> pd.Series:
    """
    El reporte mensual Control utiliza fechas con formato MM/DD/YYYY.
    Por ejemplo, dentro de "Control Agosto 2026", 08/04/2026 es 4 de agosto.
    """
    return pd.to_datetime(
        serie,
        errors="coerce",
        dayfirst=False,
    )


def obtener_control_dia_anterior(
    df_control: pd.DataFrame | None,
    fecha_referencia: pd.Timestamp | None = None,
) -> dict[str, object]:
    resultado: dict[str, object] = {
        "fecha": None,
        "carros": 0,
        "unidades": 0,
        "articulos": 0,
        "unidades_por_carro": 0.0,
        "disponible": False,
        "es_dia_calendario_anterior": False,
    }

    if df_control is None or df_control.empty:
        return resultado

    columnas_requeridas = {"ControlContenedorId", "FechaFin", "Unidades"}
    if not columnas_requeridas.issubset(df_control.columns):
        return resultado

    control = df_control.copy()
    control["FechaFinControl"] = _normalizar_fecha_control(control["FechaFin"])
    control = control.dropna(subset=["FechaFinControl"])

    if control.empty:
        return resultado

    control["FechaControl"] = control["FechaFinControl"].dt.normalize()
    control["ControlContenedorId"] = (
        control["ControlContenedorId"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    control["Unidades"] = pd.to_numeric(
        control["Unidades"], errors="coerce"
    ).fillna(0)

    if "Articulos" in control.columns:
        control["Articulos"] = pd.to_numeric(
            control["Articulos"], errors="coerce"
        ).fillna(0)
    else:
        control["Articulos"] = 0

    control = control.loc[control["ControlContenedorId"].ne("")].copy()
    if control.empty:
        return resultado

    # El reporte tiene una fila por artículo:
    # - "Unidades" corresponde a las unidades de esa línea y debe sumarse.
    # - "Articulos" representa el total del control y se repite en cada línea,
    #   por lo que se toma el máximo una sola vez por control/contenedor.
    controles_unicos = (
        control.groupby(
            ["FechaControl", "ControlContenedorId"],
            as_index=False,
            dropna=False,
        )
        .agg(
            FechaFinControl=("FechaFinControl", "max"),
            Unidades=("Unidades", "sum"),
            Articulos=("Articulos", "max"),
        )
        .reset_index(drop=True)
    )

    referencia = (
        pd.Timestamp.now().normalize()
        if fecha_referencia is None
        else pd.Timestamp(fecha_referencia).normalize()
    )
    ayer_calendario = referencia - pd.Timedelta(days=1)

    fechas_anteriores = controles_unicos.loc[
        controles_unicos["FechaControl"].lt(referencia),
        "FechaControl",
    ].dropna()

    if fechas_anteriores.empty:
        return resultado

    # Prioridad: ayer calendario. Si el reporte aún no lo contiene,
    # se utiliza el último día cerrado disponible y se informa su fecha.
    if ayer_calendario in set(fechas_anteriores.tolist()):
        fecha_objetivo = ayer_calendario
        es_ayer = True
    else:
        fecha_objetivo = fechas_anteriores.max()
        es_ayer = False

    dia = controles_unicos.loc[
        controles_unicos["FechaControl"].eq(fecha_objetivo)
    ].copy()

    carros = int(dia["ControlContenedorId"].nunique())
    unidades = int(dia["Unidades"].sum())
    articulos = int(dia["Articulos"].sum())

    return {
        "fecha": fecha_objetivo,
        "carros": carros,
        "unidades": unidades,
        "articulos": articulos,
        "unidades_por_carro": unidades / carros if carros else 0.0,
        "disponible": True,
        "es_dia_calendario_anterior": es_ayer,
    }


@st.cache_data(show_spinner="Preparando el centro de control...")
def construir_contexto_tareas(
    df_tareas: pd.DataFrame,
    df_pedidos: pd.DataFrame,
    df_detalle: pd.DataFrame,
    df_clientes: pd.DataFrame,
    df_articulos: pd.DataFrame,
    df_volumetria: pd.DataFrame,
    df_control: pd.DataFrame | None = None,
) -> dict[str, object]:
    tabla_pedidos = construir_tabla_pedidos(
        df_pedidos,
        df_detalle,
        df_articulos,
        df_clientes,
        df_volumetria,
    )

    tabla_tareas = construir_tabla_tareas(
        df_tareas,
        tabla_pedidos,
        df_clientes,
    )

    tabla_operativa = obtener_tabla_operativa(tabla_tareas)
    resumen = obtener_resumen_operativo(tabla_tareas, df_pedidos)
    avance_despachos, despachos_sin_iniciar = obtener_avance_despachos(tabla_tareas)
    carros_criticos = obtener_carros_criticos(tabla_operativa, avance_despachos)
    pendiente_pick = obtener_pendiente_pick(tabla_tareas, tabla_pedidos)
    control_dia_anterior = obtener_control_dia_anterior(df_control)

    pedidos_sin_preparacion = tabla_pedidos.loc[
        tabla_pedidos["PreparacionID"].isna()
    ].copy()

    tareas_unidades = tabla_tareas.merge(
        tabla_pedidos[["PreparacionID", "TotalUnidades"]],
        left_on="Preparacion",
        right_on="PreparacionID",
        how="left",
    )

    unidades_carros_curso = int(
        tareas_unidades.loc[
            tareas_unidades["Categoria"].eq("En Curso")
        ]
        .drop_duplicates("Preparacion")["TotalUnidades"]
        .fillna(0)
        .sum()
    )

    unidades_carros_finalizados = int(
        tareas_unidades.loc[
            tareas_unidades["Categoria"].eq("Finalizado")
        ]
        .drop_duplicates("Preparacion")["TotalUnidades"]
        .fillna(0)
        .sum()
    )

    preparaciones_activas = tabla_tareas.loc[
        tabla_tareas["Categoria"].isin(["Pendiente", "En Curso"]),
        "Preparacion",
    ].dropna().unique()

    columnas_sector = [
        columna
        for columna in [
            "IMPORTADO", "Importado", "NACIONAL", "Nacional",
            "BACHAS", "Bachas", "BLISTER", "Blister",
            "SANITARIOS", "Sanitarios", "REPUESTOS", "Repuestos",
            "FLEXIBLES", "Flexibles", "ACCESORIOS", "Accesorios",
            "VARIOS", "Varios",
        ]
        if columna in tabla_pedidos.columns
    ]

    if columnas_sector:
        familias_operativas = (
            tabla_pedidos.loc[
                tabla_pedidos["PreparacionID"].isin(preparaciones_activas),
                columnas_sector,
            ]
            .sum()
            .sort_values(ascending=False)
        )
        familias_operativas = familias_operativas.loc[familias_operativas.gt(0)]
    else:
        familias_operativas = pd.Series(dtype="float64")

    return {
        "tabla_pedidos": tabla_pedidos,
        "tabla_tareas": tabla_tareas,
        "tabla_operativa": tabla_operativa,
        "resumen": resumen,
        "avance_despachos": avance_despachos,
        "despachos_sin_iniciar": despachos_sin_iniciar,
        "carros_criticos": carros_criticos,
        "pendiente_pick": pendiente_pick,
        "control_dia_anterior": control_dia_anterior,
        "pedidos_pendientes": int(len(pedidos_sin_preparacion)),
        "unidades_pendientes": int(
            pedidos_sin_preparacion["TotalUnidades"].fillna(0).sum()
        ),
        "unidades_carros_curso": unidades_carros_curso,
        "unidades_carros_finalizados": unidades_carros_finalizados,
        "familias_operativas": familias_operativas,
    }
