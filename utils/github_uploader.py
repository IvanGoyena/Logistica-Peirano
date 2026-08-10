from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


GITHUB_OWNER = "IvanGoyena"
GITHUB_REPO = "Logistica-Peirano"
GITHUB_BRANCH = "main"

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"


class GitHubUploaderError(RuntimeError):
    pass


def _obtener_token() -> str:
    token = os.getenv("GITHUB_TOKEN", "").strip()

    if not token:
        raise GitHubUploaderError(
            "No se encontró la variable de entorno GITHUB_TOKEN."
        )

    return token


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_obtener_token()}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "Sistema-Logistico-Peirano",
    }


def _url_contenido(ruta_github: str) -> str:
    ruta = quote(
        ruta_github.replace("\\", "/").lstrip("/"),
        safe="/",
    )

    return (
        f"{GITHUB_API}/repos/"
        f"{GITHUB_OWNER}/{GITHUB_REPO}/contents/{ruta}"
    )


def _hacer_request(
    url: str,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    data = None

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = Request(
        url=url,
        data=data,
        method=method,
        headers=_headers(),
    )

    try:
        with urlopen(request, timeout=60) as response:
            contenido = response.read().decode("utf-8")
            return (
                response.status,
                json.loads(contenido)
                if contenido
                else {},
            )

    except HTTPError as error:
        contenido = error.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            detalle = json.loads(contenido)
        except Exception:
            detalle = {"message": contenido}

        raise GitHubUploaderError(
            f"GitHub API {error.code}: "
            f"{detalle.get('message', contenido)}"
        ) from error

    except URLError as error:
        raise GitHubUploaderError(
            f"No se pudo conectar con GitHub: {error}"
        ) from error


def obtener_sha_remoto(
    ruta_github: str,
) -> str | None:
    """
    Devuelve el SHA actual del archivo remoto.
    Si el archivo no existe, devuelve None.
    """

    url = (
        _url_contenido(ruta_github)
        + f"?ref={quote(GITHUB_BRANCH)}"
    )

    request = Request(
        url=url,
        method="GET",
        headers=_headers(),
    )

    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

            return data.get("sha")

    except HTTPError as error:
        if error.code == 404:
            return None

        contenido = error.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            detalle = json.loads(contenido)
        except Exception:
            detalle = {"message": contenido}

        raise GitHubUploaderError(
            f"GitHub API {error.code}: "
            f"{detalle.get('message', contenido)}"
        ) from error


def validar_archivo_local(
    archivo_local: str | Path,
) -> Path:
    ruta = Path(archivo_local)

    if not ruta.exists():
        raise GitHubUploaderError(
            f"El archivo no existe: {ruta}"
        )

    if not ruta.is_file():
        raise GitHubUploaderError(
            f"La ruta no es un archivo: {ruta}"
        )

    if ruta.stat().st_size <= 0:
        raise GitHubUploaderError(
            f"El archivo está vacío: {ruta}"
        )

    return ruta


def subir_archivo_github(
    archivo_local: str | Path,
    ruta_github: str,
    mensaje_commit: str | None = None,
) -> dict:
    """
    Crea o reemplaza un archivo del repositorio en GitHub.
    """

    ruta_local = validar_archivo_local(
        archivo_local
    )

    contenido_base64 = base64.b64encode(
        ruta_local.read_bytes()
    ).decode("ascii")

    sha_actual = obtener_sha_remoto(
        ruta_github
    )

    if mensaje_commit is None:
        mensaje_commit = (
            f"Actualizar {ruta_github}"
        )

    payload = {
        "message": mensaje_commit,
        "content": contenido_base64,
        "branch": GITHUB_BRANCH,
    }

    if sha_actual:
        payload["sha"] = sha_actual

    status, respuesta = _hacer_request(
        _url_contenido(ruta_github),
        method="PUT",
        payload=payload,
    )

    commit = respuesta.get(
        "commit",
        {},
    )

    return {
        "ok": status in (200, 201),
        "status": status,
        "archivo_local": str(ruta_local),
        "ruta_github": ruta_github,
        "sha_anterior": sha_actual,
        "commit_sha": commit.get("sha", ""),
        "commit_url": commit.get("html_url", ""),
    }
