import pandas as pd
import altair as alt
import plotly.graph_objects as go
import streamlit as st

from utils.stock.helpers import dataframe_para_streamlit, formato_entero

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




def _segmento_mapa(valor: object, ancho: int = 3) -> str:
    texto = str(valor or "").strip().upper()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.zfill(ancho) if texto.isdigit() else texto


def _claves_desde_ubicacion(valor: object) -> tuple[str, str]:
    """Devuelve claves con y sin abreviatura de área desde una ubicación WMS."""
    texto = str(valor or "").strip().upper()
    limpio = texto.replace(" ", "-").replace("_", "-").replace("/", "-")
    while "--" in limpio:
        limpio = limpio.replace("--", "-")
    segmentos = [segmento for segmento in limpio.strip("-").split("-") if segmento]

    con_area = ""
    sin_area = ""
    if len(segmentos) >= 4:
        ab = segmentos[-4]
        pasillo = _segmento_mapa(segmentos[-3])
        posicion = _segmento_mapa(segmentos[-2])
        nivel = _segmento_mapa(segmentos[-1])
        con_area = f"{ab}-{pasillo}-{posicion}-{nivel}"
        sin_area = f"{pasillo}-{posicion}-{nivel}"
    elif len(segmentos) >= 3:
        pasillo = _segmento_mapa(segmentos[-3])
        posicion = _segmento_mapa(segmentos[-2])
        nivel = _segmento_mapa(segmentos[-1])
        sin_area = f"{pasillo}-{posicion}-{nivel}"
    return con_area, sin_area


