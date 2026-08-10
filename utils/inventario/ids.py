from __future__ import annotations

from datetime import datetime
from uuid import uuid4


def generar_id(prefijo: str) -> str:
    fecha = datetime.now().strftime("%Y%m%d%H%M%S")
    aleatorio = uuid4().hex[:6].upper()
    return f"{prefijo}-{fecha}-{aleatorio}"


def generar_inventario_id() -> str:
    return generar_id("INV")


def generar_item_id() -> str:
    return generar_id("ITEM")


def generar_conteo_id() -> str:
    return generar_id("CONT")


def generar_reconteo_id() -> str:
    return generar_id("RECONT")


def generar_historial_id() -> str:
    return generar_id("HIST")


def generar_importacion_id() -> str:
    return generar_id("IMP")


def generar_accion_id() -> str:
    return generar_id("ACC")
