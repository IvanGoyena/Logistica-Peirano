"""
Lectura de históricos para el módulo de métricas.

Este módulo:
- Localiza los archivos mensuales de Control.
- Localiza los archivos mensuales de Preparación.
- Lee y consolida cada proceso por separado.
- No mezcla Control con Preparación.
- No realiza limpieza analítica.
"""

from pathlib import Path
import unicodedata

import pandas as pd


EXTENSIONES_PERMITIDAS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".xlsm",
}


def normalizar_nombre_archivo(valor: object) -> str:
    """Normaliza nombres para localizar archivos sin depender de tildes."""

    texto = str(valor).strip().upper()

    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def leer_archivo_historico(
    ruta_archivo: str | Path,
) -> pd.DataFrame:
    """Lee un CSV o Excel histórico."""

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

        return pd.read_excel(
            ruta_archivo
        )

    raise ValueError(
        f"Extensión no soportada: {ruta_archivo.name}"
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


def leer_historico_proceso(
    carpeta: str | Path,
    prefijo: str,
    proceso: str,
) -> pd.DataFrame:
    """
    Consolida únicamente los archivos del proceso indicado.
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
    """
    Devuelve las dos fuentes separadas.

    Resultado:
        {
            "control": DataFrame,
            "preparacion": DataFrame,
        }
    """

    return {
        "control": leer_historico_controles(
            carpeta
        ),
        "preparacion": leer_historico_preparaciones(
            carpeta
        ),
    }


def construir_base_metricas(
    carpeta: str | Path,
) -> dict[str, pd.DataFrame]:
    """
    Alias compatible con el nombre utilizado inicialmente.

    Ya no devuelve un único DataFrame:
    devuelve un diccionario con ambos procesos separados.
    """

    return construir_fuentes_metricas(
        carpeta
    )
