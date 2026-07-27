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
    asegurar_hoja,
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


def normalizar_remito(remito: Any) -> str:
    """Normaliza y valida uno o varios números de remito."""

    remito_texto = limpiar_texto(remito)

    if not remito_texto:
        raise ValueError("Debe ingresar al menos un número de remito.")

    # Permite cargar remitos separados por salto de línea, coma o punto y coma.
    for separador in ["\r\n", "\r", ";", ","]:
        remito_texto = remito_texto.replace(separador, "\n")

    remitos_normalizados: list[str] = []
    for valor in remito_texto.split("\n"):
        remito_limpio = limpiar_texto(valor).upper()
        if not remito_limpio:
            continue
        if remito_limpio.endswith(".0"):
            remito_limpio = remito_limpio[:-2]
        if remito_limpio not in remitos_normalizados:
            remitos_normalizados.append(remito_limpio)

    if not remitos_normalizados:
        raise ValueError("Debe ingresar al menos un número de remito válido.")

    return " | ".join(remitos_normalizados)


def separar_remitos(remitos: Any) -> list[str]:
    """Devuelve los remitos individuales de un valor almacenado."""

    texto = limpiar_texto(remitos)
    if not texto:
        return []

    for separador in ["\r\n", "\r", "\n", ";", ",", "|"]:
        texto = texto.replace(separador, "\n")

    resultado: list[str] = []
    for valor in texto.split("\n"):
        limpio = limpiar_texto(valor).upper()
        if limpio and limpio not in resultado:
            resultado.append(limpio)
    return resultado




ESTADOS_GESTION_CERRADA = {
    "FINALIZADA",
    "FINALIZADO",
    "RESUELTA",
    "RESUELTO",
    "CERRADA",
    "CERRADO",
    "RECHAZADA",
    "RECHAZADO",
    "CANCELADA",
    "CANCELADO",
    "AGRUPADA",
    "EXITOSO",
}


