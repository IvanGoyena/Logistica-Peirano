from __future__ import annotations
import html
from io import BytesIO
import pandas as pd
import streamlit as st
import altair as alt
from models.inteligencia_operativa import construir_inteligencia_operativa, simular_camionetas_clientes, OBJETIVO_CONTROL_DIARIO

try:
    from utils.google_sheets import (
        leer_planning_coordinacion, guardar_planning_coordinacion, leer_planning_historial
    )
except Exception:
    try:
        from google_sheets import (
            leer_planning_coordinacion, guardar_planning_coordinacion, leer_planning_historial
        )
    except Exception:
        leer_planning_coordinacion = guardar_planning_coordinacion = leer_planning_historial = None


def _fmt(n, dec=0):
    try:
        if dec:
            return f"{float(n):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return "0"


def _tabla(df, antig=False):
    cfg = {
        "Pedidos": st.column_config.NumberColumn(format="%d"),
        "Líneas": st.column_config.NumberColumn(format="%d"),
        "Unidades": st.column_config.NumberColumn(format="%d"),
        "Unid./línea": st.column_config.NumberColumn(format="%.1f"),
        "m³": st.column_config.NumberColumn(format="%.2f"),
        "m³/línea": st.column_config.NumberColumn(format="%.3f"),
        "Camionetas 8m³": st.column_config.NumberColumn(format="%.2f", help="Equivalente volumétrico: m³ / 8. No representa redondeo de vehículos físicos."),
        "% líneas": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    }
    if antig:
        cfg["Antig. prom."] = st.column_config.NumberColumn(format="%.1f días")
        cfg["Antig. máx."] = st.column_config.NumberColumn(format="%d días")
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg)



def _xlsx_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    bio = BytesIO()
    export = df.copy() if df is not None else pd.DataFrame()
    # Excel no soporta datetimes timezone-aware.
    for c in export.columns:
        if pd.api.types.is_datetime64_any_dtype(export[c]):
            try:
                export[c] = pd.to_datetime(export[c], errors="coerce").dt.tz_localize(None)
            except Exception:
                pass
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name=sheet_name[:31])
        ws = writer.book[sheet_name[:31]]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col_cells in ws.columns:
            vals = [str(c.value) if c.value is not None else "" for c in col_cells[:200]]
            width = min(max([len(v) for v in vals] + [10]) + 2, 45)
            ws.column_dimensions[col_cells[0].column_letter].width = width
    return bio.getvalue()


def _titulo_descargas(titulo: str, resumen: pd.DataFrame, detalle: pd.DataFrame, prefijo: str):
    c_title, c_r, c_d = st.columns([7.2, 1.4, 1.4], vertical_alignment="center")
    with c_title:
        st.markdown(f"### {titulo}")
    with c_r:
        st.download_button(
            "⬇ Resumen",
            data=_xlsx_bytes(resumen, "Resumen"),
            file_name=f"{prefijo}_Resumen.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_{prefijo}_resumen",
        )
    with c_d:
        st.download_button(
            "⬇ Detalle",
            data=_xlsx_bytes(detalle, "Detalle articulos"),
            file_name=f"{prefijo}_Detalle_Articulos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_{prefijo}_detalle",
        )


