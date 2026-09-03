from __future__ import annotations

import pandas as pd


def _texto(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def _id(s: pd.Series) -> pd.Series:
    return _texto(s).str.replace(r"\.0$", "", regex=True)


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
        cols = ["TareaId"] + comun + [c for c in ["TareaUsuarioCompleto"] if c in base.columns]
        mapa_tarea = base.loc[base["TareaId"].ne(""), cols].drop_duplicates("TareaId", keep="last")

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
    a.loc[primera, "UnidadesProceso"] = a.loc[primera, "UnidadesTarea"]
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
    unidades = pd.to_numeric(e.get("UnidadesSatisfecha", e.get("Unidades", 0)), errors="coerce").fillna(0)
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
    r["Participacion"] = ((r["Unidades"] / total * 100) if total else 0).round(1)
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
