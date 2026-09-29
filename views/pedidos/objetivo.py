from __future__ import annotations

from pathlib import Path
from datetime import date, timedelta
import re

import altair as alt
import pandas as pd
import streamlit as st

from config import CARPETA_WMS, CARPETA_MAESTROS
from utils.leer_datos import leer_archivo

OBJETIVO_LV = 750
OBJETIVO_SABADO = 500
MIN_HORAS_ACTIVO_LV = 5.5
MIN_HORAS_ACTIVO_SAB = 3.5
MIN_CONTROLES_ACTIVO = 5


def _fmt(v, dec=0):
    try:
        return f"{float(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "0"


def _leer_archivo(ruta: Path) -> pd.DataFrame:
    try:
        if ruta.suffix.lower() == ".csv":
            return pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
        return pd.read_excel(ruta)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_control_historico() -> pd.DataFrame:
    carpeta = Path(CARPETA_WMS)
    rutas = []
    for patron in ("Control*.csv", "Control*.xlsx", "Control*.xls", "control*.csv", "control*.xlsx"):
        rutas.extend(carpeta.glob(patron))
    tablas = []
    for ruta in sorted({r.resolve() for r in rutas if r.is_file()}):
        t = _leer_archivo(ruta)
        if not t.empty and "ControlContenedorId" in t.columns:
            t = t.copy(); t["ArchivoOrigen"] = ruta.name; tablas.append(t)
    if not tablas:
        return pd.DataFrame()
    total = pd.concat(tablas, ignore_index=True, sort=False).drop_duplicates()
    return total.reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_filtrar_preparaciones() -> pd.DataFrame:
    """Fuente principal de Objetivo: histórico + ventana reciente de Filtrar Preparaciones."""
    carpeta = Path(CARPETA_WMS)
    rutas = []

    # Histórico consolidado, si existe.
    for nombre in (
        "Historico Filtrar Preparaciones.csv",
        "Historico Filtrar Preparaciones.xlsx",
        "Histórico Filtrar Preparaciones.csv",
        "Histórico Filtrar Preparaciones.xlsx",
    ):
        ruta = carpeta / nombre
        if ruta.exists():
            rutas.append(ruta)
            break

    # Sumamos la ventana reciente para no depender de que el histórico ya haya sido actualizado.
    for patron in (
        "Filtrar Preparacion Ultimos 7 Dias*.csv",
        "Filtrar Preparacion Ultimos 7 Dias*.xlsx",
        "Filtrar Preparación Ultimos 7 Dias*.csv",
        "Filtrar Preparación Últimos 7 Días*.csv",
    ):
        rutas.extend(carpeta.glob(patron))

    # Si no hay histórico, usamos los meses guardados.
    if not rutas:
        for patron in ("Filtrar Preparacion*.csv", "Filtrar Preparación*.csv", "Filtrar Preparacion*.xlsx"):
            rutas.extend(carpeta.glob(patron))
        rutas = [r for r in rutas if "ultimos" not in r.name.lower() and "últimos" not in r.name.lower()]

    tablas = []
    for ruta in sorted({r.resolve() for r in rutas if r.is_file()}):
        t = _leer_archivo(ruta)
        if not t.empty and "ControlContenedorId" in t.columns:
            t = t.copy()
            t["ArchivoOrigen"] = ruta.name
            tablas.append(t)

    if not tablas:
        return pd.DataFrame()

    total = pd.concat(tablas, ignore_index=True, sort=False)

    # Una fila física de detalle de contenedor debe existir una sola vez aunque aparezca
    # tanto en histórico como en últimos 7 días. La fuente más reciente queda última.
    if "ContenedorDetalleId" in total.columns:
        clave = (total["ContenedorDetalleId"].astype("string").fillna("")
                 .str.strip().str.replace(r"\.0+$", "", regex=True))
        con = total.loc[clave.ne("")].copy()
        sin = total.loc[clave.eq("")].copy()
        if not con.empty:
            con["_k"] = (con["ContenedorDetalleId"].astype("string").fillna("")
                         .str.strip().str.replace(r"\.0+$", "", regex=True))
            con = con.drop_duplicates("_k", keep="last").drop(columns="_k")
        total = pd.concat([con, sin], ignore_index=True, sort=False)

    return total.reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def _cargar_maestro_articulos() -> pd.DataFrame:
    try:
        return leer_archivo(CARPETA_MAESTROS, "Maestro Articulo", cache=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def _cargar_maestro_personal() -> pd.DataFrame:
    """Maestro de personas: autoridad para identidad, sector y puesto."""
    try:
        return leer_archivo(CARPETA_MAESTROS, "Maestro Personal", cache=True)
    except Exception:
        return pd.DataFrame()


def _normalizar_texto(v) -> str:
    if pd.isna(v):
        return ""
    s = str(v).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _mapas_personal(personal: pd.DataFrame):
    """Devuelve mapas por login y por nombre completo usando sólo registros activos."""
    por_login, por_nombre = {}, {}
    if personal.empty:
        return por_login, por_nombre

    p = personal.copy()
    if "Estado" in p.columns:
        p = p[p["Estado"].astype("string").fillna("").str.strip().str.lower().ne("inactivo")].copy()

    for _, r in p.iterrows():
        login = _normalizar_texto(r.get("Usuario / Login", ""))
        nombre = str(r.get("Nombre Completo", "") or "").strip()
        nombre_key = _normalizar_texto(nombre)
        dato = {
            "NombreMaestro": nombre,
            "SectorMaestro": str(r.get("Sector", "") or "").strip(),
            "PuestoMaestro": str(r.get("Puesto", "") or "").strip(),
            "NominaMaestro": str(r.get("Nómina", "") or "").strip(),
            "JornadaMaestro": str(r.get("Jornada", "") or "").strip(),
        }
        if login:
            por_login[login] = dato
        if nombre_key:
            por_nombre[nombre_key] = dato
    return por_login, por_nombre


def _clasificar_persona(usuario: str, por_login: dict, por_nombre: dict):
    """Homologa login/nombre y determina si pertenece a la línea de Control."""
    key = _normalizar_texto(usuario)
    dato = por_login.get(key) or por_nombre.get(key)
    if not dato:
        return str(usuario or "").strip(), "", "", False, "Sin clasificar"

    nombre = dato["NombreMaestro"] or str(usuario or "").strip()
    sector = dato["SectorMaestro"]
    puesto = dato["PuestoMaestro"]

    # El maestro actual define la dotación de Control como Puesto = "Linea Control".
    es_control = _normalizar_texto(puesto) in {"linea control", "línea control"}
    tipo = "Control" if es_control else "Apoyo / otro sector"
    return nombre, sector, puesto, es_control, tipo


def _fecha_control(s: pd.Series) -> pd.Series:
    # Control histórico normalmente viene MM/DD/YYYY. Si no parsea, probamos dayfirst.
    a = pd.to_datetime(s, errors="coerce", dayfirst=False)
    faltan = a.isna()
    if faltan.any():
        a.loc[faltan] = pd.to_datetime(s.loc[faltan], errors="coerce", dayfirst=True)
    return a


def _preparar_base(control: pd.DataFrame, filtrar: pd.DataFrame, maestro: pd.DataFrame, personal: pd.DataFrame):
    """
    Construye un histórico mensual continuo usando la mejor fuente disponible por fecha:
    - Filtrar Preparaciones manda en las fechas que contiene (fuente operativa exacta).
    - Control completa las fechas anteriores/faltantes que todavía no están en Filtrar.
    Así no perdemos ni el mes histórico ni días recientes como el 25/09.
    """
    detalles = []
    actividades = []
    por_login, por_nombre = _mapas_personal(personal)

    # ---------------------------------------------------------
    # Construimos ambas fuentes completas y elegimos POR FECHA
    # la que tenga mayor cantidad de líneas de detalle.
    # Esto evita que un Filtrar parcial (ej. 22/09) reemplace
    # un Control completo sólo porque la fecha existe.
    # ---------------------------------------------------------
    det_f = pd.DataFrame()
    act_f = pd.DataFrame()
    det_c = pd.DataFrame()
    act_c = pd.DataFrame()

    if not filtrar.empty and "ControlContenedorId" in filtrar.columns:
        f = filtrar.copy()
        f["ControlID"] = (f["ControlContenedorId"].astype("string").fillna("")
                          .str.replace(r"\.0+$", "", regex=True).str.strip())
        f["CodigoArticulo"] = f.get("CodigoArticulo", pd.Series("", index=f.index)).astype("string").fillna("").str.strip()
        f["FechaControlDT"] = pd.to_datetime(
            f.get("ControlContenedorFechaHoraEstado", pd.Series(index=f.index, dtype="object")),
            errors="coerce", dayfirst=True,
        )
        f = f[f["FechaControlDT"].notna() & f["ControlID"].ne("")].copy()
        f["Fecha"] = f["FechaControlDT"].dt.normalize()

        nombre = f.get("ControlContenedorUsuarioCompleto", pd.Series("", index=f.index)).astype("string").fillna("").str.strip()
        if nombre.eq("").all() and {"ControlContenedorUsuarioNombre", "ControlContenedorUsuarioApellido"}.issubset(f.columns):
            nombre = (f["ControlContenedorUsuarioNombre"].fillna("").astype(str).str.strip() + " " +
                      f["ControlContenedorUsuarioApellido"].fillna("").astype(str).str.strip()).str.strip()
        f["UsuarioMostrar"] = nombre

        unidad_col = next((x for x in ["ContenedorUnidades", "UnidadesSatisfecha", "UnidadesReservada", "Unidades"] if x in f.columns), None)
        f["UnidadesNum"] = pd.to_numeric(f[unidad_col], errors="coerce").fillna(0) if unidad_col else 0

        if "ContenedorDetalleId" in f.columns:
            f["DetalleID"] = (f["ContenedorDetalleId"].astype("string").fillna("")
                              .str.replace(r"\.0+$", "", regex=True).str.strip())
            con_id = f[f["DetalleID"].ne("")].drop_duplicates("DetalleID", keep="last")
            sin_id = f[f["DetalleID"].eq("")].drop_duplicates(["ControlID", "CodigoArticulo", "Fecha"], keep="last")
            det_f = pd.concat([con_id, sin_id], ignore_index=True, sort=False)
        else:
            det_f = f.drop_duplicates(["ControlID", "CodigoArticulo", "Fecha"], keep="last").copy()
        det_f["Fuente"] = "Filtrar Preparaciones"

        controles_f = f.drop_duplicates(["ControlID", "Fecha"], keep="last").copy()
        act_f = controles_f.groupby(["Fecha", "UsuarioMostrar"], as_index=False).agg(
            PrimerControl=("FechaControlDT", "min"), UltimoControl=("FechaControlDT", "max"), Controles=("ControlID", "nunique")
        )
        act_f["Fuente"] = "Filtrar Preparaciones"

    if not control.empty and "ControlContenedorId" in control.columns:
        c = control.copy()
        c["ControlID"] = c["ControlContenedorId"].astype("string").fillna("").str.replace(r"\.0+$", "", regex=True).str.strip()
        c["CodigoArticulo"] = c.get("CodigoArticulo", pd.Series("", index=c.index)).astype("string").fillna("").str.strip()
        c["UsuarioMostrar"] = c.get("Usuario", pd.Series("", index=c.index)).astype("string").fillna("").str.strip()
        c["FechaControlDT"] = _fecha_control(c.get("FechaFin", pd.Series(index=c.index, dtype="object")))
        c = c[c["FechaControlDT"].notna() & c["ControlID"].ne("")].copy()
        c["Fecha"] = c["FechaControlDT"].dt.normalize()
        c["UnidadesNum"] = pd.to_numeric(c.get("Unidades", 0), errors="coerce").fillna(0)

        det_c = c.drop_duplicates(["ControlID", "CodigoArticulo", "Fecha"], keep="last").copy()
        det_c["Fuente"] = "Control"
        controles_c = c.drop_duplicates(["ControlID", "Fecha"], keep="last").copy()
        act_c = controles_c.groupby(["Fecha", "UsuarioMostrar"], as_index=False).agg(
            PrimerControl=("FechaControlDT", "min"), UltimoControl=("FechaControlDT", "max"), Controles=("ControlID", "nunique")
        )
        act_c["Fuente"] = "Control"

    # Elegimos la fuente más completa para cada fecha según cantidad de líneas.
    fechas = set()
    if not det_f.empty:
        fechas.update(det_f["Fecha"].dropna().unique().tolist())
    if not det_c.empty:
        fechas.update(det_c["Fecha"].dropna().unique().tolist())

    for fecha in sorted(fechas):
        df = det_f[det_f["Fecha"].eq(fecha)].copy() if not det_f.empty else pd.DataFrame()
        dc = det_c[det_c["Fecha"].eq(fecha)].copy() if not det_c.empty else pd.DataFrame()

        # Mayor número de filas de detalle = cierre más completo.
        # En empate preferimos Filtrar por tener identidad de controlador más rica.
        usar_filtrar = len(df) >= len(dc) and len(df) > 0
        if usar_filtrar:
            detalles.append(df)
            if not act_f.empty:
                actividades.append(act_f[act_f["Fecha"].eq(fecha)].copy())
        elif len(dc) > 0:
            detalles.append(dc)
            if not act_c.empty:
                actividades.append(act_c[act_c["Fecha"].eq(fecha)].copy())

    if not detalles:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    detalle = pd.concat(detalles, ignore_index=True, sort=False)

    # Familia Y Sector desde Maestro Artículos.
    # Son dimensiones distintas: no usamos Familia como reemplazo de Sector.
    detalle["Familia"] = "SIN FAMILIA"
    detalle["Sector"] = "SIN SECTOR"
    if not maestro.empty:
        cod_col = next((x for x in ["COD_ART", "Codigo", "CodigoArticulo"] if x in maestro.columns), None)
        fam_col = next((x for x in ["Familia_2", "Familia", "Rubro"] if x in maestro.columns), None)
        sector_col = next((x for x in ["Sectorizacion", "Sector", "SECTOR", "Sectorización", "Zona", "Area", "Área"] if x in maestro.columns), None)

        if cod_col:
            cols = [cod_col]
            if fam_col:
                cols.append(fam_col)
            if sector_col and sector_col not in cols:
                cols.append(sector_col)

            m = maestro[cols].copy()
            m[cod_col] = m[cod_col].astype("string").fillna("").str.strip()
            m = m.drop_duplicates(cod_col, keep="last")

            ren = {cod_col: "CodigoArticulo"}
            if fam_col:
                ren[fam_col] = "Familia_Maestro"
            if sector_col:
                ren[sector_col] = "Sector_Maestro"
            m = m.rename(columns=ren)

            detalle = detalle.merge(m, on="CodigoArticulo", how="left")

            if "Familia_Maestro" in detalle.columns:
                detalle["Familia"] = (
                    detalle["Familia_Maestro"].astype("string").fillna("").str.strip()
                    .replace("", "SIN FAMILIA")
                )
                detalle = detalle.drop(columns=["Familia_Maestro"])

            if "Sector_Maestro" in detalle.columns:
                detalle["Sector"] = (
                    detalle["Sector_Maestro"].astype("string").fillna("").str.strip()
                    .replace("", "SIN SECTOR")
                )
                detalle = detalle.drop(columns=["Sector_Maestro"])

    actividad = pd.concat(actividades, ignore_index=True, sort=False) if actividades else pd.DataFrame()
    if not actividad.empty:
        clasif = actividad["UsuarioMostrar"].apply(lambda u: _clasificar_persona(u, por_login, por_nombre))
        actividad["Operario"] = clasif.map(lambda x: x[0])
        actividad["Sector"] = clasif.map(lambda x: x[1])
        actividad["Puesto"] = clasif.map(lambda x: x[2])
        actividad["EsDotacionControl"] = clasif.map(lambda x: x[3])
        actividad["TipoDotacion"] = clasif.map(lambda x: x[4])

        actividad["HorasActividad"] = (actividad["UltimoControl"] - actividad["PrimerControl"]).dt.total_seconds().div(3600).clip(lower=0)
        actividad["EsSabado"] = actividad["Fecha"].dt.weekday.eq(5)
        actividad["JornadaCompleta"] = (
            actividad["Controles"].ge(MIN_CONTROLES_ACTIVO)
            & actividad["HorasActividad"].ge(actividad["EsSabado"].map({True:MIN_HORAS_ACTIVO_SAB, False:MIN_HORAS_ACTIVO_LV}))
        )
        lop = detalle.groupby(["Fecha", "UsuarioMostrar"], as_index=False).agg(
            Lineas=("CodigoArticulo", "count"), Unidades=("UnidadesNum", "sum"), Contenedores=("ControlID", "nunique")
        )
        actividad = actividad.merge(lop, on=["Fecha", "UsuarioMostrar"], how="left")

    diario = detalle.groupby("Fecha", as_index=False).agg(
        Lineas=("CodigoArticulo", "count"), Unidades=("UnidadesNum", "sum"), Contenedores=("ControlID", "nunique")
    )
    if not actividad.empty:
        # Dotación activa = persona de Línea Control que tuvo actividad real ese día.
        # JornadaCompleta queda como dato analítico, pero ya no es requisito para contarla.
        activos = (
            actividad[actividad["EsDotacionControl"] & actividad["Controles"].ge(1)]
            .groupby("Fecha")["Operario"].nunique().rename("OperariosActivos")
        )
        apoyos = (
            actividad[~actividad["EsDotacionControl"] & actividad["Controles"].ge(1)]
            .groupby("Fecha")["Operario"].nunique().rename("ApoyosActivos")
        )
        diario = diario.merge(activos, on="Fecha", how="left").merge(apoyos, on="Fecha", how="left")
    diario["OperariosActivos"] = diario.get("OperariosActivos", 0)
    diario["OperariosActivos"] = pd.to_numeric(diario["OperariosActivos"], errors="coerce").fillna(0).astype(int)
    diario["ApoyosActivos"] = diario.get("ApoyosActivos", 0)
    diario["ApoyosActivos"] = pd.to_numeric(diario["ApoyosActivos"], errors="coerce").fillna(0).astype(int)
    diario["DiaSemana"] = diario["Fecha"].dt.weekday
    diario = diario[diario["DiaSemana"].le(5)].copy()
    diario["Objetivo"] = diario["DiaSemana"].eq(5).map({True:OBJETIVO_SABADO, False:OBJETIVO_LV})
    diario["Cumplimiento"] = diario["Lineas"] / diario["Objetivo"]
    diario["Diferencia"] = diario["Lineas"] - diario["Objetivo"]
    diario["LineasOperario"] = diario["Lineas"].div(diario["OperariosActivos"].replace(0, pd.NA))
    diario["UnidadesOperario"] = diario["Unidades"].div(diario["OperariosActivos"].replace(0, pd.NA))
    diario["Estado"] = diario.apply(lambda r: "Superado" if r.Lineas > r.Objetivo else ("Cumplido" if r.Lineas == r.Objetivo else "Por debajo"), axis=1)
    return diario.sort_values("Fecha"), detalle, actividad

def render_objetivo() -> None:
    st.subheader("🎯 Objetivo")
    st.caption("Cierre real de Control: líneas y unidades terminadas, cumplimiento del objetivo, dotación activa de jornada completa y composición por familias.")

    control = _cargar_control_historico()
    filtrar = _cargar_filtrar_preparaciones()
    maestro = _cargar_maestro_articulos()
    personal = _cargar_maestro_personal()
    diario, detalle, actividad = _preparar_base(control, filtrar, maestro, personal)
    if diario.empty:
        st.warning("No encontré histórico válido de Filtrar Preparaciones en Data_WMS.")
        return

    fmax = diario["Fecha"].max().date(); fmin = diario["Fecha"].min().date()
    opciones = ["Esta semana", "Semana anterior", "Este mes", "Últimos 30 días", "Histórico", "Personalizado"]
    c1,c2,c3 = st.columns([1.5,1,1])
    periodo = c1.selectbox("Período", opciones, index=2, key="obj_periodo")
    hoy = fmax
    lunes = hoy - timedelta(days=hoy.weekday())
    if periodo == "Esta semana": ini, fin = lunes, hoy
    elif periodo == "Semana anterior": ini, fin = lunes-timedelta(days=7), lunes-timedelta(days=1)
    elif periodo == "Este mes": ini, fin = hoy.replace(day=1), hoy
    elif periodo == "Últimos 30 días": ini, fin = hoy-timedelta(days=29), hoy
    elif periodo == "Histórico": ini, fin = fmin, fmax
    else:
        ini = c2.date_input("Desde", value=max(fmin, hoy-timedelta(days=30)), min_value=fmin, max_value=fmax, key="obj_desde")
        fin = c3.date_input("Hasta", value=hoy, min_value=fmin, max_value=fmax, key="obj_hasta")
    if periodo != "Personalizado":
        c2.metric("Desde", ini.strftime("%d/%m/%Y")); c3.metric("Hasta", fin.strftime("%d/%m/%Y"))

    # Filtro estricto del período. Para "Este mes" reforzamos además mes/año
    # para impedir que una fecha de respaldo mal interpretada (p. ej. 31/08)
    # se cuele en la visualización de septiembre.
    diario["Fecha"] = pd.to_datetime(diario["Fecha"], errors="coerce").dt.normalize()
    d = diario.loc[
        diario["Fecha"].between(pd.Timestamp(ini), pd.Timestamp(fin), inclusive="both")
    ].copy()
    if periodo == "Este mes":
        d = d.loc[
            d["Fecha"].dt.year.eq(ini.year)
            & d["Fecha"].dt.month.eq(ini.month)
        ].copy()
    d = d.sort_values("Fecha").reset_index(drop=True)
    if d.empty:
        st.info("No hay cierres en el período seleccionado."); return

    dias = len(d); lineas = int(d["Lineas"].sum()); unidades = int(d["Unidades"].sum()); objetivo = int(d["Objetivo"].sum())
    cumplidos = int((d["Lineas"] >= d["Objetivo"]).sum()); pct = lineas/objetivo if objetivo else 0
    prom_l = d["Lineas"].mean(); prom_u = d["Unidades"].mean(); prom_op = d["OperariosActivos"].mean()
    k1,k2,k3,k4,k5,k6 = st.columns(6)
    k1.metric("Líneas cerradas", _fmt(lineas), f"{_fmt(lineas-objetivo)} vs objetivo")
    k2.metric("Cumplimiento", f"{pct:.1%}", f"{cumplidos}/{dias} días")
    k3.metric("Promedio líneas/día", _fmt(prom_l))
    k4.metric("Unidades/día", _fmt(prom_u))
    k5.metric("Operarios activos", _fmt(prom_op,1), "promedio jornada completa")
    prod = d["Lineas"].sum() / d["OperariosActivos"].sum() if d["OperariosActivos"].sum() else 0
    k6.metric("Líneas / operario", _fmt(prod,1))

    st.markdown("### 📈 Cierre diario vs objetivo")
    g = d.copy(); g["Jornada"] = g["Fecha"].dt.strftime("%d/%m"); g["Orden"] = range(len(g)); g["CumplimientoPct"] = g["Cumplimiento"]*100
    bars = alt.Chart(g).mark_bar(size=34).encode(
        x=alt.X("Jornada:N", sort=alt.SortField(field="Orden", order="ascending"), title=None),
        y=alt.Y("Lineas:Q", title="Líneas cerradas"),
        color=alt.Color("Estado:N", scale=alt.Scale(domain=["Por debajo","Cumplido","Superado"], range=["#d95f5f","#f2c14e","#4caf70"]), legend=alt.Legend(title="Resultado")),
        tooltip=[alt.Tooltip("Jornada:N", title="Fecha"), alt.Tooltip("Lineas:Q", title="Líneas", format=",.0f"), alt.Tooltip("Objetivo:Q", format=",.0f"), alt.Tooltip("Unidades:Q", format=",.0f"), alt.Tooltip("OperariosActivos:Q", title="Operarios activos"), alt.Tooltip("CumplimientoPct:Q", title="Cumplimiento %", format=".1f")]
    )
    puntos = alt.Chart(g).mark_line(point=True, strokeDash=[6,4], color="white").encode(
        x=alt.X("Jornada:N", sort=alt.SortField(field="Orden", order="ascending")), y=alt.Y("Objetivo:Q")
    )
    st.altair_chart((bars+puntos).properties(height=390), use_container_width=True)

    st.markdown("### 👥 Dotación y productividad")
    op = actividad[(actividad["Fecha"].dt.date >= ini) & (actividad["Fecha"].dt.date <= fin)].copy()
    op["Fecha"] = op["Fecha"].dt.strftime("%d/%m/%Y")
    op["HorasActividad"] = op["HorasActividad"].round(1)
    op["EstadoActividad"] = op["JornadaCompleta"].map({True:"Jornada completa", False:"Actividad parcial"})
    op["Clasificacion"] = op["TipoDotacion"]
    st.dataframe(
        op[["Fecha","Operario","Sector","Puesto","Clasificacion","EstadoActividad","HorasActividad","Controles","Lineas","Unidades"]]
        .rename(columns={"EstadoActividad":"Estado"}),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### 🧩 Composición del trabajo")
    fechas_disp = d["Fecha"].dt.date.tolist()
    fecha_sel = st.selectbox(
        "Analizar día",
        fechas_disp,
        index=len(fechas_disp)-1,
        format_func=lambda x:x.strftime("%A %d/%m/%Y"),
        key="obj_fecha_detalle",
    )
    det = detalle[detalle["Fecha"].dt.date.eq(fecha_sel)].copy()

    familia = (
        det.groupby("Familia", as_index=False)
        .agg(
            Lineas=("CodigoArticulo","count"),
            Unidades=("UnidadesNum","sum"),
            Contenedores=("ControlID","nunique"),
        )
        .sort_values("Lineas", ascending=False)
    )

    if not familia.empty:
        familia["Participacion"] = familia["Lineas"] / familia["Lineas"].sum()
        cf1,cf2 = st.columns([1.15,1])

        base = alt.Chart(familia).encode(
            theta=alt.Theta("Lineas:Q", stack=True),
            color=alt.Color("Familia:N", title="Familia"),
            tooltip=[
                alt.Tooltip("Familia:N", title="Familia"),
                alt.Tooltip("Lineas:Q", title="Líneas", format=",.0f"),
                alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                alt.Tooltip("Contenedores:Q", title="Contenedores", format=",.0f"),
                alt.Tooltip("Participacion:Q", title="% líneas", format=".1%"),
            ],
        )
        donut = base.mark_arc(innerRadius=82, outerRadius=145)

        total_lineas = int(familia["Lineas"].sum())
        centro = alt.Chart(
            pd.DataFrame({"texto":[f"{total_lineas:,} líneas"]})
        ).mark_text(
            align="center",
            baseline="middle",
            fontSize=22,
            fontWeight="bold",
            color="white",
        ).encode(text="texto:N")

        cf1.altair_chart((donut + centro).properties(height=360), use_container_width=True)

        tabla_familia = familia.rename(columns={"Participacion":"% líneas"}).copy()
        tabla_familia["% líneas"] = (
            pd.to_numeric(tabla_familia["% líneas"], errors="coerce").fillna(0) * 100
        )

        total = pd.DataFrame([{
            "Familia":"TOTAL",
            "Lineas":int(tabla_familia["Lineas"].sum()),
            "Unidades":int(pd.to_numeric(tabla_familia["Unidades"], errors="coerce").fillna(0).sum()),
            "Contenedores":int(pd.to_numeric(tabla_familia["Contenedores"], errors="coerce").fillna(0).sum()),
            "% líneas":100.0,
        }])
        tabla_familia = pd.concat([tabla_familia, total], ignore_index=True)

        cf2.dataframe(
            tabla_familia,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Familia":st.column_config.TextColumn("Familia"),
                "Lineas":st.column_config.NumberColumn("Líneas", format="%d"),
                "Unidades":st.column_config.NumberColumn("Unidades", format="%d"),
                "Contenedores":st.column_config.NumberColumn("Contenedores", format="%d"),
                "% líneas":st.column_config.NumberColumn("% líneas", format="%.1f%%"),
            },
        )

    st.markdown("### 📋 Resumen diario")
    tabla = d[["Fecha","Lineas","Objetivo","Diferencia","Cumplimiento","Unidades","Contenedores","OperariosActivos","ApoyosActivos","LineasOperario","UnidadesOperario","Estado"]].copy()
    tabla["Fecha"] = tabla["Fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(tabla, use_container_width=True, hide_index=True, column_config={"Cumplimiento":st.column_config.NumberColumn("Cumplimiento", format="%.1%%"), "LineasOperario":st.column_config.NumberColumn("L/operario", format="%.1f"), "UnidadesOperario":st.column_config.NumberColumn("U/operario", format="%.1f")})

    with st.expander("ℹ️ Criterio de operario activo"):
        st.write(
            f"Se considera jornada completa cuando la persona registra al menos {MIN_CONTROLES_ACTIVO} controles "
            f"y actividad distribuida durante ≥ {MIN_HORAS_ACTIVO_LV:g} h de lunes a viernes o "
            f"≥ {MIN_HORAS_ACTIVO_SAB:g} h el sábado. Para Operarios activos sólo cuentan las personas "
            f"que en Maestro Personal figuran con Puesto = 'Linea Control' y tengan al menos 1 control registrado ese día. "
            f"La duración entre primer y último control se conserva para clasificar la jornada como completa/parcial, "
            f"pero ya no se usa para excluir a una persona de la dotación activa. Quienes controlaron pero pertenecen "
            f"a otro puesto/sector se muestran como apoyo y no inflan la dotación de Control."
        )