def enriquecer_mapa_con_stock(
    mapa: pd.DataFrame,
    tabla_stock_total_detallado: pd.DataFrame | None,
) -> pd.DataFrame:
    """Agrega SKU, descripciones, unidades y contenedores por ubicación."""
    resultado = mapa.copy()
    columnas_default = {
        "SKUsMapa": 0,
        "UnidadesMapa": 0.0,
        "ContenedoresDetalleMapa": 0,
        "ArticulosMapa": "",
    }
    for columna, valor in columnas_default.items():
        resultado[columna] = valor

    if tabla_stock_total_detallado is None or tabla_stock_total_detallado.empty:
        return resultado
    if "Ubicacion" not in tabla_stock_total_detallado.columns:
        return resultado

    stock = tabla_stock_total_detallado.copy()
    if "FuenteStock" in stock.columns:
        stock = stock.loc[
            stock["FuenteStock"].astype("string").str.contains(
                "Almac", case=False, na=False
            )
        ].copy()
    if stock.empty:
        return resultado

    claves_exactas = {
        str(clave): str(clave)
        for clave in resultado["ClaveUbicacion"].dropna().astype(str)
    }
    claves_sin_area_df = (
        resultado[["ClaveSinArea", "ClaveUbicacion"]]
        .dropna()
        .drop_duplicates()
    )
    conteo_sin_area = claves_sin_area_df["ClaveSinArea"].value_counts()
    claves_sin_area = {
        str(fila.ClaveSinArea): str(fila.ClaveUbicacion)
        for fila in claves_sin_area_df.itertuples(index=False)
        if conteo_sin_area.get(fila.ClaveSinArea, 0) == 1
    }

    pares = stock["Ubicacion"].map(_claves_desde_ubicacion)
    stock["_ClaveConArea"] = pares.map(lambda valor: valor[0])
    stock["_ClaveSinArea"] = pares.map(lambda valor: valor[1])
    stock["_ClaveMapa"] = stock["_ClaveConArea"].map(claves_exactas)
    faltantes = stock["_ClaveMapa"].isna()
    stock.loc[faltantes, "_ClaveMapa"] = stock.loc[faltantes, "_ClaveSinArea"].map(
        claves_sin_area
    )
    stock = stock.loc[stock["_ClaveMapa"].notna()].copy()
    if stock.empty:
        return resultado

    for columna in ["ArticuloCodigo", "ArticuloDescripcion", "ContenedorNumero"]:
        if columna not in stock.columns:
            stock[columna] = ""
        stock[columna] = stock[columna].fillna("").astype(str).str.strip()
    if "Cantidad" not in stock.columns:
        stock["Cantidad"] = 0
    stock["Cantidad"] = pd.to_numeric(stock["Cantidad"], errors="coerce").fillna(0)

    articulo_ubicacion = (
        stock.groupby(["_ClaveMapa", "ArticuloCodigo", "ArticuloDescripcion"], dropna=False)
        .agg(UnidadesArticulo=("Cantidad", "sum"))
        .reset_index()
    )

    def resumir_articulos(grupo: pd.DataFrame) -> str:
        lineas = []
        for fila in grupo.sort_values("UnidadesArticulo", ascending=False).head(6).itertuples(index=False):
            descripcion = str(fila.ArticuloDescripcion or "").strip()
            etiqueta = str(fila.ArticuloCodigo or "").strip()
            if descripcion:
                etiqueta += f" · {descripcion}"
            lineas.append(f"{etiqueta} · {float(fila.UnidadesArticulo):,.0f} u".replace(",", "."))
        restantes = max(len(grupo) - 6, 0)
        if restantes:
            lineas.append(f"+ {restantes} artículos adicionales")
        return "<br>".join(lineas)

    texto_articulos = pd.DataFrame([
        {"_ClaveMapa": clave, "ArticulosMapa": resumir_articulos(grupo)}
        for clave, grupo in articulo_ubicacion.groupby("_ClaveMapa", dropna=False)
    ])
    resumen = (
        stock.groupby("_ClaveMapa", as_index=False)
        .agg(
            SKUsMapa=("ArticuloCodigo", lambda serie: serie.loc[serie.ne("")].nunique()),
            UnidadesMapa=("Cantidad", "sum"),
            ContenedoresDetalleMapa=(
                "ContenedorNumero",
                lambda serie: serie.loc[serie.ne("")].nunique(),
            ),
        )
        .merge(texto_articulos, on="_ClaveMapa", how="left")
    )

    resultado = resultado.merge(
        resumen,
        how="left",
        left_on="ClaveUbicacion",
        right_on="_ClaveMapa",
        suffixes=("", "_Stock"),
    )
    for columna, valor in columnas_default.items():
        stock_col = f"{columna}_Stock"
        if stock_col in resultado.columns:
            resultado[columna] = resultado[stock_col].fillna(resultado[columna])
            resultado.drop(columns=[stock_col], inplace=True)
    resultado.drop(columns=["_ClaveMapa"], errors="ignore", inplace=True)
    resultado["SKUsMapa"] = pd.to_numeric(resultado["SKUsMapa"], errors="coerce").fillna(0).astype(int)
    resultado["UnidadesMapa"] = pd.to_numeric(resultado["UnidadesMapa"], errors="coerce").fillna(0)
    resultado["ContenedoresDetalleMapa"] = pd.to_numeric(
        resultado["ContenedoresDetalleMapa"], errors="coerce"
    ).fillna(0).astype(int)
    resultado["ArticulosMapa"] = resultado["ArticulosMapa"].fillna("").astype(str)

    # Mantener el color, el estado y el detalle con una única fuente de verdad.
    # Una ubicación sin SKU, unidades ni contenedores reales debe verse vacía.
    tiene_stock_detalle = (
        resultado["SKUsMapa"].gt(0)
        | resultado["UnidadesMapa"].gt(0)
        | resultado["ContenedoresDetalleMapa"].gt(0)
    )
    resultado["Ocupada"] = tiene_stock_detalle
    resultado["ContenedoresMapa"] = resultado["ContenedoresDetalleMapa"]
    resultado["EstadoMapa"] = "Vacía"
    resultado.loc[~resultado["Disponible"].fillna(False), "EstadoMapa"] = "No disponible"
    resultado.loc[
        resultado["Disponible"].fillna(False) & tiene_stock_detalle,
        "EstadoMapa",
    ] = "Ocupada"

    return resultado


