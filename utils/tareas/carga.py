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




@st.cache_data(ttl=3600, show_spinner=False)
def _leer_ubicaciones_score() -> pd.DataFrame:
    """Maestro de Ubicaciones, cargado solo al entrar a Estadísticas."""
    try:
        return leer_archivo(CARPETA_MAESTROS, "Maestro Ubicaciones", cache=True)
    except Exception:
        return pd.DataFrame()


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
# HISTORICO FILTRAR PREPARACION
# ==========================================================

@st.cache_data(ttl=270, show_spinner=False)
def _leer_historico_preparaciones() -> pd.DataFrame:
    """
    Lee UNA única fuente consolidada de Filtrar Preparaciones.

    El descargador consulta DIGIP por una ventana corta y mantiene:
        Data_WMS/Historico Filtrar Preparaciones.csv

    No se deben concatenar:
        - Filtrar Preparacion Ultimos 7 Dias.csv
        - Filtrar Preparacion <Mes> <Año>.csv

    porque son copias parciales/snapshots del mismo origen y provocarían
    reprocesamiento y riesgo de mezclar versiones de una misma fila.
    """
    carpeta = Path(CARPETA_WMS)

    if not carpeta.exists():
        return pd.DataFrame()

    candidatos = [
        carpeta / "Historico Filtrar Preparaciones.csv",
        carpeta / "Historico Filtrar Preparaciones.xlsx",
        carpeta / "Histórico Filtrar Preparaciones.csv",
        carpeta / "Histórico Filtrar Preparaciones.xlsx",
    ]

    ruta = next(
        (r for r in candidatos if r.exists() and r.is_file()),
        None,
    )

    if ruta is None:
        return pd.DataFrame()

    try:
        if ruta.suffix.lower() == ".csv":
            tabla = pd.read_csv(
                ruta,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
            )
        else:
            tabla = pd.read_excel(ruta)
    except Exception:
        return pd.DataFrame()

    if tabla is None or tabla.empty:
        return pd.DataFrame()

    tabla = tabla.copy()
    tabla["ArchivoOrigenPreparacion"] = ruta.name

    # El histórico generado por el descargador ya viene consolidado.
    # Dejamos una protección extra por ContenedorDetalleId.
    if "ContenedorDetalleId" in tabla.columns:
        clave = (
            tabla["ContenedorDetalleId"]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.replace(r"\\.0+$", "", regex=True)
        )

        con_clave = tabla.loc[clave.ne("")].copy()
        sin_clave = tabla.loc[clave.eq("")].copy()

        if not con_clave.empty:
            con_clave["_ClaveHistorica"] = (
                con_clave["ContenedorDetalleId"]
                .astype("string")
                .fillna("")
                .str.strip()
                .str.replace(r"\\.0+$", "", regex=True)
            )
            con_clave = con_clave.drop_duplicates(
                subset=["_ClaveHistorica"],
                keep="last",
            ).drop(columns=["_ClaveHistorica"])

        tabla = pd.concat(
            [con_clave, sin_clave],
            ignore_index=True,
            sort=False,
        )

    return tabla.reset_index(drop=True)



# ==========================================================
# HISTORICO ANALITICO DE PREPARACION
# ==========================================================

@st.cache_data(ttl=270, show_spinner=False)
def _leer_analitico_preparacion() -> pd.DataFrame:
    """Consolida Preparacion <Mes> <Año>.*, excluyendo Filtrar Preparacion."""
    carpeta = Path(CARPETA_WMS)
    if not carpeta.exists():
        return pd.DataFrame()

    rutas = []
    for patron in (
        "Preparacion*.csv", "Preparación*.csv",
        "Preparacion*.xlsx", "Preparación*.xlsx",
        "preparacion*.csv", "preparación*.csv",
    ):
        rutas.extend(carpeta.glob(patron))

    rutas = sorted({r.resolve() for r in rutas if r.is_file() and not r.name.lower().startswith("filtrar")})
    tablas = []
    for ruta in rutas:
        try:
            if ruta.suffix.lower() == ".csv":
                t = pd.read_csv(ruta, sep=None, engine="python", encoding="utf-8-sig")
            else:
                t = pd.read_excel(ruta)
            if t is not None and not t.empty and "TareaId" in t.columns:
                t = t.copy()
                t["ArchivoOrigenAnaliticoPreparacion"] = ruta.name
                tablas.append(t)
        except Exception:
            continue
    if not tablas:
        return pd.DataFrame()
    total = pd.concat(tablas, ignore_index=True, sort=False)
    # Un TareaId contiene muchas líneas: deduplicamos solo filas idénticas, no la tarea.
    return total.drop_duplicates().reset_index(drop=True)

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

