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

# Referencias operativas calibradas con Control Feb-Sep 2026.
# Mediana histórica: ~5,91 unidades por línea.
UNIDADES_POR_LINEA_REF = 5.9142
OBJETIVO_UNIDADES_LV = round(OBJETIVO_LV * UNIDADES_POR_LINEA_REF)      # ~4.436
OBJETIVO_UNIDADES_SABADO = round(OBJETIVO_SABADO * UNIDADES_POR_LINEA_REF)  # ~2.957

# En el histórico, las jornadas con >=10% de líneas Sanitarios tuvieron
# una mediana cercana a 400 líneas vs ~666 en el resto.
UMBRAL_SAN_FUERTE = 0.10
FACTOR_OBJETIVO_SAN_FUERTE = 400 / 666
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
    """
    Histórico oficial de Objetivo.

    Fuente:
      Control <Mes> <Año>.csv

    Se usa leer_archivo() con extensión explícita para que:
      - local: lea Data_WMS físico;
      - Streamlit Cloud: lea GitHub main.
    """
    meses = [
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ]

    hoy = date.today()
    tablas = []

    # El WMS histórico disponible comienza en 2026.
    for anio in range(2026, hoy.year + 1):
        mes_hasta = hoy.month if anio == hoy.year else 12
        for numero_mes in range(1, mes_hasta + 1):
            nombre_base = f"Control {meses[numero_mes - 1]} {anio}"
            t = pd.DataFrame()

            # CSV es la descarga mensual normal. Dejamos XLSX como respaldo.
            for ext in (".csv", ".xlsx"):
                try:
                    candidato = leer_archivo(
                        CARPETA_WMS,
                        nombre_base + ext,
                        cache=False,
                    )
                except Exception:
                    candidato = pd.DataFrame()

                if (
                    candidato is not None
                    and not candidato.empty
                    and "ControlContenedorId" in candidato.columns
                ):
                    t = candidato.copy()
                    t["ArchivoOrigen"] = nombre_base + ext
                    break

            if not t.empty:
                tablas.append(t)

    if not tablas:
        return pd.DataFrame()

    total = pd.concat(tablas, ignore_index=True, sort=False)

    # Clave de detalle para no duplicar una línea si un mensual fue republicado.
    total["_ControlID"] = (
        total["ControlContenedorId"].astype("string").fillna("")
        .str.strip().str.replace(r"\.0+$", "", regex=True)
    )
    total["_Codigo"] = (
        total.get("CodigoArticulo", pd.Series("", index=total.index))
        .astype("string").fillna("").str.strip()
    )
    total["_FechaFinKey"] = (
        total.get("FechaFin", pd.Series("", index=total.index))
        .astype("string").fillna("").str.strip()
    )

    total = total.drop_duplicates(
        subset=["_ControlID", "_Codigo", "_FechaFinKey"],
        keep="last",
    )

    return total.drop(
        columns=["_ControlID", "_Codigo", "_FechaFinKey"],
        errors="ignore",
    ).reset_index(drop=True)


