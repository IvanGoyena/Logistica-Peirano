from __future__ import annotations

from pathlib import Path
from typing import Any
import time
import socket
import ssl
import http.client

import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


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
    "Remito",
    "Cliente",
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




COLUMNAS_CONFIRMACIONES_INGRESO_OC = [
    "OrdenCompra",
    "FechaConfirmadaIngreso",
    "UsuarioConfirmacion",
    "FechaRegistro",
]


COLUMNAS_COBERTURA_INFORMADOS = [
    "Pedido",
    "FechaInformado",
    "Usuario",
    "Estado",
]

COLUMNAS_CANCELACIONES_ENTREGA = [
    "CancelacionEntregaID",
    "Remito",
    "Cliente",
    "Motivo",
    "Observacion",
    "UsuarioSolicitante",
    "FechaSolicitud",
    "EstadoCancelacion",
    "TelefonoDestino",
    "EstadoWhatsApp",
    "FechaEnvioWhatsApp",
    "ResponsableConfirmacion",
    "FechaConfirmacion",
    "ObservacionConfirmacion",
    "NumeroIR",
    "FechaIR",
    "EstadoReingreso",
    "FechaReingreso",
    "FechaCierre",
    "ResponsableGestion",
    "FechaInicioGestion",
    "ResultadoOperativo",
    "ResponsableIR",
    "ObservacionIR",
    "ResponsableReingreso",
    "ObservacionReingreso",
    "ResultadoFinal",
    "UltimaActualizacion",
]

# ==========================================================
# INVENTARIOS CÍCLICOS
# ==========================================================

COLUMNAS_INVENTARIO_PLANES = [
    "InventarioID",
    "FechaCreacion",
    "FechaPlanificada",
    "TipoInventario",
    "GrupoInventario",
    "Responsable",
    "ResponsableNombre",
    "Estado",
    "CantidadArticulos",
    "CantidadUbicaciones",
    "UsuarioCreacion",
    "UsuarioCreacionNombre",
    "Observaciones",
    "FechaInicio",
    "FechaFinalizacion",
]

COLUMNAS_INVENTARIO_ITEMS = [
    "ItemID",
    "InventarioID",
    "ArticuloCodigo",
    "ArticuloDescripcion",
    "GrupoInventario",
    "Familia",
    "Familia2",
    "Sectorizacion",
    "Ubicacion",
    "Contenedor",
    "FuenteDetalle",
    "CantidadSistemaUbicacion",
    "StockERPInicial",
    "StockWMSInicial",
    "DiferenciaInicial",
    "PrioridadInicial",
    "ScorePrioridad",
    "MotivoPrioridad",
    "EstadoItem",
    "OrdenConteo",
    "TipoUbicacion",
    "AreaUbicacion",
    "PasilloUbicacion",
]

COLUMNAS_INVENTARIO_CONTEOS = [
    "ConteoID",
    "InventarioID",
    "ItemID",
    "ArticuloCodigo",
    "Ubicacion",
    "Contenedor",
    "CantidadContada",
    "UsuarioConteo",
    "UsuarioConteoNombre",
    "FechaConteo",
    "Observacion",
    "OrigenConteo",
    "ImportacionID",
    "ArchivoOrigen",
    "FilaArchivo",
    "CantidadFotoUnidades",
    "CantidadFotoCajas",
    "CantidadRelevadaUnidades",
    "CantidadRelevadaCajas",
    "DiferenciaArchivo",
    "FotoPertenece",
    "ClaveImportacion",
    "EstadoValidacion",
]

COLUMNAS_INVENTARIO_RECONTEOS = [
    "ReconteoID",
    "InventarioID",
    "ItemID",
    "ArticuloCodigo",
    "Ubicacion",
    "Contenedor",
    "CantidadRecontada",
    "UsuarioReconteo",
    "UsuarioReconteoNombre",
    "FechaReconteo",
    "Observacion",
]


COLUMNAS_INVENTARIO_IMPORTACIONES = [
    "ImportacionID",
    "InventarioID",
    "TipoImportacion",
    "NombreArchivo",
    "HashArchivo",
    "FechaCarga",
    "UsuarioCarga",
    "UsuarioCargaNombre",
    "RegistrosOriginales",
    "RegistrosValidos",
    "DuplicadosArchivo",
    "FueraDelPlan",
    "Ambiguos",
    "Errores",
    "EstadoImportacion",
]

COLUMNAS_INVENTARIO_ACCIONES = [
    "AccionID", "InventarioID", "ArticuloCodigo", "ArticuloDescripcion",
    "Diagnostico", "AccionSugerida", "SistemaObjetivo", "TipoUbicacion",
    "UbicacionesSugeridas", "DiferenciaERPvsWMS", "DiferenciaFisicavsWMS",
    "EstadoAccion", "Responsable", "FechaCreacion", "FechaActualizacion",
    "UsuarioUltimaActualizacion", "CausaRaiz", "Resolucion", "Observaciones",
]

