"""Vistas del módulo Stock."""

from .existencia import render as render_existencia
from .ocupacion import render as render_ocupacion
from .calidad import render as render_calidad
from .operativo import render as render_operativo
from .configuracion import render as render_configuracion

__all__ = [
    "render_existencia",
    "render_ocupacion",
    "render_calidad",
    "render_operativo",
    "render_configuracion",
]
