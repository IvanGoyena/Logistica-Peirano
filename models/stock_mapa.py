import pandas as pd
import altair as alt
import plotly.graph_objects as go
import streamlit as st

from utils.stock_helpers import dataframe_para_streamlit, formato_entero

def _ordenar_segmento_mapa(valor):
    texto = str(valor or "").strip()
    numero = pd.to_numeric(texto, errors="coerce")
    if pd.notna(numero):
        return (0, float(numero), texto)
    return (1, 0, texto)


def _grupo_mapa(fila: pd.Series) -> str:
    grupo = str(fila.get("GrupoOcupacion", "")).strip()
    pasillo = str(fila.get("Pasillo", "")).strip().lstrip("0") or "0"
    tercio = str(fila.get("Tercio", "")).strip().upper()

    if grupo == "Picking":
        if pasillo == "20" or tercio == "CAJONES":
            return "Cajones"
        return "Picking Rack"
    return grupo


def preparar_mapa_ubicaciones(tabla_ocupacion: pd.DataFrame) -> pd.DataFrame:
    if tabla_ocupacion is None or tabla_ocupacion.empty:
        return pd.DataFrame()

    mapa = tabla_ocupacion.copy()
    mapa["SectorMapa"] = mapa.apply(_grupo_mapa, axis=1)
    mapa["EstadoMapa"] = "Vacía"
    mapa.loc[~mapa["Disponible"].fillna(False), "EstadoMapa"] = "No disponible"
    mapa.loc[mapa["Disponible"].fillna(False) & mapa["Ocupada"].fillna(False), "EstadoMapa"] = "Ocupada"

    mapa["PasilloMapa"] = mapa["Pasillo"].astype("string").fillna("").str.strip()
    mapa["PosicionMapa"] = mapa["Posicion"].astype("string").fillna("").str.strip()
    mapa["NivelMapa"] = mapa["Nivel"].astype("string").fillna("").str.strip()
    mapa["AreaMapa"] = mapa["Area"].astype("string").fillna("SIN ÁREA").str.strip().replace("", "SIN ÁREA")
    mapa["EtiquetaUbicacion"] = (
        mapa["Ab"].astype("string").fillna("") + "-"
        + mapa["PasilloMapa"] + "-"
        + mapa["PosicionMapa"] + "-"
        + mapa["NivelMapa"]
    )
    mapa["ContenedoresMapa"] = pd.to_numeric(
        mapa.get("ContenedoresOcupados", 0), errors="coerce"
    ).fillna(0)

    return mapa



def _coordenadas_posiciones_3d(detalle, orden_posiciones):
    """Calcula X compactas y abre una calle visible al cambiar de tercio."""
    tercio_por_posicion = {}
    if "Tercio" in detalle.columns:
        for posicion, grupo in detalle.groupby("PosicionMapa", dropna=False):
            valores = (
                grupo["Tercio"].astype("string").fillna("").str.strip()
            )
            tercio_por_posicion[str(posicion)] = next(
                (valor for valor in valores if valor), ""
            )

    ancho_cubo = 32.5
    separacion_normal = 0.5
    separacion_tercio = 1.9

    posiciones_x = {}
    limites_tercios = {}
    cursor = 0.0
    tercio_anterior = None

    for indice, posicion in enumerate(orden_posiciones):
        posicion_txt = str(posicion)
        tercio_actual = tercio_por_posicion.get(posicion_txt, "") or "SIN TERCIO"

        if indice > 0:
            cursor += separacion_normal
            if tercio_actual != tercio_anterior:
                cursor += separacion_tercio

        posiciones_x[posicion_txt] = cursor

        if tercio_actual not in limites_tercios:
            limites_tercios[tercio_actual] = [cursor, cursor + ancho_cubo]
        else:
            limites_tercios[tercio_actual][1] = cursor + ancho_cubo

        cursor += ancho_cubo
        tercio_anterior = tercio_actual

    return posiciones_x, limites_tercios, ancho_cubo


