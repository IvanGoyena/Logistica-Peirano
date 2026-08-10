from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from config import (
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo


# ==========================================================
# FUENTES DEL MODULO TAREAS
# ==========================================================

FUENTES_DINAMICAS = {
    "tareas": (
        CARPETA_WMS,
        "Informe Tareas",
        False,
    ),
    "pedidos": (
        CARPETA_WMS,
        "Pedidos DIGIP",
        False,
    ),
    "detalle": (
        CARPETA_ERP,
        "Detalle Pendientes",
        False,
    ),
}

FUENTES_MAESTRAS = {
    "clientes": (
        CARPETA_MAESTROS,
        "Maestro Clientes",
        True,
    ),
    "articulos": (
        CARPETA_MAESTROS,
        "Maestro Articulo",
        True,
    ),
    "volumetria": (
        CARPETA_MAESTROS,
        "Maestro Volumetria",
        True,
    ),
}


# ==========================================================
# LECTURA DE FUENTES
# ==========================================================

@st.cache_data(
    ttl=270,
    show_spinner=False,
)
def _leer_dinamicas() -> dict[str, pd.DataFrame]:
    return {
        clave: leer_archivo(
            carpeta,
            nombre,
            cache=cache,
        )
        for clave, (
            carpeta,
            nombre,
            cache,
        ) in FUENTES_DINAMICAS.items()
    }


@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def _leer_maestras() -> dict[str, pd.DataFrame]:
    return {
        clave: leer_archivo(
            carpeta,
            nombre,
            cache=cache,
        )
        for clave, (
            carpeta,
            nombre,
            cache,
        ) in FUENTES_MAESTRAS.items()
    }


# ==========================================================
# HISTORICO DE CONTROL
# ==========================================================

def _leer_archivo_control(
    ruta: Path,
) -> pd.DataFrame:
    extension = ruta.suffix.lower()

    if extension == ".csv":
        # sep=None permite detectar coma,
        # punto y coma o tabulación.
        return pd.read_csv(
            ruta,
            sep=None,
            engine="python",
            encoding="utf-8-sig",
        )

    if extension in {
        ".xlsx",
        ".xls",
        ".xlsm",
    }:
        return pd.read_excel(
            ruta
        )

    return pd.DataFrame()


@st.cache_data(
    ttl=270,
    show_spinner=False,
)
def _leer_historico_control() -> pd.DataFrame:
    """
    Consolida los archivos mensuales cuyo
    nombre comienza con Control dentro de
    Data_WMS.

    Ejemplos admitidos:
    - Control Agosto 2026.csv
    - Control Julio 2026.xlsx
    - Control_2026_08.csv

    La deduplicación definitiva se realiza
    en el modelo mediante ControlContenedorId,
    porque el archivo puede contener varias
    líneas de artículos por un mismo control.
    """

    carpeta = Path(
        CARPETA_WMS
    )

    if not carpeta.exists():
        return pd.DataFrame()

    rutas: list[Path] = []

    for patron in (
        "Control*.csv",
        "Control*.xlsx",
        "Control*.xls",
        "Control*.xlsm",
        "control*.csv",
        "control*.xlsx",
        "control*.xls",
        "control*.xlsm",
    ):
        rutas.extend(
            carpeta.glob(
                patron
            )
        )

    # Evita duplicados por patrones
    # con diferente capitalización.
    rutas_unicas = sorted(
        {
            ruta.resolve()
            for ruta in rutas
            if ruta.is_file()
        },
        key=lambda ruta: (
            ruta.name.lower()
        ),
    )

    tablas: list[pd.DataFrame] = []

    for ruta in rutas_unicas:
        try:
            tabla = (
                _leer_archivo_control(
                    ruta
                )
            )
        except Exception:
            continue

        if (
            tabla is None
            or tabla.empty
        ):
            continue

        tabla = tabla.copy()

        tabla[
            "ArchivoOrigenControl"
        ] = ruta.name

        tablas.append(
            tabla
        )

    if not tablas:
        return pd.DataFrame()

    return pd.concat(
        tablas,
        ignore_index=True,
        sort=False,
    )


# ==========================================================
# RESPALDO EN SESSION STATE
# ==========================================================

def _recuperar_fuente(
    clave: str,
    dataframe: pd.DataFrame | None,
    nombre_visible: str,
) -> tuple[
    pd.DataFrame,
    bool,
    str | None,
]:
    clave_session = (
        f"tareas_fuente_valida_{clave}"
    )

    if (
        dataframe is not None
        and not dataframe.empty
    ):
        st.session_state[
            clave_session
        ] = dataframe.copy()

        return (
            dataframe.copy(),
            True,
            None,
        )

    respaldo = (
        st.session_state.get(
            clave_session
        )
    )

    if (
        isinstance(
            respaldo,
            pd.DataFrame,
        )
        and not respaldo.empty
    ):
        return (
            respaldo.copy(),
            False,
            (
                f"{nombre_visible}: "
                "se conserva la última "
                "versión válida."
            ),
        )

    return (
        pd.DataFrame(),
        False,
        (
            f"{nombre_visible}: "
            "no hay una versión válida "
            "disponible."
        ),
    )


# ==========================================================
# CARGA GENERAL DEL MODULO
# ==========================================================

def cargar_fuentes_tareas() -> dict[str, object]:
    mensajes: list[str] = []
    fuentes: dict[
        str,
        pd.DataFrame,
    ] = {}

    actualizaciones_criticas: list[
        bool
    ] = []

    try:
        dinamicas = (
            _leer_dinamicas()
        )
    except Exception as error:
        dinamicas = {}

        mensajes.append(
            "Fuentes operativas: "
            f"{type(error).__name__}."
        )

    try:
        maestras = (
            _leer_maestras()
        )
    except Exception as error:
        maestras = {}

        mensajes.append(
            "Maestros: "
            f"{type(error).__name__}."
        )

    definiciones = {
        **FUENTES_DINAMICAS,
        **FUENTES_MAESTRAS,
    }

    origenes = {
        **dinamicas,
        **maestras,
    }

    for (
        clave,
        (
            _carpeta,
            nombre,
            _cache,
        ),
    ) in definiciones.items():

        tabla, actualizada, mensaje = (
            _recuperar_fuente(
                clave,
                origenes.get(
                    clave
                ),
                nombre,
            )
        )

        fuentes[
            clave
        ] = tabla

        actualizaciones_criticas.append(
            actualizada
        )

        if mensaje:
            mensajes.append(
                mensaje
            )

    # El histórico de Control es
    # complementario: si falta, el tablero
    # continúa funcionando y solamente
    # omite las unidades cerradas.
    try:
        control_origen = (
            _leer_historico_control()
        )
    except Exception as error:
        control_origen = (
            pd.DataFrame()
        )

        mensajes.append(
            "Histórico de Control: "
            f"{type(error).__name__}."
        )

    (
        control,
        _,
        mensaje_control,
    ) = _recuperar_fuente(
        "control_historico",
        control_origen,
        "Histórico de Control",
    )

    fuentes[
        "control_historico"
    ] = control

    if (
        mensaje_control
        and control.empty
    ):
        mensajes.append(
            mensaje_control
        )

    return {
        "fuentes": fuentes,
        "actualizacion_completa": (
            all(
                actualizaciones_criticas
            )
        ),
        "mensajes": mensajes,
        "hora_actualizacion": (
            datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S"
            )
        ),
    }


# ==========================================================
# INVALIDACION DE CACHE
# ==========================================================

def invalidar_cache_tareas() -> None:
    _leer_dinamicas.clear()
    _leer_maestras.clear()
    _leer_historico_control.clear()
