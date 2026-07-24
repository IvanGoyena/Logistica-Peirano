from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

RUTA_JSON = Path("config/google_drive.json")

SPREADSHEET_ID = (
    "1OHWMhUFjnm9IEtOIjNswXZlevgAwt74f2fqYzHFcDBQ"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ==========================================================
# ESTRUCTURA DE LAS HOJAS
# ==========================================================

COLUMNAS_SOLICITUDES = [
    "SolicitudID",
    "Pedido",
    "Cliente",
    "TipoSolicitud",
    "Prioridad",
    "Descripcion",
    "UsuarioSolicitante",
    "FechaSolicitud",
    "EstadoSolicitud",
    "Responsable",
    "Respuesta",
    "FechaResolucion",
]


COLUMNAS_URGENCIAS = [
    "UrgenciaID",
    "Pedido",
    "Cliente",
    "Motivo",
    "FechaRequerida",
    "Observacion",
    "UsuarioSolicitante",
    "FechaSolicitud",
    "EstadoUrgencia",
    "AgrupadorDestino",
    "EstadoEjecucionDIGIP",
    "MensajeEjecucionDIGIP",
    "FechaEjecucionDIGIP",
]


COLUMNAS_RECLAMOS = [
    "ReclamoID",
    "Pedido",
    "NumeroRemito",
    "ClienteCodigo",
    "ClienteDescripcion",
    "FechaReclamo",
    "TipoReclamo",
    "Descripcion",
    "Responsable",
    "EstadoReclamo",
    "Resolucion",
    "UsuarioCreador",
    "FechaCreacion",
    "FechaCierre",
]


COLUMNAS_RECLAMOS_DETALLE = [
    "ReclamoDetalleID",
    "ReclamoID",
    "CodigoArticulo",
    "DescripcionArticulo",
    "Cantidad",
    "Observacion",
]


COLUMNAS_RECLAMOS_FOTOS = [
    "ReclamoFotoID",
    "ReclamoID",
    "NombreArchivo",
    "DriveFileID",
    "URLArchivo",
    "UsuarioCreador",
    "FechaCarga",
]


COLUMNAS_ANULACIONES = [
    "AnulacionID",
    "Pedido",
    "Cliente",
    "Motivo",
    "Descripcion",
    "UsuarioSolicitante",
    "FechaSolicitud",
    "EstadoAnulacion",
    "BloqueoActivo",
    "UsuarioResolucion",
    "Respuesta",
    "FechaResolucion",
]

ESTRUCTURA_HOJAS = {

    "Solicitudes": COLUMNAS_SOLICITUDES,

    "Urgencias": COLUMNAS_URGENCIAS,

    "Anulaciones": COLUMNAS_ANULACIONES,

    "Reclamos": COLUMNAS_RECLAMOS,

    "ReclamosDetalle": COLUMNAS_RECLAMOS_DETALLE,

    "ReclamosFotos": COLUMNAS_RECLAMOS_FOTOS,

}


# ==========================================================
# CREDENCIALES
# ==========================================================

def crear_credenciales():
    """
    Crea las credenciales tanto para ejecución local como
    para Streamlit Cloud.
    """

    if RUTA_JSON.exists():
        return service_account.Credentials.from_service_account_file(
            RUTA_JSON,
            scopes=SCOPES,
        )

    try:
        datos_credenciales = dict(
            st.secrets["gcp_service_account"]
        )
    except Exception as error:
        raise RuntimeError(
            "No se encontraron las credenciales de Google. "
            "Verificá config/google_drive.json o los Secrets "
            "de Streamlit."
        ) from error

    return service_account.Credentials.from_service_account_info(
        datos_credenciales,
        scopes=SCOPES,
    )


@st.cache_resource
def crear_servicio_sheets():
    """
    Crea el servicio de Google Sheets.
    """

    return build(
        "sheets",
        "v4",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


@st.cache_resource
def crear_servicio_drive_escritura():
    """
    Crea el servicio de Google Drive con permisos de escritura.

    Se utilizará posteriormente para guardar las fotografías
    de los reclamos.
    """

    return build(
        "drive",
        "v3",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


# ==========================================================
# FUNCIONES GENERALES
# ==========================================================

def limpiar_valor(valor: Any) -> str:
    """
    Convierte cualquier valor a texto apto para Google Sheets.
    """

    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if texto.endswith(".0"):
        numero = texto[:-2]

        if numero.replace("-", "").isdigit():
            return numero

    return texto


def nombre_rango(nombre_hoja: str, rango: str = "") -> str:
    """
    Construye un rango válido para Google Sheets.
    """

    if rango:
        return f"'{nombre_hoja}'!{rango}"

    return f"'{nombre_hoja}'"


# ==========================================================
# VALIDACIÓN DE LA PLANILLA
# ==========================================================

def obtener_nombres_hojas() -> list[str]:
    """
    Devuelve las pestañas existentes en la planilla.
    """

    servicio = crear_servicio_sheets()

    planilla = (
        servicio
        .spreadsheets()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            fields="sheets.properties.title",
        )
        .execute()
    )

    return [
        hoja["properties"]["title"]
        for hoja in planilla.get("sheets", [])
    ]


def crear_hoja(nombre_hoja: str) -> None:
    """
    Crea una pestaña nueva dentro de la planilla.
    """

    servicio = crear_servicio_sheets()

    servicio.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": nombre_hoja,
                        }
                    }
                }
            ]
        },
    ).execute()


