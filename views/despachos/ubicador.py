from __future__ import annotations

import pandas as pd
import streamlit as st

from models.despachos.ubicaciones import construir_base_contenedores_controlados
from utils.despachos.ubicaciones_store import (
    leer_ubicaciones,
    guardar_ubicacion,
    guardar_ubicaciones_lote,
    liberar_contenedores,
    reiniciar_ubicaciones,
    quitar_ubicacion,
    normalizar_ubicacion,
)


def _base_enriquecida(df_filtrar, df_tareas, tabla) -> pd.DataFrame:
    base = construir_base_contenedores_controlados(df_filtrar, df_tareas, tabla)
    ubic = leer_ubicaciones()
    if not ubic.empty:
        base = base.merge(ubic, on="Contenedor", how="left", validate="one_to_one")
    else:
        base["Ubicacion"] = ""
        base["FechaUbicacion"] = ""
        base["Usuario"] = ""
    for c in ["Ubicacion", "FechaUbicacion", "Usuario"]:
        base[c] = base[c].fillna("").astype(str)

    # Ventana operativa:
    # últimos 7 días corridos incluyendo hoy.
    # Si un contenedor sigue ubicado, permanece vigente aunque sea anterior.
    fecha_control = pd.to_datetime(
        base["FechaControl"],
        errors="coerce",
        dayfirst=True,
    )

    # Para pruebas usamos como referencia la última fecha real disponible
    # en Filtrar Preparación. Así el rango no depende del reloj del servidor.
    ultima_fecha = fecha_control.max()
    if pd.notna(ultima_fecha):
        hasta = ultima_fecha.normalize()
        desde = hasta - pd.Timedelta(days=6)
        vigente_7_dias = fecha_control.dt.normalize().between(
            desde,
            hasta,
            inclusive="both",
        )
    else:
        vigente_7_dias = pd.Series(False, index=base.index)

    # Primero limitamos el universo operativo a los últimos 7 días.
    # Una ubicación activa nunca desaparece por antigüedad.
    sigue_ubicado = base["Ubicacion"].str.strip().ne("")
    base_7d = base.loc[vigente_7_dias].copy()
    base_ubicada = base.loc[sigue_ubicado].copy()

    # Los nombres de agrupador se reutilizan. Para cada agrupador vigente
    # conservamos solamente su ÚLTIMA APARICIÓN (último día de control).
    if not base_7d.empty:
        fecha_7d = pd.to_datetime(
            base_7d["FechaControl"],
            errors="coerce",
            dayfirst=True,
        )
        base_7d["_FechaAgrupacion"] = fecha_7d.dt.normalize()

        ultima_por_agrupador = (
            base_7d.groupby("Agrupador")["_FechaAgrupacion"]
            .transform("max")
        )

        base_7d = base_7d.loc[
            base_7d["_FechaAgrupacion"].eq(ultima_por_agrupador)
        ].drop(columns=["_FechaAgrupacion"])

    # Los contenedores ya ubicados se conservan siempre hasta liberar salida.
    base = pd.concat(
        [base_7d, base_ubicada],
        ignore_index=True,
        sort=False,
    ).drop_duplicates(
        subset=["Contenedor"],
        keep="last",
    )

    return base.sort_values(
        ["FechaControl", "Contenedor"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _ficha(fila: pd.Series) -> None:
    st.markdown(f"### 📦 {fila['Contenedor']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pedido", str(fila.get("Pedido", "")))
    c2.metric("Bultos controlados", int(fila.get("BultosControladosPedido", 0) or 0))
    c3.metric("Ubicación actual", str(fila.get("Ubicacion", "")) or "SIN UBICAR")
    c4.metric("Agrupador", str(fila.get("Agrupador", "")) or "-")
    st.caption(
        f"Cliente: {fila.get('ClienteDescripcion', '')}  ·  "
        f"Control: {fila.get('FechaControl', '')}"
    )


def _base_controlados_completa(df_filtrar_preparacion, df_informe_tareas, tabla):
    """Base completa: se usa solamente para validar si el contenedor fue controlado."""
    return construir_base_contenedores_controlados(
        df_filtrar_preparacion=df_filtrar_preparacion,
        df_informe_tareas=df_informe_tareas,
        tabla_operativa=tabla,
    )


def _limpiar_sesion_pallet() -> None:
    """Limpia completamente la carga temporal del pallet actual."""
    for clave in (
        "ubicador_sesion_activa",
        "ubicador_ubicacion_sesion",
        "ubicador_bultos_sesion",
        "ubicador_base_congelada",
        "ubicador_controlados_congelados",
        "ubicador_agrupador_activo",
    ):
        st.session_state.pop(clave, None)


def _resumen_agrupador(
    base: pd.DataFrame,
    agrupador: str,
    bultos_sesion: list[str],
) -> tuple[pd.DataFrame, int, int, int]:
    grupo = base.loc[
        base["Agrupador"].fillna("").astype(str).eq(str(agrupador))
    ].copy()

    total = int(grupo["Contenedor"].nunique())
    confirmados = set(
        grupo.loc[grupo["Ubicacion"].fillna("").ne(""), "Contenedor"]
        .astype(str)
        .tolist()
    )
    sesion = set(str(c) for c in bultos_sesion)
    cargados = confirmados.union(sesion)
    pendientes = max(total - len(cargados), 0)

    filas = []
    for pedido, detalle in grupo.groupby("Pedido", dropna=False):
        contenedores = set(detalle["Contenedor"].astype(str))
        cargados_pedido = len(contenedores.intersection(cargados))
        en_pallet = len(contenedores.intersection(sesion))
        filas.append({
            "Pedido": str(pedido),
            "Cliente": str(detalle["ClienteDescripcion"].iloc[0]),
            "Total bultos": len(contenedores),
            "Cargados": cargados_pedido,
            "En este pallet": en_pallet,
            "Pendientes": max(len(contenedores) - cargados_pedido, 0),
        })

    resumen = pd.DataFrame(filas)
    if not resumen.empty:
        resumen = resumen.sort_values(
            ["Pendientes", "Pedido"],
            ascending=[False, True],
        ).reset_index(drop=True)

    return resumen, total, len(cargados), pendientes


def _tabla_pendientes_agrupadores(base: pd.DataFrame) -> pd.DataFrame:
    """Agrupadores vigentes y cantidad de bultos todavía sin ubicar."""
    if base.empty:
        return pd.DataFrame()

    filas = []
    for agrupador, grupo in base.groupby("Agrupador", dropna=False):
        agrupador = str(agrupador).strip()
        if not agrupador:
            continue

        total = int(grupo["Contenedor"].astype(str).nunique())
        ubicados = int(
            grupo.loc[
                grupo["Ubicacion"].fillna("").str.strip().ne(""),
                "Contenedor",
            ].astype(str).nunique()
        )
        pendientes = max(total - ubicados, 0)
        if pendientes <= 0:
            continue

        fechas = pd.to_datetime(
            grupo["FechaControl"],
            errors="coerce",
            dayfirst=True,
        )
        ultima = fechas.max()
        fecha_txt = ultima.strftime("%d/%m/%Y") if pd.notna(ultima) else ""

        filas.append({
            "Agrupador": agrupador,
            "Fecha agrupación": fecha_txt,
            "Pedidos": int(grupo["Pedido"].astype(str).nunique()),
            "Total bultos": total,
            "Ubicados": ubicados,
            "Pendientes": pendientes,
        })

    if not filas:
        return pd.DataFrame()

    return pd.DataFrame(filas).sort_values(
        ["Fecha agrupación", "Agrupador"],
        ascending=[False, True],
    ).reset_index(drop=True)


def _render_ubicar(base: pd.DataFrame, base_controlados: pd.DataFrame) -> None:
    st.subheader("📦 Carga de pallet")
    st.caption(
        "Elegí la posición física, escaneá todos los bultos del pallet "
        "y confirmá recién al finalizar."
    )

    sesion_activa = bool(st.session_state.get("ubicador_sesion_activa", False))

    # ----------------------------------------------------------
    # PASO 1 · INICIAR PALLET
    # ----------------------------------------------------------
    if not sesion_activa:
        with st.form("form_iniciar_pallet", clear_on_submit=True):
            destino = st.text_input(
                "Ubicación física del pallet",
                placeholder="D001",
            )
            iniciar = st.form_submit_button(
                "▶️ Iniciar carga de pallet",
                type="primary",
                width="stretch",
            )

        if iniciar:
            try:
                destino = normalizar_ubicacion(destino)
                st.session_state["ubicador_sesion_activa"] = True
                st.session_state["ubicador_ubicacion_sesion"] = destino
                st.session_state["ubicador_bultos_sesion"] = []
                st.session_state.pop("ubicador_agrupador_activo", None)

                # Congelamos la información operativa durante toda la carga.
                st.session_state["ubicador_base_congelada"] = base.copy()
                st.session_state["ubicador_controlados_congelados"] = base_controlados.copy()
                st.rerun()
            except Exception as e:
                st.error(str(e))

        st.divider()
        st.markdown("### 📋 Pendiente de ubicar")
        pendientes_df = _tabla_pendientes_agrupadores(base)
        if pendientes_df.empty:
            st.success("No hay agrupadores vigentes con bultos pendientes.")
        else:
            st.dataframe(
                pendientes_df,
                hide_index=True,
                width="stretch",
            )

            pendientes_contenedores = base.loc[
                base["Ubicacion"].fillna("").str.strip().eq(""),
                ["Agrupador", "FechaControl", "Pedido", "ClienteDescripcion", "Contenedor"],
            ].copy()
            pendientes_contenedores = pendientes_contenedores.rename(
                columns={"FechaControl": "Fecha control", "ClienteDescripcion": "Cliente"}
            ).sort_values(["Agrupador", "Pedido", "Contenedor"])

            st.download_button(
                "⬇️ Descargar contenedores pendientes para pruebas",
                data=pendientes_contenedores.to_csv(
                    index=False, encoding="utf-8-sig"
                ).encode("utf-8-sig"),
                file_name="contenedores_pendientes_ubicador.csv",
                mime="text/csv",
                width="stretch",
            )

        st.divider()
        with st.expander("🧪 Herramientas de prueba"):
            st.warning(
                "Reiniciar pruebas elimina TODAS las ubicaciones cargadas "
                "en el Ubicador. No modifica WMS ni Filtrar Preparación."
            )
            if st.button(
                "🗑️ REINICIAR TODAS LAS UBICACIONES",
                type="secondary",
                width="stretch",
                key="reiniciar_todas_ubicaciones",
            ):
                st.session_state["confirmar_reinicio_total"] = True
                st.rerun()

            if st.session_state.get("confirmar_reinicio_total", False):
                st.error("¿Confirmar borrado total de las ubicaciones de prueba?")
                c1, c2 = st.columns(2)
                if c1.button(
                    "✅ Sí, borrar todo",
                    type="primary",
                    width="stretch",
                    key="confirmar_reinicio_total_si",
                ):
                    reiniciar_ubicaciones()
                    _limpiar_sesion_pallet()
                    st.session_state.pop("confirmar_reinicio_total", None)
                    st.session_state.pop("ubicador_posicion_mapa", None)
                    st.toast("Ubicaciones de prueba reiniciadas.", icon="🧪")
                    st.rerun()
                if c2.button(
                    "Cancelar",
                    width="stretch",
                    key="confirmar_reinicio_total_no",
                ):
                    st.session_state.pop("confirmar_reinicio_total", None)
                    st.rerun()
        return

    # Durante una carga usamos siempre la foto congelada del inicio.
    base_sesion = st.session_state.get("ubicador_base_congelada")
    if not isinstance(base_sesion, pd.DataFrame) or base_sesion.empty:
        base_sesion = base.copy()
        st.session_state["ubicador_base_congelada"] = base_sesion

    base_controlados_sesion = st.session_state.get("ubicador_controlados_congelados")
    if not isinstance(base_controlados_sesion, pd.DataFrame) or base_controlados_sesion.empty:
        base_controlados_sesion = base_controlados.copy()
        st.session_state["ubicador_controlados_congelados"] = base_controlados_sesion

    ubicacion = str(st.session_state.get("ubicador_ubicacion_sesion", ""))
    bultos_sesion = list(st.session_state.get("ubicador_bultos_sesion", []))
    agrupador = str(st.session_state.get("ubicador_agrupador_activo", "")).strip()

    k1, k2, k3 = st.columns(3)
    k1.metric("📍 Posición", ubicacion)
    k2.metric("📦 En este pallet", len(bultos_sesion))
    k3.metric("🚚 Agrupador", agrupador or "Se define con el 1° bulto")

    # ----------------------------------------------------------
    # PASO 2 · ESCANEO CONTINUO
    # ----------------------------------------------------------
    with st.form("form_scan_bulto_pallet", clear_on_submit=True):
        codigo = st.text_input(
            "Escanear contenedor",
            placeholder="Escaneá el bulto y presioná Enter...",
        )
        agregar = st.form_submit_button(
            "➕ Agregar bulto",
            type="primary",
            width="stretch",
        )

    if agregar:
        codigo = str(codigo).strip()

        if not codigo.isdigit():
            st.error("El código debe ser un contenedor numérico controlado.")
        elif codigo not in set(base_controlados_sesion["Contenedor"].astype(str)):
            st.error("El contenedor no figura como controlado en Filtrar Preparación.")
        elif codigo not in set(base_sesion["Contenedor"].astype(str)):
            fila_hist = base_controlados_sesion.loc[
                base_controlados_sesion["Contenedor"].astype(str).eq(codigo)
            ].iloc[0]
            agrupador_hist = str(fila_hist.get("Agrupador", "")).strip()
            fecha_hist = fila_hist.get("FechaControl", "")
            st.warning(
                f"El contenedor {codigo} está CONTROLADO, pero pertenece a una "
                f"aparición anterior de {agrupador_hist or 'su agrupador'} "
                f"({fecha_hist}) y no forma parte de la carga vigente."
            )
        elif codigo in bultos_sesion:
            st.warning("Ese contenedor ya fue escaneado en este pallet.")
        else:
            fila = base_sesion.loc[
                base_sesion["Contenedor"].astype(str).eq(codigo)
            ].iloc[0]

            ubicacion_actual = str(fila.get("Ubicacion", "")).strip()
            agrupador_bulto = str(fila.get("Agrupador", "")).strip()

            if ubicacion_actual:
                st.error(
                    f"El contenedor {codigo} ya está ubicado en "
                    f"{ubicacion_actual}. Quitá o corregí esa ubicación antes de cargarlo."
                )
            elif not agrupador_bulto:
                st.error("El contenedor no tiene Agrupador identificado.")
            elif agrupador and agrupador_bulto != agrupador:
                st.error(
                    f"⛔ Este pallet está trabajando el agrupador {agrupador}. "
                    f"El bulto {codigo} pertenece a {agrupador_bulto}."
                )
            else:
                if not agrupador:
                    agrupador = agrupador_bulto
                    st.session_state["ubicador_agrupador_activo"] = agrupador

                bultos_sesion.append(codigo)
                st.session_state["ubicador_bultos_sesion"] = bultos_sesion
                st.rerun()

    # ----------------------------------------------------------
    # AVANCE Y PENDIENTES DEL AGRUPADOR
    # ----------------------------------------------------------
    if agrupador:
        resumen, total, cargados, pendientes = _resumen_agrupador(
            base_sesion,
            agrupador,
            bultos_sesion,
        )

        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Total agrupador", total)
        a2.metric("Cargados", cargados)
        a3.metric("Pendientes", pendientes)
        a4.metric("Avance", f"{cargados}/{total}" if total else "0/0")

        st.markdown("#### 📋 Pendientes por pedido")
        if resumen.empty:
            st.info("No hay pedidos para mostrar.")
        else:
            st.dataframe(
                resumen,
                hide_index=True,
                width="stretch",
            )

    if bultos_sesion:
        with st.expander(
            f"📦 Ver {len(bultos_sesion)} bultos de este pallet",
            expanded=False,
        ):
            detalle_sesion = base_sesion.loc[
                base_sesion["Contenedor"].astype(str).isin(bultos_sesion),
                ["Contenedor", "Pedido", "ClienteDescripcion", "Agrupador"],
            ].copy()
            st.dataframe(
                detalle_sesion,
                hide_index=True,
                width="stretch",
            )

    # ----------------------------------------------------------
    # PASO 3 · FINALIZAR PALLET
    # ----------------------------------------------------------
    st.divider()
    c1, c2 = st.columns([3, 1])

    finalizar = c1.button(
        f"✅ FINALIZAR PALLET — {len(bultos_sesion)} bultos",
        type="primary",
        width="stretch",
        disabled=not bultos_sesion,
    )
    reiniciar = c2.button(
        "🔄 REINICIAR CARGA",
        width="stretch",
    )

    if reiniciar:
        _limpiar_sesion_pallet()
        st.rerun()

    if finalizar:
        try:
            guardar_ubicaciones_lote(
                bultos_sesion,
                ubicacion,
            )

            # Calculamos si el agrupador quedó completo.
            resumen, total, cargados_antes, pendientes_antes = _resumen_agrupador(
                base_sesion,
                agrupador,
                bultos_sesion,
            )
            pendientes = max(total - cargados_antes, 0)

            # Finalizar un pallet nunca bloquea el siguiente.
            _limpiar_sesion_pallet()

            if pendientes > 0:
                st.success(
                    f"✅ {len(bultos_sesion)} bultos confirmados en {ubicacion}. "
                    f"{agrupador} queda con {pendientes} bultos pendientes."
                )
            else:
                st.success(
                    f"✅ Agrupador {agrupador} COMPLETO. "
                    f"{len(bultos_sesion)} bultos confirmados en {ubicacion}."
                )

            st.rerun()
        except Exception as e:
            st.error(str(e))


def _estado_agrupadores(base: pd.DataFrame) -> pd.DataFrame:
    """Resumen operativo de agrupadores con bultos ubicados."""
    if base.empty:
        return pd.DataFrame()

    filas = []
    for agrupador, grupo in base.groupby("Agrupador", dropna=False):
        agrupador = str(agrupador).strip()
        if not agrupador:
            continue

        contenedores = set(grupo["Contenedor"].astype(str))
        ubicados_df = grupo.loc[grupo["Ubicacion"].fillna("").ne("")].copy()
        ubicados = set(ubicados_df["Contenedor"].astype(str))

        if not ubicados:
            continue

        posiciones = sorted({
            str(x).strip()
            for x in ubicados_df["Ubicacion"].tolist()
            if str(x).strip()
        })

        filas.append({
            "Agrupador": agrupador,
            "Pedidos": int(grupo["Pedido"].nunique()),
            "TotalBultos": len(contenedores),
            "Ubicados": len(ubicados),
            "Pendientes": max(len(contenedores) - len(ubicados), 0),
            "Posiciones": posiciones,
            "Completo": len(contenedores) > 0 and len(ubicados) == len(contenedores),
        })

    return pd.DataFrame(filas)


def _inyectar_estilo_mapa() -> None:
    st.markdown(
        """
        <style>
        /* Posiciones completas: verde suave sin perder legibilidad */
        div[data-testid="stButton"] button[kind="secondary"]:has(span.map-completo-marker) {
            background: rgba(35, 134, 54, 0.24) !important;
            border-color: rgba(63, 185, 80, 0.75) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_mapa(base: pd.DataFrame) -> None:
    st.subheader("🗺️ Mapa de despacho")

    ubicados = base.loc[base["Ubicacion"].ne("")].copy()
    estados = _estado_agrupadores(base)

    completos = set()
    if not estados.empty:
        completos = set(
            estados.loc[estados["Completo"], "Agrupador"]
            .astype(str)
            .tolist()
        )

    resumen = (
        ubicados.groupby("Ubicacion")
        .agg(Bultos=("Contenedor", "nunique"), Pedidos=("Pedido", "nunique"))
        .reset_index()
        if not ubicados.empty
        else pd.DataFrame(columns=["Ubicacion", "Bultos", "Pedidos"])
    )
    mapa = resumen.set_index("Ubicacion").to_dict("index") if not resumen.empty else {}

    # Agrupadores por posición y estado visual.
    agrupadores_posicion = {}
    posicion_completa = {}
    if not ubicados.empty:
        for posicion, detalle in ubicados.groupby("Ubicacion"):
            ags = sorted({
                str(x).strip()
                for x in detalle["Agrupador"].tolist()
                if str(x).strip()
            })
            agrupadores_posicion[str(posicion)] = ags
            posicion_completa[str(posicion)] = bool(ags) and all(a in completos for a in ags)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Posiciones", 60)
    k2.metric("Con contenido", len(mapa))
    k3.metric("Libres", 60 - len(mapa))
    k4.metric("Bultos ubicados", int(ubicados["Contenedor"].nunique()))

    # Tarjetas de posición. El nombre del agrupador se muestra arriba.
    for inicio in range(1, 61, 12):
        cols = st.columns(12)
        for offset, col in enumerate(cols):
            numero = inicio + (11 - offset)
            codigo = f"D{numero:03d}"
            info = mapa.get(codigo, {})
            bultos = int(info.get("Bultos", 0))
            pedidos = int(info.get("Pedidos", 0))
            ags = agrupadores_posicion.get(codigo, [])

            with col:
                if ags:
                    titulo = " / ".join(ags)
                    st.caption(f"🚚 {titulo}")
                else:
                    st.caption(" ")

                if bultos:
                    etiqueta = f"{codigo}\n📦 {bultos} · 📋 {pedidos}"
                    if posicion_completa.get(codigo, False):
                        # Primary da una señal verde/activa según el tema,
                        # manteniendo texto e iconos legibles.
                        tipo = "primary"
                    else:
                        tipo = "secondary"
                else:
                    etiqueta = f"{codigo}\nLIBRE"
                    tipo = "secondary"

                if st.button(
                    etiqueta,
                    key=f"mapa_{codigo}",
                    width="stretch",
                    type=tipo,
                ):
                    st.session_state["ubicador_posicion_mapa"] = codigo

    seleccion = st.session_state.get("ubicador_posicion_mapa", "")
    if seleccion:
        st.markdown(f"### 📍 {seleccion}")
        detalle = ubicados.loc[ubicados["Ubicacion"].eq(seleccion)].copy()
        if detalle.empty:
            st.info("Posición libre.")
        else:
            resumen_pedidos = (
                detalle.groupby(
                    ["Pedido", "ClienteDescripcion", "Agrupador"],
                    dropna=False,
                )
                .agg(Bultos=("Contenedor", "nunique"))
                .reset_index()
            )
            st.dataframe(
                resumen_pedidos,
                hide_index=True,
                width="stretch",
            )
            with st.expander("Ver contenedores"):
                st.dataframe(
                    detalle[
                        [
                            "Contenedor",
                            "Pedido",
                            "ClienteDescripcion",
                            "FechaUbicacion",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                )

    # ----------------------------------------------------------
    # AGRUPADORES VIGENTES
    # ----------------------------------------------------------
    st.divider()
    st.markdown("### 🚚 Agrupadores vigentes")
    st.caption(
        "Los agrupadores completos pueden marcarse como salida confirmada "
        "para liberar sus posiciones."
    )

    if estados.empty:
        st.info("No hay agrupadores con mercadería ubicada.")
        return

    estados = estados.sort_values(
        ["Completo", "Pendientes", "Agrupador"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    for _, fila in estados.iterrows():
        agrupador = str(fila["Agrupador"])
        completo = bool(fila["Completo"])
        estado_txt = "🟢 COMPLETO" if completo else "🟠 EN CARGA"
        posiciones_txt = " · ".join(fila["Posiciones"]) or "-"

        with st.container(border=True):
            h1, h2, h3, h4, h5 = st.columns([2.2, 1, 1, 1.5, 1.5])
            h1.markdown(f"**🚚 {agrupador}**")
            h2.metric("Pedidos", int(fila["Pedidos"]))
            h3.metric("Bultos", f'{int(fila["Ubicados"])}/{int(fila["TotalBultos"])}')
            h4.markdown(f"**{estado_txt}**")
            h4.caption(f"📍 {posiciones_txt}")

            if completo:
                if h5.button(
                    "🚚 Confirmar salida",
                    key=f"liberar_{agrupador}",
                    type="primary",
                    width="stretch",
                ):
                    st.session_state["ubicador_confirmar_salida"] = agrupador
                    st.rerun()
            else:
                h5.metric("Pendientes", int(fila["Pendientes"]))

    confirmar = str(
        st.session_state.get("ubicador_confirmar_salida", "")
    ).strip()

    if confirmar:
        fila_conf = estados.loc[
            estados["Agrupador"].astype(str).eq(confirmar)
        ]

        if fila_conf.empty:
            st.session_state.pop("ubicador_confirmar_salida", None)
        else:
            datos = fila_conf.iloc[0]
            st.warning(
                f"¿Confirmar salida de **{confirmar}**? "
                f"Se liberarán {int(datos['Ubicados'])} bultos "
                f"de {int(datos['Pedidos'])} pedidos en "
                f"{' · '.join(datos['Posiciones'])}."
            )

            c1, c2 = st.columns(2)
            if c1.button(
                "✅ Sí, confirmar salida y liberar espacios",
                key=f"confirmar_salida_{confirmar}",
                type="primary",
                width="stretch",
            ):
                contenedores = (
                    base.loc[
                        base["Agrupador"].astype(str).eq(confirmar)
                        & base["Ubicacion"].fillna("").ne(""),
                        "Contenedor",
                    ]
                    .astype(str)
                    .unique()
                    .tolist()
                )
                liberados = liberar_contenedores(contenedores)
                st.session_state.pop("ubicador_confirmar_salida", None)
                st.session_state.pop("ubicador_posicion_mapa", None)
                st.toast(
                    f"{confirmar}: {liberados} bultos liberados.",
                    icon="🚚",
                )
                st.rerun()

            if c2.button(
                "Cancelar",
                key=f"cancelar_salida_{confirmar}",
                width="stretch",
            ):
                st.session_state.pop("ubicador_confirmar_salida", None)
                st.rerun()


def _render_buscar(base: pd.DataFrame) -> None:
    st.subheader("🔎 Buscar")
    q = st.text_input("Pedido, contenedor, cliente o agrupador", placeholder="Ej.: 216050 / 50926092559979")
    qn = str(q).strip().upper()
    if not qn:
        return

    mascara = (
        base["Pedido"].astype(str).str.upper().str.contains(qn, regex=False)
        | base["Contenedor"].astype(str).str.upper().str.contains(qn, regex=False)
        | base["ClienteDescripcion"].astype(str).str.upper().str.contains(qn, regex=False)
        | base["Agrupador"].astype(str).str.upper().str.contains(qn, regex=False)
    )
    res = base.loc[mascara].copy()
    if res.empty:
        st.warning("No se encontraron resultados.")
        return

    pedidos = res["Pedido"].nunique()
    contenedores = res["Contenedor"].nunique()
    ubicados = res.loc[res["Ubicacion"].ne(""), "Contenedor"].nunique()
    c1, c2, c3 = st.columns(3)
    c1.metric("Pedidos", pedidos)
    c2.metric("Contenedores", contenedores)
    c3.metric("Ubicados", f"{ubicados}/{contenedores}")

    st.dataframe(
        res[["Pedido", "ClienteDescripcion", "Contenedor", "Ubicacion", "Agrupador", "FechaControl"]]
        .sort_values(["Pedido", "Ubicacion", "Contenedor"]),
        hide_index=True,
        width="stretch",
    )


def render_ubicador_despachos(*, df_filtrar_preparacion: pd.DataFrame, df_informe_tareas: pd.DataFrame, tabla: pd.DataFrame) -> None:
    st.subheader("📍 Ubicador de despacho")
    st.caption("Ubicación física y virtual de contenedores controlados.")

    base_congelada = st.session_state.get("ubicador_base_congelada")
    controlados_congelados = st.session_state.get("ubicador_controlados_congelados")
    sesion_activa = bool(st.session_state.get("ubicador_sesion_activa", False))

    try:
        if sesion_activa and isinstance(base_congelada, pd.DataFrame) and not base_congelada.empty:
            base = base_congelada
        else:
            base = _base_enriquecida(df_filtrar_preparacion, df_informe_tareas, tabla)

        if sesion_activa and isinstance(controlados_congelados, pd.DataFrame) and not controlados_congelados.empty:
            base_controlados = controlados_congelados
        else:
            base_controlados = _base_controlados_completa(
                df_filtrar_preparacion, df_informe_tareas, tabla
            )
    except Exception as e:
        st.error("No se pudo construir la base del Ubicador.")
        st.exception(e)
        return

    vista = st.segmented_control(
        "Vista Ubicador",
        options=["📦 Ubicar", "🗺️ Mapa", "🔎 Buscar"],
        default="📦 Ubicar",
        key="vista_ubicador_despachos",
        label_visibility="collapsed",
    )

    if vista == "📦 Ubicar":
        _render_ubicar(base, base_controlados)
    elif vista == "🗺️ Mapa":
        _render_mapa(base)
    else:
        _render_buscar(base)
