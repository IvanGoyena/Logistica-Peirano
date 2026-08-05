from __future__ import annotations

import re

import pandas as pd

from models.cumplimiento.base_analitica_pedidos import preparar_pedidos_digip
from models.cumplimiento.historico_proceso_pedidos import resumir_hitos_pedido
from models.cumplimiento.planificacion_servicio import enriquecer_ciclo_con_planificacion


def _serie_texto(tabla: pd.DataFrame, columna: str) -> pd.Series:
    if columna not in tabla.columns:
        return pd.Series("", index=tabla.index, dtype="object")
    return tabla[columna].fillna("").astype(str).str.strip()


def _pedido_interno(valor: object) -> bool:
    texto = "" if pd.isna(valor) else str(valor).strip().upper()
    return bool(re.match(r"^(TR|RM)\b", texto))



def _calcular_cantidades_al_cierre_mes(
    detalle_proceso: pd.DataFrame,
    referencias: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula cantidades controladas hasta el cierre del mes de creación.

    El pedido pertenece a la cohorte del mes de ``FechaReferenciaFillRate``.
    Un control efectuado en un mes posterior no mejora retroactivamente el
    Fill Rate del mes donde ingresó el pedido.
    """
    columnas_salida = [
        "ClavePedido",
        "FechaCorteFillRate",
        "UnidadesPedidasCohorte",
        "UnidadesControladasCierreMes",
        "UnidadesControladasTotales",
        "UnidadesControladasPosteriores",
        "UnidadesPendientesCierreMes",
        "LineasPedidasCohorte",
        "LineasCompletasCierreMes",
        "FechaPrimerControlPosteriorCierre",
    ]
    if detalle_proceso is None or detalle_proceso.empty:
        return pd.DataFrame(columns=columnas_salida)

    detalle = detalle_proceso.copy()
    if "ClavePedido" not in detalle.columns:
        detalle["ClavePedido"] = detalle.get(
            "Pedido", pd.Series("", index=detalle.index)
        ).fillna("").astype(str).str.strip()

    mapa = referencias[["ClavePedido", "FechaReferenciaFillRate"]].copy()
    mapa = mapa.drop_duplicates("ClavePedido", keep="first")
    mapa["FechaReferenciaFillRate"] = pd.to_datetime(
        mapa["FechaReferenciaFillRate"], errors="coerce"
    )
    mapa["FechaCorteFillRate"] = (
        mapa["FechaReferenciaFillRate"].dt.to_period("M").dt.to_timestamp("M")
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    )
    detalle = detalle.merge(mapa, on="ClavePedido", how="inner")
    if detalle.empty:
        return pd.DataFrame(columns=columnas_salida)

    for columna in ["Unidades", "UnidadesSatisfecha", "ContenedorUnidades"]:
        if columna not in detalle.columns:
            detalle[columna] = 0.0
        detalle[columna] = pd.to_numeric(
            detalle[columna], errors="coerce"
        ).fillna(0).clip(lower=0)

    if "CodigoArticulo" not in detalle.columns:
        detalle["CodigoArticulo"] = "SIN ARTICULO"
    detalle["CodigoArticulo"] = (
        detalle["CodigoArticulo"].fillna("").astype(str).str.strip()
        .replace("", "SIN ARTICULO")
    )

    control = pd.to_datetime(
        detalle.get(
            "ControlContenedorFechaHoraEstado",
            pd.Series(pd.NaT, index=detalle.index),
        ),
        errors="coerce",
    )
    detalle["FechaControlFillRate"] = control
    detalle["ControlDentroMes"] = (
        control.notna()
        & detalle["FechaCorteFillRate"].notna()
        & control.le(detalle["FechaCorteFillRate"])
    )
    detalle["ControlPosteriorMes"] = (
        control.notna()
        & detalle["FechaCorteFillRate"].notna()
        & control.gt(detalle["FechaCorteFillRate"])
    )

    claves_linea = ["ClavePedido", "CodigoArticulo"]
    pedidas = (
        detalle.groupby(claves_linea, as_index=False, dropna=False)
        .agg(UnidadesPedidasLinea=("Unidades", "max"))
    )

    dentro = detalle.loc[detalle["ControlDentroMes"]].copy()
    if dentro.empty:
        control_cierre = pedidas[claves_linea].copy()
        control_cierre["UnidadesSatisfechasCierre"] = 0.0
        control_cierre["UnidadesContenedorCierre"] = 0.0
        control_cierre["TieneControlCierre"] = False
    else:
        control_cierre = (
            dentro.groupby(claves_linea, as_index=False, dropna=False)
            .agg(
                UnidadesSatisfechasCierre=("UnidadesSatisfecha", "max"),
                UnidadesContenedorCierre=("ContenedorUnidades", "sum"),
                TieneControlCierre=("FechaControlFillRate", "count"),
            )
        )
        control_cierre["TieneControlCierre"] = (
            control_cierre["TieneControlCierre"].gt(0)
        )

    todas = detalle.loc[control.notna()].copy()
    if todas.empty:
        control_total = pedidas[claves_linea].copy()
        control_total["UnidadesSatisfechasTotal"] = 0.0
        control_total["UnidadesContenedorTotal"] = 0.0
        control_total["TieneControlTotal"] = False
    else:
        control_total = (
            todas.groupby(claves_linea, as_index=False, dropna=False)
            .agg(
                UnidadesSatisfechasTotal=("UnidadesSatisfecha", "max"),
                UnidadesContenedorTotal=("ContenedorUnidades", "sum"),
                TieneControlTotal=("FechaControlFillRate", "count"),
            )
        )
        control_total["TieneControlTotal"] = control_total["TieneControlTotal"].gt(0)

    lineas = pedidas.merge(control_cierre, on=claves_linea, how="left")
    lineas = lineas.merge(control_total, on=claves_linea, how="left")
    for columna in [
        "UnidadesSatisfechasCierre", "UnidadesContenedorCierre",
        "UnidadesSatisfechasTotal", "UnidadesContenedorTotal",
    ]:
        lineas[columna] = pd.to_numeric(
            lineas.get(columna, 0), errors="coerce"
        ).fillna(0).clip(lower=0)
    for columna in ["TieneControlCierre", "TieneControlTotal"]:
        lineas[columna] = lineas.get(columna, False).fillna(False).astype(bool)

    lineas["UnidadesControladasCierreLinea"] = lineas["UnidadesSatisfechasCierre"]
    respaldo_cierre = (
        lineas["UnidadesControladasCierreLinea"].le(0)
        & lineas["TieneControlCierre"]
    )
    lineas.loc[respaldo_cierre, "UnidadesControladasCierreLinea"] = (
        lineas.loc[respaldo_cierre, "UnidadesContenedorCierre"]
    )

    lineas["UnidadesControladasTotalLinea"] = lineas["UnidadesSatisfechasTotal"]
    respaldo_total = (
        lineas["UnidadesControladasTotalLinea"].le(0)
        & lineas["TieneControlTotal"]
    )
    lineas.loc[respaldo_total, "UnidadesControladasTotalLinea"] = (
        lineas.loc[respaldo_total, "UnidadesContenedorTotal"]
    )

    lineas["UnidadesControladasCierreLinea"] = lineas[
        ["UnidadesControladasCierreLinea", "UnidadesPedidasLinea"]
    ].min(axis=1)
    lineas["UnidadesControladasTotalLinea"] = lineas[
        ["UnidadesControladasTotalLinea", "UnidadesPedidasLinea"]
    ].min(axis=1)
    lineas["LineaCompletaCierre"] = (
        lineas["UnidadesPedidasLinea"].gt(0)
        & lineas["UnidadesControladasCierreLinea"].ge(
            lineas["UnidadesPedidasLinea"]
        )
    )

    resumen = (
        lineas.groupby("ClavePedido", as_index=False)
        .agg(
            UnidadesPedidasCohorte=("UnidadesPedidasLinea", "sum"),
            UnidadesControladasCierreMes=("UnidadesControladasCierreLinea", "sum"),
            UnidadesControladasTotales=("UnidadesControladasTotalLinea", "sum"),
            LineasPedidasCohorte=("CodigoArticulo", "size"),
            LineasCompletasCierreMes=("LineaCompletaCierre", "sum"),
        )
    )
    resumen["UnidadesControladasPosteriores"] = (
        resumen["UnidadesControladasTotales"]
        - resumen["UnidadesControladasCierreMes"]
    ).clip(lower=0)
    resumen["UnidadesPendientesCierreMes"] = (
        resumen["UnidadesPedidasCohorte"]
        - resumen["UnidadesControladasCierreMes"]
    ).clip(lower=0)

    posteriores = detalle.loc[detalle["ControlPosteriorMes"]].copy()
    if posteriores.empty:
        primer_posterior = pd.DataFrame(
            columns=["ClavePedido", "FechaPrimerControlPosteriorCierre"]
        )
    else:
        primer_posterior = (
            posteriores.groupby("ClavePedido", as_index=False)
            .agg(
                FechaPrimerControlPosteriorCierre=(
                    "FechaControlFillRate", "min"
                )
            )
        )
    resumen = resumen.merge(primer_posterior, on="ClavePedido", how="left")
    resumen = resumen.merge(
        mapa[["ClavePedido", "FechaCorteFillRate"]],
        on="ClavePedido",
        how="left",
    )
    return resumen[columnas_salida]


def construir_base_fillrate(
    df_pedidos: pd.DataFrame | None,
    df_proceso_pedidos: pd.DataFrame | None,
    df_clientes: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    """Construye el universo propio de Fill Rate.

    A diferencia de OTIF, no exige pedido cerrado ni aplica maduración de 48 h.
    Incluye todos los pedidos presentes en ``Filtrar Preparación`` y usa
    Pedidos DIGIP solamente para enriquecer creación, estado y cliente.
    """
    proceso = resumir_hitos_pedido(
        df_proceso_pedidos if df_proceso_pedidos is not None else pd.DataFrame()
    )
    if proceso.empty:
        return pd.DataFrame(), {
            "pedidos_proceso": 0,
            "pedidos_con_creacion": 0,
            "pedidos_sin_creacion": 0,
            "pedidos_internos_excluidos": 0,
        }

    pedidos = preparar_pedidos_digip(df_pedidos)
    base = proceso.merge(pedidos, on="ClavePedido", how="left")

    base["Pedido"] = _serie_texto(base, "PedidoOriginal").where(
        _serie_texto(base, "PedidoOriginal").ne(""),
        _serie_texto(base, "PedidoProceso"),
    )
    base["ClienteFinal"] = _serie_texto(base, "Cliente").where(
        _serie_texto(base, "Cliente").ne(""),
        _serie_texto(base, "ClienteProceso"),
    )
    base["ClienteCodigo"] = _serie_texto(base, "ClienteCodigo").where(
        _serie_texto(base, "ClienteCodigo").ne(""),
        _serie_texto(base, "ClienteCodigoProceso"),
    )
    base["DespachoDescripcion"] = _serie_texto(base, "DespachoDescripcion").where(
        _serie_texto(base, "DespachoDescripcion").ne(""),
        _serie_texto(base, "DespachoDescripcionProceso"),
    )
    base["CodigoDespacho"] = _serie_texto(base, "CodigoDespacho").where(
        _serie_texto(base, "CodigoDespacho").ne(""),
        _serie_texto(base, "CodigoDespachoProceso"),
    )

    base["FechaHoraCreacion"] = pd.to_datetime(
        base.get("FechaHoraCreacion"), errors="coerce"
    )
    base["FechaHoraInicioPreparacion"] = pd.to_datetime(
        base.get("FechaHoraInicioPreparacionProceso"), errors="coerce"
    )
    base["FechaHoraFinPreparacion"] = pd.to_datetime(
        base.get("FechaHoraFinPreparacionProceso"), errors="coerce"
    )
    base["FechaHoraInicioControl"] = pd.to_datetime(
        base.get("FechaHoraInicioControlProceso"), errors="coerce"
    )
    base["FechaHoraFinControl"] = pd.to_datetime(
        base.get("FechaHoraFinControlProceso"), errors="coerce"
    )

    # El filtro principal sigue siendo creación. Solo se usa el primer hito de
    # proceso como respaldo diagnóstico cuando DIGIP no trae fecha.
    base["FechaReferenciaFillRate"] = base["FechaHoraCreacion"].combine_first(
        base["FechaHoraInicioPreparacion"]
    )
    base["OrigenFechaFillRate"] = "CREACION DIGIP"
    base.loc[
        base["FechaHoraCreacion"].isna()
        & base["FechaHoraInicioPreparacion"].notna(),
        "OrigenFechaFillRate",
    ] = "INICIO PREPARACION - RESPALDO"

    # Cohorte mensual: lo creado en el mes se compara únicamente contra
    # controles realizados hasta el último instante de ese mismo mes.
    cantidades_cierre = _calcular_cantidades_al_cierre_mes(
        df_proceso_pedidos if df_proceso_pedidos is not None else pd.DataFrame(),
        base[["ClavePedido", "FechaReferenciaFillRate"]],
    )
    base = base.merge(cantidades_cierre, on="ClavePedido", how="left")

    base["UnidadesPedidas"] = pd.to_numeric(
        base.get("UnidadesPedidasCohorte", base.get("UnidadesPedidasProceso", 0)),
        errors="coerce",
    ).fillna(0).clip(lower=0)
    base["UnidadesControladasCierreMes"] = pd.to_numeric(
        base.get("UnidadesControladasCierreMes", 0), errors="coerce"
    ).fillna(0).clip(lower=0)
    base["UnidadesControladasTotales"] = pd.to_numeric(
        base.get("UnidadesControladasTotales", base.get("UnidadesControladasProceso", 0)),
        errors="coerce",
    ).fillna(0).clip(lower=0)
    base["UnidadesControladasPosteriores"] = pd.to_numeric(
        base.get("UnidadesControladasPosteriores", 0), errors="coerce"
    ).fillna(0).clip(lower=0)
    base["UnidadesPendientesCierreMes"] = pd.to_numeric(
        base.get("UnidadesPendientesCierreMes", 0), errors="coerce"
    ).fillna(0).clip(lower=0)
    base["LineasPedidasProceso"] = pd.to_numeric(
        base.get("LineasPedidasCohorte", base.get("LineasPedidasProceso", 0)),
        errors="coerce",
    ).fillna(0).clip(lower=0)
    base["LineasCompletasProceso"] = pd.to_numeric(
        base.get("LineasCompletasCierreMes", 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    base["EstadoCierreFillRate"] = "PENDIENTE AL CIERRE"
    base.loc[
        base["UnidadesPedidas"].gt(0)
        & base["UnidadesControladasCierreMes"].ge(base["UnidadesPedidas"]),
        "EstadoCierreFillRate",
    ] = "COMPLETO DENTRO DEL MES"
    base.loc[
        base["UnidadesPendientesCierreMes"].gt(0)
        & base["UnidadesControladasPosteriores"].gt(0),
        "EstadoCierreFillRate",
    ] = "COMPLETADO EN MES POSTERIOR"

    internos = base["Pedido"].map(_pedido_interno)
    internos_excluidos = int(internos.sum())
    base = base.loc[~internos].copy()

    # Aporta circuito y grupo, pero no altera el universo de Fill Rate.
    base, diagnostico_planificacion = enriquecer_ciclo_con_planificacion(
        base,
        df_clientes,
    )

    diagnostico = {
        "pedidos_proceso": int(base["ClavePedido"].nunique()),
        "pedidos_con_creacion": int(base["FechaHoraCreacion"].notna().sum()),
        "pedidos_sin_creacion": int(base["FechaHoraCreacion"].isna().sum()),
        "pedidos_internos_excluidos": internos_excluidos,
        **{
            f"planificacion_{clave}": valor
            for clave, valor in diagnostico_planificacion.items()
        },
    }
    return base.reset_index(drop=True), diagnostico
