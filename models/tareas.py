import re

import pandas as pd


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

DIAS_TABLERO = 3

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

    # Campos del pedido necesarios para la operación.
    # "Pedido" se incorpora si existe para soportar:
    # 1 Pedido = varias Preparaciones = varios Carros.
    columnas_pedido = [
        "PreparacionID",
        "ClienteCodigo",
        "ClienteDescripcion",
        "PreparacionEstado",
        "TipoPreparacion",
        "Estado",
        "Fecha",
        "TotalUnidades",
        "TotalSKUs",
        "DetalleFamilias",
    ]

    if "Pedido" in df_pedidos.columns:
        columnas_pedido.append("Pedido")

    pedidos = df_pedidos[columnas_pedido].copy()

    # Claves auxiliares para cruzar preparaciones sin modificar
    # los IDs originales ni convertir nulos en cadenas vacías.
    tabla["_PreparacionKey"] = (
        tabla["PreparacionId"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    pedidos["_PreparacionKey"] = (
        pedidos["PreparacionID"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    # Evitar que valores vacíos se crucen entre sí.
    tabla.loc[
        tabla["_PreparacionKey"].fillna("").eq(""),
        "_PreparacionKey"
    ] = pd.NA
    pedidos.loc[
        pedidos["_PreparacionKey"].fillna("").eq(""),
        "_PreparacionKey"
    ] = pd.NA

    # Una preparación debe tener una única referencia de pedido.
    pedidos = (
        pedidos
        .sort_values("Fecha")
        .drop_duplicates(
            subset=["_PreparacionKey"],
            keep="last",
        )
    )

    tabla = tabla.merge(
        pedidos,
        on="_PreparacionKey",
        how="left",
        suffixes=("", "_pedido"),
    )

    tabla = tabla.drop(
        columns=["_PreparacionKey"],
        errors="ignore",
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
        "Articulos",
        "ArticulosDescripcion",
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
        *(["Pedido"] if "Pedido" in tabla.columns else []),
        *(["Vehiculo"] if "Vehiculo" in tabla.columns else []),
        *(["Peso"] if "Peso" in tabla.columns else []),
        *(["Volumen"] if "Volumen" in tabla.columns else []),

    ]
].copy()

    nombres_finales = [
        "Prioridad",
        "Orden",
        "Categoria",
        "FechaHora",
        "Estado",
        "_ArticulosTarea",
        "_ArticulosDescripcionTarea",
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
        "Familias",
    ]

    if "Pedido" in tabla.columns:
        nombres_finales.append("Pedido")
    if "Vehiculo" in tabla.columns:
        nombres_finales.append("Vehiculo")
    if "Peso" in tabla.columns:
        nombres_finales.append("Peso")
    if "Volumen" in tabla.columns:
        nombres_finales.append("Volumen")

    tabla.columns = nombres_finales

    # Informe Tareas: Peso en gramos y Volumen en mm³.
    if "Peso" in tabla.columns:
        tabla["PesoKg"] = pd.to_numeric(tabla["Peso"], errors="coerce").fillna(0) / 1000.0
    if "Volumen" in tabla.columns:
        tabla["VolumenM3"] = pd.to_numeric(tabla["Volumen"], errors="coerce").fillna(0) / 1_000_000_000.0

    # Normalizar el ID visible antes de construir cualquier vista derivada.
    tabla["Preparacion"] = (tabla["Preparacion"].astype("string").str.strip().str.replace(r"\.0+$", "", regex=True))
    tabla["Preparacion"] = tabla["Preparacion"].where(tabla["Preparacion"].notna() & tabla["Preparacion"].ne(""), pd.NA)

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

    # Los carros abiertos no vencen por fecha.
    resumen["CarrosEnCurso"] = (
        tabla.loc[tabla["Categoria"].eq("En Curso"), "Carro"].dropna().nunique()
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

    estado_activo = (
        tabla_pedidos["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["PENDIENTE", "PREPARACION"])
    )

    pendientes = tabla_pedidos[

        estado_activo

        &

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

    # Solo mostramos tareas pertenecientes a pedidos que siguen ABIERTOS.
    # Si el pedido ya quedó COMPLETO/CERRADO, desaparece del tablero aunque
    # DIGIP haya dejado una tarea o un CARRO técnicamente abierto.
    estado_pedido = (
        operativa["EstadoPedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    pedido_abierto = estado_pedido.isin(["PENDIENTE", "PREPARACION", "SUSPENDIDO", "SUSPENDIDA"])
    operativa = operativa.loc[pedido_abierto].copy()

    # Dentro de pedidos abiertos:
    # - Pendientes / En Curso / Suspendidas: sin límite de fecha.
    # - Finalizadas: solamente dentro de DIAS_TABLERO.
    estado_tarea = operativa["Estado"].fillna("").astype(str).str.strip().str.upper()
    es_suspendida = estado_tarea.str.contains("SUSPEND", na=False)
    es_abierta = operativa["Categoria"].isin(["Pendiente", "En Curso"]) | es_suspendida
    es_final_reciente = (
        operativa["Categoria"].eq("Finalizado")
        & operativa["FechaHora"].dt.normalize().ge(fecha_inicio)
    )
    operativa = operativa.loc[es_abierta | es_final_reciente].copy()

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

    # ------------------------------------------------------
    # UNA FILA OPERATIVA POR PREPARACIÓN / CARRO
    # ------------------------------------------------------
    # El Informe Tareas puede traer varias filas internas para una
    # misma preparación, repitiendo el mismo carro en el tablero.
    # La combinación Preparación + Carro conserva pedidos distintos
    # y elimina solamente duplicados operativos.
    operativa["_PreparacionKey"] = (
        operativa["Preparacion"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    operativa["_CarroKey"] = (
        operativa["Carro"]
        .fillna("")
        .astype(str)
        .str.replace(r"^[^A-Za-z0-9]*", "", regex=True)
        .str.strip()
        .str.upper()
    )

    # Para tareas ya tomadas, Preparacion + Carro sigue siendo la clave operativa.
    # Para tareas PENDIENTES todavía no existe carro: si deduplicamos solo por
    # Preparacion + Carro vacío, colapsamos todas las sectorizaciones en una sola fila.
    # Por eso, mientras no haya carro, usamos también el Área como clave.
    operativa["_AreaKey"] = (
        operativa["Area"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    operativa["_ClaveOperativa"] = operativa["_CarroKey"]
    mask_sin_carro = operativa["_CarroKey"].eq("")
    operativa.loc[mask_sin_carro, "_ClaveOperativa"] = (
        "PENDIENTE_AREA_" + operativa.loc[mask_sin_carro, "_AreaKey"]
    )

    operativa = (
        operativa
        .drop_duplicates(
            subset=["_PreparacionKey", "_ClaveOperativa"],
            keep="first",
        )
        .sort_values(
            ["Orden", "_PreparacionKey", "_AreaKey", "FechaHora"],
            ascending=[True, True, True, True],
        )
        .drop(
            columns=["_PreparacionKey", "_CarroKey", "_AreaKey", "_ClaveOperativa"],
            errors="ignore",
        )
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
    """
    Avance por despacho usando una ventana de 72 hs hábiles = 3 días hábiles.

    IMPORTANTE:
    - Para el avance SÍ se incluyen preparaciones de pedidos ya COMPLETOS,
      porque son las que forman el numerador del despacho.
    - La ventana evita mezclar reutilizaciones antiguas del mismo nombre
      de despacho.
    - Pendiente / En Curso / Finalizado participan si pertenecen a esa
      ventana operativa.
    """
    columnas = [
        "Despacho",
        "TotalPreparaciones",
        "PreparacionesFinalizadas",
        "PreparacionesEnCurso",
        "Avance",
    ]

    if tabla is None or tabla.empty:
        return pd.DataFrame(columns=columnas), []

    df = tabla.copy()

    # ------------------------------------------------------
    # VENTANA: 3 DÍAS HÁBILES
    # ------------------------------------------------------
    fechas_validas = pd.to_datetime(
        df["FechaHora"], errors="coerce"
    )

    fecha_operativa = fechas_validas.dt.normalize().max()

    if pd.isna(fecha_operativa):
        return pd.DataFrame(columns=columnas), []

    # Ejemplo: martes -> viernes como inicio de ventana.
    fecha_inicio = (
        fecha_operativa
        - pd.offsets.BDay(DIAS_TABLERO - 1)
    ).normalize()

    df["FechaHora"] = fechas_validas

    df = df.loc[
        df["FechaHora"].dt.normalize().ge(fecha_inicio)
        & df["FechaHora"].dt.normalize().le(fecha_operativa)
    ].copy()

    # ------------------------------------------------------
    # SOLO PREPARACIONES DE PEDIDO / DESPACHOS VÁLIDOS
    # ------------------------------------------------------
    if "TipoPreparacion" in df.columns:
        df = df.loc[
            df["TipoPreparacion"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("PEDIDO")
        ].copy()

    df = df.loc[
        df["Categoria"].isin(["Pendiente", "En Curso", "Finalizado"])
    ].copy()

    df = df.loc[
        df["Despacho"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=columnas), []

    # Una preparación puede tener varias tareas/sectores.
    # Para el avance cuenta una sola vez por despacho + preparación.
    df["_PreparacionKey"] = (
        df["Preparacion"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )

    df = df.loc[
        df["_PreparacionKey"].notna()
        & df["_PreparacionKey"].ne("")
    ].copy()

    total = (
        df.groupby("Despacho")["_PreparacionKey"]
        .nunique()
        .reset_index(name="TotalPreparaciones")
    )

    finalizados = (
        df.loc[df["Categoria"].eq("Finalizado")]
        .groupby("Despacho")["_PreparacionKey"]
        .nunique()
        .reset_index(name="PreparacionesFinalizadas")
    )

    en_curso = (
        df.loc[df["Categoria"].eq("En Curso")]
        .groupby("Despacho")["_PreparacionKey"]
        .nunique()
        .reset_index(name="PreparacionesEnCurso")
    )

    avance = (
        total
        .merge(finalizados, on="Despacho", how="left")
        .merge(en_curso, on="Despacho", how="left")
    )

    for columna in [
        "PreparacionesFinalizadas",
        "PreparacionesEnCurso",
    ]:
        avance[columna] = (
            avance[columna].fillna(0).astype(int)
        )

    avance["TotalPreparaciones"] = (
        avance["TotalPreparaciones"]
        .fillna(0)
        .astype(int)
    )

    avance["Avance"] = (
        avance["PreparacionesFinalizadas"]
        .div(
            avance["TotalPreparaciones"]
            .replace(0, pd.NA)
        )
        .mul(100)
        .fillna(0)
        .round(0)
    )

    # ------------------------------------------------------
    # DESPACHOS ABIERTOS DENTRO DE LA VENTANA
    # ------------------------------------------------------
    # Un despacho se considera iniciado si tiene al menos una preparación
    # En Curso o Finalizada. Pendientes puras quedan como "Sin iniciar".
    iniciadas = (
        avance["PreparacionesFinalizadas"]
        + avance["PreparacionesEnCurso"]
    )

    despachos_sin_iniciar = (
        avance.loc[
            iniciadas.eq(0),
            "Despacho",
        ]
        .sort_values()
        .tolist()
    )

    # Solo mostramos avance de despachos que ya arrancaron y todavía no
    # llegaron al 100%. Los completos siguen contando para calcular el
    # porcentaje, pero no se dibuja una dona de un despacho ya cerrado.
    avance = avance.loc[
        iniciadas.gt(0)
        & avance["Avance"].lt(100)
    ].copy()

    avance = avance.sort_values(
        ["Avance", "Despacho"],
        ascending=[True, True],
    )

    return avance, despachos_sin_iniciar


# ==========================================================
# CARROS CRITICOS
# ==========================================================

def obtener_carros_criticos(
    tabla_operativa,
    avance_despachos
):
    """
    Devuelve los pedidos/carros que pueden cerrar despachos.

    Compatible con ambos escenarios:
    - Actual: 1 pedido = 1 preparación = 1 carro.
    - Nuevo:  1 pedido = varias preparaciones = varios carros.

    La salida queda a nivel Pedido/Cliente:
        Despacho | Cliente | Carros | Sector

    Cada preparación sigue siendo un carro independiente. Cuando un pedido
    tenga varias preparaciones, sus carros se consolidan en una sola fila.
    """

    columnas_salida = ["Despacho", "Cliente", "Carros", "Sector"]

    if tabla_operativa is None or tabla_operativa.empty:
        return pd.DataFrame(columns=columnas_salida)

    if avance_despachos is None or avance_despachos.empty:
        return pd.DataFrame(columns=columnas_salida)

    criticos = avance_despachos[
        avance_despachos["Avance"] >= 50
    ].copy()

    if criticos.empty:
        return pd.DataFrame(columns=columnas_salida)

    tabla = tabla_operativa.merge(
        criticos[
            [
                "Despacho",
                "Avance",
                "TotalPreparaciones",
                "PreparacionesFinalizadas",
            ]
        ],
        on="Despacho",
        how="inner",
    )

    # Preparaciones operativamente abiertas:
    # - En Curso / Suspendidas -> muestran su carro.
    # - Pendientes sin carro   -> se marcan 🚫 SIN ASIGNAR.
    # Las finalizadas no forman parte de la alerta.
    estado_tarea = (
        tabla["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    tabla = tabla.loc[
        tabla["Categoria"].isin(["Pendiente", "En Curso"])
        | estado_tarea.str.contains("SUSPEND", na=False)
    ].copy()

    if tabla.empty:
        return pd.DataFrame(columns=columnas_salida)

    tabla["Faltan"] = (
        tabla["TotalPreparaciones"]
        - tabla["PreparacionesFinalizadas"]
    )

    # ------------------------------------------------------
    # NORMALIZACIÓN
    # ------------------------------------------------------

    def _texto_limpio(valor):
        if pd.isna(valor):
            return ""
        return str(valor).strip()

    def _sector_corto(valor):
        """
        Primeras 3 letras del sector/área.
        Ej.: SANITARIOS -> SAN / IMPORTADO -> IMP / NACIONAL -> NAC
        """
        texto = _texto_limpio(valor).upper()
        return texto[:3] if texto else "---"

    def _carro_limpio(valor):
        texto = _texto_limpio(valor)
        # Conservamos el icono visual que ya usa el tablero.
        return texto

    tabla["_SectorCorto"] = tabla["Area"].apply(_sector_corto)
    tabla["_CarroMostrar"] = tabla["Carro"].apply(_carro_limpio)

    # Detectar preparación/tarea todavía sin carro asignado.
    carro_norm = (
        tabla["_CarroMostrar"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    tabla["_SinAsignar"] = (
        carro_norm.eq("")
        | carro_norm.str.contains("SIN ASIGNAR", na=False)
    )

    # El mismo carro puede repetirse por tareas internas.
    # Lo dejamos una sola vez antes de consolidar el pedido.
    tabla["_CarroKey"] = (
        tabla["Carro"]
        .fillna("")
        .astype(str)
        .str.replace(r"^[^A-Za-z0-9]*", "", regex=True)
        .str.strip()
        .str.upper()
    )

    # Para los sin asignar no podemos deduplicar por carro vacío:
    # usamos Preparación + Área para conservar cada tarea pendiente.
    prep_key = (
        tabla["Preparacion"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
    )
    area_key = tabla["Area"].fillna("").astype(str).str.strip().str.upper()
    tabla.loc[tabla["_SinAsignar"], "_CarroKey"] = (
        "SIN_ASIGNAR_" + prep_key + "_" + area_key
    )

    tabla["_DespachoKey"] = (
        tabla["Despacho"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    tabla["_ClienteKey"] = (
        tabla["Cliente"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Si ya tenemos Pedido, esa es la clave correcta para agrupar
    # varias preparaciones/carros del mismo pedido.
    # Si todavía no existe en la fuente, mantenemos compatibilidad
    # agrupando por Despacho + Cliente.
    if "Pedido" in tabla.columns:
        pedido_key = (
            tabla["Pedido"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
        )
        tabla["_PedidoKey"] = pedido_key
        tabla.loc[tabla["_PedidoKey"].eq(""), "_PedidoKey"] = (
            tabla.loc[tabla["_PedidoKey"].eq(""), "_ClienteKey"]
        )
    else:
        tabla["_PedidoKey"] = tabla["_ClienteKey"]

    tabla = (
        tabla
        .sort_values(
            ["Avance", "Faltan", "FechaHora"],
            ascending=[False, True, True],
        )
        .drop_duplicates(
            subset=["_DespachoKey", "_PedidoKey", "_CarroKey"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------
    # CONSOLIDAR VARIOS CARROS DEL MISMO PEDIDO
    # ------------------------------------------------------

    def _unicos_ordenados(serie):
        salida = []
        vistos = set()
        for valor in serie:
            texto = _texto_limpio(valor)
            if not texto:
                continue
            clave = texto.upper()
            if clave not in vistos:
                vistos.add(clave)
                salida.append(texto)
        return salida

    filas = []

    for _, grupo in tabla.groupby(
        ["_DespachoKey", "_PedidoKey"],
        sort=False,
        dropna=False,
    ):
        grupo = grupo.sort_values(
            ["FechaHora", "_CarroKey"],
            ascending=[True, True],
        )

        # IMPORTANTE:
        # El sector debe quedar asociado al CARRO de la misma preparación.
        # No generamos dos listas independientes (carros / sectores), porque
        # eso pierde la relación 1 a 1 cuando un pedido tiene sectores distintos.
        carros_sector = []
        vistos_carro = set()

        # Sumamos las unidades a nivel CARRO/PREPARACIÓN antes de mostrarlo.
        # Así cada carro conserva su sector y su volumen real:
        # 🚧 CARRO301 (NAC - 105) - 🚧 CARRO302 (IMP - 166)
        for _, fila_carro in grupo.iterrows():
            carro = _texto_limpio(fila_carro.get("_CarroMostrar", ""))
            sector = _texto_limpio(fila_carro.get("_SectorCorto", ""))

            sin_asignar = bool(fila_carro.get("_SinAsignar", False))
            carro_key = _texto_limpio(fila_carro.get("_CarroKey", "")).upper()

            if not carro_key or carro_key in vistos_carro:
                continue

            vistos_carro.add(carro_key)

            if sin_asignar:
                # La clave es única por Preparación + Área.
                mask_carro = grupo["_CarroKey"].astype(str).eq(carro_key)
            else:
                # Todas las líneas del mismo carro/preparación.
                mask_carro = grupo["_CarroMostrar"].astype(str).map(
                    lambda x: re.sub(r"^[^A-Za-z0-9]*", "", x).strip().upper()
                ).eq(
                    re.sub(r"^[^A-Za-z0-9]*", "", carro).strip().upper()
                )

            unidades_carro = pd.to_numeric(
                grupo.loc[mask_carro, "Unidades"],
                errors="coerce",
            ).fillna(0).sum()

            unidades_txt = f"{int(round(unidades_carro)):,}".replace(",", ".")

            if sin_asignar:
                if sector and sector != "---":
                    carros_sector.append(f"🚫 SIN ASIGNAR ({sector} - {unidades_txt})")
                else:
                    carros_sector.append(f"🚫 SIN ASIGNAR ({unidades_txt})")
            else:
                # Solo para visualización quitamos el prefijo CARRO.
                carro_visual = re.sub(
                    r"^CARRO\s*",
                    "",
                    re.sub(r"^[^A-Za-z0-9]*", "", carro).strip().upper(),
                    flags=re.IGNORECASE,
                )
                if sector and sector != "---":
                    carros_sector.append(f"🚧 {carro_visual} ({sector} - {unidades_txt})")
                else:
                    carros_sector.append(f"🚧 {carro_visual} ({unidades_txt})")

        tiene_sin_asignar = bool(grupo["_SinAsignar"].any())

        filas.append(
            {
                "Despacho": _texto_limpio(grupo["Despacho"].iloc[0]),
                "Cliente": _texto_limpio(grupo["Cliente"].iloc[0]),
                # Cada carro ya sale con SU sector correcto.
                # Ej.: 🚧 CARRO301 (NAC) - 🚧 CARRO302 (IMP)
                "Carros": " - ".join(carros_sector),
                # Se conserva por compatibilidad, pero la vista ya no depende de ella.
                "Sector": "",
                "_Avance": grupo["Avance"].iloc[0],
                "_Faltan": grupo["Faltan"].iloc[0],
                "_HoraOrden": grupo["FechaHora"].min(),
                "_SinAsignarOrden": 1 if tiene_sin_asignar else 0,
            }
        )

    salida = pd.DataFrame(filas)

    if salida.empty:
        return pd.DataFrame(columns=columnas_salida)

    salida = (
        salida
        .sort_values(
            ["_SinAsignarOrden", "_Avance", "_Faltan", "_HoraOrden"],
            ascending=[False, False, True, True],
        )
        .drop(
            columns=["_SinAsignarOrden", "_Avance", "_Faltan", "_HoraOrden"],
            errors="ignore",
        )
        .reset_index(drop=True)
    )

    return salida[columnas_salida]


# ==========================================================
# FIN DEL MÓDULO TAREAS
# ==========================================================
