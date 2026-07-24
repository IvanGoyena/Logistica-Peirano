# models/consultas.py

from __future__ import annotations

import pandas as pd


# ==========================================================
# COLUMNAS VISIBLES PARA COMERCIAL
# ==========================================================

COLUMNAS_FINALES_CONSULTAS = [
    "Pedido",
    "Fecha",
    "FechaTransmisionERP",
    "HoraTransmisionERP",
    "NroEnvioERP",
    "ClienteCodigo",
    "Cliente",
    "Unidades",
    "M3",
    "Familias",
    "Planificacion",
    "Despacho",
    "CategoriaComercial",
    "EstadoComercial",
    "Contenedor",
]


# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def normalizar_texto(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.strip()


def normalizar_clave(serie: pd.Series) -> pd.Series:
    return normalizar_texto(serie).str.replace(
        r"\.0$",
        "",
        regex=True,
    )


def normalizar_pedido(serie: pd.Series) -> pd.Series:
    return normalizar_clave(serie).str.split("-").str[0]


def obtener_columna(
    tabla: pd.DataFrame,
    nombres: list[str],
    valor_default="",
) -> pd.Series:

    for nombre in nombres:
        if nombre in tabla.columns:
            return tabla[nombre].copy()

    return pd.Series(
        valor_default,
        index=tabla.index,
    )


# ==========================================================
# CARROS / CONTENEDORES
# ==========================================================