COLUMNAS_INVENTARIO_HISTORIAL = [
    "HistorialID",
    "InventarioID",
    "ItemID",
    "ArticuloCodigo",
    "Accion",
    "EstadoAnterior",
    "EstadoNuevo",
    "Usuario",
    "UsuarioNombre",
    "Fecha",
    "Detalle",
]


ESTRUCTURA_HOJAS = {

    "Solicitudes": COLUMNAS_SOLICITUDES,

    "Urgencias": COLUMNAS_URGENCIAS,

    "Anulaciones": COLUMNAS_ANULACIONES,

    "CancelacionesEntrega": COLUMNAS_CANCELACIONES_ENTREGA,

    "Reclamos": COLUMNAS_RECLAMOS,

    "ReclamosDetalle": COLUMNAS_RECLAMOS_DETALLE,

    "ReclamosFotos": COLUMNAS_RECLAMOS_FOTOS,

    "ConfirmacionesIngresoOC": COLUMNAS_CONFIRMACIONES_INGRESO_OC,

    "CoberturaInformados": COLUMNAS_COBERTURA_INFORMADOS,

    "InventarioPlanes": COLUMNAS_INVENTARIO_PLANES,

    "InventarioItems": COLUMNAS_INVENTARIO_ITEMS,

    "InventarioConteos": COLUMNAS_INVENTARIO_CONTEOS,

    "InventarioReconteos": COLUMNAS_INVENTARIO_RECONTEOS,

    "InventarioImportaciones": COLUMNAS_INVENTARIO_IMPORTACIONES,

    "InventarioAcciones": COLUMNAS_INVENTARIO_ACCIONES,

    "InventarioHistorial": COLUMNAS_INVENTARIO_HISTORIAL,

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


@st.cache_resource(ttl=1800)
def crear_servicio_sheets():
    """Crea y reutiliza el servicio de Google Sheets."""
    return build(
        "sheets",
        "v4",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


# Reintentos de transporte. Si una conexión HTTP queda cortada, se descarta
# el servicio cacheado antes del siguiente intento para forzar una conexión nueva.
_INTENTOS_RED_GOOGLE = 3
_ESPERAS_RED_GOOGLE = (1.5, 3.0)


def _es_error_autenticacion_google(error: Exception) -> bool:
    if isinstance(error, RefreshError):
        return True
    if isinstance(error, HttpError):
        try:
            if int(error.resp.status) in (401, 403):
                return True
        except Exception:
            pass
    texto = f"{type(error).__name__}: {error}".lower()
    return any(m in texto for m in (
        "invalid_grant", "invalid jwt", "token must be a short-lived token",
        "check your iat and exp", "invalid credentials", "unauthorized"
    ))


def _es_error_transitorio_red(error: Exception) -> bool:
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError, ConnectionError,
                          TimeoutError, socket.timeout, ssl.SSLError, http.client.HTTPException)):
        return True
    if isinstance(error, HttpError):
        try:
            if int(error.resp.status) in (429, 500, 502, 503, 504):
                return True
        except Exception:
            pass
    texto = f"{type(error).__name__}: {error}".lower()
    return any(m in texto for m in (
        "winerror 10053", "winerror 10054", "winerror 10060", "connection reset", "connection aborted",
        "remotedisconnected", "timed out", "timeout", "temporarily unavailable",
        "service unavailable", "rate limit"
    ))

def _reiniciar_servicio_sheets() -> None:
    """Descarta el cliente HTTP actual para que el próximo intento reconecte."""
    try:
        crear_servicio_sheets.clear()
    except Exception:
        pass


def _ejecutar_sheets_con_reintentos(crear_peticion):
    """Lecturas/idempotentes: recupera token/JWT, red, 429 y 5xx."""
    ultimo_error: Exception | None = None
    for intento in range(1, _INTENTOS_RED_GOOGLE + 1):
        try:
            servicio = crear_servicio_sheets()
            return crear_peticion(servicio).execute()
        except Exception as error:
            ultimo_error = error
            if not (_es_error_autenticacion_google(error) or _es_error_transitorio_red(error)):
                raise
            print(f"Google Sheets: error recuperable (intento {intento}/{_INTENTOS_RED_GOOGLE}): {type(error).__name__}: {error}")
            _reiniciar_servicio_sheets()
            if intento < _INTENTOS_RED_GOOGLE:
                time.sleep(_ESPERAS_RED_GOOGLE[min(intento - 1, len(_ESPERAS_RED_GOOGLE) - 1)])
    assert ultimo_error is not None
    raise ultimo_error


def _ejecutar_escritura_sheets_segura(crear_peticion):
    """Escrituras: reintenta sólo fallos claros de autenticación, evitando duplicados por cortes ambiguos."""
    try:
        servicio = crear_servicio_sheets()
        return crear_peticion(servicio).execute()
    except Exception as error:
        if not _es_error_autenticacion_google(error):
            raise
        print("Google Sheets: token/JWT rechazado en escritura; recreando servicio y reintentando una vez.")
        _reiniciar_servicio_sheets()
        servicio = crear_servicio_sheets()
        return crear_peticion(servicio).execute()


@st.cache_resource(ttl=1800)
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

