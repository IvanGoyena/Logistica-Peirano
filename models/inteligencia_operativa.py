from __future__ import annotations

import math
import unicodedata
from datetime import date
import pandas as pd

try:
    from config_planificacion import obtener_planificacion_expreso, TIPOS_VEHICULOS
except Exception:
    TIPOS_VEHICULOS = {"Camioneta": {"capacidad_m3": 8.0}, "Camion": {"capacidad_m3": 15.0}}
    def obtener_planificacion_expreso(zona_expreso):
        return {
            "ZonaExpresoNormalizada": _norm(zona_expreso) if "_norm" in globals() else str(zona_expreso).strip().upper(),
            "PlanificacionExpreso": "", "GrupoExpreso": "",
            "CodigosDespachoExpreso": [], "ZonaExpresoConfigurada": False,
        }

CAPACIDAD_CONTROL = {
    1: {"lineas": 300, "unidades": 1800},
    2: {"lineas": 520, "unidades": 3500},
    3: {"lineas": 701, "unidades": 4635},
    4: {"lineas": 809, "unidades": 5759},
    5: {"lineas": 923, "unidades": 5373},
}
OBJETIVO_LINEAS_PERSONA = 202
OBJETIVO_UNIDADES_PERSONA = 1440
M3_CAMIONETA = 8.0
DIAS_HABILES = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
PREPARACION_POR_ENTREGA = {
    "LUNES": "JUEVES",
    "MARTES": "VIERNES",
    "MIERCOLES": "LUNES",
    "JUEVES": "MARTES",
    "VIERNES": "MIERCOLES",
}


def _texto(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _norm(v):
    t = _texto(v).upper()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return " ".join(t.split())


def preparar_maestro_personal(df_personal):
    cols = ["Nombre", "Apellido", "Sector", "Puesto", "Nomina", "Jornada", "RolOperativo"]
    if df_personal is None or df_personal.empty:
        return pd.DataFrame(columns=cols)
    df = df_personal.copy()

    # Algunos lectores devuelven el maestro con encabezados genéricos y la fila
    # real de títulos dentro de los datos. Si ocurre, la promovemos automáticamente.
    actuales = {_norm(c) for c in df.columns}
    esperadas = {"NOMBRE", "APELLIDO", "SECTOR", "PUESTO", "NOMINA", "JORNADA"}
    if len(actuales & esperadas) < 3:
        for idx in df.index[:8]:
            vals = [_norm(v) for v in df.loc[idx].tolist()]
            if len(set(vals) & esperadas) >= 3:
                nuevos = [str(v).strip() if _texto(v) else f"col_{i}" for i, v in enumerate(df.loc[idx].tolist())]
                df = df.loc[df.index > idx].copy()
                df.columns = nuevos
                df = df.reset_index(drop=True)
                break

    mapa = {_norm(c): c for c in df.columns}
    ren = {}
    for dest, cands in {
        "Nombre": ["NOMBRE"], "Apellido": ["APELLIDO"], "Sector": ["SECTOR"],
        "Puesto": ["PUESTO"], "Nomina": ["NOMINA"], "Jornada": ["JORNADA"]
    }.items():
        for c in cands:
            if _norm(c) in mapa:
                ren[mapa[_norm(c)]] = dest
                break
    df = df.rename(columns=ren)
    for c in cols[:-1]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str).str.strip()
    puesto = df["Puesto"].map(_norm)
    nom = df["Nomina"].map(_norm)
    df["RolOperativo"] = "Otro"
    df.loc[puesto.eq("CONTROL") & nom.eq("MDO"), "RolOperativo"] = "Control fijo"
    df.loc[puesto.eq("PREPARACION LOZA") & nom.eq("MDO"), "RolOperativo"] = "Loza independiente"
    df.loc[nom.eq("EVENTUAL"), "RolOperativo"] = "Refuerzo eventual"
    return df[cols].reset_index(drop=True)


def dotacion_control(df_personal):
    p = preparar_maestro_personal(df_personal)
    return {
        "control_fijo": int((p.RolOperativo == "Control fijo").sum()),
        "loza": int((p.RolOperativo == "Loza independiente").sum()),
        "eventuales": int((p.RolOperativo == "Refuerzo eventual").sum()),
        "personal": p,
    }


def capacidad_para_dotacion(personas):
    personas = max(int(personas or 0), 0)
    if personas <= 0:
        return {"lineas": 0, "unidades": 0}
    if personas in CAPACIDAD_CONTROL:
        return CAPACIDAD_CONTROL[personas].copy()
    return {
        "lineas": int(round(923 + (personas - 5) * OBJETIVO_LINEAS_PERSONA)),
        "unidades": int(round(5373 + (personas - 5) * OBJETIVO_UNIDADES_PERSONA)),
    }


def _es_easy_row(row):
    """EASY sólo cuando el pedido está planificado/agrupado como EASY.

    Ser cliente CENCOSUD no alcanza: si el pedido está en LUNES/MARTES/etc.,
    debe ocupar la zona normal de entrega.
    """
    plan = _norm(row.get("Planificacion", ""))
    despacho = _norm(row.get("DespachoDescripcion", ""))
    # Si ya existe un agrupador EASY con fecha (p.ej. EASY 02-10), manda el agrupador:
    # deja de pertenecer a la zona genérica y pasa al compromiso EASY fechado.
    if "EASY" in despacho:
        return True
    if plan == "EASY" or plan.startswith("EASY "):
        return True
    return False


def _tipo_flexible(row):
    txt = " | ".join(_norm(row.get(c, "")) for c in [
        "Planificacion", "FrecuenciaPreparacion", "FrecuenciaEntrega", "ZonaExpreso"
    ])
    if "EXPRES" in txt:
        return "EXPRESOS"
    if "DIARI" in txt:
        return "DIARIOS"
    return ""


def _es_full_loza(s):
    return s.fillna("").astype(str).map(_norm).str.contains(
        r"SANITAR|LOZA|BANERA|PISO DUCHA", regex=True, na=False
    )


