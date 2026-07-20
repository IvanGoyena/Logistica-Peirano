import pandas as pd


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

    tabla = df_pedidos.copy()

    # ------------------------------------------------------
    # NORMALIZAR CAMPOS
    # ------------------------------------------------------

    tabla["Pedido"] = (
        tabla["Pedido"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["ClienteCodigo"] = (
        tabla["ClienteCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["ClienteDescripcion"] = (
        tabla["ClienteDescripcion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["Planificacion"] = (
        tabla["Planificacion"]
        .fillna("")
        .astype(str)
        .str.strip()
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

    # ------------------------------------------------------
    # SOLO PEDIDOS PLANIFICABLES
    # ------------------------------------------------------

    tabla = tabla[
        tabla["Pedido"].ne("")
        & tabla["ClienteCodigo"].ne("")
        & tabla["Planificacion"].ne("")
        & tabla["Fecha"].notna()
    ].copy()

    if tabla.empty:

        return pd.DataFrame(
            columns=[
                "Planificacion",
                "ClienteCodigo",
                "ClienteDescripcion",
                "FechaPrioridad",
                "CantidadPedidos",
                "Pedidos",
                "TotalUnidades",
                "TotalM3",
                "DiasPendiente",
            ]
        )

    # Evitar duplicar pedidos
    tabla = tabla.drop_duplicates(
        subset=["Pedido"],
        keep="first"
    )

    # ------------------------------------------------------
    # AGRUPAR CLIENTES COMPLETOS
    # ------------------------------------------------------

    resumen = (
        tabla
        .groupby(
            [
                "Planificacion",
                "ClienteCodigo",
                "ClienteDescripcion",
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
            TotalUnidades=("TotalUnidades", "sum"),
            TotalM3=("TotalM3", "sum"),
        )
    )

    hoy = pd.Timestamp.today().normalize()

    resumen["DiasPendiente"] = (
        hoy - resumen["FechaPrioridad"].dt.normalize()
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

    # ------------------------------------------------------
    # PRIORIDAD
    # Primero la planificación y luego el cliente más viejo
    # ------------------------------------------------------

    resumen = resumen.sort_values(
        by=[
            "Planificacion",
            "FechaPrioridad",
            "TotalM3",
        ],
        ascending=[
            True,
            True,
            False,
        ]
    ).reset_index(drop=True)

    resumen["PrioridadCliente"] = (
        resumen
        .groupby("Planificacion")
        .cumcount()
        + 1
    )

    return resumen


# ==========================================================
# ASIGNAR CAMIONETAS
# ==========================================================

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

    for planificacion, grupo in tabla.groupby(
        "Planificacion",
        sort=False
    ):

        grupo = grupo.sort_values(
            by=[
                "FechaPrioridad",
                "TotalM3",
            ],
            ascending=[
                True,
                False,
            ]
        )

        numero_camioneta = 1
        volumen_acumulado = 0.0

        for _, fila in grupo.iterrows():

            volumen_cliente = float(
                fila["TotalM3"]
            )

            cliente_excedido = (
                volumen_cliente > capacidad_m3
            )

            # --------------------------------------------------
            # CLIENTE QUE SUPERA SOLO LA CAPACIDAD
            # Se mantiene completo en una camioneta exclusiva
            # --------------------------------------------------

            if cliente_excedido:

                if volumen_acumulado > 0:

                    numero_camioneta += 1
                    volumen_acumulado = 0.0

                volumen_acumulado = volumen_cliente

                numero_asignado = numero_camioneta

                numero_camioneta += 1
                volumen_acumulado = 0.0

            else:

                # ----------------------------------------------
                # EL CLIENTE NO ENTRA EN LA CAMIONETA ACTUAL
                # ----------------------------------------------

                if (
                    volumen_acumulado > 0
                    and volumen_acumulado + volumen_cliente
                    > capacidad_m3
                ):

                    numero_camioneta += 1
                    volumen_acumulado = 0.0

                volumen_acumulado += volumen_cliente
                numero_asignado = numero_camioneta

            porcentaje_ocupacion = (
                volumen_cliente / capacidad_m3 * 100
            )

            asignacion = fila.to_dict()

            asignacion.update({
                "NumeroCamioneta": numero_asignado,
                "Camioneta": (
                    f"{planificacion} - "
                    f"Camioneta {numero_asignado}"
                ),
                "CapacidadM3": capacidad_m3,
                "VolumenClienteM3": volumen_cliente,
                "ClienteExcedeCapacidad": cliente_excedido,
                "OcupacionClientePct": round(
                    porcentaje_ocupacion,
                    1
                ),
            })

            asignaciones.append(asignacion)

    resultado = pd.DataFrame(asignaciones)

    # ------------------------------------------------------
    # VOLUMEN TOTAL DE CADA CAMIONETA
    # ------------------------------------------------------

    volumen_camioneta = (
        resultado
        .groupby(
            [
                "Planificacion",
                "NumeroCamioneta",
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

    volumen_camioneta["OcupacionCamionetaPct"] = (
        volumen_camioneta["VolumenCamionetaM3"]
        / capacidad_m3
        * 100
    ).round(1)

    volumen_camioneta["DisponibleM3"] = (
        capacidad_m3
        - volumen_camioneta["VolumenCamionetaM3"]
    ).round(3)

    volumen_camioneta["EstadoCapacidad"] = (
        volumen_camioneta["VolumenCamionetaM3"]
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
        volumen_camioneta,
        on=[
            "Planificacion",
            "NumeroCamioneta",
        ],
        how="left",
        validate="many_to_one"
    )

    resultado = resultado.sort_values(
        by=[
            "Planificacion",
            "NumeroCamioneta",
            "FechaPrioridad",
        ]
    ).reset_index(drop=True)

    return resultado


# ==========================================================
# DEVOLVER CAMIONETA A CADA PEDIDO
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

    asignacion_merge = (
        asignacion_clientes[
            [
                "Planificacion",
                "ClienteCodigo",
                "Camioneta",
                "NumeroCamioneta",
                "VolumenCamionetaM3",
                "OcupacionCamionetaPct",
                "EstadoCapacidad",
            ]
        ]
        .drop_duplicates(
            subset=[
                "Planificacion",
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

    tabla = tabla.merge(
        asignacion_merge,
        on=[
            "Planificacion",
            "ClienteCodigo",
        ],
        how="left",
        validate="many_to_one"
    )

    tabla["CamionetaPropuesta"] = (
        tabla["CamionetaPropuesta"]
        .fillna("")
    )

    return tabla