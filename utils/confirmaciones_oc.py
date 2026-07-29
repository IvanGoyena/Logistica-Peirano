from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from utils.google_sheets import (
    agregar_registro,
    actualizar_registro,
    eliminar_registro,
    leer_hoja,
)


NOMBRE_HOJA = "ConfirmacionesIngresoOC"
COLUMNAS_CONFIRMACIONES = [
    "OrdenCompra",
    "FechaConfirmadaIngreso",
    "UsuarioConfirmacion",
    "FechaRegistro",
]


def normalizar_orden_compra(valor: object) -> str:
    texto = "" if valor is None else str(valor).strip()
    return re.sub(r"\.0$", "", texto)


def normalizar_confirmaciones(dataframe: pd.DataFrame | None) -> pd.DataFrame:
    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=COLUMNAS_CONFIRMACIONES)

    tabla = dataframe.copy()

    for columna in COLUMNAS_CONFIRMACIONES:
        if columna not in tabla.columns:
            tabla[columna] = ""

    tabla["OrdenCompra"] = tabla["OrdenCompra"].map(normalizar_orden_compra)
    tabla["FechaConfirmadaIngreso"] = pd.to_datetime(
        tabla["FechaConfirmadaIngreso"],
        errors="coerce",
        dayfirst=True,
    )
    tabla["FechaRegistro"] = pd.to_datetime(
        tabla["FechaRegistro"],
        errors="coerce",
        dayfirst=True,
    )
    tabla["UsuarioConfirmacion"] = (
        tabla["UsuarioConfirmacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return (
        tabla.loc[
            tabla["OrdenCompra"].ne("")
            & tabla["FechaConfirmadaIngreso"].notna(),
            COLUMNAS_CONFIRMACIONES,
        ]
        .sort_values(
            ["OrdenCompra", "FechaRegistro"],
            ascending=[True, False],
        )
        .drop_duplicates("OrdenCompra", keep="first")
        .reset_index(drop=True)
    )


def leer_confirmaciones_oc(*_args, **_kwargs) -> pd.DataFrame:
    """Lee confirmaciones desde la hoja central de Google Sheets."""
    try:
        return normalizar_confirmaciones(
            leer_hoja(NOMBRE_HOJA)
        )
    except Exception:
        return pd.DataFrame(columns=COLUMNAS_CONFIRMACIONES)


def aplicar_confirmaciones_oc(
    tabla_oc: pd.DataFrame,
    confirmaciones: pd.DataFrame,
) -> pd.DataFrame:
    if tabla_oc is None or tabla_oc.empty:
        return (
            tabla_oc.copy()
            if isinstance(tabla_oc, pd.DataFrame)
            else pd.DataFrame()
        )

    tabla = tabla_oc.copy()
    tabla["OrdenCompra"] = tabla["OrdenCompra"].map(
        normalizar_orden_compra
    )
    confirmadas = normalizar_confirmaciones(confirmaciones)

    tabla = tabla.merge(
        confirmadas[COLUMNAS_CONFIRMACIONES],
        on="OrdenCompra",
        how="left",
        validate="many_to_one",
    )

    fecha_estimada = pd.to_datetime(
        tabla.get("FechaIngresoEstimada"),
        errors="coerce",
    )
    fecha_confirmada = pd.to_datetime(
        tabla["FechaConfirmadaIngreso"],
        errors="coerce",
    )

    tabla["FechaOperativaIngreso"] = fecha_confirmada.fillna(
        fecha_estimada
    )
    tabla["TipoFechaIngreso"] = "Sin fecha"
    tabla.loc[
        fecha_estimada.notna(),
        "TipoFechaIngreso",
    ] = "Estimada"
    tabla.loc[
        fecha_confirmada.notna(),
        "TipoFechaIngreso",
    ] = "Confirmada"
    tabla["EstadoFechaIngreso"] = tabla["TipoFechaIngreso"].map(
        {
            "Confirmada": "🟢 Confirmada",
            "Estimada": "🟡 Estimada",
            "Sin fecha": "⚪ Sin fecha",
        }
    )
    return tabla


def guardar_confirmaciones_oc(
    _carpeta_datos: str,
    ordenes_compra: Iterable[object],
    fecha_confirmada: date | datetime | str,
    usuario: str = "",
) -> dict:
    """Crea o actualiza una confirmación por OC en Google Sheets."""
    ordenes = sorted(
        {
            normalizar_orden_compra(valor)
            for valor in ordenes_compra
            if normalizar_orden_compra(valor)
        }
    )
    if not ordenes:
        raise ValueError("Seleccioná al menos una orden de compra.")

    fecha = pd.to_datetime(fecha_confirmada, errors="coerce")
    if pd.isna(fecha):
        raise ValueError("La fecha confirmada no es válida.")

    actuales = leer_confirmaciones_oc()
    existentes = set(actuales["OrdenCompra"].tolist())
    ahora = pd.Timestamp.now().floor("s")

    for orden in ordenes:
        registro = {
            "OrdenCompra": orden,
            "FechaConfirmadaIngreso": fecha.strftime("%d/%m/%Y"),
            "UsuarioConfirmacion": str(usuario or "").strip(),
            "FechaRegistro": ahora.strftime("%d/%m/%Y %H:%M:%S"),
        }

        if orden in existentes:
            actualizar_registro(
                nombre_hoja=NOMBRE_HOJA,
                columna_id="OrdenCompra",
                valor_id=orden,
                cambios={
                    "FechaConfirmadaIngreso": registro[
                        "FechaConfirmadaIngreso"
                    ],
                    "UsuarioConfirmacion": registro[
                        "UsuarioConfirmacion"
                    ],
                    "FechaRegistro": registro["FechaRegistro"],
                },
            )
        else:
            agregar_registro(
                nombre_hoja=NOMBRE_HOJA,
                registro=registro,
            )

    return {
        "cantidad": len(ordenes),
        "ordenes": ordenes,
        "fecha": fecha.date(),
        "destino": NOMBRE_HOJA,
        "modo": "Google Sheets",
    }


def eliminar_confirmaciones_oc(
    _carpeta_datos: str,
    ordenes_compra: Iterable[object],
) -> dict:
    """Elimina las confirmaciones seleccionadas de Google Sheets."""
    ordenes = sorted(
        {
            normalizar_orden_compra(valor)
            for valor in ordenes_compra
            if normalizar_orden_compra(valor)
        }
    )

    actuales = leer_confirmaciones_oc()
    existentes = set(actuales["OrdenCompra"].tolist())
    eliminadas = 0

    for orden in ordenes:
        if orden not in existentes:
            continue
        eliminar_registro(
            nombre_hoja=NOMBRE_HOJA,
            columna_id="OrdenCompra",
            valor_id=orden,
        )
        eliminadas += 1

    return {
        "cantidad": eliminadas,
        "ordenes": ordenes,
        "destino": NOMBRE_HOJA,
        "modo": "Google Sheets",
    }
