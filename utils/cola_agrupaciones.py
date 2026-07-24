from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

try:
    import streamlit as st
except ImportError:
    st = None


SPREADSHEET_ID = "1OHWMhUFjnm9IEtOIjNswXZlevgAwt74f2fqYzHFcDBQ"
NOMBRE_HOJA = "ColaAgrupaciones"
RUTA_JSON = Path("config/google_drive.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

COLUMNAS_COLA = [
    "OrdenID",
    "FechaSolicitud",
    "UsuarioSolicitud",
    "Camioneta",
    "CodigoDespacho",
    "CodigosDespachoJSON",
    "UsarFiltroCodigoDespacho",
    "PedidosJSON",
    "CantidadPedidos",
    "Estado",
    "Etapa",
    "Mensaje",
    "FechaInicio",
    "FechaFin",
    "DuracionSegundos",
    "Intentos",
    "WorkerID",
    "UltimaActualizacion",
]

ESTADOS_TERMINALES = {"COMPLETADA", "ERROR", "CANCELADA"}


def ahora_texto() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def limpiar_valor(valor: Any) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"

    return str(valor).strip()


def crear_credenciales():
    if RUTA_JSON.exists():
        return service_account.Credentials.from_service_account_file(
            RUTA_JSON,
            scopes=SCOPES,
        )

    if st is not None:
        try:
            datos = dict(st.secrets["gcp_service_account"])
            return service_account.Credentials.from_service_account_info(
                datos,
                scopes=SCOPES,
            )
        except Exception:
            pass

    secreto_json = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "").strip()

    if secreto_json:
        return service_account.Credentials.from_service_account_info(
            json.loads(secreto_json),
            scopes=SCOPES,
        )

    raise RuntimeError(
        "No se encontraron credenciales de Google. "
        "Usá config/google_drive.json en la PC o "
        "[gcp_service_account] en Streamlit Secrets."
    )


def crear_servicio_sheets():
    return build(
        "sheets",
        "v4",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


def nombre_rango(rango: str = "") -> str:
    if rango:
        return f"'{NOMBRE_HOJA}'!{rango}"

    return f"'{NOMBRE_HOJA}'"


def numero_a_columna_excel(numero: int) -> str:
    resultado = ""

    while numero:
        numero, resto = divmod(numero - 1, 26)
        resultado = chr(65 + resto) + resultado

    return resultado


def asegurar_hoja_cola() -> None:
    servicio = crear_servicio_sheets()

    metadata = (
        servicio.spreadsheets()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            fields="sheets.properties.title",
        )
        .execute()
    )

    hojas = {
        hoja["properties"]["title"]
        for hoja in metadata.get("sheets", [])
    }

    if NOMBRE_HOJA not in hojas:
        servicio.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": NOMBRE_HOJA,
                            }
                        }
                    }
                ]
            },
        ).execute()

    encabezados = (
        servicio.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango("1:1"),
        )
        .execute()
        .get("values", [])
    )

    actuales = encabezados[0] if encabezados else []

    if not actuales:
        servicio.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango("A1"),
            valueInputOption="RAW",
            body={"values": [COLUMNAS_COLA]},
        ).execute()
        return

    if actuales == COLUMNAS_COLA:
        return

    # ------------------------------------------------------
    # MIGRACIÓN AUTOMÁTICA DE ESTRUCTURA
    # ------------------------------------------------------
    # Si la hoja existe con una versión anterior, conserva los
    # datos de las columnas conocidas, agrega las nuevas vacías
    # y reordena todo según COLUMNAS_COLA.

    valores_actuales = (
        servicio.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(),
        )
        .execute()
        .get("values", [])
    )

    filas_actuales = valores_actuales[1:] if valores_actuales else []

    filas_migradas = []

    for fila in filas_actuales:
        fila_completa = (
            fila
            + [""] * (len(actuales) - len(fila))
        )

        registro_actual = {
            encabezado: fila_completa[indice]
            for indice, encabezado in enumerate(actuales)
            if encabezado
        }

        filas_migradas.append([
            limpiar_valor(
                registro_actual.get(columna, "")
            )
            for columna in COLUMNAS_COLA
        ])

    # Limpia la hoja completa para evitar que queden columnas
    # antiguas o valores residuales fuera de la estructura nueva.
    servicio.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_rango(),
        body={},
    ).execute()

    valores_nuevos = [COLUMNAS_COLA] + filas_migradas

    servicio.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_rango("A1"),
        valueInputOption="RAW",
        body={"values": valores_nuevos},
    ).execute()

    print(
        "Hoja ColaAgrupaciones migrada automáticamente. "
        f"Columnas anteriores: {actuales}. "
        f"Columnas actuales: {COLUMNAS_COLA}",
        flush=True,
    )


