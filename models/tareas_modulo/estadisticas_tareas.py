from __future__ import annotations

import pandas as pd


def _texto(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def _id(s: pd.Series) -> pd.Series:
    return _texto(s).str.replace(r"\.0+$", "", regex=True)


def _fecha_live(s: pd.Series) -> pd.Series:
    # Filtrar Preparación se publica en formato DD/MM/YYYY.
    return pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")


def _fecha_analitico(s: pd.Series) -> pd.Series:
    # Los analíticos de DIGIP se descargan en formato MM/DD/YYYY.
    return pd.to_datetime(s, errors="coerce", dayfirst=False, format="mixed")


def construir_base_estadisticas(
    df: pd.DataFrame,
    df_articulos: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normaliza Filtrar Preparación y excluye únicamente pedidos TR / RM."""
    if df is None or df.empty:
        return pd.DataFrame()

    t = df.copy()

    for c in [
        "CodigoArticulo", "Articulo", "PedidoCodigos", "DespachoDescripcion",
        "TareaUsuarioCompleto", "ControlContenedorUsuarioCompleto",
    ]:
        if c in t.columns:
            t[c] = _texto(t[c])

    for c in ["Unidades", "UnidadesReservada", "UnidadesSatisfecha", "ContenedorUnidades"]:
        if c in t.columns:
            t[c] = pd.to_numeric(t[c], errors="coerce").fillna(0)

    for c in ["FechaHoraEstado", "TareaFechaHoraEstado", "ControlContenedorFechaHoraEstado"]:
        if c in t.columns:
            t[c] = _fecha_live(t[c])

    for c in ["Id", "TareaId", "ControlContenedorId", "ContenedorDetalleId"]:
        if c in t.columns:
            t[c] = _id(t[c])

    if "CodigoArticulo" in t.columns:
        t["CodigoArticulo"] = _texto(t["CodigoArticulo"]).str.upper().str.replace(r"\.0$", "", regex=True)

    # SOLO se eliminan pedidos cuyo código empieza con TR o RM.
    if "PedidoCodigos" in t.columns:
        pedido = _texto(t["PedidoCodigos"]).str.upper()
        excluir = pedido.str.match(r"^(?:TR|RM)(?:\s|$)", na=False)
        t = t.loc[~excluir].copy()

    if df_articulos is not None and not df_articulos.empty and "COD_ART" in df_articulos.columns:
        m = df_articulos.copy()
        m["COD_ART"] = _texto(m["COD_ART"]).str.upper().str.replace(r"\.0$", "", regex=True)
        cols = [c for c in [
            "COD_ART", "DESCRIP", "Familia", "Familia_2", "Sector", "Sectorizacion",
            "Marca", "Tipo", "Origen", "Gama", "Rubro",
        ] if c in m.columns]
        m = m[cols].drop_duplicates("COD_ART", keep="first")
        t = t.merge(m, left_on="CodigoArticulo", right_on="COD_ART", how="left", validate="many_to_one")
        t = t.drop(columns=["COD_ART"], errors="ignore")

    return t.reset_index(drop=True)


def _mapas_live(base: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mapas para enriquecer analíticos con preparación, despacho y usuario completo."""
    if base is None or base.empty:
        return pd.DataFrame(), pd.DataFrame()

    comun = [c for c in ["Id", "PedidoCodigos", "DespachoDescripcion"] if c in base.columns]

    mapa_tarea = pd.DataFrame()
    if "TareaId" in base.columns:
        cols = ["TareaId"] + comun + [
            c for c in ["TareaUsuarioCompleto"]
            if c in base.columns
        ]

        # Filtrar Preparación es también el respaldo para reconstruir
        # unidades de Picking cuando el Analítico trae UnidadesTarea = 0.
        live_tarea = base.loc[base["TareaId"].ne("")].copy()

        mapa_tarea = (
            live_tarea[cols]
            .drop_duplicates("TareaId", keep="last")
        )

        if "ContenedorUnidades" in live_tarea.columns:
            live_tarea["_UnidadesPickingLive"] = pd.to_numeric(
                live_tarea["ContenedorUnidades"],
                errors="coerce",
            ).fillna(0)

            # Un TareaId puede repetirse por líneas/contenedores. Para no
            # duplicar la cantidad de una misma línea, usamos la mayor cantidad
            # visible por TareaId + artículo cuando existe CodigoArticulo.
            if "CodigoArticulo" in live_tarea.columns:
                live_tarea["_ArticuloPickingKey"] = (
                    _texto(live_tarea["CodigoArticulo"])
                    .str.upper()
                    .str.replace(r"\.0+$", "", regex=True)
                )
                unidades_live = (
                    live_tarea
                    .groupby(
                        ["TareaId", "_ArticuloPickingKey"],
                        as_index=False,
                        dropna=False,
                    )["_UnidadesPickingLive"]
                    .max()
                    .groupby("TareaId", as_index=False)["_UnidadesPickingLive"]
                    .sum()
                )
            else:
                unidades_live = (
                    live_tarea
                    .groupby("TareaId", as_index=False)["_UnidadesPickingLive"]
                    .max()
                )

            mapa_tarea = mapa_tarea.merge(
                unidades_live,
                on="TareaId",
                how="left",
                validate="one_to_one",
            )

    mapa_control = pd.DataFrame()
    if "ControlContenedorId" in base.columns:
        cols = ["ControlContenedorId"] + comun + [c for c in ["ControlContenedorUsuarioCompleto"] if c in base.columns]
        mapa_control = base.loc[base["ControlContenedorId"].ne(""), cols].drop_duplicates("ControlContenedorId", keep="last")

    return mapa_tarea, mapa_control


def _enriquecer_articulos(df: pd.DataFrame, df_articulos: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty or df_articulos is None or df_articulos.empty or "COD_ART" not in df_articulos.columns:
        return df
    if "CodigoArticulo" not in df.columns:
        return df

    x = df.copy()
    x["CodigoArticulo"] = _texto(x["CodigoArticulo"]).str.upper().str.replace(r"\.0$", "", regex=True)
    m = df_articulos.copy()
    m["COD_ART"] = _texto(m["COD_ART"]).str.upper().str.replace(r"\.0$", "", regex=True)
    cols = [c for c in ["COD_ART", "DESCRIP", "Familia", "Familia_2", "Sector", "Sectorizacion"] if c in m.columns]
    m = m[cols].drop_duplicates("COD_ART", keep="first")
    x = x.merge(m, left_on="CodigoArticulo", right_on="COD_ART", how="left", validate="many_to_one")
    return x.drop(columns=["COD_ART"], errors="ignore")


def _picking_analitico(
    analitico: pd.DataFrame,
    base_live: pd.DataFrame,
    df_articulos: pd.DataFrame | None,
) -> pd.DataFrame:
    if analitico is None or analitico.empty:
        return pd.DataFrame()

    a = analitico.copy()
    if "Tipo" in a.columns:
        a = a.loc[_texto(a["Tipo"]).str.lower().eq("preparacion")].copy()
    if a.empty or "TareaId" not in a.columns:
        return pd.DataFrame()

    a["TareaId"] = _id(a["TareaId"])
    a["FechaEvento"] = _fecha_analitico(a["FechaFin"])
    a["Usuario"] = _texto(a["Usuario"])
    a["CodigoArticulo"] = _texto(a.get("CodigoArticulo", pd.Series("", index=a.index))).str.upper()
    a["UnidadesDetalle"] = pd.to_numeric(a.get("UnidadesDetalle", 0), errors="coerce").fillna(0)
    a["UnidadesTarea"] = pd.to_numeric(a.get("UnidadesTarea", 0), errors="coerce").fillna(0)
    a["CuantasTareas"] = pd.to_numeric(a.get("CuantasTareas", 1), errors="coerce").fillna(1)

    # Si el TareaId existe en Filtrar ya depurado, queda habilitado. Esto mantiene
    # la exclusión TR/RM también sobre el analítico cuando tenemos correspondencia.
    mapa_tarea, _ = _mapas_live(base_live)
    if not mapa_tarea.empty:
        ids_live = set(mapa_tarea["TareaId"].tolist())
        ids_analitico_con_match = a["TareaId"].isin(ids_live)
        # No descartamos IDs históricos que no existen en el Filtrar disponible.
        if ids_analitico_con_match.any():
            # Para el período cubierto por Filtrar, solo usamos IDs habilitados.
            min_live = base_live["TareaFechaHoraEstado"].min() if "TareaFechaHoraEstado" in base_live else pd.NaT
            if pd.notna(min_live):
                a = a.loc[(a["FechaEvento"] < min_live.normalize()) | a["TareaId"].isin(ids_live)].copy()

        a = a.merge(mapa_tarea, on="TareaId", how="left", validate="many_to_one")

    a["Proceso"] = "Picking"
    a["EventoId"] = a["TareaId"]
    a["LineaId"] = a.index.astype(str)
    a["Fecha"] = a["FechaEvento"].dt.normalize()
    a["Hora"] = a["FechaEvento"].dt.hour
    a["Fuente"] = "Analítico"
    a["DatoConsolidado"] = True

    # UnidadesTarea y CuantasTareas se repiten en todas las líneas: se imputan
    # una sola vez por TareaId. Las líneas sí representan los pickeos.
    primera = ~a.duplicated("TareaId", keep="first")
    a["UnidadesProceso"] = 0.0

    # Fuente principal: UnidadesTarea del Analítico.
    unidades_tarea = pd.to_numeric(
        a["UnidadesTarea"],
        errors="coerce",
    ).fillna(0)

    # Fallback: si DIGIP deja UnidadesTarea en 0, recuperamos las unidades
    # pickeadas desde Filtrar Preparación (UnidadesSatisfecha), cruzando
    # por el mismo TareaId. Se imputa una sola vez por tarea para evitar
    # multiplicarla por cada línea del analítico.
    if "_UnidadesPickingLive" in a.columns:
        unidades_live = pd.to_numeric(
            a["_UnidadesPickingLive"],
            errors="coerce",
        ).fillna(0)
        unidades_finales = unidades_tarea.where(
            unidades_tarea.gt(0),
            unidades_live,
        )
    else:
        unidades_finales = unidades_tarea

    a.loc[primera, "UnidadesProceso"] = unidades_finales.loc[primera]

    a["EventosMetric"] = 0.0
    a.loc[primera, "EventosMetric"] = a.loc[primera, "CuantasTareas"]
    a["PickeosMetric"] = 1.0

    if "Id" not in a.columns:
        a["Id"] = a["TareaId"]
    a["Id"] = _id(a["Id"]).where(_id(a["Id"]).ne(""), a["TareaId"])

    return _enriquecer_articulos(a, df_articulos)


def _control_analitico(
    analitico: pd.DataFrame,
    base_live: pd.DataFrame,
    df_articulos: pd.DataFrame | None,
) -> pd.DataFrame:
    if analitico is None or analitico.empty or "ControlContenedorId" not in analitico.columns:
        return pd.DataFrame()

    a = analitico.copy()
    a["ControlContenedorId"] = _id(a["ControlContenedorId"])
    a["FechaEvento"] = _fecha_analitico(a["FechaFin"])
    a["UsuarioAnalitico"] = _texto(a["Usuario"])
    a["CodigoArticulo"] = _texto(a.get("CodigoArticulo", pd.Series("", index=a.index))).str.upper()
    a["Unidades"] = pd.to_numeric(a.get("Unidades", 0), errors="coerce").fillna(0)

    _, mapa_control = _mapas_live(base_live)
    if not mapa_control.empty:
        ids_live = set(mapa_control["ControlContenedorId"].tolist())
        min_live = base_live["ControlContenedorFechaHoraEstado"].min() if "ControlContenedorFechaHoraEstado" in base_live else pd.NaT
        if pd.notna(min_live):
            a = a.loc[(a["FechaEvento"] < min_live.normalize()) | a["ControlContenedorId"].isin(ids_live)].copy()
        a = a.merge(mapa_control, on="ControlContenedorId", how="left", validate="many_to_one")

    if "ControlContenedorUsuarioCompleto" in a.columns:
        usuario_full = _texto(a["ControlContenedorUsuarioCompleto"])
        a["Usuario"] = usuario_full.where(usuario_full.ne(""), a["UsuarioAnalitico"])
    else:
        a["Usuario"] = a["UsuarioAnalitico"]

    a["Proceso"] = "Control"
    a["EventoId"] = a["ControlContenedorId"]
    a["LineaId"] = a.index.astype(str)
    a["Fecha"] = a["FechaEvento"].dt.normalize()
    a["Hora"] = a["FechaEvento"].dt.hour
    a["Fuente"] = "Analítico"
    a["DatoConsolidado"] = True
    a["UnidadesProceso"] = a["Unidades"]  # en Control, Unidades es por línea y debe sumarse
    a["PickeosMetric"] = 1.0

    # El WMS cuenta más "tareas" de embalaje que IDs presentes en el analítico.
    # El conteo oficial se completa después con los ControlContenedorId de Filtrar.
    primera = ~a.duplicated("ControlContenedorId", keep="first")
    a["EventosMetric"] = 0.0
    a.loc[primera, "EventosMetric"] = 1.0

    if "Id" not in a.columns:
        a["Id"] = a["ControlContenedorId"]
    a["Id"] = _id(a["Id"]).where(_id(a["Id"]).ne(""), a["ControlContenedorId"])

    return _enriquecer_articulos(a, df_articulos)


def _live_eventos(base: pd.DataFrame, proceso: str) -> pd.DataFrame:
    if base is None or base.empty:
        return pd.DataFrame()
    picking = proceso.lower() == "picking"
    fecha_col = "TareaFechaHoraEstado" if picking else "ControlContenedorFechaHoraEstado"
    usuario_col = "TareaUsuarioCompleto" if picking else "ControlContenedorUsuarioCompleto"
    id_col = "TareaId" if picking else "ControlContenedorId"
    requeridas = [fecha_col, usuario_col, id_col]
    if any(c not in base.columns for c in requeridas):
        return pd.DataFrame()

    e = base.copy()
    e["Usuario"] = _texto(e[usuario_col])
    e["EventoId"] = _id(e[id_col])
    e["FechaEvento"] = e[fecha_col]
    e = e.loc[e["Usuario"].ne("") & e["EventoId"].ne("") & e["FechaEvento"].notna()].copy()
    e["Proceso"] = "Picking" if picking else "Control"
    e["Fecha"] = e["FechaEvento"].dt.normalize()
    e["Hora"] = e["FechaEvento"].dt.hour
    e["Fuente"] = "En vivo"
    e["DatoConsolidado"] = False
    e["LineaId"] = _id(e["ContenedorDetalleId"]) if "ContenedorDetalleId" in e.columns else e.index.astype(str)
    # IMPORTANTE:
    # Picking y Control NO usan la misma columna de unidades en Filtrar Preparación.
    #
    # - Picking: ContenedorUnidades representa las unidades efectivamente pickeadas.
    # - Control: ContenedorUnidades representa las unidades efectivamente controladas.
    #
    # La columna de Picking y la de Control se interpretan según el proceso; en ambos casos ContenedorUnidades representa el contenido efectivo del contenedor.
    # corresponde a la línea/preparación y puede ser mayor que la cantidad del
    # contenedor realmente controlado.
    if picking:
        # En Filtrar Preparación real, UnidadesSatisfecha puede quedar en 0
        # aun cuando el pickeo ya ocurrió. ContenedorUnidades refleja la
        # cantidad efectivamente contenida/pickeada por línea.
        unidades = pd.to_numeric(
            e.get(
                "ContenedorUnidades",
                e.get("Unidades", 0),
            ),
            errors="coerce",
        ).fillna(0)
    else:
        unidades = pd.to_numeric(
            e.get("ContenedorUnidades", e.get("Unidades", 0)),
            errors="coerce",
        ).fillna(0)

    e["UnidadesProceso"] = unidades
    e["PickeosMetric"] = 1.0

    # En vivo no conocemos CuantasTareas del analítico. El mejor proxy disponible
    # es 1 por TareaId / ControlContenedorId, claramente marcado como provisorio.
    primera = ~e.duplicated("EventoId", keep="first")
    e["EventosMetric"] = 0.0
    e.loc[primera, "EventosMetric"] = 1.0
    return e


def construir_eventos_hibridos(
    base_live: pd.DataFrame,
    analitico_preparacion: pd.DataFrame | None,
    analitico_control: pd.DataFrame | None,
    df_articulos: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Analítico consolidado + delta vivo de Filtrar Preparación, sin duplicar IDs."""
    pick_a = _picking_analitico(analitico_preparacion, base_live, df_articulos)
    control_a = _control_analitico(analitico_control, base_live, df_articulos)
    pick_l = _live_eventos(base_live, "Picking")
    control_l = _live_eventos(base_live, "Control")

    # PICKING: si TareaId ya existe en analítico, todo ese evento sale del analítico.
    ids_pick_a = set(pick_a["EventoId"].dropna().astype(str)) if not pick_a.empty else set()
    pick_delta = pick_l.loc[~pick_l["EventoId"].isin(ids_pick_a)].copy() if not pick_l.empty else pd.DataFrame()
    pick = pd.concat([pick_a, pick_delta], ignore_index=True, sort=False)

    # CONTROL: unidades/pickeos consolidados salen del analítico. Para el período
    # consolidado agregamos SOLO una fila de conteo por ControlContenedorId que
    # exista en Filtrar pero no en el analítico (DIGIP los usa para el KPI Tareas).
    ids_control_a = set(control_a["EventoId"].dropna().astype(str)) if not control_a.empty else set()
    control_delta = pd.DataFrame()
    if not control_l.empty:
        if not control_a.empty and control_a["FechaEvento"].notna().any():
            max_consolidado = control_a["FechaEvento"].max().normalize()
            historico_faltante = control_l.loc[
                (control_l["FechaEvento"].dt.normalize() <= max_consolidado)
                & ~control_l["EventoId"].isin(ids_control_a)
            ].copy()
            if not historico_faltante.empty:
                historico_faltante = historico_faltante.loc[~historico_faltante.duplicated("EventoId", keep="first")].copy()
                historico_faltante["UnidadesProceso"] = 0.0
                historico_faltante["PickeosMetric"] = 0.0
                historico_faltante["EventosMetric"] = 1.0
                historico_faltante["Fuente"] = "Filtrar · conteo"
                historico_faltante["DatoConsolidado"] = True

            vivo = control_l.loc[control_l["FechaEvento"].dt.normalize() > max_consolidado].copy()
            control_delta = pd.concat([historico_faltante, vivo], ignore_index=True, sort=False)
        else:
            control_delta = control_l.copy()

    control = pd.concat([control_a, control_delta], ignore_index=True, sort=False)

    return pick.reset_index(drop=True), control.reset_index(drop=True)


def resumen_usuarios(eventos: pd.DataFrame) -> pd.DataFrame:
    columnas = ["Usuario", "Tareas", "Pickeos", "Preparaciones", "Unidades", "SKUs", "Unid/Tarea", "Participacion"]
    if eventos is None or eventos.empty:
        return pd.DataFrame(columns=columnas)

    x = eventos.copy()
    for c in ["UnidadesProceso", "EventosMetric", "PickeosMetric"]:
        x[c] = pd.to_numeric(x.get(c, 0), errors="coerce").fillna(0)

    r = x.groupby("Usuario", as_index=False).agg(
        Tareas=("EventosMetric", "sum"),
        Pickeos=("PickeosMetric", "sum"),
        Preparaciones=("Id", "nunique"),
        Unidades=("UnidadesProceso", "sum"),
        SKUs=("CodigoArticulo", lambda s: s.replace("", pd.NA).dropna().nunique()),
    )
    r["Tareas"] = r["Tareas"].round(0).astype(int)
    r["Pickeos"] = r["Pickeos"].round(0).astype(int)
    r["Unidades"] = r["Unidades"].round(0).astype(int)
    r["Unid/Tarea"] = (r["Unidades"] / r["Tareas"].replace(0, pd.NA)).fillna(0).round(1)
    total = r["Unidades"].sum()
    r["Participacion"] = (r["Unidades"] / total * 100).round(1) if total else 0.0
    return r.sort_values(["Unidades", "Tareas"], ascending=False).reset_index(drop=True)


def estado_calidad(eventos: pd.DataFrame, desde, hasta) -> tuple[str, str]:
    if eventos is None or eventos.empty:
        return "Sin datos", "No hay actividad para el período seleccionado."
    x = eventos.loc[(eventos["FechaEvento"].dt.date >= desde) & (eventos["FechaEvento"].dt.date <= hasta)]
    if x.empty:
        return "Sin datos", "No hay actividad para el período seleccionado."
    fuentes = set(_texto(x["Fuente"]).tolist()) if "Fuente" in x.columns else set()
    tiene_vivo = any(f in {"En vivo"} for f in fuentes)
    tiene_analitico = any(f == "Analítico" for f in fuentes)
    if tiene_vivo and tiene_analitico:
        return "Mixto", "Histórico consolidado + delta en vivo desde Filtrar Preparación."
    if tiene_vivo:
        return "En vivo", "Datos provisorios reconstruidos desde Filtrar Preparación."
    return "Consolidado", "Datos provenientes de los reportes analíticos de DIGIP."


# ==========================================================
# SCORE DE PRODUCTIVIDAD PICKING
# ==========================================================

SCORE_JORNADA_INICIO = 6
SCORE_JORNADA_FIN = 17
SCORE_TOPE_COMPONENTE = 120.0
SCORE_PESOS = {
    "Unid_h": 0.25,
    "Tareas_h": 0.20,
    "Lineas_h": 0.20,
    "M3_h": 0.10,
    "Kg_h": 0.10,
    "Recorrido_h": 0.15,
}
SCORE_DISTANCIAS = {
    "base_tarea_m": 5.0,
    "pasillo_m": 4.0,
    "posicion_m": 1.2,
    "cambio_area_m": 12.0,
}


def _numero_ubicacion(valor) -> float:
    try:
        return float(str(valor).strip())
    except Exception:
        return float("nan")


def _ubicacion_partes(valor: object) -> tuple[str, float, float, float]:
    partes = [p.strip() for p in str(valor or "").split("-")]
    if len(partes) < 4:
        return "", float("nan"), float("nan"), float("nan")
    return (
        partes[0].upper(),
        _numero_ubicacion(partes[1]),
        _numero_ubicacion(partes[2]),
        _numero_ubicacion(partes[3]),
    )


def _clave_ubicacion(ab, pasillo, posicion, nivel) -> str:
    def n(v):
        try:
            return str(int(float(v)))
        except Exception:
            return ""
    return f"{str(ab or '').strip().upper()}|{n(pasillo)}|{n(posicion)}|{n(nivel)}"


def _minutos_operativos(inicio, fin) -> float:
    """Tiempo calendario recortado a la jornada productiva 06:00-17:00."""
    inicio = pd.to_datetime(inicio, errors="coerce")
    fin = pd.to_datetime(fin, errors="coerce")
    if pd.isna(inicio) or pd.isna(fin) or fin <= inicio:
        return 0.0

    total = 0.0
    dia = inicio.normalize()
    ultimo = fin.normalize()
    while dia <= ultimo:
        ventana_inicio = dia + pd.Timedelta(hours=SCORE_JORNADA_INICIO)
        ventana_fin = dia + pd.Timedelta(hours=SCORE_JORNADA_FIN)
        tramo_inicio = max(inicio, ventana_inicio)
        tramo_fin = min(fin, ventana_fin)
        if tramo_fin > tramo_inicio:
            total += (tramo_fin - tramo_inicio).total_seconds() / 60.0
        dia += pd.Timedelta(days=1)
    return float(total)


def _recorrido_equivalente(grupo: pd.DataFrame) -> float:
    """Reconstruye el recorrido por área, pasillo y posición/rack."""
    if grupo is None or grupo.empty:
        return 0.0
    g = grupo.sort_values([c for c in ["Orden", "FechaPickeo"] if c in grupo.columns]).copy()
    ubicaciones = []
    for val in g.get("Ubicacion", pd.Series(dtype=object)).tolist():
        p = _ubicacion_partes(val)
        if not p[0] or pd.isna(p[1]) or pd.isna(p[2]):
            continue
        if not ubicaciones or p != ubicaciones[-1]:
            ubicaciones.append(p)
    if not ubicaciones:
        return 0.0

    distancia = SCORE_DISTANCIAS["base_tarea_m"]
    prev = ubicaciones[0]
    for actual in ubicaciones[1:]:
        if actual[0] != prev[0]:
            distancia += SCORE_DISTANCIAS["cambio_area_m"]
        distancia += abs(actual[1] - prev[1]) * SCORE_DISTANCIAS["pasillo_m"]
        distancia += abs(actual[2] - prev[2]) * SCORE_DISTANCIAS["posicion_m"]
        prev = actual
    return float(distancia)


def construir_score_productividad(
    analitico: pd.DataFrame,
    df_volumetria: pd.DataFrame | None = None,
    df_ubicaciones: pd.DataFrame | None = None,
    desde=None,
    hasta=None,
    usuario: str = "Todos",
    usuarios_excluidos: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """
    Score Picking 0-120 relativo a la mediana de la operación.

    Ponderación:
      Unidades/h 25 · Tareas/h 20 · Líneas/h 20 · m3/h 10 · Kg/h 10 · Recorrido/h 15.
    El tiempo se computa únicamente entre 06:00 y 17:00, incluso si una tarea
    atraviesa una noche.
    """
    if analitico is None or analitico.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    a = analitico.copy()
    if "Tipo" in a.columns:
        a = a.loc[_texto(a["Tipo"]).str.lower().eq("preparacion")].copy()
    if a.empty or "TareaId" not in a.columns:
        return pd.DataFrame(), pd.DataFrame(), {}

    a["TareaId"] = _id(a["TareaId"])
    a["Usuario"] = _texto(a.get("Usuario", pd.Series("", index=a.index)))
    a["CodigoArticulo"] = _texto(a.get("CodigoArticulo", pd.Series("", index=a.index))).str.upper().str.replace(r"\.0+$", "", regex=True)
    a["FechaInicioScore"] = _fecha_analitico(a.get("FechaInicio", pd.Series(pd.NaT, index=a.index)))
    a["FechaFinScore"] = _fecha_analitico(a.get("FechaFin", pd.Series(pd.NaT, index=a.index)))
    a["FechaPickeo"] = _fecha_analitico(a.get("FechaPickeo", pd.Series(pd.NaT, index=a.index)))
    a["FechaScore"] = a["FechaFinScore"].dt.normalize()
    a["UnidadesDetalle"] = pd.to_numeric(a.get("UnidadesDetalle", 0), errors="coerce").fillna(0)
    a["Orden"] = pd.to_numeric(a.get("Orden", 0), errors="coerce").fillna(0)

    if desde is not None:
        a = a.loc[a["FechaScore"].dt.date >= desde].copy()
    if hasta is not None:
        a = a.loc[a["FechaScore"].dt.date <= hasta].copy()
    if usuario and usuario != "Todos":
        a = a.loc[a["Usuario"].eq(usuario)].copy()
    if usuarios_excluidos:
        excl = {" ".join(str(x).strip().upper().split()) for x in usuarios_excluidos}
        norm = a["Usuario"].map(lambda x: " ".join(str(x).strip().upper().split()))
        a = a.loc[~norm.isin(excl)].copy()
    if a.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    # Maestro de ubicaciones: valida que la línea pertenezca a una ubicación Picking.
    if df_ubicaciones is not None and not df_ubicaciones.empty:
        u = df_ubicaciones.copy()
        requeridas = {"Ab", "Pasillo", "Posicion", "Nivel"}
        if requeridas.issubset(u.columns):
            u["_UbicKey"] = [
                _clave_ubicacion(ab, pas, pos, niv)
                for ab, pas, pos, niv in zip(u["Ab"], u["Pasillo"], u["Posicion"], u["Nivel"])
            ]
            tipo_col = "Tipo" if "Tipo" in u.columns else None
            cols = ["_UbicKey"] + ([tipo_col] if tipo_col else [])
            u = u[cols].drop_duplicates("_UbicKey", keep="first")

            partes = a.get("Ubicacion", pd.Series("", index=a.index)).map(_ubicacion_partes)
            a["_UbicKey"] = partes.map(lambda p: _clave_ubicacion(*p))
            a = a.merge(u, on="_UbicKey", how="left", suffixes=("", "_Ubic"))
            if tipo_col:
                col_tipo = "Tipo_Ubic" if "Tipo_Ubic" in a.columns else tipo_col
                es_picking = _texto(a[col_tipo]).str.lower().eq("picking")
                # Solo filtramos si el maestro efectivamente logró identificar Picking.
                if es_picking.any():
                    a = a.loc[es_picking].copy()
    if a.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    # Volumetría por SKU.
    a["M3Linea"] = 0.0
    a["KgLinea"] = 0.0
    a["VolumetriaCubierta"] = False
    if df_volumetria is not None and not df_volumetria.empty and "Codigo" in df_volumetria.columns:
        v = df_volumetria.copy()
        v["Codigo"] = _texto(v["Codigo"]).str.upper().str.replace(r"\.0+$", "", regex=True)
        for c in ["Alto", "Ancho", "Profundo", "Alt", "Anc", "Prof", "Kg", "Peso"]:
            if c in v.columns:
                v[c] = pd.to_numeric(v[c], errors="coerce")
        alto = v["Alt"] if "Alt" in v.columns else v.get("Alto", 0)
        ancho = v["Anc"] if "Anc" in v.columns else v.get("Ancho", 0)
        prof = v["Prof"] if "Prof" in v.columns else v.get("Profundo", 0)
        v["_M3Unidad"] = pd.to_numeric(alto, errors="coerce").fillna(0) * pd.to_numeric(ancho, errors="coerce").fillna(0) * pd.to_numeric(prof, errors="coerce").fillna(0) / 1_000_000_000
        if "Kg" in v.columns:
            v["_KgUnidad"] = pd.to_numeric(v["Kg"], errors="coerce").fillna(0)
        elif "Peso" in v.columns:
            v["_KgUnidad"] = pd.to_numeric(v["Peso"], errors="coerce").fillna(0) / 1000
        else:
            v["_KgUnidad"] = 0.0
        v = v[["Codigo", "_M3Unidad", "_KgUnidad"]].drop_duplicates("Codigo", keep="first")
        a = a.merge(v, left_on="CodigoArticulo", right_on="Codigo", how="left", validate="many_to_one")
        a["_M3Unidad"] = pd.to_numeric(a["_M3Unidad"], errors="coerce").fillna(0)
        a["_KgUnidad"] = pd.to_numeric(a["_KgUnidad"], errors="coerce").fillna(0)
        a["M3Linea"] = a["UnidadesDetalle"] * a["_M3Unidad"]
        a["KgLinea"] = a["UnidadesDetalle"] * a["_KgUnidad"]
        a["VolumetriaCubierta"] = a["_M3Unidad"].gt(0) | a["_KgUnidad"].gt(0)

    tareas = []
    for tarea_id, g in a.groupby("TareaId", sort=False):
        usuario_t = _texto(g["Usuario"]).replace("", pd.NA).dropna()
        usuario_t = usuario_t.iloc[0] if not usuario_t.empty else ""
        inicio = g["FechaInicioScore"].dropna().min()
        fin = g["FechaFinScore"].dropna().max()
        minutos = _minutos_operativos(inicio, fin)
        unidades = float(pd.to_numeric(g["UnidadesDetalle"], errors="coerce").fillna(0).sum())
        tareas.append({
            "TareaId": tarea_id,
            "Fecha": fin.normalize() if pd.notna(fin) else pd.NaT,
            "FechaInicio": inicio,
            "FechaFin": fin,
            "Usuario": usuario_t,
            "MinutosOperativos": minutos,
            "Unidades": unidades,
            "Lineas": int(len(g)),
            "SKUs": int(g["CodigoArticulo"].replace("", pd.NA).dropna().nunique()),
            "M3": float(pd.to_numeric(g["M3Linea"], errors="coerce").fillna(0).sum()),
            "Kg": float(pd.to_numeric(g["KgLinea"], errors="coerce").fillna(0).sum()),
            "RecorridoEqM": _recorrido_equivalente(g),
            "CoberturaVol": float(g.loc[g["VolumetriaCubierta"], "UnidadesDetalle"].sum() / unidades) if unidades > 0 else 0.0,
        })
    tareas = pd.DataFrame(tareas)
    tareas = tareas.loc[tareas["MinutosOperativos"].gt(0) & tareas["Usuario"].ne("")].copy()
    if tareas.empty:
        return pd.DataFrame(), tareas, {}

    resumen = (
        tareas.groupby("Usuario", as_index=False)
        .agg(
            Tareas=("TareaId", "nunique"),
            MinutosOperativos=("MinutosOperativos", "sum"),
            Unidades=("Unidades", "sum"),
            Lineas=("Lineas", "sum"),
            SKUs=("SKUs", "sum"),
            M3=("M3", "sum"),
            Kg=("Kg", "sum"),
            RecorridoEqM=("RecorridoEqM", "sum"),
            CoberturaVol=("CoberturaVol", "mean"),
        )
    )
    resumen["Horas"] = resumen["MinutosOperativos"] / 60.0
    resumen = resumen.loc[resumen["Horas"].gt(0)].copy()
    resumen["Unid_h"] = resumen["Unidades"] / resumen["Horas"]
    resumen["Tareas_h"] = resumen["Tareas"] / resumen["Horas"]
    resumen["Lineas_h"] = resumen["Lineas"] / resumen["Horas"]
    resumen["M3_h"] = resumen["M3"] / resumen["Horas"]
    resumen["Kg_h"] = resumen["Kg"] / resumen["Horas"]
    resumen["Recorrido_h"] = resumen["RecorridoEqM"] / resumen["Horas"]

    # Referencia: mediana entre usuarios con muestra mínima suficiente.
    base_ref = resumen.loc[(resumen["Tareas"] >= 5) & (resumen["Horas"] >= 1)].copy()
    if base_ref.empty:
        base_ref = resumen.copy()
    referencias = {
        metrica: float(pd.to_numeric(base_ref[metrica], errors="coerce").dropna().median())
        for metrica in SCORE_PESOS
    }

    score = pd.Series(0.0, index=resumen.index)
    nombres_pts = {
        "Unid_h": "PtsUnid",
        "Tareas_h": "PtsTareas",
        "Lineas_h": "PtsLineas",
        "M3_h": "PtsM3",
        "Kg_h": "PtsKg",
        "Recorrido_h": "PtsRecorrido",
    }
    for metrica, peso in SCORE_PESOS.items():
        ref = referencias.get(metrica, 0.0)
        if ref > 0:
            puntos = (resumen[metrica] / ref * 100.0).clip(lower=0, upper=SCORE_TOPE_COMPONENTE)
        else:
            puntos = pd.Series(0.0, index=resumen.index)
        resumen[nombres_pts[metrica]] = puntos
        score = score + puntos * peso
    resumen["Score"] = score.round(1)
    resumen["Confianza"] = "Baja"
    resumen.loc[(resumen["Tareas"] >= 5) & (resumen["Horas"] >= 1), "Confianza"] = "Media"
    resumen.loc[(resumen["Tareas"] >= 15) & (resumen["Horas"] >= 3), "Confianza"] = "Alta"
    resumen = resumen.sort_values(["Score", "Tareas"], ascending=[False, False]).reset_index(drop=True)
    return resumen, tareas.reset_index(drop=True), referencias


# ==========================================================
# CAMPEONATO DE PRODUCTIVIDAD PICKING
# Tarea -> Día -> Mes
# ==========================================================

PUNTOS_TAREA_DIVISOR = 10.0


def construir_campeonato_productividad(
    analitico: pd.DataFrame,
    df_volumetria: pd.DataFrame | None = None,
    df_ubicaciones: pd.DataFrame | None = None,
    fecha_referencia=None,
    usuarios_excluidos: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """
    Construye el campeonato del mes de fecha_referencia.

    - Cada tarea cerrada obtiene ScoreTarea (0-120).
    - PuntosTarea = ScoreTarea / 10 (0-12 puntos por tarea).
    - Ranking diario = suma de puntos + promedio de ScoreTarea.
    - Ranking mensual = suma de puntos + promedio de ScoreTarea.
    - Las referencias son mensuales y se mantienen iguales para todos los días
      del mismo mes, evitando que el estándar cambie según quién trabajó ese día.
    """
    if fecha_referencia is None:
        fecha_referencia = pd.Timestamp.today().date()
    ref_fecha = pd.Timestamp(fecha_referencia)
    mes_inicio = ref_fecha.replace(day=1).date()
    mes_fin = (ref_fecha.replace(day=1) + pd.offsets.MonthEnd(1)).date()

    _, tareas, _ = construir_score_productividad(
        analitico,
        df_volumetria,
        df_ubicaciones,
        desde=mes_inicio,
        hasta=mes_fin,
        usuario="Todos",
        usuarios_excluidos=usuarios_excluidos,
    )
    if tareas is None or tareas.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}

    t = tareas.copy()
    t["Fecha"] = pd.to_datetime(t["Fecha"], errors="coerce").dt.normalize()
    t["Horas"] = pd.to_numeric(t["MinutosOperativos"], errors="coerce").fillna(0) / 60.0
    t = t.loc[t["Horas"].gt(0) & t["Fecha"].notna() & t["Usuario"].ne("")].copy()
    if t.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}

    # Tasas por tarea. Una tarea siempre aporta 1 tarea terminada.
    t["Unid_h"] = t["Unidades"] / t["Horas"]
    t["Tareas_h"] = 1.0 / t["Horas"]
    t["Lineas_h"] = t["Lineas"] / t["Horas"]
    t["M3_h"] = t["M3"] / t["Horas"]
    t["Kg_h"] = t["Kg"] / t["Horas"]
    t["Recorrido_h"] = t["RecorridoEqM"] / t["Horas"]

    # Referencias estables del mes a nivel tarea.
    # Se excluyen duraciones extremadamente pequeñas para que un cierre instantáneo
    # no deforme la mediana mensual.
    base_ref = t.loc[t["MinutosOperativos"].ge(2)].copy()
    if base_ref.empty:
        base_ref = t.copy()

    referencias = {
        metrica: float(pd.to_numeric(base_ref[metrica], errors="coerce").replace([float("inf"), float("-inf")], pd.NA).dropna().median())
        for metrica in SCORE_PESOS
    }

    nombres_pts = {
        "Unid_h": "PtsUnid",
        "Tareas_h": "PtsTareas",
        "Lineas_h": "PtsLineas",
        "M3_h": "PtsM3",
        "Kg_h": "PtsKg",
        "Recorrido_h": "PtsRecorrido",
    }
    score = pd.Series(0.0, index=t.index)
    for metrica, peso in SCORE_PESOS.items():
        ref = referencias.get(metrica, 0.0)
        if ref > 0:
            pts = (pd.to_numeric(t[metrica], errors="coerce").fillna(0) / ref * 100.0).clip(0, SCORE_TOPE_COMPONENTE)
        else:
            pts = pd.Series(0.0, index=t.index)
        t[nombres_pts[metrica]] = pts
        score = score + pts * peso

    t["ScoreTarea"] = score.round(1)
    t["PuntosTarea"] = (t["ScoreTarea"] / PUNTOS_TAREA_DIVISOR).round(2)
    t["FechaDia"] = t["Fecha"].dt.date

    # Ranking diario: productividad + mérito acumulado del día.
    diario = (
        t.groupby(["FechaDia", "Usuario"], as_index=False)
        .agg(
            Puntos=("PuntosTarea", "sum"),
            Score=("ScoreTarea", "mean"),
            Tareas=("TareaId", "nunique"),
            Horas=("Horas", "sum"),
            Unidades=("Unidades", "sum"),
            Lineas=("Lineas", "sum"),
            M3=("M3", "sum"),
            Kg=("Kg", "sum"),
            RecorridoEqM=("RecorridoEqM", "sum"),
        )
    )
    diario["Puntos"] = diario["Puntos"].round(1)
    diario["Score"] = diario["Score"].round(1)
    diario["Horas"] = diario["Horas"].round(2)
    diario["PosicionDia"] = (
        diario.groupby("FechaDia")["Puntos"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    # Podios diarios para el acumulado mensual.
    podios = (
        diario.assign(
            Oro=(diario["PosicionDia"] == 1).astype(int),
            Plata=(diario["PosicionDia"] == 2).astype(int),
            Bronce=(diario["PosicionDia"] == 3).astype(int),
        )
        .groupby("Usuario", as_index=False)
        .agg(Oro=("Oro", "sum"), Plata=("Plata", "sum"), Bronce=("Bronce", "sum"))
    )

    mensual = (
        t.groupby("Usuario", as_index=False)
        .agg(
            PuntosMes=("PuntosTarea", "sum"),
            ScorePromedio=("ScoreTarea", "mean"),
            Tareas=("TareaId", "nunique"),
            DiasActivos=("FechaDia", "nunique"),
            Horas=("Horas", "sum"),
            Unidades=("Unidades", "sum"),
            Lineas=("Lineas", "sum"),
        )
        .merge(podios, on="Usuario", how="left")
    )
    mensual["PuntosMes"] = mensual["PuntosMes"].round(1)
    mensual["ScorePromedio"] = mensual["ScorePromedio"].round(1)
    mensual["Horas"] = mensual["Horas"].round(2)
    mensual[["Oro", "Plata", "Bronce"]] = mensual[["Oro", "Plata", "Bronce"]].fillna(0).astype(int)
    mensual = mensual.sort_values(
        ["PuntosMes", "ScorePromedio", "Tareas"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    mensual["PosicionMes"] = range(1, len(mensual) + 1)

    return (
        t.sort_values(["Fecha", "PuntosTarea"], ascending=[False, False]).reset_index(drop=True),
        diario.sort_values(["FechaDia", "PosicionDia"]).reset_index(drop=True),
        mensual,
        referencias,
    )

