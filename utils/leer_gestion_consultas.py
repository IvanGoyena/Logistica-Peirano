# utils/leer_gestion_consultas.py

from __future__ import annotations

from typing import Any

import pandas as pd

from utils.google_sheets import (
    COLUMNAS_ANULACIONES,
    COLUMNAS_RECLAMOS,
    COLUMNAS_RECLAMOS_DETALLE,
    COLUMNAS_RECLAMOS_FOTOS,
    COLUMNAS_SOLICITUDES,
    COLUMNAS_URGENCIAS,
    leer_hoja,
)


# ==========================================================
# FUNCIONES GENERALES
# ==========================================================

def normalizar_pedido(
    pedido: Any,
) -> str:
    """
    Normaliza el número de pedido.

    Ejemplos:
        12345.0 -> 12345
        12345-1 -> 12345
    """

    if pedido is None:
        return ""

    pedido_texto = str(
        pedido
    ).strip()

    if pedido_texto.endswith(".0"):
        pedido_texto = pedido_texto[:-2]

    return (
        pedido_texto
        .split("-")[0]
        .strip()
    )


def crear_dataframe_vacio(
    columnas: list[str],
) -> pd.DataFrame:
    """
    Devuelve un DataFrame vacío con la estructura esperada.
    """

    return pd.DataFrame(
        columns=columnas
    )


def asegurar_columnas(
    dataframe: pd.DataFrame,
    columnas: list[str],
) -> pd.DataFrame:
    """
    Agrega columnas faltantes sin eliminar columnas adicionales.
    """

    tabla = dataframe.copy()

    for columna in columnas:

        if columna not in tabla.columns:
            tabla[columna] = ""

    columnas_extra = [
        columna
        for columna in tabla.columns
        if columna not in columnas
    ]

    return (
        tabla[
            columnas
            + columnas_extra
        ]
        .fillna("")
        .reset_index(drop=True)
    )


def ordenar_por_fecha(
    dataframe: pd.DataFrame,
    columna_fecha: str,
    descendente: bool = True,
) -> pd.DataFrame:
    """
    Ordena por fecha manteniendo el valor original visible.
    """

    if (
        dataframe.empty
        or columna_fecha not in dataframe.columns
    ):
        return (
            dataframe
            .copy()
            .reset_index(drop=True)
        )

    tabla = dataframe.copy()

    tabla["_FechaOrden"] = pd.to_datetime(
        tabla[columna_fecha],
        errors="coerce",
    )

    tabla = tabla.sort_values(
        "_FechaOrden",
        ascending=not descendente,
        na_position="last",
    )

    return (
        tabla
        .drop(
            columns=["_FechaOrden"]
        )
        .reset_index(drop=True)
    )


def leer_tabla_google(
    nombre_hoja: str,
    columnas: list[str],
    columna_fecha: str | None = None,
) -> pd.DataFrame:
    """
    Lee una hoja de Google Sheets y garantiza que tenga
    las columnas esperadas por la aplicación.
    """

    try:

        tabla = leer_hoja(
            nombre_hoja=nombre_hoja,
            columnas=columnas,
        )

    except Exception as error:

        raise RuntimeError(
            f"No se pudo leer la hoja "
            f"'{nombre_hoja}' de Google Sheets: "
            f"{error}"
        ) from error

    if tabla is None:

        tabla = crear_dataframe_vacio(
            columnas
        )

    tabla = asegurar_columnas(
        tabla,
        columnas,
    )

    if "Pedido" in tabla.columns:

        tabla["Pedido"] = (
            tabla["Pedido"]
            .apply(normalizar_pedido)
        )

    if columna_fecha:

        tabla = ordenar_por_fecha(
            tabla,
            columna_fecha,
        )

    return tabla.reset_index(
        drop=True
    )


# ==========================================================
# LECTURA DE GOOGLE SHEETS
# ==========================================================

def leer_solicitudes() -> pd.DataFrame:
    """
    Lee todas las solicitudes comerciales.
    """

    return leer_tabla_google(
        nombre_hoja="Solicitudes",
        columnas=COLUMNAS_SOLICITUDES,
        columna_fecha="FechaSolicitud",
    )


def leer_urgencias() -> pd.DataFrame:
    """
    Lee todas las urgencias comerciales.
    """

    return leer_tabla_google(
        nombre_hoja="Urgencias",
        columnas=COLUMNAS_URGENCIAS,
        columna_fecha="FechaSolicitud",
    )


