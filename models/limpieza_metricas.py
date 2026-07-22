"""
ETL de históricos de Control y Preparación.

Salidas principales:
- tareas_control
- tareas_preparacion
- tareas: ambos procesos homologados
- detalle_control
- detalle_preparacion
- detalle: ambos procesos homologados
- calidad
"""

import pandas as pd


COLUMNAS_TAREAS = [
    "Proceso",
    "TareaId",
    "FechaInicio",
    "FechaFin",
    "Fecha",
    "Anio",
    "Mes",
    "MesNumero",
    "Dia",
    "DiaSemana",
    "HoraInicio",
    "HoraFin",
    "Usuario",
    "UsuarioId",
    "Tipo",
    "VehiculoSugerido",
    "VehiculoReal",
    "TiempoEstimadoSegundos",
    "TiempoRealSegundos",
    "TiempoEntreTareasSegundos",
    "CumplioTiempo",
    "CumplioTiempoEntreTareas",
    "UnidadesTarea",
    "Articulos",
    "CantidadConversionTarea",
    "DuracionCalculadaSegundos",
    "DiferenciaTiempoSegundos",
    "EficienciaPct",
    "ArchivoOrigen",
]


COLUMNAS_DETALLE = [
    "Proceso",
    "TareaId",
    "FechaInicio",
    "Fecha",
    "Usuario",
    "UsuarioId",
    "CodigoArticulo",
    "DescripcionArticulo",
    "UnidadesDetalle",
    "CantidadConversionDetalle",
    "FechaPickeo",
    "Ubicacion",
    "Orden",
    "SegundosEnPickear",
    "ArchivoOrigen",
]


