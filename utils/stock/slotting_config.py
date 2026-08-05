
from __future__ import annotations

import pandas as pd


# ==========================================================
# BLOQUES FÍSICOS DEL DEPÓSITO
# ==========================================================
#
# Estos rangos son una referencia inicial basada en el layout
# compartido. Se pueden corregir sin tocar el modelo.
#
# Cuando un área se repite o comparte pasillos con otra, se
# puede crear más de una fila para la misma ÁreaPicking.
#
BLOQUES_PASILLOS = [
    {
        "AreaPicking": "NACIONAL",
        "PasilloDesde": 16,
        "PasilloHasta": 19,
        "Bloque": "NACIONAL",
    },
    {
        "AreaPicking": "BACHAS",
        "PasilloDesde": 16,
        "PasilloHasta": 17,
        "Bloque": "BACHAS",
    },
    {
        "AreaPicking": "IMPORTADO",
        "PasilloDesde": 10,
        "PasilloHasta": 15,
        "Bloque": "IMPORTADO",
    },
    {
        "AreaPicking": "BLISTER",
        "PasilloDesde": 8,
        "PasilloHasta": 9,
        "Bloque": "BLISTER",
    },
    {
        "AreaPicking": "SANITARIOS",
        "PasilloDesde": 4,
        "PasilloHasta": 7,
        "Bloque": "SANITARIOS",
    },
    {
        "AreaPicking": "ALMACEN",
        "PasilloDesde": 1,
        "PasilloHasta": 3,
        "Bloque": "ALMACEN",
    },
]


# Cantidad de pasillos que se consideran "cercanos"
# respecto del pasillo principal del picking.
RADIO_PASILLOS_CERCANOS = 1


# Umbrales iniciales del diagnóstico de dispersión.
UMBRAL_PASILLOS_NORMAL = 3
UMBRAL_PASILLOS_ALTO = 4


# Distancia usada en el score.
DISTANCIA_REVISION = 4
DISTANCIA_CRITICA = 8


def tabla_bloques_pasillos() -> pd.DataFrame:
    tabla = pd.DataFrame(BLOQUES_PASILLOS)

    if tabla.empty:
        return pd.DataFrame(
            columns=[
                "AreaPicking",
                "PasilloDesde",
                "PasilloHasta",
                "Bloque",
            ]
        )

    tabla["AreaPicking"] = (
        tabla["AreaPicking"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    tabla["Bloque"] = (
        tabla["Bloque"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    tabla["PasilloDesde"] = pd.to_numeric(
        tabla["PasilloDesde"],
        errors="coerce",
    ).fillna(0).astype(int)
    tabla["PasilloHasta"] = pd.to_numeric(
        tabla["PasilloHasta"],
        errors="coerce",
    ).fillna(0).astype(int)

    return tabla
