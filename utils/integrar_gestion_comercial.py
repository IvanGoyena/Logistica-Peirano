
from __future__ import annotations

import pandas as pd

from utils.leer_gestion_consultas import (
    leer_solicitudes,
    leer_urgencias,
    leer_anulaciones,
    leer_reclamos,
)


# ==========================================================
# NORMALIZACIÓN
# ==========================================================

def normalizar_pedido(valor):

    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


# ==========================================================
# CONTADORES
# ==========================================================

def contar_registros(df, columna_estado=None, estados_excluir=None):

    if df.empty:
        return {}

    tabla = df.copy()

    if columna_estado:

        estados_excluir = estados_excluir or []

        tabla = tabla[
            ~tabla[columna_estado]
            .astype(str)
            .str.upper()
            .isin(
                [x.upper() for x in estados_excluir]
            )
        ]

    return (
        tabla
        .groupby("Pedido")
        .size()
        .to_dict()
    )


# ==========================================================
# PEDIDOS BLOQUEADOS
# ==========================================================

def obtener_bloqueos(df_anulaciones):

    if df_anulaciones.empty:
        return set()

    tabla = df_anulaciones.copy()

    tabla = tabla[
        tabla["BloqueoActivo"]
        .astype(str)
        .str.upper()
        .isin(
            [
                "SI",
                "SÍ",
                "TRUE",
                "1"
            ]
        )
    ]

    return set(tabla["Pedido"])


# ==========================================================
# URGENCIAS
# ==========================================================

def obtener_urgencias(df_urgencias):

    if df_urgencias.empty:
        return set()

    tabla = df_urgencias.copy()

    tabla = tabla[
        ~tabla["EstadoUrgencia"]
        .astype(str)
        .str.upper()
        .isin(
            [
                "FINALIZADA",
                "FINALIZADO",
                "CANCELADA",
                "CANCELADO"
            ]
        )
    ]

    return set(tabla["Pedido"])


# ==========================================================
# TABLA OPERATIVA
# ==========================================================

def integrar_gestion_comercial(
    df_operativo,
):

    tabla = df_operativo.copy()

    tabla["Pedido"] = (
        tabla["Pedido"]
        .apply(normalizar_pedido)
    )

    solicitudes = leer_solicitudes()

    urgencias = leer_urgencias()

    anulaciones = leer_anulaciones()

    reclamos = leer_reclamos()

    for df in [
        solicitudes,
        urgencias,
        anulaciones,
        reclamos,
    ]:

        if not df.empty:

            df["Pedido"] = (
                df["Pedido"]
                .apply(normalizar_pedido)
            )

    # ===========================================
    # Cantidad solicitudes
    # ===========================================

    solicitudes_abiertas = contar_registros(
        solicitudes,
        "EstadoSolicitud",
        [
            "RESUELTA",
            "FINALIZADA",
            "CERRADA",
            "RECHAZADA",
        ]
    )

    # ===========================================
    # Reclamos
    # ===========================================

    reclamos_abiertos = contar_registros(
        reclamos,
        "EstadoReclamo",
        [
            "RESUELTO",
            "CERRADO",
            "FINALIZADO",
        ]
    )

    # ===========================================
    # Urgencias
    # ===========================================

    urgencias_activas = obtener_urgencias(
        urgencias
    )

    # ===========================================
    # Bloqueos
    # ===========================================

    pedidos_bloqueados = obtener_bloqueos(
        anulaciones
    )

    # ===========================================
    # Nuevas columnas
    # ===========================================

    tabla["SolicitudesAbiertas"] = (
        tabla["Pedido"]
        .map(solicitudes_abiertas)
        .fillna(0)
        .astype(int)
    )

    tabla["ReclamosAbiertos"] = (
        tabla["Pedido"]
        .map(reclamos_abiertos)
        .fillna(0)
        .astype(int)
    )

    tabla["UrgenciaActiva"] = (
        tabla["Pedido"]
        .isin(urgencias_activas)
    )

    tabla["BloqueoActivo"] = (
        tabla["Pedido"]
        .isin(pedidos_bloqueados)
    )

    tabla["CantidadGestiones"] = (
        tabla["SolicitudesAbiertas"]
        +
        tabla["ReclamosAbiertos"]
    )

    tabla["TieneGestion"] = (
        tabla["CantidadGestiones"] > 0
    )

    return tabla