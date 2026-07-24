# utils/estados_comerciales.py

from __future__ import annotations

from typing import Any

import pandas as pd


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

ORDEN_ESTADOS_COMERCIALES = {
    "Bloqueado por anulación": 1,
    "Con incidencia": 2,
    "Pendiente de stock": 3,
    "Pendiente de liberación": 4,
    "Disponible para preparar": 5,
    "Preparación en curso": 6,
    "Preparación parcial": 7,
    "Preparado": 8,
    "En control": 9,
    "Listo para despachar": 10,
    "Asignado a despacho": 11,
    "Despachado": 12,
    "Finalizado": 13,
    "Estado a revisar": 99,
}


DESCRIPCIONES_ESTADOS = {
    "Bloqueado por anulación": (
        "Existe una solicitud de anulación pendiente. "
        "El pedido no debe continuar avanzando."
    ),
    "Con incidencia": (
        "El pedido tiene una solicitud, observación o reclamo "
        "pendiente de resolución."
    ),
    "Pendiente de stock": (
        "El pedido todavía no puede prepararse porque tiene "
        "mercadería pendiente."
    ),
    "Pendiente de liberación": (
        "El pedido todavía no fue liberado para comenzar "
        "su preparación."
    ),
    "Disponible para preparar": (
        "El pedido está disponible y esperando ser asignado "
        "para su preparación."
    ),
    "Preparación en curso": (
        "El depósito se encuentra preparando el pedido."
    ),
    "Preparación parcial": (
        "Una parte del pedido ya fue preparada, pero todavía "
        "quedan unidades pendientes."
    ),
    "Preparado": (
        "La preparación del pedido terminó y está esperando "
        "la siguiente etapa."
    ),
    "En control": (
        "El pedido se encuentra en control antes de ser "
        "despachado."
    ),
    "Listo para despachar": (
        "El pedido está completo y disponible para cargar "
        "o retirar."
    ),
    "Asignado a despacho": (
        "El pedido fue incorporado a una salida o agrupador "
        "de despacho."
    ),
    "Despachado": (
        "El pedido ya salió del depósito."
    ),
    "Finalizado": (
        "El circuito operativo del pedido se encuentra finalizado."
    ),
    "Estado a revisar": (
        "No fue posible interpretar automáticamente el estado "
        "operativo del pedido."
    ),
}


# ==========================================================
# FUNCIONES AUXILIARES
# ==========================================================

def limpiar_texto(valor: Any) -> str:
    """
    Convierte cualquier valor en texto limpio y en mayúsculas.
    """

    if valor is None:
        return ""

    if pd.isna(valor):
        return ""

    return str(valor).strip().upper()


def normalizar_pedido(valor: Any) -> str:
    """
    Normaliza el número de pedido.
    """

    texto = limpiar_texto(valor)

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto


def convertir_numero(
    valor: Any,
    valor_default: float = 0,
) -> float:
    """
    Convierte un valor a número de forma segura.
    """

    if valor is None or pd.isna(valor):
        return valor_default

    try:
        texto = str(valor).strip().replace(",", ".")
        return float(texto)

    except (TypeError, ValueError):
        return valor_default


def valor_verdadero(valor: Any) -> bool:
    """
    Interpreta diferentes representaciones de verdadero.
    """

    texto = limpiar_texto(valor)

    return texto in {
        "SI",
        "SÍ",
        "TRUE",
        "1",
        "ACTIVO",
        "BLOQUEADO",
        "URGENTE",
    }


def buscar_valor_fila(
    fila: pd.Series,
    columnas_posibles: list[str],
    default: Any = "",
) -> Any:
    """
    Busca el primer valor disponible entre varias columnas.

    Permite que el archivo funcione aunque los nombres de
    columnas cambien ligeramente.
    """

    for columna in columnas_posibles:
        if columna in fila.index:
            valor = fila.get(columna)

            if valor is not None and not pd.isna(valor):
                return valor

    return default


# ==========================================================
# LECTURA DE INFORMACIÓN OPERATIVA
# ==========================================================

