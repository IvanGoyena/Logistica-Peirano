import pandas as pd


# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def construir_tabla_tareas(
    df_tareas,
    df_pedidos,
    df_clientes
):

    tabla = df_tareas.copy()

    # ======================================================
    # PEDIDOS
    # ======================================================

    try:

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
        ]

    except Exception as e:

        raise Exception(
            f"ERROR PEDIDOS\n\n"
            f"Columnas:\n{df_pedidos.columns.tolist()}\n\n{e}"
        )

    tabla = tabla.merge(

        pedidos,

        left_on="PreparacionId",
        right_on="PreparacionID",

        how="left"

    )

        # ======================================================
    # CLIENTES
    # ======================================================

    try:

        clientes = df_clientes[
            [
                "Codigo_Cliente",
                "Zona",
                "Provincia",
                "Localidad",
                "Distrito",
                "Entrega"
            ]
        ]

    except Exception as e:

        raise Exception(
            f"ERROR CLIENTES\n\n"
            f"Columnas:\n{df_clientes.columns.tolist()}\n\n{e}"
        )

    tabla = tabla.merge(

        clientes,

        left_on="ClienteCodigo",
        right_on="Codigo_Cliente",

        how="left"

    )

    # ======================================================
    # USUARIO
    # ======================================================

    tabla["Usuario"] = (

        tabla["UsuarioNombre"].fillna("")

        + " "

        + tabla["UsuarioApellido"].fillna("")

    ).str.strip()

    # ======================================================
    # CATEGORIA
    # (provisoria)
    # ======================================================

    tabla["Categoria"] = "Pendiente"

    tabla.loc[
        tabla["ContenedorNumero"]
        .astype(str)
        .str.upper()
        .str.contains("CARRO", na=False),
        "Categoria"
    ] = "Carro"

    # ======================================================
    # TIEMPO
    # ======================================================

    tabla["Hora"] = pd.to_datetime(
        tabla["FechaHoraEstado"],
        errors="coerce"
    )

    # ======================================================
    # TABLA FINAL
    # ======================================================

    tabla = tabla[

        [

            "Categoria",

            "TareaEstado",

            "PreparacionId",

            "ClienteDescripcion",

            "Zona",

            "Localidad",

            "AreaDescripcion",

            "DespachoDescripcion",

            "Hora",

            "ContenedorNumero",

            "Usuario",

            "PreparacionEstado",

            "TipoPreparacion",

            "Estado"

        ]

    ]

    tabla.columns = [

        "Categoria",

        "Estado",

        "Preparacion",

        "Cliente",

        "Zona",

        "Localidad",

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

def obtener_resumen_operativo(tabla):

    resumen = {}


# ==========================================================
# CARROS EN CURSO
# ==========================================================

def obtener_carros_en_curso(tabla):

    carros = tabla.copy()

    # Solo contenedores que contienen CARRO
    carros = carros[
        carros["Carro"]
        .astype(str)
        .str.upper()
        .str.contains("CARRO", na=False)
    ]

    # Quitar TipoPreparacion vacío
    carros = carros[
        carros["TipoPreparacion"]
        .fillna("")
        .str.strip()
        != ""
    ]

    # Quitar pedidos completos
    carros = carros[
        carros["EstadoPedido"]
        .fillna("")
        .str.upper()
        != "COMPLETO"
    ]

    # Columnas para la validación
    carros = carros[
        [
            "Categoria",
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
    ]

    return carros