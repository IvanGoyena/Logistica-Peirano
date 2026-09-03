from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

from utils.estado_actualizacion import registrar_version_fuente


GITHUB_OWNER = "IvanGoyena"
GITHUB_REPO = "Logistica-Peirano"
GITHUB_BRANCH = "main"

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubReaderError(RuntimeError):
    pass


def _obtener_token() -> str:
    """
    Obtiene el token desde:
    1. variable de entorno;
    2. st.secrets["GITHUB_TOKEN"];
    3. st.secrets["github"]["token"].

    El lector también puede funcionar sin token si el repositorio
    fuese público, aunque con un límite de API menor.
    """
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if token:
        return token

    try:
        token = str(
            st.secrets.get("GITHUB_TOKEN", "")
        ).strip()
    except Exception:
        token = ""

    if token:
        return token

    try:
        github = st.secrets.get("github", {})
        token = str(
            github.get("token", "")
        ).strip()
    except Exception:
        token = ""

    return token


def _headers(
    *,
    aceptar_raw: bool = False,
) -> dict[str, str]:
    token = _obtener_token()

    headers = {
        "Accept": (
            "application/vnd.github.raw+json"
            if aceptar_raw
            else "application/vnd.github+json"
        ),
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "Sistema-Logistico-Peirano",
        # Evita respuestas reutilizadas por proxies intermedios.
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    return headers


def _ruta_normalizada(
    ruta_github: str,
) -> str:
    return (
        str(ruta_github)
        .replace("\\", "/")
        .lstrip("/")
    )


def _url_contenido(
    ruta_github: str,
) -> str:
    ruta = quote(
        _ruta_normalizada(ruta_github),
        safe="/",
    )

    return (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/contents/{ruta}"
        f"?ref={quote(GITHUB_BRANCH)}"
    )


def _url_blob(
    sha: str,
) -> str:
    return (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/git/blobs/"
        f"{quote(sha)}"
    )


def _request_json(
    url: str,
) -> dict:
    request = Request(
        url=url,
        method="GET",
        headers=_headers(),
    )

    try:
        with urlopen(
            request,
            timeout=60,
        ) as response:
            contenido = response.read()

        if not contenido:
            return {}

        return json.loads(
            contenido.decode(
                "utf-8",
                errors="replace",
            )
        )

    except HTTPError as error:
        contenido = error.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            detalle = json.loads(contenido)
            mensaje = detalle.get(
                "message",
                contenido,
            )
        except Exception:
            mensaje = contenido

        raise GitHubReaderError(
            f"GitHub API {error.code}: {mensaje}"
        ) from error

    except URLError as error:
        raise GitHubReaderError(
            f"No se pudo conectar con GitHub: {error}"
        ) from error


def _decodificar_base64(
    contenido: str,
) -> bytes:
    texto = (
        str(contenido or "")
        .replace("\n", "")
        .strip()
    )

    if not texto:
        return b""

    return base64.b64decode(texto)


def descargar_archivo_github(
    ruta_github: str,
) -> tuple[bytes, dict]:
    """
    Descarga siempre la versión actual del archivo existente en main.

    Primero consulta Contents API para resolver el SHA actual.
    Para archivos grandes usa Git Blobs API, evitando el límite
    de contenido embebido de Contents API.
    """
    ruta_github = _ruta_normalizada(
        ruta_github
    )

    metadata = _request_json(
        _url_contenido(ruta_github)
    )

    if metadata.get("type") != "file":
        raise GitHubReaderError(
            f"La ruta no corresponde a un archivo: "
            f"{ruta_github}"
        )

    sha = str(
        metadata.get("sha", "")
    ).strip()

    contenido = metadata.get("content")
    encoding = str(
        metadata.get("encoding", "")
    ).lower()

    if (
        contenido
        and encoding == "base64"
    ):
        datos = _decodificar_base64(
            contenido
        )
    else:
        if not sha:
            raise GitHubReaderError(
                "GitHub no devolvió contenido ni SHA para "
                f"{ruta_github}"
            )

        blob = _request_json(
            _url_blob(sha)
        )

        if (
            str(blob.get("encoding", "")).lower()
            != "base64"
        ):
            raise GitHubReaderError(
                "El blob de GitHub no llegó en base64: "
                f"{ruta_github}"
            )

        datos = _decodificar_base64(
            blob.get("content", "")
        )

    if not datos:
        raise GitHubReaderError(
            f"GitHub devolvió el archivo vacío: {ruta_github}"
        )

    return datos, {
        "ruta_github": ruta_github,
        "sha": sha,
        "size": int(
            metadata.get(
                "size",
                len(datos),
            )
            or len(datos)
        ),
        "name": str(
            metadata.get(
                "name",
                Path(ruta_github).name,
            )
        ),
    }


def _leer_csv_bytes(
    datos: bytes,
) -> pd.DataFrame:
    errores = []

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "latin-1",
    ):
        try:
            return pd.read_csv(
                BytesIO(datos),
                sep=None,
                engine="python",
                encoding=encoding,
            )
        except Exception as error:
            errores.append(
                f"{encoding}: "
                f"{type(error).__name__}"
            )

    raise GitHubReaderError(
        "No se pudo interpretar el CSV descargado. "
        + " | ".join(errores)
    )


def _leer_excel_bytes(
    datos: bytes,
) -> pd.DataFrame:
    return pd.read_excel(
        BytesIO(datos)
    )


def _leer_dataframe_github_sin_cache(
    ruta_github: str,
) -> pd.DataFrame:
    datos, metadata = descargar_archivo_github(
        ruta_github
    )

    registrar_version_fuente(
        f"github:{ruta_github}",
        metadata.get("sha", ""),
    )

    extension = Path(
        ruta_github
    ).suffix.lower()

    print(
        "Leyendo versión actual desde GitHub: "
        f"{ruta_github} | "
        f"SHA {metadata.get('sha', '')[:10]}"
    )

    if extension == ".csv":
        return _leer_csv_bytes(datos)

    if extension in {
        ".xlsx",
        ".xls",
        ".xlsm",
    }:
        return _leer_excel_bytes(datos)

    if extension == ".parquet":
        return pd.read_parquet(
            BytesIO(datos)
        )

    raise GitHubReaderError(
        "Formato GitHub no soportado: "
        f"{extension or 'sin extensión'}"
    )


@st.cache_data(
    ttl=300,
    max_entries=32,
    show_spinner=False,
)
def _leer_dataframe_github_cache(
    ruta_github: str,
) -> pd.DataFrame:
    """
    Caché global breve para todas las lecturas desde GitHub.

    Evita consultar repetidamente la API ante cada rerun de Streamlit.
    El TTL es de 5 minutos y el botón global "Actualizar datos" puede
    invalidarla mediante st.cache_data.clear().
    """
    return _leer_dataframe_github_sin_cache(
        ruta_github
    )


def leer_archivo_github(
    ruta_github: str,
    *,
    cache: bool = False,
) -> pd.DataFrame:
    ruta_github = _ruta_normalizada(
        ruta_github
    )

    # Todas las lecturas remotas comparten la caché breve de 5 minutos.
    # El parámetro `cache` se conserva por compatibilidad con los módulos
    # existentes, pero ya no permite disparar consultas sin límite a la API.
    #
    # Una actualización manual sigue siendo inmediata porque app.py ejecuta
    # st.cache_data.clear(), invalidando esta función cacheada.
    return _leer_dataframe_github_cache(
        ruta_github
    ).copy()


def limpiar_cache_github_reader() -> None:
    _leer_dataframe_github_cache.clear()
