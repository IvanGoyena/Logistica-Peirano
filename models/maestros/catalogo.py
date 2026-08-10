from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuenteMaestro:
    clave: str
    titulo: str
    icono: str
    grupo: str
    nombres: tuple[str, ...]
    descarga: str
    origen: str
    tipo: str = "crudo"
    cache: bool = False


FUENTES_MAESTROS = (
    FuenteMaestro(
        "tareas",
        "Informe Tareas",
        "📋",
        "Dinámicas",
        ("Informe Tareas",),
        "Informe_Tareas.csv",
        "WMS",
    ),
    FuenteMaestro(
        "pedidos",
        "Pedidos DIGIP",
        "📦",
        "Dinámicas",
        ("Pedidos DIGIP",),
        "Pedidos_DIGIP.csv",
        "WMS",
    ),
    FuenteMaestro(
        "detalle",
        "Detalle Pendientes",
        "📑",
        "ERP",
        ("Detalle Pendientes",),
        "Detalle_Pendientes.csv",
        "ERP",
    ),
    FuenteMaestro(
        "pendientes_erp",
        "Pedidos Pendientes ERP",
        "🧾",
        "ERP",
        ("Pedidos Pendientes",),
        "Pedidos_Pendientes_ERP_Limpio.csv",
        "ERP",
        tipo="pendientes",
    ),
    FuenteMaestro(
        "transmisiones",
        "Transmisiones ERP",
        "🔄",
        "ERP",
        ("Pedidos Transmicion", "Pedidos Transmisión"),
        "Transmisiones_ERP_Limpio.csv",
        "ERP",
        tipo="transmisiones",
    ),
    FuenteMaestro(
        "stock_detallado",
        "Stock detallado",
        "🏭",
        "Stock",
        (
            "stock_detallado",
            "Stock Detallado",
            "Informe Stock Total",
        ),
        "Stock_Detallado.csv",
        "WMS",
    ),
    FuenteMaestro(
        "stock_recepcion",
        "Stock recepción",
        "📥",
        "Stock",
        (
            "stock_recepcion",
            "Stock Recepcion",
            "Stock Recepción",
        ),
        "Stock_Recepcion.csv",
        "WMS",
    ),
    FuenteMaestro(
        "disponible",
        "Disponible DIGIP",
        "📦",
        "Stock",
        (
            "Disponible DIGIP",
            "Disponible Digip",
            "disponible_digip",
        ),
        "Disponible_DIGIP.csv",
        "WMS",
    ),
    FuenteMaestro(
        "stock_calidad",
        "Stock Calidad / Laboratorio",
        "🧪",
        "Stock",
        (
            "stock_calidad_laboratorio",
            "Stock Calidad Laboratorio",
        ),
        "Stock_Calidad_Laboratorio.csv",
        "WMS",
    ),
    FuenteMaestro(
        "max_min",
        "Max & Min Picking",
        "⚙️",
        "Stock",
        ("Max & Min", "Max_Min", "max_min"),
        "Max_y_Min_Picking.csv",
        "MAESTROS",
    ),
    FuenteMaestro(
        "articulos",
        "Maestro Artículos",
        "📚",
        "Maestros",
        ("Maestro Articulo", "Maestro Artículos"),
        "Maestro_Articulos.csv",
        "MAESTROS",
        cache=True,
    ),
    FuenteMaestro(
        "clientes",
        "Maestro Clientes",
        "👥",
        "Maestros",
        ("Maestro Clientes",),
        "Maestro_Clientes_Limpio.csv",
        "MAESTROS",
        tipo="clientes",
    ),
    FuenteMaestro(
        "expresos",
        "Maestro Expresos",
        "🚚",
        "Maestros",
        ("Datos Expresos",),
        "Maestro_Expresos_Limpio.csv",
        "MAESTROS",
        tipo="expresos",
        cache=True,
    ),
    FuenteMaestro(
        "volumetria",
        "Maestro Volumetría",
        "📐",
        "Maestros",
        ("Maestro Volumetria", "Maestro Volumetría"),
        "Maestro_Volumetria_Limpio.csv",
        "MAESTROS",
        tipo="volumetria",
        cache=True,
    ),
)


FUENTES_POR_CLAVE = {
    fuente.clave: fuente
    for fuente in FUENTES_MAESTROS
}


GRUPOS_FUENTES = (
    "Dinámicas",
    "Stock",
    "ERP",
    "Maestros",
)
