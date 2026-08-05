"""
Lectura optimizada de históricos para el módulo de Métricas.

Estrategia:
- Cada archivo mensual se lee y cachea por separado.
- Los meses cerrados permanecen persistidos en disco.
- El mes actual usa una caché corta y puede invalidarse manualmente.
- La firma de archivos permite que Streamlit reconstruya la ETL únicamente
  cuando cambia algún archivo real.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import unicodedata

import pandas as pd
import streamlit as st


EXTENSIONES_PERMITIDAS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".xlsm",
}

MESES_NUMERO = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


def normalizar_nombre_archivo(valor: object) -> str:
    """Normaliza nombres para localizar archivos sin depender de tildes."""

    texto = str(valor).strip().upper()

    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def _leer_archivo_historico_sin_cache(
    ruta_archivo: str | Path,
) -> pd.DataFrame:
    """Lee físicamente un CSV o Excel histórico."""

    ruta_archivo = Path(ruta_archivo)
    extension = ruta_archivo.suffix.lower()

    if extension == ".csv":
        configuraciones = [
            {
                "sep": None,
                "engine": "python",
                "encoding": "utf-8-sig",
            },
            {
                "sep": ";",
                "engine": "python",
                "encoding": "latin-1",
            },
            {
                "sep": ",",
                "engine": "python",
                "encoding": "latin-1",
            },
        ]

        errores = []

        for configuracion in configuraciones:
            try:
                return pd.read_csv(
                    ruta_archivo,
                    **configuracion,
                )
            except Exception as error:
                errores.append(str(error))

        raise RuntimeError(
            f"No se pudo leer {ruta_archivo.name}. "
            + " | ".join(errores)
        )

    if extension in {".xlsx", ".xls", ".xlsm"}:
        return pd.read_excel(ruta_archivo)

    raise ValueError(
        f"Extensión no soportada: {ruta_archivo.name}"
    )


@st.cache_data(
    persist="disk",
    max_entries=120,
    show_spinner=False,
)
def _leer_archivo_mes_cerrado(
    ruta: str,
    tamanio: int,
    modificacion_ns: int,
) -> pd.DataFrame:
    """
    Lee un archivo de un mes cerrado.

    tamanio y modificacion_ns forman parte de la clave de caché. Si un archivo
    histórico fuera reemplazado excepcionalmente, se generará una nueva entrada.
    """

    _ = tamanio, modificacion_ns
    return _leer_archivo_historico_sin_cache(ruta)


@st.cache_data(
    ttl=120,
    max_entries=12,
    show_spinner=False,
)
def _leer_archivo_mes_actual(
    ruta: str,
    tamanio: int,
    modificacion_ns: int,
) -> pd.DataFrame:
    """Lee el archivo vivo del mes actual con una caché breve."""

    _ = tamanio, modificacion_ns
    return _leer_archivo_historico_sin_cache(ruta)


def extraer_periodo_archivo(
    ruta_archivo: str | Path,
) -> tuple[int | None, int | None]:
    """
    Extrae año y mes desde nombres como:
    - Preparacion Julio 2026.csv
    - Control 07 2026.xlsx

    Cuando el nombre no contiene período, devuelve (None, None).
    """

    ruta = Path(ruta_archivo)
    texto = normalizar_nombre_archivo(ruta.stem)

    anio_match = re.search(r"\b(20\d{2})\b", texto)
    anio = int(anio_match.group(1)) if anio_match else None

    mes = None
    for nombre, numero in MESES_NUMERO.items():
        if re.search(rf"\b{nombre}\b", texto):
            mes = numero
            break

    if mes is None:
        candidatos = re.findall(r"\b(0?[1-9]|1[0-2])\b", texto)
        if candidatos:
            mes = int(candidatos[-1])

    return anio, mes


def es_archivo_mes_actual(
    ruta_archivo: str | Path,
    ahora: datetime | None = None,
) -> bool:
    """
    Determina si el archivo pertenece al mes actual.

    Si el nombre no contiene año/mes, usa la fecha de modificación como respaldo.
    """

    ahora = ahora or datetime.now()
    ruta = Path(ruta_archivo)
    anio, mes = extraer_periodo_archivo(ruta)

    if anio is not None and mes is not None:
        return anio == ahora.year and mes == ahora.month

    fecha_modificacion = datetime.fromtimestamp(
        ruta.stat().st_mtime
    )
    return (
        fecha_modificacion.year == ahora.year
        and fecha_modificacion.month == ahora.month
    )


def firma_archivo(
    ruta_archivo: str | Path,
) -> tuple[str, int, int]:
    """Firma estable para detectar reemplazos o modificaciones."""

    ruta = Path(ruta_archivo)
    estadisticas = ruta.stat()

    return (
        str(ruta.resolve()),
        int(estadisticas.st_size),
        int(estadisticas.st_mtime_ns),
    )


def leer_archivo_historico(
    ruta_archivo: str | Path,
) -> pd.DataFrame:
    """
    Lee un archivo mediante la caché apropiada según su período.
    """

    ruta = Path(ruta_archivo)
    ruta_str, tamanio, modificacion_ns = firma_archivo(ruta)

    if es_archivo_mes_actual(ruta):
        return _leer_archivo_mes_actual(
            ruta_str,
            tamanio,
            modificacion_ns,
        )

    return _leer_archivo_mes_cerrado(
        ruta_str,
        tamanio,
        modificacion_ns,
    )


def buscar_archivos_historicos(
    carpeta: str | Path,
    prefijo: str,
) -> list[Path]:
    """Busca los archivos mensuales de un proceso."""

    carpeta = Path(carpeta)

    if not carpeta.exists():
        raise FileNotFoundError(
            f"No existe la carpeta: {carpeta}"
        )

    prefijo_normalizado = normalizar_nombre_archivo(
        prefijo
    )

    archivos = [
        archivo
        for archivo in carpeta.iterdir()
        if (
            archivo.is_file()
            and archivo.suffix.lower() in EXTENSIONES_PERMITIDAS
            and normalizar_nombre_archivo(
                archivo.stem
            ).startswith(prefijo_normalizado)
        )
    ]

    return sorted(
        archivos,
        key=lambda archivo: archivo.name.upper(),
    )


def firma_fuentes_metricas(
    carpeta: str | Path,
) -> tuple:
    """
    Devuelve una firma hashable de todos los históricos.

    Streamlit la utiliza como argumento de cargar_metricas(). Mientras los
    archivos no cambien, devuelve inmediatamente la ETL cacheada.
    """

    registros = []

    for prefijo in ("Control", "Preparacion"):
        for archivo in buscar_archivos_historicos(
            carpeta=carpeta,
            prefijo=prefijo,
        ):
            ruta, tamanio, modificacion_ns = firma_archivo(
                archivo
            )
            registros.append(
                (
                    prefijo,
                    archivo.name,
                    ruta,
                    tamanio,
                    modificacion_ns,
                    es_archivo_mes_actual(archivo),
                )
            )

    return tuple(registros)


def leer_historico_proceso(
    carpeta: str | Path,
    prefijo: str,
    proceso: str,
) -> pd.DataFrame:
    """
    Consolida únicamente los archivos del proceso indicado.

    La lectura de cada archivo queda cacheada individualmente.
    """

    archivos = buscar_archivos_historicos(
        carpeta=carpeta,
        prefijo=prefijo,
    )

    dataframes = []

    for archivo in archivos:
        try:
            dataframe = leer_archivo_historico(
                archivo
            )
        except Exception as error:
            raise RuntimeError(
                f"Error leyendo {archivo.name}: {error}"
            ) from error

        dataframe = dataframe.copy()
        dataframe["ArchivoOrigen"] = archivo.name
        dataframe["Proceso"] = proceso
        dataframes.append(dataframe)

    if not dataframes:
        return pd.DataFrame()

    return pd.concat(
        dataframes,
        ignore_index=True,
        sort=False,
    )


def leer_historico_controles(
    carpeta: str | Path,
) -> pd.DataFrame:
    """Devuelve el histórico crudo de Control."""

    return leer_historico_proceso(
        carpeta=carpeta,
        prefijo="Control",
        proceso="CONTROL",
    )


def leer_historico_preparaciones(
    carpeta: str | Path,
) -> pd.DataFrame:
    """Devuelve el histórico crudo de Preparación."""

    return leer_historico_proceso(
        carpeta=carpeta,
        prefijo="Preparacion",
        proceso="PREPARACION",
    )


def construir_fuentes_metricas(
    carpeta: str | Path,
) -> dict[str, pd.DataFrame]:
    """Devuelve las fuentes de Control y Preparación."""

    return {
        "control": leer_historico_controles(carpeta),
        "preparacion": leer_historico_preparaciones(carpeta),
    }


def limpiar_cache_mes_actual_metricas() -> None:
    """
    Invalida solamente la lectura del mes actual.

    No elimina la caché persistente de los meses cerrados.
    """

    _leer_archivo_mes_actual.clear()


def construir_base_metricas(
    carpeta: str | Path,
) -> dict[str, pd.DataFrame]:
    """Alias compatible con la implementación original."""

    return construir_fuentes_metricas(carpeta)
