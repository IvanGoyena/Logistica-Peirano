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
        avance_despachos["Avance"] >= 25
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
# SUGERENCIA PROPIA DE EQUIPAMIENTO
# ==========================================================

# Regla operativa propia. No depende del Vehiculo sugerido por DIGIP.
# CARRO MULTIPLE conserva como referencia 6 espacios de 0,212 m³.
# DOBLE PALLET representa UNA sola tarea de hasta 2 pallets (3,60 m³).
# APILADORA queda para tareas que superan ese volumen.
VOLUMEN_CARRO_MULTIPLE_M3 = 6 * 0.212
VOLUMEN_DOBLE_PALLET_M3 = 3.60


def sugerir_equipamiento_operativo(volumen_m3):
    volumen = pd.to_numeric(pd.Series([volumen_m3]), errors="coerce").fillna(0).iloc[0]
    volumen = float(max(volumen, 0))

    if volumen <= VOLUMEN_CARRO_MULTIPLE_M3:
        return "🛒 CARRO MULTIPLE"
    if volumen <= VOLUMEN_DOBLE_PALLET_M3:
        return "📦 DOBLE PALLET"
    return "🏗️ APILADORA"


# ==========================================================
# ORGANIZACIÓN PRE POR DESPACHO / CAMIONETA
# ==========================================================

