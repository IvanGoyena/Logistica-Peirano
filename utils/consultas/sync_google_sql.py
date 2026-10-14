from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text

from database import engine

from utils.consultas.leer_gestion_consultas import (
    leer_solicitudes,
    leer_urgencias,
    leer_anulaciones,
    leer_cancelaciones_entrega,
    leer_reclamos,
    leer_reclamos_detalle,
    leer_reclamos_fotos,
)


# ==========================================================
# NORMALIZACIÓN
# ==========================================================

def _limpiar(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.lower() in {"nan", "none", "<na>", "nat", "null"}:
        return ""
    if texto.endswith(".0") and texto[:-2].replace("-", "").isdigit():
        texto = texto[:-2]
    return texto


def _pedido(valor: Any) -> str:
    texto = _limpiar(valor)
    return texto.split("-")[0].strip() if texto else ""


def _fecha(valor: Any) -> datetime | None:
    texto = _limpiar(valor)
    if not texto:
        return None

    fecha = pd.to_datetime(
        texto,
        errors="coerce",
        dayfirst=True,
    )
    if pd.isna(fecha):
        return None

    if isinstance(fecha, pd.Timestamp):
        return fecha.to_pydatetime()

    return fecha


def _fecha_dia(valor: Any) -> date | None:
    dt = _fecha(valor)
    return dt.date() if dt is not None else None


def _booleano(valor: Any) -> bool:
    texto = _limpiar(valor).upper()
    return texto in {
        "SI", "SÍ", "TRUE", "1", "ACTIVO", "ACTIVA",
        "YES", "Y", "ON",
    }


def _numero(valor: Any) -> Decimal | None:
    texto = _limpiar(valor)
    if not texto:
        return None
    try:
        return Decimal(texto.replace(",", "."))
    except Exception:
        return None


def _json_safe(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, pd.Timestamp):
        return valor.isoformat()
    if isinstance(valor, float) and pd.isna(valor):
        return None
    return valor


def _hash_payload(payload: dict[str, Any]) -> str:
    canonico = {
        k: _json_safe(v)
        for k, v in sorted(payload.items())
    }
    texto = json.dumps(
        canonico,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


# ==========================================================
# CONFIGURACIÓN DE FUENTES
# ==========================================================

@dataclass(frozen=True)
class Fuente:
    nombre: str
    tabla: str
    pk_sql: str
    pk_google: str
    leer: Callable[[], pd.DataFrame]
    mapping: dict[str, tuple[str, Callable[[Any], Any]]]


FUENTES: tuple[Fuente, ...] = (
    Fuente(
        nombre="Solicitudes",
        tabla="commercial.solicitud",
        pk_sql="solicitud_id",
        pk_google="SolicitudID",
        leer=leer_solicitudes,
        mapping={
            "solicitud_id": ("SolicitudID", _limpiar),
            "pedido": ("Pedido", _pedido),
            "cliente": ("Cliente", _limpiar),
            "tipo_solicitud": ("TipoSolicitud", _limpiar),
            "prioridad": ("Prioridad", _limpiar),
            "descripcion": ("Descripcion", _limpiar),
            # La columna todavía no está declarada en la hoja actual.
            # Si aparece, el sincronizador ya está preparado para tomarla.
            "fecha_habilitacion": ("FechaHabilitacion", _fecha_dia),
            "usuario_solicitante": ("UsuarioSolicitante", _limpiar),
            "fecha_solicitud": ("FechaSolicitud", _fecha),
            "estado_solicitud": ("EstadoSolicitud", _limpiar),
            "responsable": ("Responsable", _limpiar),
            "respuesta": ("Respuesta", _limpiar),
            "fecha_resolucion": ("FechaResolucion", _fecha),
        },
    ),
    Fuente(
        nombre="Urgencias",
        tabla="commercial.urgencia",
        pk_sql="urgencia_id",
        pk_google="UrgenciaID",
        leer=leer_urgencias,
        mapping={
            "urgencia_id": ("UrgenciaID", _limpiar),
            "pedido": ("Pedido", _pedido),
            "cliente": ("Cliente", _limpiar),
            "motivo": ("Motivo", _limpiar),
            # Igual que FechaHabilitacion: queda listo si se incorpora
            # Prioridad a la estructura de Google Sheets.
            "prioridad": ("Prioridad", _limpiar),
            "fecha_requerida": ("FechaRequerida", _fecha_dia),
            "observacion": ("Observacion", _limpiar),
            "usuario_solicitante": ("UsuarioSolicitante", _limpiar),
            "fecha_solicitud": ("FechaSolicitud", _fecha),
            "estado_urgencia": ("EstadoUrgencia", _limpiar),
            "agrupador_destino": ("AgrupadorDestino", _limpiar),
            "estado_ejecucion_digip": ("EstadoEjecucionDIGIP", _limpiar),
            "mensaje_ejecucion_digip": ("MensajeEjecucionDIGIP", _limpiar),
            "fecha_ejecucion_digip": ("FechaEjecucionDIGIP", _fecha),
        },
    ),
    Fuente(
        nombre="Anulaciones",
        tabla="commercial.anulacion",
        pk_sql="anulacion_id",
        pk_google="AnulacionID",
        leer=leer_anulaciones,
        mapping={
            "anulacion_id": ("AnulacionID", _limpiar),
            "pedido": ("Pedido", _pedido),
            "cliente": ("Cliente", _limpiar),
            "motivo": ("Motivo", _limpiar),
            "descripcion": ("Descripcion", _limpiar),
            "usuario_solicitante": ("UsuarioSolicitante", _limpiar),
            "fecha_solicitud": ("FechaSolicitud", _fecha),
            "estado_anulacion": ("EstadoAnulacion", _limpiar),
            "bloqueo_activo": ("BloqueoActivo", _booleano),
            "usuario_resolucion": ("UsuarioResolucion", _limpiar),
            "respuesta": ("Respuesta", _limpiar),
            "fecha_resolucion": ("FechaResolucion", _fecha),
        },
    ),
    Fuente(
        nombre="Reclamos",
        tabla="commercial.reclamo",
        pk_sql="reclamo_id",
        pk_google="ReclamoID",
        leer=leer_reclamos,
        mapping={
            "reclamo_id": ("ReclamoID", _limpiar),
            "pedido": ("Pedido", _pedido),
            "remito": ("Remito", _limpiar),
            "cliente": ("Cliente", _limpiar),
            "fecha_reclamo": ("FechaReclamo", _fecha),
            "tipo_reclamo": ("TipoReclamo", _limpiar),
            "descripcion": ("Descripcion", _limpiar),
            "responsable": ("Responsable", _limpiar),
            "estado_reclamo": ("EstadoReclamo", _limpiar),
            "resolucion": ("Resolucion", _limpiar),
            "usuario_creador": ("UsuarioCreador", _limpiar),
            "fecha_creacion": ("FechaCreacion", _fecha),
            "fecha_cierre": ("FechaCierre", _fecha),
        },
    ),
    Fuente(
        nombre="ReclamosDetalle",
        tabla="commercial.reclamo_detalle",
        pk_sql="reclamo_detalle_id",
        pk_google="ReclamoDetalleID",
        leer=leer_reclamos_detalle,
        mapping={
            "reclamo_detalle_id": ("ReclamoDetalleID", _limpiar),
            "reclamo_id": ("ReclamoID", _limpiar),
            "codigo_articulo": ("CodigoArticulo", _limpiar),
            "descripcion_articulo": ("DescripcionArticulo", _limpiar),
            "cantidad": ("Cantidad", _numero),
            "observacion": ("Observacion", _limpiar),
        },
    ),
    Fuente(
        nombre="ReclamosFotos",
        tabla="commercial.reclamo_foto",
        pk_sql="reclamo_foto_id",
        pk_google="ReclamoFotoID",
        leer=leer_reclamos_fotos,
        mapping={
            "reclamo_foto_id": ("ReclamoFotoID", _limpiar),
            "reclamo_id": ("ReclamoID", _limpiar),
            "nombre_archivo": ("NombreArchivo", _limpiar),
            "drive_file_id": ("DriveFileID", _limpiar),
            "url_archivo": ("URLArchivo", _limpiar),
            "usuario_creador": ("UsuarioCreador", _limpiar),
            "fecha_carga": ("FechaCarga", _fecha),
        },
    ),
    Fuente(
        nombre="CancelacionesEntrega",
        tabla="commercial.cancelacion_entrega",
        pk_sql="cancelacion_entrega_id",
        pk_google="CancelacionEntregaID",
        leer=leer_cancelaciones_entrega,
        mapping={
            "cancelacion_entrega_id": ("CancelacionEntregaID", _limpiar),
            "remito": ("Remito", _limpiar),
            "cliente": ("Cliente", _limpiar),
            "motivo": ("Motivo", _limpiar),
            "observacion": ("Observacion", _limpiar),
            "usuario_solicitante": ("UsuarioSolicitante", _limpiar),
            "fecha_solicitud": ("FechaSolicitud", _fecha),
            "estado_cancelacion": ("EstadoCancelacion", _limpiar),
            "telefono_destino": ("TelefonoDestino", _limpiar),
            "estado_whatsapp": ("EstadoWhatsApp", _limpiar),
            "fecha_envio_whatsapp": ("FechaEnvioWhatsApp", _fecha),
            "responsable_confirmacion": ("ResponsableConfirmacion", _limpiar),
            "fecha_confirmacion": ("FechaConfirmacion", _fecha),
            "observacion_confirmacion": ("ObservacionConfirmacion", _limpiar),
            "numero_ir": ("NumeroIR", _limpiar),
            "fecha_ir": ("FechaIR", _fecha),
            "estado_reingreso": ("EstadoReingreso", _limpiar),
            "fecha_reingreso": ("FechaReingreso", _fecha),
            "fecha_cierre": ("FechaCierre", _fecha),
            "responsable_gestion": ("ResponsableGestion", _limpiar),
            "fecha_inicio_gestion": ("FechaInicioGestion", _fecha),
            "resultado_operativo": ("ResultadoOperativo", _limpiar),
            "responsable_ir": ("ResponsableIR", _limpiar),
            "observacion_ir": ("ObservacionIR", _limpiar),
            "responsable_reingreso": ("ResponsableReingreso", _limpiar),
            "observacion_reingreso": ("ObservacionReingreso", _limpiar),
            "resultado_final": ("ResultadoFinal", _limpiar),
            "ultima_actualizacion": ("UltimaActualizacion", _fecha),
        },
    ),
)


# ==========================================================
# SQL AUXILIAR
# ==========================================================

def _iniciar_run(conn, fuente: Fuente) -> int:
    return int(
        conn.execute(
            text("""
                INSERT INTO commercial.sync_run (
                    source_system,
                    source_name,
                    status
                )
                VALUES (
                    'GOOGLE_SHEETS',
                    :source_name,
                    'RUNNING'
                )
                RETURNING sync_run_id
            """),
            {"source_name": fuente.nombre},
        ).scalar_one()
    )


def _cerrar_run(
    conn,
    sync_run_id: int,
    *,
    status: str,
    rows_read: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_unchanged: int = 0,
    rows_error: int = 0,
    message: str = "",
) -> None:
    conn.execute(
        text("""
            UPDATE commercial.sync_run
            SET
                finished_at = NOW(),
                status = :status,
                rows_read = :rows_read,
                rows_inserted = :rows_inserted,
                rows_updated = :rows_updated,
                rows_unchanged = :rows_unchanged,
                rows_error = :rows_error,
                message = :message
            WHERE sync_run_id = :sync_run_id
        """),
        {
            "sync_run_id": sync_run_id,
            "status": status,
            "rows_read": rows_read,
            "rows_inserted": rows_inserted,
            "rows_updated": rows_updated,
            "rows_unchanged": rows_unchanged,
            "rows_error": rows_error,
            "message": message,
        },
    )


def _leer_existentes(conn, fuente: Fuente) -> dict[str, dict[str, Any]]:
    sql = text(
        f"""
        SELECT
            {fuente.pk_sql}::TEXT AS pk,
            source_hash,
            source_system,
            to_jsonb(t) AS payload
        FROM {fuente.tabla} t
        """
    )
    filas = conn.execute(sql).mappings().all()

    return {
        _limpiar(fila["pk"]): {
            "source_hash": _limpiar(fila["source_hash"]),
            "source_system": _limpiar(fila["source_system"]).upper(),
            "payload": dict(fila["payload"] or {}),
        }
        for fila in filas
        if _limpiar(fila["pk"])
    }


def _registrar_evento(
    conn,
    *,
    fuente: Fuente,
    entidad_id: str,
    accion: str,
    sync_run_id: int,
    hash_anterior: str | None,
    hash_nuevo: str,
    payload_anterior: dict[str, Any] | None,
    payload_nuevo: dict[str, Any],
) -> None:
    conn.execute(
        text("""
            INSERT INTO commercial.gestion_evento (
                entidad_tipo,
                entidad_id,
                accion,
                source_system,
                source_name,
                sync_run_id,
                hash_anterior,
                hash_nuevo,
                payload_anterior,
                payload_nuevo
            )
            VALUES (
                :entidad_tipo,
                :entidad_id,
                :accion,
                'GOOGLE_SHEETS',
                :source_name,
                :sync_run_id,
                :hash_anterior,
                :hash_nuevo,
                CAST(:payload_anterior AS JSONB),
                CAST(:payload_nuevo AS JSONB)
            )
        """),
        {
            "entidad_tipo": fuente.nombre.upper(),
            "entidad_id": entidad_id,
            "accion": accion,
            "source_name": fuente.nombre,
            "sync_run_id": sync_run_id,
            "hash_anterior": hash_anterior or None,
            "hash_nuevo": hash_nuevo,
            "payload_anterior": json.dumps(
                payload_anterior or {},
                ensure_ascii=False,
                default=str,
            ),
            "payload_nuevo": json.dumps(
                {
                    k: _json_safe(v)
                    for k, v in payload_nuevo.items()
                },
                ensure_ascii=False,
                default=str,
            ),
        },
    )


def _upsert(conn, fuente: Fuente, payload: dict[str, Any], source_hash: str) -> None:
    columnas = list(payload.keys())
    columnas_insert = columnas + [
        "source_system",
        "source_sheet",
        "source_hash",
        "synced_at",
        "updated_at",
    ]

    valores = [
        f":{col}"
        for col in columnas
    ] + [
        "'GOOGLE_SHEETS'",
        ":source_sheet",
        ":source_hash",
        "NOW()",
        "NOW()",
    ]

    actualizar = [
        f"{col} = EXCLUDED.{col}"
        for col in columnas
        if col != fuente.pk_sql
    ] + [
        "source_system = EXCLUDED.source_system",
        "source_sheet = EXCLUDED.source_sheet",
        "source_hash = EXCLUDED.source_hash",
        "synced_at = NOW()",
        "updated_at = NOW()",
    ]

    sql = text(
        f"""
        INSERT INTO {fuente.tabla} (
            {", ".join(columnas_insert)}
        )
        VALUES (
            {", ".join(valores)}
        )
        ON CONFLICT ({fuente.pk_sql})
        DO UPDATE SET
            {", ".join(actualizar)}
        """
    )

    params = dict(payload)
    params["source_sheet"] = fuente.nombre
    params["source_hash"] = source_hash

    conn.execute(sql, params)


# ==========================================================
# SINCRONIZACIÓN
# ==========================================================

def sincronizar_fuente(fuente: Fuente) -> dict[str, Any]:
    tabla_google = fuente.leer()
    if tabla_google is None:
        tabla_google = pd.DataFrame()

    resumen = {
        "fuente": fuente.nombre,
        "leidas": int(len(tabla_google)),
        "insertadas": 0,
        "actualizadas": 0,
        "sin_cambios": 0,
        "errores": 0,
        "omitidas_sin_id": 0,
        "status": "OK",
        "mensaje": "",
    }

    with engine.begin() as conn:
        sync_run_id = _iniciar_run(conn, fuente)

    try:
        with engine.begin() as conn:
            existentes = _leer_existentes(conn, fuente)

            for _, fila in tabla_google.iterrows():
                pk = _limpiar(
                    fila.get(fuente.pk_google, "")
                )

                if not pk:
                    resumen["omitidas_sin_id"] += 1
                    continue

                payload: dict[str, Any] = {}

                for columna_sql, (columna_google, transformador) in fuente.mapping.items():
                    valor = (
                        fila.get(columna_google, "")
                        if columna_google in tabla_google.columns
                        else ""
                    )
                    payload[columna_sql] = transformador(valor)

                # Asegurar que la PK del payload coincida con la clave original.
                payload[fuente.pk_sql] = pk

                source_hash = _hash_payload(payload)
                anterior = existentes.get(pk)

                # El host local ya escribe directamente en commercial.*.
                # Google queda como fuente legacy de la web congelada y NO
                # debe pisar una modificación más nueva hecha desde el host.
                if anterior and anterior.get("source_system") == "HOST_LOCAL":
                    resumen["sin_cambios"] += 1
                    continue

                if anterior and anterior["source_hash"] == source_hash:
                    resumen["sin_cambios"] += 1
                    continue

                accion = "INSERT" if anterior is None else "UPDATE"

                _upsert(
                    conn,
                    fuente,
                    payload,
                    source_hash,
                )

                _registrar_evento(
                    conn,
                    fuente=fuente,
                    entidad_id=pk,
                    accion=accion,
                    sync_run_id=sync_run_id,
                    hash_anterior=(
                        anterior["source_hash"]
                        if anterior
                        else None
                    ),
                    hash_nuevo=source_hash,
                    payload_anterior=(
                        anterior["payload"]
                        if anterior
                        else None
                    ),
                    payload_nuevo=payload,
                )

                if accion == "INSERT":
                    resumen["insertadas"] += 1
                else:
                    resumen["actualizadas"] += 1

            _cerrar_run(
                conn,
                sync_run_id,
                status="OK",
                rows_read=resumen["leidas"],
                rows_inserted=resumen["insertadas"],
                rows_updated=resumen["actualizadas"],
                rows_unchanged=resumen["sin_cambios"],
                rows_error=resumen["errores"],
                message=(
                    f"Omitidas sin ID: {resumen['omitidas_sin_id']}"
                ),
            )

    except Exception as error:
        resumen["status"] = "ERROR"
        resumen["errores"] += 1
        resumen["mensaje"] = f"{type(error).__name__}: {error}"

        with engine.begin() as conn:
            _cerrar_run(
                conn,
                sync_run_id,
                status="ERROR",
                rows_read=resumen["leidas"],
                rows_inserted=resumen["insertadas"],
                rows_updated=resumen["actualizadas"],
                rows_unchanged=resumen["sin_cambios"],
                rows_error=resumen["errores"],
                message=resumen["mensaje"],
            )

        raise

    return resumen


def sincronizar_todo() -> pd.DataFrame:
    resultados: list[dict[str, Any]] = []

    for fuente in FUENTES:
        try:
            resultados.append(
                sincronizar_fuente(fuente)
            )
        except Exception as error:
            resultados.append({
                "fuente": fuente.nombre,
                "leidas": 0,
                "insertadas": 0,
                "actualizadas": 0,
                "sin_cambios": 0,
                "errores": 1,
                "omitidas_sin_id": 0,
                "status": "ERROR",
                "mensaje": f"{type(error).__name__}: {error}",
            })

    return pd.DataFrame(resultados)


def validar_paridad() -> pd.DataFrame:
    """
    Compara cantidad de filas de cada Google Sheet contra su tabla SQL.
    Es una validación de conteo, no reemplaza la validación de contenido.
    """
    filas = []

    for fuente in FUENTES:
        try:
            google = fuente.leer()
            cantidad_google = int(len(google))
            google_ids = set()

            if (
                google is not None
                and not google.empty
                and fuente.pk_google in google.columns
            ):
                google_ids = {
                    _limpiar(x)
                    for x in google[fuente.pk_google].tolist()
                    if _limpiar(x)
                }

            with engine.begin() as conn:
                sql_ids = {
                    _limpiar(x)
                    for x in conn.execute(
                        text(
                            f"""
                            SELECT {fuente.pk_sql}::TEXT
                            FROM {fuente.tabla}
                            """
                        )
                    ).scalars().all()
                    if _limpiar(x)
                }

            filas.append({
                "Fuente": fuente.nombre,
                "GoogleFilas": cantidad_google,
                "GoogleIDs": len(google_ids),
                "SQLIDs": len(sql_ids),
                "FaltanEnSQL": len(google_ids - sql_ids),
                "SoloEnSQL": len(sql_ids - google_ids),
                "ParidadIDs": google_ids == sql_ids,
            })

        except Exception as error:
            filas.append({
                "Fuente": fuente.nombre,
                "GoogleFilas": None,
                "GoogleIDs": None,
                "SQLIDs": None,
                "FaltanEnSQL": None,
                "SoloEnSQL": None,
                "ParidadIDs": False,
                "Error": f"{type(error).__name__}: {error}",
            })

    return pd.DataFrame(filas)


if __name__ == "__main__":
    print("=" * 72)
    print("CONSULTAS COMERCIALES - GOOGLE SHEETS -> POSTGRESQL")
    print("=" * 72)

    resultado = sincronizar_todo()
    print("\nSINCRONIZACIÓN")
    print(resultado.to_string(index=False))

    validacion = validar_paridad()
    print("\nPARIDAD")
    print(validacion.to_string(index=False))
