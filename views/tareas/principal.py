from __future__ import annotations

import pandas as pd
import re
import streamlit as st

from models.tareas_modulo.contexto import construir_contexto_tareas
from models.tareas import sugerir_equipamiento_operativo
from utils.rendimiento import medir_tiempo, mostrar_info_dataframe
from utils.tareas.carga import cargar_fuentes_tareas, invalidar_cache_tareas
from utils.tareas.formatos import preparar_tabla_operativa_visual, resaltar_carro
from utils.tareas.graficos import grafico_avance_despacho, grafico_sectorizaciones
from utils.tareas.estilo_pantalla import (
    aplicar_estilo_pantalla,
    perfil_visual,
    selector_modo_visual,
)



def _fmt_entero(valor: object) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _detalle_control_finalizado(contexto: dict[str, object]) -> str:
    resumen = contexto["resumen"]
    control = contexto.get("control_dia_anterior", {})

    base = (
        f"Hoy {_fmt_entero(resumen['CarrosFinalizadosHoy'])} · "
        f"Ayer {_fmt_entero(resumen['CarrosFinalizadosAyer'])}"
    )

    if not control or not control.get("disponible"):
        return base + "<br>Control histórico sin datos"

    fecha = control.get("fecha")
    fecha_visible = (
        pd.Timestamp(fecha).strftime("%d/%m")
        if fecha is not None and pd.notna(fecha)
        else "Último cierre"
    )
    etiqueta_fecha = (
        "Ayer"
        if control.get("es_dia_calendario_anterior")
        else fecha_visible
    )

    return (
        base
        + "<br>"
        + f"📦 {etiqueta_fecha}: "
        + f"{_fmt_entero(control.get('unidades', 0))} unidades cerradas"
    )


