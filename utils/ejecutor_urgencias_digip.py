# utils/ejecutor_urgencias_digip.py

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


DESPACHO_DESTINO = "URGENTES"
TIPO_PREPARACION = "PEDIDO"


def normalizar_pedidos(
    pedidos: Iterable[Any],
) -> list[str]:
    resultado = []

    for valor in pedidos:
        pedido = str(valor).strip()

        if pedido.endswith(".0"):
            pedido = pedido[:-2]

        pedido = pedido.split("-")[0]

        if pedido and pedido not in resultado:
            resultado.append(pedido)

    return resultado


def ejecutar_agrupacion_urgentes(
    pedidos: Iterable[Any],
    *,
    funcion_agrupacion: Callable | None = None,
) -> dict:
    """
    Ejecuta todos los pedidos en un único lote con destino URGENTES.

    La función real del robot debe aceptar, idealmente:

        funcion_agrupacion(
            pedidos=[...],
            despacho_destino="URGENTES",
            tipo_preparacion="PEDIDO",
        )

    También se admite una función que reciba argumentos posicionales:

        funcion_agrupacion(
            [...],
            "URGENTES",
            "PEDIDO",
        )

    Este adaptador no contiene selectores de Playwright porque deben
    reutilizarse los selectores del ejecutor de camionetas que ya está
    validado en el proyecto.
    """

    pedidos_limpios = normalizar_pedidos(
        pedidos
    )

    if not pedidos_limpios:
        raise ValueError(
            "No hay pedidos pendientes para agrupar."
        )

    if funcion_agrupacion is None:
        raise RuntimeError(
            "Falta conectar la función real del ejecutor DIGIP. "
            "Importá en pages/08_Consultas.py la misma función "
            "que hoy ejecuta las camionetas y pasala como "
            "funcion_agrupacion."
        )

    try:
        resultado = funcion_agrupacion(
            pedidos=pedidos_limpios,
            despacho_destino=DESPACHO_DESTINO,
            tipo_preparacion=TIPO_PREPARACION,
        )

    except TypeError:
        resultado = funcion_agrupacion(
            pedidos_limpios,
            DESPACHO_DESTINO,
            TIPO_PREPARACION,
        )

    if resultado is False:
        raise RuntimeError(
            "El ejecutor DIGIP informó que la agrupación falló."
        )

    if isinstance(resultado, dict):
        if resultado.get("ok") is False:
            raise RuntimeError(
                str(
                    resultado.get(
                        "mensaje",
                        "La agrupación DIGIP falló.",
                    )
                )
            )

        mensaje = str(
            resultado.get(
                "mensaje",
                "Pedidos agrupados correctamente.",
            )
        )

    else:
        mensaje = (
            "Pedidos agrupados correctamente "
            "en el despacho URGENTES."
        )

    return {
        "ok": True,
        "pedidos": pedidos_limpios,
        "cantidad": len(pedidos_limpios),
        "despacho_destino": DESPACHO_DESTINO,
        "tipo_preparacion": TIPO_PREPARACION,
        "mensaje": mensaje,
    }
