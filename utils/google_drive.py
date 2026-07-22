from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


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


@st.cache_resource
def crear_servicio_drive():

    return build(
        "drive",
        "v3",
        credentials=crear_credenciales(),
        cache_discovery=False,
    )


# ==========================================================
# BÚSQUEDA
# ==========================================================

def buscar_archivo(nombre_archivo):

    servicio = crear_servicio_drive()

    nombre_seguro = nombre_archivo.replace("'", "\\'")

    consulta = (
        f"name = '{nombre_seguro}' "
        f"and '{FOLDER_ID}' in parents "
        "and trashed = false"
    )

    resultado = servicio.files().list(
        q=consulta,
        fields="files(id,name,mimeType)",
    ).execute()

    archivos = resultado.get("files", [])

    if not archivos:
        raise FileNotFoundError(
            f"No existe {nombre_archivo}"
        )

    return archivos[0]["id"]


def listar_archivos_carpeta(
    folder_id: str = FOLDER_ID,
) -> list[dict]:

    servicio = crear_servicio_drive()

    archivos = []
    token = None

    while True:

        respuesta = servicio.files().list(
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
        ).execute()

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

    servicio = crear_servicio_drive()

    request = servicio.files().get_media(
        fileId=file_id
    )

    archivo = BytesIO()

    downloader = MediaIoBaseDownload(
        archivo,
        request,
    )

    terminado = False

    while not terminado:
        _, terminado = downloader.next_chunk()

    archivo.seek(0)

    return archivo


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