def _preparar_pedidos(pedidos, detalle, transmisiones=None):
    pedidos = pedidos.copy() if pedidos is not None else pd.DataFrame()
    detalle = detalle.copy() if detalle is not None else pd.DataFrame()
    if pedidos.empty:
        return pedidos, detalle

    for c in ["Pedido", "Planificacion", "FrecuenciaPreparacion", "FrecuenciaEntrega", "ZonaExpreso",
              "ClienteDescripcion", "ClienteCodigo", "CodigoDespacho", "DespachoDescripcion"]:
        if c not in pedidos.columns:
            pedidos[c] = ""
        pedidos[c] = pedidos[c].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)

    for c in ["TotalUnidades", "TotalSKUs", "TotalM3"]:
        if c not in pedidos.columns:
            pedidos[c] = 0
        pedidos[c] = pd.to_numeric(pedidos[c], errors="coerce").fillna(0)

    # La antigüedad operativa se mide SIEMPRE desde la última transmisión al WMS/DIGIP.
    # La fecha de creación/compra se conserva sólo como dato de auditoría.
    if "Fecha" in pedidos.columns:
        pedidos["FechaCreacion"] = pd.to_datetime(pedidos["Fecha"], errors="coerce", dayfirst=True)
    else:
        pedidos["FechaCreacion"] = pd.NaT

    # `datos_dashboard` ya puede venir enriquecido con FechaTransmisionERP desde principal.py.
    # Si además recibimos la tabla de transmisiones, NO hacemos un merge con el mismo nombre
    # (eso generaría FechaTransmisionERP_x/_y y provocaría KeyError). Se usa una columna
    # temporal y se prioriza la fecha de la fuente de transmisiones cuando está disponible.
    if "FechaTransmisionERP" in pedidos.columns:
        pedidos["FechaTransmisionERP"] = pd.to_datetime(
            pedidos["FechaTransmisionERP"], errors="coerce", dayfirst=True
        )
    else:
        pedidos["FechaTransmisionERP"] = pd.NaT

    tx = transmisiones.copy() if transmisiones is not None else pd.DataFrame()
    if not tx.empty and "Pedido" in tx.columns and "FechaTransmisionERP" in tx.columns:
        tx["Pedido"] = (
            tx["Pedido"].fillna("").astype(str).str.strip()
            .str.replace(r"\.0$", "", regex=True).str.split("-").str[0]
        )
        tx["FechaTransmisionERP"] = pd.to_datetime(
            tx["FechaTransmisionERP"], errors="coerce", dayfirst=True
        )
        tx = (
            tx[["Pedido", "FechaTransmisionERP"]]
            .sort_values("FechaTransmisionERP", ascending=False, na_position="last")
            .drop_duplicates("Pedido", keep="first")
            .rename(columns={"FechaTransmisionERP": "FechaTransmisionERP_TX"})
        )
        pedidos = pedidos.merge(tx, on="Pedido", how="left")
        pedidos["FechaTransmisionERP"] = (
            pedidos["FechaTransmisionERP_TX"]
            .combine_first(pedidos["FechaTransmisionERP"])
        )
        pedidos = pedidos.drop(columns=["FechaTransmisionERP_TX"], errors="ignore")

    pedidos["FechaTransmisionERP"] = pd.to_datetime(
        pedidos["FechaTransmisionERP"], errors="coerce", dayfirst=True
    )
    # Compatibilidad con el resto del motor: `Fecha` pasa a significar fecha operativa WMS.
    # No se usa FechaCreacion como fallback: si falta transmisión, la antigüedad queda sin dato.
    pedidos["Fecha"] = pedidos["FechaTransmisionERP"]

    if not detalle.empty and "Pedido" in detalle.columns:
        detalle["Pedido"] = detalle["Pedido"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        if "ArticuloCodigo" in detalle.columns:
            lin = detalle.groupby("Pedido")["ArticuloCodigo"].nunique().rename("LineasDetalle")
            pedidos = pedidos.merge(lin, on="Pedido", how="left")
            pedidos["Lineas"] = pedidos["LineasDetalle"].fillna(pedidos["TotalSKUs"]).astype(int)
        else:
            pedidos["Lineas"] = pedidos["TotalSKUs"].astype(int)
    else:
        pedidos["Lineas"] = pedidos["TotalSKUs"].astype(int)

    pedidos["EsEasy"] = pedidos.apply(_es_easy_row, axis=1)
    pedidos["TipoFlexible"] = pedidos.apply(_tipo_flexible, axis=1)
    pedidos["Entrega"] = pedidos["FrecuenciaEntrega"].map(_norm)
    pedidos["Preparacion"] = pedidos["FrecuenciaPreparacion"].map(_norm)
    return pedidos, detalle


def _resumen(df, nombre, total_lineas_ref=0, hoy=None):
    if df is None or df.empty:
        return {
            "Tipo": nombre, "Pedidos": 0, "Líneas": 0, "Unidades": 0, "Unid./línea": 0.0,
            "m³": 0.0, "m³/línea": 0.0, "Camionetas 8m³": 0.0, "% líneas": 0.0,
            "Antig. prom.": 0.0, "Antig. máx.": 0,
        }
    lineas = float(df["Lineas"].sum())
    unidades = float(df["TotalUnidades"].sum())
    m3 = float(df["TotalM3"].sum())
    antig_prom = antig_max = 0
    if hoy is not None and "Fecha" in df.columns:
        edades = (pd.Timestamp(hoy) - pd.to_datetime(df["Fecha"], errors="coerce")).dt.days.clip(lower=0).dropna()
        if not edades.empty:
            antig_prom = float(edades.mean())
            antig_max = int(edades.max())
    return {
        "Tipo": nombre,
        "Pedidos": int(df["Pedido"].nunique()),
        "Líneas": int(round(lineas)),
        "Unidades": int(round(unidades)),
        "Unid./línea": round(unidades / lineas, 1) if lineas else 0.0,
        "m³": round(m3, 2),
        "m³/línea": round(m3 / lineas, 3) if lineas else 0.0,
        "Camionetas 8m³": round(m3 / M3_CAMIONETA, 2) if m3 else 0.0,
        "% líneas": round(lineas / total_lineas_ref * 100, 1) if total_lineas_ref else 0.0,
        "Antig. prom.": round(antig_prom, 1),
        "Antig. máx.": antig_max,
    }


def _detalle_full_loza_calificado(detalle):
    """Devuelve sólo artículos sanitarios de pedidos que califican como Full Loza.

    Regla V5.2:
    - INO: 6 unidades = 1 pallet; INO...-2 no condiciona la regla.
    - BID: 10 unidades = 1 pallet.
    - Full Loza si INO/BID superan 6 pallets equivalentes por pedido.
    - PDU: el pedido también califica si suma al menos 10 unidades.
    - PDU120 es repuesto: no condiciona la regla ni se incluye en el detalle Full Loza.
    El detalle devuelto contiene únicamente INO/BID/PDU, nunca otras familias.
    """
    if detalle is None or detalle.empty or "Pedido" not in detalle.columns:
        return pd.DataFrame(), set()
    d = detalle.copy()
    art_col = next((c for c in ["ArticuloCodigo", "CodigoArticulo", "Articulo", "Código", "Codigo"] if c in d.columns), None)
    if art_col is None:
        return pd.DataFrame(), set()
    d["_art"] = d[art_col].fillna("").astype(str).str.strip().str.upper()
    cant_col = next((c for c in ["Cantidad", "Unidades", "TotalUnidades"] if c in d.columns), None)
    d["_cant"] = pd.to_numeric(d[cant_col], errors="coerce").fillna(0) if cant_col else 0.0
    es_ino = d["_art"].str.startswith("INO")
    es_mochila = es_ino & d["_art"].str.endswith("-2")
    es_bid = d["_art"].str.startswith("BID")
    es_pdu = d["_art"].str.startswith("PDU")
    es_pdu120 = d["_art"].eq("PDU120")
    es_pdu_valido = es_pdu & ~es_pdu120
    sanit = d[es_ino | es_bid | es_pdu_valido].copy()
    if sanit.empty:
        return sanit, set()
    base = d.copy()
    base["_pallet_eq"] = 0.0
    base.loc[es_ino & ~es_mochila, "_pallet_eq"] = base.loc[es_ino & ~es_mochila, "_cant"] / 6.0
    base.loc[es_bid, "_pallet_eq"] = base.loc[es_bid, "_cant"] / 10.0
    pallets = base.groupby("Pedido")["_pallet_eq"].sum()
    pdu = base.loc[es_pdu_valido].groupby("Pedido")["_cant"].sum()
    ids = set(pallets[pallets > 6.0].index.astype(str)) | set(pdu[pdu >= 10.0].index.astype(str))
    sanit["Pedido"] = sanit["Pedido"].astype(str)
    sanit = sanit[sanit["Pedido"].isin(ids)].drop(columns=["_art", "_cant"], errors="ignore")
    return sanit, ids


def _resumen_sanitarios(pedidos, detalle, total_lineas_ref):
    dl, ids = _detalle_full_loza_calificado(detalle)
    if dl.empty or not ids:
        return pd.DataFrame([_resumen(pd.DataFrame(), "SANITARIOS", total_lineas_ref)])
    if "ArticuloCodigo" in dl.columns:
        lin = dl.groupby("Pedido")["ArticuloCodigo"].nunique().rename("LineasSan")
    else:
        lin = dl.groupby("Pedido").size().rename("LineasSan")
    cant_col = next((c for c in ["Cantidad", "Unidades", "TotalUnidades"] if c in dl.columns), None)
    uni = (pd.to_numeric(dl[cant_col], errors="coerce").fillna(0).groupby(dl["Pedido"]).sum().rename("UnidadesSan")
           if cant_col else pd.Series(dtype=float, name="UnidadesSan"))
    if "VolumenLineaM3" in dl.columns:
        vol = pd.to_numeric(dl["VolumenLineaM3"], errors="coerce").fillna(0).groupby(dl["Pedido"]).sum().rename("M3San")
    else:
        vol = pd.Series(dtype=float, name="M3San")
    san = pd.concat([lin, uni, vol], axis=1).fillna(0).reset_index()
    san = san.merge(pedidos[["Pedido"]].drop_duplicates(), on="Pedido", how="inner")
    lineas = float(san["LineasSan"].sum()); unidades = float(san["UnidadesSan"].sum()); m3 = float(san.get("M3San", pd.Series(dtype=float)).sum())
    row = {
        "Tipo": "SANITARIOS / FULL LOZA", "Pedidos": int(san["Pedido"].nunique()), "Líneas": int(lineas),
        "Unidades": int(unidades), "Unid./línea": round(unidades/lineas,1) if lineas else 0.0,
        "m³": round(m3,2), "m³/línea": round(m3/lineas,3) if lineas else 0.0,
        "Camionetas 8m³": round(m3/M3_CAMIONETA,2) if m3 else 0.0,
        "% líneas": round(lineas/total_lineas_ref*100,1) if total_lineas_ref else 0.0,
    }
    return pd.DataFrame([row])

def _resumen_pedidos_export(df, categoria="", subcategoria=""):
    if df is None or df.empty:
        return pd.DataFrame(columns=["Categoria", "Subcategoria", "Pedido", "ClienteCodigo", "ClienteDescripcion", "Planificacion", "FrecuenciaEntrega", "FrecuenciaPreparacion", "Lineas", "Unidades", "m3", "UnidLinea", "Camionetas8m3", "Fecha"])
    x = df.copy()
    x.insert(0, "Categoria", categoria)
    x.insert(1, "Subcategoria", subcategoria)
    out = pd.DataFrame({
        "Categoria": x["Categoria"],
        "Subcategoria": x["Subcategoria"],
        "Pedido": x.get("Pedido", ""),
        "ClienteCodigo": x.get("ClienteCodigo", ""),
        "ClienteDescripcion": x.get("ClienteDescripcion", ""),
        "Planificacion": x.get("Planificacion", ""),
        "FrecuenciaEntrega": x.get("FrecuenciaEntrega", ""),
        "FrecuenciaPreparacion": x.get("FrecuenciaPreparacion", ""),
        "Lineas": pd.to_numeric(x.get("Lineas", 0), errors="coerce").fillna(0),
        "Unidades": pd.to_numeric(x.get("TotalUnidades", 0), errors="coerce").fillna(0),
        "m3": pd.to_numeric(x.get("TotalM3", 0), errors="coerce").fillna(0),
        "Fecha": x.get("Fecha", pd.NaT),
    })
    out["UnidLinea"] = (out["Unidades"] / out["Lineas"].replace(0, pd.NA)).fillna(0).round(2)
    out["Camionetas8m3"] = (out["m3"] / M3_CAMIONETA).round(2)
    return out


def _detalle_export(detalle, pedidos_sel, categoria="", subcategoria="", solo_sanitarios=False):
    if detalle is None or detalle.empty or pedidos_sel is None or pedidos_sel.empty or "Pedido" not in detalle.columns:
        return pd.DataFrame()
    ids = set(pedidos_sel["Pedido"].astype(str))
    d = detalle[detalle["Pedido"].astype(str).isin(ids)].copy()
    if solo_sanitarios and not d.empty:
        dim = "Familia2" if "Familia2" in d.columns else ("Sectorizacion" if "Sectorizacion" in d.columns else None)
        if dim:
            d = d[_es_full_loza(d[dim])].copy()
    if d.empty:
        return d
    d.insert(0, "Categoria", categoria)
    d.insert(1, "Subcategoria", subcategoria)
    # Adjuntar datos de cabecera útiles sin pisar columnas existentes.
    cab_cols = [c for c in ["Pedido", "ClienteCodigo", "ClienteDescripcion", "Planificacion", "FrecuenciaEntrega", "FrecuenciaPreparacion"] if c in pedidos_sel.columns]
    cab = pedidos_sel[cab_cols].drop_duplicates("Pedido") if "Pedido" in cab_cols else pd.DataFrame()
    if not cab.empty:
        extras = [c for c in cab.columns if c == "Pedido" or c not in d.columns]
        d = d.merge(cab[extras], on="Pedido", how="left")
    return d


def construir_inteligencia_operativa(pedidos, detalle, personal=None, transmisiones=None, hoy=None, easy_activo=True, coordinaciones=None):
    hoy = hoy or date.today()
    pedidos, detalle = _preparar_pedidos(pedidos, detalle, transmisiones=transmisiones)
    if pedidos.empty:
        return {"vacio": True, "mensaje": "No hay pedidos activos para analizar."}

    dot = dotacion_control(personal)
    personas = dot["control_fijo"] or 3
    cap = capacidad_para_dotacion(personas)
    total_lineas = int(pedidos["Lineas"].sum())

    # EASY se dimensiona siempre en su bloque. ON/OFF sólo decide si participa de la lectura general.
    easy = pedidos[pedidos["EsEasy"]].copy()
    base = pedidos.copy() if easy_activo else pedidos[~pedidos["EsEasy"]].copy()

    # Las zonas semanales excluyen flexibles y EASY para evitar doble conteo.
    zonas_base = base[(base["TipoFlexible"] == "") & (~base["EsEasy"])].copy()
    filas_zona = []
    dia_hoy = DIAS_HABILES[hoy.weekday()] if hoy.weekday() < 5 else ""
    for entrega in DIAS_HABILES:
        z = zonas_base[zonas_base["Entrega"].eq(entrega)]
        r = _resumen(z, entrega.title(), max(int(zonas_base["Lineas"].sum()), 1), hoy=hoy)
        prep = PREPARACION_POR_ENTREGA[entrega]
        r["Preparación"] = prep.title()
        r["HOY"] = "🎯 HOY" if prep == dia_hoy else ""
        filas_zona.append(r)
    zonas = pd.DataFrame(filas_zona)[[
        "HOY", "Tipo", "Preparación", "Pedidos", "Líneas", "Unidades", "Unid./línea",
        "m³", "m³/línea", "Camionetas 8m³", "% líneas"
    ]]

    # Expresos y Diarios son el pulmón operativo y se muestran por separado.
    flex_rows = []
    for tipo in ["EXPRESOS", "DIARIOS"]:
        f = base[base["TipoFlexible"].eq(tipo)]
        flex_rows.append(_resumen(f, tipo.title(), max(int(base["Lineas"].sum()), 1), hoy=hoy))
    flexibles = pd.DataFrame(flex_rows)[[
        "Tipo", "Pedidos", "Líneas", "Unidades", "Unid./línea", "m³", "m³/línea",
        "Camionetas 8m³", "% líneas", "Antig. prom.", "Antig. máx."
    ]]

    sanitarios = _resumen_sanitarios(base, detalle, max(int(base["Lineas"].sum()), 1))
    easy_df = pd.DataFrame([_resumen(easy, "EASY / CENCOSUD", max(total_lineas, 1), hoy=hoy)])[[
        "Tipo", "Pedidos", "Líneas", "Unidades", "Unid./línea", "m³", "m³/línea",
        "Camionetas 8m³", "% líneas", "Antig. prom.", "Antig. máx."
    ]]

    # Lectura simple del día: asegurar zona de hoy, luego EXPRESOS, luego DIARIOS.
    hoy_row = zonas[zonas["HOY"].ne("")]
    lineas_hoy = int(hoy_row["Líneas"].sum()) if not hoy_row.empty else 0
    margen = cap["lineas"] - lineas_hoy
    exp_lineas = int(flexibles.loc[flexibles["Tipo"].eq("Expresos"), "Líneas"].sum())
    diarios_lineas = int(flexibles.loc[flexibles["Tipo"].eq("Diarios"), "Líneas"].sum())
    if margen <= 0:
        accion = f"La zona de HOY consume/supera la capacidad base en {abs(margen)} líneas. Priorizar la zona objetivo y evaluar refuerzo de Control."
    elif exp_lineas > 0:
        tomar = min(margen, exp_lineas)
        accion = f"Asegurar la zona de HOY ({lineas_hoy} líneas) y usar hasta {tomar} líneas de margen en EXPRESOS, priorizando antigüedad."
    elif diarios_lineas > 0:
        tomar = min(margen, diarios_lineas)
        accion = f"Asegurar la zona de HOY y usar hasta {tomar} líneas de margen en DIARIOS."
    else:
        accion = "La zona de HOY entra en capacidad y no hay carga flexible prioritaria. Queda margen para evaluar adelanto de otra zona."

    # Bases descargables: resumen por pedido + detalle de artículos.
    zonas_resumen_parts, zonas_detalle_parts = [], []
    for entrega in DIAS_HABILES:
        z = zonas_base[zonas_base["Entrega"].eq(entrega)].copy()
        zonas_resumen_parts.append(_resumen_pedidos_export(z, "ZONAS", entrega))
        zonas_detalle_parts.append(_detalle_export(detalle, z, "ZONAS", entrega))
    exp = base[base["TipoFlexible"].eq("EXPRESOS")].copy()
    dia = base[base["TipoFlexible"].eq("DIARIOS")].copy()
    flex_resumen = pd.concat([_resumen_pedidos_export(exp, "FLEXIBLES", "EXPRESOS"), _resumen_pedidos_export(dia, "FLEXIBLES", "DIARIOS")], ignore_index=True)
    flex_detalle = pd.concat([_detalle_export(detalle, exp, "FLEXIBLES", "EXPRESOS"), _detalle_export(detalle, dia, "FLEXIBLES", "DIARIOS")], ignore_index=True)
    san_detalle_calificado, san_ids = _detalle_full_loza_calificado(detalle)
    san_ped = base[base["Pedido"].astype(str).isin(san_ids)].copy()
    exports = {
        "zonas_resumen": pd.concat(zonas_resumen_parts, ignore_index=True),
        "zonas_detalle": pd.concat(zonas_detalle_parts, ignore_index=True),
        "flex_resumen": flex_resumen,
        "flex_detalle": flex_detalle,
        "sanitarios_resumen": _resumen_pedidos_export(san_ped, "SANITARIOS", "FULL LOZA"),
        "sanitarios_detalle": _detalle_export(san_detalle_calificado, san_ped, "SANITARIOS", "FULL LOZA", solo_sanitarios=False),
        "easy_resumen": _resumen_pedidos_export(easy, "EASY", "EASY / CENCOSUD"),
        "easy_detalle": _detalle_export(detalle, easy, "EASY", "EASY / CENCOSUD"),
    }

    simulador = construir_pool_simulador(pedidos, hoy=hoy, easy_activo=easy_activo)
    calendario_semanal = construir_calendario_semanal(pedidos, detalle=detalle, hoy=hoy, coordinaciones=coordinaciones) if "construir_calendario_semanal" in globals() else {}

    return {
        "vacio": False, "dotacion": dot, "personas_control": personas,
        "capacidad_lineas": cap["lineas"], "capacidad_unidades": cap["unidades"],
        "carga_lineas": total_lineas, "carga_unidades": int(pedidos["TotalUnidades"].sum()),
        "carga_m3": float(pedidos["TotalM3"].sum()), "dias_pendientes": round(total_lineas / OBJETIVO_CONTROL_DIARIO, 2) if OBJETIVO_CONTROL_DIARIO else 0, "zonas": zonas, "flexibles": flexibles,
        "sanitarios": sanitarios, "easy": easy_df, "easy_activo": easy_activo,
        "lineas_hoy": lineas_hoy, "margen_hoy": margen, "accion": accion,
        "exports": exports, "simulador": simulador, "calendario_semanal": calendario_semanal,
    }


def construir_pool_simulador(pedidos_preparados: pd.DataFrame, hoy=None, easy_activo=True):
    """Construye el universo operativo del simulador.

    Reglas de estado:
    - Estado=PENDIENTE: cartera todavía libre/no iniciada.
    - Estado=PREPARACION + PreparacionEstado=PENDIENTE: carga ya agrupada y
      comprometida, pero todavía no iniciada. Se cuenta en el planning, pero
      NO vuelve a proponerse en una camioneta simulada.
    - PreparacionEstado=ENPROCESO: queda fuera del simulador porque ya arrancó.

    EXPRESOS respeta config_planificacion. Además, si un cliente tiene al menos
    un pedido ya comprometido, sus pedidos libres no se vuelven a sugerir para
    evitar partir al cliente entre una agrupación real y otra simulada.
    """
    hoy = hoy or date.today()
    p = pedidos_preparados.copy()
    if p.empty:
        return {"obligatorio": pd.DataFrame(), "comprometido": pd.DataFrame(),
                "base_planning": pd.DataFrame(), "pools": {}, "expresos_grupos": pd.DataFrame(),
                "comprometidos_resumen": pd.DataFrame()}

    # ------------------------------------------------------
    # ESTADO OPERATIVO REAL DIGIP
    # ------------------------------------------------------
    estado = p.get("Estado", pd.Series("PENDIENTE", index=p.index)).fillna("").astype(str).map(_norm)
    est_prep = p.get("PreparacionEstado", pd.Series("", index=p.index)).fillna("").astype(str).map(_norm)
    prep_id = p.get("PreparacionID", pd.Series("", index=p.index)).fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    despacho = p.get("DespachoDescripcion", pd.Series("", index=p.index)).fillna("").astype(str).str.strip()

    mascara_en_curso = est_prep.eq("ENPROCESO")
    mascara_comprometido = estado.eq("PREPARACION") & est_prep.eq("PENDIENTE") & ~mascara_en_curso
    mascara_libre = estado.eq("PENDIENTE") & ~mascara_en_curso

    comprometido = p[mascara_comprometido].copy()
    libre = p[mascara_libre].copy()

    # Metadatos visibles de la agrupación real.
    if not comprometido.empty:
        comprometido["AgrupadorReal"] = despacho.loc[comprometido.index].values
        comprometido["PreparacionIDReal"] = prep_id.loc[comprometido.index].values

    # Si un cliente ya tiene algo comprometido, no sugerimos sus pedidos libres:
    # el cliente debe resolverse completo y no partirse entre real/simulado.
    clientes_comprometidos = set(
        comprometido.get("ClienteCodigo", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    ) - {""}
    if clientes_comprometidos and not libre.empty:
        libre = libre[~libre["ClienteCodigo"].fillna("").astype(str).str.strip().isin(clientes_comprometidos)].copy()

    dia_hoy = DIAS_HABILES[hoy.weekday()] if hoy.weekday() < 5 else ""
    entrega_objetivo = next((e for e, prep in PREPARACION_POR_ENTREGA.items() if prep == dia_hoy), "")

    # La zona obligatoria puede contener pedidos libres o ya agrupados pendientes,
    # pero nunca pedidos EnProceso.
    elegibles = pd.concat([libre, comprometido], ignore_index=True).drop_duplicates(subset=["Pedido"], keep="first")
    obligatorio = elegibles[(elegibles["TipoFlexible"] == "") & (~elegibles["EsEasy"]) & elegibles["Entrega"].eq(entrega_objetivo)].copy()

    # Base física del planning = zona obligatoria + TODO lo ya agrupado/no iniciado.
    # Se deduplica Pedido para no contar dos veces una preparación de la zona del día.
    base_planning = obligatorio.drop_duplicates(subset=["Pedido"], keep="first").copy()

    def agrupar_clientes(df: pd.DataFrame, canal: str, respetar_expreso: bool = False) -> pd.DataFrame:
        columnas = ["Canal", "PlanificacionGrupo", "GrupoDespacho", "ZonaExpreso", "ClaveAgrupacion",
                    "ClienteCodigo", "ClienteDescripcion", "Pedidos", "CantidadPedidos",
                    "PedidoMasAntiguo", "PedidoMasReciente", "AntiguedadMax", "Lineas", "Unidades", "m3"]
        if df is None or df.empty:
            return pd.DataFrame(columns=columnas)
        x = df.copy()
        x["Fecha"] = pd.to_datetime(x["Fecha"], errors="coerce")
        x["FechaOrden"] = x["Fecha"].fillna(pd.Timestamp(hoy))
        x["ClienteCodigo"] = x["ClienteCodigo"].fillna("").astype(str).str.strip()
        x["ClienteDescripcion"] = x["ClienteDescripcion"].fillna("").astype(str).str.strip()
        x["ClaveCliente"] = x["ClienteCodigo"].where(x["ClienteCodigo"].ne(""), x["ClienteDescripcion"])

        if respetar_expreso:
            def cfg(z):
                try:
                    return obtener_planificacion_expreso(z)
                except Exception:
                    return {"ZonaExpresoNormalizada": _norm(z), "PlanificacionExpreso": "", "GrupoExpreso": "", "ZonaExpresoConfigurada": False}
            conf = x["ZonaExpreso"].fillna("").apply(cfg).apply(pd.Series)
            x["ZonaExpreso"] = conf.get("ZonaExpresoNormalizada", x["ZonaExpreso"]).fillna("").astype(str).str.strip().str.upper()
            x["PlanificacionGrupo"] = conf.get("PlanificacionExpreso", "").fillna("").astype(str).str.strip().str.upper()
            x["GrupoDespacho"] = conf.get("GrupoExpreso", "").fillna("").astype(str).str.strip()
            configurada = conf.get("ZonaExpresoConfigurada", False)
            if not isinstance(configurada, pd.Series):
                configurada = pd.Series(False, index=x.index)
            x.loc[~configurada.astype(bool), "GrupoDespacho"] = "SIN CONFIG"
            x.loc[x["PlanificacionGrupo"].eq(""), "PlanificacionGrupo"] = "EXPRESOS"
            x["ClaveAgrupacion"] = x["PlanificacionGrupo"] + " | Grupo " + x["GrupoDespacho"] + " | " + x["ZonaExpreso"]
        else:
            x["PlanificacionGrupo"] = canal
            x["GrupoDespacho"] = "1"
            x["ZonaExpreso"] = ""
            x["ClaveAgrupacion"] = canal

        keys = ["PlanificacionGrupo", "GrupoDespacho", "ZonaExpreso", "ClaveAgrupacion", "ClaveCliente"]
        g = (x.groupby(keys, as_index=False, dropna=False)
             .agg(ClienteCodigo=("ClienteCodigo", "first"), ClienteDescripcion=("ClienteDescripcion", "first"),
                  CantidadPedidos=("Pedido", "nunique"), Pedidos=("Pedido", lambda q: " | ".join(sorted(set(q.astype(str))))),
                  PedidoMasAntiguo=("FechaOrden", "min"), PedidoMasReciente=("FechaOrden", "max"),
                  Lineas=("Lineas", "sum"), Unidades=("TotalUnidades", "sum"), m3=("TotalM3", "sum")))
        g["Canal"] = canal
        g["AntiguedadMax"] = (pd.Timestamp(hoy) - g["PedidoMasAntiguo"].dt.normalize()).dt.days.clip(lower=0)
        g["Lineas"] = pd.to_numeric(g["Lineas"], errors="coerce").fillna(0).round().astype(int)
        g["Unidades"] = pd.to_numeric(g["Unidades"], errors="coerce").fillna(0).round().astype(int)
        g["m3"] = pd.to_numeric(g["m3"], errors="coerce").fillna(0).round(3)
        g = g.sort_values(["PlanificacionGrupo", "GrupoDespacho", "PedidoMasAntiguo", "m3"], ascending=[True, True, True, False]).reset_index(drop=True)
        return g[columnas]

    def mascara_retira_de(df):
        cols_retira = [c for c in ["Planificacion", "FrecuenciaEntrega", "FrecuenciaPreparacion",
                                    "DespachoDescripcion", "TipoEntrega", "TipoPreparacion"] if c in df.columns]
        if not cols_retira:
            return pd.Series(False, index=df.index, dtype=bool)
        texto = pd.Series("", index=df.index, dtype="object")
        for c in cols_retira:
            texto = texto + " " + df[c].fillna("").astype(str).map(_norm)
        return texto.str.contains("RETIRA", na=False)

    mascara_retira = mascara_retira_de(libre)

    # Pools de simulación = SOLAMENTE pedidos todavía libres.
    exp_raw = libre[libre["TipoFlexible"].eq("EXPRESOS") & ~mascara_retira].copy()
    exp = agrupar_clientes(exp_raw, "EXPRESOS", True)
    if not exp.empty:
        exp = exp[exp["ZonaExpreso"].isin({"CABA SUR", "CABA SUR II", "CABA NORTE"})].copy()

    retira = agrupar_clientes(libre[mascara_retira].copy(), "RETIRA", False)
    dia = agrupar_clientes(libre[libre["TipoFlexible"].eq("DIARIOS") & ~mascara_retira], "DIARIOS", False)
    easy = agrupar_clientes(libre[libre["EsEasy"] & ~mascara_retira], "EASY", False) if easy_activo else pd.DataFrame()

    if not exp.empty:
        grupos = (exp.groupby(["PlanificacionGrupo", "GrupoDespacho", "ZonaExpreso", "ClaveAgrupacion"], as_index=False)
                  .agg(Clientes=("ClienteCodigo", "nunique"), Pedidos=("CantidadPedidos", "sum"),
                       Lineas=("Lineas", "sum"), Unidades=("Unidades", "sum"), m3=("m3", "sum"), AntiguedadMax=("AntiguedadMax", "max")))
    else:
        grupos = pd.DataFrame()

    # Resumen de cargas reales ya agrupadas y todavía no iniciadas.
    if not comprometido.empty:
        cr = comprometido.copy()
        cr["AgrupadorReal"] = cr.get("AgrupadorReal", "").fillna("").astype(str).str.strip().replace("", "SIN AGRUPADOR")
        comprometidos_resumen = (cr.groupby("AgrupadorReal", as_index=False)
            .agg(Pedidos=("Pedido", "nunique"), Clientes=("ClienteCodigo", "nunique"),
                 Líneas=("Lineas", "sum"), Unidades=("TotalUnidades", "sum"), m3=("TotalM3", "sum")))
        comprometidos_resumen["m3"] = pd.to_numeric(comprometidos_resumen["m3"], errors="coerce").fillna(0).round(2)
        comprometidos_resumen = comprometidos_resumen.sort_values(["m3", "Pedidos"], ascending=[False, False]).reset_index(drop=True)
    else:
        comprometidos_resumen = pd.DataFrame(columns=["AgrupadorReal", "Pedidos", "Clientes", "Líneas", "Unidades", "m3"])

    return {"obligatorio": obligatorio, "comprometido": comprometido, "base_planning": base_planning,
            "entrega_objetivo": entrega_objetivo, "dia_hoy": dia_hoy,
            "pools": {"EXPRESOS": exp, "RETIRA": retira, "DIARIOS": dia, "EASY": easy},
            "expresos_grupos": grupos, "comprometidos_resumen": comprometidos_resumen,
            "clientes_comprometidos": len(clientes_comprometidos), "tipos_vehiculos": TIPOS_VEHICULOS}

def simular_camionetas_clientes(pool: pd.DataFrame, cantidad_camionetas: int, referencia_m3: float = M3_CAMIONETA,
                                prefijo: str = "CAM SIM", filtro_clave: str | None = None,
                                numero_desde: int = 1, tipo_vehiculo: str = "Camioneta") -> pd.DataFrame:
    """Agrupa clientes completos sin mezclar ClaveAgrupacion.

    referencia_m3 es capacidad de referencia del vehículo (8 camioneta / 15 camión).
    Un cliente individual puede excederla y se mantiene completo.
    """
    if pool is None or pool.empty or cantidad_camionetas <= 0:
        return pd.DataFrame()
    pendientes = pool.copy()
    if filtro_clave is not None and "ClaveAgrupacion" in pendientes.columns:
        pendientes = pendientes[pendientes["ClaveAgrupacion"].astype(str).eq(str(filtro_clave))].copy()
    if pendientes.empty:
        return pd.DataFrame()
    pendientes = pendientes.sort_values(["PedidoMasAntiguo", "m3"], ascending=[True, False]).reset_index(drop=True)
    asignadas=[]; usados=set()
    for n in range(int(cantidad_camionetas)):
        nro=numero_desde+n; volumen=0.0; agrego=False
        # Best-fit simple por prioridad: recorre clientes del mismo grupo y completa hasta capacidad.
        for idx, row in pendientes.iterrows():
            if idx in usados: continue
            vol=float(row.get("m3",0) or 0)
            if agrego and volumen >= referencia_m3: break
            # Si entra, agregar. Si no entra pero el vehículo está vacío, cliente completo igual entra.
            if (volumen + vol <= referencia_m3) or not agrego:
                fila=row.to_dict(); fila["NumeroCamioneta"]=nro; fila["Camioneta"]=f"{prefijo} {nro}"
                fila["TipoVehiculo"]=tipo_vehiculo; fila["CapacidadVehiculoM3"]=referencia_m3
                asignadas.append(fila); usados.add(idx); volumen += vol; agrego=True
        if not agrego: break
    if not asignadas: return pd.DataFrame()
    out=pd.DataFrame(asignadas)
    tot=(out.groupby(["NumeroCamioneta","Camioneta","TipoVehiculo","CapacidadVehiculoM3"],as_index=False)
         .agg(VolumenCamioneta=("m3","sum"),ClientesCamioneta=("ClienteCodigo","nunique"),
              PedidosCamioneta=("CantidadPedidos","sum"),LineasCamioneta=("Lineas","sum"),UnidadesCamioneta=("Unidades","sum")))
    tot["OcupacionVehiculoPct"]=(tot["VolumenCamioneta"]/tot["CapacidadVehiculoM3"]*100).round(1)
    return out.merge(tot,on=["NumeroCamioneta","Camioneta","TipoVehiculo","CapacidadVehiculoM3"],how="left")


# ==========================================================
# V5 — CALENDARIO SEMANAL DE CAPACIDAD
# ==========================================================
OBJETIVO_CONTROL_DIARIO = 850
OBJETIVO_CONTROL_SABADO = round(OBJETIVO_CONTROL_DIARIO * 6 / 9)  # jornada 06:00–12:00 vs 06:00–15:00
DIAS_PLANNING = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"]


def _fecha_easy_desde_fila(row, hoy):
    """Obtiene la fecha de entrega EASY. Prioriza fecha explícita y luego nombre del agrupador."""
    for c in ["FechaEstimadaEntrega", "Fecha estimada de entrega", "FechaEntrega", "FechaEntregaProgramada"]:
        if c in row.index:
            f = pd.to_datetime(row.get(c), errors="coerce", dayfirst=True)
            if pd.notna(f):
                return f.normalize()
    import re
    txt = " | ".join(_texto(row.get(c, "")) for c in ["DespachoDescripcion", "Despacho", "Planificacion"])
    m = re.search(r"(?:EASY\s*)?(\d{1,2})[\-/](\d{1,2})(?:[\-/](\d{2,4}))?", txt, flags=re.I)
    if not m:
        return pd.NaT
    d, mo = int(m.group(1)), int(m.group(2))
    y = int(m.group(3)) if m.group(3) else pd.Timestamp(hoy).year
    if y < 100: y += 2000
    try:
        return pd.Timestamp(year=y, month=mo, day=d)
    except Exception:
        return pd.NaT


def _ventana_easy(fecha_entrega):
    """Dos jornadas operativas previas. Para lunes: viernes + sábado."""
    if pd.isna(fecha_entrega):
        return []
    f = pd.Timestamp(fecha_entrega).normalize()
    prev = []
    cursor = f - pd.Timedelta(days=1)
    while len(prev) < 2:
        # Domingo no es jornada de preparación; sábado sí.
        if cursor.weekday() != 6:
            prev.append(cursor)
        cursor -= pd.Timedelta(days=1)
    return sorted(prev)


def construir_calendario_semanal(pedidos_preparados: pd.DataFrame, detalle=None, hoy=None, coordinaciones=None):
    """Planning semanal operativo.

    - Zona ocupa su jornada fija.
    - EASY agrupado por fecha ocupa completo el PRIMER día de su ventana de 48 h; el segundo queda como respaldo.
    - RETIRA normal ocupa HOY automáticamente.
    - RETIRA Full Loza queda movible/asignable.
    - Expresos agrupados quedan asignables por el usuario.
    """
    hoy = pd.Timestamp(hoy or date.today()).normalize()
    inicio = hoy - pd.Timedelta(days=hoy.weekday())
    # Semana actual + próxima semana (lunes a sábado). Así los EASY con turno cercano
    # ya reservan capacidad aunque su preparación caiga en la semana siguiente.
    fechas = [inicio + pd.Timedelta(days=i) for i in range(13) if (inicio + pd.Timedelta(days=i)).weekday() != 6]
    cal = pd.DataFrame({"Fecha": fechas})
    # La vista operativa arranca HOY: los días ya transcurridos no aportan a la coordinación futura.
    cal = cal[cal["Fecha"] >= hoy].reset_index(drop=True)
    nombres = {0:"LUNES",1:"MARTES",2:"MIERCOLES",3:"JUEVES",4:"VIERNES",5:"SABADO"}
    cal["Día"] = cal["Fecha"].dt.weekday.map(nombres)
    cal["Semana"] = cal["Fecha"].map(lambda f: "ACTUAL" if pd.Timestamp(f) < inicio + pd.Timedelta(days=7) else "PRÓXIMA")
    entrega_por_prep = {prep: entrega for entrega, prep in PREPARACION_POR_ENTREGA.items()}
    cal["Entrega Zona"] = cal["Día"].map(entrega_por_prep).fillna("—")
    cal["Entregas EASY"] = "—"
    for c in ["Zona", "EASY", "Expresos", "RETIRA", "Prioritarios"]:
        cal[c] = 0.0
    # Segunda dimensión de carga: las líneas siguen gobernando el objetivo,
    # pero las unidades permiten detectar jornadas pesadas (especialmente EASY).
    for c in ["Zona Unid.", "EASY Unid.", "Expresos Unid.", "RETIRA Unid.", "Prioritarios Unid."]:
        cal[c] = 0.0

    p = pedidos_preparados.copy()
    if p.empty:
        cal["Total"] = 0; cal["Capacidad"] = cal["Día"].map(lambda d: OBJETIVO_CONTROL_SABADO if d == "SABADO" else OBJETIVO_CONTROL_DIARIO); cal["Margen"] = cal["Capacidad"]
        return {"calendario": cal, "expresos_agrupados": pd.DataFrame(), "retira_agrupados": pd.DataFrame(), "easy_agrupados": pd.DataFrame()}

    estado = p.get("Estado", pd.Series("PENDIENTE", index=p.index)).fillna("").astype(str).map(_norm)
    ep = p.get("PreparacionEstado", pd.Series("", index=p.index)).fillna("").astype(str).map(_norm)
    activos = p[(estado.isin(["PENDIENTE", "PREPARACION"])) & ~ep.eq("ENPROCESO")].copy()
    activos = activos.drop_duplicates("Pedido", keep="first")

    # EnProceso no forma parte de la cartera futura, pero SÍ consume capacidad HOY.
    # De esta forma la foto del día actual no pierde trabajo que ya fue iniciado.
    en_curso_hoy = p[(estado.isin(["PENDIENTE", "PREPARACION"])) & ep.eq("ENPROCESO")].copy()
    en_curso_hoy = en_curso_hoy.drop_duplicates("Pedido", keep="first")
    if not en_curso_hoy.empty and (cal["Fecha"].eq(hoy)).any():
        mask_hoy = cal["Fecha"].eq(hoy)
        for _, r in en_curso_hoy.iterrows():
            lineas = float(pd.to_numeric(pd.Series([r.get("Lineas", 0)]), errors="coerce").fillna(0).iloc[0])
            texto = " | ".join(_norm(r.get(c, "")) for c in ["Planificacion", "FrecuenciaEntrega", "FrecuenciaPreparacion", "DespachoDescripcion"])
            if bool(r.get("EsEasy", False)):
                col = "EASY"
            elif "RETIRA" in texto:
                col = "RETIRA"
            elif ("URGENTE" in texto) or ("DIARI" in texto):
                col = "Prioritarios"
            elif "EXPRES" in texto:
                col = "Expresos"
            else:
                col = "Zona"
            cal.loc[mask_hoy, col] += lineas
            unidades = float(pd.to_numeric(pd.Series([r.get("TotalUnidades", 0)]), errors="coerce").fillna(0).iloc[0])
            cal.loc[mask_hoy, f"{col} Unid."] += unidades

    # Identificar RETIRA y pedidos Full Loza para no mezclarlos con Zona.
    texto_act = activos.apply(lambda r: " | ".join(_norm(r.get(c,"")) for c in ["Planificacion","FrecuenciaEntrega","FrecuenciaPreparacion","DespachoDescripcion"]), axis=1)
    mask_retira = texto_act.str.contains("RETIRA", na=False)
    # Carga prioritaria diaria: DIARIOS + URGENTE + URGENTES 2.
    # Se resuelve HOY, igual que RETIRA normal, y no debe contaminar Zona ni proyectarse a fechas futuras.
    mask_prioritarios = texto_act.str.contains(r"DIARI|URGENTE", regex=True, na=False) & ~mask_retira & ~activos["EsEasy"]
    _, ids_full_loza = _detalle_full_loza_calificado(detalle if detalle is not None else pd.DataFrame())
    ids_full_loza = {str(x) for x in ids_full_loza}
    mask_loza = activos["Pedido"].astype(str).isin(ids_full_loza)

    # ZONAS NORMALES — asignación por FECHA CONCRETA, no sólo por nombre de día.
    #
    # Regla operativa:
    # - cada pedido de Zona aparece UNA sola vez en el horizonte;
    # - se asigna a la primera jornada de preparación que le corresponde;
    # - el corte de la jornada es 10:00. Si un pedido se transmite después de las
    #   10:00 del propio día de preparación, pasa al siguiente ciclo semanal;
    # - una fecha futura del mismo día NO vuelve a repetir la cartera que ya fue
    #   asignada al ciclo más cercano.
    #
    # Ejemplo: si hoy es jueves y mañana viernes prepara MARTES, toda la cartera
    # MARTES disponible ahora queda en mañana. El viernes de la semana próxima
    # queda vacío; sólo se llenará con pedidos cuya transmisión ya no alcance el
    # corte de mañana.
    zona = activos[(activos["TipoFlexible"] == "") & (~activos["EsEasy"]) & (~mask_retira) & (~mask_prioritarios)].copy()

    CORTE_ZONA_HORA = 10

    def _fecha_preparacion_zona(row):
        entrega = _norm(row.get("Entrega", ""))
        prep = PREPARACION_POR_ENTREGA.get(entrega, "")
        if not prep:
            return pd.NaT

        # Fechas visibles del calendario que corresponden a esta preparación.
        candidatas = cal.loc[cal["Día"].eq(prep), "Fecha"].sort_values().tolist()
        if not candidatas:
            return pd.NaT

        tx = pd.to_datetime(row.get("FechaTransmisionERP", row.get("Fecha", pd.NaT)), errors="coerce", dayfirst=True)

        for f in candidatas:
            f = pd.Timestamp(f).normalize()
            corte = f + pd.Timedelta(hours=CORTE_ZONA_HORA)

            # Sin fecha de transmisión: por seguridad operativa se toma el ciclo
            # más cercano disponible, pero nunca se duplica en el siguiente.
            if pd.isna(tx):
                return f

            # El pedido pertenece al primer ciclo cuyo corte todavía puede alcanzar.
            if pd.Timestamp(tx) <= corte:
                return f

        # Si la transmisión quedó después del último corte visible, no la forzamos
        # dentro del horizonte mostrado.
        return pd.NaT

    if not zona.empty:
        zona["FechaPreparacionZona"] = zona.apply(_fecha_preparacion_zona, axis=1)
        zona_asignada = zona[zona["FechaPreparacionZona"].notna()].copy()

        if not zona_asignada.empty:
            resumen_zona = (zona_asignada.groupby("FechaPreparacionZona", as_index=False)
                .agg(ZonaLineas=("Lineas", "sum"), ZonaUnidades=("TotalUnidades", "sum")))
            for _, rz in resumen_zona.iterrows():
                f = pd.Timestamp(rz["FechaPreparacionZona"]).normalize()
                mask_f = cal["Fecha"].eq(f)
                cal.loc[mask_f, "Zona"] += float(rz["ZonaLineas"] or 0)
                cal.loc[mask_f, "Zona Unid."] += float(rz["ZonaUnidades"] or 0)

    # EASY: la fecha del agrupador manda y genera una fecha sugerida (primer día de sus 48 h).
    # Si existe una coordinación persistida, FechaCoordinada tiene prioridad sobre la regla automática.
    easy = activos[activos["EsEasy"]].copy()
    coord_map = {}
    if coordinaciones is not None and not coordinaciones.empty:
        cc = coordinaciones.copy()
        if all(c in cc.columns for c in ["Tipo", "Referencia", "FechaCoordinada"]):
            cc = cc[cc["Tipo"].fillna("").astype(str).map(_norm).eq("EASY")].copy()
            cc = cc[~cc.get("Estado", pd.Series("PLANIFICADO", index=cc.index)).fillna("").astype(str).map(_norm).eq("CANCELADO")]
            for _, cr in cc.iterrows():
                fc = pd.to_datetime(cr.get("FechaCoordinada", ""), errors="coerce", dayfirst=True)
                if pd.notna(fc):
                    coord_map[_norm(cr.get("Referencia", ""))] = pd.Timestamp(fc).normalize()

    easy_plan_rows = []
    for _, r in easy.iterrows():
        f = _fecha_easy_desde_fila(r, hoy)
        ventana = _ventana_easy(f)
        if not ventana:
            continue
        sugerida = ventana[0]
        referencia = _texto(r.get("DespachoDescripcion", "")) or _texto(r.get("Planificacion", "")) or f"EASY {pd.Timestamp(f).strftime('%d-%m')}"
        coordinada = coord_map.get(_norm(referencia), sugerida)
        d = coordinada
        carga = float(pd.to_numeric(pd.Series([r.get("Lineas", 0)]), errors="coerce").fillna(0).iloc[0])
        unidades = float(pd.to_numeric(pd.Series([r.get("TotalUnidades", 0)]), errors="coerce").fillna(0).iloc[0])
        cal.loc[cal["Fecha"].eq(d), "EASY"] += carga
        cal.loc[cal["Fecha"].eq(d), "EASY Unid."] += unidades
        mask_d = cal["Fecha"].eq(d)
        if mask_d.any():
            etiqueta = pd.Timestamp(f).strftime("%d/%m")
            actual = str(cal.loc[mask_d, "Entregas EASY"].iloc[0])
            valores = [] if actual in ["—", "", "nan"] else actual.split(", ")
            if etiqueta not in valores: valores.append(etiqueta)
            cal.loc[mask_d, "Entregas EASY"] = ", ".join(valores)
        easy_plan_rows.append({
            "Referencia": referencia, "FechaEntrega": pd.Timestamp(f).normalize(),
            "FechaSugerida": pd.Timestamp(sugerida).normalize(), "FechaCoordinada": pd.Timestamp(d).normalize(),
            "Pedido": _texto(r.get("Pedido", "")), "Líneas": carga, "Unidades": unidades,
            "EsManual": _norm(referencia) in coord_map,
        })

    if easy_plan_rows:
        easy_plan = pd.DataFrame(easy_plan_rows)
        easy_agrupados = (easy_plan.groupby(["Referencia","FechaEntrega","FechaSugerida","FechaCoordinada","EsManual"], as_index=False)
            .agg(Pedidos=("Pedido","nunique"), Líneas=("Líneas","sum"), Unidades=("Unidades","sum"))
            .sort_values(["FechaEntrega","Referencia"]).reset_index(drop=True))
    else:
        easy_agrupados = pd.DataFrame(columns=["Referencia","FechaEntrega","FechaSugerida","FechaCoordinada","EsManual","Pedidos","Líneas","Unidades"])

    # RETIRA normal: es demanda del día y ocupa HOY automáticamente.
    # Si el pedido califica como Full Loza, no se fuerza a hoy: queda para elegir jornada.
    retira_normal = activos[mask_retira & ~mask_loza].copy()
    if not retira_normal.empty and (cal["Fecha"].eq(hoy)).any():
        cal.loc[cal["Fecha"].eq(hoy), "RETIRA"] += float(pd.to_numeric(retira_normal["Lineas"], errors="coerce").fillna(0).sum())
        cal.loc[cal["Fecha"].eq(hoy), "RETIRA Unid."] += float(pd.to_numeric(retira_normal["TotalUnidades"], errors="coerce").fillna(0).sum())

    # DIARIOS + URGENTE + URGENTES 2: demanda prioritaria del día.
    # Todo pedido activo/no iniciado de estos canales consume HOY automáticamente.
    prioritarios_hoy = activos[mask_prioritarios].copy()
    if not prioritarios_hoy.empty and (cal["Fecha"].eq(hoy)).any():
        mask_hoy = cal["Fecha"].eq(hoy)
        cal.loc[mask_hoy, "Prioritarios"] += float(pd.to_numeric(prioritarios_hoy["Lineas"], errors="coerce").fillna(0).sum())
        cal.loc[mask_hoy, "Prioritarios Unid."] += float(pd.to_numeric(prioritarios_hoy["TotalUnidades"], errors="coerce").fillna(0).sum())

    # Agrupados pendientes Expresos: coordinables y persistentes.
    comp = activos[(estado.eq("PREPARACION")) & ep.eq("PENDIENTE")].copy()
    agrup = comp.get("DespachoDescripcion", pd.Series("", index=comp.index)).fillna("").astype(str).str.strip()
    comp["AgrupadorReal"] = agrup
    txt = comp.apply(lambda r: " | ".join(_norm(r.get(c,"")) for c in ["Planificacion","FrecuenciaEntrega","FrecuenciaPreparacion","DespachoDescripcion"]), axis=1)
    exp = comp[txt.str.contains("EXPRES", na=False)].copy()

    # RETIRA Full Loza queda coordinable. RETIRA normal ya consume HOY.
    ret = activos[mask_retira & mask_loza].copy()
    if not ret.empty:
        ret["AgrupadorReal"] = ret.get("DespachoDescripcion", pd.Series("", index=ret.index)).fillna("").astype(str).str.strip()
        ret.loc[ret["AgrupadorReal"].eq(""), "AgrupadorReal"] = "RETIRA LOZA · SIN AGRUPAR"

    def _coord_por_tipo(tipo):
        out = {}
        if coordinaciones is None or coordinaciones.empty:
            return out
        cc = coordinaciones.copy()
        if not all(c in cc.columns for c in ["Tipo","Referencia","FechaCoordinada"]):
            return out
        cc = cc[cc["Tipo"].fillna("").astype(str).map(_norm).eq(_norm(tipo))].copy()
        if "Estado" in cc.columns:
            cc = cc[~cc["Estado"].fillna("").astype(str).map(_norm).eq("CANCELADO")]
        for _, cr in cc.iterrows():
            fc = pd.to_datetime(cr.get("FechaCoordinada", ""), errors="coerce", dayfirst=True)
            if pd.notna(fc):
                out[_norm(cr.get("Referencia", ""))] = pd.Timestamp(fc).normalize()
        return out

    coord_exp = _coord_por_tipo("EXPRESOS")
    coord_ret = _coord_por_tipo("RETIRA")

    def resumir(df, tipo_coord=""):
        cols=["AgrupadorReal","Pedidos","Clientes","Líneas","Unidades","m³","FechaCoordinada","EsManual"]
        if df.empty: return pd.DataFrame(columns=cols)
        z=(df.groupby("AgrupadorReal", as_index=False).agg(Pedidos=("Pedido","nunique"), Clientes=("ClienteCodigo","nunique"),
            Líneas=("Lineas","sum"), Unidades=("TotalUnidades","sum"), **{"m³":("TotalM3","sum")})
            .sort_values("Líneas", ascending=False).reset_index(drop=True))
        cmap = coord_exp if tipo_coord == "EXPRESOS" else coord_ret if tipo_coord == "RETIRA" else {}
        z["FechaCoordinada"] = z["AgrupadorReal"].map(lambda x: cmap.get(_norm(x), pd.NaT))
        z["EsManual"] = z["FechaCoordinada"].notna()
        return z

    exp_res = resumir(exp, "EXPRESOS")
    ret_res = resumir(ret, "RETIRA")

    # Las coordinaciones persistidas ya consumen capacidad en su fecha.
    for _, rr in exp_res[exp_res["FechaCoordinada"].notna()].iterrows():
        mf = cal["Fecha"].eq(pd.Timestamp(rr["FechaCoordinada"]).normalize())
        cal.loc[mf, "Expresos"] += float(rr.get("Líneas",0) or 0)
        cal.loc[mf, "Expresos Unid."] += float(rr.get("Unidades",0) or 0)
    for _, rr in ret_res[ret_res["FechaCoordinada"].notna()].iterrows():
        mf = cal["Fecha"].eq(pd.Timestamp(rr["FechaCoordinada"]).normalize())
        cal.loc[mf, "RETIRA"] += float(rr.get("Líneas",0) or 0)
        cal.loc[mf, "RETIRA Unid."] += float(rr.get("Unidades",0) or 0)

    # Mundo todavía SIN AGRUPAR: visibilidad, pero no se fuerza a una fecha futura.
    libres = activos[estado.eq("PENDIENTE")].copy()
    txt_lib = libres.apply(lambda r: " | ".join(_norm(r.get(c,"")) for c in ["Planificacion","FrecuenciaEntrega","FrecuenciaPreparacion","DespachoDescripcion"]), axis=1)
    ret_lib = txt_lib.str.contains("RETIRA", na=False)
    backlog_exp = libres[libres["TipoFlexible"].eq("EXPRESOS") & ~ret_lib & ~libres["EsEasy"]].copy()
    backlog_dia = libres[libres["TipoFlexible"].eq("DIARIOS") & ~ret_lib & ~libres["EsEasy"]].copy()

    def _backlog_row(df, tipo):
        if df.empty:
            return {"Tipo":tipo,"Pedidos":0,"Líneas":0,"Unidades":0,"m³":0.0,"Antig. máx.":0}
        edades=(hoy-pd.to_datetime(df.get("FechaTransmisionERP",df.get("Fecha")),errors="coerce").dt.normalize()).dt.days.clip(lower=0).dropna()
        return {"Tipo":tipo,"Pedidos":int(df["Pedido"].nunique()),"Líneas":int(pd.to_numeric(df["Lineas"],errors="coerce").fillna(0).sum()),
                "Unidades":int(pd.to_numeric(df["TotalUnidades"],errors="coerce").fillna(0).sum()),"m³":round(float(pd.to_numeric(df["TotalM3"],errors="coerce").fillna(0).sum()),2),
                "Antig. máx.":int(edades.max()) if not edades.empty else 0}
    backlog = pd.DataFrame([_backlog_row(backlog_exp,"EXPRESOS sin agrupar"), _backlog_row(backlog_dia,"DIARIOS sin agrupar")])

    cal[["Zona","EASY","Expresos","RETIRA","Prioritarios"]] = cal[["Zona","EASY","Expresos","RETIRA","Prioritarios"]].round(1)
    cal[["Zona Unid.","EASY Unid.","Expresos Unid.","RETIRA Unid.","Prioritarios Unid."]] = cal[["Zona Unid.","EASY Unid.","Expresos Unid.","RETIRA Unid.","Prioritarios Unid."]].round(0)
    cal["Total"] = cal[["Zona","EASY","Expresos","RETIRA","Prioritarios"]].sum(axis=1).round(1)
    cal["Total Unid."] = cal[["Zona Unid.","EASY Unid.","Expresos Unid.","RETIRA Unid.","Prioritarios Unid."]].sum(axis=1).round(0)
    cal["Capacidad"] = cal["Día"].map(lambda d: OBJETIVO_CONTROL_SABADO if d == "SABADO" else OBJETIVO_CONTROL_DIARIO)
    cal["Margen"] = (cal["Capacidad"] - cal["Total"]).round(1)
    cal["Ocupación %"] = (cal["Total"] / cal["Capacidad"].replace(0, pd.NA) * 100).fillna(0).round(1)
    return {"calendario": cal, "expresos_agrupados": exp_res, "retira_agrupados": ret_res, "easy_agrupados": easy_agrupados, "backlog_sin_agrupar": backlog}
