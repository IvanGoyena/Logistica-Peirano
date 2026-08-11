from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st


CLAVE_ULTIMA_ACTUALIZACION = "ultima_actualizacion_datos"
CLAVE_VERSIONES_FUENTES = "_versiones_fuentes_datos"
CLAVE_PLACEHOLDER = "_placeholder_ultima_actualizacion"


def _ahora_buenos_aires() -> datetime:
    return datetime.now(
        ZoneInfo("America/Argentina/Buenos_Aires")
    )


def _texto_ultima_actualizacion() -> str:
    fecha = st.session_state.get(
        CLAVE_ULTIMA_ACTUALIZACION
    )

    if fecha is None:
        return "🕒 Última actualización: --"

    return (
        "🕒 Última actualización: "
        f"{fecha.strftime('%d/%m/%Y %H:%M:%S')}"
    )


def preparar_indicador_sidebar() -> None:
    """
    Crea el indicador en el sidebar.

    El placeholder permite que una lectura realizada más tarde,
    dentro de cualquier módulo, actualice el texto en la misma
    ejecución de Streamlit.
    """
    placeholder = st.empty()

    st.session_state[
        CLAVE_PLACEHOLDER
    ] = placeholder

    placeholder.caption(
        _texto_ultima_actualizacion()
    )


def registrar_version_fuente(
    fuente: str,
    version: object,
) -> bool:
    """
    Registra una nueva versión física/remota de una fuente.

    La hora general solo cambia cuando la versión detectada es
    distinta de la última versión conocida para esa fuente.

    Devuelve True si se detectó una actualización real.
    """
    clave_fuente = str(
        fuente or ""
    ).strip()

    if not clave_fuente:
        return False

    version_texto = str(
        version if version is not None else ""
    )

    versiones = st.session_state.setdefault(
        CLAVE_VERSIONES_FUENTES,
        {},
    )

    version_anterior = versiones.get(
        clave_fuente
    )

    versiones[
        clave_fuente
    ] = version_texto

    # La primera lectura válida se considera el estado inicial
    # de datos de la sesión y también deja una referencia visible.
    cambio = (
        version_anterior is None
        or version_anterior != version_texto
    )

    if not cambio:
        return False

    st.session_state[
        CLAVE_ULTIMA_ACTUALIZACION
    ] = _ahora_buenos_aires()

    placeholder = st.session_state.get(
        CLAVE_PLACEHOLDER
    )

    if placeholder is not None:
        try:
            placeholder.caption(
                _texto_ultima_actualizacion()
            )
        except Exception:
            pass

    return True


def obtener_ultima_actualizacion():
    return st.session_state.get(
        CLAVE_ULTIMA_ACTUALIZACION
    )