def obtener_datos_estado(
    fila: pd.Series,
) -> dict[str, Any]:
    """
    Extrae de una fila los campos necesarios para determinar
    el estado comercial.
    """

    return {
        "pedido": buscar_valor_fila(
            fila,
            [
                "Pedido",
                "Número",
                "Numero",
                "NumeroPedido",
                "NroPedido",
            ],
        ),

        "estado_pedido": buscar_valor_fila(
            fila,
            [
                "Estado Final Ajustado",
                "EstadoFinalAjustado",
                "EstadoPedido",
                "Estado",
            ],
        ),

        "estado_preparacion": buscar_valor_fila(
            fila,
            [
                "PreparacionEstado",
                "EstadoPreparacion",
                "Preparación Estado",
                "Preparacion Estado",
            ],
        ),

        "estado_tarea": buscar_valor_fila(
            fila,
            [
                "TareaEstado",
                "EstadoTarea",
                "Estado Tarea",
            ],
        ),

        "tipo_tarea": buscar_valor_fila(
            fila,
            [
                "TipoTarea",
                "TareaTipo",
                "Tipo Tarea",
            ],
        ),

        "despacho": buscar_valor_fila(
            fila,
            [
                "Despacho",
                "Agrupador",
                "DespachoNombre",
                "NombreDespacho",
            ],
        ),

        "pendiente": buscar_valor_fila(
            fila,
            [
                "Pendiente",
                "UnidadesPendientes",
                "CantidadPendiente",
                "PendienteUnidades",
            ],
            0,
        ),

        "total": buscar_valor_fila(
            fila,
            [
                "Total",
                "Unidades",
                "CantidadTotal",
                "TotalUnidades",
            ],
            0,
        ),

        "reservado": buscar_valor_fila(
            fila,
            [
                "Reservado",
                "UnidadesReservadas",
                "CantidadReservada",
            ],
            0,
        ),

        "bloqueado": buscar_valor_fila(
            fila,
            [
                "BloqueoActivo",
                "PedidoBloqueado",
                "Bloqueado",
            ],
            False,
        ),

        "urgente": buscar_valor_fila(
            fila,
            [
                "UrgenciaActiva",
                "EsUrgente",
                "Urgente",
            ],
            False,
        ),

        "solicitudes_abiertas": buscar_valor_fila(
            fila,
            [
                "SolicitudesAbiertas",
                "CantidadSolicitudes",
            ],
            0,
        ),

        "reclamos_abiertos": buscar_valor_fila(
            fila,
            [
                "ReclamosAbiertos",
                "CantidadReclamos",
            ],
            0,
        ),
    }


# ==========================================================
# DETERMINACIÓN DEL ESTADO COMERCIAL
# ==========================================================

