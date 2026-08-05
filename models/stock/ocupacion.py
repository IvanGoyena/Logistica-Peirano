import pandas as pd
import altair as alt
import streamlit as st

from utils.stock.helpers import formato_entero

def _texto_normalizado(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip().upper()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto


def _segmento_ubicacion(valor: object, ancho: int = 3) -> str:
    texto = _texto_normalizado(valor)
    if texto.isdigit():
        return texto.zfill(ancho)
    return texto


def _bool_ubicacion(valor: object) -> bool:
    return _texto_normalizado(valor) in {
        "TRUE", "VERDADERO", "1", "SI", "SÍ", "YES", "ACTIVA", "DISPONIBLE"
    }


def _buscar_columna(dataframe: pd.DataFrame, candidatos: list[str]) -> str | None:
    if dataframe is None or dataframe.empty:
        return None

    mapa = {
        str(columna).strip().lower()
        .replace("á", "a").replace("é", "e")
        .replace("í", "i").replace("ó", "o")
        .replace("ú", "u"): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        clave = (
            candidato.strip().lower()
            .replace("á", "a").replace("é", "e")
            .replace("í", "i").replace("ó", "o")
            .replace("ú", "u")
        )
        if clave in mapa:
            return mapa[clave]

    return None


def preparar_maestro_ubicaciones(dataframe: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = [
        "CodigoVerificador", "Area", "Ab", "Pasillo", "Posicion", "Nivel",
        "Rotacion", "Estado", "Orden", "Tipo", "Disponible", "Tercio",
        "Capacidad Pallets", "CapacidadNumerica", "ClaveUbicacion",
        "ClaveSinArea", "GrupoOcupacion",
    ]

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=columnas_salida)

    tabla = dataframe.copy()
    tabla.columns = [str(columna).strip() for columna in tabla.columns]

    for columna in [
        "CodigoVerificador", "Area", "Ab", "Pasillo", "Posicion", "Nivel",
        "Rotacion", "Estado", "Tipo", "Disponible", "Tercio",
        "Capacidad Pallets",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""

    tabla["Area"] = tabla["Area"].map(_texto_normalizado)
    tabla["Ab"] = tabla["Ab"].map(_texto_normalizado)
    tabla["Pasillo"] = tabla["Pasillo"].map(_segmento_ubicacion)
    tabla["Posicion"] = tabla["Posicion"].map(_segmento_ubicacion)
    tabla["Nivel"] = tabla["Nivel"].map(_segmento_ubicacion)
    tabla["Tipo"] = tabla["Tipo"].map(
        lambda valor: str(valor).strip().title() if not pd.isna(valor) else ""
    )
    tabla["Estado"] = tabla["Estado"].map(
        lambda valor: str(valor).strip() if not pd.isna(valor) else ""
    )
    tabla["Tercio"] = tabla["Tercio"].map(
        lambda valor: str(valor).strip() if not pd.isna(valor) else ""
    )
    tabla["Disponible"] = tabla["Disponible"].map(_bool_ubicacion)

    capacidad_texto = (
        tabla["Capacidad Pallets"].astype("string")
        .str.replace(",", ".", regex=False)
        .str.extract(r"(\d+(?:\.\d+)?)", expand=False)
    )
    tabla["CapacidadNumerica"] = pd.to_numeric(
        capacidad_texto,
        errors="coerce",
    ).fillna(1).clip(lower=1)

    tabla["ClaveUbicacion"] = (
        tabla["Ab"] + "-" + tabla["Pasillo"] + "-"
        + tabla["Posicion"] + "-" + tabla["Nivel"]
    )
    tabla["ClaveSinArea"] = (
        tabla["Pasillo"] + "-" + tabla["Posicion"] + "-" + tabla["Nivel"]
    )

    def clasificar_grupo(fila: pd.Series) -> str:
        tipo = _texto_normalizado(fila.get("Tipo"))
        area = _texto_normalizado(fila.get("Area"))

        # El área debe evaluarse antes que el tipo. En el maestro, PASILLO
        # pertenece al tipo Almacén, pero operativamente se mide separado.
        if area == "PASILLO":
            return "Pasillo"
        if tipo == "ACEITUNA" or area == "LOZA":
            return "Aceituna"
        if tipo == "ENTRE PISO" or area == "ENTRE PISO":
            return "Entrepiso"

        clave = (
            f"{_texto_normalizado(fila.get('Ab'))}-"
            f"{_segmento_ubicacion(fila.get('Pasillo'))}-"
            f"{_segmento_ubicacion(fila.get('Posicion'))}-"
            f"{_segmento_ubicacion(fila.get('Nivel'))}"
        )

        # CAL-001 es una ubicación de tránsito y queda fuera de los
        # indicadores de mercadería no apta.
        if clave == "LAB-001-001-001":
            return "Calidad Laboratorio"

        if clave in {
            "CAL-002-001-001",
            "CAL-003-001-001",
        }:
            return "Calidad Piso"

        if (
            _texto_normalizado(fila.get("Ab")) == "CAL"
            and clave not in {
                "CAL-001-001-001",
                "CAL-002-001-001",
                "CAL-003-001-001",
            }
        ):
            return "Calidad Racks"

        if tipo == "ALMACEN" and area == "ALMACEN":
            return "Almacén"
        if tipo == "PICKING":
            return "Picking"
        if tipo == "ESTANTERIAS" or area == "ESTANTERIAS":
            return "Estanterías"
        return "No aplica"

    tabla["GrupoOcupacion"] = tabla.apply(clasificar_grupo, axis=1)

    return tabla[columnas_salida].copy()


def construir_ocupacion_deposito(
    maestro_ubicaciones: pd.DataFrame,
    stock_detallado: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Cruza el maestro contra el stock real.

    Se prueban distintos formatos de ubicación del reporte WMS y se elige
    automáticamente el que obtiene mayor cantidad de coincidencias.
    """

    maestro = preparar_maestro_ubicaciones(maestro_ubicaciones)

    # El Maestro de Ubicaciones puede contener filas repetidas para la misma
    # ubicación física. Antes del cruce se consolida una única fila por
    # ClaveUbicacion, priorizando ubicaciones disponibles y con mayor capacidad.
    cantidad_duplicados_maestro = 0

    if not maestro.empty and "ClaveUbicacion" in maestro.columns:
        mascara_duplicados = maestro["ClaveUbicacion"].duplicated(keep=False)
        cantidad_duplicados_maestro = int(mascara_duplicados.sum())

        if cantidad_duplicados_maestro > 0:
            maestro = (
                maestro
                .assign(
                    _PrioridadDisponible=(
                        maestro.get(
                            "Disponible",
                            pd.Series(False, index=maestro.index),
                        )
                        .fillna(False)
                        .astype(bool)
                        .astype(int)
                    ),
                    _PrioridadCapacidad=pd.to_numeric(
                        maestro.get(
                            "CapacidadNumerica",
                            pd.Series(1, index=maestro.index),
                        ),
                        errors="coerce",
                    ).fillna(1),
                )
                .sort_values(
                    [
                        "ClaveUbicacion",
                        "_PrioridadDisponible",
                        "_PrioridadCapacidad",
                    ],
                    ascending=[True, False, False],
                )
                .drop_duplicates(
                    subset=["ClaveUbicacion"],
                    keep="first",
                )
                .drop(
                    columns=[
                        "_PrioridadDisponible",
                        "_PrioridadCapacidad",
                    ]
                )
                .reset_index(drop=True)
            )

    diagnostico = {
        "columna_ubicacion": None,
        "formato_detectado": None,
        "coincidencias": 0,
        "ubicaciones_stock": 0,
        "porcentaje_match": 0.0,
        "duplicados_maestro_consolidados": cantidad_duplicados_maestro,
    }

    if maestro.empty:
        return maestro, diagnostico

    resultado = maestro.copy()
    resultado["ContenedoresOcupados"] = 0
    resultado["OcupacionPallets"] = 0.0
    resultado["Ocupada"] = False

    if stock_detallado is None or stock_detallado.empty:
        resultado["CapacidadDisponible"] = resultado["CapacidadNumerica"].where(
            resultado["Disponible"], 0
        )
        resultado["PorcentajeOcupacion"] = 0.0
        return resultado, diagnostico

    columna_ubicacion = _buscar_columna(
        stock_detallado,
        [
            "Ubicacion", "Ubicación", "UbicacionCodigo", "Ubicación Código",
            "CodigoUbicacion", "Código Ubicación", "Posicion", "Posición",
            "Location", "LocationCode",
        ],
    )
    columna_contenedor = _buscar_columna(
        stock_detallado,
        [
            "Contenedor", "ContenedorCodigo", "Código Contenedor",
            "CodigoContenedor", "Container", "LPN",
        ],
    )
    columna_area_stock = _buscar_columna(
        stock_detallado,
        [
            "Area", "Área", "AreaCodigo", "Área Código",
            "Zona", "Sector", "WarehouseArea",
        ],
    )
    columna_cantidad = _buscar_columna(
        stock_detallado,
        [
            "Cantidad", "Stock", "Unidades", "CantidadStock",
            "Cantidad Disponible",
        ],
    )
    columna_articulo = _buscar_columna(
        stock_detallado,
        [
            "ArticuloCodigo", "Artículo Código", "CodigoArticulo",
            "Código Artículo", "CodArticulo", "Articulo", "Artículo",
        ],
    )

    if columna_ubicacion is None:
        resultado["CapacidadDisponible"] = resultado["CapacidadNumerica"].where(
            resultado["Disponible"], 0
        )
        resultado["PorcentajeOcupacion"] = 0.0
        return resultado, diagnostico

    stock = stock_detallado.copy()

    # Una ubicación se considera ocupada únicamente cuando existe stock real.
    # Se eliminan filas auxiliares del reporte con cantidad cero o sin artículo,
    # que anteriormente podían marcar ubicaciones vacías como ocupadas.
    if columna_cantidad is not None:
        stock["_CantidadOcupacion"] = pd.to_numeric(
            stock[columna_cantidad], errors="coerce"
        ).fillna(0)
        stock = stock.loc[stock["_CantidadOcupacion"].gt(0)].copy()

    if columna_articulo is not None:
        stock["_ArticuloOcupacion"] = stock[columna_articulo].map(_texto_normalizado)
        stock = stock.loc[stock["_ArticuloOcupacion"].ne("")].copy()

    stock["_UbicacionOriginal"] = stock[columna_ubicacion].map(_texto_normalizado)
    stock = stock.loc[stock["_UbicacionOriginal"].ne("")].copy()

    claves_maestro = set(resultado["ClaveUbicacion"])
    claves_sin_area = set(resultado["ClaveSinArea"])

    def variantes(valor: str) -> dict[str, str]:
        limpio = (
            valor.replace(" ", "-").replace("_", "-").replace("/", "-")
            .replace("--", "-").strip("-")
        )
        compacto = "".join(caracter for caracter in valor if caracter.isalnum())
        segmentos = [segmento for segmento in limpio.split("-") if segmento]

        salida = {
            "texto": limpio,
            "compacto": compacto,
        }

        if len(segmentos) >= 4:
            ab = segmentos[-4]
            pasillo = _segmento_ubicacion(segmentos[-3])
            posicion = _segmento_ubicacion(segmentos[-2])
            nivel = _segmento_ubicacion(segmentos[-1])
            salida["con_area"] = f"{ab}-{pasillo}-{posicion}-{nivel}"
            salida["sin_area"] = f"{pasillo}-{posicion}-{nivel}"
        elif len(segmentos) >= 3:
            pasillo = _segmento_ubicacion(segmentos[-3])
            posicion = _segmento_ubicacion(segmentos[-2])
            nivel = _segmento_ubicacion(segmentos[-1])
            salida["sin_area"] = f"{pasillo}-{posicion}-{nivel}"

        return salida

    # ------------------------------------------------------
    # CRUCE SEGURO CONTRA EL MAESTRO
    # ------------------------------------------------------
    # No se utiliza un único formato global "sin área" para todas las filas.
    # Esa estrategia podía asociar una ubicación de otra área con varias
    # ubicaciones del maestro que compartían Pasillo-Posición-Nivel.
    #
    # Prioridad del cruce:
    # 1. Clave completa con abreviatura de área.
    # 2. Texto original, solamente cuando coincide exactamente con el maestro.
    # 3. Clave sin área, únicamente si es única dentro del maestro.

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
    claves_sin_area_unicas = {
        str(fila.ClaveSinArea): str(fila.ClaveUbicacion)
        for fila in claves_sin_area_df.itertuples(index=False)
        if conteo_sin_area.get(fila.ClaveSinArea, 0) == 1
    }

    variantes_stock = stock["_UbicacionOriginal"].map(variantes)
    stock["_VarianteTexto"] = variantes_stock.map(
        lambda valor: valor.get("texto", "")
    )
    stock["_VarianteConArea"] = variantes_stock.map(
        lambda valor: valor.get("con_area", "")
    )
    stock["_VarianteSinArea"] = variantes_stock.map(
        lambda valor: valor.get("sin_area", "")
    )

    stock["_ClaveMapa"] = stock["_VarianteConArea"].map(claves_exactas)

    faltantes = stock["_ClaveMapa"].isna()
    stock.loc[faltantes, "_ClaveMapa"] = (
        stock.loc[faltantes, "_VarianteTexto"].map(claves_exactas)
    )

    faltantes = stock["_ClaveMapa"].isna()
    stock.loc[faltantes, "_ClaveMapa"] = (
        stock.loc[faltantes, "_VarianteSinArea"].map(claves_sin_area_unicas)
    )

    muestras = stock["_UbicacionOriginal"].drop_duplicates()
    coincidencias = int(
        stock.loc[stock["_ClaveMapa"].notna(), "_UbicacionOriginal"].nunique()
    )

    diagnostico.update({
        "columna_ubicacion": columna_ubicacion,
        "formato_detectado": "cruce_exacto_con_fallback_unico",
        "coincidencias": coincidencias,
        "ubicaciones_stock": int(muestras.size),
        "porcentaje_match": (
            coincidencias / muestras.size * 100 if muestras.size else 0
        ),
    })

    # Solo las filas que pudieron vincularse de forma inequívoca participan
    # del cálculo. Las claves sin área duplicadas se descartan para evitar
    # ocupaciones falsas en PASILLO, ALMACÉN o PICKING.
    stock_cruzado = stock.loc[stock["_ClaveMapa"].notna()].copy()

    if columna_contenedor is not None:
        stock_cruzado["_Contenedor"] = stock_cruzado[columna_contenedor].map(
            _texto_normalizado
        )
        ocupacion_stock = (
            stock_cruzado.groupby("_ClaveMapa", dropna=False)
            .agg(
                ContenedoresValidos=(
                    "_Contenedor",
                    lambda serie: serie.loc[serie.ne("")].nunique(),
                ),
                FilasStock=("_ClaveMapa", "size"),
            )
            .reset_index()
        )
        ocupacion_stock["ContenedoresOcupados"] = (
            ocupacion_stock["ContenedoresValidos"]
            .where(ocupacion_stock["ContenedoresValidos"].gt(0), 1)
            .astype(int)
        )
        ocupacion_stock = ocupacion_stock[
            ["_ClaveMapa", "ContenedoresOcupados"]
        ]
    else:
        ocupacion_stock = (
            stock_cruzado.groupby("_ClaveMapa", dropna=False)
            .size().clip(upper=1)
            .rename("ContenedoresOcupados").reset_index()
        )

    resultado = resultado.merge(
        ocupacion_stock,
        how="left",
        left_on="ClaveUbicacion",
        right_on="_ClaveMapa",
        suffixes=("", "_Stock"),
        validate="one_to_one",
    )
    resultado["ContenedoresOcupados"] = pd.to_numeric(
        resultado.get(
            "ContenedoresOcupados_Stock",
            resultado.get("ContenedoresOcupados"),
        ),
        errors="coerce",
    ).fillna(0)
    resultado.drop(
        columns=[
            columna
            for columna in ["_ClaveMapa", "ContenedoresOcupados_Stock"]
            if columna in resultado.columns
        ],
        inplace=True,
    )

    # ------------------------------------------------------
    # SUPERFICIES DE PISO
    # ------------------------------------------------------
    # LOZA (Aceituna) y ENTRE PISO se miden por contenedores distintos
    # contra la capacidad total definida en el maestro. El WMS puede traer
    # el sector como nombre de área, abreviatura, clave completa o código
    # verificador; por eso se utilizan todos esos caminos de identificación.

    stock["_AreaStock"] = (
        stock[columna_area_stock].map(_texto_normalizado)
        if columna_area_stock is not None
        else pd.Series("", index=stock.index, dtype="string")
    )

    stock["_VarianteConArea"] = stock["_UbicacionOriginal"].map(
        lambda valor: variantes(valor).get("con_area", "")
    )
    stock["_VarianteTexto"] = stock["_UbicacionOriginal"].map(
        lambda valor: variantes(valor).get("texto", "")
    )
    stock["_UbicacionCompacta"] = stock["_UbicacionOriginal"].map(
        lambda valor: "".join(c for c in _texto_normalizado(valor) if c.isalnum())
    )

    maestro_aceituna = resultado.loc[resultado["GrupoOcupacion"].eq("Aceituna")].copy()
    maestro_entrepiso = resultado.loc[resultado["GrupoOcupacion"].eq("Entrepiso")].copy()

    claves_aceituna = set(maestro_aceituna["ClaveUbicacion"].dropna().astype(str))
    claves_entrepiso = set(maestro_entrepiso["ClaveUbicacion"].dropna().astype(str))
    verificadores_aceituna = set(
        maestro_aceituna["CodigoVerificador"].map(_texto_normalizado).loc[lambda x: x.ne("")]
    )
    verificadores_entrepiso = set(
        maestro_entrepiso["CodigoVerificador"].map(_texto_normalizado).loc[lambda x: x.ne("")]
    )

    def contiene_token(serie: pd.Series, patron: str) -> pd.Series:
        return serie.fillna("").astype(str).str.contains(patron, regex=True, na=False)

    mascara_loza_stock = (
        contiene_token(stock["_AreaStock"], r"(?:^|[^A-Z0-9])(?:LOZA|ACEITUNA|LOZ)(?:[^A-Z0-9]|$)")
        | contiene_token(stock["_VarianteTexto"], r"(?:^|[- ])(?:LOZA|ACEITUNA|LOZ)(?:[- ]|$)")
        | stock["_VarianteConArea"].isin(claves_aceituna)
        | stock["_UbicacionOriginal"].isin(verificadores_aceituna)
        | stock["_UbicacionCompacta"].isin(
            {"".join(c for c in valor if c.isalnum()) for valor in verificadores_aceituna}
        )
    )

    mascara_entrepiso_stock = (
        contiene_token(stock["_AreaStock"], r"(?:^|[^A-Z0-9])(?:ENTRE[ -]?PISO|ENTREPISO|ENT)(?:[^A-Z0-9]|$)")
        | contiene_token(stock["_VarianteTexto"], r"(?:^|[- ])(?:ENTRE[ -]?PISO|ENTREPISO|ENT)(?:[- ]|$)")
        | stock["_VarianteConArea"].isin(claves_entrepiso)
        | stock["_UbicacionOriginal"].isin(verificadores_entrepiso)
        | stock["_UbicacionCompacta"].isin(
            {"".join(c for c in valor if c.isalnum()) for valor in verificadores_entrepiso}
        )
    )

    if columna_contenedor is not None:
        stock["_ContenedorPiso"] = stock[columna_contenedor].map(_texto_normalizado)
        contenedor_valido = stock["_ContenedorPiso"].ne("")

        contenedores_loza = int(
            stock.loc[mascara_loza_stock & contenedor_valido, "_ContenedorPiso"].nunique()
        )
        contenedores_entrepiso = int(
            stock.loc[mascara_entrepiso_stock & contenedor_valido, "_ContenedorPiso"].nunique()
        )
    else:
        # Sólo como respaldo cuando el reporte no trae una columna de contenedor.
        contenedores_loza = int(mascara_loza_stock.sum())
        contenedores_entrepiso = int(mascara_entrepiso_stock.sum())

    mascara_aceituna = resultado["GrupoOcupacion"].eq("Aceituna")
    mascara_entrepiso = resultado["GrupoOcupacion"].eq("Entrepiso")

    # Se guarda el agregado en una sola fila para evitar duplicarlo si en el
    # futuro el maestro incorpora más de un registro para la misma superficie.
    resultado.loc[mascara_aceituna, "ContenedoresOcupados"] = 0
    resultado.loc[mascara_entrepiso, "ContenedoresOcupados"] = 0

    indices_aceituna = resultado.index[mascara_aceituna].tolist()
    indices_entrepiso = resultado.index[mascara_entrepiso].tolist()

    if indices_aceituna:
        resultado.loc[indices_aceituna[0], "ContenedoresOcupados"] = contenedores_loza
    if indices_entrepiso:
        resultado.loc[indices_entrepiso[0], "ContenedoresOcupados"] = contenedores_entrepiso

    diagnostico["contenedores_loza"] = contenedores_loza
    diagnostico["contenedores_entrepiso"] = contenedores_entrepiso
    diagnostico["filas_loza_detectadas"] = int(mascara_loza_stock.sum())
    diagnostico["filas_entrepiso_detectadas"] = int(mascara_entrepiso_stock.sum())

    resultado["OcupacionPallets"] = resultado[
        ["ContenedoresOcupados", "CapacidadNumerica"]
    ].min(axis=1)
    resultado["Ocupada"] = resultado["ContenedoresOcupados"].gt(0)
    resultado["CapacidadDisponible"] = resultado["CapacidadNumerica"].where(
        resultado["Disponible"], 0
    )
    resultado["PorcentajeOcupacion"] = (
        resultado["OcupacionPallets"]
        .div(resultado["CapacidadDisponible"].replace(0, pd.NA))
        .mul(100)
        .fillna(0)
        .clip(0, 100)
    )

    return resultado, diagnostico


def resumir_ocupacion(
    tabla: pd.DataFrame,
    grupo: str | None = None,
) -> dict:
    """
    Resume la ocupación según la lógica operativa del sector.

    - Almacén, Pasillo, Picking y Estanterías: una ubicación con stock
      cuenta como ocupada, independientemente de cuántos pallets contenga.
    - Aceituna, Entrepiso, Calidad Laboratorio y Calidad Piso:
      son superficies de piso y se dimensionan por capacidad de pallets
      versus contenedores distintos alojados.
    - Calidad Racks: una ubicación física equivale a un pallet.
    - Global: incluye exclusivamente Almacén + Pasillo.
    """
    vacio = {
        "capacidad": 0.0, "ocupado": 0.0, "libre": 0.0,
        "porcentaje": 0.0, "ubicaciones": 0, "unidad": "ubicaciones",
    }
    if tabla is None or tabla.empty:
        return vacio

    base = tabla.loc[tabla["Disponible"]].copy()

    if grupo == "Global":
        base = base.loc[
            base["GrupoOcupacion"].isin(["Almacén", "Pasillo"])
        ]
    elif grupo == "Picking Rack":
        base = base.loc[base["GrupoOcupacion"].eq("Picking")].copy()
        mascara_cajones = (
            base["Pasillo"].astype("string").str.strip().str.lstrip("0").eq("20")
            | base["Tercio"].astype("string").str.upper().str.strip().eq("CAJONES")
        )
        base = base.loc[~mascara_cajones]
    elif grupo == "Cajones":
        base = base.loc[base["GrupoOcupacion"].eq("Picking")].copy()
        mascara_cajones = (
            base["Pasillo"].astype("string").str.strip().str.lstrip("0").eq("20")
            | base["Tercio"].astype("string").str.upper().str.strip().eq("CAJONES")
        )
        base = base.loc[mascara_cajones]
    elif grupo:
        base = base.loc[base["GrupoOcupacion"].eq(grupo)]

    usa_capacidad_pallets = grupo in {
        "Aceituna",
        "Entrepiso",
        "Calidad Laboratorio",
        "Calidad Piso",
    }

    if usa_capacidad_pallets:
        capacidad = float(base["CapacidadNumerica"].sum())
        ocupado = float(
            base[["ContenedoresOcupados", "CapacidadNumerica"]]
            .min(axis=1)
            .sum()
        )
        unidad = "contenedores"
    else:
        capacidad = float(len(base))
        ocupado = float(base["Ocupada"].sum())
        unidad = "ubicaciones"

    libre = max(capacidad - ocupado, 0)
    porcentaje = ocupado / capacidad * 100 if capacidad else 0

    return {
        "capacidad": capacidad,
        "ocupado": ocupado,
        "libre": libre,
        "porcentaje": porcentaje,
        "ubicaciones": int(len(base)),
        "unidad": unidad,
    }


def grafico_donut_ocupacion(
    titulo: str,
    resumen: dict,
    color_ocupado: str = "#24456D",
    color_libre: str = "#E9ECEF",
) -> alt.Chart:
    porcentaje = float(resumen["porcentaje"])
    datos = pd.DataFrame({
        "Estado": ["Ocupado", "Libre"],
        "Capacidad": [resumen["ocupado"], resumen["libre"]],
    })

    base = (
        alt.Chart(datos)
        .mark_arc(innerRadius=58, outerRadius=82, cornerRadius=3)
        .encode(
            theta=alt.Theta("Capacidad:Q", stack=True),
            color=alt.Color(
                "Estado:N",
                scale=alt.Scale(
                    domain=["Ocupado", "Libre"],
                    range=[color_ocupado, color_libre],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Estado:N"),
                alt.Tooltip("Capacidad:Q", format=",.0f"),
            ],
        )
    )

    texto_centro = (
        alt.Chart(pd.DataFrame({"texto": [f"{porcentaje:.1f}%"]}))
        .mark_text(fontSize=25, fontWeight="bold", color="#F8FAFC")
        .encode(text="texto:N")
    )

    subtitulo = (
        alt.Chart(pd.DataFrame({
            "texto": [
                f'{resumen["ocupado"]:,.0f} / {resumen["capacidad"]:,.0f}'
                .replace(",", ".")
            ]
        }))
        .mark_text(fontSize=11, color="#CBD5E1", dy=24)
        .encode(text="texto:N")
    )

    return (
        (base + texto_centro + subtitulo)
        .properties(title=titulo, height=205)
        .configure_title(
            anchor="middle",
            fontSize=14,
            fontWeight="bold",
            color="#F8FAFC",
            offset=8,
        )
        .configure_view(stroke=None)
    )


def mostrar_tarjeta_donut(
    titulo: str,
    resumen: dict,
    key: str,
    color_ocupado: str = "#24456D",
    color_libre: str = "#E9ECEF",
    icono: str = "📦",
) -> None:
    unidad = resumen.get("unidad", "ubicaciones")
    borde = color_ocupado
    with st.container(border=True):
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:.55rem;margin-bottom:-.6rem;">
                <span style="font-size:1.25rem">{icono}</span>
                <span style="font-weight:800;color:{color_ocupado};font-size:.95rem;letter-spacing:.02em;">
                    {titulo.upper()}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.altair_chart(
            grafico_donut_ocupacion(
                "",
                resumen,
                color_ocupado=color_ocupado,
                color_libre=color_libre,
            ),
            width="stretch",
            key=key,
        )
        if unidad == "contenedores":
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**{formato_entero(resumen['ocupado'])}**<br><small>contenedores</small>", unsafe_allow_html=True)
            c2.markdown(f"**{formato_entero(resumen['libre'])}**<br><small>libres</small>", unsafe_allow_html=True)
            c3.markdown(f"**{formato_entero(resumen['capacidad'])}**<br><small>capacidad</small>", unsafe_allow_html=True)
        else:
            c1, c2 = st.columns(2)
            c1.markdown(f"**{formato_entero(resumen['libre'])}**<br><small>vacías</small>", unsafe_allow_html=True)
            c2.markdown(f"**{formato_entero(resumen['capacidad'])}**<br><small>total ubicaciones</small>", unsafe_allow_html=True)