def leer_anulaciones() -> pd.DataFrame:
    """
    Lee todas las solicitudes de anulación.
    """

    return leer_tabla_google(
        nombre_hoja="Anulaciones",
        columnas=COLUMNAS_ANULACIONES,
        columna_fecha="FechaSolicitud",
    )


def leer_reclamos() -> pd.DataFrame:
    """
    Lee todos los reclamos.
    """

    return leer_tabla_google(
        nombre_hoja="Reclamos",
        columnas=COLUMNAS_RECLAMOS,
        columna_fecha="FechaCreacion",
    )


def leer_reclamos_detalle() -> pd.DataFrame:
    """
    Lee los artículos asociados a los reclamos.
    """

    return leer_tabla_google(
        nombre_hoja="ReclamosDetalle",
        columnas=COLUMNAS_RECLAMOS_DETALLE,
    )


def leer_reclamos_fotos() -> pd.DataFrame:
    """
    Lee las fotos asociadas a los reclamos.
    """

    return leer_tabla_google(
        nombre_hoja="ReclamosFotos",
        columnas=COLUMNAS_RECLAMOS_FOTOS,
        columna_fecha="FechaCarga",
    )


def leer_toda_la_gestion() -> dict[
    str,
    pd.DataFrame,
]:
    """
    Devuelve toda la información del módulo.
    """

    return {
        "solicitudes": leer_solicitudes(),
        "urgencias": leer_urgencias(),
        "anulaciones": leer_anulaciones(),
        "reclamos": leer_reclamos(),
        "reclamos_detalle": (
            leer_reclamos_detalle()
        ),
        "reclamos_fotos": (
            leer_reclamos_fotos()
        ),
    }


# ==========================================================
# CONSULTAS POR PEDIDO
# ==========================================================

def filtrar_por_pedido(
    dataframe: pd.DataFrame,
    pedido: Any,
) -> pd.DataFrame:
    """
    Filtra una tabla por número de pedido.
    """

    pedido_normalizado = (
        normalizar_pedido(pedido)
    )

    if (
        dataframe.empty
        or not pedido_normalizado
    ):
        return dataframe.iloc[
            0:0
        ].copy()

    if "Pedido" not in dataframe.columns:

        return dataframe.iloc[
            0:0
        ].copy()

    mascara = (
        dataframe["Pedido"]
        .apply(normalizar_pedido)
        .eq(pedido_normalizado)
    )

    return (
        dataframe.loc[mascara]
        .copy()
        .reset_index(drop=True)
    )


def obtener_solicitudes_pedido(
    pedido: Any,
) -> pd.DataFrame:

    return filtrar_por_pedido(
        leer_solicitudes(),
        pedido,
    )


def obtener_urgencias_pedido(
    pedido: Any,
) -> pd.DataFrame:

    return filtrar_por_pedido(
        leer_urgencias(),
        pedido,
    )


def obtener_anulaciones_pedido(
    pedido: Any,
) -> pd.DataFrame:

    return filtrar_por_pedido(
        leer_anulaciones(),
        pedido,
    )


def obtener_reclamos_pedido(
    pedido: Any,
) -> pd.DataFrame:

    return filtrar_por_pedido(
        leer_reclamos(),
        pedido,
    )


def obtener_detalle_reclamo(
    reclamo_id: Any,
) -> pd.DataFrame:
    """
    Obtiene los artículos de un reclamo.
    """

    tabla = leer_reclamos_detalle()

    reclamo_buscado = str(
        reclamo_id or ""
    ).strip()

    if (
        tabla.empty
        or not reclamo_buscado
    ):
        return tabla.iloc[
            0:0
        ].copy()

    return (
        tabla.loc[
            tabla["ReclamoID"]
            .astype(str)
            .str.strip()
            .eq(reclamo_buscado)
        ]
        .copy()
        .reset_index(drop=True)
    )


def obtener_fotos_reclamo(
    reclamo_id: Any,
) -> pd.DataFrame:
    """
    Obtiene las fotos de un reclamo.
    """

    tabla = leer_reclamos_fotos()

    reclamo_buscado = str(
        reclamo_id or ""
    ).strip()

    if (
        tabla.empty
        or not reclamo_buscado
    ):
        return tabla.iloc[
            0:0
        ].copy()

    return (
        tabla.loc[
            tabla["ReclamoID"]
            .astype(str)
            .str.strip()
            .eq(reclamo_buscado)
        ]
        .copy()
        .reset_index(drop=True)
    )


# ==========================================================
# SOLICITUDES ABIERTAS
# ==========================================================