def leer_encabezados(nombre_hoja: str) -> list[str]:
    """
    Lee la primera fila de una hoja.
    """

    servicio = crear_servicio_sheets()

    resultado = (
        servicio
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja, "1:1"),
        )
        .execute()
    )

    valores = resultado.get("values", [])

    if not valores:
        return []

    return [
        limpiar_valor(valor)
        for valor in valores[0]
    ]


def escribir_encabezados(
    nombre_hoja: str,
    columnas: list[str],
) -> None:
    """
    Escribe los encabezados en la primera fila.
    """

    servicio = crear_servicio_sheets()

    servicio.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_rango(nombre_hoja, "A1"),
        valueInputOption="RAW",
        body={
            "values": [columnas],
        },
    ).execute()


def inicializar_planilla() -> dict[str, Any]:
    """
    Verifica que existan todas las hojas y encabezados.

    Si una hoja está vacía, escribe automáticamente sus
    encabezados. No sobrescribe hojas que ya contienen una
    estructura diferente.
    """

    hojas_existentes = obtener_nombres_hojas()

    hojas_creadas = []
    encabezados_creados = []
    hojas_validadas = []

    for nombre_hoja, columnas in ESTRUCTURA_HOJAS.items():

        if nombre_hoja not in hojas_existentes:
            crear_hoja(nombre_hoja)
            hojas_creadas.append(nombre_hoja)

        encabezados_actuales = leer_encabezados(nombre_hoja)

        if not encabezados_actuales:
            escribir_encabezados(
                nombre_hoja=nombre_hoja,
                columnas=columnas,
            )

            encabezados_creados.append(nombre_hoja)
            continue

        if encabezados_actuales != columnas:
            raise ValueError(
                f"La hoja '{nombre_hoja}' tiene encabezados "
                "diferentes a los esperados.\n\n"
                f"Actuales: {encabezados_actuales}\n\n"
                f"Esperados: {columnas}"
            )

        hojas_validadas.append(nombre_hoja)

    return {
        "ok": True,
        "spreadsheet_id": SPREADSHEET_ID,
        "hojas_creadas": hojas_creadas,
        "encabezados_creados": encabezados_creados,
        "hojas_validadas": hojas_validadas,
    }


# ==========================================================
# LECTURA
# ==========================================================

def leer_hoja(
    nombre_hoja: str,
    columnas: list[str] | None = None,
) -> pd.DataFrame:
    """
    Lee una pestaña completa y devuelve un DataFrame.
    """

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas_esperadas = (
        columnas
        if columnas is not None
        else ESTRUCTURA_HOJAS[nombre_hoja]
    )

    servicio = crear_servicio_sheets()

    resultado = (
        servicio
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja),
        )
        .execute()
    )

    valores = resultado.get("values", [])

    if not valores:
        return pd.DataFrame(columns=columnas_esperadas)

    encabezados = valores[0]
    filas = valores[1:]

    filas_normalizadas = []

    for fila in filas:
        fila_completa = (
            fila
            + [""] * (len(encabezados) - len(fila))
        )

        filas_normalizadas.append(
            fila_completa[:len(encabezados)]
        )

    dataframe = pd.DataFrame(
        filas_normalizadas,
        columns=encabezados,
    )

    for columna in columnas_esperadas:
        if columna not in dataframe.columns:
            dataframe[columna] = ""

    columnas_extra = [
        columna
        for columna in dataframe.columns
        if columna not in columnas_esperadas
    ]

    return dataframe[
        columnas_esperadas + columnas_extra
    ].copy()


# ==========================================================
# INSERCIÓN
# ==========================================================

def agregar_registro(
    nombre_hoja: str,
    registro: dict[str, Any],
) -> None:
    """
    Agrega una fila nueva respetando el orden de columnas.
    """

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas = ESTRUCTURA_HOJAS[nombre_hoja]

    fila = [
        limpiar_valor(registro.get(columna, ""))
        for columna in columnas
    ]

    servicio = crear_servicio_sheets()

    servicio.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_rango(nombre_hoja, "A1"),
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={
            "values": [fila],
        },
    ).execute()


# ==========================================================
# PRUEBA DE CONEXIÓN
# ==========================================================

def probar_conexion() -> dict[str, Any]:
    """
    Inicializa y valida la estructura completa.
    """

    resultado = inicializar_planilla()

    return {
        **resultado,
        "mensaje": (
            "Conexión con Google Sheets realizada "
            "correctamente."
        ),
    }


# ==========================================================
# ACTUALIZACIÓN DE REGISTROS
# ==========================================================

