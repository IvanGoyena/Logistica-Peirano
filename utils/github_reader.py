from __future__ import annotations

import base64
import json
import os
import time
import threading
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

# Protección frente a límites/transitorios de GitHub.
# El caché de Streamlit sigue siendo la primera barrera; esto agrega
# un circuito de protección para evitar tormentas de requests.
_CIRCUIT_LOCK = threading.RLock()
_CIRCUIT_OPEN_UNTIL = 0.0
_CIRCUIT_REASON = ""
_CIRCUIT_SECONDS_RATE_LIMIT = 300
_CIRCUIT_SECONDS_TRANSIENT = 30

# Cachea rutas inexistentes para no repetir 404 en cada rerun/búsqueda.
_NEGATIVE_CACHE: dict[str, float] = {}
_NEGATIVE_CACHE_TTL = 900


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


def _abrir_circuito(segundos: int, motivo: str) -> None:
    global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_REASON
    with _CIRCUIT_LOCK:
        _CIRCUIT_OPEN_UNTIL = max(
            _CIRCUIT_OPEN_UNTIL,
            time.monotonic() + max(1, int(segundos)),
        )
        _CIRCUIT_REASON = str(motivo or "").strip()


def _verificar_circuito() -> None:
    with _CIRCUIT_LOCK:
        restante = _CIRCUIT_OPEN_UNTIL - time.monotonic()
        motivo = _CIRCUIT_REASON

    if restante > 0:
        raise GitHubReaderError(
            "GitHub temporalmente protegido por circuit breaker "
            f"({int(restante) + 1}s). {motivo}"
        )


def _request_json(
    url: str,
) -> dict:
    _verificar_circuito()

    request = Request(
        url=url,
        method="GET",
        headers=_headers(),
    )

    try:
        with urlopen(
            request,
            timeout=30,
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

        mensaje_txt = str(mensaje or "")
        headers = getattr(error, "headers", None)
        restante = ""
        reset_epoch = ""
        retry_after = ""

        if headers is not None:
            restante = str(headers.get("X-RateLimit-Remaining", "")).strip()
            reset_epoch = str(headers.get("X-RateLimit-Reset", "")).strip()
            retry_after = str(headers.get("Retry-After", "")).strip()

        es_rate_limit = (
            error.code in {403, 429}
            and (
                restante == "0"
                or "rate limit" in mensaje_txt.lower()
                or "secondary rate limit" in mensaje_txt.lower()
                or error.code == 429
            )
        )

        if es_rate_limit:
            espera = _CIRCUIT_SECONDS_RATE_LIMIT

            if retry_after.isdigit():
                espera = max(espera, int(retry_after))

            if reset_epoch.isdigit():
                espera_reset = int(reset_epoch) - int(time.time()) + 5
                espera = max(espera, espera_reset)

            _abrir_circuito(
                espera,
                f"GitHub API {error.code}: {mensaje_txt}",
            )

        elif 500 <= error.code <= 599:
            _abrir_circuito(
                _CIRCUIT_SECONDS_TRANSIENT,
                f"GitHub API {error.code}: {mensaje_txt}",
            )

        raise GitHubReaderError(
            f"GitHub API {error.code}: {mensaje_txt}"
        ) from error

    except URLError as error:
        _abrir_circuito(
            _CIRCUIT_SECONDS_TRANSIENT,
            f"Error de conexión: {error}",
        )
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

    ahora = time.monotonic()
    vencimiento_404 = _NEGATIVE_CACHE.get(ruta_github, 0.0)
    if vencimiento_404 > ahora:
        raise GitHubReaderError(
            f"GitHub API 404 cacheado: {ruta_github}"
        )
    elif vencimiento_404:
        _NEGATIVE_CACHE.pop(ruta_github, None)

    try:
        metadata = _request_json(
            _url_contenido(ruta_github)
        )
    except GitHubReaderError as error:
        if "GitHub API 404:" in str(error):
            _NEGATIVE_CACHE[ruta_github] = (
                time.monotonic() + _NEGATIVE_CACHE_TTL
            )
        raise

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
    ttl=270,
    max_entries=64,
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
    """Limpia únicamente el lector GitHub, sin borrar todo st.cache_data."""
    global _CIRCUIT_OPEN_UNTIL, _CIRCUIT_REASON

    _leer_dataframe_github_cache.clear()
    _NEGATIVE_CACHE.clear()

    with _CIRCUIT_LOCK:
        _CIRCUIT_OPEN_UNTIL = 0.0
        _CIRCUIT_REASON = ""
