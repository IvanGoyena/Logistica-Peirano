from __future__ import annotations

import pandas as pd

from utils.consultas.leer_gestion_consultas import (
    obtener_solicitudes_abiertas,
    obtener_urgencias_activas,
    obtener_anulaciones_pendientes,
    obtener_reclamos_abiertos,
)
from utils.consultas.gestion_consultas import (
    finalizar_solicitud_automaticamente,
)


def normalizar_pedido_gestion(valor: object) -> str:
    texto = str(valor or "").strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def normalizar_pedido_wms_desde_codigo(valor: object) -> str:
    """
    Obtiene la clave de pedido utilizada por las gestiones desde
    el cÃ³digo completo informado por Pedidos DIGIP.

    Ejemplo:
        9999 70-1 -> 70
    """

    texto = str(valor or "").strip()

    if not texto:
        return ""

    partes = texto.split()

    if len(partes) >= 2:
        texto = partes[1]

    return texto.split("-")[0].strip()


def obtener_bloqueos_gestiones() -> tuple[
    set[str],
    dict[str, set[str]],
]:
    """
    Devuelve los pedidos que no pueden entrar al planificador porque
    poseen una gestiÃ³n comercial abierta.
    """

    reclamos_abiertos = obtener_reclamos_abiertos()

    if reclamos_abiertos is None:
        reclamos_abiertos = pd.DataFrame()

    gestiones = {
        "Solicitud": obtener_solicitudes_abiertas(),
        "Urgencia": obtener_urgencias_activas(),
        "AnulaciÃ³n": obtener_anulaciones_pendientes(),
        "Reclamo": reclamos_abiertos,
    }

    pedidos_por_gestion: dict[str, set[str]] = {}
    pedidos_bloqueados: set[str] = set()

    for tipo_gestion, dataframe in gestiones.items():

        if dataframe is None or dataframe.empty:
            pedidos_por_gestion[tipo_gestion] = set()
            continue

        if "Pedido" not in dataframe.columns:
            pedidos_por_gestion[tipo_gestion] = set()
            continue

        pedidos = set(
            dataframe["Pedido"]
            .apply(normalizar_pedido_gestion)
            .loc[lambda serie: serie.ne("")]
            .tolist()
        )

        pedidos_por_gestion[tipo_gestion] = pedidos
        pedidos_bloqueados.update(pedidos)

    return pedidos_bloqueados, pedidos_por_gestion


def cerrar_solicitudes_resueltas(
    df_pedidos: pd.DataFrame,
) -> int:
    """
    Finaliza solicitudes abiertas cuando el pedido:
    - pasÃ³ a COMPLETO en DIGIP; o
    - dejÃ³ de existir en el reporte actual de Pedidos DIGIP.

    Devuelve la cantidad de solicitudes cerradas.
    """

    solicitudes_abiertas = obtener_solicitudes_abiertas()

    if (
        solicitudes_abiertas is None
        or solicitudes_abiertas.empty
        or df_pedidos is None
        or df_pedidos.empty
        or "Codigo" not in df_pedidos.columns
    ):
        return 0

    pedidos_crudo = df_pedidos.copy()

    pedidos_crudo["PedidoGestion"] = (
        pedidos_crudo["Codigo"]
        .apply(normalizar_pedido_wms_desde_codigo)
    )

    pedidos_crudo["EstadoGestion"] = (
        pedidos_crudo.get(
            "Estado",
            pd.Series("", index=pedidos_crudo.index),
        )
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    pedidos_presentes = set(
        pedidos_crudo["PedidoGestion"]
        .loc[lambda serie: serie.ne("")]
        .tolist()
    )

    pedidos_completos = set(
        pedidos_crudo.loc[
            pedidos_crudo["EstadoGestion"].eq("COMPLETO"),
            "PedidoGestion",
        ].tolist()
    )

    cantidad_cerradas = 0

    for _, solicitud in solicitudes_abiertas.iterrows():

        solicitud_id = str(
            solicitud.get("SolicitudID", "")
        ).strip()

        pedido_solicitud = normalizar_pedido_gestion(
            solicitud.get("Pedido", "")
        )

        motivo_cierre = ""

        if pedido_solicitud in pedidos_completos:
            motivo_cierre = (
                "GestiÃ³n cerrada automÃ¡ticamente porque "
                "el pedido pasÃ³ al estado Completo en DIGIP."
            )

        elif (
            pedido_solicitud
            and pedido_solicitud not in pedidos_presentes
        ):
            motivo_cierre = (
                "GestiÃ³n cerrada automÃ¡ticamente porque "
                "el pedido ya no figura en el reporte actual "
                "de Pedidos DIGIP."
            )

        if solicitud_id and motivo_cierre:
            finalizar_solicitud_automaticamente(
                solicitud_id=solicitud_id,
                motivo=motivo_cierre,
            )
            cantidad_cerradas += 1

    return cantidad_cerradas

