# utils/gestion_consultas.py

from __future__ import annotations

import re
import uuid

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from utils.google_sheets import (
    agregar_registro,
    actualizar_registro,
    eliminar_registro,
    leer_hoja,
)


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

ZONA_HORARIA = ZoneInfo(
    "America/Argentina/Buenos_Aires"
)


# ==========================================================
# FUNCIONES GENERALES
# ==========================================================

def obtener_fecha_hora() -> str:
    """
    Devuelve la fecha y hora actual de Argentina.
    """

    return datetime.now(
        ZONA_HORARIA
    ).strftime("%Y-%m-%d %H:%M:%S")


def limpiar_texto(
    valor: Any,
) -> str:
    """
    Convierte valores vacíos o None en texto vacío.
    """

    if valor is None:
        return ""

    return str(valor).strip()


def normalizar_pedido(
    pedido: Any,
) -> str:
    """
    Normaliza el pedido.

    Ejemplos:
    12345.0  -> 12345
    12345-1  -> 12345
    """

    pedido_texto = limpiar_texto(
        pedido
    )

    if not pedido_texto:
        raise ValueError(
            "El número de pedido es obligatorio."
        )

    if re.fullmatch(
        r"\d+\.0",
        pedido_texto,
    ):
        pedido_texto = pedido_texto[:-2]

    return (
        pedido_texto
        .split("-")[0]
        .strip()
    )


def generar_id(
    prefijo: str,
) -> str:
    """
    Genera un identificador único.
    """

    fecha = datetime.now(
        ZONA_HORARIA
    ).strftime("%Y%m%d")

    codigo = uuid.uuid4().hex[:6].upper()

    return f"{prefijo}-{fecha}-{codigo}"


def obtener_registro_por_id(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
) -> dict[str, Any] | None:
    """
    Busca un registro de Google Sheets por su ID.
    """

    tabla = leer_hoja(
        nombre_hoja
    )

    if tabla is None or tabla.empty:
        return None

    if columna_id not in tabla.columns:
        raise ValueError(
            f"La columna '{columna_id}' no existe "
            f"en la hoja '{nombre_hoja}'."
        )

    valor_buscado = limpiar_texto(
        valor_id
    )

    coincidencias = tabla.loc[
        tabla[columna_id]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq(valor_buscado)
    ]

    if coincidencias.empty:
        return None

    return coincidencias.iloc[0].to_dict()


# ==========================================================
# SOLICITUDES
# ==========================================================

def guardar_solicitud(
    pedido: Any,
    cliente: str,
    tipo_solicitud: str,
    descripcion: str,
    usuario_solicitante: str,
    prioridad: str = "Normal",
) -> dict[str, Any]:
    """
    Registra una solicitud comercial.
    """

    pedido_normalizado = normalizar_pedido(
        pedido
    )

    tipo_solicitud = limpiar_texto(
        tipo_solicitud
    )

    descripcion = limpiar_texto(
        descripcion
    )

    prioridad = (
        limpiar_texto(prioridad)
        or "Normal"
    )

    if not tipo_solicitud:
        raise ValueError(
            "El tipo de solicitud es obligatorio."
        )

    if not descripcion:
        raise ValueError(
            "La descripción de la solicitud "
            "es obligatoria."
        )

    registro = {
        "SolicitudID": generar_id("SOL"),
        "Pedido": pedido_normalizado,
        "Cliente": limpiar_texto(cliente),
        "TipoSolicitud": tipo_solicitud,
        "Prioridad": prioridad,
        "Descripcion": descripcion,
        "UsuarioSolicitante": limpiar_texto(
            usuario_solicitante
        ),
        "FechaSolicitud": obtener_fecha_hora(),
        "EstadoSolicitud": "Pendiente",
        "Responsable": "",
        "Respuesta": "",
        "FechaResolucion": "",
    }

    agregar_registro(
        "Solicitudes",
        registro,
    )

    return {
        "ok": True,
        "id": registro["SolicitudID"],
        "pedido": pedido_normalizado,
        "mensaje": (
            "Solicitud registrada correctamente."
        ),
    }