def determinar_estado_comercial(
    fila: pd.Series,
) -> str:
    """
    Traduce los estados operativos del pedido a un estado
    entendible para Comercial.

    El orden de las reglas es importante.
    """

    datos = obtener_datos_estado(fila)

    estado_pedido = limpiar_texto(
        datos["estado_pedido"]
    )

    estado_preparacion = limpiar_texto(
        datos["estado_preparacion"]
    )

    estado_tarea = limpiar_texto(
        datos["estado_tarea"]
    )

    tipo_tarea = limpiar_texto(
        datos["tipo_tarea"]
    )

    despacho = limpiar_texto(
        datos["despacho"]
    )

    pendiente = convertir_numero(
        datos["pendiente"]
    )

    total = convertir_numero(
        datos["total"]
    )

    reservado = convertir_numero(
        datos["reservado"]
    )

    solicitudes_abiertas = convertir_numero(
        datos["solicitudes_abiertas"]
    )

    reclamos_abiertos = convertir_numero(
        datos["reclamos_abiertos"]
    )

    bloqueado = valor_verdadero(
        datos["bloqueado"]
    )

    # ======================================================
    # 1. BLOQUEOS E INCIDENCIAS
    # ======================================================

    if bloqueado:
        return "Bloqueado por anulación"

    if solicitudes_abiertas > 0 or reclamos_abiertos > 0:
        return "Con incidencia"

    # ======================================================
    # 2. PEDIDOS FINALIZADOS O DESPACHADOS
    # ======================================================

    if estado_pedido in {
        "DESPACHADO",
        "DESPACHADA",
        "ENTREGADO",
        "ENTREGADA",
        "SALIDA CONFIRMADA",
    }:
        return "Despachado"

    if estado_pedido in {
        "FINALIZADO",
        "FINALIZADA",
        "COMPLETO",
        "COMPLETADO",
        "CERRADO",
        "CERRADA",
    } and pendiente <= 0:
        return "Finalizado"

    # ======================================================
    # 3. ASIGNACIÓN A DESPACHO
    # ======================================================

    if despacho not in {
        "",
        "SIN DESPACHO",
        "SIN ASIGNAR",
        "NO ASIGNADO",
        "NAN",
    }:
        if estado_pedido not in {
            "DESPACHADO",
            "FINALIZADO",
            "FINALIZADA",
        }:
            return "Asignado a despacho"

    # ======================================================
    # 4. CONTROL Y PEDIDO LISTO
    # ======================================================

    if tipo_tarea in {
        "CONTROL",
        "CONTROL CIEGO",
        "VERIFICACION",
        "VERIFICACIÓN",
        "EMPAQUE",
        "EMPAQUETADO",
    }:
        if estado_tarea in {
            "EN CURSO",
            "INICIADA",
            "INICIADO",
            "ASIGNADA",
            "ASIGNADO",
            "PENDIENTE",
        }:
            return "En control"

        if estado_tarea in {
            "FINALIZADA",
            "FINALIZADO",
            "COMPLETA",
            "COMPLETO",
            "CERRADA",
            "CERRADO",
        }:
            return "Listo para despachar"

    if estado_pedido in {
        "LISTO PARA DESPACHAR",
        "LISTO PARA DESPACHO",
        "LISTO",
        "CONTROLADO",
        "EMPAQUETADO",
    }:
        return "Listo para despachar"

    # ======================================================
    # 5. PREPARACIÓN
    # ======================================================

    if estado_preparacion in {
        "EN CURSO",
        "PREPARACION",
        "PREPARACIÓN",
        "INICIADA",
        "INICIADO",
        "ASIGNADA",
        "ASIGNADO",
    }:
        if total > 0 and 0 < pendiente < total:
            return "Preparación parcial"

        return "Preparación en curso"

    if estado_tarea in {
        "EN CURSO",
        "INICIADA",
        "INICIADO",
        "ASIGNADA",
        "ASIGNADO",
    } and tipo_tarea in {
        "PICKING",
        "PREPARACION",
        "PREPARACIÓN",
        "ALMACEN",
        "ALMACÉN",
    }:
        if total > 0 and 0 < pendiente < total:
            return "Preparación parcial"

        return "Preparación en curso"

    if estado_preparacion in {
        "PREPARADA",
        "PREPARADO",
        "FINALIZADA",
        "FINALIZADO",
        "COMPLETA",
        "COMPLETO",
    }:
        return "Preparado"

    # ======================================================
    # 6. DISPONIBILIDAD Y STOCK
    # ======================================================

    if estado_pedido in {
        "PENDIENTE STOCK",
        "SIN STOCK",
        "FALTA STOCK",
        "STOCK PENDIENTE",
        "NO DISPONIBLE",
    }:
        return "Pendiente de stock"

    if pendiente > reservado and pendiente > 0:
        return "Pendiente de stock"

    if estado_pedido in {
        "SIN LIBERAR",
        "PENDIENTE LIBERACION",
        "PENDIENTE LIBERACIÓN",
        "NO LIBERADO",
        "BLOQUEADO ERP",
    }:
        return "Pendiente de liberación"

    if estado_pedido in {
        "PENDIENTE",
        "DISPONIBLE",
        "LIBERADO",
        "LIBERADA",
        "SIN PREPARACION",
        "SIN PREPARACIÓN",
    }:
        return "Disponible para preparar"

    if pendiente > 0 and reservado >= pendiente:
        return "Disponible para preparar"

    # ======================================================
    # 7. CASOS RESIDUALES
    # ======================================================

    if pendiente <= 0 and total > 0:
        return "Preparado"

    return "Estado a revisar"