def buscar_fila_por_id(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
) -> int | None:
    """
    Busca un registro por ID.

    Devuelve el número real de fila en Google Sheets.
    La fila 1 corresponde a los encabezados.
    """

    dataframe = leer_hoja(nombre_hoja)

    if dataframe.empty:
        return None

    if columna_id not in dataframe.columns:
        raise ValueError(
            f"La columna '{columna_id}' no existe "
            f"en la hoja '{nombre_hoja}'."
        )

    valor_buscado = limpiar_valor(valor_id)

    coincidencias = dataframe.index[
        dataframe[columna_id]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq(valor_buscado)
    ].tolist()

    if not coincidencias:
        return None

    # DataFrame comienza en 0 y Sheets tiene encabezado en fila 1.
    return int(coincidencias[0]) + 2


def actualizar_registro(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
    cambios: dict[str, Any],
) -> None:
    """
    Actualiza columnas puntuales de un registro existente.
    """

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas = ESTRUCTURA_HOJAS[nombre_hoja]

    fila_sheets = buscar_fila_por_id(
        nombre_hoja=nombre_hoja,
        columna_id=columna_id,
        valor_id=valor_id,
    )

    if fila_sheets is None:
        raise ValueError(
            f"No se encontró el registro '{valor_id}' "
            f"en la hoja '{nombre_hoja}'."
        )

    servicio = crear_servicio_sheets()

    actualizaciones = []

    for columna, valor in cambios.items():

        if columna not in columnas:
            raise ValueError(
                f"La columna '{columna}' no pertenece "
                f"a la hoja '{nombre_hoja}'."
            )

        indice_columna = columnas.index(columna)
        letra_columna = numero_a_columna_excel(
            indice_columna + 1
        )

        actualizaciones.append({
            "range": nombre_rango(
                nombre_hoja,
                f"{letra_columna}{fila_sheets}",
            ),
            "values": [[limpiar_valor(valor)]],
        })

    if not actualizaciones:
        return

    servicio.spreadsheets().values().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "valueInputOption": "RAW",
            "data": actualizaciones,
        },
    ).execute()


def eliminar_registro(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
) -> None:
    """
    Elimina físicamente una fila de Google Sheets.
    """

    fila_sheets = buscar_fila_por_id(
        nombre_hoja=nombre_hoja,
        columna_id=columna_id,
        valor_id=valor_id,
    )

    if fila_sheets is None:
        raise ValueError(
            f"No se encontró el registro '{valor_id}' "
            f"en la hoja '{nombre_hoja}'."
        )

    servicio = crear_servicio_sheets()

    metadata = (
        servicio
        .spreadsheets()
        .get(
            spreadsheetId=SPREADSHEET_ID,
            fields="sheets.properties",
        )
        .execute()
    )

    sheet_id = None

    for hoja in metadata.get("sheets", []):
        propiedades = hoja.get("properties", {})

        if propiedades.get("title") == nombre_hoja:
            sheet_id = propiedades.get("sheetId")
            break

    if sheet_id is None:
        raise ValueError(
            f"No se encontró la hoja '{nombre_hoja}'."
        )

    # Google Sheets API utiliza índices comenzando en cero.
    indice_inicio = fila_sheets - 1

    servicio.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={
            "requests": [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": indice_inicio,
                            "endIndex": indice_inicio + 1,
                        }
                    }
                }
            ]
        },
    ).execute()


# ==========================================================
# UTILIDADES DE COLUMNAS
# ==========================================================

def numero_a_columna_excel(numero: int) -> str:
    """
    Convierte un número de columna en letras.

    Ejemplos:
        1  -> A
        26 -> Z
        27 -> AA
    """

    if numero < 1:
        raise ValueError(
            "El número de columna debe ser mayor a cero."
        )

    resultado = ""

    while numero:
        numero, resto = divmod(numero - 1, 26)
        resultado = chr(65 + resto) + resultado

    return resultado

def actualizar_registro(
    nombre_hoja,
    columna_id,
    valor_id,
    cambios,
):
    """
    Actualiza una fila buscando por una columna ID.
    """

    df = leer_hoja(nombre_hoja)

    if df.empty:
        raise ValueError("La hoja está vacía.")

    indice = df[
        df[columna_id].astype(str).str.strip()
        == str(valor_id).strip()
    ].index

    if len(indice) == 0:
        raise ValueError(
            f"No existe {valor_id} en {nombre_hoja}"
        )

    fila = indice[0]

    for columna, valor in cambios.items():
        df.loc[fila, columna] = valor

    servicio = crear_servicio_sheets()

    servicio.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_hoja,
    ).execute()

    servicio.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{nombre_hoja}!A1",
        valueInputOption="RAW",
        body={
            "values":[
                list(df.columns)
            ] + df.fillna("").values.tolist()
        },
    ).execute()

    def eliminar_registro(
    nombre_hoja,
    columna_id,
    valor_id,
):
       df = leer_hoja(nombre_hoja)

    df = df[
        df[columna_id].astype(str).str.strip()
        != str(valor_id).strip()
    ]

    servicio = crear_servicio_sheets()

    servicio.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=nombre_hoja,
    ).execute()

    servicio.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{nombre_hoja}!A1",
        valueInputOption="RAW",
        body={
            "values":[
                list(df.columns)
            ] + df.fillna("").values.tolist()
        },
    ).execute()