def _grafico_pasillo_2d(detalle: pd.DataFrame, titulo: str, altura_minima: int = 150):
    posiciones = sorted(
        detalle["PosicionMapa"].dropna().unique().tolist(),
        key=_ordenar_segmento_mapa,
    )
    niveles = sorted(
        detalle["NivelMapa"].dropna().unique().tolist(),
        key=_ordenar_segmento_mapa,
        reverse=True,
    )
    tooltip = [
        alt.Tooltip("EtiquetaUbicacion:N", title="Ubicación"),
        alt.Tooltip("AreaMapa:N", title="Área"),
        alt.Tooltip("PasilloMapa:N", title="Pasillo"),
        alt.Tooltip("PosicionMapa:N", title="Posición"),
        alt.Tooltip("NivelMapa:N", title="Nivel"),
        alt.Tooltip("Tercio:N", title="Tercio"),
        alt.Tooltip("EstadoMapa:N", title="Estado"),
        alt.Tooltip("SKUsMapa:Q", title="SKU", format=",.0f"),
        alt.Tooltip("UnidadesMapa:Q", title="Unidades", format=",.0f"),
        alt.Tooltip("ContenedoresDetalleMapa:Q", title="Contenedores", format=",.0f"),
        alt.Tooltip("ArticulosMapa:N", title="Artículos"),
    ]
    return (
        alt.Chart(detalle)
        .mark_rect(cornerRadius=2, stroke="#111827", strokeWidth=1)
        .encode(
            x=alt.X(
                "PosicionMapa:N",
                title="Posición",
                sort=posiciones,
                axis=alt.Axis(labelAngle=-90, labelLimit=45),
            ),
            y=alt.Y("NivelMapa:N", title="Nivel", sort=niveles),
            color=alt.Color(
                "EstadoMapa:N",
                scale=alt.Scale(
                    domain=["Ocupada", "Vacía", "No disponible"],
                    range=["#22C55E", "#E5E7EB", "#EF4444"],
                ),
                legend=None,
            ),
            tooltip=tooltip,
        )
        .properties(
            title=titulo,
            height=max(altura_minima, min(250, len(niveles) * 42)),
        )
    )


def _agregar_prismas_sector_3d(
    figura: go.Figure,
    datos: pd.DataFrame,
    *,
    color: str,
    nombre: str,
    coordenadas: dict[tuple[str, str], float],
    pasillos_y: dict[str, float],
    niveles_z: dict[tuple[str, str], float],
) -> None:
    """Agrega todas las ubicaciones de un estado al mapa 3D completo."""
    if datos.empty:
        return

    ancho = 0.88
    profundidad = 0.78
    alto = 1.02

    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    ii: list[int] = []
    jj: list[int] = []
    kk: list[int] = []
    hover_x: list[float] = []
    hover_y: list[float] = []
    hover_z: list[float] = []
    hover_text: list[str] = []

    caras = [
        (0, 1, 2), (0, 2, 3),
        (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1),
        (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3),
        (3, 7, 4), (3, 4, 0),
    ]

    for fila in datos.itertuples(index=False):
        pasillo = str(getattr(fila, "PasilloMapa"))
        posicion = str(getattr(fila, "PosicionMapa"))
        nivel = str(getattr(fila, "NivelMapa"))

        x0 = coordenadas.get((pasillo, posicion), 0.0)
        y0 = pasillos_y.get(pasillo, 0.0)
        z0 = niveles_z.get((pasillo, nivel), 0.0)
        x1 = x0 + ancho
        y1 = y0 + profundidad
        z1 = z0 + alto

        vertices = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]
        base_idx = len(xs)
        for vx, vy, vz in vertices:
            xs.append(vx)
            ys.append(vy)
            zs.append(vz)
        for a, b, c in caras:
            ii.append(base_idx + a)
            jj.append(base_idx + b)
            kk.append(base_idx + c)

        hover_x.append(x0 + ancho / 2)
        hover_y.append(y0 + profundidad / 2)
        hover_z.append(z0 + alto / 2)
        articulos = str(getattr(fila, "ArticulosMapa", "") or "")
        hover_text.append(
            f"<b>{getattr(fila, 'EtiquetaUbicacion', '')}</b><br>"
            f"Sector: {getattr(fila, 'SectorMapa', '')}<br>"
            f"Área: {getattr(fila, 'AreaMapa', '')}<br>"
            f"Pasillo: {pasillo}<br>"
            f"Posición: {posicion}<br>"
            f"Nivel: {nivel}<br>"
            f"Tercio: {getattr(fila, 'Tercio', '')}<br>"
            f"Estado: {getattr(fila, 'EstadoMapa', '')}<br>"
            f"SKU distintos: {int(getattr(fila, 'SKUsMapa', 0) or 0)}<br>"
            f"Unidades: {float(getattr(fila, 'UnidadesMapa', 0) or 0):,.0f}<br>"
            f"Artículos:<br>{articulos}"
        )

    figura.add_trace(go.Mesh3d(
        x=xs,
        y=ys,
        z=zs,
        i=ii,
        j=jj,
        k=kk,
        color=color,
        opacity=0.94,
        flatshading=True,
        name=nombre,
        hoverinfo="skip",
        showscale=False,
        lighting=dict(ambient=0.64, diffuse=0.72, roughness=0.70, specular=0.10),
        lightposition=dict(x=100, y=-160, z=180),
    ))
    figura.add_trace(go.Scatter3d(
        x=hover_x,
        y=hover_y,
        z=hover_z,
        mode="markers",
        marker=dict(size=6, color=color, opacity=0.01),
        text=hover_text,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
        name=f"Detalle {nombre}",
    ))


