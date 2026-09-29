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
    Fuente de control para Operación en vivo.

    Consolida, en este orden de prioridad:
      1) histórico consolidado (.csv/.xlsx y también .csv.tmp)
      2) archivo mensual Filtrar Preparacion
      3) ventana reciente Ultimos 7 Dias

    La fuente más reciente queda última y gana al deduplicar.
    """
    carpeta = Path(CARPETA_WMS)
    if not carpeta.exists():
        return pd.DataFrame()

    def _leer(ruta: Path) -> pd.DataFrame:
        try:
            nombre = ruta.name.lower()
            if nombre.endswith(".csv") or nombre.endswith(".csv.tmp") or nombre.endswith(".tmp"):
                return pd.read_csv(
                    ruta,
                    sep=None,
                    engine="python",
                    encoding="utf-8-sig",
                )
            if ruta.suffix.lower() in {".xlsx", ".xls", ".xlsm"}:
                return pd.read_excel(ruta)
        except Exception:
            return pd.DataFrame()
        return pd.DataFrame()

    rutas: list[tuple[int, Path]] = []

    # 1. Histórico. Incluye el .tmp que genera el proceso de consolidación.
    for nombre in (
        "Historico Filtrar Preparaciones.csv",
        "Historico Filtrar Preparaciones.csv.tmp",
        "Historico Filtrar Preparaciones.xlsx",
        "Histórico Filtrar Preparaciones.csv",
        "Histórico Filtrar Preparaciones.csv.tmp",
        "Histórico Filtrar Preparaciones.xlsx",
    ):
        r = carpeta / nombre
        if r.exists() and r.is_file():
            rutas.append((10, r))

    # 2. Mensuales guardados.
    for patron in (
        "Filtrar Preparacion*.csv",
        "Filtrar Preparacion*.xlsx",
        "Filtrar Preparación*.csv",
        "Filtrar Preparación*.xlsx",
    ):
        for r in carpeta.glob(patron):
            nom = r.name.lower()
            if "ultimos 7 dias" in nom or "últimos 7 días" in nom:
                continue
            rutas.append((20, r))

    # 3. Ventana reciente: máxima prioridad.
    for patron in (
        "Filtrar Preparacion Ultimos 7 Dias*.csv",
        "Filtrar Preparacion Ultimos 7 Dias*.xlsx",
        "Filtrar Preparación Ultimos 7 Dias*.csv",
        "Filtrar Preparación Últimos 7 Días*.csv",
    ):
        for r in carpeta.glob(patron):
            rutas.append((30, r))

    # Evitar leer dos veces la misma ruta.
    unicas: dict[str, tuple[int, Path]] = {}
    for prioridad, ruta in rutas:
        clave = str(ruta.resolve()).lower()
        anterior = unicas.get(clave)
        if anterior is None or prioridad > anterior[0]:
            unicas[clave] = (prioridad, ruta)

    tablas = []
    for prioridad, ruta in sorted(
        unicas.values(),
        key=lambda x: (x[0], x[1].stat().st_mtime if x[1].exists() else 0),
    ):
        df = _leer(ruta)
        if df is None or df.empty:
            continue

        df = df.copy()
        df.columns = [
            str(c).replace("\ufeff", "").strip()
            for c in df.columns
        ]

        # Sólo sirve como fuente de control si identifica la preparación.
        if "Id" not in df.columns:
            continue

        df["_PrioridadFuente"] = prioridad
        df["_MTimeFuente"] = ruta.stat().st_mtime
        df["ArchivoOrigenPreparacion"] = ruta.name
        tablas.append(df)

    if not tablas:
        return pd.DataFrame()

    total = pd.concat(tablas, ignore_index=True, sort=False)

    def _key(serie: pd.Series) -> pd.Series:
        return (
            serie.astype("string")
            .fillna("")
            .str.strip()
            .str.replace(r"\.0+$", "", regex=True)
        )

    # Claves normalizadas para que 123 y 123.0 sean iguales.
    total["_PrepKey"] = _key(total["Id"])
    if "ContenedorId" in total.columns:
        total["_ContKey"] = _key(total["ContenedorId"])
    else:
        total["_ContKey"] = ""

    if "TareaId" in total.columns:
        total["_TareaKey"] = _key(total["TareaId"])
    else:
        total["_TareaKey"] = ""

    if "ContenedorDetalleId" in total.columns:
        total["_DetalleKey"] = _key(total["ContenedorDetalleId"])
    else:
        total["_DetalleKey"] = ""

    # Orden: histórico -> mensual -> últimos 7 días; dentro de cada fuente,
    # el archivo más nuevo gana.
    total = total.sort_values(
        ["_PrioridadFuente", "_MTimeFuente"],
        kind="stable",
    )

    # Una fila física de detalle no debe duplicarse entre histórico/mensual/reciente.
    con_detalle = total["_DetalleKey"].ne("")
    parte_detalle = (
        total.loc[con_detalle]
        .drop_duplicates("_DetalleKey", keep="last")
    )

    # Si no existe ContenedorDetalleId, deduplicamos de forma conservadora
    # por preparación + contenedor + tarea, conservando la versión más reciente.
    parte_sin = total.loc[~con_detalle].copy()
    if not parte_sin.empty:
        clave_fallback = ["_PrepKey", "_ContKey", "_TareaKey"]
        parte_sin = parte_sin.drop_duplicates(clave_fallback, keep="last")

    total = pd.concat(
        [parte_detalle, parte_sin],
        ignore_index=True,
        sort=False,
    )

    return total.drop(
        columns=[
            "_PrioridadFuente",
            "_MTimeFuente",
            "_PrepKey",
            "_ContKey",
            "_TareaKey",
            "_DetalleKey",
        ],
        errors="ignore",
    ).reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def _leer_preparaciones_recientes_directo() -> pd.DataFrame:
    """Lee DIRECTAMENTE el archivo más nuevo de Filtrar Preparacion Ultimos 7 Dias.

    Esta fuente no se mezcla ni deduplica con históricos. Se usa para obtener
    usuario y fecha/hora real de los controles recientes.
    """
    carpeta = Path(CARPETA_WMS)
    if not carpeta.exists():
        return pd.DataFrame()

    candidatos: list[Path] = []
    patrones = (
        "Filtrar Preparacion Ultimos 7 Dias*.csv",
        "Filtrar Preparacion Ultimos 7 Dias*.xlsx",
        "Filtrar Preparación Ultimos 7 Dias*.csv",
        "Filtrar Preparación Últimos 7 Días*.csv",
        "Filtrar Preparación Últimos 7 Días*.xlsx",
    )
    for patron in patrones:
        candidatos.extend(r for r in carpeta.glob(patron) if r.is_file())

    if not candidatos:
        return pd.DataFrame()

    # El archivo físicamente más reciente es la fuente autoritativa.
    ruta = max(candidatos, key=lambda r: r.stat().st_mtime)

    try:
        if ruta.suffix.lower() == ".csv":
            df = pd.read_csv(
                ruta,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
            )
        else:
            df = pd.read_excel(ruta)
    except Exception:
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(x).replace("\ufeff", "").strip() for x in df.columns]

    # Sin Id no sirve para cruzar con PreparacionId.
    if "Id" not in df.columns:
        return pd.DataFrame()

    df["ArchivoOrigenPreparacionReciente"] = ruta.name
    return df.reset_index(drop=True)


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

    # Filtrar Preparaciones también es fuente operativa:
    # aporta quién controló y cuándo.
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

    # Fuente DIRECTA de controles recientes. No pasa por el consolidador histórico.
    # Es la que usa principal.py para resolver hora/usuario de los últimos controles.
    try:
        prep_reciente_directo = _leer_preparaciones_recientes_directo()
    except Exception as error:
        prep_reciente_directo = pd.DataFrame()
        mensajes.append(
            "Filtrar Preparacion Ultimos 7 Dias directo: "
            f"{type(error).__name__}."
        )

    fuentes["preparaciones_recientes"] = prep_reciente_directo

    if incluir_estadisticas:
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
    _leer_preparaciones_recientes_directo.clear()
    _leer_analitico_preparacion.clear()
    _leer_ubicaciones_score.clear()