def _render_kpis(contexto: dict[str, object]) -> None:
    resumen = contexto["resumen"]
    pendiente_pick = contexto["pendiente_pick"]

    tarjetas = [
        (
            "📦 Pedidos pendientes",
            _fmt_entero(contexto["pedidos_pendientes"]),
            f"{_fmt_entero(contexto['unidades_pendientes'])} unidades",
        ),
        (
            "📥 Pendiente de pickear",
            _fmt_entero(pendiente_pick["Preparaciones"]),
            f"{_fmt_entero(pendiente_pick['Unidades'])} unidades",
        ),
        (
            "🛒 Carros en curso",
            _fmt_entero(resumen["CarrosEnCurso"]),
            f"{_fmt_entero(contexto['unidades_carros_curso'])} unidades",
        ),
        (
            "✅ Carros finalizados",
            _fmt_entero(resumen["CarrosFinalizados"]),
            _detalle_control_finalizado(contexto),
        ),
    ]

    # st.columns garantiza que las cuatro tarjetas ocupen TODO el ancho.
    columnas = st.columns(4, gap="medium")

    for columna, (etiqueta, valor, detalle) in zip(columnas, tarjetas):
        with columna:
            html = (
                '<div class="tareas-kpi-card tareas-kpi-card-principal">'
                f'<div class="tareas-kpi-label">{etiqueta}</div>'
                f'<div class="tareas-kpi-value">{valor}</div>'
                f'<div class="tareas-kpi-detail">{detalle}</div>'
                '</div>'
            )
            st.markdown(html, unsafe_allow_html=True)

    # Más presencia visual sin alterar el resto del estilo de la app.
    st.markdown(
        """
        <style>
        .tareas-kpi-card-principal {
            width: 100% !important;
            min-height: 150px !important;
            padding: 20px 22px !important;
            box-sizing: border-box !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-label {
            font-size: clamp(1rem, 1.08vw, 1.18rem) !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-value {
            font-size: clamp(2.8rem, 3.15vw, 3.75rem) !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-detail {
            font-size: clamp(.9rem, .97vw, 1.08rem) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_indicadores(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    # 1) Avance de despachos arriba, ocupando todo el ancho.
    with st.container(border=True):
        st.markdown("#### 🚛 Avance de despachos")
        sin_iniciar = contexto["despachos_sin_iniciar"]
        if sin_iniciar:
            st.caption(
                f"Sin iniciar ({len(sin_iniciar)}): " + " · ".join(sin_iniciar)
            )

        avance = contexto["avance_despachos"]
        if avance.empty:
            st.info("No hay despachos activos con avance parcial.")
        else:
            # Los donuts quedan en una sola fila superior siempre que entren.
            cantidad_columnas = min(len(avance), 5 if perfil == "tv" else 4)
            cantidad_columnas = max(cantidad_columnas, 1)
            columnas = st.columns(cantidad_columnas)
            for indice, (_, fila) in enumerate(avance.iterrows()):
                with columnas[indice % cantidad_columnas]:
                    grafico_avance_despacho(fila, perfil=perfil)

    # 2) Debajo: tabla a la izquierda y gráfico de sectores a la derecha.
    col_criticos, col_sectores = st.columns(
        [1.65, 1.0], vertical_alignment="top"
    )

    with col_criticos:
        with st.container(border=True):
            st.markdown("#### 🚨 Estado de Preparaciones / Control")

            control_base = contexto["tabla_operativa"].copy()

            if control_base.empty:
                st.info("No hay preparaciones operativas para mostrar.")
            else:
                # Normalización visual.
                for col in ["Despacho", "Cliente", "Preparacion", "Area", "Carro", "Categoria"]:
                    if col not in control_base.columns:
                        control_base[col] = ""
                    control_base[col] = (
                        control_base[col]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                    )

                control_base["Preparacion"] = (
                    control_base["Preparacion"]
                    .str.replace(r"\\.0+$", "", regex=True)
                )
                control_base["Area"] = control_base["Area"].str.upper()

                # Filtro propio de esta tabla por Agrupador / Camioneta.
                opciones_control = sorted(
                    x for x in control_base["Despacho"].unique().tolist() if x
                )
                filtro_control = st.selectbox(
                    "Agrupador / Camioneta",
                    ["Todos"] + opciones_control,
                    key="control_filtro_agrupador_camioneta",
                )

                if filtro_control != "Todos":
                    control_base = control_base.loc[
                        control_base["Despacho"].eq(filtro_control)
                    ].copy()

                def _estado_control_fila(fila):
                    categoria = str(fila.get("Categoria", "")).strip()
                    area = str(fila.get("Area", "")).strip().upper() or "SIN ÁREA"
                    carro = str(fila.get("Carro", "")).strip()

                    unidades = pd.to_numeric(
                        pd.Series([fila.get("Unidades", 0)]), errors="coerce"
                    ).fillna(0).iloc[0]
                    unidades = int(round(float(unidades)))

                    # Abreviaturas operativas.
                    siglas_area = {
                        "IMPORTADO": "IMP",
                        "NACIONAL": "NAC",
                        "SANITARIOS": "SAN",
                        "INTERPLANTA": "INT",
                    }
                    area_corta = siglas_area.get(area, area[:3] if area else "S/A")

                    # Mostrar SOLO símbolo + número: CARRO91 -> 91.
                    numero_carro = re.sub(r"CARRO", "", carro, flags=re.IGNORECASE).strip()
                    match_numero = re.search(r"\d+", numero_carro)
                    if match_numero:
                        numero_carro = match_numero.group(0)

                    detalle_area = f"{area_corta} - {unidades} u."

                    if categoria == "Finalizado":
                        return f"✅ {detalle_area}"

                    if (
                        numero_carro
                        and "SIN ASIGNAR" not in carro.upper()
                        and carro.lower() != "nan"
                    ):
                        return f"🚧 {numero_carro} ({detalle_area})"

                    return f"⏳ SIN ASIGNAR ({detalle_area})"

                control_base["_DetalleControl"] = control_base.apply(
                    _estado_control_fila, axis=1
                )

                # Una fila por Cliente + ID Preparación dentro de cada Despacho.
                # Conservamos todas las áreas: controladas, tomadas y sin asignar.
                agrupado_control = (
                    control_base.groupby(
                        ["Despacho", "Cliente", "Preparacion"],
                        as_index=False,
                        dropna=False,
                    )
                    .agg(
                        Estado=(
                            "_DetalleControl",
                            lambda s: " · ".join(dict.fromkeys(
                                x for x in s.astype(str).tolist() if x
                            )),
                        )
                    )
                )

                # Orden: despacho -> cliente -> preparación numérica cuando sea posible.
                agrupado_control["_PrepOrden"] = pd.to_numeric(
                    agrupado_control["Preparacion"], errors="coerce"
                )
                agrupado_control = agrupado_control.sort_values(
                    ["Despacho", "Cliente", "_PrepOrden", "Preparacion"],
                    na_position="last",
                ).drop(columns=["_PrepOrden"])

                agrupado_control = agrupado_control.rename(
                    columns={
                        "Preparacion": "ID Preparación",
                        "Estado": "Carros / Áreas",
                    }
                )

                st.caption(
                    f"{len(agrupado_control)} preparación(es) visibles"
                    + (
                        f" · {filtro_control}"
                        if filtro_control != "Todos"
                        else ""
                    )
                )

                st.dataframe(
                    agrupado_control[
                        ["Despacho", "Cliente", "Carros / Áreas"]
                    ],
                    width="stretch",
                    hide_index=True,
                    height=430,
                    column_config={
                        "Despacho": st.column_config.TextColumn(
                            "Agrupador / Camioneta", width="medium"
                        ),
                        "Cliente": st.column_config.TextColumn(
                            "Cliente", width="medium"
                        ),
                        "Carros / Áreas": st.column_config.TextColumn(
                            "Pendiente de control / Áreas controladas / Sin asignar",
                            width="large",
                        ),
                    },
                )

    with col_sectores:
        with st.container(border=True):
            st.markdown("#### 📦 Sectores en preparación")
            grafico_sectorizaciones(
                contexto["familias_operativas"],
                perfil=perfil,
            )


def _render_tabla(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    tabla_base = contexto["tabla_operativa"].copy()
    tabla = preparar_tabla_operativa_visual(tabla_base)

    # Mostrar explícitamente la división operativa antes de que exista el carro.
    # El modelo mantiene el orden por Preparación y Área, de modo que las tareas
    # de un mismo cliente/preparación quedan juntas sin ordenar por Cliente.
    if len(tabla) == len(tabla_base):
        tabla = tabla.reset_index(drop=True)
        tabla_base = tabla_base.reset_index(drop=True)

        if "Preparacion" in tabla_base.columns:
            tabla.insert(1, "Preparación", tabla_base["Preparacion"])

        if "Area" in tabla_base.columns:
            area_visible = (
                tabla_base["Area"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            tabla.insert(3 if "Preparación" in tabla.columns else 2, "Área", area_visible)

        # Si todavía no fue tomada, el carro no existe. Lo dejamos explícito
        # para diferenciar una tarea pendiente sectorizada de un dato faltante.
        if "Carro" in tabla.columns and "Categoria" in tabla_base.columns:
            pendiente = tabla_base["Categoria"].astype(str).eq("Pendiente")
            carro_vacio = tabla["Carro"].fillna("").astype(str).str.strip().eq("")
            tabla.loc[pendiente & carro_vacio, "Carro"] = "⏳ Sin asignar"

    st.markdown("### 📋 Operación en curso")

    # Filtro operativo por despacho. Solo afecta la tabla visible.
    columna_despacho = None
    if "Despacho" in tabla.columns:
        columna_despacho = "Despacho"
    elif "DespachoDescripcion" in tabla.columns:
        columna_despacho = "DespachoDescripcion"

    despacho_seleccionado = "Todos"
    if columna_despacho is not None:
        opciones_despacho = (
            tabla[columna_despacho]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        opciones_despacho = sorted(
            valor for valor in opciones_despacho.unique().tolist() if valor
        )

        despacho_seleccionado = st.selectbox(
            "Filtrar por despacho",
            ["Todos"] + opciones_despacho,
            key="operacion_filtro_despacho",
        )

        if despacho_seleccionado != "Todos":
            tabla = tabla.loc[
                tabla[columna_despacho]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq(despacho_seleccionado)
            ].copy()

            # Aplicar el mismo filtro sobre la tabla operativa original.
            # La inteligencia necesita columnas técnicas como Preparacion,
            # Area y Categoria que la tabla visual renombra/oculta.
            if "Despacho" in tabla_base.columns:
                tabla_base = tabla_base.loc[
                    tabla_base["Despacho"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .eq(despacho_seleccionado)
                ].copy()
            elif "DespachoDescripcion" in tabla_base.columns:
                tabla_base = tabla_base.loc[
                    tabla_base["DespachoDescripcion"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .eq(despacho_seleccionado)
                ].copy()

    if despacho_seleccionado == "Todos":
        st.caption(f"{len(tabla)} registros activos")
    else:
        st.caption(f"{len(tabla)} registros · Despacho: {despacho_seleccionado}")

    if tabla.empty:
        st.info("No hay tareas operativas para mostrar con el despacho seleccionado.")
        return

    # ======================================================
    # INTELIGENCIA OPERATIVA: TAREAS QUE CIERRAN PREPARACIONES
    # ======================================================
    # IMPORTANTE: usar tabla_base, no la tabla visual.
    # preparar_tabla_operativa_visual renombra Preparacion -> Preparación
    # y Area -> Área, por eso la versión anterior producía KeyError.
    intel = tabla_base.copy()
    intel["_Prep"] = intel["Preparacion"].astype("string").fillna("").str.strip()
    intel["_Area"] = intel["Area"].fillna("").astype(str).str.strip().str.upper()
    intel["_Categoria"] = intel["Categoria"].astype(str).str.strip()
    intel["_Resuelta"] = intel["_Categoria"].eq("Finalizado")

    carro_intel = (
        intel["Carro"].fillna("").astype(str).str.strip()
        if "Carro" in intel.columns
        else pd.Series("", index=intel.index, dtype="object")
    )
    sin_carro = (
        carro_intel.eq("")
        | carro_intel.str.contains("SIN ASIGNAR", case=False, na=False)
    )

    # Remanente real: solo tareas que todavía no fueron tomadas.
    intel["_Pendiente"] = (
        ~intel["_Resuelta"]
        & ~intel["_Categoria"].eq("En Curso")
        & sin_carro
    )

    for c in ["Unidades", "SKUs", "VolumenM3", "PesoKg"]:
        if c not in intel.columns:
            intel[c] = 0.0
        intel[c] = pd.to_numeric(intel[c], errors="coerce").fillna(0.0)

    # Estado real de cada preparación según sus áreas.
    prep_estado = (
        intel.groupby("_Prep", as_index=False)
        .agg(AreasTotales=("_Area", "nunique"))
    )
    areas_pend = (
        intel.loc[intel["_Pendiente"]]
        .groupby("_Prep")["_Area"].nunique()
        .rename("AreasPendientes")
    )
    areas_res = (
        intel.loc[intel["_Resuelta"]]
        .groupby("_Prep")["_Area"].nunique()
        .rename("AreasResueltas")
    )
    prep_estado = prep_estado.merge(areas_pend, on="_Prep", how="left").merge(
        areas_res, on="_Prep", how="left"
    )
    prep_estado[["AreasPendientes", "AreasResueltas"]] = (
        prep_estado[["AreasPendientes", "AreasResueltas"]].fillna(0).astype(int)
    )

    pendientes_i = intel.loc[intel["_Pendiente"]].merge(
        prep_estado, on="_Prep", how="left"
    )

    if not pendientes_i.empty:
        agg = {
            "Cliente": "first",
            "Despacho": "first",
            "Unidades": "max",
            "SKUs": "max",
            "VolumenM3": "max",
            "PesoKg": "max",
            "AreasTotales": "max",
            "AreasResueltas": "max",
            "AreasPendientes": "max",
            "Categoria": "first",
        }
        if "Vehiculo" in pendientes_i.columns:
            agg["Vehiculo"] = "first"

        prioridad = (
            pendientes_i.groupby(["_Prep", "_Area"], as_index=False).agg(agg)
        )

        # 45% cierre inmediato + 25% cercanía al cierre +
        # 20% quick win físico + 10% continuidad de una tarea ya tomada.
        prioridad["CierraPreparacion"] = prioridad["AreasPendientes"].eq(1)
        prioridad["CercaniaCierre"] = (
            1.0 - (
                (prioridad["AreasPendientes"] - 1).clip(lower=0)
                / prioridad["AreasTotales"].clip(lower=1)
            )
        ).clip(0, 1)

        vol = prioridad["VolumenM3"].clip(lower=0)
        uni = prioridad["Unidades"].clip(lower=0)
        max_vol = float(vol.max()) if len(vol) else 0.0
        max_uni = float(uni.max()) if len(uni) else 0.0
        facilidad_vol = 1 - (vol / max_vol) if max_vol > 0 else 1.0
        facilidad_uni = 1 - (uni / max_uni) if max_uni > 0 else 1.0
        prioridad["QuickWin"] = (facilidad_vol * 0.6 + facilidad_uni * 0.4).clip(0, 1)
        prioridad["ScorePrioridad"] = (
            prioridad["CierraPreparacion"].astype(float) * 50
            + prioridad["CercaniaCierre"] * 30
            + prioridad["QuickWin"] * 20
        ).clip(0, 100).round().astype(int)

        prioridad["Accion"] = "🟡 SIGUIENTE"
        prioridad.loc[prioridad["ScorePrioridad"].lt(50), "Accion"] = "⚪ COLA"
        prioridad.loc[prioridad["ScorePrioridad"].ge(70), "Accion"] = "🟠 ALTA"
        prioridad.loc[prioridad["CierraPreparacion"], "Accion"] = "🔥 CERRAR YA"

        prioridad = prioridad.sort_values(
            ["CierraPreparacion", "ScorePrioridad", "AreasPendientes", "VolumenM3"],
            ascending=[False, False, True, True],
        ).reset_index(drop=True)

        impacto_area = (
            prioridad.groupby("_Area", as_index=False)
            .agg(
                Tareas=("_Prep", "nunique"),
                CierraAhora=("CierraPreparacion", "sum"),
                ScoreProm=("ScorePrioridad", "mean"),
                VolPend=("VolumenM3", "sum"),
            )
            .sort_values(
                ["CierraAhora", "ScoreProm", "Tareas"],
                ascending=[False, False, False],
            )
        )

        st.markdown("#### 🎯 Tareas que cierran Preparaciones")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Preparaciones por cerrar", int(prioridad["_Prep"].nunique()))
        k2.metric(
            "Cerrables ahora",
            int(prioridad.loc[prioridad["CierraPreparacion"], "_Prep"].nunique()),
        )
        k3.metric("Tareas / áreas pendientes", int(len(prioridad)))
        k4.metric("Volumen pendiente", f"{prioridad['VolumenM3'].sum():.2f} m³")

        if not impacto_area.empty:
            top = impacto_area.iloc[0]
            area_top = str(top["_Area"]).strip()
            cierres_top = int(top["CierraAhora"])
            tareas_top = int(top["Tareas"])
            if cierres_top:
                st.success(
                    f"**Prioridad ahora: {area_top}.** "
                    f"Atacar {tareas_top} tarea(s) de esta área permite cerrar "
                    f"**{cierres_top} preparación(es) inmediatamente**."
                )
            else:
                st.info(
                    f"**Prioridad ahora: {area_top}.** "
                    "Es el área con mejor combinación entre cercanía al cierre, "
                    "esfuerzo restante y continuidad operativa."
                )

        c1, c2 = st.columns([1.0, 2.0], vertical_alignment="top")
        with c1:
            st.markdown("**Orden recomendado por área**")
            ta = impacto_area.copy()
            ta["Score"] = ta["ScoreProm"].round().astype(int)
            ta["Vol. pend."] = ta["VolPend"].round(2)
            ta = ta.rename(columns={"_Area": "Área", "CierraAhora": "Cierra prep."})
            st.dataframe(
                ta[["Área", "Tareas", "Cierra prep.", "Score", "Vol. pend."]],
                hide_index=True, width="stretch", height=275,
            )

        with c2:
            st.markdown("**Qué conviene sacar primero**")
            tm = prioridad.copy()
            tm["Preparación"] = tm["_Prep"]
            tm["Área"] = tm["_Area"]
            tm["Áreas listas"] = tm["AreasResueltas"].astype(int)
            tm["Faltan"] = tm["AreasPendientes"].astype(int)
            tm["Vol. m³"] = tm["VolumenM3"].round(3)
            tm["Prioridad"] = tm["ScorePrioridad"]
            cols = [
                "Accion", "Prioridad", "Preparación", "Cliente", "Área",
                "Áreas listas", "Faltan", "Unidades", "SKUs", "Vol. m³",
            ]
            # Sugerencia NUESTRA por volumetría; no usa Vehiculo de DIGIP.
            tm["Vehículo sugerido"] = tm["VolumenM3"].apply(
                sugerir_equipamiento_operativo
            )
            cols.insert(5, "Vehículo sugerido")
            st.dataframe(
                tm[cols].head(15), hide_index=True, width="stretch", height=275,
            )

        st.caption(
            "Prioridad: cierre inmediato de preparación → cercanía al cierre → "
            "quick win por volumen/unidades. Las tareas ya tomadas salen de esta propuesta."
        )
        st.divider()

    # ======================================================
    # ORGANIZACIÓN FÍSICA PRE POR DESPACHO / CAMIONETA
    # ======================================================
    organizacion_pre = contexto.get("organizacion_pre", pd.DataFrame()).copy()

    # Respetar el mismo filtro de despacho seleccionado en la pantalla.
    if (
        not organizacion_pre.empty
        and despacho_seleccionado != "Todos"
        and "Despacho / Camioneta" in organizacion_pre.columns
    ):
        organizacion_pre = organizacion_pre.loc[
            organizacion_pre["Despacho / Camioneta"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq(despacho_seleccionado)
        ].copy()

    st.markdown("#### 📍 Organización de posiciones PRE")

    if organizacion_pre.empty:
        st.info("No hay Despachos/Camionetas activos para asignar a PRE.")
    else:
        # Completar visualmente las cuatro posiciones cuando se mira el tablero general.
        if despacho_seleccionado == "Todos":
            usados = set(organizacion_pre["PRE"].astype(str))
            libres = []
            for numero in range(1, 5):
                pre = f"PRE {numero}"
                if pre not in usados:
                    libres.append({
                        "PRE": pre,
                        "Despacho / Camioneta": "—",
                        "Estado": "⚪ LIBRE",
                        "Preparaciones": 0,
                        "Áreas pendientes": 0,
                        "Áreas controladas": 0,
                        "Vol. pendiente m³": 0.0,
                        "Área sugerida": "—",
                        "Equipamiento sugerido": "—",
                    })
            if libres:
                organizacion_pre = pd.concat(
                    [organizacion_pre, pd.DataFrame(libres)],
                    ignore_index=True,
                )

        st.dataframe(
            organizacion_pre,
            hide_index=True,
            width="stretch",
            column_config={
                "PRE": st.column_config.TextColumn("PRE", width="small"),
                "Despacho / Camioneta": st.column_config.TextColumn(
                    "Despacho / Camioneta", width="medium"
                ),
                "Área sugerida": st.column_config.TextColumn(
                    "Área sugerida", width="medium"
                ),
                "Equipamiento sugerido": st.column_config.TextColumn(
                    "Equipamiento sugerido", width="large"
                ),
                "Vol. pendiente m³": st.column_config.NumberColumn(
                    "Vol. pendiente m³", format="%.2f"
                ),
            },
        )

        sin_pre = organizacion_pre[
            organizacion_pre["PRE"].astype(str).str.contains("SIN PRE", na=False)
        ]
        if not sin_pre.empty:
            st.warning(
                f"⚠️ Hay {len(sin_pre)} Despacho(s)/Camioneta(s) activos sin posición PRE disponible."
            )

    st.caption(
        "PRE organiza físicamente el Despacho/Camioneta. "
        "El equipamiento es una sugerencia propia calculada por volumen y no depende de DIGIP."
    )
    st.divider()

    st.dataframe(
        tabla.style.format({"Unidades": "{:.0f}", "SKUs": "{:.0f}"}).apply(
            resaltar_carro, axis=1
        ),
        width="stretch",
        hide_index=True,
        height={"pc": 560, "monitor": 620, "tv": 790}[perfil],
    )


@st.fragment(run_every="5m")
def _render_fragmento_operativo(perfil: str) -> None:
    carga = cargar_fuentes_tareas()
    fuentes = carga["fuentes"]

    faltantes = [
        nombre
        for nombre, clave in [
            ("Informe Tareas", "tareas"),
            ("Pedidos DIGIP", "pedidos"),
            ("Detalle Pendientes", "detalle"),
            ("Maestro Clientes", "clientes"),
            ("Maestro Artículo", "articulos"),
            ("Maestro Volumetría", "volumetria"),
        ]
        if fuentes[clave] is None or fuentes[clave].empty
    ]

    if faltantes:
        st.error("No se puede construir el tablero. Faltan: " + ", ".join(faltantes))
        return

    if carga["actualizacion_completa"]:
        st.caption(
            f"✅ Datos actualizados: {carga['hora_actualizacion']} · "
            "actualización automática cada 5 minutos"
        )
    else:
        st.caption(
            f"⚠️ Último intento: {carga['hora_actualizacion']} · "
            "se conserva información válida anterior"
        )

    if carga["mensajes"]:
        with st.expander("⚠️ Detalle de actualización", expanded=False):
            for mensaje in carga["mensajes"]:
                st.caption(f"• {mensaje}")

    with medir_tiempo("Construir contexto operativo"):
        contexto = construir_contexto_tareas(
            fuentes["tareas"],
            fuentes["pedidos"],
            fuentes["detalle"],
            fuentes["clientes"],
            fuentes["articulos"],
            fuentes["volumetria"],
            fuentes.get("control_historico"),
        )

    mostrar_info_dataframe("Tabla pedidos", contexto["tabla_pedidos"])
    mostrar_info_dataframe("Tabla tareas", contexto["tabla_tareas"])
    mostrar_info_dataframe("Tabla operativa", contexto["tabla_operativa"])

    _render_kpis(contexto)
    _render_indicadores(contexto, perfil=perfil)
    _render_tabla(contexto, perfil=perfil)


def render_tareas() -> None:
    with st.sidebar:
        st.markdown("### Visualización")
        modo = selector_modo_visual()
        st.toggle("Diagnóstico de rendimiento", key="debug_rendimiento")

    perfil = perfil_visual(modo)
    aplicar_estilo_pantalla(modo)

    encabezado, acciones = st.columns([5, 1], vertical_alignment="center")
    with encabezado:
        st.title("📋 Centro de Control Operativo")
        st.caption("Seguimiento en vivo de pedidos, carros, despachos y sectores")
    with acciones:
        if st.button("🔄 Actualizar ahora", width="stretch"):
            invalidar_cache_tareas()
            construir_contexto_tareas.clear()
            st.rerun()

    # Navegación con carga bajo demanda: a diferencia de st.tabs,
    # solamente se ejecuta la vista seleccionada. Esto evita construir
    # Estadísticas mientras el usuario está trabajando en Operación en vivo.
    vista = st.segmented_control(
        "Vista del módulo",
        options=["⚡ Operación en vivo", "📊 Estadísticas"],
        default="⚡ Operación en vivo",
        key="tareas_vista_modulo",
        label_visibility="collapsed",
    )

    if vista == "📊 Estadísticas":
        from views.tareas.estadisticas import render_estadisticas_tareas

        render_estadisticas_tareas()
    else:
        _render_fragmento_operativo(perfil)
