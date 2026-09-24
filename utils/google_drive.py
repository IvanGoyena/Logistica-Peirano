from io import BytesIO
from pathlib import Path
import time


import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

RUTA_JSON = Path("config/google_drive.json")

FOLDER_ID = "1G60r5Z5dHsNlPr8mIRWWTG6ArT02wOJD"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

EXTENSIONES_SINCRONIZABLES = {
    ".csv",
    ".xlsx",
    ".xls",
    ".xlsm",
}


# ==========================================================
# CREDENCIALES Y CONEXIÓN
# ==========================================================

def crear_credenciales():

    if RUTA_JSON.exists():

        return service_account.Credentials.from_service_account_file(
            RUTA_JSON,
            scopes=SCOPES,
        )

    return service_account.Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=SCOPES,
    )


@st.cache_resource(ttl=1800, show_spinner=False)
def crear_servicio_drive():
    """
    Crea el cliente de Google Drive.

    El TTL evita conservar indefinidamente un cliente antiguo. Ante errores
    recuperables, _ejecutar_drive() limpia esta caché y crea credenciales
    nuevas automáticamente.
    """
    return build(
        "drive",
        "v3",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


def _es_error_recuperable(error: Exception) -> bool:
    """Indica si conviene reconstruir el cliente y reintentar una vez."""
    if isinstance(error, (RefreshError, TransportError, TimeoutError, ConnectionError)):
        return True

    if isinstance(error, HttpError):
        status = getattr(getattr(error, "resp", None), "status", None)
        return status in {401, 403, 408, 429, 500, 502, 503, 504}

    texto = str(error).lower()
    marcas = (
        "invalid_grant",
        "invalid jwt",
        "token",
        "timed out",
        "timeout",
        "connection",
        "temporarily unavailable",
    )
    return any(marca in texto for marca in marcas)


def _reiniciar_servicio_drive() -> None:
    """Descarta el cliente cacheado para forzar credenciales/servicio nuevos."""
    try:
        crear_servicio_drive.clear()
    except Exception:
        # No dejamos que una limpieza de caché impida el reintento.
        pass


def _ejecutar_drive(crear_request, *, reintentos: int = 1):
    """
    Ejecuta una llamada a Drive con recuperación automática.

    Si falla por autenticación o un problema transitorio:
    1) descarta el servicio cacheado;
    2) espera brevemente;
    3) crea credenciales nuevas;
    4) reintenta una sola vez.
    """
    ultimo_error = None

    for intento in range(reintentos + 1):
        try:
            servicio = crear_servicio_drive()
            return crear_request(servicio).execute()
        except Exception as error:
            ultimo_error = error

            if intento >= reintentos or not _es_error_recuperable(error):
                raise

            print(
                "Google Drive: error recuperable; "
                "se regenerará la conexión y se reintentará una vez."
            )
            print(f"{type(error).__name__}: {error}")

            _reiniciar_servicio_drive()
            time.sleep(1)

    raise ultimo_error


# ==========================================================
# BÚSQUEDA
# ==========================================================

def buscar_archivo(nombre_archivo):

    nombre_seguro = nombre_archivo.replace("'", "\\'")

    consulta = (
        f"name = '{nombre_seguro}' "
        f"and '{FOLDER_ID}' in parents "
        "and trashed = false"
    )

    resultado = _ejecutar_drive(
        lambda servicio: servicio.files().list(
            q=consulta,
            fields="files(id,name,mimeType)",
        )
    )

    archivos = resultado.get("files", [])

    if not archivos:
        raise FileNotFoundError(
            f"No existe {nombre_archivo}"
        )

    return archivos[0]["id"]


def listar_archivos_carpeta(
    folder_id: str = FOLDER_ID,
) -> list[dict]:

    archivos = []
    token = None

    while True:

        respuesta = _ejecutar_drive(
            lambda servicio: servicio.files().list(
                q=(
                    f"'{folder_id}' in parents "
                    "and trashed = false"
                ),
                fields=(
                    "nextPageToken,"
                    "files(id,name,mimeType,modifiedTime,size)"
                ),
                pageToken=token,
                pageSize=1000,
            )
        )

        archivos.extend(
            respuesta.get("files", [])
        )

        token = respuesta.get("nextPageToken")

        if not token:
            break

    return archivos


# ==========================================================
# DESCARGA
# ==========================================================

def descargar_archivo(file_id):
    """Descarga un archivo y reconstruye la conexión si falla a mitad de camino."""
    ultimo_error = None

    for intento in range(2):
        try:
            servicio = crear_servicio_drive()
            request = servicio.files().get_media(fileId=file_id)
            archivo = BytesIO()
            downloader = MediaIoBaseDownload(archivo, request)

            terminado = False
            while not terminado:
                _, terminado = downloader.next_chunk()

            archivo.seek(0)
            return archivo

        except Exception as error:
            ultimo_error = error

            if intento >= 1 or not _es_error_recuperable(error):
                raise

            print(
                "Google Drive: falló una descarga; "
                "se regenerará la conexión y se reintentará una vez."
            )
            print(f"{type(error).__name__}: {error}")
            _reiniciar_servicio_drive()
            time.sleep(1)

    raise ultimo_error


def descargar_archivo_a_disco(
    file_id: str,
    destino: str | Path,
) -> Path:

    destino = Path(destino)

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    archivo = descargar_archivo(file_id)

    destino.write_bytes(
        archivo.getvalue()
    )

    return destino


@st.cache_resource(
    ttl=3600,
    show_spinner=False,
)
def sincronizar_carpeta_drive(
    carpeta_destino: str | Path,
    folder_id: str = FOLDER_ID,
) -> dict:

    carpeta_destino = Path(
        carpeta_destino
    )

    carpeta_destino.mkdir(
        parents=True,
        exist_ok=True,
    )

    archivos_drive = listar_archivos_carpeta(
        folder_id=folder_id
    )

    descargados = []
    omitidos = []

    for archivo in archivos_drive:

        nombre = archivo["name"]
        extension = Path(nombre).suffix.lower()

        if extension not in EXTENSIONES_SINCRONIZABLES:
            omitidos.append(nombre)
            continue

        destino = carpeta_destino / nombre

        tamano_drive = archivo.get("size")

        archivo_igual = (
            destino.exists()
            and tamano_drive is not None
            and destino.stat().st_size == int(tamano_drive)
        )

        if archivo_igual:
            continue

        descargar_archivo_a_disco(
            file_id=archivo["id"],
            destino=destino,
        )

        descargados.append(nombre)

    return {
        "carpeta": str(carpeta_destino),
        "archivos_drive": len(archivos_drive),
        "descargados": descargados,
        "omitidos": omitidos,
    }


# ==========================================================
# LECTURA DE EXCEL
# ==========================================================

def leer_excel(nombre):

    file_id = buscar_archivo(nombre)
    archivo = descargar_archivo(file_id)

    return pd.read_excel(archivo)


@st.cache_data(ttl=86400)
def leer_excel_cache(nombre):

    file_id = buscar_archivo(nombre)
    archivo = descargar_archivo(file_id)

    return pd.read_excel(archivo)


# ==========================================================
# LECTURA DE CSV
# ==========================================================

def leer_csv(nombre):

    file_id = buscar_archivo(nombre)
    archivo = descargar_archivo(file_id)

    return pd.read_csv(
        archivo,
        sep=";",
        encoding="utf-8-sig",
        low_memory=False,
    )


@st.cache_data(ttl=86400)
def leer_csv_cache(nombre):

    file_id = buscar_archivo(nombre)
    archivo = descargar_archivo(file_id)

    return pd.read_csv(
        archivo,
        sep=";",
        encoding="utf-8-sig",
        low_memory=False,
    )