@st.cache_data(ttl=300, show_spinner=False)
def _cargar_filtrar_preparaciones() -> pd.DataFrame:
    """
    Fuente Filtrar histórica.

    Regla:
    - Meses CERRADOS: Filtrar Preparacion <Mes> <Año> es la fuente oficial.
    - Mes ACTUAL: Historico Filtrar Preparaciones conserva lo acumulado.
    - Últimos 7 días se incorpora aparte y tiene prioridad en el mes actual.
    """
    meses = [
        "Enero","Febrero","Marzo","Abril","Mayo","Junio",
        "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
    ]
    hoy = date.today()
    tablas = []

    # 1) Mensuales cerrados. NO cargamos el mes actual desde mensual:
    # durante el mes puede ser una descarga parcial.
    for anio in range(2026, hoy.year + 1):
        mes_hasta = (hoy.month - 1) if anio == hoy.year else 12
        for numero_mes in range(1, mes_hasta + 1):
            base = f"Filtrar Preparacion {meses[numero_mes-1]} {anio}"
            for ext in (".csv",".xlsx"):
                try:
                    t = leer_archivo(CARPETA_WMS, base + ext, cache=False)
                except Exception:
                    t = pd.DataFrame()
                if t is not None and not t.empty and "ControlContenedorId" in t.columns:
                    t=t.copy()
                    t["ArchivoOrigen"]=base+ext
                    t["_TipoFuente"]="FILTRAR_MENSUAL_CERRADO"
                    tablas.append(t)
                    break

    # 2) Histórico acumulado: sólo nos interesa para el MES ACTUAL.
    for nombre in [
        "Historico Filtrar Preparaciones.csv",
        "Historico Filtrar Preparaciones.csv.tmp",
        "Historico Filtrar Preparacion.csv",
        "Histórico Filtrar Preparaciones.csv",
    ]:
        try:
            h=leer_archivo(CARPETA_WMS,nombre,cache=False)
        except Exception:
            h=pd.DataFrame()
        if h is not None and not h.empty and "ControlContenedorFechaHoraEstado" in h.columns:
            h=h.copy()
            fh=pd.to_datetime(h["ControlContenedorFechaHoraEstado"],errors="coerce",dayfirst=True)
            h=h[fh.dt.to_period("M").eq(pd.Timestamp(hoy).to_period("M"))].copy()
            if not h.empty:
                h["ArchivoOrigen"]=nombre
                h["_TipoFuente"]="HISTORICO_MES_ACTUAL"
                tablas.append(h)
            break

    if not tablas:
        return pd.DataFrame()

    total=pd.concat(tablas,ignore_index=True,sort=False)

    # Deduplicar únicamente por detalle físico, nunca por Control+Código.
    if "ContenedorDetalleId" in total.columns:
        did=total["ContenedorDetalleId"].astype("string").fillna("").str.strip().str.replace(r"\.0+$","",regex=True)
        con=total[did.ne("")].copy()
        if not con.empty:
            con["_DID"]=con["ContenedorDetalleId"].astype("string").fillna("").str.strip().str.replace(r"\.0+$","",regex=True)
            con=con.drop_duplicates("_DID",keep="last").drop(columns="_DID")
        sin=total[did.eq("")].copy()
        claves=[c for c in ["ControlContenedorId","CodigoArticulo","ControlContenedorFechaHoraEstado","PedidoCodigos"] if c in sin.columns]
        if claves and not sin.empty:
            sin=sin.drop_duplicates(claves,keep="last")
        total=pd.concat([con,sin],ignore_index=True,sort=False)

    return total.reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def _cargar_filtrar_hoy_vivo() -> pd.DataFrame:
    """
    Fuente operativa prioritaria de los últimos 7 días.

    IMPORTANTE: se pide el .csv explícitamente. En Streamlit Cloud esto evita
    que resolver_nombre() lo convierta erróneamente en .xlsx.
    """
    candidatos = [
        "Filtrar Preparacion Ultimos 7 Dias.csv",
        "Filtrar Preparaciones Ultimos 7 Dias.csv",
        "Filtrar Preparación Últimos 7 Días.csv",
        "Filtrar Preparaciones Últimos 7 Días.csv",
    ]

    vivo = pd.DataFrame()
    for nombre in candidatos:
        try:
            t = leer_archivo(CARPETA_WMS, nombre, cache=False)
        except Exception:
            t = pd.DataFrame()

        if (
            t is not None
            and not t.empty
            and "ControlContenedorId" in t.columns
            and "ControlContenedorFechaHoraEstado" in t.columns
        ):
            vivo = t.copy()
            vivo["ArchivoOrigen"] = nombre
            break

    if vivo.empty:
        return pd.DataFrame()

    raw = vivo["ControlContenedorFechaHoraEstado"]
    fecha = pd.to_datetime(raw, errors="coerce", dayfirst=True)

    # Respaldo para formatos ISO / no ambiguos.
    faltan = fecha.isna()
    if faltan.any():
        fecha.loc[faltan] = pd.to_datetime(raw.loc[faltan], errors="coerce")

    vivo["_FechaViva"] = fecha
    vivo = vivo[vivo["_FechaViva"].notna()].copy()
    if vivo.empty:
        return vivo

    # IMPORTANTE:
    # "Últimos 7 días" no se usa sólo para HOY. Es la fuente operativa
    # más completa para TODAS las fechas que contiene, porque conserva
    # Pedido, Despacho, Cliente y el detalle físico real.
    # Esto permite que 30/09, por ejemplo, conserve EASY y PEDIDOS LOZA.
    vivo["_EsUltimos7"] = True

    # Deduplicación de detalle.
    if "ContenedorDetalleId" in vivo.columns:
        did = (
            vivo["ContenedorDetalleId"].astype("string").fillna("")
            .str.strip().str.replace(r"\.0+$", "", regex=True)
        )
        con_id = vivo[did.ne("")].copy()
        if not con_id.empty:
            con_id["_DID"] = (
                con_id["ContenedorDetalleId"].astype("string").fillna("")
                .str.strip().str.replace(r"\.0+$", "", regex=True)
            )
            con_id = con_id.drop_duplicates("_DID", keep="last").drop(columns="_DID")

        sin_id = vivo[did.eq("")].copy()
        if not sin_id.empty:
            claves = [
                c for c in [
                    "ControlContenedorId",
                    "CodigoArticulo",
                    "ControlContenedorFechaHoraEstado",
                ]
                if c in sin_id.columns
            ]
            if claves:
                sin_id = sin_id.drop_duplicates(claves, keep="last")

        vivo = pd.concat([con_id, sin_id], ignore_index=True, sort=False)

    return vivo.drop(columns=["_FechaViva"], errors="ignore").reset_index(drop=True)