def asegurar_columnas(
    dataframe: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    """Agrega como NA las columnas que no existan."""

    resultado = dataframe.copy()

    for columna in columnas:
        if columna not in resultado.columns:
            resultado[columna] = pd.NA

    return resultado


def limpiar_texto(
    serie: pd.Series,
    mayusculas: bool = False,
) -> pd.Series:
    """Normaliza espacios y valores nulos de una columna textual."""

    resultado = (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if mayusculas:
        resultado = resultado.str.upper()

    return resultado


def convertir_fecha(
    serie: pd.Series,
) -> pd.Series:
    """
    Convierte las fechas exportadas por DIGIP/WMS.

    El formato real de los archivos históricos es:

        MM/DD/YYYY HH:MM:SS

    Ejemplo:
        04/06/2026 06:09:21
        corresponde al 6 de abril de 2026.

    No debe utilizarse dayfirst=True porque desplaza
    registros hacia meses incorrectos.
    """

    return pd.to_datetime(
        serie,
        format="%m/%d/%Y %H:%M:%S",
        errors="coerce",
    )


def convertir_numero(
    serie: pd.Series,
) -> pd.Series:
    """Convierte una serie a número."""

    return pd.to_numeric(
        serie,
        errors="coerce",
    )


MAPA_MESES = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SEPTIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}


def agregar_variables_temporales(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega variables de calendario y hora."""

    resultado = dataframe.copy()

    resultado["Fecha"] = (
        resultado["FechaInicio"].dt.normalize()
    )

    resultado["Anio"] = (
        resultado["FechaInicio"].dt.year
    )

    resultado["MesNumero"] = (
        resultado["FechaInicio"].dt.month
    )

    resultado["Mes"] = (
        resultado["FechaInicio"]
        .dt.month
        .map(MAPA_MESES)
    )
    mapa_dias = {
        0: "LUNES",
        1: "MARTES",
        2: "MIERCOLES",
        3: "JUEVES",
        4: "VIERNES",
        5: "SABADO",
        6: "DOMINGO",
    }

    resultado["DiaSemana"] = (
        resultado["FechaInicio"]
        .dt.dayofweek
        .map(mapa_dias)
    )

    resultado["Dia"] = (
        resultado["FechaInicio"].dt.day
    )

    resultado["HoraInicio"] = (
        resultado["FechaInicio"].dt.strftime(
            "%H:%M:%S"
        )
    )

    resultado["HoraFin"] = (
        resultado["FechaFin"].dt.strftime(
            "%H:%M:%S"
        )
    )

    return resultado


def agregar_metricas_tiempo(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula métricas derivadas sin reemplazar los tiempos originales."""

    resultado = dataframe.copy()

    resultado["DuracionCalculadaSegundos"] = (
        resultado["FechaFin"]
        - resultado["FechaInicio"]
    ).dt.total_seconds()

    resultado["DiferenciaTiempoSegundos"] = (
        resultado["TiempoRealSegundos"]
        - resultado["TiempoEstimadoSegundos"]
    )

    denominador = resultado[
        "TiempoRealSegundos"
    ].where(
        resultado["TiempoRealSegundos"] > 0
    )

    resultado["EficienciaPct"] = (
        resultado["TiempoEstimadoSegundos"]
        / denominador
        * 100
    ).round(2)

    return resultado


def puntuar_nombre_usuario(
    valor: object,
) -> int:
    """
    Asigna mayor puntaje a nombres y apellidos.

    Ejemplos:
        Gustavo Soderquvist -> puntaje alto
        gsoderquvist        -> puntaje bajo
    """

    texto = str(valor).strip()

    if not texto:
        return 0

    puntaje = 1

    # Los nombres completos suelen contener espacios.
    if " " in texto:
        puntaje += 10

    # Priorizar textos con mayúsculas y minúsculas,
    # característicos de nombre y apellido.
    if (
        any(caracter.isupper() for caracter in texto)
        and any(caracter.islower() for caracter in texto)
    ):
        puntaje += 3

    # Penalizar formatos típicos de usuario técnico.
    if texto.islower() and " " not in texto:
        puntaje -= 2

    return puntaje


def construir_maestro_usuarios(
    df_control: pd.DataFrame,
    df_preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye una equivalencia única de UsuarioId a nombre.

    Se combinan ambos procesos y se prioriza el valor que
    tenga aspecto de nombre y apellido.
    """

    bases = []

    for proceso, dataframe in [
        ("CONTROL", df_control),
        ("PREPARACION", df_preparacion),
    ]:

        if dataframe is None or dataframe.empty:
            continue

        base = asegurar_columnas(
            dataframe.copy(),
            [
                "UsuarioId",
                "Usuario",
            ],
        )[
            [
                "UsuarioId",
                "Usuario",
            ]
        ].copy()

        base["ProcesoOrigenUsuario"] = proceso

        base["UsuarioIdClave"] = (
            base["UsuarioId"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\\.0$",
                "",
                regex=True,
            )
        )

        base["UsuarioNombreCandidato"] = (
            base["Usuario"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        base = base[
            base["UsuarioIdClave"].ne("")
            & base["UsuarioNombreCandidato"].ne("")
        ].copy()

        bases.append(base)

    if not bases:

        return pd.DataFrame(
            columns=[
                "UsuarioIdClave",
                "UsuarioNombre",
            ]
        )

    candidatos = pd.concat(
        bases,
        ignore_index=True,
        sort=False,
    )

    candidatos = candidatos.drop_duplicates(
        subset=[
            "UsuarioIdClave",
            "UsuarioNombreCandidato",
        ]
    )

    candidatos["PuntajeNombre"] = (
        candidatos[
            "UsuarioNombreCandidato"
        ].map(
            puntuar_nombre_usuario
        )
    )

    # Ante empate se prioriza Preparación porque en los
    # reportes analizados contiene nombre y apellido.
    candidatos["PrioridadProceso"] = (
        candidatos[
            "ProcesoOrigenUsuario"
        ]
        .map(
            {
                "PREPARACION": 2,
                "CONTROL": 1,
            }
        )
        .fillna(0)
    )

    maestro = (
        candidatos
        .sort_values(
            [
                "UsuarioIdClave",
                "PuntajeNombre",
                "PrioridadProceso",
                "UsuarioNombreCandidato",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .drop_duplicates(
            subset=["UsuarioIdClave"],
            keep="first",
        )
        .rename(
            columns={
                "UsuarioNombreCandidato": (
                    "UsuarioNombre"
                ),
            }
        )
        [
            [
                "UsuarioIdClave",
                "UsuarioNombre",
            ]
        ]
        .reset_index(drop=True)
    )

    return maestro


def aplicar_maestro_usuarios(
    dataframe: pd.DataFrame,
    maestro_usuarios: pd.DataFrame,
) -> pd.DataFrame:
    """
    Reemplaza el usuario técnico por nombre y apellido,
    conservando UsuarioOriginal para auditoría.
    """

    if dataframe is None or dataframe.empty:
        return dataframe.copy()

    resultado = asegurar_columnas(
        dataframe.copy(),
        [
            "Usuario",
            "UsuarioId",
        ],
    )

    resultado["UsuarioOriginal"] = (
        resultado["Usuario"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    resultado["UsuarioIdClave"] = (
        resultado["UsuarioId"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            r"\\.0$",
            "",
            regex=True,
        )
    )

    if (
        maestro_usuarios is None
        or maestro_usuarios.empty
    ):

        resultado["UsuarioNombre"] = (
            resultado["UsuarioOriginal"]
        )

    else:

        resultado = resultado.merge(
            maestro_usuarios,
            on="UsuarioIdClave",
            how="left",
            validate="many_to_one",
        )

        resultado["UsuarioNombre"] = (
            resultado["UsuarioNombre"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        resultado["UsuarioNombre"] = (
            resultado["UsuarioNombre"]
            .where(
                resultado[
                    "UsuarioNombre"
                ].ne(""),
                resultado[
                    "UsuarioOriginal"
                ],
            )
        )

    # Usuario pasa a ser el campo estandarizado utilizado
    # por el dashboard y sus filtros.
    resultado["Usuario"] = (
        resultado["UsuarioNombre"]
    )

    return resultado


def preparar_base_control(
    df_control: pd.DataFrame,
) -> pd.DataFrame:
    """Normaliza columnas y tipos del histórico de Control."""

    if df_control.empty:
        return df_control.copy()

    resultado = df_control.copy()

    resultado = resultado.rename(
        columns={
            "ControlContenedorId": "TareaId",
        }
    )

    resultado = asegurar_columnas(
        resultado,
        [
            "TareaId",
            "FechaInicio",
            "FechaFin",
            "Usuario",
            "UsuarioId",
            "TiempoEstimadoSegundos",
            "TiempoRealSegundos",
            "TiempoEntreTareasSegundos",
            "CumplioTiempo",
            "CumplioTiempoEntreTareas",
            "Unidades",
            "Articulos",
            "CantidadConversion",
            "CodigoArticulo",
            "DescripcionArticulo",
            "UnidadesDetalle",
            "CantidadConversionDetalle",
            "ArchivoOrigen",
        ],
    )

    resultado["Proceso"] = "CONTROL"
    resultado["Tipo"] = "Control"
    resultado["VehiculoSugerido"] = ""
    resultado["VehiculoReal"] = ""

    for columna in [
        "FechaInicio",
        "FechaFin",
    ]:
        resultado[columna] = convertir_fecha(
            resultado[columna]
        )

    for columna in [
        "TareaId",
        "UsuarioId",
        "TiempoEstimadoSegundos",
        "TiempoRealSegundos",
        "TiempoEntreTareasSegundos",
        "Unidades",
        "Articulos",
        "CantidadConversion",
        "UnidadesDetalle",
        "CantidadConversionDetalle",
    ]:
        resultado[columna] = convertir_numero(
            resultado[columna]
        )

    for columna in [
        "Usuario",
        "CumplioTiempo",
        "CumplioTiempoEntreTareas",
        "CodigoArticulo",
        "DescripcionArticulo",
        "ArchivoOrigen",
    ]:
        resultado[columna] = limpiar_texto(
            resultado[columna]
        )

    return resultado


def preparar_base_preparacion(
    df_preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """Normaliza columnas y tipos del histórico de Preparación."""

    if df_preparacion.empty:
        return df_preparacion.copy()

    resultado = asegurar_columnas(
        df_preparacion.copy(),
        [
            "TareaId",
            "FechaInicio",
            "FechaFin",
            "Usuario",
            "UsuarioId",
            "Tipo",
            "VehiculoSugerido",
            "VehiculoReal",
            "TiempoEstimadoSegundos",
            "TiempoRealSegundos",
            "TiempoEntreTareasSegundos",
            "CumplioTiempo",
            "CumplioTiempoEntreTareas",
            "UnidadesTarea",
            "Articulos",
            "CantidadConversionTarea",
            "CodigoArticulo",
            "DescripcionArticulo",
            "UnidadesDetalle",
            "CantidadConversionDetalle",
            "FechaPickeo",
            "Ubicacion",
            "Orden",
            "SegundosEnPickear",
            "ArchivoOrigen",
        ],
    )

    resultado["Proceso"] = "PREPARACION"

    for columna in [
        "FechaInicio",
        "FechaFin",
        "FechaPickeo",
    ]:
        resultado[columna] = convertir_fecha(
            resultado[columna]
        )

    for columna in [
        "TareaId",
        "UsuarioId",
        "TiempoEstimadoSegundos",
        "TiempoRealSegundos",
        "TiempoEntreTareasSegundos",
        "UnidadesTarea",
        "Articulos",
        "CantidadConversionTarea",
        "UnidadesDetalle",
        "CantidadConversionDetalle",
        "Orden",
        "SegundosEnPickear",
    ]:
        resultado[columna] = convertir_numero(
            resultado[columna]
        )

    for columna in [
        "Usuario",
        "Tipo",
        "VehiculoSugerido",
        "VehiculoReal",
        "CumplioTiempo",
        "CumplioTiempoEntreTareas",
        "CodigoArticulo",
        "DescripcionArticulo",
        "Ubicacion",
        "ArchivoOrigen",
    ]:
        resultado[columna] = limpiar_texto(
            resultado[columna]
        )

    return resultado


def construir_tareas_control(
    control: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye una fila por tarea de Control.

    En Control, la columna Unidades aparece a nivel de línea.
    Por eso se suma dentro de cada TareaId.
    """

    if control.empty:
        return pd.DataFrame(
            columns=COLUMNAS_TAREAS
        )

    claves = [
        "Proceso",
        "TareaId",
        "ArchivoOrigen",
    ]

    tareas = (
        control
        .sort_values(
            ["TareaId", "FechaInicio"]
        )
        .groupby(
            claves,
            dropna=False,
            as_index=False,
        )
        .agg(
            FechaInicio=("FechaInicio", "min"),
            FechaFin=("FechaFin", "max"),
            Usuario=("Usuario", "first"),
            UsuarioId=("UsuarioId", "first"),
            Tipo=("Tipo", "first"),
            VehiculoSugerido=(
                "VehiculoSugerido",
                "first",
            ),
            VehiculoReal=("VehiculoReal", "first"),
            TiempoEstimadoSegundos=(
                "TiempoEstimadoSegundos",
                "first",
            ),
            TiempoRealSegundos=(
                "TiempoRealSegundos",
                "first",
            ),
            TiempoEntreTareasSegundos=(
                "TiempoEntreTareasSegundos",
                "first",
            ),
            CumplioTiempo=("CumplioTiempo", "first"),
            CumplioTiempoEntreTareas=(
                "CumplioTiempoEntreTareas",
                "first",
            ),
            UnidadesTarea=("Unidades", "sum"),
            Articulos=(
                "CodigoArticulo",
                lambda serie: serie[
                    serie.ne("")
                ].nunique(),
            ),
            CantidadConversionTarea=(
                "CantidadConversion",
                "sum",
            ),
        )
    )

    tareas = agregar_variables_temporales(
        tareas
    )

    tareas = agregar_metricas_tiempo(
        tareas
    )

    return asegurar_columnas(
        tareas,
        COLUMNAS_TAREAS,
    )[COLUMNAS_TAREAS]


def construir_tareas_preparacion(
    preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """Construye una fila por tarea de Preparación."""

    if preparacion.empty:
        return pd.DataFrame(
            columns=COLUMNAS_TAREAS
        )

    claves = [
        "Proceso",
        "TareaId",
        "ArchivoOrigen",
    ]

    tareas = (
        preparacion
        .sort_values(
            ["TareaId", "FechaInicio"]
        )
        .groupby(
            claves,
            dropna=False,
            as_index=False,
        )
        .agg(
            FechaInicio=("FechaInicio", "min"),
            FechaFin=("FechaFin", "max"),
            Usuario=("Usuario", "first"),
            UsuarioId=("UsuarioId", "first"),
            Tipo=("Tipo", "first"),
            VehiculoSugerido=(
                "VehiculoSugerido",
                "first",
            ),
            VehiculoReal=("VehiculoReal", "first"),
            TiempoEstimadoSegundos=(
                "TiempoEstimadoSegundos",
                "first",
            ),
            TiempoRealSegundos=(
                "TiempoRealSegundos",
                "first",
            ),
            TiempoEntreTareasSegundos=(
                "TiempoEntreTareasSegundos",
                "first",
            ),
            CumplioTiempo=("CumplioTiempo", "first"),
            CumplioTiempoEntreTareas=(
                "CumplioTiempoEntreTareas",
                "first",
            ),
            UnidadesTarea=("UnidadesTarea", "first"),
            Articulos=("Articulos", "first"),
            CantidadConversionTarea=(
                "CantidadConversionTarea",
                "first",
            ),
        )
    )

    tareas = agregar_variables_temporales(
        tareas
    )

    tareas = agregar_metricas_tiempo(
        tareas
    )

    return asegurar_columnas(
        tareas,
        COLUMNAS_TAREAS,
    )[COLUMNAS_TAREAS]


def construir_detalle_control(
    control: pd.DataFrame,
) -> pd.DataFrame:
    """Construye el detalle homologado de Control."""

    if control.empty:
        return pd.DataFrame(
            columns=COLUMNAS_DETALLE
        )

    detalle = control.copy()

    detalle["Fecha"] = (
        detalle["FechaInicio"].dt.normalize()
    )

    # En Control, Unidades contiene la cantidad de la línea.
    unidades_detalle_original = (
        detalle["UnidadesDetalle"]
        .fillna(0)
    )

    detalle["UnidadesDetalle"] = (
        unidades_detalle_original.where(
            unidades_detalle_original.ne(0),
            detalle["Unidades"],
        )
    )

    detalle["FechaPickeo"] = pd.NaT
    detalle["Ubicacion"] = ""
    detalle["Orden"] = pd.NA
    detalle["SegundosEnPickear"] = pd.NA

    detalle = asegurar_columnas(
        detalle,
        COLUMNAS_DETALLE,
    )

    return detalle[COLUMNAS_DETALLE].copy()


def construir_detalle_preparacion(
    preparacion: pd.DataFrame,
) -> pd.DataFrame:
    """Construye el detalle homologado de Preparación."""

    if preparacion.empty:
        return pd.DataFrame(
            columns=COLUMNAS_DETALLE
        )

    detalle = preparacion.copy()

    detalle["Fecha"] = (
        detalle["FechaInicio"].dt.normalize()
    )

    detalle = asegurar_columnas(
        detalle,
        COLUMNAS_DETALLE,
    )

    return detalle[COLUMNAS_DETALLE].copy()


def construir_resumen_calidad(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
) -> pd.DataFrame:
    """Genera controles básicos de calidad de la ETL."""

    controles = [
        {
            "Control": "Tareas totales",
            "Valor": len(tareas),
        },
        {
            "Control": "Tareas sin identificador",
            "Valor": int(
                tareas["TareaId"].isna().sum()
            ),
        },
        {
            "Control": "Tareas sin fecha de inicio",
            "Valor": int(
                tareas["FechaInicio"].isna().sum()
            ),
        },
        {
            "Control": "Tareas sin fecha de fin",
            "Valor": int(
                tareas["FechaFin"].isna().sum()
            ),
        },
        {
            "Control": "Tareas con tiempo real negativo",
            "Valor": int(
                (
                    tareas["TiempoRealSegundos"] < 0
                ).fillna(False).sum()
            ),
        },
        {
            "Control": "Líneas de detalle",
            "Valor": len(detalle),
        },
        {
            "Control": "Detalle sin código de artículo",
            "Valor": int(
                detalle["CodigoArticulo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq("")
                .sum()
            ),
        },
        {
            "Control": "Detalle sin tarea relacionada",
            "Valor": int(
                detalle["TareaId"].isna().sum()
            ),
        },
    ]

    return pd.DataFrame(controles)


def ejecutar_etl_metricas(
    df_control: pd.DataFrame,
    df_preparacion: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Ejecuta toda la primera etapa de ETL."""

    # Maestro común de usuarios para homologar
    # nombres entre Control y Preparación.
    maestro_usuarios = construir_maestro_usuarios(
        df_control=df_control,
        df_preparacion=df_preparacion,
    )

    control_limpio = preparar_base_control(
        df_control
    )

    preparacion_limpia = preparar_base_preparacion(
        df_preparacion
    )

    control_limpio = aplicar_maestro_usuarios(
        dataframe=control_limpio,
        maestro_usuarios=maestro_usuarios,
    )

    preparacion_limpia = aplicar_maestro_usuarios(
        dataframe=preparacion_limpia,
        maestro_usuarios=maestro_usuarios,
    )

    tareas_control = construir_tareas_control(
        control_limpio
    )

    tareas_preparacion = construir_tareas_preparacion(
        preparacion_limpia
    )

    detalle_control = construir_detalle_control(
        control_limpio
    )

    detalle_preparacion = construir_detalle_preparacion(
        preparacion_limpia
    )

    tareas = pd.concat(
        [
            tareas_control,
            tareas_preparacion,
        ],
        ignore_index=True,
        sort=False,
    )

    detalle = pd.concat(
        [
            detalle_control,
            detalle_preparacion,
        ],
        ignore_index=True,
        sort=False,
    )

    calidad = construir_resumen_calidad(
        tareas=tareas,
        detalle=detalle,
    )

    return {
        "control_crudo": df_control,
        "preparacion_crudo": df_preparacion,
        "maestro_usuarios": maestro_usuarios,
        "control_limpio": control_limpio,
        "preparacion_limpia": preparacion_limpia,
        "tareas_control": tareas_control,
        "tareas_preparacion": tareas_preparacion,
        "tareas": tareas,
        "detalle_control": detalle_control,
        "detalle_preparacion": detalle_preparacion,
        "detalle": detalle,
        "calidad": calidad,
    }