def _agregar_cubos_3d(
    figura,
    datos_estado,
    color,
    nombre,
    posiciones_x,
    niveles_idx,
    ancho_cubo,
):
    """Dibuja una ubicación como un cubo/prisma robusto y agrega sus aristas."""
    if datos_estado.empty:
        return

    profundidad = 0.88
    alto = 1.10

    xs, ys, zs = [], [], []
    ii, jj, kk = [], [], []
    hover_x, hover_y, hover_z, hover_text = [], [], [], []
    line_x, line_y, line_z = [], [], []

    caras = [
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    ]
    aristas = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]

    for _, fila in datos_estado.iterrows():
        x0 = posiciones_x.get(str(fila["PosicionMapa"]), 0.0)
        z0 = niveles_idx.get(str(fila["NivelMapa"]), 0) * 1.20
        x1 = x0 + ancho_cubo
        y0, y1 = 0.0, profundidad
        z1 = z0 + alto

        vertices = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
        base_idx = len(xs)
        for vx, vy, vz in vertices:
            xs.append(vx); ys.append(vy); zs.append(vz)
        for a, b, c in caras:
            ii.append(base_idx + a); jj.append(base_idx + b); kk.append(base_idx + c)

        for a, b in aristas:
            line_x.extend([vertices[a][0], vertices[b][0], None])
            line_y.extend([vertices[a][1], vertices[b][1], None])
            line_z.extend([vertices[a][2], vertices[b][2], None])

        hover_x.append(x0 + ancho_cubo / 2)
        hover_y.append(profundidad / 2)
        hover_z.append(z0 + alto / 2)
        hover_text.append(
            f"<b>{fila.get('EtiquetaUbicacion', '')}</b><br>"
            f"Área: {fila.get('AreaMapa', '')}<br>"
            f"Posición: {fila.get('PosicionMapa', '')}<br>"
            f"Nivel: {fila.get('NivelMapa', '')}<br>"
            f"Tercio: {fila.get('Tercio', '')}<br>"
            f"Estado: {fila.get('EstadoMapa', '')}<br>"
            f"Contenedores: {int(fila.get('ContenedoresMapa', 0) or 0)}"
        )

    figura.add_trace(go.Mesh3d(
        x=xs, y=ys, z=zs,
        i=ii, j=jj, k=kk,
        color=color,
        opacity=0.96,
        flatshading=True,
        name=nombre,
        hoverinfo="skip",
        showscale=False,
        lighting=dict(ambient=0.58, diffuse=0.78, roughness=0.62, specular=0.16),
        lightposition=dict(x=80, y=-120, z=140),
    ))

    # Aristas oscuras: hacen que cada fila/ubicación se lea como un cubo.
    figura.add_trace(go.Scatter3d(
        x=line_x, y=line_y, z=line_z,
        mode="lines",
        line=dict(color="rgba(15,23,42,0.88)", width=2.2),
        hoverinfo="skip",
        showlegend=False,
    ))

    figura.add_trace(go.Scatter3d(
        x=hover_x, y=hover_y, z=hover_z,
        mode="markers",
        marker=dict(size=8, color=color, opacity=0.01),
        text=hover_text,
        hovertemplate="%{text}<extra></extra>",
        name=f"Detalle {nombre}",
        showlegend=False,
    ))


def _agregar_marcos_tercios(figura, limites_tercios, altura_total):
    """Dibuja el marco externo y el nombre de cada tercio."""
    profundidad = 0.88
    for tercio, (x_inicio, x_fin) in limites_tercios.items():
        z_sup = altura_total + 0.10
        marco_x = [
            x_inicio, x_fin, x_fin, x_inicio, x_inicio, None,
            x_inicio, x_inicio, None, x_fin, x_fin,
        ]
        marco_y = [
            0, 0, profundidad, profundidad, 0, None,
            0, 0, None, 0, 0,
        ]
        marco_z = [
            0, 0, 0, 0, 0, None,
            0, z_sup, None, 0, z_sup,
        ]
        figura.add_trace(go.Scatter3d(
            x=marco_x, y=marco_y, z=marco_z,
            mode="lines",
            line=dict(color="rgba(100,116,139,0.95)", width=5),
            hoverinfo="skip",
            showlegend=False,
        ))
        figura.add_trace(go.Scatter3d(
            x=[(x_inicio + x_fin) / 2],
            y=[profundidad / 2],
            z=[z_sup + 0.28],
            mode="text",
            text=[f"<b>TERCIO {tercio}</b>" if str(tercio).isdigit() else f"<b>{tercio}</b>"],
            textfont=dict(color="#FACC15", size=12),
            hoverinfo="skip",
            showlegend=False,
        ))