def actualizar_solicitud(
    solicitud_id: str,
    estado_solicitud: str,
    responsable: str,
    respuesta: str = "",
) -> dict[str, Any]:
    """
    Actualiza el estado y la respuesta de una solicitud.
    """

    solicitud_id = limpiar_texto(
        solicitud_id
    )

    if not solicitud_id:
        raise ValueError(
            "El identificador de la solicitud "
            "es obligatorio."
        )

    estados_validos = {
        "PENDIENTE": "Pendiente",
        "EN REVISIÓN": "En revisión",
        "EN REVISION": "En revisión",
        "EN CURSO": "En curso",
        "FINALIZADA": "Finalizada",
        "FINALIZADO": "Finalizada",
    }

    estado_normalizado = limpiar_texto(
        estado_solicitud
    ).upper()

    if estado_normalizado not in estados_validos:
        raise ValueError(
            "Estado de solicitud no válido. "
            "Utilizá Pendiente, En revisión, "
            "En curso o Finalizada."
        )

    registro = obtener_registro_por_id(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
    )

    if registro is None:
        raise ValueError(
            f"No se encontró la solicitud "
            f"{solicitud_id}."
        )

    estado_final = estados_validos[
        estado_normalizado
    ]

    actualizar_registro(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
        cambios={
            "EstadoSolicitud": estado_final,
            "Responsable": limpiar_texto(
                responsable
            ),
            "Respuesta": limpiar_texto(
                respuesta
            ),
            "FechaResolucion": (
                obtener_fecha_hora()
                if estado_final == "Finalizada"
                else ""
            ),
        },
    )

    return {
        "ok": True,
        "id": solicitud_id,
        "estado": estado_final,
        "mensaje": (
            "Solicitud actualizada correctamente."
        ),
    }


def finalizar_solicitud_automaticamente(
    solicitud_id: str,
    motivo: str,
) -> dict[str, Any]:
    """
    Finaliza una solicitud por el estado real del pedido.
    """

    return actualizar_solicitud(
        solicitud_id=solicitud_id,
        estado_solicitud="Finalizada",
        responsable="Sistema",
        respuesta=motivo,
    )


def editar_solicitud(
    solicitud_id: str,
    tipo_solicitud: str,
    prioridad: str,
    descripcion: str,
) -> dict[str, Any]:
    """
    Edita una solicitud que todavía no fue finalizada.
    """

    solicitud_id = limpiar_texto(
        solicitud_id
    )

    tipo_solicitud = limpiar_texto(
        tipo_solicitud
    )

    prioridad = (
        limpiar_texto(prioridad)
        or "Normal"
    )

    descripcion = limpiar_texto(
        descripcion
    )

    if not solicitud_id:
        raise ValueError(
            "El identificador de la solicitud "
            "es obligatorio."
        )

    if not tipo_solicitud:
        raise ValueError(
            "El tipo de solicitud es obligatorio."
        )

    if not descripcion:
        raise ValueError(
            "La descripción de la solicitud "
            "es obligatoria."
        )

    registro = obtener_registro_por_id(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
    )

    if registro is None:
        raise ValueError(
            f"No se encontró la solicitud "
            f"{solicitud_id}."
        )

    estado_actual = limpiar_texto(
        registro.get(
            "EstadoSolicitud",
            "",
        )
    ).upper()

    if estado_actual in {
        "FINALIZADA",
        "FINALIZADO",
        "CANCELADA",
        "CANCELADO",
    }:
        raise ValueError(
            "No se puede editar una solicitud "
            "finalizada."
        )

    actualizar_registro(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
        cambios={
            "TipoSolicitud": tipo_solicitud,
            "Prioridad": prioridad,
            "Descripcion": descripcion,
        },
    )

    return {
        "ok": True,
        "id": solicitud_id,
        "mensaje": (
            "Solicitud modificada correctamente."
        ),
    }