def obtener_organizacion_pre(tabla_operativa):
    """
    Construye una sugerencia visual de ocupación PRE por Despacho/Camioneta.

    PRE no se asigna por preparación individual: representa el lugar físico
    donde se consolida el Despacho/Camioneta.

    La asignación es una sugerencia del tablero:
    - conserva hasta 4 despachos activos;
    - prioriza despachos ya iniciados;
    - luego los ordena por antigüedad;
    - PRE 1..4 se muestran como posiciones físicas.
    """
    columnas = [
        "PRE", "Despacho / Camioneta", "Estado", "Preparaciones",
        "Áreas pendientes", "Áreas controladas", "Vol. pendiente m³",
        "Área sugerida", "Equipamiento sugerido",
    ]

    if tabla_operativa is None or tabla_operativa.empty:
        return pd.DataFrame(columns=columnas)

    df = tabla_operativa.copy()

    if "Despacho" not in df.columns:
        return pd.DataFrame(columns=columnas)

    df["_Despacho"] = (
        df["Despacho"].astype("string").fillna("").str.strip()
    )
    df = df.loc[df["_Despacho"].ne("")].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas)

    df["_Categoria"] = df["Categoria"].astype("string").fillna("").str.strip()
    df["_Resuelta"] = df["_Categoria"].eq("Finalizado")

    carro_pre = (
        df["Carro"].astype("string").fillna("").str.strip()
        if "Carro" in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    df["_SinAsignar"] = (
        ~df["_Resuelta"]
        & ~df["_Categoria"].eq("En Curso")
        & (
            carro_pre.eq("")
            | carro_pre.str.contains("SIN ASIGNAR", case=False, na=False)
        )
    )
    df["_Abierta"] = ~df["_Resuelta"]

    for c in ["VolumenM3"]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["_Prep"] = (
        df["Preparacion"].astype("string").fillna("").str.strip()
    )
    df["_Area"] = (
        df["Area"].astype("string").fillna("").str.strip().str.upper()
    )

    # Una tarea puede repetirse internamente. Consolidamos por despacho,
    # preparación y área antes de sumar volumen/estado.
    detalle = (
        df.sort_values("FechaHora")
        .drop_duplicates(["_Despacho", "_Prep", "_Area"], keep="last")
        .copy()
    )

    filas = []
    for despacho, grupo in detalle.groupby("_Despacho", sort=False):
        abiertas = grupo.loc[grupo["_Abierta"]].copy()
        resueltas = grupo.loc[grupo["_Resuelta"]].copy()
        por_tomar = grupo.loc[grupo["_SinAsignar"]].copy()

        # Volumen/equipamiento = remanente todavía sin tomar.
        volumen_pendiente = float(por_tomar["VolumenM3"].sum())
        equipos = (
            por_tomar["VolumenM3"]
            .apply(sugerir_equipamiento_operativo)
            .value_counts()
        )

        partes_equipo = []
        for equipo in ["🛒 CARRO MULTIPLE", "📦 DOBLE PALLET", "🏗️ APILADORA"]:
            cantidad = int(equipos.get(equipo, 0))
            if cantidad:
                partes_equipo.append(f"{cantidad} × {equipo}")

        # Área sugerida dinámica: solo remanente todavía sin tomar.
        if por_tomar.empty:
            area_sugerida = "✅ COMPLETO"
        else:
            estado_prep = grupo.groupby("_Prep", as_index=False).agg(
                AreasTotales=("_Area", "nunique")
            )
            pend_prep = por_tomar.groupby("_Prep")["_Area"].nunique().rename("AreasPendientes")
            estado_prep = estado_prep.merge(pend_prep, on="_Prep", how="left")
            estado_prep["AreasPendientes"] = estado_prep["AreasPendientes"].fillna(0).astype(int)

            candidatos = por_tomar.merge(estado_prep, on="_Prep", how="left")
            candidatos["CierraPreparacion"] = candidatos["AreasPendientes"].eq(1)
            candidatos["CercaniaCierre"] = (
                1.0 - (
                    (candidatos["AreasPendientes"] - 1).clip(lower=0)
                    / candidatos["AreasTotales"].clip(lower=1)
                )
            ).clip(0, 1)

            vol = candidatos["VolumenM3"].clip(lower=0)
            max_vol = float(vol.max()) if len(vol) else 0.0
            candidatos["QuickWin"] = 1 - (vol / max_vol) if max_vol > 0 else 1.0
            candidatos["ScoreArea"] = (
                candidatos["CierraPreparacion"].astype(float) * 50
                + candidatos["CercaniaCierre"] * 30
                + candidatos["QuickWin"] * 20
            )

            ranking = candidatos.groupby("_Area", as_index=False).agg(
                CierraAhora=("CierraPreparacion", "sum"),
                ScoreProm=("ScoreArea", "mean"),
                Tareas=("_Prep", "nunique"),
                Volumen=("VolumenM3", "sum"),
            ).sort_values(
                ["CierraAhora", "ScoreProm", "Tareas", "Volumen"],
                ascending=[False, False, False, True],
            )

            if ranking.empty:
                area_sugerida = "—"
            else:
                top = ranking.iloc[0]
                nombre = str(top["_Area"]).strip()
                area_sugerida = f"🔥 {nombre}" if int(top["CierraAhora"]) > 0 else f"➡️ {nombre}"

        en_curso = bool(
            grupo["_Categoria"].eq("En Curso").any()
            or grupo["_Resuelta"].any()
        )
        estado = "🟢 EN CURSO" if en_curso else "🟡 SIGUIENTE"

        filas.append({
            "Despacho / Camioneta": despacho,
            "Estado": estado,
            "Preparaciones": int(grupo["_Prep"].replace("", pd.NA).nunique()),
            "Áreas pendientes": int(por_tomar["_Area"].replace("", pd.NA).nunique()),
            "Áreas controladas": int(resueltas["_Area"].replace("", pd.NA).nunique()),
            "Vol. pendiente m³": round(volumen_pendiente, 2),
            "Área sugerida": area_sugerida,
            "Equipamiento sugerido": (
                " · ".join(partes_equipo)
                if partes_equipo
                else "✅ PICKING TOTALMENTE ASIGNADO"
            ),
            "_Iniciado": 0 if en_curso else 1,
            "_Hora": grupo["FechaHora"].min(),
        })

    salida = pd.DataFrame(filas)
    if salida.empty:
        return pd.DataFrame(columns=columnas)

    salida = salida.sort_values(
        ["_Iniciado", "_Hora", "Despacho / Camioneta"],
        ascending=[True, True, True],
    ).reset_index(drop=True)

    # Las cuatro posiciones físicas configuradas.
    salida["PRE"] = [
        f"PRE {i + 1}" if i < 4 else "⚠️ SIN PRE"
        for i in range(len(salida))
    ]

    salida = salida.drop(columns=["_Iniciado", "_Hora"], errors="ignore")
    return salida[columnas]

# ==========================================================
# FIN DEL MÓDULO TAREAS
# ==========================================================
