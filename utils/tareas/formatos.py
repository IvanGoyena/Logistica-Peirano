from __future__ import annotations

import pandas as pd


def preparar_tabla_operativa_visual(tabla: pd.DataFrame) -> pd.DataFrame:
    visual = tabla.copy()

    for columna in ["Unidades", "SKUs"]:
        if columna in visual.columns:
            visual[columna] = pd.to_numeric(
                visual[columna], errors="coerce"
            ).fillna(0).astype("int64")

    for columna in [
        "Prioridad", "Carro", "Cliente", "Despacho", "Hora",
        "Usuario", "Estado", "Familias",
    ]:
        if columna in visual.columns:
            visual[columna] = visual[columna].fillna("").astype(str)

    columnas = [
        "Prioridad", "Carro", "Cliente", "Unidades", "SKUs",
        "Despacho", "Hora", "Usuario", "Estado", "Familias",
    ]
    return visual[[c for c in columnas if c in visual.columns]].copy()


def resaltar_carro(fila: pd.Series) -> list[str]:
    estilos = [""] * len(fila)
    if "Carro" not in fila.index:
        return estilos

    indice = fila.index.get_loc("Carro")
    if fila.get("Prioridad") == "🔴":
        estilos[indice] = "background-color:#991B1B;color:white;font-weight:700;"
    elif fila.get("Prioridad") == "🟠":
        estilos[indice] = "background-color:#9A3412;color:white;font-weight:700;"
    return estilos
