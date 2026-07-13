import pandas as pd

# ==========================================================
# CONFIGURACIÓN
# ==========================================================

HORAS_TABLERO = 48

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
            "Fecha"
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
    # HORA (SOLO PARA MOSTRAR)
    # ------------------------------------------------------

    tabla["Hora"] = tabla["FechaHora"].dt.strftime("%H:%M")

    # ------------------------------------------------------
    # TABLA FINAL
    # ------------------------------------------------------

    tabla = tabla[
        [
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
            "Estado"
        ]
    ].copy()

    tabla.columns = [
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
        "EstadoPedido"
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
    # VENTANA DEL TABLERO
    # ------------------------------------------------------

    limite = pd.Timestamp.now() - pd.Timedelta(hours=HORAS_TABLERO)

    # ------------------------------------------------------
    # PEDIDOS PENDIENTES
    # (No completos y no eliminados)
    # ------------------------------------------------------

    resumen["PedidosPendientes"] = len(

        df_pedidos[

            ~df_pedidos["Estado"]
            .fillna("")
            .str.upper()
            .isin(
                [
                    "COMPLETO",
                    "ELIMINADO"
                ]
            )

        ]

    )

    # ------------------------------------------------------
    # CARROS EN CURSO
    # ------------------------------------------------------

    resumen["CarrosEnCurso"] = (

        tabla[

            (tabla["Categoria"] == "En Curso")

            &

            (tabla["FechaHora"] >= limite)

        ]["Carro"]

        .nunique()

    )

    # ------------------------------------------------------
    # CARROS FINALIZADOS
    # ------------------------------------------------------

    resumen["CarrosFinalizados"] = (

        tabla[

            (tabla["Categoria"] == "Finalizado")

            &

            (tabla["FechaHora"] >= limite)

        ]["Carro"]

        .nunique()

    )

    return resumen

# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def obtener_tabla_operativa(tabla):

    operativa = tabla.copy()

    limite = pd.Timestamp.now() - pd.Timedelta(hours=HORAS_TABLERO)

    operativa = operativa[

        operativa["FechaHora"] >= limite

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

            "Categoria",

            "FechaHora"

        ]

    )

    operativa.reset_index(

        drop=True,

        inplace=True

    )

    return operativa

# ==========================================================
# FIN DEL MÓDULO TAREAS
# ==========================================================