def construir_mapa_sector_3d(base: pd.DataFrame, sector: str) -> go.Figure:
    """Construye una vista 3D completa con todos los pasillos del sector."""
    pasillos = sorted(
        base["PasilloMapa"].dropna().astype(str).unique().tolist(),
        key=_ordenar_segmento_mapa,
    )

    coordenadas: dict[tuple[str, str], float] = {}
    pasillos_y: dict[str, float] = {}
    niveles_z: dict[tuple[str, str], float] = {}
    max_posiciones = 1
    max_niveles = 1

    separacion_pasillos = 1.75
    for indice_pasillo, pasillo in enumerate(pasillos):
        detalle_pasillo = base.loc[base["PasilloMapa"].astype(str).eq(pasillo)]
        posiciones = sorted(
            detalle_pasillo["PosicionMapa"].dropna().astype(str).unique().tolist(),
            key=_ordenar_segmento_mapa,
        )
        niveles = sorted(
            detalle_pasillo["NivelMapa"].dropna().astype(str).unique().tolist(),
            key=_ordenar_segmento_mapa,
        )
        max_posiciones = max(max_posiciones, len(posiciones))
        max_niveles = max(max_niveles, len(niveles))
        pasillos_y[pasillo] = indice_pasillo * separacion_pasillos

        for indice_posicion, posicion in enumerate(posiciones):
            coordenadas[(pasillo, posicion)] = indice_posicion * 0.98
        for indice_nivel, nivel in enumerate(niveles):
            niveles_z[(pasillo, nivel)] = indice_nivel * 1.14

    figura = go.Figure()
    configuracion = [
        ("Ocupada", "#22C55E"),
        ("Vacía", "#D1D5DB"),
        ("No disponible", "#EF4444"),
    ]
    for estado, color in configuracion:
        _agregar_prismas_sector_3d(
            figura,
            base.loc[base["EstadoMapa"].eq(estado)],
            color=color,
            nombre=estado,
            coordenadas=coordenadas,
            pasillos_y=pasillos_y,
            niveles_z=niveles_z,
        )

    tick_y = [pasillos_y[p] + 0.39 for p in pasillos]
    extension_y = (len(pasillos) - 1) * separacion_pasillos + 0.9 if pasillos else 1
    extension_x = max_posiciones * 0.98
    extension_z = max_niveles * 1.14

    figura.update_layout(
        title=dict(text=f"{sector} · Vista 3D completa", x=0.02),
        height=620,
        margin=dict(l=0, r=0, t=45, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.01, x=0.02),
        scene=dict(
            bgcolor="rgba(0,0,0,0)",
            aspectmode="manual",
            aspectratio=dict(
                x=max(2.4, min(4.5, extension_x / 14)),
                y=max(1.4, min(3.8, extension_y / 10)),
                z=max(1.15, min(2.0, extension_z / 3.2)),
            ),
            camera=dict(
                eye=dict(x=1.55, y=-2.10, z=1.55),
                up=dict(x=0, y=0, z=1),
            ),
            xaxis=dict(
                title="Posición relativa",
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                range=[-0.2, extension_x + 0.2],
            ),
            yaxis=dict(
                title="Pasillo",
                tickmode="array",
                tickvals=tick_y,
                ticktext=pasillos,
                showgrid=False,
                zeroline=False,
                range=[-0.35, extension_y + 0.35],
            ),
            zaxis=dict(
                title="Nivel",
                showgrid=False,
                zeroline=False,
                showticklabels=False,
                range=[-0.15, extension_z + 0.25],
            ),
        ),
    )
    return figura


