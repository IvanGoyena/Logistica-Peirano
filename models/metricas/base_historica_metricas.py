"""
Base histórica compartida entre Métricas y otros módulos.

Métricas actúa como productor:
- ejecuta la ETL;
- prepara las bases enriquecidas;
- publica tareas y detalle en Parquet.

Stock y futuros módulos actúan como consumidores:
- leen el Parquet;
- no vuelven a ejecutar la ETL histórica.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import pandas as pd

from config import CARPETA_DATOS


NOMBRE_CARPETA_CACHE = "_cache_metricas"
NOMBRE_TAREAS = "metricas_tareas_enriquecidas.parquet"
NOMBRE_DETALLE = "metricas_detalle_enriquecido.parquet"
NOMBRE_METADATA = "metricas_base_metadata.json"


def carpeta_base_historica(
    carpeta_datos: str | Path = CARPETA_DATOS,
) -> Path:
    return Path(carpeta_datos) / NOMBRE_CARPETA_CACHE


def rutas_base_historica(
    carpeta_datos: str | Path = CARPETA_DATOS,
) -> dict[str, Path]:
    carpeta = carpeta_base_historica(carpeta_datos)
    return {
        "carpeta": carpeta,
        "tareas": carpeta / NOMBRE_TAREAS,
        "detalle": carpeta / NOMBRE_DETALLE,
        "metadata": carpeta / NOMBRE_METADATA,
    }


def _firma_serializable(valor):
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, dict):
        return {
            str(clave): _firma_serializable(contenido)
            for clave, contenido in sorted(
                valor.items(),
                key=lambda item: str(item[0]),
            )
        }
    if isinstance(valor, (list, tuple, set)):
        return [_firma_serializable(item) for item in valor]
    return str(valor)


def hash_firma_historicos(firma_historicos) -> str:
    contenido = json.dumps(
        _firma_serializable(firma_historicos),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        contenido.encode("utf-8")
    ).hexdigest()


def leer_metadata_base_historica(
    carpeta_datos: str | Path = CARPETA_DATOS,
) -> dict:
    ruta = rutas_base_historica(carpeta_datos)["metadata"]

    if not ruta.exists():
        return {}

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            contenido = json.load(archivo)
        return contenido if isinstance(contenido, dict) else {}
    except Exception:
        return {}


def base_historica_disponible(
    carpeta_datos: str | Path = CARPETA_DATOS,
) -> bool:
    rutas = rutas_base_historica(carpeta_datos)
    return (
        rutas["tareas"].exists()
        and rutas["detalle"].exists()
        and rutas["metadata"].exists()
    )


def firma_base_historica_metricas(
    carpeta_datos: str | Path = CARPETA_DATOS,
) -> tuple:
    """
    Firma liviana para invalidar las cachés consumidoras.

    No abre los Parquet; solamente inspecciona metadata, tamaño y modificación.
    """

    rutas = rutas_base_historica(carpeta_datos)

    if not base_historica_disponible(carpeta_datos):
        return ("BASE_METRICAS_NO_DISPONIBLE",)

    metadata = leer_metadata_base_historica(carpeta_datos)

    registros = [
        metadata.get("firma_historicos_hash", ""),
        metadata.get("publicado_en", ""),
    ]

    for clave in ("tareas", "detalle", "metadata"):
        ruta = rutas[clave]
        stat = ruta.stat()
        registros.append(
            (
                clave,
                str(ruta.resolve()),
                int(stat.st_size),
                int(stat.st_mtime_ns),
            )
        )

    return tuple(registros)


def _fecha_extrema(
    dataframe: pd.DataFrame,
    funcion: str,
) -> str | None:
    for candidato in ("Fecha", "FechaInicio", "FechaPickeo"):
        if candidato not in dataframe.columns:
            continue

        serie = pd.to_datetime(
            dataframe[candidato],
            errors="coerce",
        ).dropna()

        if serie.empty:
            continue

        valor = serie.min() if funcion == "min" else serie.max()
        return valor.isoformat()

    return None


def _escribir_parquet_atomico(
    dataframe: pd.DataFrame,
    destino: Path,
) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)

    temporal = destino.with_name(
        f".{destino.stem}.{os.getpid()}.{uuid4().hex}.tmp.parquet"
    )

    try:
        dataframe.to_parquet(
            temporal,
            index=False,
            compression="snappy",
        )
        temporal.replace(destino)
    except ImportError as error:
        temporal.unlink(missing_ok=True)
        raise RuntimeError(
            "Para publicar la base histórica se necesita pyarrow. "
            "Agregá `pyarrow` al requirements.txt."
        ) from error
    except Exception:
        temporal.unlink(missing_ok=True)
        raise


def _escribir_json_atomico(
    contenido: dict,
    destino: Path,
) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)

    temporal = destino.with_name(
        f".{destino.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )

    try:
        with temporal.open("w", encoding="utf-8") as archivo:
            json.dump(
                contenido,
                archivo,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        temporal.replace(destino)
    except Exception:
        temporal.unlink(missing_ok=True)
        raise


def publicar_base_historica_metricas(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
    firma_historicos,
    carpeta_datos: str | Path = CARPETA_DATOS,
    forzar: bool = False,
) -> dict:
    """
    Publica la base analítica solamente cuando cambió el histórico.

    La comparación se realiza contra el hash de la firma de los archivos
    mensuales. Los cambios de filtros o navegación no reescriben el Parquet.
    """

    if tareas is None or detalle is None:
        raise ValueError(
            "Las bases de tareas y detalle no pueden ser None."
        )

    rutas = rutas_base_historica(carpeta_datos)
    rutas["carpeta"].mkdir(parents=True, exist_ok=True)

    firma_hash = hash_firma_historicos(
        firma_historicos
    )
    metadata_anterior = leer_metadata_base_historica(
        carpeta_datos
    )

    misma_version = (
        not forzar
        and base_historica_disponible(carpeta_datos)
        and metadata_anterior.get(
            "firma_historicos_hash"
        ) == firma_hash
    )

    if misma_version:
        return {
            **metadata_anterior,
            "actualizado": False,
        }

    _escribir_parquet_atomico(
        tareas,
        rutas["tareas"],
    )
    _escribir_parquet_atomico(
        detalle,
        rutas["detalle"],
    )

    metadata = {
        "version": 1,
        "publicado_en": datetime.now().isoformat(timespec="seconds"),
        "firma_historicos_hash": firma_hash,
        "filas_tareas": int(len(tareas)),
        "filas_detalle": int(len(detalle)),
        "fecha_minima": (
            _fecha_extrema(detalle, "min")
            or _fecha_extrema(tareas, "min")
        ),
        "fecha_maxima": (
            _fecha_extrema(detalle, "max")
            or _fecha_extrema(tareas, "max")
        ),
        "archivo_tareas": rutas["tareas"].name,
        "archivo_detalle": rutas["detalle"].name,
    }

    _escribir_json_atomico(
        metadata,
        rutas["metadata"],
    )

    return {
        **metadata,
        "actualizado": True,
    }


def _columnas_existentes_parquet(
    ruta: Path,
) -> list[str] | None:
    try:
        import pyarrow.parquet as pq

        return list(
            pq.ParquetFile(ruta).schema.names
        )
    except Exception:
        return None


def _leer_parquet_columnas(
    ruta: Path,
    columnas: Iterable[str] | None = None,
) -> pd.DataFrame:
    columnas_solicitadas = (
        list(dict.fromkeys(columnas))
        if columnas is not None
        else None
    )

    if columnas_solicitadas:
        disponibles = _columnas_existentes_parquet(
            ruta
        )

        if disponibles is not None:
            columnas_solicitadas = [
                columna
                for columna in columnas_solicitadas
                if columna in disponibles
            ]

            if not columnas_solicitadas:
                return pd.DataFrame()

    return pd.read_parquet(
        ruta,
        columns=columnas_solicitadas,
    )


def leer_base_historica_metricas(
    carpeta_datos: str | Path = CARPETA_DATOS,
    columnas_tareas: Iterable[str] | None = None,
    columnas_detalle: Iterable[str] | None = None,
    incluir_tareas: bool = True,
    incluir_detalle: bool = True,
) -> dict:
    """
    Lee la base publicada.

    Los consumidores pueden solicitar solamente las columnas necesarias,
    reduciendo memoria, transferencia y tiempo de apertura.
    """

    rutas = rutas_base_historica(carpeta_datos)

    if not base_historica_disponible(carpeta_datos):
        raise FileNotFoundError(
            "Todavía no existe la base histórica publicada. "
            "Abrí el módulo Métricas y presioná Actualizar."
        )

    resultado = {
        "metadata": leer_metadata_base_historica(
            carpeta_datos
        ),
    }

    if incluir_tareas:
        resultado["tareas"] = _leer_parquet_columnas(
            rutas["tareas"],
            columnas_tareas,
        )

    if incluir_detalle:
        resultado["detalle"] = _leer_parquet_columnas(
            rutas["detalle"],
            columnas_detalle,
        )

    return resultado