def eliminar_solicitud(
    solicitud_id: str,
) -> dict[str, Any]:
    """
    Elimina una solicitud no finalizada.
    """

    solicitud_id = limpiar_texto(
        solicitud_id
    )

    if not solicitud_id:
        raise ValueError(
            "El identificador de la solicitud "
            "es obligatorio."
        )

    registro = obtener_registro_por_id(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
    )

    if registro is None:
        raise ValueError(
            f"No se encontró la solicitud "
            f"{solicitud_id}."
        )

    estado_actual = limpiar_texto(
        registro.get(
            "EstadoSolicitud",
            "",
        )
    ).upper()

    if estado_actual in {
        "FINALIZADA",
        "FINALIZADO",
    }:
        raise ValueError(
            "No se puede eliminar una solicitud "
            "finalizada."
        )

    eliminar_registro(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
    )

    return {
        "ok": True,
        "id": solicitud_id,
        "mensaje": (
            "Solicitud eliminada correctamente."
        ),
    }


# ==========================================================
# URGENCIAS
# ==========================================================

def guardar_urgencia(
    pedido: Any,
    cliente: str,
    motivo: str,
    usuario_solicitante: str,
    fecha_requerida: str = "",
    observacion: str = "",
) -> dict[str, Any]:
    """
    Registra una urgencia para procesarla posteriormente
    en DIGIP.
    """

    pedido_normalizado = normalizar_pedido(
        pedido
    )

    motivo = limpiar_texto(
        motivo
    )

    if not motivo:
        raise ValueError(
            "El motivo de la urgencia "
            "es obligatorio."
        )

    registro = {
        "UrgenciaID": generar_id("URG"),
        "Pedido": pedido_normalizado,
        "Cliente": limpiar_texto(cliente),
        "Motivo": motivo,
        "FechaRequerida": limpiar_texto(
            fecha_requerida
        ),
        "Observacion": limpiar_texto(
            observacion
        ),
        "UsuarioSolicitante": limpiar_texto(
            usuario_solicitante
        ),
        "FechaSolicitud": obtener_fecha_hora(),
        "EstadoUrgencia": "Pendiente",
        "AgrupadorDestino": "URGENTES",
        "EstadoEjecucionDIGIP": "Pendiente",
        "MensajeEjecucionDIGIP": "",
        "FechaEjecucionDIGIP": "",
    }

    agregar_registro(
        "Urgencias",
        registro,
    )

    return {
        "ok": True,
        "id": registro["UrgenciaID"],
        "pedido": pedido_normalizado,
        "mensaje": (
            "Urgencia registrada correctamente."
        ),
    }


# ==========================================================
# ANULACIONES
# ==========================================================

def guardar_anulacion(
    pedido: Any,
    cliente: str,
    motivo: str,
    descripcion: str,
    usuario_solicitante: str,
) -> dict[str, Any]:
    """
    Registra una solicitud de anulación.
    """

    pedido_normalizado = normalizar_pedido(
        pedido
    )

    motivo = limpiar_texto(
        motivo
    )

    if not motivo:
        raise ValueError(
            "El motivo de anulación "
            "es obligatorio."
        )

    registro = {
        "AnulacionID": generar_id("ANU"),
        "Pedido": pedido_normalizado,
        "Cliente": limpiar_texto(cliente),
        "Motivo": motivo,
        "Descripcion": limpiar_texto(
            descripcion
        ),
        "UsuarioSolicitante": limpiar_texto(
            usuario_solicitante
        ),
        "FechaSolicitud": obtener_fecha_hora(),
        "EstadoAnulacion": "Solicitada",
        "BloqueoActivo": "SI",
        "UsuarioResolucion": "",
        "Respuesta": "",
        "FechaResolucion": "",
    }

    agregar_registro(
        "Anulaciones",
        registro,
    )

    return {
        "ok": True,
        "id": registro["AnulacionID"],
        "pedido": pedido_normalizado,
        "bloqueo_activo": True,
        "mensaje": (
            "Solicitud de anulación registrada. "
            "El pedido quedó bloqueado preventivamente."
        ),
    }