def render_inteligencia(
    datos_dashboard: pd.DataFrame,
    tabla_detalle_dashboard: pd.DataFrame,
    tabla_personal: pd.DataFrame | None = None,
    tabla_transmisiones: pd.DataFrame | None = None,
) -> None:
    st.subheader("🧠 Inteligencia operativa")
    st.caption("Planning diario + radiografía de demanda: zona obligatoria, camionetas simuladas por cliente completo, zonas semanales, carga flexible, Sanitarios y EASY. La antigüedad y prioridad se calculan desde la fecha de transmisión al WMS, no desde la creación del pedido.")

    # EASY independiente. OFF lo excluye de la lectura general, pero su tabla sigue visible.
    if "io_v3_easy_activo" not in st.session_state:
        st.session_state["io_v3_easy_activo"] = True
    easy_activo = st.toggle(
        "🏬 EASY activo en la planificación",
        value=st.session_state["io_v3_easy_activo"],
        key="io_v3_easy_toggle",
        help="ON: EASY participa de la lectura operativa. OFF: se excluye de la demanda general, pero sigue visible en su bloque independiente.",
    )
    st.session_state["io_v3_easy_activo"] = easy_activo

    # Decisiones persistidas del planning. Si Google no responde, el tablero sigue con reglas automáticas.
    coordinaciones = pd.DataFrame()
    error_coord = None
    if leer_planning_coordinacion is not None:
        try:
            coordinaciones = leer_planning_coordinacion()
        except Exception as e:
            error_coord = str(e)

    io = construir_inteligencia_operativa(
        datos_dashboard,
        tabla_detalle_dashboard,
        personal=tabla_personal,
        transmisiones=tabla_transmisiones,
        easy_activo=easy_activo,
        coordinaciones=coordinaciones,
    )
    if io.get("vacio"):
        st.info(io.get("mensaje")); return

    # ==========================================================
    # V5 — CALENDARIO SEMANAL DE CAPACIDAD
    # ==========================================================
    st.markdown("## 📅 Planning semanal de capacidad")
    st.caption("Planning maestro de preparación y entrega: Zona se agenda por cronograma; EASY toma la fecha del agrupador (EASY DD-MM) y reserva el 100% en el primer día de sus 48 h previas; RETIRA normal, DIARIOS, URGENTE y URGENTES 2 ocupan automáticamente el día actual; RETIRA normal, DIARIOS y URGENTES consumen HOY; EASY, Expresos agrupados y RETIRA Full Loza pueden quedar coordinados con fecha persistente. El backlog sin agrupar queda visible aparte. Objetivo: 850 líneas L-V y 567 el sábado.")
    sem = io.get("calendario_semanal", {})
    cal = sem.get("calendario", pd.DataFrame()).copy()
    exp_agr = sem.get("expresos_agrupados", pd.DataFrame()).copy()
    ret_agr = sem.get("retira_agrupados", pd.DataFrame()).copy()
    easy_agr = sem.get("easy_agrupados", pd.DataFrame()).copy()
    backlog = sem.get("backlog_sin_agrupar", pd.DataFrame()).copy()

    # Asignación virtual por FECHA concreta.
    # No usamos sólo el nombre del día porque el horizonte contiene, por ejemplo,
    # dos VIERNES distintos y una asignación por "VIERNES" duplicaría la carga.
    asignaciones = {}
    if not cal.empty:
        cal["Fecha"] = pd.to_datetime(cal["Fecha"], errors="coerce").dt.normalize()
        filas_fecha = cal.loc[cal["Fecha"].notna(), ["Día", "Fecha"]].drop_duplicates("Fecha")
        mapa_fechas = {
            f"{str(r['Día']).upper()} {pd.Timestamp(r['Fecha']).strftime('%d/%m')}": pd.Timestamp(r["Fecha"])
            for _, r in filas_fecha.iterrows()
        }
        opciones_fecha = ["Sin asignar"] + list(mapa_fechas.keys())
    else:
        mapa_fechas = {}
        opciones_fecha = ["Sin asignar"]

    # EASY: regla automática de 48 h + posibilidad de adelantar/reprogramar y persistir la decisión.
    if error_coord:
        st.warning("El planning se muestra con reglas automáticas porque no se pudo leer la coordinación guardada en Google Sheets.")

    if not cal.empty and easy_agr is not None and not easy_agr.empty:
        with st.expander("🏬 Coordinar EASY · fecha sugerida vs. fecha acordada", expanded=True):
            st.caption("La fecha sugerida sigue siendo el primer día de las 48 h previas. Si coordinás otra fecha, esa decisión queda guardada y manda sobre la regla automática.")
            for i, r in easy_agr.iterrows():
                ref = str(r.get("Referencia", f"EASY {i+1}"))
                f_ent = pd.to_datetime(r.get("FechaEntrega"), errors="coerce")
                f_sug = pd.to_datetime(r.get("FechaSugerida"), errors="coerce")
                f_coord = pd.to_datetime(r.get("FechaCoordinada"), errors="coerce")
                c1,c2,c3,c4 = st.columns([3.6,1.55,1.55,1.0], vertical_alignment="center")
                ent_txt = f_ent.strftime("%d/%m") if pd.notna(f_ent) else "—"
                sug_txt = f_sug.strftime("%d/%m") if pd.notna(f_sug) else "—"
                manual = " · ✍️ coordinado" if bool(r.get("EsManual", False)) else " · automático"
                c1.markdown(f"**{ref}** · entrega **{ent_txt}** · sugerido **{sug_txt}** · {_fmt(r.get('Líneas',0))} L / {_fmt(r.get('Unidades',0))} U{manual}")

                key_easy = f"io_easy_coord_{i}_{ref}"
                default_label = "Sin asignar"
                if pd.notna(f_coord):
                    for lab, ff in mapa_fechas.items():
                        if pd.Timestamp(ff).normalize() == pd.Timestamp(f_coord).normalize():
                            default_label = lab; break
                idx_default = opciones_fecha.index(default_label) if default_label in opciones_fecha else 0
                seleccion = c2.selectbox("Preparar", opciones_fecha, index=idx_default, key=key_easy, label_visibility="collapsed")
                obs = c3.text_input("Observación", key=f"io_easy_obs_{i}_{ref}", placeholder="Opcional", label_visibility="collapsed")
                if c4.button("💾 Guardar", key=f"io_easy_save_{i}_{ref}", use_container_width=True):
                    if guardar_planning_coordinacion is None:
                        st.error("No está disponible el módulo de persistencia de Google Sheets.")
                    elif seleccion == "Sin asignar":
                        st.error("Elegí una fecha concreta de preparación antes de guardar.")
                    else:
                        try:
                            usuario = str(st.session_state.get("usuario_nombre") or st.session_state.get("usuario") or st.session_state.get("username") or "Operación")
                            fecha_obj = mapa_fechas[seleccion]
                            guardar_planning_coordinacion({
                                "Tipo": "EASY", "Referencia": ref,
                                "FechaEntrega": f_ent.strftime("%Y-%m-%d") if pd.notna(f_ent) else "",
                                "FechaSugerida": f_sug.strftime("%Y-%m-%d") if pd.notna(f_sug) else "",
                                "FechaCoordinada": pd.Timestamp(fecha_obj).strftime("%Y-%m-%d"),
                                "Lineas": r.get("Líneas",0), "Unidades": r.get("Unidades",0),
                                "Estado": "PLANIFICADO", "Usuario": usuario, "Observacion": obs,
                            })
                            st.success(f"{ref}: preparación guardada para {pd.Timestamp(fecha_obj).strftime('%d/%m')}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"No se pudo guardar la coordinación: {e}")

            if leer_planning_historial is not None:
                with st.popover("🕘 Ver historial de coordinación"):
                    try:
                        hist = leer_planning_historial()
                        if hist.empty:
                            st.caption("Todavía no hay cambios registrados.")
                        else:
                            h = hist[hist.get("Tipo", "").fillna("").astype(str).str.upper().eq("EASY")].copy()
                            cols_h = [c for c in ["Fecha","Referencia","FechaAnterior","FechaNueva","Accion","Usuario","Observacion"] if c in h.columns]
                            st.dataframe(h[cols_h].tail(30).iloc[::-1], hide_index=True, width="stretch")
                    except Exception as e:
                        st.caption(f"No se pudo leer el historial: {e}")

    if not cal.empty and exp_agr is not None and not exp_agr.empty:
        with st.expander("⚡ Coordinar Expresos ya agrupados", expanded=True):
            st.caption("Acá aparece lo que ya está agrupado en DIGIP pero todavía no inició. La fecha guardada queda persistida y consume capacidad del planning.")
            for i, r in exp_agr.iterrows():
                nombre = str(r.get("AgrupadorReal", f"EXP {i+1}"))
                f_coord = pd.to_datetime(r.get("FechaCoordinada"), errors="coerce")
                c1,c2,c3,c4 = st.columns([3.4,1.45,1.55,1.0], vertical_alignment="center")
                estado_txt = " · ✍️ coordinado" if pd.notna(f_coord) else " · pendiente de coordinar"
                c1.markdown(f"**{nombre}** · {_fmt(r.get('Pedidos',0))} pedidos · {_fmt(r.get('Líneas',0))} L / {_fmt(r.get('Unidades',0))} U · {_fmt(r.get('m³',0),2)} m³{estado_txt}")
                default_label = "Sin asignar"
                if pd.notna(f_coord):
                    for lab, ff in mapa_fechas.items():
                        if pd.Timestamp(ff).normalize() == pd.Timestamp(f_coord).normalize(): default_label=lab; break
                idx = opciones_fecha.index(default_label) if default_label in opciones_fecha else 0
                fecha_sel = c2.selectbox("Preparar", opciones_fecha, index=idx, key=f"io_v7_exp_fecha_{i}_{nombre}", label_visibility="collapsed")
                obs = c3.text_input("Observación", key=f"io_v7_exp_obs_{i}_{nombre}", placeholder="Opcional", label_visibility="collapsed")
                if c4.button("💾 Guardar", key=f"io_v7_exp_save_{i}_{nombre}", use_container_width=True):
                    if guardar_planning_coordinacion is None: st.error("No está disponible Google Sheets.")
                    elif fecha_sel == "Sin asignar": st.error("Elegí una fecha concreta.")
                    else:
                        try:
                            usuario=str(st.session_state.get("usuario_nombre") or st.session_state.get("usuario") or st.session_state.get("username") or "Operación")
                            fo=mapa_fechas[fecha_sel]
                            guardar_planning_coordinacion({"Tipo":"EXPRESOS","Referencia":nombre,"FechaCoordinada":fo.strftime("%Y-%m-%d"),"Lineas":r.get("Líneas",0),"Unidades":r.get("Unidades",0),"Estado":"PLANIFICADO","Usuario":usuario,"Observacion":obs})
                            st.success(f"{nombre}: guardado para {fo.strftime('%d/%m')}."); st.rerun()
                        except Exception as e: st.error(f"No se pudo guardar: {e}")

    # RETIRA normal/DIARIOS/URGENTES consumen HOY automáticamente. Sólo RETIRA Full Loza se coordina.
    if not cal.empty and ret_agr is not None and not ret_agr.empty:
        with st.expander("🚽 Coordinar RETIRA Full Loza", expanded=False):
            for i, r in ret_agr.iterrows():
                nombre = str(r.get("AgrupadorReal", f"RETIRA {i+1}"))
                f_coord = pd.to_datetime(r.get("FechaCoordinada"), errors="coerce")
                c1,c2,c3,c4 = st.columns([3.4,1.45,1.55,1.0], vertical_alignment="center")
                c1.markdown(f"**{nombre}** · {_fmt(r.get('Pedidos',0))} pedidos · {_fmt(r.get('Líneas',0))} L / {_fmt(r.get('Unidades',0))} U")
                default_label="Sin asignar"
                if pd.notna(f_coord):
                    for lab,ff in mapa_fechas.items():
                        if pd.Timestamp(ff).normalize()==pd.Timestamp(f_coord).normalize(): default_label=lab; break
                idx=opciones_fecha.index(default_label) if default_label in opciones_fecha else 0
                fecha_sel=c2.selectbox("Preparar",opciones_fecha,index=idx,key=f"io_v7_ret_fecha_{i}_{nombre}",label_visibility="collapsed")
                obs=c3.text_input("Observación",key=f"io_v7_ret_obs_{i}_{nombre}",placeholder="Opcional",label_visibility="collapsed")
                if c4.button("💾 Guardar",key=f"io_v7_ret_save_{i}_{nombre}",use_container_width=True):
                    if guardar_planning_coordinacion is None: st.error("No está disponible Google Sheets.")
                    elif fecha_sel=="Sin asignar": st.error("Elegí una fecha concreta.")
                    else:
                        try:
                            usuario=str(st.session_state.get("usuario_nombre") or st.session_state.get("usuario") or st.session_state.get("username") or "Operación")
                            fo=mapa_fechas[fecha_sel]
                            guardar_planning_coordinacion({"Tipo":"RETIRA","Referencia":nombre,"FechaCoordinada":fo.strftime("%Y-%m-%d"),"Lineas":r.get("Líneas",0),"Unidades":r.get("Unidades",0),"Estado":"PLANIFICADO","Usuario":usuario,"Observacion":obs})
                            st.success(f"{nombre}: guardado para {fo.strftime('%d/%m')}."); st.rerun()
                        except Exception as e: st.error(f"No se pudo guardar: {e}")

    # Foto global: TODO el pendiente real, esté o no planificado. Incluye HOY.
    dias_pend = float(io.get("dias_pendientes", 0) or 0)
    g1,g2,g3,g4 = st.columns(4)
    g1.metric("📦 Pendiente total", f"{_fmt(io.get('carga_lineas',0))} líneas")
    g2.metric("Unidades pendientes", _fmt(io.get("carga_unidades",0)))
    g3.metric("⏱️ Días equivalentes", f"{_fmt(dias_pend,1)} días", help="Total de líneas pendientes / 850 líneas por jornada. Incluye el día actual y no depende de si la carga ya está planificada.")
    g4.metric("Objetivo diario", f"{_fmt(OBJETIVO_CONTROL_DIARIO)} líneas")

    if backlog is not None and not backlog.empty:
        st.markdown("### 📦 Pendiente todavía sin agrupar")
        st.caption("Visibilidad del mundo que todavía está detrás de DIGIP. No se fuerza a una fecha futura hasta que exista una agrupación/decisión operativa.")
        b=backlog.copy()
        total_b={"Tipo":"TOTAL SIN AGRUPAR","Pedidos":int(pd.to_numeric(b.get("Pedidos",0),errors="coerce").fillna(0).sum()),"Líneas":int(pd.to_numeric(b.get("Líneas",0),errors="coerce").fillna(0).sum()),"Unidades":int(pd.to_numeric(b.get("Unidades",0),errors="coerce").fillna(0).sum()),"m³":round(float(pd.to_numeric(b.get("m³",0),errors="coerce").fillna(0).sum()),2),"Antig. máx.":int(pd.to_numeric(b.get("Antig. máx.",0),errors="coerce").fillna(0).max())}
        b=pd.concat([b,pd.DataFrame([total_b])],ignore_index=True)
        st.dataframe(b,hide_index=True,width="stretch",column_config={"Pedidos":st.column_config.NumberColumn(format="%d"),"Líneas":st.column_config.NumberColumn(format="%d"),"Unidades":st.column_config.NumberColumn(format="%d"),"m³":st.column_config.NumberColumn(format="%.2f"),"Antig. máx.":st.column_config.NumberColumn(format="%d días")})

    if not cal.empty:
        cal["Total"] = cal[[c for c in ["Zona","EASY","Expresos","RETIRA","Prioritarios"] if c in cal.columns]].sum(axis=1).round(1)
        unid_cols = [c for c in ["Zona Unid.","EASY Unid.","Expresos Unid.","RETIRA Unid.","Prioritarios Unid."] if c in cal.columns]
        cal["Total Unid."] = cal[unid_cols].sum(axis=1).round(0) if unid_cols else 0
        cal["Capacidad"] = cal["Día"].map(lambda d: 567 if d == "SABADO" else OBJETIVO_CONTROL_DIARIO)
        cal["Margen"] = (cal["Capacidad"]-cal["Total"]).round(1)
        cal["Ocupación %"] = (cal["Total"]/cal["Capacidad"].replace(0, pd.NA)*100).fillna(0).round(1)

        # KPIs ejecutivos del horizonte visible (HOY en adelante).
        total_lin = float(cal["Total"].sum())
        total_uni = float(cal["Total Unid."].sum())
        capacidad_total = float(cal["Capacidad"].sum())
        ocup_prom = (total_lin / capacidad_total * 100) if capacidad_total else 0
        idx_cargado = cal["Ocupación %"].idxmax()
        fila_cargada = cal.loc[idx_cargado]
        idx_uni = cal["Total Unid."].idxmax()
        fila_uni = cal.loc[idx_uni]
        k1,k2,k3,k4,k5 = st.columns(5)
        k1.metric("Líneas planificadas", _fmt(total_lin))
        k2.metric("Unidades planificadas", _fmt(total_uni))
        k3.metric("Ocupación del horizonte", f"{ocup_prom:.1f}%")
        k4.metric("Día más cargado", f"{str(fila_cargada['Día']).title()} · {float(fila_cargada['Ocupación %']):.1f}%")
        k5.metric("Pico de unidades", f"{str(fila_uni['Día']).title()} · {_fmt(fila_uni['Total Unid.'])}")

        # Gráficos del planning: las líneas gobiernan capacidad, pero las unidades nunca se pierden.
        # Barras = líneas por canal y fecha. Etiqueta superior = unidades totales de la jornada.
        canales_base = ["Zona", "EASY", "Expresos", "RETIRA", "Prioritarios"]
        mapa_unidades = {
            "Zona": "Zona Unid.",
            "EASY": "EASY Unid.",
            "Expresos": "Expresos Unid.",
            "RETIRA": "RETIRA Unid.",
            "Prioritarios": "Prioritarios Unid.",
        }
        canales_graf = [c for c in canales_base if c in cal.columns]
        graf_cols = ["Fecha"] + canales_graf + [mapa_unidades[c] for c in canales_graf if mapa_unidades[c] in cal.columns]
        graf = cal[graf_cols].copy()
        graf["Fecha"] = pd.to_datetime(graf["Fecha"], errors="coerce")
        graf = graf[graf["Fecha"].notna()].sort_values("Fecha").reset_index(drop=True)

        dias_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
        graf["Jornada"] = graf["Fecha"].apply(lambda f: f"{dias_es.get(f.weekday(), '')} {f.strftime('%d/%m')}")
        graf["Orden"] = range(len(graf))

        # Formato largo con líneas y unidades del mismo canal para enriquecer el tooltip.
        filas_plot = []
        for _, r in graf.iterrows():
            for canal in canales_graf:
                col_u = mapa_unidades.get(canal)
                filas_plot.append({
                    "Jornada": r["Jornada"],
                    "Orden": r["Orden"],
                    "Canal": canal,
                    "Líneas": float(pd.to_numeric(pd.Series([r.get(canal, 0)]), errors="coerce").fillna(0).iloc[0]),
                    "Unidades": float(pd.to_numeric(pd.Series([r.get(col_u, 0)]), errors="coerce").fillna(0).iloc[0]) if col_u else 0.0,
                })
        graf_plot = pd.DataFrame(filas_plot)

        # Totales por jornada para escribir las unidades arriba de cada barra.
        totales_fecha = graf[["Jornada", "Orden"]].copy()
        totales_fecha["Líneas"] = graf[canales_graf].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        cols_uni = [mapa_unidades[c] for c in canales_graf if mapa_unidades[c] in graf.columns]
        totales_fecha["Unidades"] = graf[cols_uni].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1) if cols_uni else 0
        totales_fecha["EtiquetaUnidades"] = totales_fecha["Unidades"].map(lambda x: f"{_fmt(x)} u")

        resumen_canales = pd.DataFrame({
            "Canal": canales_graf,
            "Líneas": [float(pd.to_numeric(cal[c], errors="coerce").fillna(0).sum()) for c in canales_graf],
            "Unidades": [float(pd.to_numeric(cal.get(mapa_unidades[c], 0), errors="coerce").fillna(0).sum()) if mapa_unidades[c] in cal.columns else 0.0 for c in canales_graf],
        })
        resumen_canales = resumen_canales[resumen_canales["Líneas"] > 0].copy()

        st.caption("**Planning visual de carga — líneas + unidades**")
        col_graf, col_torta = st.columns([2.55, 1], gap="large")

        with col_graf:
            barras = (
                alt.Chart(graf_plot)
                .mark_bar(size=52)
                .encode(
                    x=alt.X(
                        "Jornada:N",
                        sort=alt.SortField(field="Orden", order="ascending"),
                        title="Fecha de preparación",
                        axis=alt.Axis(labelAngle=0, labelPadding=12, labelFontSize=12, titlePadding=16),
                    ),
                    y=alt.Y("sum(Líneas):Q", title="Líneas", axis=alt.Axis(labelFontSize=11, titlePadding=12)),
                    color=alt.Color("Canal:N", title="Canal"),
                    order=alt.Order("Orden:Q", sort="ascending"),
                    tooltip=[
                        alt.Tooltip("Jornada:N", title="Preparación"),
                        alt.Tooltip("Canal:N"),
                        alt.Tooltip("sum(Líneas):Q", title="Líneas", format=",.0f"),
                        alt.Tooltip("sum(Unidades):Q", title="Unidades", format=",.0f"),
                    ],
                )
            )
            etiquetas_unidades = (
                alt.Chart(totales_fecha)
                .mark_text(dy=-10, color="white", fontSize=13, fontWeight="bold")
                .encode(
                    x=alt.X("Jornada:N", sort=alt.SortField(field="Orden", order="ascending")),
                    y=alt.Y("Líneas:Q"),
                    text=alt.Text("EtiquetaUnidades:N"),
                    tooltip=[
                        alt.Tooltip("Jornada:N", title="Preparación"),
                        alt.Tooltip("Líneas:Q", title="Líneas totales", format=",.0f"),
                        alt.Tooltip("Unidades:Q", title="Unidades totales", format=",.0f"),
                    ],
                )
            )
            chart_barras = (barras + etiquetas_unidades).properties(height=440, title="Carga por fecha de preparación")
            st.altair_chart(chart_barras, use_container_width=True)

        with col_torta:
            if resumen_canales.empty:
                st.info("No hay líneas planificadas para componer por canal.")
            else:
                total_torta = float(resumen_canales["Líneas"].sum())
                total_uni_torta = float(resumen_canales["Unidades"].sum())
                torta = (
                    alt.Chart(resumen_canales)
                    .mark_arc(innerRadius=72, outerRadius=125)
                    .encode(
                        theta=alt.Theta("Líneas:Q", stack=True),
                        color=alt.Color("Canal:N", title="Tipo de entrega"),
                        tooltip=[
                            alt.Tooltip("Canal:N", title="Canal"),
                            alt.Tooltip("Líneas:Q", title="Líneas", format=",.0f"),
                            alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                        ],
                    )
                )
                texto_centro = (
                    alt.Chart(pd.DataFrame({"texto": [f"{_fmt(total_torta)}\nlíneas"]}))
                    .mark_text(size=20, fontWeight="bold", lineBreak="\n", color="white")
                    .encode(
                        text="texto:N",
                        tooltip=[alt.Tooltip("texto:N", title=f"Total: {_fmt(total_uni_torta)} unidades")],
                    )
                )
                chart_torta = (torta + texto_centro).properties(height=440, title="Composición pendiente por canal")
                st.altair_chart(chart_torta, use_container_width=True)

        # Tabla compacta: cada canal muestra Líneas / Unidades en una sola columna.
        # Conservamos las columnas numéricas originales en `cal` para todos los cálculos.
        vista_cal = cal[["Semana","Día","Fecha","Entrega Zona","Entregas EASY"]].copy()

        def _lu(col_lin: str, col_uni: str) -> pd.Series:
            lin = pd.to_numeric(cal.get(col_lin, 0), errors="coerce").fillna(0)
            uni = pd.to_numeric(cal.get(col_uni, 0), errors="coerce").fillna(0)
            return pd.Series(
                [f"{_fmt(l)} / {_fmt(u)}" for l, u in zip(lin, uni)],
                index=cal.index,
            )

        vista_cal["Zona L/U"] = _lu("Zona", "Zona Unid.")
        vista_cal["EASY L/U"] = _lu("EASY", "EASY Unid.")
        vista_cal["Expresos L/U"] = _lu("Expresos", "Expresos Unid.")
        vista_cal["RETIRA L/U"] = _lu("RETIRA", "RETIRA Unid.")
        vista_cal["Prioritarios L/U"] = _lu("Prioritarios", "Prioritarios Unid.")
        vista_cal["Total L/U"] = _lu("Total", "Total Unid.")
        vista_cal["Capacidad"] = cal["Capacidad"]
        vista_cal["Margen"] = cal["Margen"]
        vista_cal["Ocupación %"] = cal["Ocupación %"]

        st.caption("L/U = Líneas / Unidades")
        st.dataframe(vista_cal, hide_index=True, width="stretch", column_config={
            "Fecha": st.column_config.DateColumn(format="DD/MM"),
            "Zona L/U": st.column_config.TextColumn(help="Líneas / Unidades de Zona"),
            "EASY L/U": st.column_config.TextColumn(help="Líneas / Unidades de EASY"),
            "Expresos L/U": st.column_config.TextColumn(help="Líneas / Unidades de Expresos"),
            "RETIRA L/U": st.column_config.TextColumn(help="Líneas / Unidades de RETIRA"),
            "Prioritarios L/U": st.column_config.TextColumn(help="Líneas / Unidades de DIARIOS + URGENTE + URGENTES 2"),
            "Total L/U": st.column_config.TextColumn(help="Líneas / Unidades totales planificadas"),
            "Capacidad": st.column_config.NumberColumn(format="%.0f", help="Objetivo diario expresado en líneas"),
            "Margen": st.column_config.NumberColumn(format="%.0f", help="Capacidad de líneas menos líneas planificadas"),
            "Ocupación %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=120),
        })
        mejor = cal.loc[cal["Margen"].idxmax()] if not cal.empty else None
        if mejor is not None:
            st.info(f"💡 Mayor margen disponible: **{mejor['Día'].title()}**, {_fmt(mejor['Margen'])} líneas libres sobre su capacidad del día ({_fmt(mejor['Capacidad'])}).")

    # ==========================================================
    # SIMULADOR DE PLANNING DIARIO
    # ==========================================================
    st.markdown("## 🚚 Simulador de planning del día")
    sim = io.get("simulador", {})
    obligatorio = sim.get("obligatorio", pd.DataFrame())
    comprometido = sim.get("comprometido", pd.DataFrame())
    base_planning = sim.get("base_planning", obligatorio)
    comprometidos_resumen = sim.get("comprometidos_resumen", pd.DataFrame())
    entrega_obj = sim.get("entrega_objetivo", "")

    # La base diaria incluye sólo la zona obligatoria. Los agrupados futuros se ubican en el calendario semanal.
    base_lineas = int(pd.to_numeric(base_planning.get("Lineas", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not base_planning.empty else 0
    base_unidades = int(pd.to_numeric(base_planning.get("TotalUnidades", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not base_planning.empty else 0
    base_m3 = float(pd.to_numeric(base_planning.get("TotalM3", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()) if not base_planning.empty else 0.0
    base_pedidos = int(base_planning["Pedido"].nunique()) if not base_planning.empty and "Pedido" in base_planning.columns else 0

    oblig_ped = int(obligatorio["Pedido"].nunique()) if not obligatorio.empty and "Pedido" in obligatorio.columns else 0
    comp_ped = int(comprometido["Pedido"].nunique()) if not comprometido.empty and "Pedido" in comprometido.columns else 0
    st.info(
        f"🎯 **Planning base real** · {_fmt(base_pedidos)} pedidos · {_fmt(base_lineas)} líneas · "
        f"{_fmt(base_unidades)} unidades · {_fmt(base_m3,2)} m³.  "
        f"Zona obligatoria {entrega_obj.title() if entrega_obj else 'sin zona'}: **{_fmt(oblig_ped)} pedidos** · "
        f"agrupados/no iniciados disponibles para ubicar en la semana: **{_fmt(comp_ped)} pedidos**."
    )

    if comprometidos_resumen is not None and not comprometidos_resumen.empty:
        with st.expander("📌 Carga ya comprometida — agrupada y todavía no iniciada", expanded=False):
            st.caption("Se suma al planning y a la capacidad de Control, pero no vuelve a entrar en las propuestas simuladas. Preparaciones EnProceso quedan fuera de la cartera futura, pero las del día actual sí ocupan capacidad HOY.")
            st.dataframe(
                comprometidos_resumen.rename(columns={"AgrupadorReal":"Agrupador real", "m3":"m³"}),
                hide_index=True, width="stretch",
                column_config={"m³": st.column_config.NumberColumn(format="%.2f")},
            )

    st.caption("La simulación propone únicamente cartera todavía libre. Si un cliente ya tiene pedidos comprometidos en una preparación pendiente, no se vuelve a sugerir para evitar partirlo. La referencia es 8 m³ por camioneta y 15 m³ por camión; el cliente siempre permanece completo.")

    pools = sim.get("pools", {})
    grupos_exp = sim.get("expresos_grupos", pd.DataFrame())
    tipos_veh = sim.get("tipos_vehiculos", {"Camioneta":{"capacidad_m3":8.0}, "Camion":{"capacidad_m3":15.0}})

    st.markdown("### 🚚 Cargas adicionales simuladas")
    st.caption("EXPRESOS muestra sólo cartera libre de los agrupadores configurados. Lo ya agrupado/no iniciado ya está incorporado arriba como carga comprometida; EnProceso no participa. RETIRA se mantiene independiente.")

    partes = []
    contador_global = 1

    # Panorama compacto: informa toda la deuda válida sin llenar la pantalla de controles.
    if grupos_exp is not None and not grupos_exp.empty:
        st.markdown("#### ⚡ Panorama de EXPRESOS")
        panorama = grupos_exp.copy()
        panorama["Agrupador"] = panorama["ZonaExpreso"].fillna("").astype(str)
        panorama = panorama[["Agrupador", "PlanificacionGrupo", "GrupoDespacho", "Clientes", "Pedidos", "Lineas", "Unidades", "m3", "AntiguedadMax"]]
        panorama = panorama.rename(columns={"PlanificacionGrupo":"Día", "GrupoDespacho":"Grupo", "Lineas":"Líneas", "m3":"m³", "AntiguedadMax":"Antig. máx."})
        st.dataframe(panorama, hide_index=True, width="stretch", column_config={
            "m³": st.column_config.NumberColumn(format="%.2f"),
            "Antig. máx.": st.column_config.NumberColumn(format="%d días"),
        })

        opciones_exp = grupos_exp.sort_values(["AntiguedadMax","m3"], ascending=[False,False]).reset_index(drop=True)
        mapa_exp = {
            f"{r['ZonaExpreso']} · {r['PlanificacionGrupo']} · Grupo {r['GrupoDespacho']}": str(r["ClaveAgrupacion"])
            for _, r in opciones_exp.iterrows()
        }
        e1,e2,e3,e4 = st.columns([3.0,1.5,1.1,1.2], vertical_alignment="bottom")
        sel_exp = e1.selectbox("Agrupador Expreso", options=list(mapa_exp.keys()), key="io_exp_selector")
        tipo_exp = e2.selectbox("Vehículo", options=["Camioneta","Camión"], key="io_exp_vehiculo")
        cant_exp = e3.number_input("Cantidad", min_value=0, max_value=10, value=0, step=1, key="io_exp_cantidad")
        clave_exp = mapa_exp.get(sel_exp)
        fila_sel = opciones_exp[opciones_exp["ClaveAgrupacion"].astype(str).eq(str(clave_exp))]
        if not fila_sel.empty:
            rr_exp=fila_sel.iloc[0]
            e4.info(f"{float(rr_exp['m3']):.1f} m³\n\n{int(rr_exp['AntiguedadMax'])} d máx.")
        if cant_exp and clave_exp:
            cap = 8.0 if tipo_exp == "Camioneta" else 15.0
            pref = "EXP CAM" if tipo_exp == "Camioneta" else "EXP CAMIÓN"
            asg = simular_camionetas_clientes(pools.get("EXPRESOS", pd.DataFrame()), int(cant_exp), cap, pref, clave_exp, contador_global, tipo_exp)
            if not asg.empty:
                partes.append(asg); contador_global += int(asg["NumeroCamioneta"].nunique())
    else:
        st.info("No hay carga pendiente en CABA SUR, CABA SUR II o CABA NORTE para simular.")

    # RETIRA normal ya está comprometido en la jornada actual. Sólo Full Loza se mueve desde el calendario.
    st.markdown("#### 🏷️ RETIRA")
    st.caption("RETIRA normal ya ocupa automáticamente la capacidad de HOY. Los RETIRA que califican como Full Loza se programan desde el calendario semanal y no se agregan manualmente acá.")

    st.markdown("#### 📦 Otros canales")
    od1,od2,oe1,oe2,rr = st.columns([1.4,1.4,1.4,1.4,1.0])
    n_dia_cam = od1.number_input("DIARIOS · Camionetas",0,10,0,1,key="io_dia_cam")
    n_dia_trk = od2.number_input("DIARIOS · Camiones",0,10,0,1,key="io_dia_trk")
    oe1.caption("EASY se agenda automáticamente 48 h antes")
    oe2.caption("No requiere carga manual")
    n_easy_cam = 0
    n_easy_trk = 0
    rr.write(""); rr.write("")
    if rr.button("↺ Resetear", use_container_width=True, key="io_sim_reset_v41"):
        for k in list(st.session_state.keys()):
            if str(k).startswith(("io_exp_","io_ret_","io_dia_","io_easy_")):
                st.session_state[k]=0
        st.rerun()

    for canal, cant, cap, pref, tipo in [
        ("DIARIOS",n_dia_cam,8.0,"DIA CAM","Camioneta"),("DIARIOS",n_dia_trk,15.0,"DIA CAMIÓN","Camión"),
        ("EASY",n_easy_cam if easy_activo else 0,8.0,"EASY CAM","Camioneta"),("EASY",n_easy_trk if easy_activo else 0,15.0,"EASY CAMIÓN","Camión")]:
        if cant:
            poolx=pools.get(canal,pd.DataFrame()).copy()
            if partes and not poolx.empty:
                usados=set(pd.concat(partes,ignore_index=True).loc[lambda d:d["Canal"].eq(canal),"ClienteCodigo"].astype(str))
                poolx=poolx[~poolx["ClienteCodigo"].astype(str).isin(usados)].copy()
            asg=simular_camionetas_clientes(poolx,int(cant),cap,pref,None,contador_global,tipo)
            if not asg.empty:
                partes.append(asg); contador_global += int(asg["NumeroCamioneta"].nunique())

    asignadas = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    add_lineas = int(asignadas.groupby(["Canal","ClaveAgrupacion","ClienteCodigo"])["Lineas"].first().sum()) if not asignadas.empty else 0
    add_unidades = int(asignadas.groupby(["Canal","ClaveAgrupacion","ClienteCodigo"])["Unidades"].first().sum()) if not asignadas.empty else 0
    add_m3 = float(asignadas.groupby(["Canal","ClaveAgrupacion","ClienteCodigo"])["m3"].first().sum()) if not asignadas.empty else 0.0
    add_pedidos = int(asignadas.groupby(["Canal","ClaveAgrupacion","ClienteCodigo"])["CantidadPedidos"].first().sum()) if not asignadas.empty else 0
    total_lineas_sim = base_lineas + add_lineas
    total_m3_sim = base_m3 + add_m3
    capacidad = int(io["capacidad_lineas"])
    uso_control = total_lineas_sim / capacidad * 100 if capacidad else 0

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Planning", f"{_fmt(base_pedidos + add_pedidos)} pedidos", f"+{_fmt(add_pedidos)} simulados")
    k2.metric("Líneas", _fmt(total_lineas_sim), f"+{_fmt(add_lineas)}")
    k3.metric("Unidades", _fmt(base_unidades + add_unidades), f"+{_fmt(add_unidades)}")
    k4.metric("Volumen", f"{_fmt(total_m3_sim,2)} m³", f"{_fmt(total_m3_sim/8,2)} cam. eq.")
    k5.metric("Capacidad Control", f"{_fmt(uso_control,1)}%", f"{_fmt(total_lineas_sim)} / {_fmt(capacidad)} líneas")

    if total_lineas_sim > capacidad:
        st.error(f"🔴 El planning simulado supera la capacidad base de Control en **{_fmt(total_lineas_sim-capacidad)} líneas**.")
    elif asignadas.empty:
        st.warning("🟡 Planning base cargado. Agregá una camioneta o camión en el grupo/canal que quieras simular.")
    else:
        st.success(f"🟢 Planning dentro de capacidad. Quedan **{_fmt(capacidad-total_lineas_sim)} líneas** de margen estimado en Control.")

    if not asignadas.empty:
        resumen_cam=(asignadas.groupby(["Canal","ClaveAgrupacion","Camioneta","NumeroCamioneta","TipoVehiculo","CapacidadVehiculoM3"],as_index=False)
                     .agg(Clientes=("ClienteCodigo","nunique"),Pedidos=("CantidadPedidos","sum"),Líneas=("Lineas","sum"),Unidades=("Unidades","sum"),m3=("m3","sum")))
        resumen_cam["Ocupación"]=(resumen_cam["m3"]/resumen_cam["CapacidadVehiculoM3"]*100).round(1)
        st.markdown("#### Camionetas / camiones simulados")
        st.dataframe(resumen_cam[["Canal","ClaveAgrupacion","Camioneta","TipoVehiculo","Clientes","Pedidos","Líneas","Unidades","m3","CapacidadVehiculoM3","Ocupación"]],hide_index=True,width="stretch",
            column_config={"m3":st.column_config.NumberColumn("m³",format="%.2f"),"CapacidadVehiculoM3":st.column_config.NumberColumn("Capacidad ref. m³",format="%.1f"),"Ocupación":st.column_config.ProgressColumn(format="%.1f%%",min_value=0,max_value=max(150,float(resumen_cam["Ocupación"].max())))})
        with st.expander("🔎 Ver clientes y pedidos incluidos en la simulación",expanded=False):
            det=asignadas[["Canal","ClaveAgrupacion","Camioneta","TipoVehiculo","ClienteCodigo","ClienteDescripcion","CantidadPedidos","Pedidos","AntiguedadMax","Lineas","Unidades","m3"]].copy()
            det=det.rename(columns={"CantidadPedidos":"Cant. pedidos","AntiguedadMax":"Antig. máx.","m3":"m³"})
            st.dataframe(det,hide_index=True,width="stretch")

    st.markdown("---")

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("📋 Cartera total", f"{_fmt(io['carga_lineas'])} líneas", f"{_fmt(io['carga_unidades'])} unidades")
    c2.metric("📦 Volumen cartera", f"{_fmt(io['carga_m3'],1)} m³", f"{_fmt(io['carga_m3']/8,1)} camionetas eq.")
    c3.metric("🎯 Capacidad Control", f"{_fmt(io['capacidad_lineas'])} líneas/día", f"{io['personas_control']} controles fijos")
    c4.metric("📅 Zona HOY", f"{_fmt(io['lineas_hoy'])} líneas", "según FrecuenciaPreparacion")
    c5.metric("🟢 Margen HOY" if io['margen_hoy'] >= 0 else "🔴 Déficit HOY", f"{_fmt(abs(io['margen_hoy']))} líneas", "antes de Expresos / Diarios")

    st.info(f"🧭 **Lectura operativa:** {io['accion']}")

    _titulo_descargas("📅 Planificación por zonas", io["exports"]["zonas_resumen"], io["exports"]["zonas_detalle"], "Zonas")
    st.caption("Cada fila representa la demanda pendiente por día de ENTREGA. 'Preparación' indica qué jornada debe atacarse. La fila 🎯 HOY es el objetivo operativo actual.")
    _tabla(io["zonas"])

    _titulo_descargas("🚚 Expresos y Diarios", io["exports"]["flex_resumen"], io["exports"]["flex_detalle"], "Expresos_Diarios")
    st.caption("Carga flexible. Regla de prioridad para aprovechar el margen: **EXPRESOS primero**, luego DIARIOS. El adelanto de otra zona queda para una etapa posterior.")
    _tabla(io["flexibles"], antig=True)

    _titulo_descargas("🚽 Sanitarios / Full Loza (>6 pallets INO/BID o ≥10 PDU; PDU120 excluido)", io["exports"]["sanitarios_resumen"], io["exports"]["sanitarios_detalle"], "Sanitarios_Full_Loza")
    st.caption("Demanda dimensionada de forma independiente para entender el peso real de la célula de Loza/Sanitarios.")
    _tabla(io["sanitarios"])

    _titulo_descargas("🏬 EASY", io["exports"]["easy_resumen"], io["exports"]["easy_detalle"], "EASY")
    estado = "🟢 ON · participa de la planificación" if easy_activo else "⚫ OFF · excluido de la planificación general"
    st.caption(estado + ". La tabla siempre queda visible para dimensionar su demanda.")
    _tabla(io["easy"], antig=True)

    with st.expander("👥 Nómina y supuestos del modelo"):
        if io["dotacion"]["personal"].empty:
            st.warning("No se pudo leer Maestro Personal. Se usa fallback de 3 controles.")
        else:
            st.dataframe(io["dotacion"]["personal"], hide_index=True, width="stretch")
        st.caption("Capacidad histórica Feb–Sep 2026. Líneas = KPI principal. Camionetas = equivalente volumétrico m³ / 8.")