@st.cache_data(ttl=300, show_spinner=False)
def obtener_nombres_hojas() -> list[str]:
    """
    Devuelve las pestañas existentes en la planilla.
    """

    planilla = _ejecutar_sheets_con_reintentos(
        lambda servicio: servicio.spreadsheets().get(
            spreadsheetId=SPREADSHEET_ID,
            fields="sheets.properties.title",
        )
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


@st.cache_data(ttl=300, show_spinner=False)
def leer_encabezados(nombre_hoja: str) -> list[str]:
    """
    Lee la primera fila de una hoja.
    """

    resultado = _ejecutar_sheets_con_reintentos(
        lambda servicio: servicio.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja, "1:1"),
        )
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

    _ejecutar_escritura_sheets_segura(
        lambda servicio: servicio.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja, "A1"),
            valueInputOption="RAW",
            body={"values": [columnas]},
        )
    )
    limpiar_cache_google_sheets(metadata=True)


def asegurar_hoja(nombre_hoja: str) -> None:
    """Crea una hoja configurada y sus encabezados cuando todavía no existe."""

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(f"Hoja no configurada: {nombre_hoja}")

    columnas = ESTRUCTURA_HOJAS[nombre_hoja]
    hojas_existentes = obtener_nombres_hojas()

    if nombre_hoja not in hojas_existentes:
        crear_hoja(nombre_hoja)
        escribir_encabezados(nombre_hoja, columnas)
        return

    encabezados = leer_encabezados(nombre_hoja)
    if not encabezados:
        escribir_encabezados(nombre_hoja, columnas)
        return

    if encabezados != columnas:
        # Migración segura: si la hoja conserva el mismo orden y sólo le
        # faltan columnas nuevas al final, se amplían los encabezados sin
        # tocar los registros existentes.
        if columnas[:len(encabezados)] == encabezados:
            escribir_encabezados(nombre_hoja, columnas)
            return

        raise ValueError(
            f"La hoja '{nombre_hoja}' tiene encabezados diferentes "
            "a los esperados."
        )


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

@st.cache_data(ttl=20, max_entries=40, show_spinner=False)
def _leer_hoja_cache(
    nombre_hoja: str,
    columnas_cache: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Lectura cacheada para reducir requests a Google Sheets."""

    columnas = (
        list(columnas_cache)
        if columnas_cache is not None
        else None
    )
    return _leer_hoja_sin_cache(
        nombre_hoja,
        columnas,
    )


def leer_hoja(
    nombre_hoja: str,
    columnas: list[str] | None = None,
) -> pd.DataFrame:
    """Lee una hoja usando una caché corta y devuelve una copia."""

    resultado = _leer_hoja_cache(
        nombre_hoja,
        tuple(columnas) if columnas else None,
    )
    return resultado.copy()


def _leer_hoja_sin_cache(
    nombre_hoja: str,
    columnas: list[str] | None = None,
) -> pd.DataFrame:
    """Lectura real de Google Sheets."""

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas_esperadas = (
        columnas
        if columnas is not None
        else ESTRUCTURA_HOJAS[nombre_hoja]
    )

    resultado = _ejecutar_sheets_con_reintentos(
        lambda servicio: (
            servicio
            .spreadsheets()
            .values()
            .get(
                spreadsheetId=SPREADSHEET_ID,
                range=nombre_rango(nombre_hoja),
            )
        )
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


def limpiar_cache_google_sheets(
    *,
    metadata: bool = False,
) -> None:
    """Invalida sólo las capas de lectura de Google Sheets."""

    _leer_hoja_cache.clear()

    if metadata:
        obtener_nombres_hojas.clear()
        leer_encabezados.clear()


# ==========================================================
# INSERCIÓN
# ==========================================================

def agregar_registro(
    nombre_hoja: str,
    registro: dict[str, Any],
) -> None:
    """Agrega una fila sin volver a leer encabezados."""

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas = ESTRUCTURA_HOJAS[nombre_hoja]
    fila = [
        limpiar_valor(registro.get(columna, ""))
        for columna in columnas
    ]

    _ejecutar_escritura_sheets_segura(
        lambda servicio: servicio.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja, "A1"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [fila]},
        )
    )

    limpiar_cache_google_sheets()


def agregar_registros(
    nombre_hoja: str,
    registros: list[dict[str, Any]],
) -> None:
    """Agrega múltiples filas en una sola llamada."""

    if not registros:
        return

    if nombre_hoja not in ESTRUCTURA_HOJAS:
        raise ValueError(
            f"Hoja no configurada: {nombre_hoja}"
        )

    columnas = ESTRUCTURA_HOJAS[nombre_hoja]
    filas = [
        [
            limpiar_valor(registro.get(columna, ""))
            for columna in columnas
        ]
        for registro in registros
    ]

    _ejecutar_escritura_sheets_segura(
        lambda servicio: servicio.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=nombre_rango(nombre_hoja, "A1"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": filas},
        )
    )

    limpiar_cache_google_sheets()


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

    limpiar_cache_google_sheets()


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

    limpiar_cache_google_sheets()


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
