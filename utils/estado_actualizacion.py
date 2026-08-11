from __future__ import annotations

from datetime import datetime
from threading import Lock
from zoneinfo import ZoneInfo


_LOCK = Lock()
_ULTIMA_ACTUALIZACION: datetime | None = None
_VERSIONES_FUENTES: dict[str, str] = {}


def _ahora_buenos_aires() -> datetime:
    return datetime.now(
        ZoneInfo("America/Argentina/Buenos_Aires")
    )


def registrar_version_fuente(
    fuente: str,
    version: object,
) -> bool:
    """
    Registra la versión observada de una fuente SIN ejecutar comandos
    de Streamlit ni tocar st.session_state.

    Esto es seguro aunque la lectura ocurra dentro de una función
    decorada con @st.cache_data.
    """
    global _ULTIMA_ACTUALIZACION

    clave_fuente = str(
        fuente or ""
    ).strip()

    if not clave_fuente:
        return False

    version_texto = str(
        version if version is not None else ""
    )

    with _LOCK:
        version_anterior = _VERSIONES_FUENTES.get(
            clave_fuente
        )

        _VERSIONES_FUENTES[
            clave_fuente
        ] = version_texto

        cambio = (
            version_anterior is None
            or version_anterior != version_texto
        )

        if cambio:
            _ULTIMA_ACTUALIZACION = (
                _ahora_buenos_aires()
            )

        return cambio


def registrar_actualizacion_manual() -> None:
    """
    Registra una actualización general solicitada manualmente.
    """
    global _ULTIMA_ACTUALIZACION

    with _LOCK:
        _ULTIMA_ACTUALIZACION = (
            _ahora_buenos_aires()
        )


def obtener_ultima_actualizacion() -> datetime | None:
    with _LOCK:
        return _ULTIMA_ACTUALIZACION
