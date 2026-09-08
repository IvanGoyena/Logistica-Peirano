from __future__ import annotations

import pandas as pd
import streamlit as st

from models.tareas_modulo.pedidos_tareas import construir_tabla_pedidos_tareas
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
    Por ejemplo, dentro de "Control Agosto 2026", 08/25/2026 es 25 de agosto.
    """
    return pd.to_datetime(
        serie,
        errors="coerce",
        format="mixed",
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
        .str.replace(r"\.0+$", "", regex=True)
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


def _normalizar_id(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    texto = texto.replace(".0", "") if texto.endswith(".0") else texto
    return texto


def _normalizar_pedido_erp(valor: object) -> str:
    """Convierte variantes DIGIP/ERP a la clave numérica del pedido."""
    texto = _normalizar_id(valor)
    if not texto:
        return ""
    # DIGIP: '0001  215205-1' -> '215205'
    texto = texto.split("-")[0].strip()
    partes = texto.split()
    if partes:
        texto = partes[-1]
    return texto


def _normalizar_sector(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().upper()
    equivalencias = {
        "NAC": "NACIONAL",
        "IMP": "IMPORTADO",
        "BLI": "BLISTER",
        "BAC": "BACHAS",
        "SAN": "SANITARIOS",
        "REP": "REPUESTOS",
        "FLE": "FLEXIBLES",
        "ACC": "ACCESORIOS",
        "VAR": "VARIOS",
    }
    return equivalencias.get(texto, texto)


def _extraer_codigo_articulo(descripcion: object) -> str:
    """Informe Tareas solo informa el código cuando la tarea tiene 1 artículo."""
    if pd.isna(descripcion):
        return ""
    texto = str(descripcion).strip()
    if not texto:
        return ""
    # Ej.: '81-180 - DUCHA ...' -> '81-180'
    return texto.split(" - ", 1)[0].strip().upper()


def enriquecer_tareas_con_detalle(
    tabla_tareas: pd.DataFrame,
    df_detalle: pd.DataFrame,
    df_articulos: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reparte unidades/SKUs/familias a nivel tarea.

    Versión optimizada:
    - prepara el detalle ERP una sola vez;
    - genera índices agregados por Pedido+Artículo y Pedido+Sector;
    - evita filtrar/copiar df_detalle por cada fila de tarea.

    Mantiene la misma prioridad:
    1) artículo exacto cuando DIGIP informa un único artículo;
    2) Pedido + Área/Sector para tareas de varios artículos;
    3) sin correspondencia si no puede asignarse de forma segura.
    """
    if tabla_tareas is None or tabla_tareas.empty:
        return tabla_tareas, pd.DataFrame()

    if (
        df_detalle is None
        or df_detalle.empty
        or df_articulos is None
        or df_articulos.empty
    ):
        return tabla_tareas, pd.DataFrame()

    tareas = tabla_tareas.copy()
    detalle = df_detalle.copy()
    maestro = df_articulos.copy()

    requeridas_detalle = {"nro_com", "cod_art", "can_art"}
    if (
        not requeridas_detalle.issubset(detalle.columns)
        or "COD_ART" not in maestro.columns
    ):
        return tareas, pd.DataFrame()

    # ------------------------------------------------------
    # NORMALIZACIÓN DEL DETALLE ERP
    # ------------------------------------------------------
    detalle["_PedidoKey"] = detalle["nro_com"].map(_normalizar_pedido_erp)
    detalle["_ArticuloKey"] = (
        detalle["cod_art"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0+$", "", regex=True)
    )
    detalle["_Cantidad"] = pd.to_numeric(
        detalle["can_art"], errors="coerce"
    ).fillna(0)

    # ------------------------------------------------------
    # MAESTRO DE ARTÍCULOS
    # ------------------------------------------------------
    maestro["_ArticuloKey"] = (
        maestro["COD_ART"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0+$", "", regex=True)
    )

    cols_maestro = ["_ArticuloKey"]
    for c in ["Sectorizacion", "Familia", "Familia_2"]:
        if c in maestro.columns:
            cols_maestro.append(c)

    maestro = (
        maestro[cols_maestro]
        .drop_duplicates("_ArticuloKey", keep="first")
    )

    detalle = detalle.merge(
        maestro,
        on="_ArticuloKey",
        how="left",
        validate="many_to_one",
    )

    if "Sectorizacion" in detalle.columns:
        detalle["_SectorKey"] = detalle["Sectorizacion"].map(
            _normalizar_sector
        )
    else:
        detalle["_SectorKey"] = ""

    # ------------------------------------------------------
    # NORMALIZACIÓN DE TAREAS
    # ------------------------------------------------------
    tareas["_PedidoKey"] = tareas.get(
        "Pedido",
        pd.Series(index=tareas.index, dtype=object),
    ).map(_normalizar_pedido_erp)

    tareas["_AreaKey"] = tareas["Area"].map(_normalizar_sector)

    tareas["_ArticuloExacto"] = tareas.get(
        "_ArticulosDescripcionTarea",
        pd.Series(index=tareas.index, dtype=object),
    ).map(_extraer_codigo_articulo)

    tareas["_CantArticulosTarea"] = pd.to_numeric(
        tareas.get("_ArticulosTarea", 0),
        errors="coerce",
    ).fillna(0).astype(int)

    # ------------------------------------------------------
    # AGREGADOS PRECALCULADOS
    # ------------------------------------------------------
    # Antes se hacía:
    # detalle.loc[detalle["_PedidoKey"].eq(pedido)].copy()
    # para CADA tarea. Ahora todo se calcula una sola vez.

    por_articulo = (
        detalle.groupby(
            ["_PedidoKey", "_ArticuloKey"],
            as_index=False,
            dropna=False,
        )
        .agg(
            Unidades=("_Cantidad", "sum"),
        )
    )

    # Pedido+Artículo siempre representa un SKU exacto.
    por_articulo["SKUs"] = (
        por_articulo["Unidades"].ne(0).astype(int)
    )
    por_articulo["Familias"] = ""

    if "Sectorizacion" in detalle.columns:
        # Texto de familias/sectores por Pedido + Sector.
        sector_etiquetas = (
            detalle.assign(
                _Etiqueta=detalle["Sectorizacion"]
                .fillna("Sin sector")
                .astype(str)
                .str.strip()
            )
            .groupby(
                ["_PedidoKey", "_SectorKey", "_Etiqueta"],
                dropna=False,
            )["_Cantidad"]
            .sum()
            .reset_index()
        )

        sector_etiquetas = sector_etiquetas.loc[
            sector_etiquetas["_Cantidad"].ne(0)
        ].copy()

        if not sector_etiquetas.empty:
            sector_etiquetas["Parte"] = (
                sector_etiquetas["_Etiqueta"].astype(str)
                + " ("
                + sector_etiquetas["_Cantidad"].astype(int).astype(str)
                + ")"
            )
            textos_sector = (
                sector_etiquetas
                .sort_values(
                    ["_PedidoKey", "_SectorKey", "_Cantidad"],
                    ascending=[True, True, False],
                )
                .groupby(
                    ["_PedidoKey", "_SectorKey"],
                    dropna=False,
                )["Parte"]
                .agg(" | ".join)
                .rename("Familias")
                .reset_index()
            )
        else:
            textos_sector = pd.DataFrame(
                columns=["_PedidoKey", "_SectorKey", "Familias"]
            )
    else:
        textos_sector = pd.DataFrame(
            columns=["_PedidoKey", "_SectorKey", "Familias"]
        )

    por_sector = (
        detalle.groupby(
            ["_PedidoKey", "_SectorKey"],
            as_index=False,
            dropna=False,
        )
        .agg(
            Unidades=("_Cantidad", "sum"),
            SKUs=(
                "_ArticuloKey",
                lambda s: int(
                    s[
                        detalle.loc[s.index, "_Cantidad"].ne(0)
                    ].nunique()
                ),
            ),
        )
    )

    por_sector = por_sector.merge(
        textos_sector,
        on=["_PedidoKey", "_SectorKey"],
        how="left",
    )
    por_sector["Familias"] = por_sector["Familias"].fillna("")

    mapa_articulo = {
        (str(r["_PedidoKey"]), str(r["_ArticuloKey"])): (
            int(r["Unidades"]),
            int(r["SKUs"]),
            str(r["Familias"]),
        )
        for _, r in por_articulo.iterrows()
    }

    mapa_sector = {
        (str(r["_PedidoKey"]), str(r["_SectorKey"])): (
            int(r["Unidades"]),
            int(r["SKUs"]),
            str(r["Familias"]),
        )
        for _, r in por_sector.iterrows()
    }

    # ------------------------------------------------------
    # LOOKUPS O(1) POR TAREA
    # ------------------------------------------------------
    unidades: list[int] = []
    skus: list[int] = []
    familias: list[str] = []
    metodos: list[str] = []
    alertas: list[dict[str, object]] = []

    columnas_lookup = [
        "_PedidoKey",
        "_AreaKey",
        "_ArticuloExacto",
        "_CantArticulosTarea",
        "Preparacion",
        "Area",
    ]

    for fila in tareas[columnas_lookup].itertuples(index=False, name=None):
        (
            pedido,
            area,
            articulo_exacto,
            cant_articulos,
            preparacion,
            area_visible,
        ) = fila

        pedido = "" if pd.isna(pedido) else str(pedido)
        area = "" if pd.isna(area) else str(area)
        articulo_exacto = (
            "" if pd.isna(articulo_exacto) else str(articulo_exacto)
        )

        asignacion = None
        metodo = "sin_correspondencia"

        if cant_articulos == 1 and articulo_exacto:
            asignacion = mapa_articulo.get(
                (pedido, articulo_exacto)
            )
            if asignacion is not None:
                metodo = "articulo_exacto"

        if asignacion is None and area:
            asignacion = mapa_sector.get((pedido, area))
            if asignacion is not None:
                metodo = "sectorizacion"

        if asignacion is None:
            unidades.append(0)
            skus.append(0)
            familias.append("⚠ Sin correspondencia")
            metodos.append(metodo)

            if pedido:
                alertas.append(
                    {
                        "Preparacion": preparacion,
                        "Pedido": pedido,
                        "Area": area_visible,
                        "Motivo": (
                            "No se pudo asignar detalle ERP a esta tarea "
                            "sin duplicar unidades."
                        ),
                    }
                )
            continue

        total_unidades, total_skus, texto_familias = asignacion
        unidades.append(total_unidades)
        skus.append(total_skus)
        familias.append(texto_familias)
        metodos.append(metodo)

    tareas["Unidades"] = unidades
    tareas["SKUs"] = skus
    tareas["Familias"] = familias
    tareas["_MetodoEnriquecimiento"] = metodos

    alertas_df = pd.DataFrame(alertas)

    tareas = tareas.drop(
        columns=[
            "_PedidoKey",
            "_AreaKey",
            "_ArticuloExacto",
            "_CantArticulosTarea",
        ],
        errors="ignore",
    )

    return tareas, alertas_df


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
    tabla_pedidos = construir_tabla_pedidos_tareas(
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

    # Enriquecimiento a nivel TAREA: evita repetir TotalUnidades/TotalSKUs
    # del pedido en cada sector/preparación.
    tabla_tareas, alertas_sectorizacion = enriquecer_tareas_con_detalle(
        tabla_tareas,
        df_detalle,
        df_articulos,
    )

    tabla_operativa = obtener_tabla_operativa(tabla_tareas)

    # ------------------------------------------------------
    # COMPATIBILIDAD DEL RESUMEN OPERATIVO
    # ------------------------------------------------------
    # models.tareas.obtener_resumen_operativo todavía utiliza
    # la clave histórica "PedidoId". El reporte nuevo de DIGIP
    # cambió ese encabezado.
    #
    # En vez de volver a depender del archivo crudo, usamos la
    # tabla de pedidos ya normalizada y agregamos la clave de
    # compatibilidad que espera el KPI.
    pedidos_resumen = tabla_pedidos.copy()

    if "Pedido" in pedidos_resumen.columns:
        pedidos_resumen["PedidoId"] = (
            pedidos_resumen["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    resumen = obtener_resumen_operativo(
        tabla_tareas,
        pedidos_resumen,
    )

    # El avance necesita la historia reciente COMPLETA, incluidos pedidos
    # que ya cerraron. La tabla visual sigue usando solo pedidos abiertos.
    avance_despachos, despachos_sin_iniciar = obtener_avance_despachos(tabla_tareas)
    carros_criticos = obtener_carros_criticos(tabla_operativa, avance_despachos)
    pendiente_pick = obtener_pendiente_pick(tabla_operativa, tabla_pedidos)
    control_dia_anterior = obtener_control_dia_anterior(df_control)

    mascara_estado_activo = (
        tabla_pedidos["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["PENDIENTE", "PREPARACION"])
    )

    pedidos_sin_preparacion = tabla_pedidos.loc[
        mascara_estado_activo
        & tabla_pedidos["PreparacionID"].isna()
    ].copy()

    # ------------------------------------------------------
    # NORMALIZAR CLAVE DE PREPARACIÓN ANTES DEL MERGE
    # ------------------------------------------------------
    # Informe Tareas puede traer Preparacion como float (ej. 12345.0)
    # y Pedidos DIGIP la trae como string. Pandas no permite merge
    # entre float64 y string, por eso normalizamos ambos lados.
    tabla_tareas = tabla_tareas.copy()
    tabla_pedidos = tabla_pedidos.copy()

    tabla_tareas["Preparacion"] = (
        tabla_tareas["Preparacion"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )

    tabla_pedidos["PreparacionID"] = (
        tabla_pedidos["PreparacionID"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )

    tabla_tareas["Preparacion"] = tabla_tareas["Preparacion"].where(
        tabla_tareas["Preparacion"].notna()
        & tabla_tareas["Preparacion"].ne(""),
        pd.NA,
    )

    tabla_pedidos["PreparacionID"] = tabla_pedidos["PreparacionID"].where(
        tabla_pedidos["PreparacionID"].notna()
        & tabla_pedidos["PreparacionID"].ne(""),
        pd.NA,
    )

    tareas_unidades = tabla_operativa.merge(
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

    estado_tarea_operativa = (
        tabla_operativa["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    mascara_abierta_operativa = (
        tabla_operativa["Categoria"].isin(["Pendiente", "En Curso"])
        | estado_tarea_operativa.str.contains("SUSPEND", na=False)
    )

    preparaciones_activas = (
        tabla_operativa.loc[
            mascara_abierta_operativa,
            "Preparacion",
        ]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    # Segunda clave para tareas viejas: Pedido ERP.
    # Así una preparación abierta de la semana anterior no se pierde del gráfico
    # si el ID de preparación histórico difiere de la referencia actual.
    if "Pedido" in tabla_operativa.columns:
        pedidos_activos_serie = (
            tabla_operativa.loc[
                mascara_abierta_operativa,
                "Pedido",
            ]
            .dropna()
            .map(_normalizar_pedido_erp)
        )
        pedidos_activos = set(
            pedidos_activos_serie.loc[
                pedidos_activos_serie.ne("")
            ].tolist()
        )
    else:
        pedidos_activos = set()

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
        mascara_sector_activo = (
            tabla_pedidos["PreparacionID"]
            .astype("string")
            .str.strip()
            .isin(preparaciones_activas)
        )

        if pedidos_activos and "Pedido" in tabla_pedidos.columns:
            pedido_key_tabla = tabla_pedidos["Pedido"].map(
                _normalizar_pedido_erp
            )
            mascara_sector_activo = (
                mascara_sector_activo
                | pedido_key_tabla.isin(pedidos_activos)
            )

        pedidos_sector_activos = tabla_pedidos.loc[
            mascara_sector_activo
        ].copy()

        # Si coincidió por Preparación y por Pedido, la fila sigue contando una vez.
        clave_dedupe = [
            col for col in ["Pedido", "PreparacionID"]
            if col in pedidos_sector_activos.columns
        ]
        if clave_dedupe:
            pedidos_sector_activos = (
                pedidos_sector_activos
                .drop_duplicates(subset=clave_dedupe, keep="last")
            )

        familias_operativas = (
            pedidos_sector_activos[columnas_sector]
            .apply(pd.to_numeric, errors="coerce")
            .fillna(0)
            .sum()
            .sort_values(ascending=False)
        )
        familias_operativas = familias_operativas.loc[
            familias_operativas.gt(0)
        ]
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
        "alertas_sectorizacion": alertas_sectorizacion,
    }