def _mostrar_vista_completa_sector(mapa: pd.DataFrame) -> None:
    sectores = [s for s in ["Almacén", "Picking Rack"] if s in mapa["SectorMapa"].unique()]
    if not sectores:
        return

    with st.expander("🧭 Vista completa de Almacén y Picking", expanded=False):
        st.caption(
            "Permite recorrer todos los pasillos en paneles 2D o visualizar el sector "
            "completo dentro de un único modelo 3D."
        )
        col_sector, col_vista, col_cargar = st.columns(
            [1.15, 1.25, 2.1],
            vertical_alignment="bottom",
        )
        with col_sector:
            sector = st.selectbox(
                "Sector completo",
                options=sectores,
                key="mapa_sector_completo",
            )
        with col_vista:
            vista_completa = st.radio(
                "Tipo de vista",
                options=["Paneles 2D", "Modelo 3D completo"],
                horizontal=True,
                key="mapa_tipo_vista_completa",
            )
        with col_cargar:
            cargar = st.toggle(
                "Cargar sector completo",
                value=False,
                key="mapa_cargar_sector_completo",
                help="Se mantiene apagado por defecto para no ralentizar la pantalla.",
            )

        if not cargar:
            st.info("Activá la vista para cargar todos los pasillos del sector seleccionado.")
            return

        base = mapa.loc[mapa["SectorMapa"].eq(sector)].copy()
        pasillos = sorted(
            base["PasilloMapa"].dropna().unique().tolist(),
            key=_ordenar_segmento_mapa,
        )
        if not pasillos:
            st.info("No hay pasillos disponibles para este sector.")
            return

        total = int(len(base))
        disponibles = int(base["Disponible"].fillna(False).astype(bool).sum())
        ocupadas = int(
            (base["Disponible"].fillna(False).astype(bool)
             & base["Ocupada"].fillna(False).astype(bool)).sum()
        )
        porcentaje = ocupadas / disponibles * 100 if disponibles else 0
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pasillos", formato_entero(len(pasillos)))
        k2.metric("Ubicaciones", formato_entero(total))
        k3.metric("Ocupadas", formato_entero(ocupadas))
        k4.metric("Ocupación", f"{porcentaje:.1f}%")

        if vista_completa == "Modelo 3D completo":
            st.caption(
                "Cada línea de profundidad representa un pasillo real. Picking y Almacén "
                "conservan sus propias posiciones y niveles."
            )
            with st.spinner(f"Construyendo mapa 3D completo de {sector}..."):
                figura = construir_mapa_sector_3d(base, sector)
            st.plotly_chart(
                figura,
                use_container_width=True,
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                    "responsive": True,
                },
                key=f"mapa_3d_completo_{sector}",
            )
            return

        for inicio in range(0, len(pasillos), 2):
            columnas = st.columns(2, gap="large")
            for offset, pasillo in enumerate(pasillos[inicio:inicio + 2]):
                detalle = base.loc[base["PasilloMapa"].eq(pasillo)].copy()
                ocupadas_pasillo = int((detalle["Disponible"] & detalle["Ocupada"]).sum())
                disponibles_pasillo = int(detalle["Disponible"].sum())
                porcentaje_pasillo = (
                    ocupadas_pasillo / disponibles_pasillo * 100
                    if disponibles_pasillo else 0
                )
                with columnas[offset]:
                    with st.container(border=True):
                        st.markdown(
                            f"##### Pasillo {pasillo} · {porcentaje_pasillo:.1f}%"
                        )
                        grafico = _grafico_pasillo_2d(
                            detalle,
                            titulo="",
                            altura_minima=135,
                        )
                        st.altair_chart(
                            grafico,
                            use_container_width=True,
                            key=f"mapa_completo_{sector}_{pasillo}",
                        )

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
            f"Contenedores: {int(fila.get('ContenedoresDetalleMapa', fila.get('ContenedoresMapa', 0)) or 0)}<br>"
            f"SKU distintos: {int(fila.get('SKUsMapa', 0) or 0)}<br>"
            f"Unidades: {float(fila.get('UnidadesMapa', 0) or 0):,.0f}<br>"
            f"Artículos:<br>{fila.get('ArticulosMapa', '')}"
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

