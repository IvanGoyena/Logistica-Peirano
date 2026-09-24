from __future__ import annotations
import html
from io import BytesIO
import pandas as pd
import streamlit as st
from models.inteligencia_operativa import construir_inteligencia_operativa, simular_camionetas_clientes, OBJETIVO_CONTROL_DIARIO


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

    io = construir_inteligencia_operativa(
        datos_dashboard,
        tabla_detalle_dashboard,
        personal=tabla_personal,
        transmisiones=tabla_transmisiones,
        easy_activo=easy_activo,
    )
    if io.get("vacio"):
        st.info(io.get("mensaje")); return

    # ==========================================================
    # V5 — CALENDARIO SEMANAL DE CAPACIDAD
    # ==========================================================
    st.markdown("## 📅 Planning semanal de capacidad")
    st.caption("Planning maestro de preparación y entrega: Zona se agenda por cronograma; EASY toma la fecha del agrupador (EASY DD-MM) y reserva el 100% en el primer día de sus 48 h previas; RETIRA normal ocupa el día actual; RETIRA Full Loza y Expresos agrupados quedan movibles. Objetivo: 850 líneas L-V y 567 el sábado.")
    sem = io.get("calendario_semanal", {})
    cal = sem.get("calendario", pd.DataFrame()).copy()
    exp_agr = sem.get("expresos_agrupados", pd.DataFrame()).copy()
    ret_agr = sem.get("retira_agrupados", pd.DataFrame()).copy()

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

    if not cal.empty and exp_agr is not None and not exp_agr.empty:
        with st.expander("⚡ Ubicar camionetas Expresos ya agrupadas", expanded=True):
            for i, r in exp_agr.iterrows():
                nombre = str(r.get("AgrupadorReal", f"EXP {i+1}"))
                c1,c2,c3 = st.columns([3.4,1.3,1.8], vertical_alignment="center")
                c1.markdown(f"**{nombre}** · {_fmt(r.get('Pedidos',0))} pedidos · {_fmt(r.get('Líneas',0))} líneas · {_fmt(r.get('m³',0),2)} m³")
                key = "io_v56_exp_fecha_" + str(i)
                fecha_sel = c2.selectbox("Preparar", opciones_fecha, key=key, label_visibility="collapsed")
                c3.caption("No iniciado · movible")
                if fecha_sel != "Sin asignar":
                    fecha_obj = mapa_fechas[fecha_sel]
                    asignaciones[nombre] = fecha_obj.strftime("%Y-%m-%d")
                    mask_fecha = cal["Fecha"].eq(fecha_obj)
                    cal.loc[mask_fecha, "Expresos"] += float(r.get("Líneas",0))
                    if "Expresos Unid." in cal.columns:
                        cal.loc[mask_fecha, "Expresos Unid."] += float(r.get("Unidades",0))

    # Sólo RETIRA Full Loza queda movible. El RETIRA normal ya ocupa automáticamente HOY.
    if not cal.empty and ret_agr is not None and not ret_agr.empty:
        with st.expander("🚽 Ubicar RETIRA Full Loza", expanded=False):
            for i, r in ret_agr.iterrows():
                nombre = str(r.get("AgrupadorReal", f"RETIRA {i+1}"))
                c1,c2 = st.columns([4.5,1.5], vertical_alignment="center")
                c1.markdown(f"**{nombre}** · {_fmt(r.get('Pedidos',0))} pedidos · {_fmt(r.get('Líneas',0))} líneas")
                fecha_sel = c2.selectbox("Preparar", opciones_fecha, key=f"io_v56_ret_fecha_{i}", label_visibility="collapsed")
                if fecha_sel != "Sin asignar":
                    fecha_obj = mapa_fechas[fecha_sel]
                    mask_fecha = cal["Fecha"].eq(fecha_obj)
                    cal.loc[mask_fecha, "RETIRA"] += float(r.get("Líneas",0))
                    if "RETIRA Unid." in cal.columns:
                        cal.loc[mask_fecha, "RETIRA Unid."] += float(r.get("Unidades",0))

    if not cal.empty:
        cal["Total"] = cal[["Zona","EASY","Expresos","RETIRA"]].sum(axis=1).round(1)
        unid_cols = [c for c in ["Zona Unid.","EASY Unid.","Expresos Unid.","RETIRA Unid."] if c in cal.columns]
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

        # Gráfico de composición de líneas por canal.
        # IMPORTANTE: usamos etiquetas categóricas YA ordenadas por fecha.
        # Así evitamos que Streamlit interprete el eje como tiempo continuo y muestre horas.
        graf = cal[["Fecha","Zona","EASY","Expresos","RETIRA"]].copy()
        graf["Fecha"] = pd.to_datetime(graf["Fecha"], errors="coerce").dt.normalize()
        graf = graf[graf["Fecha"].notna()].sort_values("Fecha", kind="stable").reset_index(drop=True)

        dias_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
        # Prefijo numérico invisible para preservar estrictamente el orden cronológico
        # aun cuando Vega/Streamlit trate el índice como categoría.
        graf["Jornada"] = [
            f"{i:02d} · {dias_es.get(f.weekday(), '')} {f.strftime('%d/%m')}"
            for i, f in enumerate(graf["Fecha"])
        ]
        graf = graf.set_index("Jornada")[["Zona","EASY","Expresos","RETIRA"]]

        st.caption("**Carga planificada por canal — líneas · desde HOY hasta fin de la semana siguiente**")
        st.bar_chart(graf, use_container_width=True, height=260)

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