def obtener_solicitudes_abiertas(
) -> pd.DataFrame:
    """
    Devuelve solicitudes que todavía requieren gestión.
    """

    tabla = leer_solicitudes()

    if tabla.empty:
        return tabla

    estados_abiertos = {
        "PENDIENTE",
        "EN REVISIÓN",
        "EN REVISION",
        "EN CURSO",
        "EN GESTIÓN",
        "EN GESTION",
    }

    mascara = (
        tabla["EstadoSolicitud"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(estados_abiertos)
    )

    return (
        tabla.loc[mascara]
        .copy()
        .reset_index(drop=True)
    )


# ==========================================================
# URGENCIAS ACTIVAS
# ==========================================================

def obtener_urgencias_activas(
) -> pd.DataFrame:
    """
    Devuelve urgencias todavía activas.
    """

    tabla = leer_urgencias()

    if tabla.empty:
        return tabla

    estados_inactivos = {
        "FINALIZADA",
        "FINALIZADO",
        "CANCELADA",
        "CANCELADO",
        "RECHAZADA",
        "RECHAZADO",
        "AGRUPADA",
    }

    mascara = ~(
        tabla["EstadoUrgencia"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(estados_inactivos)
    )

    return (
        tabla.loc[mascara]
        .copy()
        .reset_index(drop=True)
    )


def pedido_tiene_urgencia_activa(
    pedido: Any,
) -> bool:

    return not filtrar_por_pedido(
        obtener_urgencias_activas(),
        pedido,
    ).empty


# ==========================================================
# ANULACIONES Y BLOQUEOS
# ==========================================================

def obtener_anulaciones_pendientes(
) -> pd.DataFrame:
    """
    Devuelve anulaciones que mantienen bloqueado el pedido.
    """

    tabla = leer_anulaciones()

    if tabla.empty:
        return tabla

    estados_pendientes = {
        "SOLICITADA",
        "EN REVISIÓN",
        "EN REVISION",
        "APROBADA",
    }

    mascara_estado = (
        tabla["EstadoAnulacion"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(estados_pendientes)
    )

    mascara_bloqueo = (
        tabla["BloqueoActivo"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({
            "SI",
            "SÍ",
            "TRUE",
            "1",
        })
    )

    return (
        tabla.loc[
            mascara_estado
            & mascara_bloqueo
        ]
        .copy()
        .reset_index(drop=True)
    )


def obtener_pedidos_bloqueados(
) -> set[str]:
    """
    Devuelve pedidos bloqueados por anulación.
    """

    tabla = (
        obtener_anulaciones_pendientes()
    )

    if tabla.empty:
        return set()

    return {
        pedido
        for pedido in (
            tabla["Pedido"]
            .apply(normalizar_pedido)
            .tolist()
        )
        if pedido
    }


def pedido_esta_bloqueado(
    pedido: Any,
) -> bool:

    return (
        normalizar_pedido(pedido)
        in obtener_pedidos_bloqueados()
    )


def obtener_motivo_bloqueo(
    pedido: Any,
) -> dict[str, str] | None:

    tabla = filtrar_por_pedido(
        obtener_anulaciones_pendientes(),
        pedido,
    )

    if tabla.empty:
        return None

    registro = tabla.iloc[0]

    return {
        "AnulacionID": str(
            registro.get(
                "AnulacionID",
                "",
            )
        ),
        "Pedido": str(
            registro.get(
                "Pedido",
                "",
            )
        ),
        "Motivo": str(
            registro.get(
                "Motivo",
                "",
            )
        ),
        "Descripcion": str(
            registro.get(
                "Descripcion",
                "",
            )
        ),
        "UsuarioSolicitante": str(
            registro.get(
                "UsuarioSolicitante",
                "",
            )
        ),
        "FechaSolicitud": str(
            registro.get(
                "FechaSolicitud",
                "",
            )
        ),
        "EstadoAnulacion": str(
            registro.get(
                "EstadoAnulacion",
                "",
            )
        ),
    }


# ==========================================================
# RECLAMOS ABIERTOS
# ==========================================================

def obtener_reclamos_abiertos(
) -> pd.DataFrame:
    """
    Devuelve reclamos que todavía no fueron cerrados.
    """

    tabla = leer_reclamos()

    if tabla.empty:
        return tabla

    estados_cerrados = {
        "RESUELTO",
        "RESUELTA",
        "CERRADO",
        "CERRADA",
        "CANCELADO",
        "CANCELADA",
    }

    mascara = ~(
        tabla["EstadoReclamo"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(estados_cerrados)
    )

    return (
        tabla.loc[mascara]
        .copy()
        .reset_index(drop=True)
    )


def pedido_tiene_reclamo_abierto(
    pedido: Any,
) -> bool:

    return not filtrar_por_pedido(
        obtener_reclamos_abiertos(),
        pedido,
    ).empty


# ==========================================================
# HISTORIAL DEL PEDIDO
# ==========================================================

def obtener_historial_pedido(
    pedido: Any,
) -> pd.DataFrame:
    """
    Consolida las gestiones registradas para un pedido.
    """

    pedido_normalizado = (
        normalizar_pedido(pedido)
    )

    registros: list[
        dict[str, Any]
    ] = []

    solicitudes = obtener_solicitudes_pedido(
        pedido_normalizado
    )

    for _, fila in solicitudes.iterrows():

        registros.append({
            "Fecha": fila.get(
                "FechaSolicitud",
                "",
            ),
            "TipoGestion": "Solicitud",
            "IDGestion": fila.get(
                "SolicitudID",
                "",
            ),
            "Estado": fila.get(
                "EstadoSolicitud",
                "",
            ),
            "Detalle": fila.get(
                "Descripcion",
                "",
            ),
            "Usuario": fila.get(
                "UsuarioSolicitante",
                "",
            ),
        })

    urgencias = obtener_urgencias_pedido(
        pedido_normalizado
    )

    for _, fila in urgencias.iterrows():

        registros.append({
            "Fecha": fila.get(
                "FechaSolicitud",
                "",
            ),
            "TipoGestion": "Urgencia",
            "IDGestion": fila.get(
                "UrgenciaID",
                "",
            ),
            "Estado": fila.get(
                "EstadoUrgencia",
                "",
            ),
            "Detalle": fila.get(
                "Motivo",
                "",
            ),
            "Usuario": fila.get(
                "UsuarioSolicitante",
                "",
            ),
        })

    anulaciones = obtener_anulaciones_pedido(
        pedido_normalizado
    )

    for _, fila in anulaciones.iterrows():

        registros.append({
            "Fecha": fila.get(
                "FechaSolicitud",
                "",
            ),
            "TipoGestion": "Anulación",
            "IDGestion": fila.get(
                "AnulacionID",
                "",
            ),
            "Estado": fila.get(
                "EstadoAnulacion",
                "",
            ),
            "Detalle": fila.get(
                "Motivo",
                "",
            ),
            "Usuario": fila.get(
                "UsuarioSolicitante",
                "",
            ),
        })

    reclamos = obtener_reclamos_pedido(
        pedido_normalizado
    )

    for _, fila in reclamos.iterrows():

        registros.append({
            "Fecha": fila.get(
                "FechaCreacion",
                "",
            ),
            "TipoGestion": "Reclamo",
            "IDGestion": fila.get(
                "ReclamoID",
                "",
            ),
            "Estado": fila.get(
                "EstadoReclamo",
                "",
            ),
            "Detalle": fila.get(
                "Descripcion",
                "",
            ),
            "Usuario": fila.get(
                "UsuarioCreador",
                "",
            ),
        })

    columnas_historial = [
        "Fecha",
        "TipoGestion",
        "IDGestion",
        "Estado",
        "Detalle",
        "Usuario",
    ]

    if not registros:

        return pd.DataFrame(
            columns=columnas_historial
        )

    historial = pd.DataFrame(
        registros
    )

    historial["_FechaOrden"] = (
        pd.to_datetime(
            historial["Fecha"],
            errors="coerce",
        )
    )

    return (
        historial
        .sort_values(
            "_FechaOrden",
            ascending=False,
            na_position="last",
        )
        .drop(
            columns=["_FechaOrden"]
        )
        .reset_index(drop=True)
    )


# ==========================================================
# RESUMEN GENERAL
# ==========================================================

def obtener_resumen_gestion(
) -> dict[str, int]:
    """
    Devuelve los indicadores principales del módulo.
    """

    solicitudes_abiertas = (
        obtener_solicitudes_abiertas()
    )

    urgencias_activas = (
        obtener_urgencias_activas()
    )

    anulaciones_pendientes = (
        obtener_anulaciones_pendientes()
    )

    reclamos_abiertos = (
        obtener_reclamos_abiertos()
    )

    return {
        "SolicitudesAbiertas": len(
            solicitudes_abiertas
        ),
        "UrgenciasActivas": len(
            urgencias_activas
        ),
        "AnulacionesPendientes": len(
            anulaciones_pendientes
        ),
        "ReclamosAbiertos": len(
            reclamos_abiertos
        ),
        "PedidosBloqueados": len(
            obtener_pedidos_bloqueados()
        ),
    }