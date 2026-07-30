from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


def _normalizar_texto(valor: object) -> str:
    if valor is None or pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def _normalizar_codigo(valor: object) -> str:
    return _normalizar_texto(valor).upper()


def _buscar_columna(
    dataframe: pd.DataFrame,
    candidatos: Iterable[str],
    obligatoria: bool = True,
) -> str | None:
    mapa = {
        re.sub(r"[^a-z0-9]", "", str(columna).lower()): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        clave = re.sub(r"[^a-z0-9]", "", candidato.lower())
        if clave in mapa:
            return mapa[clave]

    if obligatoria:
        raise ValueError(
            "No se encontró ninguna de estas columnas: "
            + ", ".join(candidatos)
        )

    return None


def _serie_numerica(
    dataframe: pd.DataFrame,
    columna: str | None,
) -> pd.Series:
    if columna is None:
        return pd.Series(0.0, index=dataframe.index)

    return (
        pd.to_numeric(dataframe[columna], errors="coerce")
        .fillna(0)
        .clip(lower=0)
    )


def _preparar_stock_erp(df_stock_erp: pd.DataFrame | None) -> pd.DataFrame:
    columnas_salida = [
        "ArticuloCodigo",
        "ArticuloDescripcionERP",
        "DisponibleERP",
        "TransitoERP",
        "StockFisicoERP",
        "ReservadoERP",
        "DisponibleTotalERP",
    ]

    if df_stock_erp is None or df_stock_erp.empty:
        return pd.DataFrame(columns=columnas_salida)

    stock = df_stock_erp.copy()

    col_codigo = _buscar_columna(
        stock,
        ["cod_art", "CodigoArticulo", "ArticuloCodigo", "Codigo"],
    )
    col_descripcion = _buscar_columna(
        stock,
        ["des_art", "DescripcionArticulo", "ArticuloDescripcion"],
        obligatoria=False,
    )
    col_disponible = _buscar_columna(
        stock,
        ["est_1", "DisponibleERP", "Aprobado"],
    )
    col_transito = _buscar_columna(
        stock,
        ["est_8", "TransitoERP", "PendienteERP"],
    )
    col_fisico = _buscar_columna(
        stock,
        ["stk_fis", "StockFisicoERP"],
        obligatoria=False,
    )
    col_reservado = _buscar_columna(
        stock,
        ["stk_res", "ReservadoERP"],
        obligatoria=False,
    )
    col_disponible_total = _buscar_columna(
        stock,
        ["stk_dis", "DisponibleTotalERP"],
        obligatoria=False,
    )

    preparado = pd.DataFrame(index=stock.index)
    preparado["ArticuloCodigo"] = stock[col_codigo].map(_normalizar_codigo)
    preparado["ArticuloDescripcionERP"] = (
        stock[col_descripcion].fillna("").astype(str).str.strip()
        if col_descripcion
        else ""
    )
    preparado["DisponibleERP"] = _serie_numerica(stock, col_disponible)
    preparado["TransitoERP"] = _serie_numerica(stock, col_transito)
    preparado["StockFisicoERP"] = _serie_numerica(stock, col_fisico)
    preparado["ReservadoERP"] = _serie_numerica(stock, col_reservado)
    preparado["DisponibleTotalERP"] = _serie_numerica(
        stock,
        col_disponible_total,
    )

    preparado = preparado.loc[
        preparado["ArticuloCodigo"].ne("")
    ].copy()

    return (
        preparado.groupby("ArticuloCodigo", as_index=False)
        .agg(
            ArticuloDescripcionERP=(
                "ArticuloDescripcionERP",
                lambda serie: next(
                    (x for x in serie.astype(str) if x.strip()),
                    "",
                ),
            ),
            DisponibleERP=("DisponibleERP", "sum"),
            TransitoERP=("TransitoERP", "sum"),
            StockFisicoERP=("StockFisicoERP", "sum"),
            ReservadoERP=("ReservadoERP", "sum"),
            DisponibleTotalERP=("DisponibleTotalERP", "sum"),
        )
    )


def _preparar_stock_wms(df_disponible: pd.DataFrame | None) -> pd.DataFrame:
    if df_disponible is None or df_disponible.empty:
        return pd.DataFrame(
            columns=["ArticuloCodigo", "DisponibleWMS"]
        )

    stock = df_disponible.copy()

    col_codigo = _buscar_columna(
        stock,
        [
            "CodigoArticulo",
            "ArticuloCodigo",
            "cod_art",
            "Articulo",
            "Codigo",
        ],
    )
    col_disponible = _buscar_columna(
        stock,
        [
            "Disponible",
            "StockDisponible",
            "CantidadDisponible",
            "stk_dis",
        ],
    )

    preparado = pd.DataFrame({
        "ArticuloCodigo": stock[col_codigo].map(_normalizar_codigo),
        "DisponibleWMS": _serie_numerica(stock, col_disponible),
    })

    preparado = preparado.loc[
        preparado["ArticuloCodigo"].ne("")
    ].copy()

    return (
        preparado.groupby("ArticuloCodigo", as_index=False)
        .agg(DisponibleWMS=("DisponibleWMS", "sum"))
    )


def _pedidos_activos_digip(
    df_pedidos_digip: pd.DataFrame | None,
) -> set[str]:
    if df_pedidos_digip is None or df_pedidos_digip.empty:
        return set()

    columna_codigo = _buscar_columna(
        df_pedidos_digip,
        ["Codigo", "Pedido", "Numero", "Número"],
        obligatoria=False,
    )

    if columna_codigo is None:
        return set()

    def extraer_pedido(valor: object) -> str:
        texto = _normalizar_texto(valor)
        if not texto:
            return ""

        partes = texto.split()
        if len(partes) >= 2:
            texto = partes[1]

        return texto.split("-")[0].strip()

    return {
        pedido
        for pedido in df_pedidos_digip[columna_codigo].map(extraer_pedido)
        if pedido
    }


def analizar_cobertura_pedidos_erp(
    tabla_detalle_erp: pd.DataFrame,
    tabla_pendientes_erp: pd.DataFrame,
    df_pedidos_digip: pd.DataFrame,
    df_disponible: pd.DataFrame,
    df_stock_erp: pd.DataFrame | None = None,
    tabla_clientes: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Analiza compromisos pendientes fuera de DIGIP.

    Fuente principal de cobertura:
    - est_1 del reporte ERP: stock aprobado bruto;
    - stk_res del reporte ERP: stock ya reservado;
    - disponible real para nuevas ventas: max(est_1 - stk_res, 0);
    - est_8 del reporte ERP: pendiente / tránsito.

    El disponible WMS se conserva como contraste para detectar
    diferencias entre ambos sistemas.

    La asignación de stock se realiza por código y en orden de fecha/pedido
    para evitar contar el mismo disponible más de una vez.
    """

    columnas_lineas = [
        "Pedido",
        "Fecha",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Planificacion",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "CantidadSolicitada",
        "DisponibleERPInicial",
        "TransitoERP",
        "DisponibleWMS",
        "DiferenciaERPvsWMS",
        "CantidadCubierta",
        "CantidadFaltante",
        "FaltanteLuegoTransito",
        "EstadoCobertura",
        "AlertaStock",
    ]
    columnas_resumen = [
        "Pedido",
        "Fecha",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Planificacion",
        "UnidadesSolicitadas",
        "UnidadesCubiertas",
        "UnidadesFaltantes",
        "UnidadesEnTransito",
        "FaltanteLuegoTransito",
        "PorcentajeCobertura",
        "CodigosConFaltante",
        "CodigosConDiferencia",
        "EstadoCobertura",
        "AlertaStock",
    ]

    if (
        tabla_detalle_erp is None
        or tabla_detalle_erp.empty
        or tabla_pendientes_erp is None
        or tabla_pendientes_erp.empty
    ):
        return (
            pd.DataFrame(columns=columnas_lineas),
            pd.DataFrame(columns=columnas_resumen),
        )

    detalle = tabla_detalle_erp.copy()
    pendientes = tabla_pendientes_erp.copy()

    col_pedido_det = _buscar_columna(
        detalle,
        ["Pedido", "Numero", "Número"],
    )
    col_articulo = _buscar_columna(
        detalle,
        ["ArticuloCodigo", "CodigoArticulo", "Artículo", "Articulo"],
    )
    col_descripcion = _buscar_columna(
        detalle,
        [
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "Descripción",
            "Descripcion",
        ],
        obligatoria=False,
    )
    col_cantidad = _buscar_columna(
        detalle,
        [
            "CantidadPendiente",
            "Cantidad",
            "Unidades",
            "Pendiente",
        ],
    )
    col_fecha_det = _buscar_columna(
        detalle,
        ["Fecha", "FechaPedido"],
        obligatoria=False,
    )

    col_pedido_pen = _buscar_columna(
        pendientes,
        [
            "nro_com",
            "Pedido",
            "Numero",
            "Número",
        ],
    )
    col_fecha_pen = _buscar_columna(
        pendientes,
        [
            "fec_com",
            "Fecha",
            "FechaPedido",
        ],
        obligatoria=False,
    )
    col_cliente_codigo = _buscar_columna(
        pendientes,
        [
            "cod_cli",
            "ClienteCodigo",
            "CodigoCliente",
        ],
        obligatoria=False,
    )
    col_cliente_descripcion = _buscar_columna(
        pendientes,
        [
            "nombre",
            "ClienteDescripcion",
            "Cliente",
        ],
        obligatoria=False,
    )
    col_distrito = _buscar_columna(
        pendientes,
        [
            "cod_dist",
            "CodigoDistrito",
            "Distrito",
        ],
        obligatoria=False,
    )

    base_pedidos = pd.DataFrame({
        "Pedido": pendientes[col_pedido_pen].map(_normalizar_texto),
        "FechaPedido": (
            pd.to_datetime(
                pendientes[col_fecha_pen],
                errors="coerce",
                dayfirst=True,
            )
            if col_fecha_pen
            else pd.NaT
        ),
        "ClienteCodigo": (
            pendientes[col_cliente_codigo].map(_normalizar_texto)
            if col_cliente_codigo
            else ""
        ),
        "ClienteDescripcion": (
            pendientes[col_cliente_descripcion]
            .fillna("")
            .astype(str)
            .str.strip()
            if col_cliente_descripcion
            else ""
        ),
        "CodigoDistrito": (
            pendientes[col_distrito].map(_normalizar_texto)
            if col_distrito
            else ""
        ),
    }).drop_duplicates("Pedido", keep="first")

    # -----------------------------------------------------
    # PLANIFICACIÓN DESDE MAESTRO DE CLIENTES
    # -----------------------------------------------------
    #
    # CodigoSucursal se arma con cod_cli + cod_dist.
    # Como el maestro puede conservar el distrito con distintos
    # formatos (1, 01, 001, con guion o sin guion), se generan
    # variantes y se selecciona la que exista realmente en el maestro.
    base_pedidos["ClienteCodigo"] = (
        base_pedidos["ClienteCodigo"].map(_normalizar_codigo)
    )
    base_pedidos["CodigoDistrito"] = (
        base_pedidos["CodigoDistrito"].map(_normalizar_texto)
    )
    base_pedidos["CodigoSucursal"] = ""
    base_pedidos["Planificacion"] = ""

    if tabla_clientes is not None and not tabla_clientes.empty:
        clientes = tabla_clientes.copy()

        col_cliente_maestro = _buscar_columna(
            clientes,
            [
                "CodigoSucursal",
                "ClienteCodigo",
                "CodigoCliente",
                "cod_cli",
            ],
            obligatoria=False,
        )
        col_planificacion = _buscar_columna(
            clientes,
            [
                "FrecuenciaEntrega",
                "DiaEntrega",
                "Planificacion",
                "Planificación",
            ],
            obligatoria=False,
        )

        if col_cliente_maestro and col_planificacion:
            maestro_planificacion = pd.DataFrame({
                "CodigoSucursal": (
                    clientes[col_cliente_maestro]
                    .map(_normalizar_codigo)
                ),
                "PlanificacionMaestro": (
                    clientes[col_planificacion]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.upper()
                ),
            })

            maestro_planificacion = (
                maestro_planificacion
                .loc[
                    maestro_planificacion["CodigoSucursal"].ne("")
                ]
                .drop_duplicates(
                    subset=["CodigoSucursal"],
                    keep="first",
                )
            )

            codigos_maestro = set(
                maestro_planificacion["CodigoSucursal"].tolist()
            )

            def construir_codigo_sucursal(fila: pd.Series) -> str:
                cliente = _normalizar_codigo(
                    fila.get("ClienteCodigo", "")
                )
                distrito = _normalizar_texto(
                    fila.get("CodigoDistrito", "")
                )

                if not cliente:
                    return ""

                if not distrito:
                    return cliente if cliente in codigos_maestro else ""

                # Corrige valores provenientes de Excel: 23.0 -> 23.
                if distrito.endswith(".0"):
                    distrito = distrito[:-2]

                variantes = [
                    f"{cliente}{distrito}",
                    f"{cliente}{distrito.zfill(2)}",
                    f"{cliente}{distrito.zfill(3)}",
                    f"{cliente}-{distrito}",
                    f"{cliente}-{distrito.zfill(2)}",
                    f"{cliente} {distrito}",
                    f"{cliente} {distrito.zfill(2)}",
                ]

                for variante in dict.fromkeys(variantes):
                    codigo = _normalizar_codigo(variante)
                    if codigo in codigos_maestro:
                        return codigo

                return _normalizar_codigo(
                    f"{cliente}{distrito.zfill(2)}"
                )

            base_pedidos["CodigoSucursal"] = (
                base_pedidos.apply(
                    construir_codigo_sucursal,
                    axis=1,
                )
            )

            base_pedidos = base_pedidos.merge(
                maestro_planificacion,
                on="CodigoSucursal",
                how="left",
                validate="many_to_one",
            )

            base_pedidos["Planificacion"] = (
                base_pedidos["PlanificacionMaestro"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            base_pedidos = base_pedidos.drop(
                columns=["PlanificacionMaestro"],
                errors="ignore",
            )

    pedidos_activos = _pedidos_activos_digip(df_pedidos_digip)

    base_pedidos = base_pedidos.loc[
        base_pedidos["Pedido"].ne("")
        & ~base_pedidos["Pedido"].isin(pedidos_activos)
    ].copy()

    if base_pedidos.empty:
        return (
            pd.DataFrame(columns=columnas_lineas),
            pd.DataFrame(columns=columnas_resumen),
        )

    lineas = pd.DataFrame({
        "Pedido": detalle[col_pedido_det].map(_normalizar_texto),
        "FechaDetalle": (
            pd.to_datetime(detalle[col_fecha_det], errors="coerce")
            if col_fecha_det
            else pd.NaT
        ),
        "ArticuloCodigo": detalle[col_articulo].map(_normalizar_codigo),
        "ArticuloDescripcion": (
            detalle[col_descripcion].fillna("").astype(str).str.strip()
            if col_descripcion
            else ""
        ),
        "CantidadSolicitada": _serie_numerica(detalle, col_cantidad),
    })

    lineas = lineas.loc[
        lineas["Pedido"].isin(set(base_pedidos["Pedido"]))
        & lineas["ArticuloCodigo"].ne("")
        & lineas["CantidadSolicitada"].gt(0)
    ].copy()

    if lineas.empty:
        return (
            pd.DataFrame(columns=columnas_lineas),
            pd.DataFrame(columns=columnas_resumen),
        )

    lineas = lineas.merge(
        base_pedidos,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )
    lineas["Fecha"] = lineas["FechaPedido"].fillna(
        lineas["FechaDetalle"]
    )
    lineas = lineas.drop(
        columns=["FechaPedido", "FechaDetalle"],
        errors="ignore",
    )

    stock_erp = _preparar_stock_erp(df_stock_erp)
    stock_wms = _preparar_stock_wms(df_disponible)

    lineas = lineas.merge(
        stock_erp,
        on="ArticuloCodigo",
        how="left",
        validate="many_to_one",
    )
    lineas = lineas.merge(
        stock_wms,
        on="ArticuloCodigo",
        how="left",
        validate="many_to_one",
    )

    for columna in [
        "DisponibleERP",
        "TransitoERP",
        "StockFisicoERP",
        "ReservadoERP",
        "DisponibleTotalERP",
        "DisponibleWMS",
    ]:
        lineas[columna] = (
            pd.to_numeric(lineas.get(columna, 0), errors="coerce")
            .fillna(0)
            .clip(lower=0)
        )

    # -----------------------------------------------------
    # DISPONIBLE REAL PARA NUEVAS VENTAS
    # -----------------------------------------------------
    #
    # Confirmado por operación:
    # est_1 representa stock aprobado bruto y stk_res contiene
    # las unidades ya reservadas. Para analizar nuevos pedidos,
    # el disponible real debe ser:
    #
    #     Disponible ERP real = est_1 - stk_res
    #
    # Nunca se permiten valores negativos.
    lineas["StockAprobadoERP"] = lineas["DisponibleERP"]

    lineas["DisponibleERP"] = (
        lineas["StockAprobadoERP"]
        - lineas["ReservadoERP"]
    ).clip(lower=0)

    sin_descripcion = lineas["ArticuloDescripcion"].eq("")
    lineas.loc[sin_descripcion, "ArticuloDescripcion"] = (
        lineas.loc[sin_descripcion, "ArticuloDescripcionERP"]
        .fillna("")
        .astype(str)
    )

    lineas = lineas.sort_values(
        ["ArticuloCodigo", "Fecha", "Pedido"],
        ascending=[True, True, True],
        na_position="last",
    ).reset_index(drop=True)

    lineas["AcumuladoPrevio"] = (
        lineas.groupby("ArticuloCodigo")["CantidadSolicitada"]
        .cumsum()
        - lineas["CantidadSolicitada"]
    )

    lineas["DisponibleERPInicial"] = lineas["DisponibleERP"]

    lineas["DisponibleERPAntesLinea"] = (
        lineas["DisponibleERPInicial"] - lineas["AcumuladoPrevio"]
    ).clip(lower=0)

    lineas["CantidadCubierta"] = (
        pd.concat(
            [
                lineas["CantidadSolicitada"],
                lineas["DisponibleERPAntesLinea"],
            ],
            axis=1,
        )
        .min(axis=1)
    )

    lineas["CantidadFaltante"] = (
        lineas["CantidadSolicitada"] - lineas["CantidadCubierta"]
    ).clip(lower=0)

    lineas["FaltanteAcumuladoPrevio"] = (
        lineas.groupby("ArticuloCodigo")["CantidadFaltante"]
        .cumsum()
        - lineas["CantidadFaltante"]
    )

    lineas["TransitoAntesLinea"] = (
        lineas["TransitoERP"] - lineas["FaltanteAcumuladoPrevio"]
    ).clip(lower=0)

    lineas["CantidadCubiertaTransito"] = (
        pd.concat(
            [
                lineas["CantidadFaltante"],
                lineas["TransitoAntesLinea"],
            ],
            axis=1,
        )
        .min(axis=1)
    )

    lineas["FaltanteLuegoTransito"] = (
        lineas["CantidadFaltante"] - lineas["CantidadCubiertaTransito"]
    ).clip(lower=0)

    lineas["DiferenciaERPvsWMS"] = (
        lineas["DisponibleERPInicial"] - lineas["DisponibleWMS"]
    )

    tolerancia = 0.5
    diferencia = lineas["DiferenciaERPvsWMS"].abs().gt(tolerancia)

    lineas["EstadoCobertura"] = "Con cobertura"
    lineas.loc[
        lineas["CantidadFaltante"].gt(0)
        & lineas["FaltanteLuegoTransito"].eq(0),
        "EstadoCobertura",
    ] = "Cobertura en tránsito"
    lineas.loc[
        lineas["FaltanteLuegoTransito"].gt(0),
        "EstadoCobertura",
    ] = "Sin cobertura"

    lineas["AlertaStock"] = ""
    lineas.loc[
        diferencia & lineas["DisponibleERPInicial"].gt(lineas["DisponibleWMS"]),
        "AlertaStock",
    ] = "ERP mayor que WMS"
    lineas.loc[
        diferencia & lineas["DisponibleWMS"].gt(lineas["DisponibleERPInicial"]),
        "AlertaStock",
    ] = "WMS mayor que ERP"
    lineas.loc[
        lineas["DisponibleERPInicial"].gt(0)
        & lineas["DisponibleWMS"].eq(0),
        "AlertaStock",
    ] = "Hay ERP, sin stock WMS"
    lineas.loc[
        lineas["DisponibleWMS"].gt(0)
        & lineas["DisponibleERPInicial"].eq(0),
        "AlertaStock",
    ] = "Hay WMS, sin disponible ERP"

    orden_estado = {
        "Sin cobertura": 0,
        "Cobertura en tránsito": 1,
        "Con cobertura": 2,
    }

    lineas["_OrdenEstado"] = (
        lineas["EstadoCobertura"].map(orden_estado).fillna(9)
    )

    resumen = (
        lineas.groupby(
            [
                "Pedido",
                "Fecha",
                "ClienteCodigo",
                "ClienteDescripcion",
                "Planificacion",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            UnidadesSolicitadas=("CantidadSolicitada", "sum"),
            UnidadesCubiertas=("CantidadCubierta", "sum"),
            UnidadesFaltantes=("CantidadFaltante", "sum"),
            UnidadesEnTransito=("CantidadCubiertaTransito", "sum"),
            FaltanteLuegoTransito=("FaltanteLuegoTransito", "sum"),
            CodigosConFaltante=(
                "ArticuloCodigo",
                lambda serie: int(
                    lineas.loc[
                        serie.index,
                        "CantidadFaltante",
                    ].gt(0).sum()
                ),
            ),
            CodigosConDiferencia=(
                "ArticuloCodigo",
                lambda serie: int(
                    lineas.loc[
                        serie.index,
                        "AlertaStock",
                    ].ne("").sum()
                ),
            ),
            _OrdenEstado=("_OrdenEstado", "min"),
            Alertas=(
                "AlertaStock",
                lambda serie: " | ".join(
                    dict.fromkeys(
                        valor
                        for valor in serie.astype(str)
                        if valor.strip()
                    )
                ),
            ),
        )
    )

    resumen["PorcentajeCobertura"] = (
        resumen["UnidadesCubiertas"]
        .div(resumen["UnidadesSolicitadas"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .clip(lower=0, upper=100)
    )

    inverso_estado = {valor: clave for clave, valor in orden_estado.items()}
    resumen["EstadoCobertura"] = (
        resumen["_OrdenEstado"]
        .map(inverso_estado)
        .fillna("Con cobertura")
    )
    resumen["AlertaStock"] = resumen["Alertas"].fillna("")

    for columna in [
        "CantidadSolicitada",
        "DisponibleERPInicial",
        "TransitoERP",
        "DisponibleWMS",
        "DiferenciaERPvsWMS",
        "CantidadCubierta",
        "CantidadFaltante",
        "FaltanteLuegoTransito",
    ]:
        lineas[columna] = (
            pd.to_numeric(lineas[columna], errors="coerce")
            .fillna(0)
            .round(0)
            .astype(int)
        )

    for columna in [
        "UnidadesSolicitadas",
        "UnidadesCubiertas",
        "UnidadesFaltantes",
        "UnidadesEnTransito",
        "FaltanteLuegoTransito",
        "CodigosConFaltante",
        "CodigosConDiferencia",
    ]:
        resumen[columna] = (
            pd.to_numeric(resumen[columna], errors="coerce")
            .fillna(0)
            .round(0)
            .astype(int)
        )

    lineas = (
        lineas[columnas_lineas]
        .sort_values(
            [
                "FaltanteLuegoTransito",
                "CantidadFaltante",
                "ArticuloCodigo",
                "Fecha",
            ],
            ascending=[False, False, True, True],
        )
        .reset_index(drop=True)
    )

    resumen = (
        resumen[columnas_resumen]
        .sort_values(
            [
                "FaltanteLuegoTransito",
                "UnidadesFaltantes",
                "Fecha",
            ],
            ascending=[False, False, True],
        )
        .reset_index(drop=True)
    )

    return lineas, resumen
