"""
Motor de planificación logística.

Regla definitiva para pedidos con código de expreso:

1. Si la planificación contiene un día de LUNES a VIERNES,
   el pedido entra en la planificación semanal correspondiente.
2. En ese caso EsExpreso queda en False y el destino expreso
   no participa de la agrupación.
3. Si no existe un día semanal y el código es expreso,
   se utiliza el destino expreso: CABA SUR, CABA SUR II,
   CABA NORTE, etc.
"""

import re
import unicodedata

import pandas as pd

from config_planificacion import (
    ZONAS_PLANIFICACION,
    CLIENTES_PRIORITARIOS,
    PRIORIDAD_GENERAL,
    GRUPOS_EXCLUIDOS,
    obtener_planificacion_expreso,
)

# Código genérico usado por los pedidos enviados mediante expreso.
CODIGO_DESPACHO_EXPRESOS = "05010001"


# ==========================================================
# NORMALIZACIÓN
# ==========================================================

def normalizar_codigo(valor) -> str:

    if pd.isna(valor):
        return ""

    codigo = str(valor).strip()

    if codigo.endswith(".0"):
        codigo = codigo[:-2]

    return codigo


def codigo_comparable(valor) -> str:

    codigo = normalizar_codigo(valor)

    return codigo.lstrip("0") or "0"


CODIGO_EXPRESO_COMPARABLE = codigo_comparable(
    CODIGO_DESPACHO_EXPRESOS
)

# Los pedidos cargados con el código genérico de expreso,
# pero con un día semanal de entrega, deben planificarse
# como reparto normal y no como EXPRESOS.
DIAS_ENTREGA_SEMANAL = {
    "LUNES",
    "MARTES",
    "MIERCOLES",
    "JUEVES",
    "VIERNES",
}


def normalizar_texto_sin_acentos(valor) -> str:

    texto = normalizar_codigo(valor).upper()

    return "".join(
        caracter
        for caracter in unicodedata.normalize(
            "NFD",
            texto
        )
        if unicodedata.category(caracter) != "Mn"
    )


def extraer_dia_entrega(valor) -> str:
    """
    Convierte valores como:

    - Jueves
    - 4 - Jueves
    - 4 - Jueves | Grupo 1

    en:

    - JUEVES
    """

    texto = normalizar_texto_sin_acentos(valor)

    coincidencia = re.search(
        r"\\b(LUNES|MARTES|MIERCOLES|JUEVES|VIERNES)\\b",
        texto,
    )

    if coincidencia is None:
        return ""

    return coincidencia.group(1)


def extraer_grupo_entrega(valor) -> str:
    """
    Extrae el grupo desde valores como:

    4 - Jueves | Grupo 1
    """

    texto = normalizar_texto_sin_acentos(valor)

    coincidencia = re.search(
        r"GRUPO\\s*[-:]?\\s*([A-Z0-9]+)",
        texto,
    )

    if coincidencia is None:
        return "1"

    return coincidencia.group(1)


INDICE_ZONAS_NORMALIZADO = {
    codigo_comparable(codigo): {
        **configuracion,
        "codigo_original": str(codigo),
    }
    for codigo, configuracion
    in ZONAS_PLANIFICACION.items()
}


# ==========================================================
# CONFIGURACIÓN DE ZONAS Y PRIORIDADES
# ==========================================================

def es_codigo_expreso(codigo_despacho) -> bool:

    return (
        codigo_comparable(codigo_despacho)
        == CODIGO_EXPRESO_COMPARABLE
    )


def obtener_configuracion_zona(
    codigo_despacho
) -> dict:

    codigo_recibido = normalizar_codigo(
        codigo_despacho
    )

    configuracion = ZONAS_PLANIFICACION.get(
        codigo_recibido
    )

    codigo_configurado = codigo_recibido

    if configuracion is None:

        configuracion = INDICE_ZONAS_NORMALIZADO.get(
            codigo_comparable(codigo_recibido)
        )

        if configuracion is not None:
            codigo_configurado = configuracion[
                "codigo_original"
            ]

    if configuracion is None:

        return {
            "CodigoDespachoNormalizado": codigo_recibido,
            "CodigoDespachoConfigurado": "",
            "ZonaDescripcion": "",
            "GrupoDespacho": "",
            "PlanificacionConfigurada": "",
            "ZonaConfigurada": False,
            "EsExpreso": es_codigo_expreso(
                codigo_recibido
            ),
        }

    return {
        "CodigoDespachoNormalizado": codigo_recibido,
        "CodigoDespachoConfigurado": codigo_configurado,
        "ZonaDescripcion": configuracion.get(
            "descripcion",
            ""
        ),
        "GrupoDespacho": str(
            configuracion.get(
                "grupo",
                ""
            )
        ).strip(),
        "PlanificacionConfigurada": str(
            configuracion.get(
                "planificacion",
                ""
            )
        ).strip(),
        "ZonaConfigurada": True,
        "EsExpreso": es_codigo_expreso(
            codigo_recibido
        ),
    }


