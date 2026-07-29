from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from utils.leer_datos import leer_archivo, fecha_archivo


EXTENSIONES_SOPORTADAS = (".csv", ".xlsx", ".xls", ".xlsm")


def _candidatos(nombres: str | Iterable[str]) -> list[str]:
    """Genera nombres posibles sin repetir, con y sin extensión."""
    if isinstance(nombres, str):
        nombres = [nombres]

    resultado: list[str] = []

    for nombre in nombres:
        nombre = str(nombre).strip()
        if not nombre:
            continue

        ruta = Path(nombre)
        extension = ruta.suffix.lower()
        base = str(ruta.with_suffix("")) if extension in EXTENSIONES_SOPORTADAS else nombre

        # Primero se prueba exactamente lo indicado.
        variantes = [nombre]

        # Luego el nombre base, para conservar compatibilidad con leer_archivo.
        if base != nombre:
            variantes.append(base)

        # Finalmente todos los formatos admitidos.
        variantes.extend(f"{base}{ext}" for ext in EXTENSIONES_SOPORTADAS)

        for variante in variantes:
            if variante not in resultado:
                resultado.append(variante)

    return resultado


def leer_archivo_flexible(
    carpeta: str,
    nombres: str | Iterable[str],
    *,
    cache: bool = False,
) -> tuple[pd.DataFrame, str | None]:
    """
    Intenta leer una fuente por varios nombres y formatos.

    Devuelve el primer DataFrame con registros y el nombre resuelto.
    Si no encuentra ninguna alternativa, devuelve un DataFrame vacío.
    """
    ultimo_df = pd.DataFrame()

    for candidato in _candidatos(nombres):
        try:
            df = leer_archivo(carpeta, candidato, cache=cache)
        except Exception:
            continue

        if isinstance(df, pd.DataFrame):
            ultimo_df = df
            if not df.empty:
                return df, candidato

    return ultimo_df, None


def fecha_archivo_flexible(
    carpeta: str,
    nombre_resuelto: str | None,
    nombres_alternativos: str | Iterable[str],
) -> str:
    """Obtiene la fecha usando primero el nombre que pudo leerse."""
    candidatos: list[str] = []

    if nombre_resuelto:
        candidatos.append(nombre_resuelto)

    candidatos.extend(
        candidato
        for candidato in _candidatos(nombres_alternativos)
        if candidato not in candidatos
    )

    for candidato in candidatos:
        try:
            return fecha_archivo(carpeta, candidato)
        except Exception:
            continue

    return "Fecha de actualización no disponible"