def construir_mapa_3d(detalle, orden_posiciones, orden_niveles, titulo):
    posiciones_x, limites_tercios, ancho_cubo = _coordenadas_posiciones_3d(
        detalle, orden_posiciones
    )
    niveles_asc = list(reversed(orden_niveles))
    niveles_idx = {str(valor): indice for indice, valor in enumerate(niveles_asc)}

    figura = go.Figure()
    configuracion = [
        ("Ocupada", "#22C55E"),
        ("Vacía", "#D1D5DB"),
        ("No disponible", "#EF4444"),
    ]
    for estado, color in configuracion:
        _agregar_cubos_3d(
            figura,
            detalle.loc[detalle["EstadoMapa"].eq(estado)],
            color,
            estado,
            posiciones_x,
            niveles_idx,
            ancho_cubo,
        )

    altura_total = max(1.10, len(niveles_asc) * 1.20 - 0.10)
    _agregar_marcos_tercios(figura, limites_tercios, altura_total)

    tick_x = [
        posiciones_x[str(valor)] + ancho_cubo / 2
        for valor in orden_posiciones
    ]
    extension_x = max(
        (posiciones_x[str(valor)] + ancho_cubo for valor in orden_posiciones),
        default=1.0,
    )

    figura.update_layout(
        title=dict(text=titulo, x=0.02),
        height=430,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.02, x=0.02),
        scene=dict(
            bgcolor="rgba(0,0,0,0)",
            aspectmode="manual",
            # Vista compacta pero con bloques gruesos.
            aspectratio=dict(
                x=min(4.5, max(2.7, extension_x / 12.0)),
                y=1.0,
                z=max(1.65, len(niveles_asc) / 2.0),
            ),
            camera=dict(
                eye=dict(x=1.45, y=-2.15, z=1.45),
                up=dict(x=0, y=0, z=1),
            ),
            xaxis=dict(
                title="Posición",
                range=[-0.40, extension_x + 0.40],
                tickmode="array",
                tickvals=tick_x,
                ticktext=orden_posiciones,
                showgrid=False,
                zeroline=False,
                tickangle=-90,
            ),
            yaxis=dict(
                title="Profundidad",
                range=[-0.10, 1.05],
                showticklabels=False,
                showgrid=False,
                zeroline=False,
            ),
            zaxis=dict(
                title="Nivel",
                range=[-0.10, altura_total + 0.75],
                tickmode="array",
                tickvals=[i * 1.20 + 0.55 for i in range(len(niveles_asc))],
                ticktext=niveles_asc,
                showgrid=False,
                zeroline=False,
            ),
        ),
    )
    return figura