def leer_cola() -> pd.DataFrame:
    asegurar_hoja_cola()
    servicio = crear_servicio_sheets()

    valores = (
        servicio.spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(),
        )
        .execute()
        .get("values", [])
    )

    if len(valores) <= 1:
        return pd.DataFrame(columns=COLUMNAS_COLA)

    encabezados = valores[0]
    filas = []

    for fila in valores[1:]:
        completa = fila + [""] * (len(encabezados) - len(fila))
        filas.append(completa[:len(encabezados)])

    df = pd.DataFrame(filas, columns=encabezados)

    for columna in COLUMNAS_COLA:
        if columna not in df.columns:
            df[columna] = ""

    return df[COLUMNAS_COLA].copy()


def agregar_fila(registro: dict[str, Any]) -> None:
    asegurar_hoja_cola()
    servicio = crear_servicio_sheets()

    fila = [
        limpiar_valor(registro.get(columna, ""))
        for columna in COLUMNAS_COLA
    ]

    servicio.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_rango("A1"),
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [fila]},
    ).execute()


def buscar_fila_orden(orden_id: str) -> int | None:
    df = leer_cola()

    if df.empty:
        return None

    coincidencias = df.index[
        df["OrdenID"].astype(str).str.strip().eq(str(orden_id).strip())
    ].tolist()

    if not coincidencias:
        return None

    return int(coincidencias[0]) + 2


def actualizar_orden(
    orden_id: str,
    cambios: dict[str, Any],
) -> None:
    fila = buscar_fila_orden(orden_id)

    if fila is None:
        raise ValueError(f"No existe la orden {orden_id}.")

    servicio = crear_servicio_sheets()
    data = []

    cambios_finales = {
        **cambios,
        "UltimaActualizacion": ahora_texto(),
    }

    for columna, valor in cambios_finales.items():
        if columna not in COLUMNAS_COLA:
            raise ValueError(f"Columna inválida en cola: {columna}")

        indice = COLUMNAS_COLA.index(columna) + 1
        letra = numero_a_columna_excel(indice)

        data.append({
            "range": nombre_rango(f"{letra}{fila}"),
            "values": [[limpiar_valor(valor)]],
        })

    servicio.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "valueInputOption": "RAW",
            "data": data,
        },
    ).execute()


def crear_orden_agrupacion(
    *,
    camioneta: str,
    codigo_despacho: str,
    codigos_despacho: list[str],
    usar_filtro_codigo_despacho: bool,
    pedidos: list[str],
    usuario: str,
) -> str:
    pedidos_normalizados = list(
        dict.fromkeys(
            str(pedido).strip()
            for pedido in pedidos
            if str(pedido).strip()
        )
    )

    codigos_normalizados = list(
        dict.fromkeys(
            str(codigo).strip()
            for codigo in codigos_despacho
            if str(codigo).strip()
        )
    )

    if not pedidos_normalizados:
        raise ValueError("La orden no contiene pedidos.")

    orden_id = f"AGR-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6].upper()}"
    fecha = ahora_texto()

    agregar_fila({
        "OrdenID": orden_id,
        "FechaSolicitud": fecha,
        "UsuarioSolicitud": usuario,
        "Camioneta": camioneta,
        "CodigoDespacho": codigo_despacho,
        "CodigosDespachoJSON": json.dumps(
            codigos_normalizados,
            ensure_ascii=False,
        ),
        "UsarFiltroCodigoDespacho": usar_filtro_codigo_despacho,
        "PedidosJSON": json.dumps(
            pedidos_normalizados,
            ensure_ascii=False,
        ),
        "CantidadPedidos": len(pedidos_normalizados),
        "Estado": "PENDIENTE",
        "Etapa": "encolada",
        "Mensaje": "Orden recibida y pendiente de ejecución.",
        "FechaInicio": "",
        "FechaFin": "",
        "DuracionSegundos": "",
        "Intentos": 0,
        "WorkerID": "",
        "UltimaActualizacion": fecha,
    })

    return orden_id


def obtener_orden(orden_id: str) -> dict[str, Any] | None:
    df = leer_cola()

    if df.empty:
        return None

    filas = df[
        df["OrdenID"].astype(str).str.strip().eq(str(orden_id).strip())
    ]

    if filas.empty:
        return None

    return filas.iloc[0].to_dict()


def obtener_siguiente_pendiente() -> dict[str, Any] | None:
    df = leer_cola()

    if df.empty:
        return None

    pendientes = df[
        df["Estado"].astype(str).str.strip().str.upper().eq("PENDIENTE")
    ].copy()

    if pendientes.empty:
        return None

    pendientes["_fecha"] = pd.to_datetime(
        pendientes["FechaSolicitud"],
        errors="coerce",
    )

    pendientes = pendientes.sort_values(
        by="_fecha",
        ascending=True,
        na_position="last",
    )

    return pendientes.iloc[0].drop(labels=["_fecha"]).to_dict()


def marcar_en_proceso(
    orden_id: str,
    worker_id: str,
    intentos: int,
) -> None:
    actualizar_orden(
        orden_id,
        {
            "Estado": "EN_PROCESO",
            "Etapa": "inicio",
            "Mensaje": "El worker tomó la orden.",
            "FechaInicio": ahora_texto(),
            "WorkerID": worker_id,
            "Intentos": intentos,
        },
    )


def worker_id_local() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"
