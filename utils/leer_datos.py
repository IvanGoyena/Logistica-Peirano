from pathlib import Path
from datetime import datetime
import os

import pandas as pd

from utils.google_drive import (
    leer_excel,
    leer_excel_cache,
    leer_csv,
    leer_csv_cache,
    buscar_archivo,
)
from utils.github_reader import (
    GitHubReaderError,
    leer_archivo_github,
    limpiar_cache_github_reader,
)
from utils.estado_actualizacion import registrar_version_fuente


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
        nombre_carpeta = (
            Path(carpeta)
            .name
            .strip()
            .lower()
        )

        return (
            nombre_carpeta
            in CARPETAS_REPOSITORIO
        )

    except Exception:
        return False


def _resolver_ruta_local(
    carpeta,
    nombre,
) -> Path:
    return (
        Path(carpeta)
        / resolver_nombre(nombre)
    )


def _resolver_ruta_github(
    carpeta,
    nombre,
) -> str:
    """
    Convierte:
        C:/.../Data_WMS + Pedidos DIGIP.xlsx
    en:
        Data_WMS/Pedidos DIGIP.xlsx
    """
    nombre_carpeta = (
        Path(carpeta)
        .name
        .strip()
    )

    return (
        f"{nombre_carpeta}/"
        f"{resolver_nombre(nombre)}"
    ).replace("\\", "/")


# =====================================================
# DETECTAR STREAMLIT CLOUD
# =====================================================

def _es_streamlit_cloud() -> bool:
    """
    Usa primero la bandera definida en config.py.

    Como respaldo reconoce variables habituales de un entorno
    desplegado. En el host/local devolverá False.
    """
    try:
        from config import ES_STREAMLIT_CLOUD

        return bool(
            ES_STREAMLIT_CLOUD
        )
    except Exception:
        pass

    indicadores = (
        "STREAMLIT_SHARING_MODE",
        "STREAMLIT_CLOUD",
    )

    return any(
        str(
            os.getenv(variable, "")
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "cloud",
        }
        for variable in indicadores
    )


# =====================================================
# LECTURA LOCAL
# =====================================================

def _leer_csv_local(
    ruta: Path,
) -> pd.DataFrame:
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
                f"{encoding}: "
                f"{type(error).__name__}"
            )

    raise ValueError(
        "No se pudo leer el CSV local. "
        + " | ".join(errores)
    )


def _leer_excel_local(
    ruta: Path,
) -> pd.DataFrame:
    return pd.read_excel(
        ruta
    )


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

    estado = ruta.stat()

    registrar_version_fuente(
        f"local:{ruta.resolve()}",
        (
            int(estado.st_mtime_ns),
            int(estado.st_size),
        ),
    )

    extension = ruta.suffix.lower()

    print(
        "Leyendo desde repositorio local: "
        f"{ruta}"
    )

    if extension == ".csv":
        return _leer_csv_local(
            ruta
        )

    if extension in {
        ".xlsx",
        ".xls",
        ".xlsm",
    }:
        return _leer_excel_local(
            ruta
        )

    if extension == ".parquet":
        return pd.read_parquet(
            ruta
        )

    print(
        "Formato local no soportado: "
        f"{ruta.name}"
    )

    return pd.DataFrame()


# =====================================================
# LECTURA DE FUENTE VERSIONADA
# =====================================================

def _leer_fuente_repositorio(
    carpeta,
    nombre,
    *,
    cache: bool,
) -> pd.DataFrame:
    """
    LOCAL:
        lee el archivo físico de Data_WMS/Data_ERP/Data_Maestros.

    STREAMLIT CLOUD:
        consulta la versión actual de main directamente mediante
        GitHub API, sin depender del checkout/redeploy de Streamlit.
    """
    if not _es_streamlit_cloud():
        return _leer_archivo_local(
            carpeta,
            nombre,
        )

    ruta_github = _resolver_ruta_github(
        carpeta,
        nombre,
    )

    try:
        return leer_archivo_github(
            ruta_github,
            cache=cache,
        )

    except GitHubReaderError as error:
        # No ocultamos el problema: queda registrado claramente.
        # Como respaldo se intenta el checkout local para que la app
        # no quede inutilizable ante una caída puntual de GitHub.
        print("")
        print("=" * 60)
        print("ERROR LEYENDO VERSION ACTUAL DESDE GITHUB")
        print(ruta_github)
        print(error)
        print(
            "Se intentará el archivo local del deploy "
            "como fallback."
        )
        print("=" * 60)

        return _leer_archivo_local(
            carpeta,
            nombre,
        )


# =====================================================
# LEER ARCHIVO
# =====================================================

def leer_archivo(
    carpeta,
    nombre,
    cache=False,
):
    """
    Arquitectura final:

    1. Data_WMS / Data_ERP / Data_Maestros:
       - host/local -> archivo físico local;
       - Streamlit Cloud -> última versión de GitHub main.

    2. Rutas antiguas:
       conserva Google Drive para las funcionalidades que
       todavía lo necesitan de forma intencional.
    """

    try:
        nombre = resolver_nombre(
            nombre
        )

        # -------------------------------------------------
        # NUEVA ESTRUCTURA REPOSITORIO / GITHUB
        # -------------------------------------------------
        if _es_carpeta_repositorio(
            carpeta
        ):
            return _leer_fuente_repositorio(
                carpeta,
                nombre,
                cache=cache,
            )

        # -------------------------------------------------
        # COMPATIBILIDAD CON GOOGLE DRIVE
        # -------------------------------------------------
        extension = Path(
            nombre
        ).suffix.lower()

        if extension == ".csv":
            if cache:
                print(
                    "Usando CACHE Google Drive: "
                    f"{nombre}"
                )
                return leer_csv_cache(
                    nombre
                )

            print(
                "Leyendo desde Google Drive: "
                f"{nombre}"
            )

            return leer_csv(
                nombre
            )

        if extension in {
            ".xlsx",
            ".xls",
            ".xlsm",
        }:
            if cache:
                print(
                    "Usando CACHE Google Drive: "
                    f"{nombre}"
                )
                return leer_excel_cache(
                    nombre
                )

            print(
                "Leyendo desde Google Drive: "
                f"{nombre}"
            )

            return leer_excel(
                nombre
            )

        print(
            "Formato no soportado: "
            f"{nombre}"
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
    Para el host devuelve la modificación del archivo local.

    En Streamlit Cloud informa que la fuente se consume directamente
    desde GitHub main. La vigencia real se controla por SHA en cada
    lectura no cacheada.
    """

    try:
        nombre = resolver_nombre(
            nombre
        )

        if _es_carpeta_repositorio(
            carpeta
        ):
            if _es_streamlit_cloud():
                return "GitHub main · lectura directa"

            ruta = _resolver_ruta_local(
                carpeta,
                nombre,
            )

            if not ruta.exists():
                return "--"

            timestamp = (
                ruta.stat().st_mtime
            )

            return datetime.fromtimestamp(
                timestamp
            ).strftime(
                "%d/%m/%Y %H:%M:%S"
            )

        buscar_archivo(
            nombre
        )

        return "Google Drive"

    except Exception:
        return "--"


# =====================================================
# LIMPIEZA GLOBAL DEL LECTOR GITHUB
# =====================================================

def limpiar_cache_lector_github() -> None:
    """
    Útil para botones globales de actualización si se desea limpiar
    también la caché de maestros remotos.
    """
    limpiar_cache_github_reader()
