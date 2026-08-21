from __future__ import annotations

import re
import unicodedata

import pandas as pd

from models.detalle import (
    construir_tabla_detalle,
    construir_resumen_pedidos,
)


# ==========================================================
# NORMALIZACIÓN CENTRAL DEL REPORTE PEDIDOS DIGIP
# ==========================================================

def _clave_columna(nombre: object) -> str:
    valor = str(nombre or "").strip()
    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(
        caracter
        for caracter in valor
        if not unicodedata.combining(caracter)
    )
    valor = valor.lower()
    return re.sub(r"[^a-z0-9]+", "", valor)


def normalizar_pedidos_digip(
    df_pedidos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convierte el reporte de Pedidos DIGIP al contrato interno
    usado por Pedidos, Despachos y otros módulos.

    Soporta el formato histórico y el formato nuevo de DIGIP.
    """
    if df_pedidos is None:
        return pd.DataFrame()

    tabla = df_pedidos.copy()

    aliases = {
        "pedidoid": "PedidoID",
        "codigo": "Codigo",
        "codigopedido": "Codigo",
        "clienteid": "ClienteID",
        "codigocliente": "ClienteCodigo",
        "clienteubicaciondescripcion": "ClienteUbicacionDescripcion",
        "clientedescripcion": "ClienteDescripcion",
        "codigodespacho": "CodigoDespacho",
        "codigodeenvio": "CodigoDeEnvio",
        "serviciodeenvio": "ServicioDeEnvioTipo",
        "serviciodeenviotipo": "ServicioDeEnvioTipo",
        "ordenpreparacion": "OrdenPreparacion",
        "despachoid": "DespachoID",
        "preparacionid": "PreparacionID",
        "tipopreparacion": "TipoPreparacion",
        "estadopreparacion": "PreparacionEstado",
        "fechaestimadadeentrega": "FechaEstimadaEntrega",
        "despachodescripcion": "DespachoDescripcion",
        "despacho": "DespachoDescripcion",
        "unidadespedidas": "UnidadesPedidas",
        "unidadessatisfechas": "UnidadesSatisfechas",
    }

    columnas_originales = list(tabla.columns)
    destinos_existentes = set(columnas_originales)
    renombres: dict[str, str] = {}

    for columna in columnas_originales:
        # Evitar que "Despacho Id.1" sea interpretado como DespachoID.
        if str(columna).strip().lower().endswith(".1"):
            continue

        destino = aliases.get(
            _clave_columna(columna)
        )

        if (
            destino
            and columna != destino
            and destino not in destinos_existentes
        ):
            renombres[columna] = destino
            destinos_existentes.add(destino)

    if renombres:
        tabla = tabla.rename(
            columns=renombres
        )

    if "Codigo" not in tabla.columns:
        raise ValueError(
            "Pedidos DIGIP no contiene una columna de código de pedido. "
            f"Columnas recibidas: {list(df_pedidos.columns)}"
        )

    # ------------------------------------------------------
    # PEDIDO NORMALIZADO
    # ------------------------------------------------------
    # Formato nuevo real:
    # "0001  213970-1" -> "213970"
    #
    # También soporta:
    # "213970-1" -> "213970"
    # "PEDIDO 213970-1" -> "213970"
    codigo = (
        tabla["Codigo"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["Pedido"] = (
        codigo
        .str.split()
        .str[-1]
        .fillna("")
        .str.split("-")
        .str[0]
        .str.strip()
    )

    # ------------------------------------------------------
    # TEXTOS DEL CONTRATO
    # ------------------------------------------------------
    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "ClienteUbicacionDescripcion",
        "Estado",
        "TipoPreparacion",
        "PreparacionEstado",
        "CodigoDespacho",
        "DespachoDescripcion",
    ]

    for columna in columnas_texto:
        if columna not in tabla.columns:
            tabla[columna] = ""

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
        )

    # PreparacionID debe conservar NA cuando no existe.
    if "PreparacionID" not in tabla.columns:
        tabla["PreparacionID"] = pd.Series(
            pd.NA,
            index=tabla.index,
            dtype="string",
        )
    else:
        preparacion = (
            tabla["PreparacionID"]
            .astype("string")
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
        )

        tabla["PreparacionID"] = (
            preparacion.where(
                preparacion.notna()
                & preparacion.ne("")
                & preparacion.str.upper().ne("NAN"),
                pd.NA,
            )
        )

    # ------------------------------------------------------
    # UNIDADES INFORMADAS POR DIGIP
    # ------------------------------------------------------
    # Campos incorporados recientemente al reporte Pedidos DIGIP.
    # Se conservan separados de TotalUnidades para no modificar el
    # contrato histórico utilizado por Pedidos, Despachos y Tareas.
    for columna in [
        "UnidadesPedidas",
        "UnidadesSatisfechas",
    ]:
        if columna in tabla.columns:
            tabla[columna] = (
                pd.to_numeric(tabla[columna], errors="coerce")
                .fillna(0)
            )

    # ------------------------------------------------------
    # FECHAS
    # ------------------------------------------------------
    for columna in [
        "Fecha",
        "FechaEstimadaEntrega",
    ]:
        if columna in tabla.columns:
            tabla[columna] = pd.to_datetime(
                tabla[columna],
                errors="coerce",
                dayfirst=True,
            )

    return tabla


# ==========================================================
# TABLA PEDIDOS
# ==========================================================

def construir_tabla_pedidos(
    df_pedidos,
    df_detalle,
    df_articulos,
    df_clientes,
    df_volumetria,
    tabla_detalle_preparada=None,
):
    # ==========================================================
    # NORMALIZAR REPORTE DIGIP
    # ==========================================================
    tabla = normalizar_pedidos_digip(
        df_pedidos
    )

    # ==========================================================
    # CLIENTE DESDE MAESTRO CLIENTES
    # ==========================================================
    # El campo "ClienteUbicacion Descripcion" de DIGIP describe
    # la ubicación/sucursal logística (ej.: CANNING, COMUNA 10),
    # NO el nombre comercial del cliente.
    #
    # Para ClienteDescripcion usamos:
    # Maestro Clientes.Codigo_Cliente -> Maestro Clientes.Cliente
    maestro_clientes = (
        df_clientes.copy()
        if df_clientes is not None
        else pd.DataFrame()
    )

    if not maestro_clientes.empty:
        maestro_clientes.columns = (
            maestro_clientes.columns
            .astype(str)
            .str.strip()
        )

        if (
            "Codigo_Cliente" in maestro_clientes.columns
            and "Cliente" in maestro_clientes.columns
        ):
            clientes_nombre = maestro_clientes[
                [
                    "Codigo_Cliente",
                    "Cliente",
                ]
            ].copy()

            clientes_nombre["ClienteCodigo"] = (
                clientes_nombre["Codigo_Cliente"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
            )

            clientes_nombre["ClienteDescripcionMaestro"] = (
                clientes_nombre["Cliente"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            clientes_nombre = (
                clientes_nombre.loc[
                    clientes_nombre["ClienteCodigo"].ne("")
                ]
                .sort_values(
                    [
                        "ClienteCodigo",
                        "ClienteDescripcionMaestro",
                    ]
                )
                .drop_duplicates(
                    subset=["ClienteCodigo"],
                    keep="first",
                )
                [
                    [
                        "ClienteCodigo",
                        "ClienteDescripcionMaestro",
                    ]
                ]
            )

            tabla["ClienteCodigo"] = (
                tabla["ClienteCodigo"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
            )

            tabla = tabla.merge(
                clientes_nombre,
                on="ClienteCodigo",
                how="left",
                validate="many_to_one",
            )

            # El Maestro es la fuente principal del nombre.
            # Sólo si no encuentra coincidencia conservamos una
            # descripción anterior válida como respaldo.
            descripcion_anterior = (
                tabla["ClienteDescripcion"]
                if "ClienteDescripcion" in tabla.columns
                else pd.Series(
                    "",
                    index=tabla.index,
                    dtype="string",
                )
            )

            tabla["ClienteDescripcion"] = (
                tabla["ClienteDescripcionMaestro"]
                .fillna("")
                .astype(str)
                .str.strip()
                .where(
                    tabla["ClienteDescripcionMaestro"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .ne(""),
                    descripcion_anterior
                    .fillna("")
                    .astype(str)
                    .str.strip(),
                )
            )

            tabla = tabla.drop(
                columns=[
                    "ClienteDescripcionMaestro",
                ],
                errors="ignore",
            )

    # ==========================================================
    # TABLA DETALLE
    # ==========================================================
    tabla_detalle = (
        tabla_detalle_preparada
        if tabla_detalle_preparada is not None
        else construir_tabla_detalle(
            df_detalle,
            df_articulos,
            df_volumetria,
        )
    )

    # Asegurar misma clave para el merge.
    if "Pedido" in tabla_detalle.columns:
        tabla_detalle = tabla_detalle.copy()
        tabla_detalle["Pedido"] = (
            tabla_detalle["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
            .str.split("-")
            .str[0]
        )

    # ==========================================================
    # RESUMEN DEL DETALLE
    # ==========================================================
    resumen = construir_resumen_pedidos(
        tabla_detalle
    )

    if not resumen.empty:
        resumen = resumen.copy()
        resumen["Pedido"] = (
            resumen["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(
                r"\.0$",
                "",
                regex=True,
            )
            .str.split("-")
            .str[0]
        )

    # ==========================================================
    # MERGE
    # ==========================================================
    tabla = tabla.merge(
        resumen,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    # ==========================================================
    # PEDIDOS ACTIVOS
    # ==========================================================
    # No depender de mayúsculas, tildes o espacios.
    estado_normalizado = (
        tabla["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(
            "Ó",
            "O",
            regex=False,
        )
    )

    tabla = tabla.loc[
        estado_normalizado.isin(
            [
                "PENDIENTE",
                "PREPARACION",
            ]
        )
    ].copy()

    # ==========================================================
    # NO DESCARTAR ACTIVOS SIN DETALLE
    # ==========================================================
    # Antes se eliminaban con TotalUnidades.notna().
    # Eso puede vaciar el módulo si el ERP y DIGIP están desfasados.
    # Se conserva el pedido activo y las métricas quedan en cero.
    for columna in [
        "TotalUnidades",
        "TotalSKUs",
        "CantidadFamilias",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = 0

        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    if "TotalM3" not in tabla.columns:
        tabla["TotalM3"] = 0.0

    tabla["TotalM3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .round(3)
    )

    if "DetalleFamilias" not in tabla.columns:
        tabla["DetalleFamilias"] = ""

    tabla["DetalleFamilias"] = (
        tabla["DetalleFamilias"]
        .fillna("")
        .astype(str)
    )

    # ==========================================================
    # LIMPIEZA DE COLUMNAS TÉCNICAS
    # ==========================================================
    tabla = tabla.drop(
        columns=[
            "PedidoID",
            "Codigo",
            "CodigoDeEnvio",
            "ServicioDeEnvioTipo",
            "OrdenPreparacion",
            "DespachoID",
            "ClienteID",
            "Tags",
            "Despacho Id.1",
        ],
        errors="ignore",
    )

    # ==========================================================
    # ORDEN DE COLUMNAS
    # ==========================================================
    columnas_fijas = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "TipoPreparacion",
        "PreparacionEstado",
        "CodigoDespacho",
        "DespachoDescripcion",
        "Fecha",
        "FechaEstimadaEntrega",
        "PreparacionID",
        "Importe",
        "TotalUnidades",
        "TotalM3",
        "TotalSKUs",
        "CantidadFamilias",
        "DetalleFamilias",
    ]

    columnas_fijas = [
        columna
        for columna in columnas_fijas
        if columna in tabla.columns
    ]

    columnas_extra = [
        columna
        for columna in tabla.columns
        if columna not in columnas_fijas
    ]

    return tabla[
        columnas_fijas
        + sorted(columnas_extra)
    ].reset_index(drop=True)
