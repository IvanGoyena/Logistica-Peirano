from io import BytesIO
from pathlib import Path

import pandas as pd

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# ==========================================================
# CONFIGURACION
# ==========================================================

RUTA_JSON = Path("config/google_drive.json")

FOLDER_ID = "1G60r5Z5dHsNlPr8mIRWWTG6ArT02wOJD"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


# ==========================================================
# CONEXION
# ==========================================================

credenciales = service_account.Credentials.from_service_account_file(
    RUTA_JSON,
    scopes=SCOPES
)

service = build(
    "drive",
    "v3",
    credentials=credenciales
)


def buscar_archivo(nombre_archivo):

    consulta = (
        f"name = '{nombre_archivo}' "
        f"and '{FOLDER_ID}' in parents "
        f"and trashed = false"
    )

    resultado = service.files().list(
        q=consulta,
        fields="files(id,name,mimeType)"
    ).execute()

    archivos = resultado.get("files", [])

    print("\nArchivos encontrados:")
    for a in archivos:
        print(a)

    if not archivos:
        raise FileNotFoundError(f"No existe {nombre_archivo}")

    return archivos[0]["id"]


# ==========================================================
# DESCARGAR
# ==========================================================

def descargar_archivo(file_id):

    request = service.files().get_media(fileId=file_id)

    archivo = BytesIO()

    downloader = MediaIoBaseDownload(
        archivo,
        request
    )

    terminado = False

    while not terminado:

        _, terminado = downloader.next_chunk()

    archivo.seek(0)

    return archivo


# ==========================================================
# LEER EXCEL
# ==========================================================

def leer_excel(nombre):

    file_id = buscar_archivo(nombre)

    archivo = descargar_archivo(file_id)

    return pd.read_excel(archivo)


# ==========================================================
# LEER CSV
# ==========================================================

def leer_csv(nombre):

    file_id = buscar_archivo(nombre)

    archivo = descargar_archivo(file_id)

    return pd.read_csv(
        archivo,
        sep=";",
        encoding="utf-8-sig",
        low_memory=False
    )