def cargar_fuentes_tareas(
    incluir_estadisticas: bool = False,
) -> dict[str, object]:
    """
    Carga las fuentes del módulo.

    incluir_estadisticas=False:
        carga solamente lo necesario para Operación en vivo.

    incluir_estadisticas=True:
        agrega Filtrar Preparación y Analítico de Preparación,
        que son históricos pesados usados únicamente por Estadísticas.
    """
    mensajes: list[str] = []
    fuentes: dict[str, pd.DataFrame] = {}
    actualizaciones_criticas: list[bool] = []

    try:
        dinamicas = _leer_dinamicas()
    except Exception as error:
        dinamicas = {}
        mensajes.append(
            "Fuentes operativas: "
            f"{type(error).__name__}."
        )

    try:
        maestras = _leer_maestras()
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

    for clave, (_carpeta, nombre, _cache) in definiciones.items():
        tabla, actualizada, mensaje = _recuperar_fuente(
            clave,
            origenes.get(clave),
            nombre,
        )

        fuentes[clave] = tabla
        actualizaciones_criticas.append(actualizada)

        if mensaje:
            mensajes.append(mensaje)

    # Control sigue siendo necesario para Operación en vivo.
    try:
        control_origen = _leer_historico_control()
    except Exception as error:
        control_origen = pd.DataFrame()
        mensajes.append(
            "Histórico de Control: "
            f"{type(error).__name__}."
        )

    control, _, mensaje_control = _recuperar_fuente(
        "control_historico",
        control_origen,
        "Histórico de Control",
    )
    fuentes["control_historico"] = control

    if mensaje_control and control.empty:
        mensajes.append(mensaje_control)

    # Los históricos pesados de Estadísticas NO se leen durante
    # Operación en vivo. Se cargan solamente al entrar a esa vista.
    if incluir_estadisticas:
        try:
            prep_origen = _leer_historico_preparaciones()
        except Exception as error:
            prep_origen = pd.DataFrame()
            mensajes.append(
                "Histórico Filtrar Preparacion: "
                f"{type(error).__name__}."
            )

        prep, _, mensaje_prep = _recuperar_fuente(
            "preparaciones_historico",
            prep_origen,
            "Histórico Filtrar Preparacion",
        )
        fuentes["preparaciones_historico"] = prep

        if mensaje_prep and prep.empty:
            mensajes.append(mensaje_prep)

        try:
            analitico_prep_origen = _leer_analitico_preparacion()
        except Exception as error:
            analitico_prep_origen = pd.DataFrame()
            mensajes.append(
                "Analítico Preparación: "
                f"{type(error).__name__}."
            )

        analitico_prep, _, mensaje_analitico_prep = _recuperar_fuente(
            "preparacion_analitico",
            analitico_prep_origen,
            "Analítico Preparación",
        )
        fuentes["preparacion_analitico"] = analitico_prep

        if mensaje_analitico_prep and analitico_prep.empty:
            mensajes.append(mensaje_analitico_prep)

        # El Score de Productividad necesita el layout físico, pero solo
        # dentro de Estadísticas para no encarecer Operación en vivo.
        fuentes["ubicaciones"] = _leer_ubicaciones_score()

    return {
        "fuentes": fuentes,
        "actualizacion_completa": all(actualizaciones_criticas),
        "mensajes": mensajes,
        "hora_actualizacion": datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        ),
    }


# ==========================================================
# INVALIDACION DE CACHE
# ==========================================================

def invalidar_cache_tareas() -> None:
    _leer_dinamicas.clear()
    _leer_maestras.clear()
    _leer_historico_control.clear()
    _leer_historico_preparaciones.clear()
    _leer_analitico_preparacion.clear()
    _leer_ubicaciones_score.clear()
