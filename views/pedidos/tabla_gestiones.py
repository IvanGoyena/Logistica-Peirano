from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.consultas.leer_gestion_consultas import (
    obtener_reclamos_abiertos, leer_reclamos, leer_reclamos_detalle, leer_reclamos_fotos,
)
from utils.consultas.gestion_consultas import actualizar_solicitud
from utils.consultas.gestion_reclamos import actualizar_reclamo

def render_tabla_gestiones(
    tabla: pd.DataFrame,
    solicitudes_abiertas: pd.DataFrame,
    reclamos_abiertos: pd.DataFrame,
) -> None:
        # =====================================================
        # AVISO Y GESTIÓN DE SOLICITUDES COMERCIALES
        # =====================================================

        ESTADOS_SOLICITUD = [
            "Pendiente",
            "En revisión",
            "En curso",
            "Finalizada",
        ]


        # =====================================================
        # RECLAMOS PENDIENTES
        # =====================================================

        ESTADOS_RECLAMO_GESTION = [
            "Pendiente",
            "En revisión",
            "En gestión",
            "Resuelto",
            "Rechazado",
        ]


        @st.dialog(
            "🧾 Gestionar reclamos",
            width="large",
        )
        def abrir_reclamos_pendientes() -> None:
            """
            Permite consultar y gestionar los reclamos abiertos sin
            ocupar espacio permanente en la página de Pedidos.
            """

            reclamos_actuales = obtener_reclamos_abiertos()

            if reclamos_actuales is None or reclamos_actuales.empty:
                st.success(
                    "No hay reclamos pendientes de revisión.",
                    icon="✅",
                )
                return

            tabla_reclamos = reclamos_actuales.copy()

            columnas_reclamos = [
                "ReclamoID",
                "Pedido",
                "Remito",
                "Cliente",
                "FechaReclamo",
                "TipoReclamo",
                "Descripcion",
                "Responsable",
                "EstadoReclamo",
                "Resolucion",
                "UsuarioCreador",
                "FechaCreacion",
                "FechaCierre",
            ]

            for columna in columnas_reclamos:
                if columna not in tabla_reclamos.columns:
                    tabla_reclamos[columna] = ""

            tabla_reclamos["FechaCreacionOrden"] = pd.to_datetime(
                tabla_reclamos["FechaCreacion"],
                errors="coerce",
            )

            tabla_reclamos["FechaCreacionVisible"] = (
                tabla_reclamos["FechaCreacionOrden"]
                .dt.strftime("%d/%m/%Y %H:%M")
                .fillna(
                    tabla_reclamos["FechaCreacion"]
                    .fillna("")
                    .astype(str)
                )
            )

            tabla_reclamos = (
                tabla_reclamos
                .sort_values(
                    by="FechaCreacionOrden",
                    ascending=False,
                    na_position="last",
                )
                .reset_index(drop=True)
            )

            total_reclamos = len(tabla_reclamos)
            pedidos_afectados = tabla_reclamos["Pedido"].nunique()

            resumen_1, resumen_2 = st.columns(2)
            resumen_1.metric("Reclamos abiertos", total_reclamos)
            resumen_2.metric("Pedidos involucrados", pedidos_afectados)

            opciones_reclamo = {}

            for _, fila in tabla_reclamos.iterrows():
                reclamo_id = str(fila.get("ReclamoID", "")).strip()
                pedido = str(fila.get("Pedido", "")).strip()
                cliente = str(fila.get("Cliente", "")).strip()
                incidencia = str(fila.get("TipoReclamo", "")).strip()
                estado = str(fila.get("EstadoReclamo", "")).strip()

                etiqueta = (
                    f"{pedido or 'Sin pedido'} · "
                    f"{incidencia or 'Sin incidencia'} · "
                    f"{estado or 'Pendiente'} · "
                    f"{cliente or 'Cliente sin identificar'}"
                )
                opciones_reclamo[etiqueta] = reclamo_id

            etiqueta_seleccionada = st.selectbox(
                "Seleccionar reclamo",
                options=list(opciones_reclamo.keys()),
                key="selector_reclamo_gestion",
            )

            reclamo_id = opciones_reclamo[etiqueta_seleccionada]

            coincidencia = tabla_reclamos.loc[
                tabla_reclamos["ReclamoID"]
                .astype(str)
                .eq(str(reclamo_id))
            ]

            if coincidencia.empty:
                st.error("No se encontró el reclamo seleccionado.")
                return

            reclamo = coincidencia.iloc[0]

            pedido = str(reclamo.get("Pedido", "")).strip()
            remito = str(reclamo.get("Remito", "")).strip()
            cliente = str(reclamo.get("Cliente", "")).strip()
            incidencia = str(reclamo.get("TipoReclamo", "")).strip()
            descripcion = str(reclamo.get("Descripcion", "")).strip()
            registrado_por = str(reclamo.get("UsuarioCreador", "")).strip()
            fecha_creacion = str(
                reclamo.get("FechaCreacionVisible", "")
            ).strip()
            responsable_actual = str(
                reclamo.get("Responsable", "")
            ).strip()
            resolucion_actual = str(
                reclamo.get("Resolucion", "")
            ).strip()
            estado_actual = str(
                reclamo.get("EstadoReclamo", "Pendiente")
            ).strip()

            if estado_actual not in ESTADOS_RECLAMO_GESTION:
                estado_actual = "Pendiente"

            cabecera_1, cabecera_2, cabecera_3 = st.columns(
                [1, 2.4, 1.2],
                vertical_alignment="center",
            )

            with cabecera_1:
                st.metric("Pedido", pedido or "Sin dato")

            with cabecera_2:
                st.markdown(f"**{cliente or 'Cliente sin identificar'}**")
                st.caption(
                    f"{incidencia or 'Reclamo'} · Remito {remito or 'Sin dato'}"
                )

            with cabecera_3:
                st.metric("Estado", estado_actual)

            st.info(
                descripcion or "El reclamo no tiene descripción.",
                icon="📝",
            )

            datos_1, datos_2, datos_3 = st.columns(3)

            with datos_1:
                st.caption(
                    f"**Registrado por**  \n{registrado_por or 'Sin dato'}"
                )

            with datos_2:
                st.caption(
                    f"**Fecha de creación**  \n{fecha_creacion or 'Sin dato'}"
                )

            with datos_3:
                st.caption(
                    f"**Responsable actual**  \n"
                    f"{responsable_actual or 'Logistica'}"
                )

            detalle_reclamos = leer_reclamos_detalle()

            if detalle_reclamos is not None and not detalle_reclamos.empty:
                detalle_seleccionado = detalle_reclamos.loc[
                    detalle_reclamos["ReclamoID"]
                    .astype(str)
                    .eq(str(reclamo_id))
                ].copy()

                if not detalle_seleccionado.empty:
                    st.markdown("#### Artículos reclamados")

                    columnas_detalle = [
                        "CodigoArticulo",
                        "DescripcionArticulo",
                        "Cantidad",
                        "Observacion",
                    ]

                    for columna in columnas_detalle:
                        if columna not in detalle_seleccionado.columns:
                            detalle_seleccionado[columna] = ""

                    st.dataframe(
                        detalle_seleccionado[columnas_detalle].rename(
                            columns={
                                "CodigoArticulo": "Código",
                                "DescripcionArticulo": "Descripción",
                                "Cantidad": "Cantidad reclamada",
                                "Observacion": "Detalle de cantidades",
                            }
                        ),
                        width="stretch",
                        hide_index=True,
                    )

            fotos_reclamos = leer_reclamos_fotos()

            if fotos_reclamos is not None and not fotos_reclamos.empty:
                fotos_seleccionadas = fotos_reclamos.loc[
                    fotos_reclamos["ReclamoID"]
                    .astype(str)
                    .eq(str(reclamo_id))
                ].copy()

                if not fotos_seleccionadas.empty:
                    st.markdown("#### Fotografías")

                    for posicion, (_, foto) in enumerate(
                        fotos_seleccionadas.iterrows(),
                        start=1,
                    ):
                        nombre_foto = str(
                            foto.get("NombreArchivo", f"Fotografía {posicion}")
                        ).strip()
                        url_foto = str(
                            foto.get("URLArchivo", "")
                        ).strip()

                        if url_foto:
                            st.link_button(
                                f"📷 {nombre_foto or f'Fotografía {posicion}'}",
                                url_foto,
                                width="stretch",
                            )

            st.divider()

            with st.form(
                f"form_gestion_reclamo_{reclamo_id}",
                clear_on_submit=False,
            ):
                formulario_1, formulario_2 = st.columns([1, 2])

                with formulario_1:
                    nuevo_estado_reclamo = st.selectbox(
                        "Estado",
                        options=ESTADOS_RECLAMO_GESTION,
                        index=ESTADOS_RECLAMO_GESTION.index(
                            estado_actual
                        ),
                    )

                with formulario_2:
                    resolucion_reclamo = st.text_area(
                        "Respuesta / resolución",
                        value=resolucion_actual,
                        placeholder=(
                            "Detalle de la revisión, respuesta al reclamo "
                            "o solución aplicada por Logística..."
                        ),
                        height=120,
                    )

                guardar_reclamo = st.form_submit_button(
                    "💾 Guardar gestión del reclamo",
                    type="primary",
                    width="stretch",
                )

            if guardar_reclamo:
                usuario_logistica = (
                    st.session_state.get("usuario")
                    or st.session_state.get("nombre_usuario")
                    or "Logistica"
                )

                try:
                    resultado = actualizar_reclamo(
                        reclamo_id=reclamo_id,
                        estado_reclamo=nuevo_estado_reclamo,
                        resolucion=resolucion_reclamo,
                        responsable=usuario_logistica,
                    )

                    st.toast("Reclamo actualizado.", icon="✅")

                    # Fuerza el rerun completo de la aplicación para cerrar
                    # el diálogo después de guardar la gestión.
                    st.rerun(scope="app")

                except Exception as error:
                    st.error("No se pudo actualizar el reclamo.")
                    st.exception(error)


        @st.dialog(
            "📚 Histórico de reclamos",
            width="large",
        )
        def abrir_historico_reclamos() -> None:
            """
            Muestra todos los reclamos guardados en Google Sheets,
            tanto abiertos como cerrados, sin permitir su modificación.
            """

            reclamos_historicos = leer_reclamos()

            if reclamos_historicos is None or reclamos_historicos.empty:
                st.info(
                    "Todavía no hay reclamos registrados.",
                    icon="🧾",
                )
                return

            tabla_historica = reclamos_historicos.copy()

            columnas_requeridas = [
                "ReclamoID",
                "Pedido",
                "Remito",
                "Cliente",
                "TipoReclamo",
                "Descripcion",
                "Responsable",
                "EstadoReclamo",
                "Resolucion",
                "UsuarioCreador",
                "FechaCreacion",
                "FechaCierre",
            ]

            for columna in columnas_requeridas:
                if columna not in tabla_historica.columns:
                    tabla_historica[columna] = ""

            tabla_historica["Pedido"] = (
                tabla_historica["Pedido"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )

            tabla_historica["FechaCreacionOrden"] = pd.to_datetime(
                tabla_historica["FechaCreacion"],
                errors="coerce",
            )

            tabla_historica["FechaVisible"] = (
                tabla_historica["FechaCreacionOrden"]
                .dt.strftime("%d/%m/%Y %H:%M")
                .fillna(
                    tabla_historica["FechaCreacion"]
                    .fillna("")
                    .astype(str)
                )
            )

            tabla_historica["FechaCierreVisible"] = (
                pd.to_datetime(
                    tabla_historica["FechaCierre"],
                    errors="coerce",
                )
                .dt.strftime("%d/%m/%Y %H:%M")
                .fillna(
                    tabla_historica["FechaCierre"]
                    .fillna("")
                    .astype(str)
                )
                .replace("", "Abierto")
            )

            tabla_historica = (
                tabla_historica
                .sort_values(
                    "FechaCreacionOrden",
                    ascending=False,
                    na_position="last",
                )
                .reset_index(drop=True)
            )

            estados = sorted(
                estado
                for estado in tabla_historica["EstadoReclamo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
                if estado
            )

            filtro_1, filtro_2 = st.columns([2, 1])

            with filtro_1:
                busqueda = st.text_input(
                    "Buscar",
                    placeholder="Pedido, remito, cliente, incidencia o ID...",
                    key="buscar_historico_reclamos_pedidos",
                )

            with filtro_2:
                estado_filtro = st.selectbox(
                    "Estado",
                    options=["Todos"] + estados,
                    key="estado_historico_reclamos_pedidos",
                )

            reclamos_filtrados = tabla_historica.copy()

            if busqueda.strip():
                texto_busqueda = busqueda.strip()
                mascara = pd.Series(False, index=reclamos_filtrados.index)

                for columna in [
                    "ReclamoID",
                    "Pedido",
                    "Remito",
                    "Cliente",
                    "TipoReclamo",
                ]:
                    mascara = mascara | (
                        reclamos_filtrados[columna]
                        .fillna("")
                        .astype(str)
                        .str.contains(
                            texto_busqueda,
                            case=False,
                            na=False,
                            regex=False,
                        )
                    )

                reclamos_filtrados = reclamos_filtrados.loc[mascara].copy()

            if estado_filtro != "Todos":
                reclamos_filtrados = reclamos_filtrados[
                    reclamos_filtrados["EstadoReclamo"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .eq(estado_filtro)
                ].copy()

            tabla_visible = (
                reclamos_filtrados[
                    [
                        "ReclamoID",
                        "Pedido",
                        "Remito",
                        "Cliente",
                        "TipoReclamo",
                        "EstadoReclamo",
                        "Responsable",
                        "FechaVisible",
                        "FechaCierreVisible",
                    ]
                ]
                .rename(
                    columns={
                        "ReclamoID": "ID",
                        "TipoReclamo": "Incidencia",
                        "EstadoReclamo": "Estado",
                        "FechaVisible": "Fecha alta",
                        "FechaCierreVisible": "Fecha cierre",
                    }
                )
                .reset_index(drop=True)
            )

            st.caption(
                f"{len(tabla_visible):,} reclamo(s) registrado(s)"
                .replace(",", ".")
            )

            evento = st.dataframe(
                tabla_visible,
                width="stretch",
                hide_index=True,
                height=min(420, 85 + len(tabla_visible) * 35),
                on_select="rerun",
                selection_mode="single-row",
                key="tabla_historico_reclamos_pedidos",
                column_config={
                    "ID": None,
                    "Pedido": st.column_config.TextColumn(width="small"),
                    "Remito": st.column_config.TextColumn(width="small"),
                    "Cliente": st.column_config.TextColumn(width="large"),
                    "Incidencia": st.column_config.TextColumn(width="medium"),
                    "Estado": st.column_config.TextColumn(width="small"),
                    "Responsable": st.column_config.TextColumn(width="small"),
                    "Fecha alta": st.column_config.TextColumn(width="small"),
                    "Fecha cierre": st.column_config.TextColumn(width="small"),
                },
            )

            filas = evento.selection.rows if evento is not None else []

            if not filas:
                st.caption(
                    "Seleccioná un registro para ver su descripción y resolución."
                )
                return

            reclamo = (
                reclamos_filtrados
                .reset_index(drop=True)
                .iloc[filas[0]]
            )

            st.divider()

            detalle_1, detalle_2, detalle_3 = st.columns([1, 2.3, 1])
            detalle_1.metric("Pedido", str(reclamo.get("Pedido", "")) or "Sin dato")

            with detalle_2:
                st.markdown(
                    f"**{str(reclamo.get('Cliente', '')).strip() or 'Cliente sin identificar'}**"
                )
                st.caption(
                    f"{str(reclamo.get('TipoReclamo', '')).strip() or 'Reclamo'} · "
                    f"Remito {str(reclamo.get('Remito', '')).strip() or 'Sin dato'}"
                )

            detalle_3.metric(
                "Estado",
                str(reclamo.get("EstadoReclamo", "")).strip() or "Sin estado",
            )

            st.info(
                str(reclamo.get("Descripcion", "")).strip()
                or "El reclamo no tiene descripción.",
                icon="📝",
            )

            resolucion = str(reclamo.get("Resolucion", "")).strip()

            if resolucion:
                st.success(resolucion, icon="✅")
            else:
                st.warning(
                    "El reclamo todavía no tiene una resolución registrada.",
                    icon="⏳",
                )

            info_1, info_2, info_3 = st.columns(3)
            info_1.caption(
                f"**Registrado por**  \n"
                f"{str(reclamo.get('UsuarioCreador', '')).strip() or 'Sin dato'}"
            )
            info_2.caption(
                f"**Fecha de alta**  \n"
                f"{str(reclamo.get('FechaVisible', '')).strip() or 'Sin dato'}"
            )
            info_3.caption(
                f"**Fecha de cierre**  \n"
                f"{str(reclamo.get('FechaCierreVisible', '')).strip() or 'Abierto'}"
            )

            reclamo_id = str(reclamo.get("ReclamoID", "")).strip()
            detalle_reclamos = leer_reclamos_detalle()

            if detalle_reclamos is not None and not detalle_reclamos.empty:
                detalle_seleccionado = detalle_reclamos.loc[
                    detalle_reclamos["ReclamoID"]
                    .astype(str)
                    .eq(reclamo_id)
                ].copy()

                if not detalle_seleccionado.empty:
                    st.markdown("#### Artículos reclamados")
                    columnas_detalle = [
                        "CodigoArticulo",
                        "DescripcionArticulo",
                        "Cantidad",
                        "Observacion",
                    ]

                    for columna in columnas_detalle:
                        if columna not in detalle_seleccionado.columns:
                            detalle_seleccionado[columna] = ""

                    st.dataframe(
                        detalle_seleccionado[columnas_detalle].rename(
                            columns={
                                "CodigoArticulo": "Código",
                                "DescripcionArticulo": "Descripción",
                                "Cantidad": "Cantidad reclamada",
                                "Observacion": "Detalle de cantidades",
                            }
                        ),
                        width="stretch",
                        hide_index=True,
                    )

            fotos_reclamos = leer_reclamos_fotos()

            if fotos_reclamos is not None and not fotos_reclamos.empty:
                fotos_seleccionadas = fotos_reclamos.loc[
                    fotos_reclamos["ReclamoID"]
                    .astype(str)
                    .eq(reclamo_id)
                ].copy()

                if not fotos_seleccionadas.empty:
                    st.markdown("#### Fotografías")

                    for posicion, (_, foto) in enumerate(
                        fotos_seleccionadas.iterrows(),
                        start=1,
                    ):
                        nombre = str(
                            foto.get("NombreArchivo", f"Fotografía {posicion}")
                        ).strip()
                        url = str(foto.get("URLArchivo", "")).strip()

                        if url:
                            st.link_button(
                                f"📷 {nombre or f'Fotografía {posicion}'}",
                                url,
                                width="stretch",
                            )


        reclamos_totales_historial = leer_reclamos()

        if reclamos_totales_historial is None:
            reclamos_totales_historial = pd.DataFrame()

        if not reclamos_abiertos.empty:

            cantidad_reclamos_abiertos = len(reclamos_abiertos)
            pedidos_con_reclamo = (
                reclamos_abiertos["Pedido"].nunique()
                if "Pedido" in reclamos_abiertos.columns
                else 0
            )

            aviso_reclamo, boton_reclamo, boton_historico = st.columns(
                [4.6, 1.25, 1.15],
                vertical_alignment="center",
            )

            with aviso_reclamo:
                st.warning(
                    (
                        f"Hay {cantidad_reclamos_abiertos} reclamo(s) "
                        f"pendiente(s) de revisión sobre "
                        f"{pedidos_con_reclamo} pedido(s)."
                    ),
                    icon="🧾",
                )

            with boton_reclamo:
                ver_reclamos_pendientes = st.button(
                    "Gestionar reclamos",
                    icon="🧾",
                    type="primary",
                    width="stretch",
                    key="btn_ver_reclamos_pendientes",
                )

            with boton_historico:
                ver_historico_reclamos = st.button(
                    "Histórico",
                    icon="📚",
                    width="stretch",
                    key="btn_historico_reclamos_pedidos",
                )

            if ver_reclamos_pendientes:
                abrir_reclamos_pendientes()

            if ver_historico_reclamos:
                abrir_historico_reclamos()

        else:
            aviso_sin_reclamos, boton_historico = st.columns(
                [5.85, 1.15],
                vertical_alignment="center",
            )

            with aviso_sin_reclamos:
                st.success(
                    "No hay reclamos pendientes de revisión.",
                    icon="✅",
                )

            with boton_historico:
                ver_historico_reclamos = st.button(
                    "Histórico",
                    icon="📚",
                    width="stretch",
                    disabled=reclamos_totales_historial.empty,
                    key="btn_historico_reclamos_pedidos_sin_abiertos",
                )

            if ver_historico_reclamos:
                abrir_historico_reclamos()


        @st.dialog(
            "📩 Gestionar solicitud comercial",
            width="large",
        )
        def abrir_gestion_solicitud(
            solicitud_id: str,
        ) -> None:
            """
            Abre una ventana modal para gestionar una solicitud sin
            ocupar espacio permanente en la pantalla principal.
            """

            coincidencia = solicitudes_abiertas.loc[
                solicitudes_abiertas["SolicitudID"]
                .astype(str)
                .eq(str(solicitud_id))
            ].copy()

            if coincidencia.empty:
                st.error("No se encontró la solicitud seleccionada.")
                return

            solicitud = coincidencia.iloc[0]

            pedido = str(
                solicitud.get("Pedido", "")
            ).strip()

            cliente = str(
                solicitud.get("Cliente", "")
            ).strip()

            tipo_solicitud = str(
                solicitud.get("TipoSolicitud", "")
            ).strip()

            prioridad = str(
                solicitud.get("Prioridad", "")
            ).strip()

            descripcion = str(
                solicitud.get("Descripcion", "")
            ).strip()

            solicitado_por = str(
                solicitud.get("UsuarioSolicitante", "")
            ).strip()

            fecha_solicitud = str(
                solicitud.get("FechaSolicitudVisible", "")
            ).strip()

            responsable_actual = str(
                solicitud.get("Responsable", "")
            ).strip()

            unidades_pedido = int(
                pd.to_numeric(
                    solicitud.get("TotalUnidades", 0),
                    errors="coerce",
                )
                if pd.notna(
                    pd.to_numeric(
                        solicitud.get("TotalUnidades", 0),
                        errors="coerce",
                    )
                )
                else 0
            )

            volumen_pedido = float(
                pd.to_numeric(
                    solicitud.get("TotalM3", 0),
                    errors="coerce",
                )
                if pd.notna(
                    pd.to_numeric(
                        solicitud.get("TotalM3", 0),
                        errors="coerce",
                    )
                )
                else 0
            )

            estado_actual = str(
                solicitud.get(
                    "EstadoSolicitud",
                    "Pendiente",
                )
            ).strip()

            if estado_actual not in ESTADOS_SOLICITUD:
                estado_actual = "Pendiente"

            prioridad_icono = {
                "ALTA": "🔴",
                "NORMAL": "🟡",
                "BAJA": "🟢",
            }.get(
                prioridad.upper(),
                "⚪",
            )

            cabecera_1, cabecera_2, cabecera_3, cabecera_4 = st.columns(
                [0.9, 2.1, 0.9, 0.9],
                vertical_alignment="center",
            )

            with cabecera_1:
                st.metric(
                    "Pedido",
                    pedido or "Sin dato",
                )

            with cabecera_2:
                st.markdown(f"**{cliente or 'Cliente sin identificar'}**")
                st.caption(
                    f"{tipo_solicitud or 'Solicitud'} · "
                    f"{prioridad_icono} {prioridad or 'Sin prioridad'}"
                )

            with cabecera_3:
                st.metric(
                    "Unidades",
                    f"{unidades_pedido:,}".replace(",", "."),
                )

            with cabecera_4:
                volumen_formateado = (
                    f"{volumen_pedido:,.3f} m³"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

                st.metric(
                    "Volumen",
                    volumen_formateado,
                )

            st.caption(
                f"**Estado actual:** {estado_actual}"
            )

            st.info(
                descripcion or "La solicitud no tiene detalle.",
                icon="📝",
            )

            datos_col_1, datos_col_2, datos_col_3 = st.columns(3)

            with datos_col_1:
                st.caption(
                    f"**Solicitado por**  \n"
                    f"{solicitado_por or 'Sin dato'}"
                )

            with datos_col_2:
                st.caption(
                    f"**Fecha**  \n"
                    f"{fecha_solicitud or 'Sin dato'}"
                )

            with datos_col_3:
                st.caption(
                    f"**Responsable actual**  \n"
                    f"{responsable_actual or 'Sin asignar'}"
                )

            st.divider()

            with st.form(
                f"form_gestion_solicitud_{solicitud_id}",
                clear_on_submit=False,
            ):

                formulario_1, formulario_2 = st.columns(
                    [1, 2],
                )

                with formulario_1:

                    nuevo_estado_solicitud = st.selectbox(
                        "Estado",
                        options=ESTADOS_SOLICITUD,
                        index=ESTADOS_SOLICITUD.index(
                            estado_actual
                        ),
                    )

                with formulario_2:

                    observacion_logistica = st.text_area(
                        "Observación / respuesta",
                        value=str(
                            solicitud.get(
                                "Respuesta",
                                "",
                            )
                        ),
                        placeholder=(
                            "Detalle de la revisión o acción "
                            "realizada por Logística..."
                        ),
                        height=110,
                    )

                guardar_estado_solicitud = (
                    st.form_submit_button(
                        "💾 Guardar actualización",
                        type="primary",
                        width="stretch",
                    )
                )

            if guardar_estado_solicitud:

                usuario_logistica = (
                    st.session_state.get("usuario")
                    or st.session_state.get("nombre_usuario")
                    or "Logística"
                )

                try:

                    resultado_actualizacion = actualizar_solicitud(
                        solicitud_id=solicitud_id,
                        estado_solicitud=nuevo_estado_solicitud,
                        responsable=usuario_logistica,
                        respuesta=observacion_logistica,
                    )

                    st.success(
                        resultado_actualizacion["mensaje"]
                    )

                    st.toast(
                        "Solicitud actualizada.",
                        icon="✅",
                    )

                    st.rerun()

                except Exception as error:

                    st.error(
                        "No se pudo actualizar la solicitud."
                    )

                    st.exception(error)


        if solicitudes_abiertas.empty:

            st.success(
                "No hay solicitudes comerciales pendientes.",
                icon="✅",
            )

        else:

            total_solicitudes_abiertas = len(solicitudes_abiertas)
            pedidos_con_solicitud = solicitudes_abiertas["Pedido"].nunique()

            prioridad_alta = int(
                solicitudes_abiertas["Prioridad"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("ALTA")
                .sum()
            )

            cantidad_cancelaciones = int(
                solicitudes_abiertas["TipoSolicitud"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .isin({"CANCELACIÓN", "CANCELACION"})
                .sum()
            )

            st.warning(
                (
                    f"Hay {total_solicitudes_abiertas} solicitudes "
                    f"comerciales pendientes sobre "
                    f"{pedidos_con_solicitud} pedidos."
                ),
                icon="📩",
            )

            with st.expander(
                (
                    f"📩 Solicitudes comerciales "
                    f"({total_solicitudes_abiertas})"
                ),
                expanded=False,
            ):

                (
                    resumen_col_1,
                    resumen_col_2,
                    resumen_col_3,
                    resumen_col_4,
                ) = st.columns(4)

                resumen_col_1.metric(
                    "Abiertas",
                    total_solicitudes_abiertas,
                )

                resumen_col_2.metric(
                    "Pedidos",
                    pedidos_con_solicitud,
                )

                resumen_col_3.metric(
                    "Prioridad alta",
                    prioridad_alta,
                )

                resumen_col_4.metric(
                    "Cancelaciones",
                    cantidad_cancelaciones,
                    help=(
                        "Solicitudes abiertas de Cancelación que "
                        "requieren revisión prioritaria."
                    ),
                )

                solicitudes_abiertas_ordenadas = (
                    solicitudes_abiertas
                    .assign(
                        EsCancelacion=(
                            solicitudes_abiertas["TipoSolicitud"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                            .str.upper()
                            .isin({"CANCELACIÓN", "CANCELACION"})
                            .astype(int)
                        ),
                        EsPrioridadAlta=(
                            solicitudes_abiertas["Prioridad"]
                            .fillna("")
                            .astype(str)
                            .str.strip()
                            .str.upper()
                            .eq("ALTA")
                            .astype(int)
                        ),
                    )
                    .sort_values(
                        by=[
                            "EsCancelacion",
                            "EsPrioridadAlta",
                            "FechaSolicitudOrden",
                        ],
                        ascending=[False, False, False],
                        na_position="last",
                    )
                    .reset_index(drop=True)
                )

                tabla_solicitudes_visible = (
                    solicitudes_abiertas_ordenadas[
                        [
                            "SolicitudID",
                            "Pedido",
                            "Cliente",
                            "TipoSolicitud",
                            "Prioridad",
                            "TotalUnidades",
                            "TotalM3",
                            "Descripcion",
                            "FechaSolicitudVisible",
                            "EstadoSolicitud",
                            "Responsable",
                        ]
                    ]
                    .rename(
                        columns={
                            "SolicitudID": "ID",
                            "TipoSolicitud": "Tipo",
                            "Descripcion": "Detalle",
                            "FechaSolicitudVisible": "Fecha",
                            "EstadoSolicitud": "Estado",
                        }
                    )
                    .reset_index(drop=True)
                )

                evento_solicitudes = st.dataframe(
                    tabla_solicitudes_visible,
                    width="stretch",
                    hide_index=True,
                    height=min(
                        340,
                        85 + len(tabla_solicitudes_visible) * 35,
                    ),
                    on_select="rerun",
                    selection_mode="single-row",
                    key="tabla_solicitudes_comerciales",
                    column_config={
                        "ID": None,
                        "Pedido": st.column_config.TextColumn(
                            "Pedido",
                            width="small",
                        ),
                        "Cliente": st.column_config.TextColumn(
                            "Cliente",
                            width="medium",
                        ),
                        "Tipo": st.column_config.TextColumn(
                            "Solicitud",
                            width="medium",
                        ),
                        "Prioridad": st.column_config.TextColumn(
                            "Prioridad",
                            width="small",
                        ),
                        "Detalle": st.column_config.TextColumn(
                            "Detalle",
                            width="large",
                        ),
                        "Fecha": st.column_config.TextColumn(
                            "Fecha",
                            width="small",
                        ),
                        "Estado": st.column_config.TextColumn(
                            "Estado",
                            width="small",
                        ),
                        "Responsable": st.column_config.TextColumn(
                            "Responsable",
                            width="small",
                        ),
                    },
                )

                filas_seleccionadas = (
                    evento_solicitudes.selection.rows
                    if evento_solicitudes is not None
                    else []
                )

                accion_col_1, accion_col_2 = st.columns(
                    [4, 1],
                    vertical_alignment="center",
                )

                with accion_col_1:

                    if filas_seleccionadas:

                        fila_seleccionada = filas_seleccionadas[0]

                        solicitud_seleccionada = (
                            tabla_solicitudes_visible.iloc[
                                fila_seleccionada
                            ]
                        )

                        st.caption(
                            f"Seleccionada: pedido "
                            f"**{solicitud_seleccionada['Pedido']}** · "
                            f"{solicitud_seleccionada['Tipo']}"
                        )

                    else:

                        st.caption(
                            "Seleccioná una fila para gestionar la solicitud."
                        )

                with accion_col_2:

                    gestionar_solicitud = st.button(
                        "Gestionar",
                        icon="📩",
                        type="primary",
                        width="stretch",
                        disabled=not bool(filas_seleccionadas),
                        key="btn_gestionar_solicitud_seleccionada",
                    )

                if gestionar_solicitud and filas_seleccionadas:

                    indice_seleccionado = filas_seleccionadas[0]

                    solicitud_id_seleccionada = str(
                        tabla_solicitudes_visible.iloc[
                            indice_seleccionado
                        ]["ID"]
                    )

                    abrir_gestion_solicitud(
                        solicitud_id_seleccionada
                    )


        st.markdown("---")


        # =====================================================
        # CONTENEDOR DE KPIs
        # Se crea acá para que aparezca arriba de los filtros
        # =====================================================

        contenedor_kpis = st.container()

        st.markdown("---")

        # =====================================================
        # OPCIONES DISPONIBLES PARA LOS FILTROS
        # =====================================================

        opciones_estado = sorted(
            tabla["Estado"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.str.strip().ne("")]
            .unique()
            .tolist()
        )

        opciones_preparacion = sorted(
            tabla["PreparacionEstado"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.str.strip().ne("")]
            .unique()
            .tolist()
        )

        opciones_planificacion = sorted(
            tabla["Planificacion"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.str.strip().ne("")]
            .unique()
            .tolist()
        )

        opciones_despacho = sorted(
            tabla["DespachoDescripcion"]
            .dropna()
            .astype(str)
            .loc[lambda serie: serie.str.strip().ne("")]
            .unique()
            .tolist()
        )

        fecha_minima = tabla["Fecha"].min()
        fecha_maxima = tabla["Fecha"].max()


        # =====================================================
        # ESTADO INICIAL DE LOS FILTROS
        # =====================================================

        if "filtros_pedidos" not in st.session_state:

            st.session_state["filtros_pedidos"] = {
                "estados": [],
                "preparaciones": [],
                "planificaciones": [],
                "despachos": [],
                "fecha_desde": (
                    fecha_minima.date()
                    if pd.notna(fecha_minima)
                    else None
                ),
                "fecha_hasta": (
                    fecha_maxima.date()
                    if pd.notna(fecha_maxima)
                    else None
                ),
                "busqueda": ""
            }
        # Ajustar las fechas guardadas al rango actual de los datos
        if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

            fecha_minima_actual = fecha_minima.date()
            fecha_maxima_actual = fecha_maxima.date()

            fecha_desde_guardada = st.session_state[
                "filtros_pedidos"
            ].get("fecha_desde")

            fecha_hasta_guardada = st.session_state[
                "filtros_pedidos"
            ].get("fecha_hasta")

            if (
                fecha_desde_guardada is None
                or fecha_desde_guardada < fecha_minima_actual
                or fecha_desde_guardada > fecha_maxima_actual
            ):
                st.session_state[
                    "filtros_pedidos"
                ]["fecha_desde"] = fecha_minima_actual

            if (
                fecha_hasta_guardada is None
                or fecha_hasta_guardada > fecha_maxima_actual
                or fecha_hasta_guardada < fecha_minima_actual
            ):
                st.session_state[
                    "filtros_pedidos"
                ]["fecha_hasta"] = fecha_maxima_actual

        filtros_aplicados = st.session_state["filtros_pedidos"]


        # =====================================================
        # APLICAR LOS FILTROS GUARDADOS
        # =====================================================

        tabla_filtrada = tabla.copy()

        if filtros_aplicados["estados"]:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["Estado"].isin(
                    filtros_aplicados["estados"]
                )
            ]

        if filtros_aplicados["preparaciones"]:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["PreparacionEstado"].isin(
                    filtros_aplicados["preparaciones"]
                )
            ]

        if filtros_aplicados["planificaciones"]:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["Planificacion"].isin(
                    filtros_aplicados["planificaciones"]
                )
            ]

        if filtros_aplicados["despachos"]:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["DespachoDescripcion"].isin(
                    filtros_aplicados["despachos"]
                )
            ]

        fecha_desde = filtros_aplicados["fecha_desde"]
        fecha_hasta = filtros_aplicados["fecha_hasta"]

        if fecha_desde is not None:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["Fecha"].ge(
                    pd.Timestamp(fecha_desde)
                )
            ]

        if fecha_hasta is not None:

            tabla_filtrada = tabla_filtrada[
                tabla_filtrada["Fecha"].lt(
                    pd.Timestamp(fecha_hasta)
                    + pd.Timedelta(days=1)
                )
            ]

        texto_busqueda = filtros_aplicados["busqueda"]

        if texto_busqueda:

            mascara_busqueda = (
                tabla_filtrada["Pedido"]
                .astype(str)
                .str.contains(
                    texto_busqueda,
                    case=False,
                    na=False
                )
                |
                tabla_filtrada["ClienteCodigo"]
                .astype(str)
                .str.contains(
                    texto_busqueda,
                    case=False,
                    na=False
                )
                |
                tabla_filtrada["ClienteDescripcion"]
                .astype(str)
                .str.contains(
                    texto_busqueda,
                    case=False,
                    na=False
                )
            )

            tabla_filtrada = tabla_filtrada[
                mascara_busqueda
            ]


        # =====================================================
        # BASE ÚNICA PARA KPIs
        # =====================================================

        tabla_kpis = (
            tabla_filtrada
            .drop_duplicates(
                subset=["Pedido"],
                keep="first"
            )
            .copy()
        )


        # =====================================================
        # CÁLCULO DE KPIs
        # =====================================================

        total_pedidos = tabla_kpis["Pedido"].nunique()

        total_unidades = int(
            tabla_kpis["TotalUnidades"].sum()
        )

        total_volumetria = float(
            tabla_kpis["TotalM3"].sum()
        )

        total_importe = float(
            tabla_kpis["ImporteERP"].sum()
        )

        pedidos_en_preparacion = int(
            tabla_kpis["PreparacionEstado"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
            .sum()
        )


        # =====================================================
        # MOSTRAR KPIs ARRIBA DE LOS FILTROS
        # =====================================================

        with contenedor_kpis:

            st.subheader("📊 Resumen Operativo")

            kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)

            with kpi1:

                st.metric(
                    "📦 Pedidos",
                    f"{total_pedidos:,}".replace(",", ".")
                )

            with kpi2:

                st.metric(
                    "🔢 Unidades",
                    f"{total_unidades:,}".replace(",", ".")
                )

            with kpi3:

                st.metric(
                    "📐 Volumen total",
                    f"{total_volumetria:,.3f} m³"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

            with kpi4:

                st.metric(
                    "🛒 Con preparación",
                    f"{pedidos_en_preparacion:,}"
                    .replace(",", ".")
                )

            with kpi5:

                st.metric(
                    "📩 Solicitudes",
                    f"{len(solicitudes_abiertas):,}"
                    .replace(",", ".")
                )

            with kpi6:

                st.metric(
                    "💰 Importe",
                    f"$ {total_importe:,.0f}"
                    .replace(",", ".")
                )



        # =====================================================
        # AGRUPADORES REALES DE DIGIP
        # El planificador de camionetas fue trasladado a 03_Despachos.py.

        # =====================================================
        # FILTROS DE LA TABLA OPERATIVA
        # Se muestran después de la planificación de camionetas.
        # Los filtros guardados ya fueron aplicados previamente
        # para calcular los KPIs y la propuesta de planificación.
        # =====================================================

        st.markdown("---")

        st.subheader("🔎 Filtros de la Tabla Operativa")

        with st.form(
            key="formulario_filtros_pedidos",
            clear_on_submit=False
        ):

            filtro1, filtro2, filtro3, filtro4 = st.columns(4)

            with filtro1:

                estados_form = st.multiselect(
                    "Estado",
                    options=opciones_estado,
                    default=filtros_aplicados["estados"]
                )

            with filtro2:

                preparaciones_form = st.multiselect(
                    "Estado preparación",
                    options=opciones_preparacion,
                    default=filtros_aplicados["preparaciones"]
                )

            with filtro3:

                planificaciones_form = st.multiselect(
                    "Planificación",
                    options=opciones_planificacion,
                    default=filtros_aplicados["planificaciones"]
                )

            with filtro4:

                despachos_form = st.multiselect(
                    "Despacho",
                    options=opciones_despacho,
                    default=filtros_aplicados["despachos"]
                )

            filtro5, filtro6 = st.columns([1, 2])

            with filtro5:

                if pd.notna(fecha_minima) and pd.notna(fecha_maxima):

                    rango_fechas_form = st.date_input(
                        "Rango de fechas",
                        value=(
                            filtros_aplicados["fecha_desde"],
                            filtros_aplicados["fecha_hasta"]
                        ),
                        min_value=fecha_minima.date(),
                        max_value=fecha_maxima.date()
                    )

                else:

                    rango_fechas_form = None

            with filtro6:

                busqueda_form = st.text_input(
                    "Buscar pedido o cliente",
                    value=filtros_aplicados["busqueda"],
                    placeholder=(
                        "Número de pedido, código "
                        "o nombre del cliente..."
                    )
                )

                boton1, boton2 = st.columns(2)

                with boton1:

                    aplicar_filtros = st.form_submit_button(
                        "🔎 Aplicar filtros",
                        width="stretch",
                        type="primary"
                    )

                with boton2:

                    quitar_filtros = st.form_submit_button(
                        "🧹 Quitar filtros",
                        width="stretch"
                    )


        # =====================================================
        # GUARDAR O QUITAR FILTROS
        # =====================================================

        if quitar_filtros:

            st.session_state["filtros_pedidos"] = {
                "estados": [],
                "preparaciones": [],
                "planificaciones": [],
                "despachos": [],
                "fecha_desde": (
                    fecha_minima.date()
                    if pd.notna(fecha_minima)
                    else None
                ),
                "fecha_hasta": (
                    fecha_maxima.date()
                    if pd.notna(fecha_maxima)
                    else None
                ),
                "busqueda": ""
            }

            st.rerun()


        if aplicar_filtros:

            if (
                rango_fechas_form
                and len(rango_fechas_form) == 2
            ):

                fecha_desde_form = rango_fechas_form[0]
                fecha_hasta_form = rango_fechas_form[1]

            else:

                fecha_desde_form = None
                fecha_hasta_form = None

            st.session_state["filtros_pedidos"] = {
                "estados": estados_form,
                "preparaciones": preparaciones_form,
                "planificaciones": planificaciones_form,
                "despachos": despachos_form,
                "fecha_desde": fecha_desde_form,
                "fecha_hasta": fecha_hasta_form,
                "busqueda": busqueda_form.strip()
            }

            # La planificación y la tabla fueron calculadas antes de
            # renderizar este formulario. Se relanza la página para que
            # ambos bloques utilicen inmediatamente los nuevos filtros.
            st.rerun()


        # =====================================================
        # DESCARGA
        # =====================================================

        csv_tabla_operativa = (
            tabla_filtrada.to_csv(
                index=False,
                sep=";",
                encoding="utf-8-sig",
                date_format="%d/%m/%Y"
            )
            .encode("utf-8-sig")
        )

        st.download_button(
            label="⬇️ Descargar tabla operativa",
            data=csv_tabla_operativa,
            file_name="Tabla_Operativa_Pedidos.csv",
            mime="text/csv",
            width="stretch"
        )


        # =====================================================
        # TABLA
        # =====================================================

        st.subheader("📋 Tabla Operativa")

        st.caption(
            f"{len(tabla_filtrada):,} registros visibles · "
            f"{tabla_filtrada['Pedido'].nunique():,} pedidos únicos · "
            f"{len(tabla):,} registros totales"
            .replace(",", ".")
        )

        st.dataframe(
            tabla_filtrada,
            width="stretch",
            hide_index=True,
            height=750,
            column_config={

                "Fecha": st.column_config.DateColumn(
                    "Fecha",
                    format="DD/MM/YYYY"
                ),

                "FechaTransmisionERP": st.column_config.DateColumn(
                    "Fecha transmisión",
                    format="DD/MM/YYYY"
                ),

                "HoraTransmisionERP": st.column_config.TextColumn(
                    "Hora transmisión"
                ),

                "TotalUnidades": st.column_config.NumberColumn(
                    "Unidades",
                    format="%d"
                ),
                "TotalM3": st.column_config.NumberColumn(
                 "M³",
                format="%.3f"
                ),

                "TotalSKUs": st.column_config.NumberColumn(
                    "SKUs",
                    format="%d"
                ),

                "ImporteERP": st.column_config.NumberColumn(
                    "Importe ERP",
                    format="$ %.0f"
                ),
            }
        )

