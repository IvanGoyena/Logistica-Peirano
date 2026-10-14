from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from utils.google_sheets import (
    agregar_registro as _agregar_registro,
    actualizar_registro as _actualizar_registro,
    eliminar_registro as _eliminar_registro,
    leer_hoja as _leer_hoja,
    asegurar_hoja as _asegurar_hoja,
)


def asegurar_hoja(nombre_hoja: str, *_: Any, **__: Any) -> bool:
    _asegurar_hoja(nombre_hoja)
    return True


def leer_hoja(nombre_hoja: str, columnas: list[str] | None = None, **_: Any):
    return _leer_hoja(nombre_hoja, columnas=columnas)


def agregar_registro(nombre_hoja: str, registro: dict[str, Any], **_: Any) -> dict[str, Any]:
    _asegurar_hoja(nombre_hoja)
    _agregar_registro(nombre_hoja, registro)
    return registro


def insertar_registro(
    nombre_hoja: str,
    registro: dict[str, Any],
    *,
    conexion: Any | None = None,
    registrar_evento: bool = True,
    **_: Any,
) -> dict[str, Any]:
    # Google Sheets no usa una conexión transaccional. Los argumentos se
    # conservan para mantener el mismo contrato que persistencia_sql.py.
    _ = conexion, registrar_evento
    return agregar_registro(nombre_hoja, registro)


def actualizar_registro(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
    cambios: dict[str, Any],
    *,
    conexion: Any | None = None,
    **_: Any,
) -> None:
    _ = conexion
    _asegurar_hoja(nombre_hoja)
    _actualizar_registro(
        nombre_hoja=nombre_hoja,
        columna_id=columna_id,
        valor_id=valor_id,
        cambios=cambios,
    )


def eliminar_registro(*args: Any, **kwargs: Any):
    return _eliminar_registro(*args, **kwargs)


@contextmanager
def transaccion() -> Iterator[None]:
    # Interfaz compatible con el backend SQL. En Sheets cada escritura es
    # independiente; se conserva el context manager para no duplicar lógica.
    yield None
