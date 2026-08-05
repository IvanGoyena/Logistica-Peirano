from __future__ import annotations

import re

import pandas as pd

from models.stock.ocupacion import preparar_maestro_ubicaciones


def _normalizar_texto(valor: object) -> str:
    if pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def _normalizar_nombre_columna(valor: object) -> str:
    texto = str(valor).strip().lower()
    reemplazos = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
        " ": "",
        "_": "",
        "-": "",
        "/": "",
        ".": "",
    }

    for origen, destino in reemplazos.items():
        texto = texto.replace(origen, destino)

    return texto


def _buscar_columna(
    tabla: pd.DataFrame,
    candidatos: list[str],
) -> str | None:
    if tabla is None or tabla.empty:
        return None

    mapa = {
        _normalizar_nombre_columna(columna): columna
        for columna in tabla.columns
    }

    for candidato in candidatos:
        clave = _normalizar_nombre_columna(candidato)

        if clave in mapa:
            return mapa[clave]

    return None


def _buscar_columna_parcial(
    tabla: pd.DataFrame,
    fragmentos: list[str],
    excluir: list[str] | None = None,
) -> str | None:
    """
    Busca una columna por fragmentos normalizados cuando el nombre
    exacto cambia entre versiones del reporte.
    """
    if tabla is None or tabla.empty:
        return None

    excluir = excluir or []
    fragmentos_norm = [
        _normalizar_nombre_columna(
            fragmento
        )
        for fragmento in fragmentos
    ]
    excluir_norm = [
        _normalizar_nombre_columna(
            fragmento
        )
        for fragmento in excluir
    ]

    for columna in tabla.columns:
        nombre = _normalizar_nombre_columna(
            columna
        )

        if any(
            fragmento in nombre
            for fragmento in excluir_norm
        ):
            continue

        if any(
            fragmento in nombre
            for fragmento in fragmentos_norm
        ):
            return columna

    return None


def _serie_texto(
    tabla: pd.DataFrame,
    candidatos: list[str],
) -> pd.Series:
    columna = _buscar_columna(
        tabla,
        candidatos,
    )

    if columna is None:
        return pd.Series(
            "",
            index=tabla.index,
            dtype="object",
        )

    return (
        tabla[columna]
        .fillna("")
        .astype(str)
        .map(_normalizar_texto)
    )


def _serie_numero(
    tabla: pd.DataFrame,
    candidatos: list[str],
) -> pd.Series:
    columna = _buscar_columna(
        tabla,
        candidatos,
    )

    if columna is None:
        return pd.Series(
            0.0,
            index=tabla.index,
            dtype="float64",
        )

    return pd.to_numeric(
        tabla[columna],
        errors="coerce",
    ).fillna(0)


def _serie_fecha(
    tabla: pd.DataFrame,
    candidatos: list[str],
) -> pd.Series:
    columna = _buscar_columna(
        tabla,
        candidatos,
    )

    if columna is None:
        return pd.Series(
            pd.NaT,
            index=tabla.index,
            dtype="datetime64[ns]",
        )

    return pd.to_datetime(
        tabla[columna],
        errors="coerce",
        dayfirst=True,
    )


def _normalizar_ubicacion(valor: object) -> str:
    texto = _normalizar_texto(valor)
    texto = texto.replace("_", "-").replace("/", "-").replace(" ", "-")
    texto = re.sub(r"-+", "-", texto).strip("-")

    segmentos = [
        segmento
        for segmento in texto.split("-")
        if segmento
    ]

    if len(segmentos) >= 4:
        prefijo = segmentos[-4]
        partes = [
            segmento.zfill(3)
            if segmento.isdigit()
            else segmento
            for segmento in segmentos[-3:]
        ]
        return "-".join([prefijo, *partes])

    return texto


def _clasificar_sector_calidad(
    ubicacion: object,
    area: object = "",
) -> str:
    clave = _normalizar_ubicacion(
        ubicacion
    )
    area_texto = _normalizar_texto(
        area
    )

    if clave.startswith("LAB-") or "LABORATORIO" in area_texto:
        return "Laboratorio"

    if clave == "CAL-001-001-001":
        return "Tránsito"

    if clave == "CAL-002-001-001":
        return "Mercadería de segunda"

    if clave == "CAL-003-001-001":
        return "Reproceso pendiente"

    if clave.startswith("CAL-"):
        return "Racks Calidad"

    if "CALIDAD" in area_texto:
        return "Calidad sin clasificar"

    return "Sin clasificar"


