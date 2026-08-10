from pathlib import Path
from datetime import datetime

import pandas as pd

from utils.google_drive import (
    leer_excel,
    leer_excel_cache,
    leer_csv,
    leer_csv_cache,
    buscar_archivo,
)


# =====================================================
# CONFIGURACIÓN
# =====================================================

CARPETAS_REPOSITORIO = {
    "data_wms",
    "data_erp",
    "data_maestros",
}


# =====================================================
# RESOLVER NOMBRE DEL ARCHIVO
# =====================================================

def resolver_nombre(nombre):
    if Path(nombre).suffix != "":
        return nombre

    nombre_lower = nombre.strip().lower()

    if nombre_lower == "informe tareas":
        return "Informe Tareas.csv"

    if nombre_lower == "maestro clientes":
        return "Maestro Clientes.xlsm"

    return f"{nombre}.xlsx"


# =====================================================
# DETECTAR ORIGEN LOCAL / REPOSITORIO
# =====================================================

def _es_carpeta_repositorio(carpeta) -> bool:
    try:
        nombre_carpeta = Path(carpeta).name.strip().lower()
        return nombre_carpeta in CARPETAS_REPOSITORIO
    except Exception:
        return False


def _resolver_ruta_local(carpeta, nombre) -> Path:
    return Path(carpeta) / resolver_nombre(nombre)


# =====================================================
# LECTURA LOCAL
# =====================================================

def _leer_csv_local(ruta: Path) -> pd.DataFrame:
    errores = []

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "latin-1",
    ):
        try:
            return pd.read_csv(
                ruta,
                sep=None,
                engine="python",
                encoding=encoding,
            )
        except Exception as error:
            errores.append(
                f"{encoding}: {type(error).__name__}"
            )

    raise ValueError(
        "No se pudo leer el CSV local. "
        + " | ".join(errores)
    )


def _leer_excel_local(ruta: Path) -> pd.DataFrame:
    return pd.read_excel(ruta)


def _leer_archivo_local(
    carpeta,
    nombre,
) -> pd.DataFrame:
    ruta = _resolver_ruta_local(
        carpeta,
        nombre,
    )

    if not ruta.exists():
        return pd.DataFrame()

    extension = ruta.suffix.lower()

    print(
        f"Leyendo desde repositorio local: {ruta}"
    )

    if extension == ".csv":
        return _leer_csv_local(ruta)

    if extension in {
        ".xlsx",
        ".xls",
        ".xlsm",
    }:
        return _leer_excel_local(ruta)

    print(
        f"Formato local no soportado: {ruta.name}"
    )
    return pd.DataFrame()


# =====================================================
# LEER ARCHIVO
# =====================================================

def leer_archivo(
    carpeta,
    nombre,
    cache=False,
):
    """
    Nueva lógica:

    1. Si la carpeta es Data_WMS, Data_ERP o Data_Maestros,
       lee directamente el archivo físico del proyecto.

    2. Para las rutas antiguas conserva la lectura desde
       Google Drive, evitando romper módulos todavía no migrados.
    """

    try:
        nombre = resolver_nombre(nombre)

        # -------------------------------------------------
        # NUEVA ESTRUCTURA LOCAL / GITHUB
        # -------------------------------------------------
        if _es_carpeta_repositorio(carpeta):
            return _leer_archivo_local(
                carpeta,
                nombre,
            )

        # -------------------------------------------------
        # COMPATIBILIDAD TEMPORAL CON GOOGLE DRIVE
        # -------------------------------------------------
        extension = Path(nombre).suffix.lower()

        if extension == ".csv":
            if cache:
                print(
                    f"Usando CACHE Google Drive: {nombre}"
                )
                return leer_csv_cache(nombre)

            print(
                f"Leyendo desde Google Drive: {nombre}"
            )
            return leer_csv(nombre)

        if extension in {
            ".xlsx",
            ".xls",
            ".xlsm",
        }:
            if cache:
                print(
                    f"Usando CACHE Google Drive: {nombre}"
                )
                return leer_excel_cache(nombre)

            print(
                f"Leyendo desde Google Drive: {nombre}"
            )
            return leer_excel(nombre)

        print(
            f"Formato no soportado: {nombre}"
        )
        return pd.DataFrame()

    except Exception as error:
        print("")
        print("=" * 60)
        print("ERROR LEYENDO ARCHIVO")
        print(type(error).__name__)
        print(error)
        print("=" * 60)

        return pd.DataFrame()


# =====================================================
# FECHA ARCHIVO
# =====================================================

def fecha_archivo(
    carpeta,
    nombre,
):
    """
    Para las nuevas carpetas devuelve la fecha y hora real
    de modificación del archivo.

    Para fuentes todavía no migradas conserva la indicación
    de Google Drive.
    """

    try:
        nombre = resolver_nombre(nombre)

        # -------------------------------------------------
        # NUEVA ESTRUCTURA LOCAL / GITHUB
        # -------------------------------------------------
        if _es_carpeta_repositorio(carpeta):
            ruta = _resolver_ruta_local(
                carpeta,
                nombre,
            )

            if not ruta.exists():
                return "--"

            timestamp = ruta.stat().st_mtime

            return datetime.fromtimestamp(
                timestamp
            ).strftime(
                "%d/%m/%Y %H:%M:%S"
            )

        # -------------------------------------------------
        # COMPATIBILIDAD GOOGLE DRIVE
        # -------------------------------------------------
        buscar_archivo(nombre)

        return "Google Drive"

    except Exception:
        return "--"