# ==========================================================
# DETALLE Y PRIORIDAD
# ==========================================================

def obtener_descripcion_estado(
    estado_comercial: str,
) -> str:
    """
    Devuelve una descripción amigable del estado comercial.
    """

    return DESCRIPCIONES_ESTADOS.get(
        estado_comercial,
        DESCRIPCIONES_ESTADOS["Estado a revisar"],
    )


def obtener_orden_estado(
    estado_comercial: str,
) -> int:
    """
    Devuelve el orden lógico del estado comercial.
    """

    return ORDEN_ESTADOS_COMERCIALES.get(
        estado_comercial,
        99,
    )


def determinar_prioridad_comercial(
    fila: pd.Series,
) -> str:
    """
    Devuelve la prioridad visible para Comercial.
    """

    datos = obtener_datos_estado(fila)

    if valor_verdadero(datos["bloqueado"]):
        return "Bloqueado"

    if valor_verdadero(datos["urgente"]):
        return "Urgente"

    reclamos = convertir_numero(
        datos["reclamos_abiertos"]
    )

    solicitudes = convertir_numero(
        datos["solicitudes_abiertas"]
    )

    if reclamos > 0 or solicitudes > 0:
        return "Con gestión"

    return "Normal"


# ==========================================================
# APLICACIÓN SOBRE DATAFRAME
# ==========================================================

def agregar_estados_comerciales(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Agrega a la tabla operativa las columnas necesarias
    para la vista de Comercial.
    """

    if df is None:
        return pd.DataFrame()

    tabla = df.copy()

    if tabla.empty:
        tabla["EstadoComercial"] = pd.Series(dtype=str)
        tabla["DescripcionEstado"] = pd.Series(dtype=str)
        tabla["OrdenEstadoComercial"] = pd.Series(dtype=int)
        tabla["PrioridadComercial"] = pd.Series(dtype=str)

        return tabla

    tabla["EstadoComercial"] = tabla.apply(
        determinar_estado_comercial,
        axis=1,
    )

    tabla["DescripcionEstado"] = tabla[
        "EstadoComercial"
    ].map(obtener_descripcion_estado)

    tabla["OrdenEstadoComercial"] = tabla[
        "EstadoComercial"
    ].map(obtener_orden_estado)

    tabla["PrioridadComercial"] = tabla.apply(
        determinar_prioridad_comercial,
        axis=1,
    )

    return tabla


# ==========================================================
# VISTA COMERCIAL
# ==========================================================

def construir_vista_comercial(
    df_operativo: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye una tabla simplificada para el módulo
    07_Consultas.

    Conserva únicamente las columnas disponibles.
    """

    tabla = agregar_estados_comerciales(
        df_operativo
    )

    columnas_deseadas = [
        "Pedido",
        "Número",
        "Numero",
        "Fecha",
        "Cliente",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Localidad",
        "Provincia",
        "TipoPreparacion",
        "TipoPedido",
        "Total",
        "Unidades",
        "Pendiente",
        "Reservado",
        "EstadoComercial",
        "DescripcionEstado",
        "PrioridadComercial",
        "Despacho",
        "Agrupador",
        "SolicitudesAbiertas",
        "ReclamosAbiertos",
        "BloqueoActivo",
        "UrgenciaActiva",
        "OrdenEstadoComercial",
    ]

    columnas_existentes = [
        columna
        for columna in columnas_deseadas
        if columna in tabla.columns
    ]

    vista = tabla[columnas_existentes].copy()

    if "OrdenEstadoComercial" in vista.columns:
        vista = vista.sort_values(
            by="OrdenEstadoComercial",
            ascending=True,
            na_position="last",
        )

    return vista.reset_index(drop=True)