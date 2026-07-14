import pandas as pd


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

DIAS_TABLERO = 2

# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def construir_tabla_tareas(
    df_tareas,
    df_pedidos,
    df_clientes
):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_tareas.copy()

    # ------------------------------------------------------
    # SOLO TAREAS DE PREPARACIÓN
    # ------------------------------------------------------

    tabla = tabla[
        tabla["TareaTipo"]
        .fillna("")
        .str.upper()
        .str.contains("PREPARACION")
    ].copy()

    # ------------------------------------------------------
    # PEDIDOS
    # ------------------------------------------------------

    pedidos = df_pedidos[
    [
        "PreparacionID",
        "ClienteCodigo",
        "ClienteDescripcion",
        "PreparacionEstado",
        "TipoPreparacion",
        "Estado",
        "Fecha",
        "TotalUnidades",
        "TotalSKUs",
        "DetalleFamilias"
    ]
].copy()

    tabla = tabla.merge(

        pedidos,

        left_on="PreparacionId",
        right_on="PreparacionID",

        how="left"

    )

    # ------------------------------------------------------
    # CLIENTES
    # ------------------------------------------------------

    clientes = df_clientes[
        [
            "Codigo_Cliente",
            "Zona",
            "Provincia",
            "Localidad",
            "Distrito",
            "Entrega"
        ]
    ].copy()

    tabla = tabla.merge(

        clientes,

        left_on="ClienteCodigo",
        right_on="Codigo_Cliente",

        how="left"

    )

    # ------------------------------------------------------
    # USUARIO
    # ------------------------------------------------------

    tabla["Usuario"] = (

        tabla["UsuarioNombre"].fillna("")

        + " "

        + tabla["UsuarioApellido"].fillna("")

    ).str.strip()

    # ------------------------------------------------------
    # FECHA Y HORA
    # ------------------------------------------------------

    tabla["FechaHora"] = (
        pd.to_datetime(
            tabla["FechaHoraEstado"],
            errors="coerce"
        )
        - pd.Timedelta(hours=3)
    )

    # ------------------------------------------------------
    # CATEGORÍA OPERATIVA
    # ------------------------------------------------------

    tabla["Categoria"] = "Pendiente"

    contenedor = (
        tabla["ContenedorNumero"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # En Curso
    tabla.loc[
        contenedor.str.contains("CARRO", na=False),
        "Categoria"
    ] = "En Curso"

    # Finalizado
    tabla.loc[
        (
            (contenedor != "")
            &
            (~contenedor.str.contains("CARRO", na=False))
            &
            (
                tabla["TareaEstado"]
                .fillna("")
                .str.upper()
                .eq("FINALIZADA")
            )
        ),
        "Categoria"
    ] = "Finalizado"
    
    
    # ------------------------------------------------------
    # SEMÁFORO OPERATIVO
    # ------------------------------------------------------

    tabla["Semaforo"] = "🟡"

    # Carro cerrado pero todavía abierto en la operación
    tabla.loc[
        (tabla["Categoria"] == "En Curso")
        &
        (
            tabla["Estado"]
            .fillna("")
            .str.upper()
            == "FINALIZADA"
        ),
        "Semaforo"
    ] = "🔴"

    # Carro en proceso
    tabla.loc[
        (tabla["Categoria"] == "En Curso")
        &
        (
            tabla["Estado"]
            .fillna("")
            .str.upper()
            != "FINALIZADA"
        ),
        "Semaforo"
    ] = "🟠"

    # Carro completamente cerrado
    tabla.loc[
        tabla["Categoria"] == "Finalizado",
        "Semaforo"
    ] = "🟢"   

    # ------------------------------------------------------
    # ORDEN DE PRIORIDAD
    # ------------------------------------------------------

    tabla["Orden"] = 4

    # 🔴 Resolver
    tabla.loc[
        (tabla["Categoria"] == "En Curso")
        &
        (
            tabla["Estado"]
            .fillna("")
            .str.upper()
            == "FINALIZADA"
        ),
        "Orden"
    ] = 1

    # 🟠 Trabajando
    tabla.loc[
        (tabla["Categoria"] == "En Curso")
        &
        (
            tabla["Estado"]
            .fillna("")
            .str.upper()
            != "FINALIZADA"
        ),
        "Orden"
    ] = 2

    # 🟡 Pendiente
    tabla.loc[
        tabla["Categoria"] == "Pendiente",
        "Orden"
    ] = 3

    # 🟢 Finalizado
    tabla.loc[
        tabla["Categoria"] == "Finalizado",
        "Orden"
    ] = 4

    # ------------------------------------------------------
    # ICONO VISUAL DEL CARRO
    # ------------------------------------------------------

    # 🔴 Prioridad Alta
    tabla.loc[
        tabla["Semaforo"] == "🔴",
        "ContenedorNumero"
    ] = (
        "🚨 "
        + tabla.loc[
            tabla["Semaforo"] == "🔴",
            "ContenedorNumero"
        ].astype(str)
    )

    # 🟠 En Trabajo
    tabla.loc[
        tabla["Semaforo"] == "🟠",
        "ContenedorNumero"
    ] = (
        "🚧 "
        + tabla.loc[
            tabla["Semaforo"] == "🟠",
            "ContenedorNumero"
        ].astype(str)
    )

    # ------------------------------------------------------
    # HORA (SOLO PARA MOSTRAR)
    # ------------------------------------------------------

    tabla["Hora"] = tabla["FechaHora"].dt.strftime("%H:%M")
    

    # ------------------------------------------------------
    # TABLA FINAL
    # ------------------------------------------------------

    tabla = tabla[
    [

        "Semaforo",
        "Orden",
        "Categoria",
        "FechaHora",
        "TareaEstado",
        "PreparacionId",
        "ClienteDescripcion",
        "AreaDescripcion",
        "DespachoDescripcion",
        "Hora",
        "ContenedorNumero",
        "Usuario",
        "PreparacionEstado",
        "TipoPreparacion",
        "Estado",
        "TotalUnidades",
        "TotalSKUs",
        "DetalleFamilias",

    ]
].copy()

    tabla.columns = [

    "Prioridad",
    "Orden",
    "Categoria",
    "FechaHora",
    "Estado",
    "Preparacion",
    "Cliente",
    "Area",
    "Despacho",
    "Hora",
    "Carro",
    "Usuario",
    "EstadoPreparacion",
    "TipoPreparacion",
    "EstadoPedido",
    "Unidades",
    "SKUs",
    "Familias"

]
    return tabla

# ==========================================================
# KPIs
# ==========================================================

def obtener_resumen_operativo(
    tabla,
    df_pedidos
):

    resumen = {}

    # ------------------------------------------------------
    # DÍA OPERATIVO
    # ------------------------------------------------------

    fecha_operativa = tabla["FechaHora"].dt.normalize().max()
    fecha_inicio = fecha_operativa - pd.Timedelta(days=2)


    # ------------------------------------------------------
    # PEDIDOS PENDIENTES
    # ------------------------------------------------------

    resumen["PedidosPendientes"] = (

        df_pedidos[

            df_pedidos["Estado"]

            .fillna("")

            .str.upper()

            .isin(

                [

                    "PENDIENTE",
                    "PREPARACION"

                ]

            )

        ]["PedidoId"]

        .nunique()

    )

# ------------------------------------------------------
# CARROS EN CURSO
# ------------------------------------------------------

    resumen["CarrosEnCurso"] = (

    tabla[

        (tabla["Categoria"] == "En Curso")

        &

        (tabla["FechaHora"].dt.normalize() >= fecha_inicio)

    ]["Carro"]

    .nunique()

)

# ------------------------------------------------------
# CARROS FINALIZADOS
# ------------------------------------------------------

    hoy = (

        tabla[

        (tabla["Categoria"] == "Finalizado")

        &

        (tabla["FechaHora"].dt.normalize() == fecha_operativa)

    ]["Carro"]

    .nunique()

)

    ayer = (

    tabla[

        (tabla["Categoria"] == "Finalizado")

        &

        (tabla["FechaHora"].dt.normalize() == (fecha_operativa - pd.Timedelta(days=1)))

    ]["Carro"]

    .nunique()

)

    resumen["CarrosFinalizados"] = hoy + ayer

    resumen["CarrosFinalizadosHoy"] = hoy

    resumen["CarrosFinalizadosAyer"] = ayer

    return resumen
# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def obtener_tabla_operativa(tabla):

    operativa = tabla.copy()

    fecha_operativa = operativa["FechaHora"].dt.normalize().max()
    fecha_inicio = fecha_operativa - pd.Timedelta(days=DIAS_TABLERO - 1)
    operativa = operativa[

    operativa["FechaHora"].dt.normalize() >= fecha_inicio

].copy()

    operativa = operativa[

        operativa["TipoPreparacion"]
        .fillna("")
        .str.upper()
        == "PEDIDO"

    ].copy()

    categorias = [

        "Pendiente",

        "En Curso",

        "Finalizado"

    ]

    operativa["Categoria"] = pd.Categorical(

        operativa["Categoria"],

        categories=categorias,

        ordered=True

    )

    operativa = operativa.sort_values(

    [

        "Orden",

        "FechaHora"

    ],

    ascending=[True, True]

)

    operativa.reset_index(

        drop=True,

        inplace=True

    )
    operativa = operativa.drop(columns="Orden")
    
    return operativa


# ==========================================================
# AVANCE POR DESPACHO
# ==========================================================

def obtener_avance_despachos(tabla):

    # ---------------------------------------
    # FECHA OPERATIVA
    # ---------------------------------------

    fecha_operativa = tabla["FechaHora"].dt.normalize().max()

    fecha_inicio = fecha_operativa - pd.Timedelta(days=DIAS_TABLERO - 1)

    df = tabla[

    tabla["FechaHora"].dt.normalize() >= fecha_inicio

].copy()

    # ---------------------------------------
    # SOLO OPERACIÓN VIVA
    # ---------------------------------------

    df = df[
        df["Categoria"].isin([
            "Pendiente",
            "En Curso",
            "Finalizado"
        ])
    ].copy()

    # ---------------------------------------
    # ELIMINAR DESPACHOS VACÍOS
    # ---------------------------------------

    df = df[
        df["Despacho"]
        .fillna("")
        .str.strip()
        != ""
    ].copy()
    # ---------------------------------------
    # TOTAL DE PREPARACIONES
    # (Representa la carga del despacho)
    # ---------------------------------------

    total = (

        df

        .groupby("Despacho")["Preparacion"]

        .nunique()

        .reset_index(name="TotalPreparaciones")

    )

    # ---------------------------------------
    # PREPARACIONES FINALIZADAS
    # ---------------------------------------

    finalizados = (

        df[
            df["Categoria"] == "Finalizado"
        ]

        .groupby("Despacho")["Preparacion"]

        .nunique()

        .reset_index(name="PreparacionesFinalizadas")

    )

    # ---------------------------------------
    # MERGE
    # ---------------------------------------

    avance = total.merge(

        finalizados,

        on="Despacho",

        how="left"

    )

    avance["PreparacionesFinalizadas"] = (

        avance["PreparacionesFinalizadas"]

        .fillna(0)

        .astype(int)

    )

    # ---------------------------------------
    # %
    # ---------------------------------------

    avance["Avance"] = (

        avance["PreparacionesFinalizadas"]

        /

        avance["TotalPreparaciones"]

        * 100

    ).round(0)

    # ---------------------------------------
    # SOLO DESPACHOS CON TRABAJO PENDIENTE
    # ---------------------------------------

    avance = avance[
        avance["Avance"] < 100
    ].copy()

    # ---------------------------------------
    # ORDEN
    # ---------------------------------------

    avance = avance.sort_values(

        "Avance",

        ascending=True

    )

    return avance


    # ---------------------------------------
    # CARROS CRITICOS
    # ---------------------------------------



def obtener_carros_criticos(

    tabla_operativa,
    avance_despachos

):
    criticos = avance_despachos[

    avance_despachos["Avance"] >= 50

].copy()
    
    tabla = tabla_operativa.merge(

    criticos[

        [

            "Despacho",

            "Avance",

            "TotalPreparaciones",

            "PreparacionesFinalizadas"

        ]

    ],

    on="Despacho",

    how="inner"

)

    tabla = tabla[

    tabla["Categoria"] == "En Curso"

].copy()
    
    tabla["Faltan"] = (

    tabla["TotalPreparaciones"]

    -

    tabla["PreparacionesFinalizadas"]

)
    
    tabla = tabla.sort_values(

    [

        "Avance",

        "Faltan",

        "Hora"

    ],

    ascending=[

        False,

        True,

        True

    ]

)
    tabla = tabla[

    [

        "Despacho",

        "Avance",

        "Faltan",

        "Carro",

        "Cliente",

        "Unidades",

    ]

]
    

    return tabla


# ==========================================================
# FIN DEL MÓDULO TAREAS
# ==========================================================