def mostrar_mapa_visual_deposito(tabla_ocupacion: pd.DataFrame) -> None:
    mapa = preparar_mapa_ubicaciones(tabla_ocupacion)
    if mapa.empty:
        st.info("No hay datos disponibles para construir el mapa visual.")
        return

    # Las superficies de piso se analizarán luego con un plano específico.
    sectores_rack = [
        sector for sector in [
            "Almacén", "Pasillo", "Picking Rack", "Cajones", "Estanterías"
        ] if sector in mapa["SectorMapa"].unique()
    ]

    st.markdown("---")
    st.markdown(
        """
        <div style="margin-top:.35rem;margin-bottom:.8rem">
          <h2 style="margin:0">🗺️ Mapa visual del depósito</h2>
          <div style="color:#94A3B8;margin-top:.2rem">
            Cada celda representa una ubicación física del maestro. Seleccioná un sector y un pasillo para recorrer el rack nivel por nivel.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Vista general por pasillo
    mapa_racks = mapa.loc[mapa["SectorMapa"].isin(sectores_rack)].copy()

    if mapa_racks.empty:
        st.warning(
            "El Maestro Ubicaciones fue leído, pero no se encontraron sectores "
            "válidos para el mapa. Revisá GrupoOcupacion y SectorMapa."
        )
        return

    resumen_pasillos = (
        mapa_racks.groupby(["SectorMapa", "PasilloMapa"], dropna=False)
        .agg(
            TotalUbicaciones=("ClaveUbicacion", "nunique"),
            UbicacionesOcupadas=("Ocupada", lambda serie: int(serie.fillna(False).astype(bool).sum())),
            UbicacionesDisponibles=("Disponible", lambda serie: int(serie.fillna(False).astype(bool).sum())),
        )
        .reset_index()
    )
    resumen_pasillos["UbicacionesVacias"] = (
        resumen_pasillos["UbicacionesDisponibles"]
        - resumen_pasillos["UbicacionesOcupadas"]
    ).clip(lower=0)
    resumen_pasillos["PorcentajeOcupacion"] = (
        resumen_pasillos["UbicacionesOcupadas"]
        .div(resumen_pasillos["UbicacionesDisponibles"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .astype(float)
    )
    resumen_pasillos["PasilloOrden"] = pd.to_numeric(
        resumen_pasillos["PasilloMapa"], errors="coerce"
    ).fillna(9999)
    resumen_pasillos = resumen_pasillos.sort_values(
        ["SectorMapa", "PasilloOrden", "PasilloMapa"]
    ).reset_index(drop=True)

    with st.container(border=True):
        encabezado_grafico, filtro_grafico = st.columns([2.4, 1])
        with encabezado_grafico:
            st.markdown("#### Vista general por pasillo")
            st.caption(
                "Permite detectar rápidamente pasillos saturados o con capacidad disponible, "
                "sin ampliar horizontalmente la página."
            )
        with filtro_grafico:
            sector_resumen = st.selectbox(
                "Sector a comparar",
                options=sectores_rack,
                key="mapa_sector_resumen_pasillos",
            )

        resumen_sector = resumen_pasillos.loc[
            resumen_pasillos["SectorMapa"].eq(sector_resumen)
        ].copy()

        grafico_pasillos = (
            alt.Chart(resumen_sector)
            .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=16)
            .encode(
                x=alt.X(
                    "PasilloMapa:N",
                    title="Pasillo",
                    sort=alt.SortField(field="PasilloOrden", order="ascending"),
                    axis=alt.Axis(labelAngle=0, labelOverlap=True, labelLimit=45),
                ),
                y=alt.Y(
                    "PorcentajeOcupacion:Q",
                    title="% de ocupación",
                    scale=alt.Scale(domain=[0, 100]),
                ),
                color=alt.value({
                    "Almacén": "#3B82F6",
                    "Pasillo": "#2563EB",
                    "Picking Rack": "#8B5CF6",
                    "Cajones": "#A855F7",
                    "Estanterías": "#65A30D",
                }.get(sector_resumen, "#3B82F6")),
                tooltip=[
                    alt.Tooltip("PasilloMapa:N", title="Pasillo"),
                    alt.Tooltip("UbicacionesOcupadas:Q", title="Ocupadas", format=",.0f"),
                    alt.Tooltip("UbicacionesVacias:Q", title="Vacías", format=",.0f"),
                    alt.Tooltip("UbicacionesDisponibles:Q", title="Disponibles", format=",.0f"),
                    alt.Tooltip("PorcentajeOcupacion:Q", title="Ocupación", format=".1f"),
                ],
            )
            .properties(height=245, title=sector_resumen)
        )

        st.altair_chart(
            grafico_pasillos,
            use_container_width=True,
            key="mapa_resumen_pasillos_compacto",
        )

    # =====================================================
    # VISUALIZACIÓN DETALLADA CON FILTROS LATERALES
    # =====================================================
    st.markdown("#### Visualización del pasillo seleccionado")
    st.caption(
        "Elegí un sector, área y pasillo. Los filtros de este bloque son independientes "
        "de la vista general superior."
    )

    panel_filtros, panel_mapa = st.columns([0.9, 3.1], gap="large")

    with panel_filtros:
        with st.container(border=True):
            st.markdown("##### Filtros del mapa")

            sector_seleccionado = st.selectbox(
                "Sector",
                options=sectores_rack,
                key="mapa_sector_seleccionado",
            )

            base_sector = mapa.loc[
                mapa["SectorMapa"].eq(sector_seleccionado)
            ].copy()

            areas = sorted(
                base_sector["AreaMapa"].dropna().unique().tolist()
            )
            area_seleccionada = st.selectbox(
                "Área",
                options=["Todas"] + areas,
                key="mapa_area_seleccionada",
            )

            if area_seleccionada != "Todas":
                base_sector = base_sector.loc[
                    base_sector["AreaMapa"].eq(area_seleccionada)
                ].copy()

            pasillos = sorted(
                base_sector["PasilloMapa"].dropna().unique().tolist(),
                key=_ordenar_segmento_mapa,
            )

            if not pasillos:
                st.info("No hay pasillos para la selección realizada.")
                return

            pasillo_seleccionado = st.selectbox(
                "Pasillo",
                options=pasillos,
                key="mapa_pasillo_seleccionado",
            )

            vista_mapa = st.radio(
                "Vista",
                options=["2D", "3D"],
                horizontal=True,
                key="mapa_tipo_vista_pasillo",
            )

        detalle = base_sector.loc[
            base_sector["PasilloMapa"].eq(pasillo_seleccionado)
        ].copy()

        if detalle.empty:
            st.info("No se encontraron ubicaciones para la selección realizada.")
            return

        total = int(len(detalle))
        disponibles = int(detalle["Disponible"].sum())
        ocupadas = int((detalle["Disponible"] & detalle["Ocupada"]).sum())
        vacias = max(disponibles - ocupadas, 0)
        no_disponibles = max(total - disponibles, 0)
        porcentaje = ocupadas / disponibles * 100 if disponibles else 0

        with st.container(border=True):
            st.markdown("##### Resumen del pasillo")
            st.metric("Ubicaciones", formato_entero(total))
            r1, r2 = st.columns(2)
            r1.metric("Ocupadas", formato_entero(ocupadas))
            r2.metric("Vacías", formato_entero(vacias))
            st.metric("No disponibles", formato_entero(no_disponibles))
            st.metric("Ocupación", f"{porcentaje:.1f}%")
            st.progress(min(max(porcentaje / 100, 0), 1))

        with st.container(border=True):
            st.markdown("##### Referencia")
            st.markdown(
                "<div style='font-size:.86rem;line-height:1.8'>"
                "<div><b style='color:#22C55E'>■</b> Ocupada</div>"
                "<div><b style='color:#E5E7EB'>■</b> Vacía</div>"
                "<div><b style='color:#EF4444'>■</b> No disponible</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    orden_posiciones = sorted(
        detalle["PosicionMapa"].dropna().unique().tolist(),
        key=_ordenar_segmento_mapa,
    )
    orden_niveles = sorted(
        detalle["NivelMapa"].dropna().unique().tolist(),
        key=_ordenar_segmento_mapa,
        reverse=True,
    )

    detalle["TextoCelda"] = detalle["ContenedoresMapa"].apply(
        lambda valor: "" if valor <= 0 else str(int(valor))
    )

    base_rect = (
        alt.Chart(detalle)
        .mark_rect(cornerRadius=2, stroke="#111827", strokeWidth=1.2)
        .encode(
            x=alt.X(
                "PosicionMapa:N",
                title="Posición",
                sort=orden_posiciones,
                axis=alt.Axis(labelAngle=0, labelLimit=60),
            ),
            y=alt.Y(
                "NivelMapa:N",
                title="Nivel",
                sort=orden_niveles,
            ),
            color=alt.Color(
                "EstadoMapa:N",
                title="Estado",
                scale=alt.Scale(
                    domain=["Ocupada", "Vacía", "No disponible"],
                    range=["#22C55E", "#E5E7EB", "#EF4444"],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("EtiquetaUbicacion:N", title="Ubicación"),
                alt.Tooltip("AreaMapa:N", title="Área"),
                alt.Tooltip("PasilloMapa:N", title="Pasillo"),
                alt.Tooltip("PosicionMapa:N", title="Posición"),
                alt.Tooltip("NivelMapa:N", title="Nivel"),
                alt.Tooltip("Tercio:N", title="Tercio"),
                alt.Tooltip("EstadoMapa:N", title="Estado"),
                alt.Tooltip("ContenedoresMapa:Q", title="Contenedores", format=",.0f"),
                alt.Tooltip("CodigoVerificador:N", title="Código verificador"),
            ],
        )
    )

    texto = (
        alt.Chart(detalle.loc[detalle["ContenedoresMapa"].gt(0)])
        .mark_text(fontSize=9, fontWeight="bold", color="#0F172A")
        .encode(
            x=alt.X("PosicionMapa:N", sort=orden_posiciones),
            y=alt.Y("NivelMapa:N", sort=orden_niveles),
            text="TextoCelda:N",
        )
    )

    alto_mapa = max(230, min(360, len(orden_niveles) * 46))
    mapa_chart = (base_rect + texto).properties(
        height=alto_mapa,
        title=f"{sector_seleccionado} · Pasillo {pasillo_seleccionado} · Vista 2D",
    )

    with panel_mapa:
        with st.container(border=True):
            st.markdown(
                f"##### {sector_seleccionado} · Pasillo {pasillo_seleccionado} · "
                f"{'Plano 2D' if vista_mapa == '2D' else 'Modelo 3D'}"
            )

            if vista_mapa == "2D":
                st.altair_chart(
                    mapa_chart,
                    use_container_width=True,
                    key="mapa_detalle_ubicaciones_2d",
                )
            else:
                figura_3d = construir_mapa_3d(
                    detalle=detalle,
                    orden_posiciones=orden_posiciones,
                    orden_niveles=orden_niveles,
                    titulo="",
                )
                figura_3d.update_layout(
                    height=410,
                    margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", y=1.0, x=0.01),
                )
                st.plotly_chart(
                    figura_3d,
                    use_container_width=True,
                    config={
                        "displaylogo": False,
                        "scrollZoom": True,
                        "responsive": True,
                    },
                    key="mapa_detalle_ubicaciones_3d",
                )
                st.caption(
                    "Arrastrá para rotar, usá la rueda para acercar y pasá el cursor "
                    "sobre cada bloque para ver su detalle."
                )

    with st.expander("📋 Ver ubicaciones del pasillo seleccionado"):
        columnas = [
            "EtiquetaUbicacion", "AreaMapa", "PasilloMapa", "PosicionMapa",
            "NivelMapa", "Tercio", "EstadoMapa", "ContenedoresMapa",
            "CodigoVerificador",
        ]
        tabla_detalle = detalle[[c for c in columnas if c in detalle.columns]].copy()
        tabla_detalle = tabla_detalle.rename(columns={
            "EtiquetaUbicacion": "Ubicación",
            "AreaMapa": "Área",
            "PasilloMapa": "Pasillo",
            "PosicionMapa": "Posición",
            "NivelMapa": "Nivel",
            "EstadoMapa": "Estado",
            "ContenedoresMapa": "Contenedores",
            "CodigoVerificador": "Código verificador",
        })
        st.dataframe(
            dataframe_para_streamlit(tabla_detalle),
            hide_index=True, width="stretch", height=420,
        )