def mostrar_mapa_visual_deposito(
    tabla_ocupacion: pd.DataFrame,
    tabla_stock_total_detallado: pd.DataFrame | None = None,
) -> None:
    mapa = preparar_mapa_ubicaciones(tabla_ocupacion)
    mapa = enriquecer_mapa_con_stock(mapa, tabla_stock_total_detallado)
    if mapa.empty:
        st.info("No hay datos disponibles para construir el mapa visual.")
        return

    sectores_rack = [
        sector for sector in [
            "Almacén", "Pasillo", "Picking Rack", "Cajones", "Estanterías"
        ] if sector in mapa["SectorMapa"].unique()
    ]

    st.markdown("---")
    st.markdown("## 🗺️ Mapa visual del depósito")
    st.caption(
        "Vista general por pasillo, mapa completo por sector y detalle de cada ubicación."
    )

    mapa_racks = mapa.loc[mapa["SectorMapa"].isin(sectores_rack)].copy()
    if mapa_racks.empty:
        st.warning("No se encontraron sectores válidos para construir el mapa.")
        return

    resumen_pasillos = (
        mapa_racks.groupby(["SectorMapa", "PasilloMapa"], dropna=False)
        .agg(
            TotalUbicaciones=("ClaveUbicacion", "nunique"),
            UbicacionesOcupadas=("Ocupada", lambda s: int(s.fillna(False).astype(bool).sum())),
            UbicacionesDisponibles=("Disponible", lambda s: int(s.fillna(False).astype(bool).sum())),
        )
        .reset_index()
    )
    resumen_pasillos["UbicacionesVacias"] = (
        resumen_pasillos["UbicacionesDisponibles"] - resumen_pasillos["UbicacionesOcupadas"]
    ).clip(lower=0)
    resumen_pasillos["PorcentajeOcupacion"] = (
        resumen_pasillos["UbicacionesOcupadas"]
        .div(resumen_pasillos["UbicacionesDisponibles"].replace(0, pd.NA))
        .mul(100).fillna(0).astype(float)
    )
    resumen_pasillos["PasilloOrden"] = pd.to_numeric(
        resumen_pasillos["PasilloMapa"], errors="coerce"
    ).fillna(9999)

    sectores_comparables = [s for s in ["Almacén", "Pasillo"] if s in sectores_rack]
    with st.container(border=True):
        encabezado, filtro = st.columns([2.4, 1])
        with encabezado:
            st.markdown("#### Vista general por pasillo")
            st.caption("Comparación rápida de ocupación en Almacén y Pasillo.")
        with filtro:
            sector_resumen = st.selectbox(
                "Sector a comparar",
                options=sectores_comparables or sectores_rack,
                key="mapa_sector_resumen_pasillos",
            )
        resumen_sector = resumen_pasillos.loc[
            resumen_pasillos["SectorMapa"].eq(sector_resumen)
        ].sort_values(["PasilloOrden", "PasilloMapa"])
        grafico_pasillos = (
            alt.Chart(resumen_sector)
            .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, size=16)
            .encode(
                x=alt.X("PasilloMapa:N", title="Pasillo", sort=None,
                        axis=alt.Axis(labelAngle=0, labelOverlap=True, labelLimit=45)),
                y=alt.Y("PorcentajeOcupacion:Q", title="% de ocupación",
                        scale=alt.Scale(domain=[0, 100])),
                color=alt.value("#3B82F6" if sector_resumen == "Almacén" else "#2563EB"),
                tooltip=[
                    alt.Tooltip("PasilloMapa:N", title="Pasillo"),
                    alt.Tooltip("UbicacionesOcupadas:Q", title="Ocupadas", format=",.0f"),
                    alt.Tooltip("UbicacionesVacias:Q", title="Vacías", format=",.0f"),
                    alt.Tooltip("UbicacionesDisponibles:Q", title="Disponibles", format=",.0f"),
                    alt.Tooltip("PorcentajeOcupacion:Q", title="Ocupación", format=".1f"),
                ],
            ).properties(height=245)
        )
        st.altair_chart(grafico_pasillos, use_container_width=True,
                        key="mapa_resumen_pasillos_compacto")

    _mostrar_vista_completa_sector(mapa)

    st.markdown("#### Visualización del pasillo seleccionado")
    st.caption("Los filtros de este bloque son independientes de las otras visualizaciones.")
    panel_filtros, panel_mapa = st.columns([0.9, 3.1], gap="large")

    with panel_filtros:
        with st.container(border=True):
            st.markdown("##### Filtros del mapa")
            sector_seleccionado = st.selectbox(
                "Sector", options=sectores_rack, key="mapa_sector_seleccionado"
            )
            base_sector = mapa.loc[mapa["SectorMapa"].eq(sector_seleccionado)].copy()
            areas = sorted(base_sector["AreaMapa"].dropna().unique().tolist())
            area_seleccionada = st.selectbox(
                "Área", options=["Todas"] + areas, key="mapa_area_seleccionada"
            )
            if area_seleccionada != "Todas":
                base_sector = base_sector.loc[base_sector["AreaMapa"].eq(area_seleccionada)].copy()
            pasillos = sorted(base_sector["PasilloMapa"].dropna().unique().tolist(),
                              key=_ordenar_segmento_mapa)
            if not pasillos:
                st.info("No hay pasillos para la selección realizada.")
                return
            pasillo_seleccionado = st.selectbox(
                "Pasillo", options=pasillos, key="mapa_pasillo_seleccionado"
            )
            vista_mapa = st.radio(
                "Vista", options=["2D", "3D"], horizontal=True,
                key="mapa_tipo_vista_pasillo"
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
                "</div>", unsafe_allow_html=True,
            )

    orden_posiciones = sorted(detalle["PosicionMapa"].dropna().unique().tolist(),
                              key=_ordenar_segmento_mapa)
    orden_niveles = sorted(detalle["NivelMapa"].dropna().unique().tolist(),
                           key=_ordenar_segmento_mapa, reverse=True)
    detalle["TextoCelda"] = detalle["ContenedoresMapa"].apply(
        lambda valor: "" if valor <= 0 else str(int(valor))
    )
    mapa_chart = _grafico_pasillo_2d(
        detalle,
        f"{sector_seleccionado} · Pasillo {pasillo_seleccionado} · Vista 2D",
        altura_minima=max(230, min(360, len(orden_niveles) * 46)),
    )

    with panel_mapa:
        with st.container(border=True):
            st.markdown(
                f"##### {sector_seleccionado} · Pasillo {pasillo_seleccionado} · "
                f"{'Plano 2D' if vista_mapa == '2D' else 'Modelo 3D'}"
            )
            if vista_mapa == "2D":
                st.altair_chart(mapa_chart, use_container_width=True,
                                key="mapa_detalle_ubicaciones_2d")
            else:
                figura_3d = construir_mapa_3d(
                    detalle=detalle,
                    orden_posiciones=orden_posiciones,
                    orden_niveles=orden_niveles,
                    titulo="",
                )
                figura_3d.update_layout(
                    height=410, margin=dict(l=0, r=0, t=10, b=0),
                    legend=dict(orientation="h", y=1.0, x=0.01),
                )
                st.plotly_chart(
                    figura_3d, use_container_width=True,
                    config={"displaylogo": False, "scrollZoom": True, "responsive": True},
                    key="mapa_detalle_ubicaciones_3d",
                )
                st.caption("Arrastrá para rotar, acercá y pasá el cursor sobre cada bloque.")

    with st.expander("📋 Ver artículos y ubicaciones del pasillo seleccionado"):
        columnas = [
            "EtiquetaUbicacion", "AreaMapa", "PasilloMapa", "PosicionMapa",
            "NivelMapa", "Tercio", "EstadoMapa", "ContenedoresDetalleMapa",
            "SKUsMapa", "UnidadesMapa", "ArticulosMapa", "CodigoVerificador",
        ]
        tabla_detalle = detalle[[c for c in columnas if c in detalle.columns]].copy()
        tabla_detalle = tabla_detalle.rename(columns={
            "EtiquetaUbicacion": "Ubicación", "AreaMapa": "Área",
            "PasilloMapa": "Pasillo", "PosicionMapa": "Posición",
            "NivelMapa": "Nivel", "EstadoMapa": "Estado",
            "ContenedoresDetalleMapa": "Contenedores", "SKUsMapa": "SKU distintos",
            "UnidadesMapa": "Unidades", "ArticulosMapa": "Artículos",
            "CodigoVerificador": "Código verificador",
        })
        tabla_detalle["Artículos"] = tabla_detalle["Artículos"].str.replace("<br>", " | ", regex=False)
        st.dataframe(
            dataframe_para_streamlit(tabla_detalle), hide_index=True,
            width="stretch", height=460,
        )
