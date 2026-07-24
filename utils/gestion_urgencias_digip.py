# utils/gestion_urgencias_digip.py

from __future__ import annotations

from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd

from utils.google_sheets import (
    actualizar_registro,
)

from utils.leer_gestion_consultas import (
    leer_urgencias,
)


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

ZONA_HORARIA = ZoneInfo(
    "America/Argentina/Buenos_Aires"
)


# ==========================================================
# FUNCIONES GENERALES
# ==========================================================

def normalizar_pedido(
    valor,
) -> str:
    """
    Normaliza números de pedido y transmisiones.
    """

    if valor is None:
        return ""

    pedido = str(valor).strip()

    if pedido.endswith(".0"):
        pedido = pedido[:-2]

    return pedido.split("-")[0].strip()


def obtener_fecha_hora() -> str:
    """
    Devuelve fecha y hora de Argentina.
    """

    return datetime.now(
        ZONA_HORARIA
    ).strftime("%Y-%m-%d %H:%M:%S")


# ==========================================================
# URGENCIAS PENDIENTES
# ==========================================================

def obtener_urgencias_pendientes_digip(
) -> pd.DataFrame:
    """
    Obtiene las urgencias que todavía deben ejecutarse
    en DIGIP.
    """

    tabla = leer_urgencias()

    if tabla is None or tabla.empty:
        return pd.DataFrame()

    columnas_requeridas = {
        "UrgenciaID",
        "Pedido",
        "EstadoUrgencia",
        "EstadoEjecucionDIGIP",
        "FechaSolicitud",
    }

    faltantes = (
        columnas_requeridas
        - set(tabla.columns)
    )

    if faltantes:
        raise ValueError(
            "La hoja Urgencias no contiene "
            "las columnas requeridas: "
            f"{sorted(faltantes)}"
        )

    tabla = tabla.copy()

    tabla["Pedido"] = (
        tabla["Pedido"]
        .fillna("")
        .apply(normalizar_pedido)
    )

    estado_urgencia = (
        tabla["EstadoUrgencia"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    estado_ejecucion = (
        tabla["EstadoEjecucionDIGIP"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    mascara = (
        estado_urgencia.isin({
            "PENDIENTE",
            "ACTIVA",
            "ERROR",
        })
        &
        estado_ejecucion.isin({
            "",
            "PENDIENTE",
            "ERROR",
        })
    )

    pendientes = tabla.loc[
        mascara
    ].copy()

    if pendientes.empty:
        return pendientes

    pendientes[
        "FechaSolicitudOrden"
    ] = pd.to_datetime(
        pendientes["FechaSolicitud"],
        errors="coerce",
    )

    pendientes = (
        pendientes
        .sort_values(
            "FechaSolicitudOrden",
            ascending=True,
            na_position="last",
        )
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .drop(
            columns=["FechaSolicitudOrden"]
        )
        .reset_index(drop=True)
    )

    return pendientes


def obtener_pedidos_pendientes_digip(
) -> list[str]:
    """
    Devuelve los números de los pedidos pendientes.
    """

    pendientes = (
        obtener_urgencias_pendientes_digip()
    )

    if pendientes.empty:
        return []

    pedidos = (
        pendientes["Pedido"]
        .fillna("")
        .apply(normalizar_pedido)
        .tolist()
    )

    return [
        pedido
        for pedido in pedidos
        if pedido
    ]


# ==========================================================
# ACTUALIZACIÓN DE ESTADOS
# ==========================================================

def actualizar_estado_lote(
    pedidos: Iterable[str],
    *,
    estado_urgencia: str,
    estado_ejecucion: str,
    mensaje: str = "",
    registrar_fecha_ejecucion: bool = False,
) -> int:
    """
    Actualiza en Google Sheets todas las urgencias
    correspondientes a los pedidos indicados.
    """

    pedidos_normalizados = {
        normalizar_pedido(pedido)
        for pedido in pedidos
        if normalizar_pedido(pedido)
    }

    if not pedidos_normalizados:
        return 0

    tabla = leer_urgencias()

    if tabla is None or tabla.empty:
        return 0

    if "UrgenciaID" not in tabla.columns:
        raise ValueError(
            "La hoja Urgencias no contiene "
            "la columna UrgenciaID."
        )

    if "Pedido" not in tabla.columns:
        raise ValueError(
            "La hoja Urgencias no contiene "
            "la columna Pedido."
        )

    tabla = tabla.copy()

    tabla["PedidoNormalizado"] = (
        tabla["Pedido"]
        .fillna("")
        .apply(normalizar_pedido)
    )

    coincidencias = tabla.loc[
        tabla["PedidoNormalizado"].isin(
            pedidos_normalizados
        )
    ].copy()

    if coincidencias.empty:
        return 0

    fecha_ejecucion = (
        obtener_fecha_hora()
        if registrar_fecha_ejecucion
        else None
    )

    cantidad_actualizada = 0

    for _, registro in coincidencias.iterrows():

        urgencia_id = str(
            registro.get(
                "UrgenciaID",
                "",
            )
        ).strip()

        if not urgencia_id:
            continue

        cambios = {
            "EstadoUrgencia": estado_urgencia,
            "EstadoEjecucionDIGIP": (
                estado_ejecucion
            ),
            "MensajeEjecucionDIGIP": str(
                mensaje
            ),
        }

        if fecha_ejecucion is not None:
            cambios[
                "FechaEjecucionDIGIP"
            ] = fecha_ejecucion

        actualizar_registro(
            nombre_hoja="Urgencias",
            columna_id="UrgenciaID",
            valor_id=urgencia_id,
            cambios=cambios,
        )

        cantidad_actualizada += 1

    return cantidad_actualizada


def marcar_lote_procesando(
    pedidos: Iterable[str],
) -> int:
    """
    Marca las urgencias como procesando.
    """

    return actualizar_estado_lote(
        pedidos,
        estado_urgencia="Procesando",
        estado_ejecucion="Procesando",
        mensaje="Ejecución iniciada.",
    )


def marcar_lote_exitoso(
    pedidos: Iterable[str],
    mensaje: str = (
        "Pedidos agrupados correctamente "
        "en el despacho URGENTES."
    ),
) -> int:
    """
    Marca las urgencias como agrupadas correctamente.
    """

    return actualizar_estado_lote(
        pedidos,
        estado_urgencia="Agrupada",
        estado_ejecucion="Exitoso",
        mensaje=mensaje,
        registrar_fecha_ejecucion=True,
    )


def marcar_lote_error(
    pedidos: Iterable[str],
    mensaje: str,
) -> int:
    """
    Registra el error y deja la urgencia disponible
    para volver a intentar.
    """

    return actualizar_estado_lote(
        pedidos,
        estado_urgencia="Pendiente",
        estado_ejecucion="Error",
        mensaje=str(mensaje),
        registrar_fecha_ejecucion=True,
    )