def preparar_stock_calidad(
    stock_calidad: pd.DataFrame,
    tabla_articulos: pd.DataFrame | None = None,
    tabla_volumetria: pd.DataFrame | None = None,
    maestro_ubicaciones: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columnas_salida = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "AreaReporte",
        "Ubicacion",
        "Contenedor",
        "ContenedorDetectado",
        "Lote",
        "Cantidad",
        "VolumenUnitarioM3",
        "VolumenTotalM3",
        "FechaVencimiento",
        "DiasAlVencimiento",
        "FechaIngresoEstimada",
        "DiasEnCalidad",
        "SectorCalidad",
        "ClaveRegistroCalidad",
    ]

    if (
        stock_calidad is None
        or stock_calidad.empty
    ):
        return pd.DataFrame(
            columns=columnas_salida
        )

    origen = stock_calidad.copy()
    tabla = pd.DataFrame(
        index=origen.index
    )

    tabla["ArticuloCodigo"] = _serie_texto(
        origen,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "Código Artículo",
            "Codigo",
            "Artículo",
            "Articulo",
            "CodArticulo",
        ],
    )
    tabla["ArticuloDescripcion"] = _serie_texto(
        origen,
        [
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "Descripción",
            "Descripcion",
        ],
    )
    tabla["AreaReporte"] = _serie_texto(
        origen,
        [
            "Area",
            "Área",
            "Sector",
            "Zona",
        ],
    )
    tabla["Ubicacion"] = _serie_texto(
        origen,
        [
            "Ubicacion",
            "Ubicación",
            "CodigoUbicacion",
            "UbicacionCodigo",
            "Location",
            "Posicion",
        ],
    ).map(_normalizar_ubicacion)
    tabla["CodigoVerificadorStock"] = _serie_texto(
        origen,
        [
            "CodigoVerificador",
            "Código Verificador",
            "Codigo Verificador",
            "Verificador",
            "CodigoVerif",
            "Código Verif.",
        ],
    )
    columna_contenedor = _buscar_columna(
        origen,
        [
            "Contenedor",
            "ContenedorNumero",
            "Contenedor Número",
            "NumeroContenedor",
            "Número Contenedor",
            "NroContenedor",
            "Nro. Contenedor",
            "CodigoContenedor",
            "Código Contenedor",
            "ContenedorCodigo",
            "Contenedor Código",
            "IdentificadorContenedor",
            "IdContenedor",
            "Container",
            "ContainerNumber",
            "ContainerId",
            "LPN",
            "SSCC",
        ],
    )

    if columna_contenedor is None:
        columna_contenedor = _buscar_columna_parcial(
            origen,
            [
                "contenedor",
                "container",
                "lpn",
                "sscc",
            ],
            excluir=[
                "cantidad",
                "capacidad",
                "ubicacion",
                "verificador",
            ],
        )

    if columna_contenedor is None:
        tabla["Contenedor"] = pd.Series(
            "",
            index=origen.index,
            dtype="object",
        )
    else:
        # Se convierte directamente a texto para conservar ceros
        # iniciales y códigos alfanuméricos.
        tabla["Contenedor"] = (
            origen[columna_contenedor]
            .fillna("")
            .astype(str)
            .map(_normalizar_texto)
        )
    tabla["Lote"] = _serie_texto(
        origen,
        ["Lote", "Lot"],
    )
    tabla["Cantidad"] = _serie_numero(
        origen,
        [
            "Cantidad",
            "Unidades",
            "Stock",
            "CantidadStock",
            "Cantidad Disponible",
        ],
    ).clip(lower=0)
    tabla["FechaVencimiento"] = _serie_fecha(
        origen,
        [
            "FechaVencimiento",
            "Fecha Vencimiento",
            "Vencimiento",
        ],
    )
    tabla["DiasAlVencimiento"] = _serie_numero(
        origen,
        [
            "DiasAlVencimiento",
            "Dias Vencimiento",
            "Días",
            "Dias",
        ],
    )

    tabla = tabla.loc[
        tabla["ArticuloCodigo"].ne("")
        & tabla["Cantidad"].gt(0)
    ].copy()

    if tabla.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    # ------------------------------------------------------
    # Maestro de artículos
    # ------------------------------------------------------
    tabla["Familia"] = ""
    tabla["Familia2"] = ""
    tabla["Sectorizacion"] = ""

    if (
        tabla_articulos is not None
        and not tabla_articulos.empty
    ):
        articulos = tabla_articulos.copy()
        codigo_col = _buscar_columna(
            articulos,
            [
                "ArticuloCodigo",
                "CodigoArticulo",
                "Codigo",
                "Artículo",
            ],
        )

        if codigo_col is not None:
            articulos["_CodigoCalidad"] = (
                articulos[codigo_col]
                .fillna("")
                .astype(str)
                .map(_normalizar_texto)
            )

            columnas_mapear = {
                "ArticuloDescripcion": [
                    "ArticuloDescripcion",
                    "Descripcion",
                    "Descripción",
                ],
                "Familia": [
                    "Familia",
                    "Familia_1",
                    "Familia1",
                ],
                "Familia2": [
                    "Familia_2",
                    "Familia2",
                    "Subfamilia",
                ],
                "Sectorizacion": [
                    "Sectorizacion",
                    "Sectorización",
                    "Sector",
                ],
            }

            seleccion = ["_CodigoCalidad"]

            for destino, candidatos in columnas_mapear.items():
                columna = _buscar_columna(
                    articulos,
                    candidatos,
                )

                if columna is not None:
                    articulos[destino] = (
                        articulos[columna]
                        .fillna("")
                        .astype(str)
                        .map(_normalizar_texto)
                    )
                    seleccion.append(destino)

            metadata = (
                articulos[seleccion]
                .drop_duplicates(
                    "_CodigoCalidad"
                )
            )

            tabla = tabla.merge(
                metadata,
                how="left",
                left_on="ArticuloCodigo",
                right_on="_CodigoCalidad",
                suffixes=("", "_Maestro"),
                validate="many_to_one",
            )

            if "ArticuloDescripcion_Maestro" in tabla.columns:
                tabla["ArticuloDescripcion"] = (
                    tabla["ArticuloDescripcion"]
                    .where(
                        tabla[
                            "ArticuloDescripcion"
                        ].ne(""),
                        tabla[
                            "ArticuloDescripcion_Maestro"
                        ],
                    )
                )

            for columna in [
                "Familia",
                "Familia2",
                "Sectorizacion",
            ]:
                columna_maestro = (
                    f"{columna}_Maestro"
                )

                if columna_maestro in tabla.columns:
                    tabla[columna] = (
                        tabla[columna]
                        .where(
                            tabla[columna].ne(""),
                            tabla[columna_maestro],
                        )
                    )

    # ------------------------------------------------------
    # Volumetría
    # ------------------------------------------------------
    tabla["VolumenUnitarioM3"] = 0.0

    if (
        tabla_volumetria is not None
        and not tabla_volumetria.empty
    ):
        volumetria = tabla_volumetria.copy()
        codigo_col = _buscar_columna(
            volumetria,
            [
                "ArticuloCodigo",
                "CodigoArticulo",
                "Codigo",
                "Artículo",
            ],
        )
        volumen_col = _buscar_columna(
            volumetria,
            [
                "VolumenUnitarioM3",
                "VolumenM3",
                "Volumetria",
                "Volumetría",
                "M3",
            ],
        )

        if (
            codigo_col is not None
            and volumen_col is not None
        ):
            volumetria["_CodigoCalidad"] = (
                volumetria[codigo_col]
                .fillna("")
                .astype(str)
                .map(_normalizar_texto)
            )
            volumetria["_VolumenCalidad"] = (
                pd.to_numeric(
                    volumetria[volumen_col],
                    errors="coerce",
                )
                .fillna(0)
                .clip(lower=0)
            )

            mapa_volumen = (
                volumetria.groupby(
                    "_CodigoCalidad"
                )["_VolumenCalidad"]
                .max()
            )

            tabla["VolumenUnitarioM3"] = (
                tabla["ArticuloCodigo"]
                .map(mapa_volumen)
                .fillna(0)
            )

    tabla["VolumenTotalM3"] = (
        tabla["Cantidad"]
        * tabla["VolumenUnitarioM3"]
    )

    # ------------------------------------------------------
    # Fecha estimada de ingreso
    # ------------------------------------------------------
    tabla["FechaIngresoEstimada"] = (
        tabla["FechaVencimiento"]
        - pd.to_timedelta(
            2000,
            unit="D",
        )
    )

    hoy = pd.Timestamp.today().normalize()
    fecha_respaldo = (
        hoy
        - pd.to_timedelta(
            (
                2000
                - tabla["DiasAlVencimiento"]
            ).clip(lower=0),
            unit="D",
        )
    )

    tabla["FechaIngresoEstimada"] = (
        tabla["FechaIngresoEstimada"]
        .where(
            tabla[
                "FechaIngresoEstimada"
            ].notna(),
            fecha_respaldo,
        )
    )

    tabla["DiasEnCalidad"] = (
        hoy
        - tabla[
            "FechaIngresoEstimada"
        ].dt.normalize()
    ).dt.days.clip(lower=0)

    # ------------------------------------------------------
    # Ubicación por código verificador como respaldo
    # ------------------------------------------------------
    if (
        maestro_ubicaciones is not None
        and not maestro_ubicaciones.empty
    ):
        maestro = preparar_maestro_ubicaciones(
            maestro_ubicaciones
        )

        if not maestro.empty:
            verificadores = (
                maestro.loc[
                    maestro[
                        "CodigoVerificador"
                    ].astype(str).str.strip().ne("")
                ][
                    [
                        "CodigoVerificador",
                        "ClaveUbicacion",
                    ]
                ]
                .drop_duplicates(
                    "CodigoVerificador"
                )
            )

            mapa_verificador = dict(
                zip(
                    verificadores[
                        "CodigoVerificador"
                    ].map(_normalizar_texto),
                    verificadores[
                        "ClaveUbicacion"
                    ],
                )
            )

            # El reporte Stock Calidad Laboratorio identifica la
            # posición principalmente mediante CodigoVerificador.
            # Se cruza contra el mismo campo del Maestro de Ubicaciones.
            mascara_sin_ubicacion = (
                tabla["Ubicacion"].eq("")
                & tabla[
                    "CodigoVerificadorStock"
                ].ne("")
            )

            tabla.loc[
                mascara_sin_ubicacion,
                "Ubicacion",
            ] = (
                tabla.loc[
                    mascara_sin_ubicacion,
                    "CodigoVerificadorStock",
                ]
                .map(mapa_verificador)
                .fillna("")
            )

            # También se corrigen ubicaciones que vengan informadas con
            # el propio código verificador en lugar de la clave CAL/LAB.
            mascara_ubicacion_es_verificador = (
                tabla["Ubicacion"].ne("")
                & ~tabla["Ubicacion"].str.match(
                    r"^(CAL|LAB)-",
                    na=False,
                )
                & tabla["Ubicacion"].isin(
                    mapa_verificador
                )
            )

            tabla.loc[
                mascara_ubicacion_es_verificador,
                "Ubicacion",
            ] = tabla.loc[
                mascara_ubicacion_es_verificador,
                "Ubicacion",
            ].map(
                mapa_verificador
            )

    tabla["UbicacionEncontrada"] = (
        tabla["Ubicacion"]
        .fillna("")
        .astype(str)
        .str.match(
            r"^(CAL|LAB)-",
            na=False,
        )
    )

    tabla["SectorCalidad"] = [
        _clasificar_sector_calidad(
            ubicacion,
            area,
        )
        for ubicacion, area in zip(
            tabla["Ubicacion"],
            tabla["AreaReporte"],
        )
    ]

    # Si excepcionalmente el reporte no trae ningún identificador
    # de contenedor, se conserva un identificador técnico por fila para
    # que la tabla no pierda trazabilidad. Este respaldo NO se utiliza
    # para inflar la ocupación por pallets.
    tabla["ContenedorDetectado"] = (
        tabla["Contenedor"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    tabla["ClaveRegistroCalidad"] = (
        tabla["Ubicacion"]
        .where(
            tabla["Ubicacion"].ne(""),
            "SIN_UBICACION",
        )
        + "|"
        + tabla["Contenedor"]
        .where(
            tabla["Contenedor"].ne(""),
            "SIN_CONTENEDOR",
        )
        + "|"
        + tabla["ArticuloCodigo"]
    )

    for columna in [
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "AreaReporte",
        "Ubicacion",
        "Contenedor",
        "Lote",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
        )

    return tabla[
        columnas_salida
    ].reset_index(drop=True)



def _preparar_capacidad_calidad_desde_maestro(
    maestro_ubicaciones: pd.DataFrame,
) -> pd.DataFrame:
    """
    Recupera la capacidad real directamente desde el Maestro de
    Ubicaciones, tolerando variantes del nombre de la columna.
    """
    columnas_salida = [
        "ClaveUbicacion",
        "CapacidadRealCalidad",
    ]

    if (
        maestro_ubicaciones is None
        or maestro_ubicaciones.empty
    ):
        return pd.DataFrame(
            columns=columnas_salida
        )

    maestro = maestro_ubicaciones.copy()

    columna_ab = _buscar_columna(
        maestro,
        [
            "Ab",
            "Abreviatura",
            "AreaAb",
            "Código Área",
        ],
    )
    columna_pasillo = _buscar_columna(
        maestro,
        [
            "Pasillo",
            "Aisle",
        ],
    )
    columna_posicion = _buscar_columna(
        maestro,
        [
            "Posicion",
            "Posición",
            "Position",
        ],
    )
    columna_nivel = _buscar_columna(
        maestro,
        [
            "Nivel",
            "Level",
        ],
    )
    columna_capacidad = _buscar_columna(
        maestro,
        [
            "Capacidad Pallets",
            "CapacidadPallets",
            "Capacidad_Pallets",
            "Capacidad pallet",
            "Capacidad",
        ],
    )

    if columna_capacidad is None:
        columna_capacidad = _buscar_columna_parcial(
            maestro,
            [
                "capacidadpallet",
                "palletcapacity",
            ],
        )

    if (
        columna_ab is None
        or columna_pasillo is None
        or columna_posicion is None
        or columna_nivel is None
    ):
        return pd.DataFrame(
            columns=columnas_salida
        )

    def segmento(valor: object) -> str:
        texto = _normalizar_texto(valor)
        return (
            texto.zfill(3)
            if texto.isdigit()
            else texto
        )

    resultado = pd.DataFrame(
        {
            "ClaveUbicacion": (
                maestro[columna_ab]
                .map(_normalizar_texto)
                + "-"
                + maestro[columna_pasillo]
                .map(segmento)
                + "-"
                + maestro[columna_posicion]
                .map(segmento)
                + "-"
                + maestro[columna_nivel]
                .map(segmento)
            )
        }
    )

    if columna_capacidad is None:
        resultado[
            "CapacidadRealCalidad"
        ] = 1.0
    else:
        capacidad_texto = (
            maestro[columna_capacidad]
            .astype("string")
            .str.replace(
                ",",
                ".",
                regex=False,
            )
            .str.extract(
                r"(\d+(?:\.\d+)?)",
                expand=False,
            )
        )

        resultado[
            "CapacidadRealCalidad"
        ] = pd.to_numeric(
            capacidad_texto,
            errors="coerce",
        ).fillna(1).clip(lower=1)

    # Si existe más de una fila para la misma ubicación física,
    # se conserva la mayor capacidad declarada.
    resultado = (
        resultado.groupby(
            "ClaveUbicacion",
            as_index=False,
        )
        .agg(
            CapacidadRealCalidad=(
                "CapacidadRealCalidad",
                "max",
            )
        )
    )

    return resultado[columnas_salida]



def construir_ocupacion_calidad(
    maestro_ubicaciones: pd.DataFrame,
    detalle_calidad: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    """
    Construye la ocupación de Calidad directamente desde el maestro crudo.

    Reglas:
    - Laboratorio: suma de Capacidad Pallets de ubicaciones LAB.
    - Piso Calidad: suma de Capacidad Pallets de CAL-002 y CAL-003.
    - Racks Calidad: cantidad de ubicaciones físicas CAL restantes,
      sin utilizar el campo Disponible.
    - Tránsito: capacidad de CAL-001, mostrada separadamente.
    """
    columnas_salida = [
        "GrupoCalidad",
        "Capacidad",
        "Ocupado",
        "Libre",
        "Porcentaje",
        "Unidad",
        "Ubicaciones",
        "Contenedores",
        "SKU",
        "Unidades",
        "VolumenM3",
    ]

    if (
        maestro_ubicaciones is None
        or maestro_ubicaciones.empty
    ):
        return (
            pd.DataFrame(
                columns=columnas_salida
            ),
            {
                "capacidad_total": 0.0,
                "ocupado_total": 0.0,
                "libre_total": 0.0,
                "porcentaje_total": 0.0,
            },
        )

    maestro_crudo = maestro_ubicaciones.copy()

    columna_ab = _buscar_columna(
        maestro_crudo,
        [
            "Ab",
            "Abreviatura",
            "AreaAb",
        ],
    )
    columna_area = _buscar_columna(
        maestro_crudo,
        [
            "Area",
            "Área",
        ],
    )
    columna_pasillo = _buscar_columna(
        maestro_crudo,
        [
            "Pasillo",
            "Aisle",
        ],
    )
    columna_posicion = _buscar_columna(
        maestro_crudo,
        [
            "Posicion",
            "Posición",
            "Position",
        ],
    )
    columna_nivel = _buscar_columna(
        maestro_crudo,
        [
            "Nivel",
            "Level",
        ],
    )
    columna_capacidad = _buscar_columna(
        maestro_crudo,
        [
            "Capacidad Pallets",
            "CapacidadPallets",
            "Capacidad_Pallets",
            "Capacidad pallet",
            "Capacidad",
        ],
    )

    if columna_capacidad is None:
        columna_capacidad = (
            _buscar_columna_parcial(
                maestro_crudo,
                [
                    "capacidadpallet",
                    "palletcapacity",
                ],
            )
        )

    if (
        columna_pasillo is None
        or columna_posicion is None
        or columna_nivel is None
    ):
        return (
            pd.DataFrame(
                columns=columnas_salida
            ),
            {
                "capacidad_total": 0.0,
                "ocupado_total": 0.0,
                "libre_total": 0.0,
                "porcentaje_total": 0.0,
            },
        )

    def normalizar_segmento(
        valor: object,
    ) -> str:
        texto = _normalizar_texto(
            valor
        )
        return (
            texto.zfill(3)
            if texto.isdigit()
            else texto
        )

    if columna_ab is not None:
        prefijo = (
            maestro_crudo[columna_ab]
            .fillna("")
            .astype(str)
            .map(_normalizar_texto)
        )
    elif columna_area is not None:
        area_serie = (
            maestro_crudo[columna_area]
            .fillna("")
            .astype(str)
            .map(_normalizar_texto)
        )
        prefijo = pd.Series(
            "",
            index=maestro_crudo.index,
            dtype="object",
        )
        prefijo.loc[
            area_serie.str.contains(
                "LABORATORIO",
                na=False,
            )
        ] = "LAB"
        prefijo.loc[
            area_serie.str.contains(
                "CALIDAD",
                na=False,
            )
        ] = "CAL"
    else:
        prefijo = pd.Series(
            "",
            index=maestro_crudo.index,
            dtype="object",
        )

    maestro_base = pd.DataFrame(
        index=maestro_crudo.index
    )
    maestro_base["Ab"] = prefijo
    maestro_base["Pasillo"] = (
        maestro_crudo[columna_pasillo]
        .map(normalizar_segmento)
    )
    maestro_base["Posicion"] = (
        maestro_crudo[columna_posicion]
        .map(normalizar_segmento)
    )
    maestro_base["Nivel"] = (
        maestro_crudo[columna_nivel]
        .map(normalizar_segmento)
    )
    maestro_base["ClaveUbicacion"] = (
        maestro_base["Ab"]
        + "-"
        + maestro_base["Pasillo"]
        + "-"
        + maestro_base["Posicion"]
        + "-"
        + maestro_base["Nivel"]
    )

    if columna_capacidad is None:
        maestro_base[
            "CapacidadPallets"
        ] = 1.0
    else:
        capacidad_texto = (
            maestro_crudo[columna_capacidad]
            .astype("string")
            .str.replace(
                ".",
                "",
                regex=False,
            )
            .str.replace(
                ",",
                ".",
                regex=False,
            )
            .str.extract(
                r"(-?\d+(?:\.\d+)?)",
                expand=False,
            )
        )

        maestro_base[
            "CapacidadPallets"
        ] = (
            pd.to_numeric(
                capacidad_texto,
                errors="coerce",
            )
            .fillna(1)
            .clip(lower=1)
        )

    # Una ubicación física puede repetirse en el maestro. Se conserva
    # una sola fila y la mayor capacidad declarada.
    maestro_base = (
        maestro_base.loc[
            maestro_base["Ab"].isin(
                ["CAL", "LAB"]
            )
        ]
        .groupby(
            [
                "ClaveUbicacion",
                "Ab",
                "Pasillo",
                "Posicion",
                "Nivel",
            ],
            as_index=False,
        )
        .agg(
            CapacidadPallets=(
                "CapacidadPallets",
                "max",
            )
        )
    )

    maestro_base[
        "SectorCalidad"
    ] = "Sin clasificar"

    maestro_base.loc[
        maestro_base["Ab"].eq("LAB"),
        "SectorCalidad",
    ] = "Laboratorio"

    maestro_base.loc[
        maestro_base["Ab"].eq("CAL")
        & maestro_base["Pasillo"].eq("001"),
        "SectorCalidad",
    ] = "Tránsito"

    maestro_base.loc[
        maestro_base["Ab"].eq("CAL")
        & maestro_base["Pasillo"].eq("002"),
        "SectorCalidad",
    ] = "Mercadería de segunda"

    maestro_base.loc[
        maestro_base["Ab"].eq("CAL")
        & maestro_base["Pasillo"].eq("003"),
        "SectorCalidad",
    ] = "Reproceso pendiente"

    maestro_base.loc[
        maestro_base["Ab"].eq("CAL")
        & ~maestro_base["Pasillo"].isin(
            ["001", "002", "003"]
        ),
        "SectorCalidad",
    ] = "Racks Calidad"

    detalle = (
        detalle_calidad.copy()
        if detalle_calidad is not None
        else pd.DataFrame()
    )

    if not detalle.empty:
        detalle["Ubicacion"] = (
            detalle["Ubicacion"]
            .fillna("")
            .astype(str)
            .map(_normalizar_ubicacion)
        )
        detalle["Contenedor"] = (
            detalle["Contenedor"]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        detalle["SectorCalidad"] = (
            detalle["SectorCalidad"]
            .fillna("")
            .astype(str)
        )

    configuracion = [
        {
            "nombre": "Laboratorio",
            "sectores": [
                "Laboratorio",
            ],
            "tipo": "pallets",
        },
        {
            "nombre": "Piso Calidad",
            "sectores": [
                "Mercadería de segunda",
                "Reproceso pendiente",
            ],
            "tipo": "pallets",
        },
        {
            "nombre": "Racks Calidad",
            "sectores": [
                "Racks Calidad",
            ],
            "tipo": "ubicaciones",
        },
        {
            "nombre": "Tránsito",
            "sectores": [
                "Tránsito",
            ],
            "tipo": "pallets",
        },
    ]

    filas = []

    for regla in configuracion:
        nombre = regla["nombre"]
        sectores = regla["sectores"]
        tipo = regla["tipo"]

        maestro_grupo = (
            maestro_base.loc[
                maestro_base[
                    "SectorCalidad"
                ].isin(sectores)
            ].copy()
        )

        detalle_grupo = (
            detalle.loc[
                detalle[
                    "SectorCalidad"
                ].isin(sectores)
            ].copy()
            if not detalle.empty
            else pd.DataFrame()
        )

        if tipo == "pallets":
            # Piso y Laboratorio utilizan la capacidad pallet declarada
            # directamente en el maestro.
            capacidad = float(
                maestro_grupo[
                    "CapacidadPallets"
                ].sum()
            )
            ocupado = float(
                detalle_grupo.loc[
                    detalle_grupo[
                        "Contenedor"
                    ].ne(""),
                    "Contenedor",
                ].nunique()
                if not detalle_grupo.empty
                else 0
            )
            unidad = "pallets"
        else:
            # En racks cada clave física representa una posición.
            # No se utiliza Disponible porque en Calidad figura FALSO
            # por no ser stock vendible.
            capacidad = float(
                maestro_grupo[
                    "ClaveUbicacion"
                ].nunique()
            )

            ubicaciones_validas = set(
                maestro_grupo[
                    "ClaveUbicacion"
                ].dropna().astype(str)
            )

            if not detalle_grupo.empty:
                ocupadas_reales = (
                    detalle_grupo.loc[
                        detalle_grupo[
                            "Ubicacion"
                        ].isin(
                            ubicaciones_validas
                        )
                    ][
                        "Ubicacion"
                    ].nunique()
                )
            else:
                ocupadas_reales = 0

            ocupado = float(
                ocupadas_reales
            )
            unidad = "ubicaciones"

        # La ocupación nunca puede superar la capacidad física.
        ocupado = min(
            ocupado,
            capacidad,
        )
        libre = max(
            capacidad - ocupado,
            0,
        )
        porcentaje = (
            ocupado / capacidad * 100
            if capacidad > 0
            else 0
        )

        filas.append(
            {
                "GrupoCalidad": nombre,
                "Capacidad": capacidad,
                "Ocupado": ocupado,
                "Libre": libre,
                "Porcentaje": porcentaje,
                "Unidad": unidad,
                "Ubicaciones": int(
                    detalle_grupo.loc[
                        detalle_grupo[
                            "Ubicacion"
                        ].ne(""),
                        "Ubicacion",
                    ].nunique()
                    if not detalle_grupo.empty
                    else 0
                ),
                "Contenedores": int(
                    detalle_grupo.loc[
                        detalle_grupo[
                            "Contenedor"
                        ].ne(""),
                        "Contenedor",
                    ].nunique()
                    if not detalle_grupo.empty
                    else 0
                ),
                "SKU": int(
                    detalle_grupo[
                        "ArticuloCodigo"
                    ].nunique()
                    if not detalle_grupo.empty
                    else 0
                ),
                "Unidades": float(
                    detalle_grupo[
                        "Cantidad"
                    ].sum()
                    if not detalle_grupo.empty
                    else 0
                ),
                "VolumenM3": float(
                    detalle_grupo[
                        "VolumenTotalM3"
                    ].sum()
                    if not detalle_grupo.empty
                    else 0
                ),
            }
        )

    ocupacion = pd.DataFrame(
        filas,
        columns=columnas_salida,
    )

    global_base = ocupacion.loc[
        ocupacion[
            "GrupoCalidad"
        ].ne("Tránsito")
    ].copy()

    capacidad_total = float(
        global_base[
            "Capacidad"
        ].sum()
    )
    ocupado_total = float(
        global_base[
            "Ocupado"
        ].sum()
    )
    libre_total = max(
        capacidad_total - ocupado_total,
        0,
    )

    resumen_global = {
        "capacidad_total": capacidad_total,
        "ocupado_total": ocupado_total,
        "libre_total": libre_total,
        "porcentaje_total": (
            ocupado_total
            / capacidad_total
            * 100
            if capacidad_total > 0
            else 0
        ),
    }

    return (
        ocupacion,
        resumen_global,
    )


def resumir_stock_calidad(
    detalle_calidad: pd.DataFrame,
) -> pd.DataFrame:
    columnas = [
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "Familia",
        "Familia2",
        "Sectorizacion",
        "SectorCalidad",
        "Unidades",
        "Contenedores",
        "Ubicaciones",
        "VolumenTotalM3",
        "DiasEnCalidad",
        "FechaIngresoEstimada",
    ]

    if (
        detalle_calidad is None
        or detalle_calidad.empty
    ):
        return pd.DataFrame(
            columns=columnas
        )

    resumen = (
        detalle_calidad.groupby(
            [
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Familia2",
                "Sectorizacion",
                "SectorCalidad",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Unidades=(
                "Cantidad",
                "sum",
            ),
            Contenedores=(
                "Contenedor",
                lambda serie: serie.loc[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            Ubicaciones=(
                "Ubicacion",
                lambda serie: serie.loc[
                    serie.astype(str).str.strip().ne("")
                ].nunique(),
            ),
            VolumenTotalM3=(
                "VolumenTotalM3",
                "sum",
            ),
            DiasEnCalidad=(
                "DiasEnCalidad",
                "max",
            ),
            FechaIngresoEstimada=(
                "FechaIngresoEstimada",
                "min",
            ),
        )
    )

    return resumen[
        columnas
    ].sort_values(
        [
            "DiasEnCalidad",
            "Unidades",
        ],
        ascending=[
            False,
            False,
        ],
        na_position="last",
    ).reset_index(drop=True)
