from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from utils.google_sheets import (
    agregar_registro,
    actualizar_registro,
    asegurar_hoja,
    leer_hoja,
)


NOMBRE_HOJA = "CoberturaInformados"

COLUMNAS = [
    "Pedido",
    "FechaInformado",
    "Usuario",
    "Estado",
]


def _normalizar_pedido(valor: object) -> str:
    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def leer_pedidos_informados() -> pd.DataFrame:
    try:
        # La pestaña puede no existir todavía en una planilla ya creada.
        # Se asegura su existencia antes de intentar leer el rango.
        asegurar_hoja(NOMBRE_HOJA)

        datos = leer_hoja(
            nombre_hoja=NOMBRE_HOJA,
            columnas=COLUMNAS,
        )
    except Exception:
        return pd.DataFrame(columns=COLUMNAS)

    for columna in COLUMNAS:
        if columna not in datos.columns:
            datos[columna] = ""

    datos = datos[COLUMNAS].copy()
    datos["Pedido"] = datos["Pedido"].map(_normalizar_pedido)
    datos["Estado"] = (
        datos["Estado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return (
        datos.loc[datos["Pedido"].ne("")]
        .drop_duplicates(
            subset=["Pedido"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def obtener_pedidos_informados() -> set[str]:
    datos = leer_pedidos_informados()

    return set(
        datos.loc[
            datos["Estado"].eq("INFORMADO"),
            "Pedido",
        ].tolist()
    )


def _guardar_estado_pedido(
    pedido: str,
    estado: str,
    usuario: str,
) -> None:
    # Asegura la pestaña también antes de escribir, por si la app
    # todavía no ejecutó la inicialización general de la planilla.
    asegurar_hoja(NOMBRE_HOJA)

    pedido_normalizado = _normalizar_pedido(pedido)

    if not pedido_normalizado:
        return

    registro = {
        "Pedido": pedido_normalizado,
        "FechaInformado": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "Usuario": str(usuario or "").strip() or "Sin identificar",
        "Estado": str(estado).strip().upper(),
    }

    existentes = leer_pedidos_informados()

    if (
        not existentes.empty
        and pedido_normalizado
        in set(existentes["Pedido"].tolist())
    ):
        actualizar_registro(
            nombre_hoja=NOMBRE_HOJA,
            columna_id="Pedido",
            valor_id=pedido_normalizado,
            cambios={
                "FechaInformado": registro["FechaInformado"],
                "Usuario": registro["Usuario"],
                "Estado": registro["Estado"],
            },
        )
    else:
        agregar_registro(
            nombre_hoja=NOMBRE_HOJA,
            registro=registro,
        )


def marcar_pedidos_informados(
    pedidos: Iterable[object],
    usuario: str = "",
) -> pd.DataFrame:
    pedidos_normalizados = list(
        dict.fromkeys(
            pedido
            for pedido in (
                _normalizar_pedido(valor)
                for valor in pedidos
            )
            if pedido
        )
    )

    if not pedidos_normalizados:
        raise ValueError(
            "No se recibieron pedidos para marcar como informados."
        )

    for pedido in pedidos_normalizados:
        _guardar_estado_pedido(
            pedido=pedido,
            estado="INFORMADO",
            usuario=usuario,
        )

    return leer_pedidos_informados()


def reabrir_pedidos_informados(
    pedidos: Iterable[object],
    usuario: str = "",
) -> pd.DataFrame:
    pedidos_normalizados = list(
        dict.fromkeys(
            pedido
            for pedido in (
                _normalizar_pedido(valor)
                for valor in pedidos
            )
            if pedido
        )
    )

    if not pedidos_normalizados:
        raise ValueError(
            "No se recibieron pedidos para volver a mostrar."
        )

    for pedido in pedidos_normalizados:
        _guardar_estado_pedido(
            pedido=pedido,
            estado="REABIERTO",
            usuario=usuario,
        )

    return leer_pedidos_informados()