def existe_gestion_abierta(
    nombre_hoja: str,
    pedido: Any,
    columna_estado: str,
    columna_tipo: str | None = None,
    tipo: str = "",
) -> dict[str, Any] | None:
    """
    Busca una gestión abierta equivalente antes de insertar.

    Es una protección simple contra doble clic o reintentos
    inmediatos desde la interfaz.
    """

    pedido_normalizado = normalizar_pedido(pedido)
    tabla = leer_hoja(nombre_hoja)

    if tabla is None or tabla.empty or "Pedido" not in tabla.columns:
        return None

    pedidos = (
        tabla["Pedido"]
        .fillna("")
        .apply(lambda valor: normalizar_pedido(valor) if limpiar_texto(valor) else "")
    )

    mascara = pedidos.eq(pedido_normalizado)

    if columna_estado in tabla.columns:
        estados = (
            tabla[columna_estado]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
        mascara &= ~estados.isin(ESTADOS_GESTION_CERRADA)

    tipo_limpio = limpiar_texto(tipo)

    if columna_tipo and tipo_limpio and columna_tipo in tabla.columns:
        tipos = (
            tabla[columna_tipo]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
        mascara &= tipos.eq(tipo_limpio.upper())

    coincidencias = tabla.loc[mascara]

    if coincidencias.empty:
        return None

    return coincidencias.iloc[0].to_dict()


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

    existente = existe_gestion_abierta(
        nombre_hoja="Solicitudes",
        pedido=pedido_normalizado,
        columna_estado="EstadoSolicitud",
        columna_tipo="TipoSolicitud",
        tipo=tipo_solicitud,
    )

    if existente is not None:
        return {
            "ok": True,
            "duplicado": True,
            "id": limpiar_texto(
                existente.get("SolicitudID", "")
            ),
            "pedido": pedido_normalizado,
            "mensaje": (
                "El pedido ya tiene una solicitud abierta "
                "del mismo tipo. No se creó un duplicado."
            ),
        }

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
    usuario_cancelacion: str = "",
    motivo: str = "Cancelada desde Consultas Comerciales.",
) -> dict[str, Any]:
    """
    Cancela lógicamente una solicitud no finalizada.

    La fila permanece en Google Sheets para conservar el
    histórico de la gestión.
    """

    solicitud_id = limpiar_texto(solicitud_id)

    if not solicitud_id:
        raise ValueError(
            "El identificador de la solicitud es obligatorio."
        )

    registro = obtener_registro_por_id(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
    )

    if registro is None:
        raise ValueError(
            f"No se encontró la solicitud {solicitud_id}."
        )

    estado_actual = limpiar_texto(
        registro.get("EstadoSolicitud", "")
    ).upper()

    if estado_actual in {
        "FINALIZADA",
        "FINALIZADO",
        "CANCELADA",
        "CANCELADO",
    }:
        raise ValueError(
            "La solicitud ya está finalizada o cancelada."
        )

    responsable = (
        limpiar_texto(usuario_cancelacion)
        or limpiar_texto(registro.get("Responsable", ""))
        or "Usuario no identificado"
    )

    actualizar_registro(
        nombre_hoja="Solicitudes",
        columna_id="SolicitudID",
        valor_id=solicitud_id,
        cambios={
            "EstadoSolicitud": "Cancelada",
            "Responsable": responsable,
            "Respuesta": limpiar_texto(motivo),
            "FechaResolucion": obtener_fecha_hora(),
        },
    )

    return {
        "ok": True,
        "id": solicitud_id,
        "estado": "Cancelada",
        "mensaje": (
            "Solicitud cancelada correctamente. "
            "El registro se conserva en el histórico."
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

    existente = existe_gestion_abierta(
        nombre_hoja="Urgencias",
        pedido=pedido_normalizado,
        columna_estado="EstadoUrgencia",
    )

    if existente is not None:
        return {
            "ok": True,
            "duplicado": True,
            "id": limpiar_texto(
                existente.get("UrgenciaID", "")
            ),
            "pedido": pedido_normalizado,
            "mensaje": (
                "El pedido ya tiene una urgencia activa. "
                "No se creó un duplicado."
            ),
        }

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


# ==========================================================
# CANCELACIONES DE ENTREGA
# ==========================================================

ESTADOS_CANCELACION_CERRADA = {
    "FINALIZADA",
    "CANCELADA",
}

ESTADOS_CANCELACION_VALIDOS = {
    "Pendiente de envío",
    "Alerta enviada",
    "Entrega detenida",
    "Ya despachado",
    "IR generado",
    "Mercadería reingresada",
    "Finalizada",
    "Cancelada",
}


def guardar_cancelacion_entrega(
    remito: Any,
    cliente: str,
    motivo: str,
    observacion: str,
    usuario_solicitante: str,
    telefono_destino: str,
) -> dict[str, Any]:
    """Registra una cancelación de entrega por uno o varios remitos."""

    asegurar_hoja("CancelacionesEntrega")

    remito_normalizado = normalizar_remito(remito)
    motivo_limpio = limpiar_texto(motivo)

    if not motivo_limpio:
        raise ValueError("El motivo de cancelación es obligatorio.")

    tabla = leer_hoja("CancelacionesEntrega")

    if tabla is not None and not tabla.empty and "Remito" in tabla.columns:
        remitos_nuevos = set(separar_remitos(remito_normalizado))
        coincidencia_indice = None
        remitos_duplicados: set[str] = set()

        for indice, fila in tabla.iterrows():
            estado = limpiar_texto(fila.get("EstadoCancelacion", "")).upper()
            if estado in ESTADOS_CANCELACION_CERRADA:
                continue

            existentes = set(separar_remitos(fila.get("Remito", "")))
            repetidos = remitos_nuevos.intersection(existentes)
            if repetidos:
                coincidencia_indice = indice
                remitos_duplicados.update(repetidos)
                break

        if coincidencia_indice is not None:
            existente = tabla.loc[coincidencia_indice]
            detalle = ", ".join(sorted(remitos_duplicados))
            return {
                "ok": True,
                "duplicado": True,
                "id": limpiar_texto(existente.get("CancelacionEntregaID", "")),
                "remito": remito_normalizado,
                "mensaje": f"Ya existe una cancelación activa para: {detalle}.",
            }

    registro = {
        "CancelacionEntregaID": generar_id("CAN-ENT"),
        "Remito": remito_normalizado,
        "Cliente": limpiar_texto(cliente),
        "Motivo": motivo_limpio,
        "Observacion": limpiar_texto(observacion),
        "UsuarioSolicitante": limpiar_texto(usuario_solicitante),
        "FechaSolicitud": obtener_fecha_hora(),
        "EstadoCancelacion": "Pendiente de envío",
        "TelefonoDestino": limpiar_texto(telefono_destino),
        "EstadoWhatsApp": "Pendiente de envío",
        "FechaEnvioWhatsApp": "",
        "ResponsableConfirmacion": "",
        "FechaConfirmacion": "",
        "ObservacionConfirmacion": "",
        "NumeroIR": "",
        "FechaIR": "",
        "EstadoReingreso": "Pendiente",
        "FechaReingreso": "",
        "FechaCierre": "",
    }

    agregar_registro("CancelacionesEntrega", registro)

    return {
        "ok": True,
        "duplicado": False,
        "id": registro["CancelacionEntregaID"],
        "remito": remito_normalizado,
        "registro": registro,
        "mensaje": "Cancelación de entrega registrada correctamente.",
    }


def actualizar_cancelacion_entrega(
    cancelacion_id: Any,
    cambios: dict[str, Any],
) -> dict[str, Any]:
    """Actualiza una cancelación de entrega existente."""

    cancelacion_id_limpio = limpiar_texto(cancelacion_id)
    if not cancelacion_id_limpio:
        raise ValueError("El ID de cancelación es obligatorio.")

    actualizar_registro(
        nombre_hoja="CancelacionesEntrega",
        columna_id="CancelacionEntregaID",
        valor_id=cancelacion_id_limpio,
        cambios=cambios,
    )

    return {"ok": True, "id": cancelacion_id_limpio}


def marcar_whatsapp_cancelacion_enviado(
    cancelacion_id: Any,
    responsable: str = "",
) -> dict[str, Any]:
    """Confirma manualmente que el aviso preparado fue enviado por WhatsApp."""

    ahora = obtener_fecha_hora()
    return actualizar_cancelacion_entrega(
        cancelacion_id,
        {
            "EstadoWhatsApp": "Enviado - confirmado manualmente",
            "FechaEnvioWhatsApp": ahora,
            "EstadoCancelacion": "Alerta enviada",
            "ResponsableConfirmacion": limpiar_texto(responsable),
            "FechaConfirmacion": ahora,
            "ObservacionConfirmacion": "Aviso enviado por WhatsApp.",
        },
    )


def confirmar_cancelacion_entrega(
    cancelacion_id: Any,
    estado: str,
    responsable: str,
    observacion: str = "",
) -> dict[str, Any]:
    """Registra la respuesta operativa recibida luego del aviso."""

    estado_limpio = limpiar_texto(estado)
    estados_validos = {
        "Entrega detenida",
        "Ya despachado",
        "Cancelada",
    }

    if estado_limpio not in estados_validos:
        raise ValueError("Estado de confirmación inválido.")

    ahora = obtener_fecha_hora()
    cambios = {
        "EstadoCancelacion": estado_limpio,
        "ResponsableConfirmacion": limpiar_texto(responsable),
        "FechaConfirmacion": ahora,
        "ObservacionConfirmacion": limpiar_texto(observacion),
    }

    if estado_limpio == "Cancelada":
        cambios["FechaCierre"] = ahora

    return actualizar_cancelacion_entrega(cancelacion_id, cambios)


def registrar_ir_cancelacion(
    cancelacion_id: Any,
    numero_ir: str,
    responsable: str,
    observacion: str = "",
) -> dict[str, Any]:
    """Registra el IR generado para el reingreso de la mercadería."""

    numero_ir_limpio = limpiar_texto(numero_ir)
    if not numero_ir_limpio:
        raise ValueError("El número de IR es obligatorio.")

    return actualizar_cancelacion_entrega(
        cancelacion_id,
        {
            "NumeroIR": numero_ir_limpio,
            "FechaIR": obtener_fecha_hora(),
            "EstadoCancelacion": "IR generado",
            "ResponsableConfirmacion": limpiar_texto(responsable),
            "ObservacionConfirmacion": limpiar_texto(observacion),
        },
    )


def confirmar_reingreso_cancelacion(
    cancelacion_id: Any,
    responsable: str,
    observacion: str = "",
) -> dict[str, Any]:
    """Confirma que la mercadería volvió a ingresar físicamente."""

    ahora = obtener_fecha_hora()
    return actualizar_cancelacion_entrega(
        cancelacion_id,
        {
            "EstadoCancelacion": "Mercadería reingresada",
            "EstadoReingreso": "Confirmado",
            "FechaReingreso": ahora,
            "ResponsableConfirmacion": limpiar_texto(responsable),
            "ObservacionConfirmacion": limpiar_texto(observacion),
        },
    )


def finalizar_cancelacion_entrega(
    cancelacion_id: Any,
    responsable: str,
    observacion: str = "",
) -> dict[str, Any]:
    """Cierra definitivamente una cancelación ya regularizada."""

    ahora = obtener_fecha_hora()
    return actualizar_cancelacion_entrega(
        cancelacion_id,
        {
            "EstadoCancelacion": "Finalizada",
            "EstadoReingreso": "Finalizado",
            "FechaCierre": ahora,
            "ResponsableConfirmacion": limpiar_texto(responsable),
            "ObservacionConfirmacion": limpiar_texto(observacion),
        },
    )


# Compatibilidad con versiones anteriores del módulo.
def finalizar_reingreso_cancelacion(
    cancelacion_id: Any,
    responsable: str,
    observacion: str = "",
) -> dict[str, Any]:
    return confirmar_reingreso_cancelacion(
        cancelacion_id,
        responsable,
        observacion,
    )