def construir_contenedores(
    df_tareas: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    Agrupa todos los carros o contenedores relacionados con una
    misma preparación.

    Ejemplo:
        CARRO021 | CARRO035
    """

    columnas_salida = [
        "PreparacionID",
        "Contenedor",
    ]

    if df_tareas is None or df_tareas.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    tareas = df_tareas.copy()

    columna_preparacion = None

    for candidata in [
        "PreparacionId",
        "PreparacionID",
        "Preparacion",
    ]:
        if candidata in tareas.columns:
            columna_preparacion = candidata
            break

    columna_contenedor = None

    for candidata in [
        "ContenedorNumero",
        "Carro",
        "Contenedor",
    ]:
        if candidata in tareas.columns:
            columna_contenedor = candidata
            break

    if (
        columna_preparacion is None
        or columna_contenedor is None
    ):
        return pd.DataFrame(
            columns=columnas_salida
        )

    # Únicamente tareas de preparación.
    if "TareaTipo" in tareas.columns:
        tareas = tareas[
            tareas["TareaTipo"]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.contains(
                "PREPARACION",
                na=False,
            )
        ].copy()

    tareas["PreparacionID"] = normalizar_clave(
        tareas[columna_preparacion]
    )

    tareas["Contenedor"] = normalizar_texto(
        tareas[columna_contenedor]
    )

    tareas = tareas[
        tareas["PreparacionID"].ne("")
        & tareas["Contenedor"].ne("")
    ].copy()

    if tareas.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    def unir_unicos(serie: pd.Series) -> str:
        valores = []

        for valor in serie:
            texto = str(valor).strip()

            if texto and texto not in valores:
                valores.append(texto)

        return " | ".join(valores)

    resumen = (
        tareas
        .groupby(
            "PreparacionID",
            as_index=False,
        )
        .agg(
            Contenedor=(
                "Contenedor",
                unir_unicos,
            )
        )
    )

    return resumen[
        columnas_salida
    ].copy()


# ==========================================================
# ESTADOS COMERCIALES
# ==========================================================

def construir_estados_comerciales(
    consultas: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """
    Estados simples para la consulta de Comercial.

    Reglas:
    1. Sin preparación:
       Pendiente / Esperando ingreso a preparación.

    2. Con preparación pero sin carro o contenedor:
       Pendiente de iniciar / Preparación creada y pendiente de inicio.

    3. Con CARRO:
       En preparación / Pedido actualmente en preparación.

    4. Con contenedor numérico:
       Preparado / Preparación finalizada.

    5. Con contenedor numérico y despacho descriptivo:
       Asignado a despacho / Pedido preparado y agrupado en el despacho.
    """

    preparacion = normalizar_clave(
        consultas["PreparacionID"]
    )

    contenedor = normalizar_texto(
        consultas["Contenedor"]
    )

    despacho = normalizar_texto(
        consultas["Despacho"]
    )

    tiene_preparacion = preparacion.ne("")
    tiene_contenedor = contenedor.ne("")
    tiene_carro = contenedor.str.upper().str.contains(
        "CARRO",
        na=False,
    )
    tiene_despacho = despacho.ne("")

    categoria = pd.Series(
        "Pendiente",
        index=consultas.index,
        dtype="object",
    )

    estado = pd.Series(
        "Esperando ingreso a preparación",
        index=consultas.index,
        dtype="object",
    )

    # Preparación creada, todavía sin carro.
    mascara = tiene_preparacion & ~tiene_contenedor

    categoria.loc[mascara] = "Pendiente de iniciar"
    estado.loc[mascara] = (
        "Preparación creada y pendiente de inicio"
    )

    # Preparación trabajando con carro.
    mascara = tiene_preparacion & tiene_carro

    categoria.loc[mascara] = "En preparación"
    estado.loc[mascara] = (
        "Pedido actualmente en preparación"
    )

    # Preparación cerrada en contenedor definitivo.
    mascara = (
        tiene_preparacion
        & tiene_contenedor
        & ~tiene_carro
    )

    categoria.loc[mascara] = "Preparado"
    estado.loc[mascara] = "Preparación finalizada"

    # Solo corresponde mostrar asignación cuando existe una
    # descripción real de despacho.
    mascara = (
        tiene_preparacion
        & tiene_contenedor
        & ~tiene_carro
        & tiene_despacho
    )

    categoria.loc[mascara] = "Asignado a despacho"
    estado.loc[mascara] = (
        "Pedido preparado y agrupado en el despacho"
    )

    return categoria, estado


# ==========================================================
# TABLA DE CONSULTAS
# ==========================================================

def construir_tabla_consultas(
    tabla_operativa_pedidos: pd.DataFrame,
    df_tareas: pd.DataFrame | None = None,
) -> pd.DataFrame:

    if (
        tabla_operativa_pedidos is None
        or tabla_operativa_pedidos.empty
    ):
        return pd.DataFrame(
            columns=COLUMNAS_FINALES_CONSULTAS
        )

    tabla = tabla_operativa_pedidos.copy()

    requeridas = [
        "Pedido",
        "Fecha",
        "ClienteCodigo",
        "ClienteDescripcion",
        "PreparacionID",
        "TotalUnidades",
        "TotalM3",
        "DetalleFamilias",
    ]

    faltantes = [
        columna
        for columna in requeridas
        if columna not in tabla.columns
    ]

    if faltantes:
        raise ValueError(
            "Faltan columnas para construir la tabla de consultas: "
            f"{faltantes}"
        )

    consultas = pd.DataFrame(
        index=tabla.index
    )

    consultas["Pedido"] = normalizar_pedido(
        tabla["Pedido"]
    )

    consultas["Fecha"] = pd.to_datetime(
        tabla["Fecha"],
        errors="coerce",
        utc=True,
    ).dt.tz_localize(None)

    consultas["FechaTransmisionERP"] = pd.to_datetime(
        obtener_columna(
            tabla,
            ["FechaTransmisionERP"],
            pd.NaT,
        ),
        errors="coerce",
    )

    consultas["HoraTransmisionERP"] = normalizar_texto(
        obtener_columna(
            tabla,
            ["HoraTransmisionERP"],
        )
    )

    consultas["NroEnvioERP"] = normalizar_clave(
        obtener_columna(
            tabla,
            ["NroEnvioERP"],
        )
    )

    consultas["ClienteCodigo"] = normalizar_clave(
        tabla["ClienteCodigo"]
    )

    consultas["Cliente"] = normalizar_texto(
        tabla["ClienteDescripcion"]
    ).replace(
        "",
        "Sin cliente",
    )

    consultas["Unidades"] = (
        pd.to_numeric(
            tabla["TotalUnidades"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    consultas["M3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .round(3)
    )

    consultas["Familias"] = normalizar_texto(
        tabla["DetalleFamilias"]
    ).replace(
        "",
        "Sin familia",
    )

    consultas["Planificacion"] = normalizar_texto(
        obtener_columna(
            tabla,
            ["Planificacion"],
        )
    ).replace(
        "",
        "Sin definir",
    )

    # IMPORTANTE:
    # Para Comercial solo se muestra la descripción real.
    # El código interno NO se usa como reemplazo.
    consultas["Despacho"] = normalizar_texto(
        obtener_columna(
            tabla,
            ["DespachoDescripcion"],
        )
    )

    consultas["PreparacionID"] = normalizar_clave(
        tabla["PreparacionID"]
    )

    contenedores = construir_contenedores(
        df_tareas
    )

    consultas = consultas.merge(
        contenedores,
        on="PreparacionID",
        how="left",
        validate="many_to_one",
    )

    # Vacío es intencional: significa que todavía no tiene
    # carro ni contenedor asociado.
    consultas["Contenedor"] = normalizar_texto(
        consultas["Contenedor"]
    )

    categoria, estado = construir_estados_comerciales(
        consultas
    )

    consultas["CategoriaComercial"] = categoria
    consultas["EstadoComercial"] = estado

    consultas = (
        consultas
        .sort_values(
            by=[
                "Fecha",
                "Pedido",
            ],
            ascending=[
                False,
                False,
            ],
            na_position="last",
        )
        .drop_duplicates(
            # El número central puede repetirse en distintos códigos WMS
            # (por ejemplo, sucursal/prefijo distinto). No se debe deduplicar
            # únicamente por Pedido porque podría ocultar otro cliente.
            subset=[
                "Pedido",
                "ClienteCodigo",
                "PreparacionID",
            ],
            keep="first",
        )
        .reset_index(drop=True)
    )

    return consultas[
        COLUMNAS_FINALES_CONSULTAS
    ].copy()