@st.cache_data(ttl=1800, show_spinner=False)
def _cargar_maestro_articulos() -> pd.DataFrame:
    try:
        return leer_archivo(CARPETA_MAESTROS, "Maestro Articulo", cache=True)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def _cargar_maestro_personal() -> pd.DataFrame:
    """
    Maestro de personas.

    Primero intenta Data_Maestros/Maestro Personal.xlsx en la fuente versionada.
    Si temporalmente falta, usa un fallback mínimo SOLO para Línea Control,
    evitando que Objetivo vuelva a mostrar 0 operarios.
    """
    try:
        p = leer_archivo(
            CARPETA_MAESTROS,
            "Maestro Personal.xlsx",
            cache=False,
        )
    except Exception:
        p = pd.DataFrame()

    if p is not None and not p.empty:
        return p

    # Respaldo basado en la nómina actual entregada para Objetivo.
    return pd.DataFrame([
        {"Usuario / Login":"ascirica",     "Nombre Completo":"Agustin Scirica",       "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"MDO",      "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"gsoderquvist", "Nombre Completo":"Gustavo Soderquvist",   "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"MDO",      "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"mbatista",     "Nombre Completo":"Maximo Batista",        "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"MDO",      "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"mhernandez",   "Nombre Completo":"Mirko Hernandez",       "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"MDO",      "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"nievasm",      "Nombre Completo":"Maximiliano Nievas",    "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"MDO",      "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"lescanoj",     "Nombre Completo":"Javier Lescano",        "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"EVENTUAL", "Jornada":"Completa", "Estado":"Activo"},
        {"Usuario / Login":"niperez",      "Nombre Completo":"Nicolas Perez",         "Sector":"Preparacion", "Puesto":"Linea Control", "Nómina":"EVENTUAL", "Jornada":"Completa", "Estado":"Activo"},
    ])


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


def _preparar_base(control: pd.DataFrame, filtrar: pd.DataFrame, maestro: pd.DataFrame, personal: pd.DataFrame, filtrar_hoy: pd.DataFrame | None = None):
    """
    Construye Objetivo con dos fuentes separadas:
    - Fechas cerradas: reportes mensuales Control.
    - Jornada viva: Filtrar Preparacion Ultimos 7 Dias, sólo en su fecha máxima.
    Filtrar no reemplaza cierres mensuales históricos.
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

    # La fuente viva se anexa de forma explícita. Para su fecha máxima elimina
    # cualquier copia de esa misma fecha que haya quedado en el consolidado.
    if filtrar_hoy is not None and not filtrar_hoy.empty:
        vivo = filtrar_hoy.copy()
        raw_v = vivo.get("ControlContenedorFechaHoraEstado", pd.Series(index=vivo.index, dtype="object"))
        fv = pd.to_datetime(raw_v, errors="coerce")
        faltan_v = fv.isna()
        if faltan_v.any():
            fv.loc[faltan_v] = pd.to_datetime(raw_v.loc[faltan_v], errors="coerce", dayfirst=True)
        vivo["_FechaTmp"] = fv.dt.normalize()

        # Últimos 7 días actualiza exclusivamente el MES ACTUAL.
        # Un mes cerrado queda congelado por su Filtrar mensual completo.
        periodo_actual = pd.Timestamp(date.today()).to_period("M")
        vivo = vivo[vivo["_FechaTmp"].dt.to_period("M").eq(periodo_actual)].copy()
        fechas_vivas = set(vivo["_FechaTmp"].dropna().tolist())

        if fechas_vivas:
            if not filtrar.empty:
                base_f = filtrar.copy()
                raw_b = base_f.get("ControlContenedorFechaHoraEstado", pd.Series(index=base_f.index, dtype="object"))
                fb = pd.to_datetime(raw_b, errors="coerce")
                faltan_b = fb.isna()
                if faltan_b.any():
                    fb.loc[faltan_b] = pd.to_datetime(raw_b.loc[faltan_b], errors="coerce", dayfirst=True)
                base_f["_FechaTmp"] = fb.dt.normalize()
                # Últimos 7 días manda sobre histórico Filtrar para TODAS
                # las fechas presentes en el archivo, no sólo la fecha máxima.
                base_f = base_f[~base_f["_FechaTmp"].isin(fechas_vivas)].drop(columns="_FechaTmp", errors="ignore")
            else:
                base_f = pd.DataFrame()

            vivo = vivo.drop(columns="_FechaTmp", errors="ignore")
            filtrar = pd.concat([base_f, vivo], ignore_index=True, sort=False)

    if not filtrar.empty and "ControlContenedorId" in filtrar.columns:
        f = filtrar.copy()
        f["ControlID"] = (f["ControlContenedorId"].astype("string").fillna("")
                          .str.replace(r"\.0+$", "", regex=True).str.strip())
        f["CodigoArticulo"] = f.get("CodigoArticulo", pd.Series("", index=f.index)).astype("string").fillna("").str.strip()

        # Línea comercial del día vivo:
        # una misma línea puede estar repartida en varios contenedores.
        # Por eso NO usamos ControlContenedorId + Código para contar líneas.
        if "Id" in f.columns:
            f["PedidoKey"] = (
                f["Id"].astype("string").fillna("")
                .str.strip().str.replace(r"\.0+$", "", regex=True)
            )
        elif "PedidoCodigos" in f.columns:
            f["PedidoKey"] = f["PedidoCodigos"].astype("string").fillna("").str.strip()
        else:
            f["PedidoKey"] = f["ControlID"]

        f["LineaComercialKey"] = f["PedidoKey"] + "|" + f["CodigoArticulo"]

        # Contexto operativo explícito del WMS.
        # EASY sólo se marca cuando la fuente lo identifica: cliente CENCOSUD
        # o descripción/código de despacho EASY. No se infiere por cantidad.
        despacho_desc = (
            f.get("DespachoDescripcion", pd.Series("", index=f.index))
            .astype("string").fillna("").str.strip().str.upper()
        )

        # EASY oficial: únicamente agrupador/despacho "EASY dd-mm".
        # NO usamos Cliente=CENCOSUD porque también existen sucursales chicas
        # que no deben clasificar la jornada como EASY.
        f["EsEasy"] = despacho_desc.str.match(
            r"^EASY\s+\d{2}-\d{2}$",
            case=False,
            na=False,
        )

        # LOZA explícita manda sobre el porcentaje de familia.
        f["EsLozaExplicita"] = despacho_desc.str.contains(
            r"PEDIDOS\s+LOZA",
            case=False,
            regex=True,
            na=False,
        )

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

        # Los reportes mensuales Control no incluyen Pedido.
        # Conservamos su granularidad histórica disponible: Control + Código.
        c["LineaComercialKey"] = c["ControlID"] + "|" + c["CodigoArticulo"]
        # El reporte mensual Control no trae cliente/pedido/despacho.
        # No inventamos retrospectivamente la marca EASY.
        c["EsEasy"] = False
        c["EsLozaExplicita"] = False

        c["UsuarioMostrar"] = c.get("Usuario", pd.Series("", index=c.index)).astype("string").fillna("").str.strip()
        c["FechaControlDT"] = _fecha_control(c.get("FechaFin", pd.Series(index=c.index, dtype="object")))
        c = c[c["FechaControlDT"].notna() & c["ControlID"].ne("")].copy()
        c["Fecha"] = c["FechaControlDT"].dt.normalize()
        c["UnidadesNum"] = pd.to_numeric(c.get("Unidades", 0), errors="coerce").fillna(0)

        det_c = c.drop_duplicates(["ControlID", "CodigoArticulo", "Fecha"], keep="last").copy()
        det_c["Fuente"] = "Control"
        det_c["_TipoFuente"] = "CONTROL_FALLBACK"
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

        # Para jornadas históricas elegimos la fuente más completa.
        # Para HOY, si existe información proveniente de "Últimos 7 días",
        # forzamos Filtrar porque es la fuente viva que se actualiza durante la jornada.
        filtrar_tiene_hoy_vivo = (
            not df.empty
            and "_EsUltimos7" in df.columns
            and df["_EsUltimos7"].fillna(False).astype(bool).any()
        )

        # Filtrar es la fuente operativa principal: conserva pedido, despacho,
        # cliente y detalle físico. Control sólo completa fechas sin Filtrar.
        usar_filtrar = len(df) > 0
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

    # Sanitarios se identifica desde el maestro de artículos.
    fam_norm = detalle["Familia"].astype("string").fillna("").str.strip().str.lower()
    sec_norm = detalle["Sector"].astype("string").fillna("").str.strip().str.lower()
    loza_exp = detalle.get("EsLozaExplicita", pd.Series(False, index=detalle.index)).fillna(False).astype(bool)
    # LOZA OPERATIVA: clasificación por código, no por Familia.
    # Incluye únicamente piezas que generan carga física real:
    #   INO...-1 = inodoro
    #   INO...-2 = mochila/depósito
    #   BID...   = bidet
    #   PDU...   = piso de ducha (PDU120 excluido: es desagüe)
    #   BAN...   = bañera
    # Excluye asientos, fijaciones, válvulas, tapas, repuestos y BACHAS.
    cod_loza = detalle["CodigoArticulo"].astype("string").fillna("").str.strip().str.upper()
    detalle["TipoLoza"] = "NO_LOZA"
    detalle.loc[cod_loza.str.match(r"^INO.+-1$", na=False), "TipoLoza"] = "INODORO"
    detalle.loc[cod_loza.str.match(r"^INO.+-2$", na=False), "TipoLoza"] = "MOCHILA"
    detalle.loc[cod_loza.str.match(r"^BID", na=False), "TipoLoza"] = "BIDET"
    detalle.loc[cod_loza.str.match(r"^PDU", na=False) & ~cod_loza.eq("PDU120"), "TipoLoza"] = "PISO_DUCHA"
    detalle.loc[cod_loza.str.match(r"^BAN", na=False), "TipoLoza"] = "BANERA"
    detalle["EsSanitario"] = detalle["TipoLoza"].ne("NO_LOZA")
    if "EsEasy" not in detalle.columns:
        detalle["EsEasy"] = False
    detalle["EsEasy"] = detalle["EsEasy"].fillna(False).astype(bool)

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
            Lineas=("LineaComercialKey", "nunique"),
            Unidades=("UnidadesNum", "sum"),
            Contenedores=("ControlID", "nunique"),
        )
        actividad = actividad.merge(lop, on=["Fecha", "UsuarioMostrar"], how="left")

    # Etiqueta de fuente para auditoría.
    if "_TipoFuente" not in detalle.columns:
        detalle["_TipoFuente"] = detalle.get("Fuente", "SIN_FUENTE")

    diario = detalle.groupby("Fecha", as_index=False).agg(
        FuenteDatos=("_TipoFuente", lambda s: " + ".join(sorted(set(str(x) for x in s.dropna() if str(x))))),
        Lineas=("LineaComercialKey", "nunique"),
        Unidades=("UnidadesNum", "sum"),
        Contenedores=("ControlID", "nunique"),
        LineasSan=("LineaComercialKey", lambda s: s[detalle.loc[s.index, "EsSanitario"]].nunique()),
        UnidadesSan=("UnidadesNum", lambda s: s[detalle.loc[s.index, "EsSanitario"]].sum()),
        LineasLoza=("LineaComercialKey", lambda s: s[detalle.loc[s.index, "EsLozaExplicita"].fillna(False).astype(bool)].nunique() if "EsLozaExplicita" in detalle.columns else 0),
        UnidadesLoza=("UnidadesNum", lambda s: s[detalle.loc[s.index, "EsLozaExplicita"].fillna(False).astype(bool)].sum() if "EsLozaExplicita" in detalle.columns else 0),
        LineasEasy=("LineaComercialKey", lambda s: s[detalle.loc[s.index, "EsEasy"]].nunique()),
        UnidadesEasy=("UnidadesNum", lambda s: s[detalle.loc[s.index, "EsEasy"]].sum()),
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
    # --- Carga operativa LOZA por jornada ---
    # El inodoro y su mochila del mismo modelo forman un COMBO.
    # No sumamos 1+1 como dos piezas de carga: emparejamos cantidades.
    loza = detalle[detalle["EsSanitario"]].copy()
    if not loza.empty:
        loza["UnidadesLozaNum"] = pd.to_numeric(loza["UnidadesNum"], errors="coerce").fillna(0)
        loza["CodigoLoza"] = loza["CodigoArticulo"].astype("string").fillna("").str.upper().str.strip()
        loza["ModeloINO"] = loza["CodigoLoza"].str.replace(r"-[12]$", "", regex=True)

        # Totales por día/tipo.
        piv = loza.pivot_table(
            index="Fecha", columns="TipoLoza", values="UnidadesLozaNum",
            aggfunc="sum", fill_value=0
        )
        for col in ["INODORO","MOCHILA","BIDET","PISO_DUCHA","BANERA"]:
            if col not in piv.columns:
                piv[col] = 0

        # Emparejamiento de INO-1 + INO-2 por modelo.
        inos = loza[loza["TipoLoza"].isin(["INODORO","MOCHILA"])].pivot_table(
            index=["Fecha","ModeloINO"], columns="TipoLoza",
            values="UnidadesLozaNum", aggfunc="sum", fill_value=0
        ).reset_index()
        for col in ["INODORO","MOCHILA"]:
            if col not in inos.columns:
                inos[col] = 0
        inos["CombosINO"] = inos[["INODORO","MOCHILA"]].min(axis=1)
        inos["InodorosSueltos"] = (inos["INODORO"] - inos["CombosINO"]).clip(lower=0)
        inos["MochilasSueltas"] = (inos["MOCHILA"] - inos["CombosINO"]).clip(lower=0)
        ino_dia = inos.groupby("Fecha", as_index=False)[["CombosINO","InodorosSueltos","MochilasSueltas"]].sum()

        piv = piv.reset_index().merge(ino_dia, on="Fecha", how="left").fillna(0)

        # Equivalentes físicos: combo cuenta una vez.
        piv["LozaEquivalente"] = (
            piv["CombosINO"] + piv["InodorosSueltos"] + piv["MochilasSueltas"]
            + piv["BIDET"] + piv["PISO_DUCHA"] + piv["BANERA"]
        )

        # Pallets equivalentes de carga operativa.
        # Inodoro: 6/pallet. Bidet: 10/pallet.
        # Mochilas cerradas varían 35/45/48; usamos 45 como referencia
        # visible y mantenemos unidades separadas para poder recalibrarlo.
        # Combo usa el componente dominante: el inodoro (6/pallet), no suma mochila.
        piv["PalletsEqINO"] = (piv["CombosINO"] + piv["InodorosSueltos"]) / 6.0
        piv["PalletsEqBidet"] = piv["BIDET"] / 10.0
        piv["PalletsEqMochilaSuelta"] = piv["MochilasSueltas"] / 45.0
        # PDU/Bañera se dejan como piezas visibles; no inventamos capacidad pallet.
        piv["PalletsEqLozaBase"] = piv["PalletsEqINO"] + piv["PalletsEqBidet"] + piv["PalletsEqMochilaSuelta"]

        diario = diario.merge(
            piv[["Fecha","INODORO","MOCHILA","BIDET","PISO_DUCHA","BANERA",
                 "CombosINO","InodorosSueltos","MochilasSueltas",
                 "LozaEquivalente","PalletsEqLozaBase"]],
            on="Fecha", how="left"
        )
    else:
        for col in ["INODORO","MOCHILA","BIDET","PISO_DUCHA","BANERA",
                    "CombosINO","InodorosSueltos","MochilasSueltas",
                    "LozaEquivalente","PalletsEqLozaBase"]:
            diario[col] = 0

    for col in ["INODORO","MOCHILA","BIDET","PISO_DUCHA","BANERA",
                "CombosINO","InodorosSueltos","MochilasSueltas",
                "LozaEquivalente","PalletsEqLozaBase"]:
        diario[col] = pd.to_numeric(diario[col], errors="coerce").fillna(0)

    # --- Clasificación de CARGA LOZA por PEDIDO/PREPARACIÓN ---
    # Sólo combo INO+mochila e inodoro suelto + BIDET determinan carga.
    # 6 combos/inodoros = 1 pallet; 10 bidets = 1 pallet.
    # Pisos de ducha y bañeras se auditan, pero NO disparan carga operativa.
    # Umbral: >= 3 pallets equivalentes EN UN MISMO PEDIDO/PREPARACIÓN.
    carga_base = detalle[detalle["EsSanitario"]].copy()
    if not carga_base.empty:
        carga_base["UnidadesCarga"] = pd.to_numeric(carga_base["UnidadesNum"], errors="coerce").fillna(0)
        carga_base["CodigoCarga"] = carga_base["CodigoArticulo"].astype("string").fillna("").str.upper().str.strip()
        carga_base["ModeloINO"] = carga_base["CodigoCarga"].str.replace(r"-[12]$", "", regex=True)

        # La clave ya normalizada por la fuente prioriza Id y luego PedidoCodigos.
        carga_base["PedidoCarga"] = carga_base.get("PedidoKey", pd.Series("", index=carga_base.index)).astype("string").fillna("")
        vacio = carga_base["PedidoCarga"].str.strip().eq("")
        if vacio.any():
            carga_base.loc[vacio, "PedidoCarga"] = carga_base.loc[vacio, "ControlID"].astype("string")

        # INO-1 / INO-2 se emparejan dentro del mismo pedido y modelo.
        ci = carga_base[carga_base["TipoLoza"].isin(["INODORO","MOCHILA"])].pivot_table(
            index=["Fecha","PedidoCarga","ModeloINO"],
            columns="TipoLoza",
            values="UnidadesCarga",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        for col in ["INODORO","MOCHILA"]:
            if col not in ci.columns:
                ci[col] = 0
        ci["Combos"] = ci[["INODORO","MOCHILA"]].min(axis=1)
        ci["InodorosSueltosPedido"] = (ci["INODORO"] - ci["Combos"]).clip(lower=0)

        ino_pedido = ci.groupby(["Fecha","PedidoCarga"], as_index=False).agg(
            CombosPedido=("Combos","sum"),
            InodorosSueltosPedido=("InodorosSueltosPedido","sum"),
        )

        bid = carga_base[carga_base["TipoLoza"].eq("BIDET")].groupby(
            ["Fecha","PedidoCarga"], as_index=False
        )["UnidadesCarga"].sum().rename(columns={"UnidadesCarga":"BidetsPedido"})

        pisos = carga_base[carga_base["TipoLoza"].eq("PISO_DUCHA")].groupby(
            ["Fecha","PedidoCarga"], as_index=False
        )["UnidadesCarga"].sum().rename(columns={"UnidadesCarga":"PisosDuchaPedido"})

        ban = carga_base[carga_base["TipoLoza"].eq("BANERA")].groupby(
            ["Fecha","PedidoCarga"], as_index=False
        )["UnidadesCarga"].sum().rename(columns={"UnidadesCarga":"BanerasPedido"})

        pedidos = ino_pedido.merge(bid, on=["Fecha","PedidoCarga"], how="outer")
        pedidos = pedidos.merge(pisos, on=["Fecha","PedidoCarga"], how="outer")
        pedidos = pedidos.merge(ban, on=["Fecha","PedidoCarga"], how="outer").fillna(0)

        for col in ["CombosPedido","InodorosSueltosPedido","BidetsPedido","PisosDuchaPedido","BanerasPedido"]:
            pedidos[col] = pd.to_numeric(pedidos[col], errors="coerce").fillna(0)

        pedidos["PalletsEqPedido"] = (
            (pedidos["CombosPedido"] + pedidos["InodorosSueltosPedido"]) / 6.0
            + pedidos["BidetsPedido"] / 10.0
        )
        pedidos["EsCargaLoza"] = pedidos["PalletsEqPedido"].ge(3.0)
        pedidos["TieneLozaPedido"] = (
            pedidos[["CombosPedido","InodorosSueltosPedido","BidetsPedido","PisosDuchaPedido","BanerasPedido"]]
            .sum(axis=1).gt(0)
        )

        resumen_carga = pedidos.groupby("Fecha", as_index=False).agg(
            PedidosConLoza=("TieneLozaPedido","sum"),
            PedidosCargaLoza=("EsCargaLoza","sum"),
        )
        chicos = pedidos[pedidos["TieneLozaPedido"] & ~pedidos["EsCargaLoza"]].groupby("Fecha").size().rename("PedidosLozaChicos").reset_index()
        carga = pedidos[pedidos["EsCargaLoza"]].groupby("Fecha", as_index=False).agg(
            CombosCarga=("CombosPedido","sum"),
            InodorosSueltosCarga=("InodorosSueltosPedido","sum"),
            BidetsCarga=("BidetsPedido","sum"),
            PalletsEqCarga=("PalletsEqPedido","sum"),
            MayorCargaPedido=("PalletsEqPedido","max"),
        )
        resumen_carga = resumen_carga.merge(chicos, on="Fecha", how="left").merge(carga, on="Fecha", how="left").fillna(0)
        diario = diario.merge(resumen_carga, on="Fecha", how="left")
    else:
        for col in ["PedidosConLoza","PedidosLozaChicos","PedidosCargaLoza","CombosCarga",
                    "InodorosSueltosCarga","BidetsCarga","PalletsEqCarga","MayorCargaPedido"]:
            diario[col] = 0

    for col in ["PedidosConLoza","PedidosLozaChicos","PedidosCargaLoza","CombosCarga",
                "InodorosSueltosCarga","BidetsCarga","PalletsEqCarga","MayorCargaPedido"]:
        if col not in diario.columns:
            diario[col] = 0
        diario[col] = pd.to_numeric(diario[col], errors="coerce").fillna(0)

    diario["DiaSemana"] = diario["Fecha"].dt.weekday
    diario = diario[diario["DiaSemana"].le(5)].copy()
    diario["ObjetivoBase"] = diario["DiaSemana"].eq(5).map({True:OBJETIVO_SABADO, False:OBJETIVO_LV})
    diario["ObjetivoUnidades"] = diario["DiaSemana"].eq(5).map({True:OBJETIVO_UNIDADES_SABADO, False:OBJETIVO_UNIDADES_LV})

    diario["PctSan"] = diario["LineasSan"].div(diario["Lineas"].replace(0, pd.NA)).fillna(0)
    diario["PctEasy"] = diario["LineasEasy"].div(diario["Lineas"].replace(0, pd.NA)).fillna(0)

    # SAN fuerte ajusta la referencia de líneas porque el histórico muestra
    # una caída estructural de throughput cuando >=10% de las líneas son Sanitarios.
    diario["SanFuerte"] = diario["PctSan"].ge(UMBRAL_SAN_FUERTE)
    diario["Objetivo"] = diario["ObjetivoBase"].astype(float)
    diario.loc[diario["SanFuerte"], "Objetivo"] = (
        diario.loc[diario["SanFuerte"], "ObjetivoBase"] * FACTOR_OBJETIVO_SAN_FUERTE
    ).round()

    diario["CumplimientoLineas"] = diario["Lineas"] / diario["Objetivo"].replace(0, pd.NA)
    diario["CumplimientoUnidades"] = diario["Unidades"] / diario["ObjetivoUnidades"].replace(0, pd.NA)

    # Cumplimiento operativo: reconoce dos formas válidas de consumir capacidad.
    # Muchas líneas chicas -> gobiernan líneas.
    # Pocas líneas con mucha cantidad (caso EASY) -> gobiernan unidades.
    diario["Cumplimiento"] = diario[["CumplimientoLineas", "CumplimientoUnidades"]].max(axis=1).fillna(0)
    diario["Diferencia"] = diario["Lineas"] - diario["Objetivo"]

    # Sólo un pedido individual >=3 pallets equivalentes de combo/inodoro+bidet
    # convierte la jornada en CARGA LOZA. La suma de pedidos chicos NO lo hace.
    diario["TieneLozaSan"] = diario["PedidosCargaLoza"].gt(0)
    diario["Mix"] = "Normal"
    diario.loc[diario["TieneLozaSan"], "Mix"] = "🚽 CARGA LOZA"
    diario.loc[diario["LineasEasy"].gt(0), "Mix"] = "🏬 EASY"
    diario.loc[diario["TieneLozaSan"] & diario["LineasEasy"].gt(0), "Mix"] = "🏬🚽 MIX"
    diario["LineasOperario"] = diario["Lineas"].div(diario["OperariosActivos"].replace(0, pd.NA))
    diario["UnidadesOperario"] = diario["Unidades"].div(diario["OperariosActivos"].replace(0, pd.NA))
    fecha_en_curso = None
    if filtrar_hoy is not None and not filtrar_hoy.empty:
        raw_h = filtrar_hoy.get("ControlContenedorFechaHoraEstado", pd.Series(index=filtrar_hoy.index, dtype="object"))
        fh = pd.to_datetime(raw_h, errors="coerce")
        faltan_h = fh.isna()
        if faltan_h.any():
            fh.loc[faltan_h] = pd.to_datetime(raw_h.loc[faltan_h], errors="coerce", dayfirst=True)
        if fh.notna().any():
            fecha_en_curso = fh.dt.normalize().max().date()

    diario["Estado"] = diario.apply(
        lambda r: (
            "En curso"
            if fecha_en_curso is not None and r.Fecha.date() == fecha_en_curso
            else ("Superado" if r.Cumplimiento > 1.0 else ("Cumplido" if r.Cumplimiento >= 0.95 else "Por debajo"))
        ),
        axis=1,
    )
    return diario.sort_values("Fecha"), detalle, actividad

def render_objetivo() -> None:
    st.subheader("🎯 Objetivo")
    st.caption("Fuente: Filtrar Preparaciones histórico/mensual + Últimos 7 Días como actualización viva; Control mensual sólo completa fechas sin Filtrar. EASY se marca únicamente cuando el agrupador/despacho es EASY dd-mm.")

    control = _cargar_control_historico()
    filtrar = _cargar_filtrar_preparaciones()
    filtrar_hoy = _cargar_filtrar_hoy_vivo()
    maestro = _cargar_maestro_articulos()
    personal = _cargar_maestro_personal()
    diario, detalle, actividad = _preparar_base(control, filtrar, maestro, personal, filtrar_hoy)
    if diario.empty:
        st.warning("No encontré histórico válido de Filtrar Preparaciones en Data_WMS.")
        return

    fmax = diario["Fecha"].max().date()
    fmin = diario["Fecha"].min().date()
    diario["Fecha"] = pd.to_datetime(diario["Fecha"], errors="coerce").dt.normalize()

    st.markdown("### 📅 Período de análisis")
    fd1, fd2 = st.columns(2)
    ini = fd1.date_input(
        "Desde",
        value=max(fmin, fmax - timedelta(days=29)),
        min_value=fmin,
        max_value=fmax,
        key="obj_desde_directo",
    )
    fin = fd2.date_input(
        "Hasta",
        value=fmax,
        min_value=fmin,
        max_value=fmax,
        key="obj_hasta_directo",
    )
    if ini > fin:
        st.warning("La fecha Desde no puede ser posterior a Hasta.")
        return

    d = diario.loc[
        diario["Fecha"].between(pd.Timestamp(ini), pd.Timestamp(fin), inclusive="both")
    ].copy()
    d = d.sort_values("Fecha", kind="stable").reset_index(drop=True)
    if d.empty:
        st.info("No hay cierres en el período seleccionado.")
        return

    dias = len(d)
    lineas = int(d["Lineas"].sum())
    unidades = int(d["Unidades"].sum())
    objetivo = int(d["Objetivo"].sum())
    cerrados = d[d["Estado"].ne("En curso")].copy()
    cumplidos = int((cerrados["Cumplimiento"] >= 0.95).sum())
    dias_cerrados = len(cerrados)
    pct = float(cerrados["Cumplimiento"].mean()) if len(cerrados) else float(d["Cumplimiento"].mean())
    prom_u = d["Unidades"].mean()
    prom_op = d["OperariosActivos"].mean()
    prod = d["Lineas"].sum() / d["OperariosActivos"].sum() if d["OperariosActivos"].sum() else 0
    upl = unidades / lineas if lineas else 0
    jornadas_easy = int(d["LineasEasy"].gt(0).sum())
    jornadas_loza = int(d["TieneLozaSan"].sum())

    def _kpi_card(icono, titulo, valor, detalle_txt):
        st.markdown(
            f"""
            <div style="
                border:1px solid #2d3a4d;
                border-radius:10px;
                padding:14px 16px 12px 16px;
                min-height:108px;
                background:#111823;
                margin-bottom:10px;">
                <div style="font-size:13px;font-weight:700;color:#f3f6fb;margin-bottom:8px;">
                    {icono} {titulo}
                </div>
                <div style="font-size:27px;font-weight:800;line-height:1.05;color:#ffffff;">
                    {valor}
                </div>
                <div style="font-size:11px;color:#8fb7e8;margin-top:10px;">
                    {detalle_txt}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    r1 = st.columns(4)
    with r1[0]:
        _kpi_card("🎯", "Cumplimiento operativo", f"{pct:.1%}", f"{cumplidos} de {dias_cerrados} jornadas cerradas ≥95%")
    with r1[1]:
        _kpi_card("📦", "Líneas cerradas", _fmt(lineas), f"Objetivo ajustado acumulado: {_fmt(objetivo)}")
    with r1[2]:
        _kpi_card("🔢", "Unidades", _fmt(unidades), f"{_fmt(prom_u)} promedio por jornada")
    with r1[3]:
        _kpi_card("⚖️", "Unidades / línea", _fmt(upl,1), f"Referencia histórica: {_fmt(UNIDADES_POR_LINEA_REF,1)}")

    r2 = st.columns(4)
    with r2[0]:
        _kpi_card("👥", "Dotación", _fmt(prom_op,1), "Operarios activos promedio")
    with r2[1]:
        _kpi_card("⚡", "Líneas / operario", _fmt(prod,1), "Productividad acumulada de Control")
    with r2[2]:
        _kpi_card("🏬", "Jornadas EASY", _fmt(jornadas_easy), f"{(jornadas_easy/dias if dias else 0):.0%} de las jornadas del período")
    with r2[3]:
        _kpi_card("🚽", "Jornadas LOZA / SAN", _fmt(jornadas_loza), f"{(jornadas_loza/dias if dias else 0):.0%} de las jornadas del período")

    st.markdown("### 📈 Producción diaria vs capacidad operativa")
    g = d.copy().sort_values("Fecha", kind="stable").reset_index(drop=True)
    # Etiqueta visual compacta: sólo iconos sobre la barra.
    # El valor completo de Mix se conserva para auditoría y tooltip.
    g["IconoMix"] = ""
    g.loc[g["Mix"].eq("🏬 EASY"), "IconoMix"] = "🏬"
    g.loc[g["Mix"].eq("🚽 CARGA LOZA"), "IconoMix"] = "🚽"
    g.loc[g["Mix"].eq("🏬🚽 MIX"), "IconoMix"] = "🏬 🚽"
    g["Jornada"] = g["Fecha"].dt.strftime("%d/%m")
    g["Orden"] = range(len(g))
    g["CumplimientoPct"] = g["Cumplimiento"]*100
    g["CumplimientoLineasPct"] = g["CumplimientoLineas"]*100
    g["CumplimientoUnidadesPct"] = g["CumplimientoUnidades"]*100
    g["UnidadesLinea"] = g["Unidades"].div(g["Lineas"].replace(0, pd.NA)).fillna(0)
    bars = alt.Chart(g).mark_bar(size=34).encode(
        x=alt.X("Fecha:T", title=None, axis=alt.Axis(format="%d/%m", labelAngle=-55)),
        y=alt.Y("Lineas:Q", title="Líneas cerradas"),
        color=alt.Color("Estado:N", scale=alt.Scale(domain=["Por debajo","Cumplido","Superado","En curso"], range=["#d95f5f","#f2c14e","#4caf70","#5dade2"]), legend=alt.Legend(title="Resultado")),
        tooltip=[
            alt.Tooltip("Jornada:N", title="Fecha"),
            alt.Tooltip("Mix:N", title="Mix"),
            alt.Tooltip("Lineas:Q", title="Líneas", format=",.0f"),
            alt.Tooltip("Objetivo:Q", title="Objetivo líneas ajustado", format=",.0f"),
            alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
            alt.Tooltip("ObjetivoUnidades:Q", title="Referencia unidades", format=",.0f"),
            alt.Tooltip("UnidadesLinea:Q", title="Unidades/línea", format=".1f"),
            alt.Tooltip("LineasEasy:Q", title="Líneas EASY", format=",.0f"),
            alt.Tooltip("UnidadesEasy:Q", title="Unidades EASY", format=",.0f"),
            alt.Tooltip("PedidosCargaLoza:Q", title="Pedidos CARGA LOZA", format=",.0f"),
            alt.Tooltip("CombosCarga:Q", title="Combos en carga", format=",.0f"),
            alt.Tooltip("BidetsCarga:Q", title="Bidets en carga", format=",.0f"),
            alt.Tooltip("PalletsEqCarga:Q", title="Pallets eq. carga", format=".1f"),
            alt.Tooltip("MayorCargaPedido:Q", title="Mayor pedido pallets eq.", format=".1f"),
            alt.Tooltip("PISO_DUCHA:Q", title="Pisos ducha (informativo)", format=",.0f"),
            alt.Tooltip("BANERA:Q", title="Bañeras (informativo)", format=",.0f"),
            alt.Tooltip("OperariosActivos:Q", title="Operarios activos"),
            alt.Tooltip("CumplimientoLineasPct:Q", title="Cumpl. líneas %", format=".1f"),
            alt.Tooltip("CumplimientoUnidadesPct:Q", title="Cumpl. unidades %", format=".1f"),
            alt.Tooltip("CumplimientoPct:Q", title="Cumpl. operativo %", format=".1f"),
        ]
    )
    puntos = alt.Chart(g).mark_line(point=True, strokeDash=[6,4], color="white").encode(
        x=alt.X("Fecha:T"), y=alt.Y("Objetivo:Q")
    )
    marcas = alt.Chart(g[g["IconoMix"].ne("")]).mark_text(
        dy=-10,
        fontSize=18,
        align="center",
        baseline="bottom",
    ).encode(
        x=alt.X("Fecha:T"),
        y=alt.Y("Lineas:Q"),
        text=alt.Text("IconoMix:N"),
        tooltip=[alt.Tooltip("Mix:N", title="Contexto operativo")]
    )
    st.altair_chart((bars+puntos+marcas).properties(height=410), use_container_width=True)

    with st.expander("🔎 Auditoría de fuente del período"):
        aud = d[[
            "Fecha","FuenteDatos","Lineas","Unidades",
            "LineasEasy","UnidadesEasy",
            "PedidosConLoza","PedidosLozaChicos","PedidosCargaLoza",
            "CombosCarga","InodorosSueltosCarga","BidetsCarga",
            "PalletsEqCarga","MayorCargaPedido",
            "PISO_DUCHA","BANERA",
            "LozaEquivalente",
            "LineasLoza","UnidadesLoza","Mix"
        ]].copy()
        aud["Fecha"] = aud["Fecha"].dt.strftime("%d/%m/%Y")
        st.dataframe(
            aud.rename(columns={
                "Lineas":"Líneas totales",
                "Unidades":"Unidades totales",
                "LineasEasy":"Líneas EASY",
                "UnidadesEasy":"Unidades EASY",
                "PedidosConLoza":"Pedidos con LOZA",
                "PedidosLozaChicos":"Pedidos LOZA chicos",
                "PedidosCargaLoza":"Pedidos CARGA LOZA",
                "CombosCarga":"Combos en carga",
                "InodorosSueltosCarga":"Inodoros sueltos carga",
                "BidetsCarga":"Bidets en carga",
                "PalletsEqCarga":"Pallets eq. CARGA",
                "MayorCargaPedido":"Mayor pedido (pallets eq.)",
                "PISO_DUCHA":"Pisos ducha",
                "BANERA":"Bañeras",
                "LozaEquivalente":"LOZA equivalente total",
                "LineasLoza":"Líneas PEDIDOS LOZA",
                "UnidadesLoza":"Unidades PEDIDOS LOZA",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "CARGA LOZA se evalúa por pedido/preparación: 6 combos/inodoros = 1 pallet y 10 bidets = 1 pallet. "
            "Sólo pedidos individuales de 3 pallets equivalentes o más marcan 🚽 CARGA LOZA. "
            "Varios pedidos chicos no se acumulan para disparar la marca. Pisos de ducha y bañeras se muestran, "
            "pero se consideran carga normal de la jornada."
        )

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
            Lineas=("LineaComercialKey","nunique"),
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
    tabla = d[["Fecha","Mix","Lineas","Objetivo","CumplimientoLineas","Unidades","ObjetivoUnidades","CumplimientoUnidades","Cumplimiento","PctSan","Contenedores","OperariosActivos","ApoyosActivos","LineasOperario","UnidadesOperario","Estado"]].copy()
    tabla["Fecha"] = tabla["Fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(tabla, use_container_width=True, hide_index=True, column_config={
        "CumplimientoLineas":st.column_config.NumberColumn("Cumpl. líneas", format="%.1%%"),
        "CumplimientoUnidades":st.column_config.NumberColumn("Cumpl. unidades", format="%.1%%"),
        "Cumplimiento":st.column_config.NumberColumn("Cumpl. operativo", format="%.1%%"),
        "PctSan":st.column_config.NumberColumn("% SAN", format="%.1%%"),
        "LineasOperario":st.column_config.NumberColumn("L/operario", format="%.1f"),
        "UnidadesOperario":st.column_config.NumberColumn("U/operario", format="%.1f")
    })

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
