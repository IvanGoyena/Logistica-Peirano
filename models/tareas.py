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
            errors="coerce",
            dayfirst=True
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

# CARRO terminado pero todavía pendiente de resolver
    tabla.loc[
    (
        tabla["Categoria"] == "En Curso"
    )
    &
    (
        tabla["TareaEstado"]
        .fillna("")
        .str.upper()
        .eq("FINALIZADA")
    ),
    "Semaforo"
] = "🔴"

# CARRO que todavía se está preparando
    tabla.loc[
    (
        tabla["Categoria"] == "En Curso"
    )
    &
    (
        tabla["TareaEstado"]
        .fillna("")
        .str.upper()
        .ne("FINALIZADA")
    ),
    "Semaforo"
] = "🟠"

# Contenedor numérico completamente cerrado
    tabla.loc[
    tabla["Categoria"] == "Finalizado",
    "Semaforo"
] = "🟢"


# ------------------------------------------------------
# ORDEN DE PRIORIDAD
# ------------------------------------------------------

    tabla["Orden"] = 4

# 1 - CARRO terminado, pendiente de resolver
    tabla.loc[
    (
        tabla["Categoria"] == "En Curso"
    )
    &
    (
        tabla["TareaEstado"]
        .fillna("")
        .str.upper()
        .eq("FINALIZADA")
    ),
    "Orden"
] = 1

# 2 - CARRO trabajando
    tabla.loc[
    (
        tabla["Categoria"] == "En Curso"
    )
    &
    (
        tabla["TareaEstado"]
        .fillna("")
        .str.upper()
        .ne("FINALIZADA")
    ),
    "Orden"
] = 2

# 3 - Preparación que todavía no comenzó
    tabla.loc[
    tabla["Categoria"] == "Pendiente",
    "Orden"
] = 3

# 4 - Contenedor numérico finalizado
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
# PENDIENTE DE PICKEAR
# ==========================================================

def obtener_pendiente_pick(
    tabla_tareas,
    tabla_pedidos
):

    # ---------------------------------------
    # PREPARACIONES ACTIVAS EN LA OPERACIÓN
    # ---------------------------------------

    preparaciones_en_curso = set(

        tabla_tareas[
            tabla_tareas["Categoria"].isin(
                [
                    "En Curso",
                    "Finalizado"
                ]
            )
        ]["Preparacion"]

        .dropna()

        .unique()

    )

    # ---------------------------------------
    # PREPARACIONES PENDIENTES DE INICIAR
    # ---------------------------------------

    pendientes = tabla_pedidos[

        (~tabla_pedidos["PreparacionID"].isin(preparaciones_en_curso))

        &

        (tabla_pedidos["PreparacionID"].notna())

    ].copy()

    return {

        "Preparaciones": pendientes["PreparacionID"].nunique(),

        "Unidades": int(

            pendientes["TotalUnidades"]

            .fillna(0)

            .sum()

        )

    }

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

    fecha_operativa = (
        tabla["FechaHora"]
        .dt.normalize()
        .max()
    )

    fecha_inicio = (
        fecha_operativa
        - pd.Timedelta(days=DIAS_TABLERO - 1)
    )

    df = tabla[
        tabla["FechaHora"].dt.normalize() >= fecha_inicio
    ].copy()

    # ---------------------------------------
    # SOLO OPERACIÓN VIVA
    # ---------------------------------------

    df = df[
        df["Categoria"].isin(
            [
                "Pendiente",
                "En Curso",
                "Finalizado",
            ]
        )
    ].copy()

    # ---------------------------------------
    # ELIMINAR DESPACHOS VACÍOS
    # ---------------------------------------

    df = df[
        df["Despacho"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    ].copy()

    # ---------------------------------------
    # TOTAL DE PREPARACIONES DEL DESPACHO
    # ---------------------------------------

    total = (
        df
        .groupby("Despacho")["Preparacion"]
        .nunique()
        .reset_index(
            name="TotalPreparaciones"
        )
    )

    # ---------------------------------------
    # PREPARACIONES CERRADAS
    #
    # Finalizado significa:
    # contenedor numérico + tarea finalizada
    # ---------------------------------------

    finalizados = (
        df[
            df["Categoria"] == "Finalizado"
        ]
        .groupby("Despacho")["Preparacion"]
        .nunique()
        .reset_index(
            name="PreparacionesFinalizadas"
        )
    )

    # ---------------------------------------
    # UNIR RESULTADOS
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

    avance["TotalPreparaciones"] = (
        avance["TotalPreparaciones"]
        .fillna(0)
        .astype(int)
    )

    # ---------------------------------------
    # PORCENTAJE
    # ---------------------------------------

    avance["Avance"] = (
        avance["PreparacionesFinalizadas"]
        /
        avance["TotalPreparaciones"]
        * 100
    ).round(0)

    # ---------------------------------------
    # GUARDAR DESPACHOS SIN INICIAR
    # Antes de quitarlos de las donas
    # ---------------------------------------

    despachos_sin_iniciar = (
        avance[
            avance["Avance"] == 0
        ]["Despacho"]
        .sort_values()
        .tolist()
    )

    # ---------------------------------------
    # SOLO DONAS DE DESPACHOS ACTIVOS
    # ---------------------------------------

    avance = avance[
        (
            avance["Avance"] > 0
        )
        &
        (
            avance["Avance"] < 100
        )
    ].copy()

    avance = avance.sort_values(
        "Avance",
        ascending=True
    )

    return avance, despachos_sin_iniciar

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

        "Carro",

        "Cliente",

        "Unidades",

    ]

]
    

    return tabla


# ==========================================================
# FIN DEL MÓDULO TAREAS
# ==========================================================