def obtener_prioridad_cliente(
    codigo_cliente
) -> dict:

    codigo = normalizar_codigo(
        codigo_cliente
    ).upper()

    configuracion = CLIENTES_PRIORITARIOS.get(
        codigo
    )

    if configuracion is None:

        return {
            "EsPrioritario": False,
            "PrioridadConfigurada": PRIORIDAD_GENERAL,
            "TipoEntregaPrioridad": "",
            "ResponsablePrioridad": "",
        }

    return {
        "EsPrioritario": True,
        "PrioridadConfigurada": int(
            configuracion.get(
                "prioridad",
                PRIORIDAD_GENERAL
            )
        ),
        "TipoEntregaPrioridad": configuracion.get(
            "tipo_entrega",
            ""
        ),
        "ResponsablePrioridad": configuracion.get(
            "responsable",
            ""
        ),
    }


# ==========================================================
# ENRIQUECER PEDIDOS PARA PLANIFICACIÓN
# ==========================================================

def enriquecer_pedidos_planificacion(
    df_pedidos: pd.DataFrame
) -> pd.DataFrame:

    tabla = df_pedidos.copy()

    if tabla.empty:

        columnas_salida_vacia = [
            "CodigoDespachoNormalizado",
            "CodigoDespachoConfigurado",
            "ZonaDescripcion",
            "GrupoDespacho",
            "PlanificacionConfigurada",
            "ZonaConfigurada",
            "EsExpreso",
            "ZonaExpreso",
            "ZonaExpresoConfigurada",
            "DiaEntregaConfigurado",
            "CoincidePlanificacion",
            "ClaveAgrupacion",
            "EsPrioritario",
            "PrioridadConfigurada",
            "TipoEntregaPrioridad",
            "ResponsablePrioridad",
        ]

        for columna in columnas_salida_vacia:

            if columna not in tabla.columns:

                if columna in {
                    "ZonaConfigurada",
                    "EsExpreso",
                    "ZonaExpresoConfigurada",
                    "CoincidePlanificacion",
                    "EsPrioritario",
                }:
                    tabla[columna] = pd.Series(
                        dtype="bool"
                    )

                elif columna == "PrioridadConfigurada":
                    tabla[columna] = pd.Series(
                        dtype="int64"
                    )

                else:
                    tabla[columna] = pd.Series(
                        dtype="object"
                    )

        return tabla

    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Planificacion",
        "CodigoDespacho",
    ]

    for columna in columnas_texto:

        tabla[columna] = (
            tabla[columna]
            .apply(normalizar_codigo)
        )

    tabla["ClienteCodigo"] = (
        tabla["ClienteCodigo"]
        .str.upper()
    )

    tabla["Planificacion"] = (
        tabla["Planificacion"]
        .str.upper()
    )

    columnas_configuracion_zona = [
        "CodigoDespachoNormalizado",
        "CodigoDespachoConfigurado",
        "ZonaDescripcion",
        "GrupoDespacho",
        "PlanificacionConfigurada",
        "ZonaConfigurada",
        "EsExpreso",
    ]

    if tabla.empty:

        configuracion_zonas = pd.DataFrame(
            columns=columnas_configuracion_zona,
            index=tabla.index,
        )

    else:

        configuracion_zonas = (
            tabla["CodigoDespacho"]
            .apply(obtener_configuracion_zona)
            .apply(pd.Series)
            .reindex(
                columns=columnas_configuracion_zona
            )
        )

    tabla = pd.concat(
        [
            tabla.reset_index(drop=True),
            configuracion_zonas.reset_index(drop=True),
        ],
        axis=1
    )

    tabla["EsExpreso"] = (
        tabla["EsExpreso"]
        .fillna(False)
        .astype(bool)
    )

    tabla["ZonaConfigurada"] = (
        tabla["ZonaConfigurada"]
        .fillna(False)
        .astype(bool)
    )

    # ------------------------------------------------------
    # EXPRESOS
    #
    # REGLA PRINCIPAL:
    # - Planificacion ya contiene el día de entrega del cliente.
    # - ZonaExpreso / ZonaAgrupadorExpreso determina el grupo.
    # - La configuración nunca reemplaza un día informado.
    #
    # Ejemplo:
    # Planificacion = JUEVES
    # ZonaExpreso = CABA SUR II
    # Resultado = JUEVES | Grupo 1
    # ------------------------------------------------------

    # ------------------------------------------------------
    # CLASIFICACIÓN DEFINITIVA DE EXPRESOS
    # ------------------------------------------------------
    #
    # No alcanza con mirar el código de despacho.
    # Algunos clientes tienen el código genérico de expreso,
    # pero poseen un día semanal de entrega.
    #
    # Esos pedidos deben entrar en la planificación normal:
    # LUNES, MARTES, MIÉRCOLES, JUEVES o VIERNES.
    # ------------------------------------------------------

    planificacion_original = (
        tabla["Planificacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    dia_entrega_semanal = (
        planificacion_original
        .apply(extraer_dia_entrega)
    )

    grupo_entrega_semanal = (
        planificacion_original
        .apply(extraer_grupo_entrega)
    )

    mascara_codigo_expreso = (
        tabla["EsExpreso"]
        .fillna(False)
        .astype(bool)
    )

    mascara_entrega_semanal = (
        dia_entrega_semanal.ne("")
    )

    mascara_expresos_semanales = (
        mascara_codigo_expreso
        & mascara_entrega_semanal
    )

    # Continúan como expresos solamente aquellos pedidos
    # cuyo código es expreso y no poseen día semanal.
    mascara_expresos = (
        mascara_codigo_expreso
        & ~mascara_entrega_semanal
    )

    tabla["EsExpreso"] = mascara_expresos

    # ------------------------------------------------------
    # INTEGRACIÓN REAL A LA PLANIFICACIÓN SEMANAL
    # ------------------------------------------------------
    #
    # Ejemplo:
    # 4 - Jueves | Grupo 1
    #
    # se convierte en:
    # Planificacion = JUEVES
    # GrupoDespacho = 1
    # EsExpreso = False
    # ------------------------------------------------------

    tabla.loc[
        mascara_expresos_semanales,
        "Planificacion"
    ] = dia_entrega_semanal.loc[
        mascara_expresos_semanales
    ]

    tabla.loc[
        mascara_expresos_semanales,
        "PlanificacionConfigurada"
    ] = dia_entrega_semanal.loc[
        mascara_expresos_semanales
    ]

    tabla.loc[
        mascara_expresos_semanales,
        "GrupoDespacho"
    ] = grupo_entrega_semanal.loc[
        mascara_expresos_semanales
    ]

    tabla.loc[
        mascara_expresos_semanales,
        "ZonaConfigurada"
    ] = True

    tabla.loc[
        mascara_expresos_semanales,
        "ZonaDescripcion"
    ] = (
        "ENTREGA SEMANAL "
        + dia_entrega_semanal.loc[
            mascara_expresos_semanales
        ]
    )

    if "ZonaExpreso" in tabla.columns:

        zona_expreso = (
            tabla["ZonaExpreso"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    elif "ZonaAgrupadorExpreso" in tabla.columns:

        zona_expreso = (
            tabla["ZonaAgrupadorExpreso"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    else:

        zona_expreso = pd.Series(
            "",
            index=tabla.index,
            dtype="object",
        )

    columnas_configuracion_expreso = [
        "ZonaExpresoNormalizada",
        "PlanificacionExpreso",
        "GrupoExpreso",
        "CodigosDespachoExpreso",
        "ZonaExpresoConfigurada",
    ]

    if tabla.empty:

        configuracion_expresos = pd.DataFrame(
            columns=columnas_configuracion_expreso,
            index=tabla.index,
        )

    else:

        configuracion_expresos = (
            zona_expreso
            .apply(obtener_planificacion_expreso)
            .apply(pd.Series)
            .reindex(
                columns=columnas_configuracion_expreso
            )
        )

    tabla["ZonaExpreso"] = (
        configuracion_expresos[
            "ZonaExpresoNormalizada"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla["ZonaExpresoConfigurada"] = (
        configuracion_expresos[
            "ZonaExpresoConfigurada"
        ]
        .fillna(False)
        .astype(bool)
    )

    mascara_expresos_configurados = (
        mascara_expresos
        & tabla["ZonaExpresoConfigurada"]
    )

    # El grupo sí proviene de la zona configurada.
    tabla.loc[
        mascara_expresos_configurados,
        "GrupoDespacho"
    ] = configuracion_expresos.loc[
        mascara_expresos_configurados,
        "GrupoExpreso"
    ].values

    tabla.loc[
        mascara_expresos_configurados,
        "ZonaDescripcion"
    ] = tabla.loc[
        mascara_expresos_configurados,
        "ZonaExpreso"
    ]

    # Planificacion conserva la agrupación operativa:
    # CABA SUR, CABA SUR II, CABA NORTE, etc.
    #
    # El día configurado se guarda por separado para control,
    # pero nunca reemplaza el nombre de la zona.
    tabla["DiaEntregaConfigurado"] = ""

    tabla.loc[
        mascara_expresos_configurados,
        "DiaEntregaConfigurado"
    ] = configuracion_expresos.loc[
        mascara_expresos_configurados,
        "PlanificacionExpreso"
    ].values

    # Para validar los expresos, la planificación configurada
    # coincide con la propia agrupación operativa.
    tabla.loc[
        mascara_expresos,
        "PlanificacionConfigurada"
    ] = tabla.loc[
        mascara_expresos,
        "Planificacion"
    ]

    tabla.loc[
        mascara_expresos,
        "ZonaConfigurada"
    ] = True

    # Las zonas todavía no configuradas no se eliminan.
    # Quedan identificadas para poder agregarlas después.
    mascara_expresos_sin_config = (
        mascara_expresos
        & ~tabla["ZonaExpresoConfigurada"]
    )

    tabla.loc[
        mascara_expresos_sin_config,
        "ZonaDescripcion"
    ] = zona_expreso.loc[
        mascara_expresos_sin_config
    ]

    tabla.loc[
        mascara_expresos_sin_config,
        "GrupoDespacho"
    ] = "EXPRESO SIN CONFIG"

    tabla["CoincidePlanificacion"] = (
        tabla["Planificacion"].eq(
            tabla["PlanificacionConfigurada"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
    )

    planificacion_texto = (
        tabla["Planificacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    grupo_despacho_texto = (
        tabla["GrupoDespacho"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["ClaveAgrupacion"] = (
        planificacion_texto
        + " | Grupo "
        + grupo_despacho_texto
    )

    prioridades = (
        tabla["ClienteCodigo"]
        .apply(obtener_prioridad_cliente)
        .apply(pd.Series)
    )

    tabla = pd.concat(
        [
            tabla.reset_index(drop=True),
            prioridades.reset_index(drop=True),
        ],
        axis=1
    )

    return tabla


# ==========================================================
# CONSTRUIR RESUMEN DE CLIENTES
# ==========================================================

def construir_resumen_clientes_planificacion(
    df_pedidos: pd.DataFrame
) -> pd.DataFrame:

    columnas_requeridas = [
        "Pedido",
        "Fecha",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Planificacion",
        "CodigoDespacho",
        "TotalUnidades",
        "TotalM3",
    ]

    columnas_faltantes = [
        columna
        for columna in columnas_requeridas
        if columna not in df_pedidos.columns
    ]

    if columnas_faltantes:

        raise ValueError(
            "Faltan columnas para construir la planificación: "
            f"{columnas_faltantes}"
        )

    tabla = enriquecer_pedidos_planificacion(
        df_pedidos
    )

    tabla["Fecha"] = pd.to_datetime(
        tabla["Fecha"],
        errors="coerce"
    )

    tabla["TotalUnidades"] = (
        pd.to_numeric(
            tabla["TotalUnidades"],
            errors="coerce"
        )
        .fillna(0)
    )

    tabla["TotalM3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce"
        )
        .fillna(0)
    )

    tabla = tabla.drop_duplicates(
        subset=["Pedido"],
        keep="first"
    )

    tabla = tabla[
        tabla["Pedido"].ne("")
        & tabla["ClienteCodigo"].ne("")
        & tabla["Planificacion"].ne("")
        & tabla["Fecha"].notna()
        & tabla["ZonaConfigurada"]
        & tabla["GrupoDespacho"].notna()
        & ~tabla["GrupoDespacho"].isin(
            GRUPOS_EXCLUIDOS
        )
    ].copy()

    if tabla.empty:
        return pd.DataFrame()

    resumen = (
        tabla
        .groupby(
            [
                "Planificacion",
                "GrupoDespacho",
                "ClaveAgrupacion",
                "ClienteCodigo",
                "ClienteDescripcion",
                "EsPrioritario",
                "PrioridadConfigurada",
                "EsExpreso",
            ],
            as_index=False
        )
        .agg(
            FechaPrioridad=("Fecha", "min"),
            CantidadPedidos=("Pedido", "nunique"),
            Pedidos=(
                "Pedido",
                lambda serie: " | ".join(
                    sorted(
                        serie.astype(str).unique()
                    )
                )
            ),
            CodigosDespacho=(
                "CodigoDespacho",
                lambda serie: " | ".join(
                    sorted(
                        serie.astype(str).unique()
                    )
                )
            ),
            Zonas=(
                "ZonaDescripcion",
                lambda serie: " | ".join(
                    sorted(
                        {
                            zona
                            for zona in serie.astype(str)
                            if zona.strip()
                        }
                    )
                )
            ),
            TotalUnidades=("TotalUnidades", "sum"),
            TotalM3=("TotalM3", "sum"),
        )
    )

    hoy = pd.Timestamp.today().normalize()

    resumen["DiasPendiente"] = (
        hoy
        - resumen["FechaPrioridad"].dt.normalize()
    ).dt.days

    resumen["TotalUnidades"] = (
        resumen["TotalUnidades"]
        .fillna(0)
        .astype(int)
    )

    resumen["TotalM3"] = (
        resumen["TotalM3"]
        .fillna(0)
        .round(3)
    )

    # Los clientes prioritarios conservan su prioridad.
    # A igualdad de prioridad, se toma primero el más antiguo.
    resumen = resumen.sort_values(
        by=[
            "Planificacion",
            "GrupoDespacho",
            "EsPrioritario",
            "PrioridadConfigurada",
            "FechaPrioridad",
            "TotalM3",
        ],
        ascending=[
            True,
            True,
            False,
            True,
            True,
            False,
        ]
    ).reset_index(drop=True)

    resumen["PrioridadCliente"] = (
        resumen
        .groupby(
            [
                "Planificacion",
                "GrupoDespacho",
            ]
        )
        .cumcount()
        + 1
    )

    return resumen


# ==========================================================
# ASIGNACIÓN BEST FIT
# ==========================================================

def _buscar_mejor_vehiculo(
    vehiculos: list,
    volumen_cliente: float,
    capacidad_m3: float,
    grupos_permitidos: set | None = None
):

    candidatos = []

    for vehiculo in vehiculos:

        if grupos_permitidos is not None:
            if vehiculo["GrupoVehiculo"] not in grupos_permitidos:
                continue

        nuevo_volumen = (
            vehiculo["VolumenAcumuladoM3"]
            + volumen_cliente
        )

        if nuevo_volumen <= capacidad_m3:

            espacio_restante = (
                capacidad_m3
                - nuevo_volumen
            )

            candidatos.append(
                (
                    espacio_restante,
                    vehiculo["NumeroCamioneta"],
                    vehiculo,
                )
            )

    if not candidatos:
        return None

    candidatos.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    return candidatos[0][2]


def _crear_vehiculo(
    numero_camioneta: int,
    grupo_vehiculo: str,
) -> dict:

    return {
        "NumeroCamioneta": numero_camioneta,
        "GrupoVehiculo": grupo_vehiculo,
        "VolumenAcumuladoM3": 0.0,
    }


def asignar_camionetas(
    resumen_clientes: pd.DataFrame,
    capacidad_m3: float
) -> pd.DataFrame:

    if capacidad_m3 <= 0:

        raise ValueError(
            "La capacidad de la camioneta debe ser mayor que cero."
        )

    if resumen_clientes.empty:
        return resumen_clientes.copy()

    tabla = resumen_clientes.copy()
    asignaciones = []

    for planificacion, bloque in tabla.groupby(
        "Planificacion",
        sort=False
    ):

        vehiculos = []
        siguiente_numero = 1

        clientes_zona = bloque[
            ~bloque["EsExpreso"]
        ].copy()

        clientes_expresos = bloque[
            bloque["EsExpreso"]
        ].copy()

        # --------------------------------------------------
        # 1. CLIENTES DE ZONA
        # Cada grupo zonal se mantiene separado.
        # El best fit busca espacios en todas las camionetas
        # abiertas de ese mismo grupo.
        # --------------------------------------------------

        for grupo_despacho, grupo in clientes_zona.groupby(
            "GrupoDespacho",
            sort=False
        ):

            grupo = grupo.sort_values(
                by=[
                    "EsPrioritario",
                    "PrioridadConfigurada",
                    "FechaPrioridad",
                    "TotalM3",
                ],
                ascending=[
                    False,
                    True,
                    True,
                    False,
                ]
            )

            for _, fila in grupo.iterrows():

                volumen_cliente = float(
                    fila["TotalM3"]
                )

                cliente_excedido = (
                    volumen_cliente > capacidad_m3
                )

                vehiculo = None

                if not cliente_excedido:

                    vehiculo = _buscar_mejor_vehiculo(
                        vehiculos=vehiculos,
                        volumen_cliente=volumen_cliente,
                        capacidad_m3=capacidad_m3,
                        grupos_permitidos={
                            str(grupo_despacho)
                        },
                    )

                if vehiculo is None:

                    vehiculo = _crear_vehiculo(
                        numero_camioneta=siguiente_numero,
                        grupo_vehiculo=str(
                            grupo_despacho
                        ),
                    )

                    vehiculos.append(vehiculo)
                    siguiente_numero += 1

                vehiculo["VolumenAcumuladoM3"] += (
                    volumen_cliente
                )

                asignacion = fila.to_dict()

                asignacion.update({
                    "NumeroCamioneta": vehiculo[
                        "NumeroCamioneta"
                    ],
                    "GrupoVehiculo": vehiculo[
                        "GrupoVehiculo"
                    ],
                    "Camioneta": (
                        f"{planificacion} - "
                        f"Camioneta "
                        f"{vehiculo['NumeroCamioneta']}"
                    ),
                    "CapacidadM3": capacidad_m3,
                    "VolumenClienteM3": volumen_cliente,
                    "ClienteExcedeCapacidad": (
                        cliente_excedido
                    ),
                    "OcupacionClientePct": round(
                        volumen_cliente
                        / capacidad_m3
                        * 100,
                        1
                    ),
                })

                asignaciones.append(asignacion)

        # --------------------------------------------------
        # 2. CLIENTES EXPRESOS
        #
        # El expreso ya viene asociado a esta Planificacion.
        # Se prueba contra TODAS las camionetas zonales de esa
        # planificación, sin mezclar planificaciones distintas.
        # Así completa huecos de grupos zonales existentes.
        # --------------------------------------------------

        clientes_expresos = clientes_expresos.sort_values(
            by=[
                "EsPrioritario",
                "PrioridadConfigurada",
                "FechaPrioridad",
                "TotalM3",
            ],
            ascending=[
                False,
                True,
                True,
                False,
            ]
        )

        for _, fila in clientes_expresos.iterrows():

            volumen_cliente = float(
                fila["TotalM3"]
            )

            cliente_excedido = (
                volumen_cliente > capacidad_m3
            )

            vehiculo = None

            if not cliente_excedido:

                vehiculo = _buscar_mejor_vehiculo(
                    vehiculos=vehiculos,
                    volumen_cliente=volumen_cliente,
                    capacidad_m3=capacidad_m3,
                    grupos_permitidos={
                        str(fila["GrupoDespacho"])
                    },
                )

            if vehiculo is None:

                vehiculo = _crear_vehiculo(
                    numero_camioneta=siguiente_numero,
                    grupo_vehiculo=str(
                        fila["GrupoDespacho"]
                    ),
                )

                vehiculos.append(vehiculo)
                siguiente_numero += 1

            vehiculo["VolumenAcumuladoM3"] += (
                volumen_cliente
            )

            asignacion = fila.to_dict()

            asignacion.update({
                "NumeroCamioneta": vehiculo[
                    "NumeroCamioneta"
                ],
                "GrupoVehiculo": vehiculo[
                    "GrupoVehiculo"
                ],
                "Camioneta": (
                    f"{planificacion} - "
                    f"Camioneta "
                    f"{vehiculo['NumeroCamioneta']}"
                ),
                "CapacidadM3": capacidad_m3,
                "VolumenClienteM3": volumen_cliente,
                "ClienteExcedeCapacidad": (
                    cliente_excedido
                ),
                "OcupacionClientePct": round(
                    volumen_cliente
                    / capacidad_m3
                    * 100,
                    1
                ),
            })

            asignaciones.append(asignacion)

    resultado = pd.DataFrame(asignaciones)

    if resultado.empty:
        return resultado

    resumen_vehiculos = (
        resultado
        .groupby(
            [
                "Planificacion",
                "NumeroCamioneta",
                "GrupoVehiculo",
            ],
            as_index=False
        )
        .agg(
            VolumenCamionetaM3=(
                "VolumenClienteM3",
                "sum"
            ),
            ClientesCamioneta=(
                "ClienteCodigo",
                "nunique"
            ),
            PedidosCamioneta=(
                "CantidadPedidos",
                "sum"
            ),
            UnidadesCamioneta=(
                "TotalUnidades",
                "sum"
            ),
        )
    )

    resumen_vehiculos["CapacidadM3"] = capacidad_m3

    resumen_vehiculos["OcupacionCamionetaPct"] = (
        resumen_vehiculos["VolumenCamionetaM3"]
        / capacidad_m3
        * 100
    ).round(1)

    resumen_vehiculos["DisponibleM3"] = (
        capacidad_m3
        - resumen_vehiculos["VolumenCamionetaM3"]
    ).round(3)

    resumen_vehiculos["EstadoCapacidad"] = (
        resumen_vehiculos["VolumenCamionetaM3"]
        .apply(
            lambda volumen:
            "🔴 Excedida"
            if volumen > capacidad_m3
            else (
                "🟢 Completa"
                if volumen >= capacidad_m3 * 0.90
                else (
                    "🟡 Media"
                    if volumen >= capacidad_m3 * 0.60
                    else "⚪ Baja"
                )
            )
        )
    )

    resultado = resultado.merge(
        resumen_vehiculos,
        on=[
            "Planificacion",
            "NumeroCamioneta",
            "GrupoVehiculo",
        ],
        how="left",
        validate="many_to_one",
        suffixes=("", "_Resumen"),
    )

    # El merge anterior conserva CapacidadM3 de la asignación.
    if "CapacidadM3_Resumen" in resultado.columns:
        resultado = resultado.drop(
            columns=["CapacidadM3_Resumen"]
        )

    resultado = resultado.sort_values(
        by=[
            "Planificacion",
            "NumeroCamioneta",
            "EsPrioritario",
            "PrioridadConfigurada",
            "FechaPrioridad",
        ],
        ascending=[
            True,
            True,
            False,
            True,
            True,
        ]
    ).reset_index(drop=True)

    return resultado


# ==========================================================
# DEVOLVER ASIGNACIÓN A CADA PEDIDO
# ==========================================================

def asignar_camioneta_a_pedidos(
    df_pedidos: pd.DataFrame,
    asignacion_clientes: pd.DataFrame
) -> pd.DataFrame:

    tabla = df_pedidos.copy()

    if asignacion_clientes.empty:

        tabla["CamionetaPropuesta"] = ""
        tabla["NumeroCamioneta"] = pd.NA

        return tabla

    tabla_enriquecida = enriquecer_pedidos_planificacion(
        tabla
    )

    asignacion_merge = (
        asignacion_clientes[
            [
                "Planificacion",
                "GrupoDespacho",
                "ClienteCodigo",
                "Camioneta",
                "NumeroCamioneta",
                "GrupoVehiculo",
                "VolumenCamionetaM3",
                "OcupacionCamionetaPct",
                "EstadoCapacidad",
            ]
        ]
        .drop_duplicates(
            subset=[
                "Planificacion",
                "GrupoDespacho",
                "ClienteCodigo",
            ],
            keep="first"
        )
        .rename(
            columns={
                "Camioneta": "CamionetaPropuesta"
            }
        )
    )

    tabla_enriquecida = tabla_enriquecida.merge(
        asignacion_merge,
        on=[
            "Planificacion",
            "GrupoDespacho",
            "ClienteCodigo",
        ],
        how="left",
        validate="many_to_one"
    )

    tabla_enriquecida["CamionetaPropuesta"] = (
        tabla_enriquecida["CamionetaPropuesta"]
        .fillna("")
    )

    return tabla_enriquecida