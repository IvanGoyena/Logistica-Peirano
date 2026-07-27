from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from utils.google_sheets import agregar_registro, actualizar_registro, leer_hoja, asegurar_hoja

ZONA_HORARIA = ZoneInfo("America/Argentina/Buenos_Aires")
ESTADOS_CERRADOS = {"FINALIZADA", "CANCELADA"}


def ahora() -> str:
    return datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M:%S")


def limpiar(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def generar_id() -> str:
    return f"CAN-ENT-{datetime.now(ZONA_HORARIA):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:5].upper()}"


def separar_remitos(valor: Any) -> list[str]:
    partes = re.split(r"[\n,;]+", limpiar(valor))
    salida=[]
    for item in partes:
        item=item.strip()
        if item and item not in salida:
            salida.append(item)
    if not salida:
        raise ValueError("Ingresá al menos un remito.")
    return salida


def normalizar_remitos(valor: Any) -> str:
    return "\n".join(separar_remitos(valor))


def actualizar(cancelacion_id: Any, cambios: dict[str, Any]) -> dict[str, Any]:
    cid=limpiar(cancelacion_id)
    if not cid:
        raise ValueError("El ID de la gestión es obligatorio.")
    cambios={**cambios, "UltimaActualizacion": ahora()}
    actualizar_registro("CancelacionesEntrega","CancelacionEntregaID",cid,cambios)
    return {"ok": True, "id": cid}


def guardar_cancelacion_entrega(remito: Any, cliente: str, motivo: str, observacion: str,
                                usuario_solicitante: str, telefono_destino: str) -> dict[str, Any]:
    asegurar_hoja("CancelacionesEntrega")
    remitos=normalizar_remitos(remito)
    tabla=leer_hoja("CancelacionesEntrega")
    nuevos=set(separar_remitos(remitos))
    if tabla is not None and not tabla.empty and "Remito" in tabla.columns:
        for _,fila in tabla.iterrows():
            estado=limpiar(fila.get("EstadoCancelacion","")).upper()
            if estado in ESTADOS_CERRADOS:
                continue
            repetidos=nuevos.intersection(set(separar_remitos(fila.get("Remito",""))))
            if repetidos:
                return {"ok": True,"duplicado": True,
                        "id": limpiar(fila.get("CancelacionEntregaID","")),
                        "mensaje": "Ya existe una cancelación activa para: "+", ".join(sorted(repetidos))}
    fecha=ahora()
    registro={
        "CancelacionEntregaID": generar_id(), "Remito": remitos, "Cliente": limpiar(cliente),
        "Motivo": limpiar(motivo), "Observacion": limpiar(observacion),
        "UsuarioSolicitante": limpiar(usuario_solicitante), "FechaSolicitud": fecha,
        "EstadoCancelacion": "Pendiente de envío", "TelefonoDestino": limpiar(telefono_destino),
        "EstadoWhatsApp": "Pendiente de envío", "FechaEnvioWhatsApp": "",
        "ResponsableConfirmacion": "", "FechaConfirmacion": "", "ObservacionConfirmacion": "",
        "NumeroIR": "", "FechaIR": "", "EstadoReingreso": "Pendiente",
        "FechaReingreso": "", "FechaCierre": "", "ResponsableGestion": "",
        "FechaInicioGestion": "", "ResultadoOperativo": "", "ResponsableIR": "",
        "ObservacionIR": "", "ResponsableReingreso": "", "ObservacionReingreso": "",
        "ResultadoFinal": "", "UltimaActualizacion": fecha,
    }
    agregar_registro("CancelacionesEntrega",registro)
    return {"ok":True,"duplicado":False,"id":registro["CancelacionEntregaID"],"registro":registro}


def confirmar_envio_whatsapp(cancelacion_id: Any, responsable: str="") -> dict[str,Any]:
    fecha=ahora()
    return actualizar(cancelacion_id,{"EstadoWhatsApp":"Enviado - confirmado manualmente",
        "FechaEnvioWhatsApp":fecha,"EstadoCancelacion":"Enviada a Logística",
        "ResponsableConfirmacion":limpiar(responsable),"FechaConfirmacion":fecha,
        "ObservacionConfirmacion":"Aviso enviado por WhatsApp."})


def tomar_gestion(cancelacion_id: Any, responsable: str) -> dict[str,Any]:
    if not limpiar(responsable): raise ValueError("Indicá el responsable de la gestión.")
    return actualizar(cancelacion_id,{"EstadoCancelacion":"En gestión",
        "ResponsableGestion":limpiar(responsable),"FechaInicioGestion":ahora()})


def confirmar_resultado_operativo(cancelacion_id: Any, resultado: str, responsable: str,
                                  observacion: str="") -> dict[str,Any]:
    validos={"Entrega detenida","Ya despachado","Cancelada"}
    if resultado not in validos: raise ValueError("Resultado operativo inválido.")
    cambios={"EstadoCancelacion":resultado,"ResultadoOperativo":resultado,
        "ResponsableConfirmacion":limpiar(responsable),"FechaConfirmacion":ahora(),
        "ObservacionConfirmacion":limpiar(observacion)}
    if resultado=="Cancelada":
        cambios.update({"FechaCierre":ahora(),"ResultadoFinal":"Gestión cancelada"})
    return actualizar(cancelacion_id,cambios)


def registrar_ir(cancelacion_id: Any, numero_ir: str, responsable: str, observacion: str="") -> dict[str,Any]:
    if not limpiar(numero_ir): raise ValueError("El número de IR es obligatorio.")
    return actualizar(cancelacion_id,{"NumeroIR":limpiar(numero_ir),"FechaIR":ahora(),
        "EstadoCancelacion":"IR generado","ResponsableIR":limpiar(responsable),
        "ObservacionIR":limpiar(observacion)})


def confirmar_reingreso(cancelacion_id: Any, responsable: str, observacion: str="") -> dict[str,Any]:
    return actualizar(cancelacion_id,{"EstadoCancelacion":"Mercadería reingresada",
        "EstadoReingreso":"Confirmado","FechaReingreso":ahora(),
        "ResponsableReingreso":limpiar(responsable),"ObservacionReingreso":limpiar(observacion)})


def finalizar_gestion(cancelacion_id: Any, responsable: str, observacion: str="") -> dict[str,Any]:
    texto="Entrega detenida, IR generado y mercadería reingresada."
    if limpiar(observacion): texto += " "+limpiar(observacion)
    return actualizar(cancelacion_id,{"EstadoCancelacion":"Finalizada","EstadoReingreso":"Finalizado",
        "FechaCierre":ahora(),"ResponsableConfirmacion":limpiar(responsable),"ResultadoFinal":texto})
