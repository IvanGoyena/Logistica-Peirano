from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator

import pandas as pd
from sqlalchemy import text as sql_text

from database import engine


# Contrato Python actual -> tablas PostgreSQL commercial.*.
# Mantiene los nombres que ya consume la interfaz para no reescribir el módulo.
ENTIDADES: dict[str, dict[str, Any]] = {
    "Solicitudes": {
        "table": "commercial.solicitud",
        "id_py": "SolicitudID",
        "id_sql": "solicitud_id",
        "fields": {
            "SolicitudID": "solicitud_id",
            "Pedido": "pedido",
            "Cliente": "cliente",
            "TipoSolicitud": "tipo_solicitud",
            "Prioridad": "prioridad",
            "Descripcion": "descripcion",
            "FechaHabilitacion": "fecha_habilitacion",
            "UsuarioSolicitante": "usuario_solicitante",
            "FechaSolicitud": "fecha_solicitud",
            "EstadoSolicitud": "estado_solicitud",
            "Responsable": "responsable",
            "Respuesta": "respuesta",
            "FechaResolucion": "fecha_resolucion",
        },
    },
    "Urgencias": {
        "table": "commercial.urgencia",
        "id_py": "UrgenciaID",
        "id_sql": "urgencia_id",
        "fields": {
            "UrgenciaID": "urgencia_id",
            "Pedido": "pedido",
            "Cliente": "cliente",
            "Motivo": "motivo",
            "Prioridad": "prioridad",
            "FechaRequerida": "fecha_requerida",
            "Observacion": "observacion",
            "UsuarioSolicitante": "usuario_solicitante",
            "FechaSolicitud": "fecha_solicitud",
            "EstadoUrgencia": "estado_urgencia",
            "AgrupadorDestino": "agrupador_destino",
            "EstadoEjecucionDIGIP": "estado_ejecucion_digip",
            "MensajeEjecucionDIGIP": "mensaje_ejecucion_digip",
            "FechaEjecucionDIGIP": "fecha_ejecucion_digip",
        },
    },
    "Anulaciones": {
        "table": "commercial.anulacion",
        "id_py": "AnulacionID",
        "id_sql": "anulacion_id",
        "fields": {
            "AnulacionID": "anulacion_id",
            "Pedido": "pedido",
            "Cliente": "cliente",
            "Motivo": "motivo",
            "Descripcion": "descripcion",
            "UsuarioSolicitante": "usuario_solicitante",
            "FechaSolicitud": "fecha_solicitud",
            "EstadoAnulacion": "estado_anulacion",
            "BloqueoActivo": "bloqueo_activo",
            "UsuarioResolucion": "usuario_resolucion",
            "Respuesta": "respuesta",
            "FechaResolucion": "fecha_resolucion",
        },
    },
    "CancelacionesEntrega": {
        "table": "commercial.cancelacion_entrega",
        "id_py": "CancelacionEntregaID",
        "id_sql": "cancelacion_entrega_id",
        "fields": {
            "CancelacionEntregaID": "cancelacion_entrega_id",
            "Remito": "remito",
            "Cliente": "cliente",
            "Motivo": "motivo",
            "Observacion": "observacion",
            "UsuarioSolicitante": "usuario_solicitante",
            "FechaSolicitud": "fecha_solicitud",
            "EstadoCancelacion": "estado_cancelacion",
            "TelefonoDestino": "telefono_destino",
            "EstadoWhatsApp": "estado_whatsapp",
            "FechaEnvioWhatsApp": "fecha_envio_whatsapp",
            "ResponsableConfirmacion": "responsable_confirmacion",
            "FechaConfirmacion": "fecha_confirmacion",
            "ObservacionConfirmacion": "observacion_confirmacion",
            "NumeroIR": "numero_ir",
            "FechaIR": "fecha_ir",
            "EstadoReingreso": "estado_reingreso",
            "FechaReingreso": "fecha_reingreso",
            "FechaCierre": "fecha_cierre",
            "ResponsableGestion": "responsable_gestion",
            "FechaInicioGestion": "fecha_inicio_gestion",
            "ResultadoOperativo": "resultado_operativo",
            "ResponsableIR": "responsable_ir",
            "ObservacionIR": "observacion_ir",
            "ResponsableReingreso": "responsable_reingreso",
            "ObservacionReingreso": "observacion_reingreso",
            "ResultadoFinal": "resultado_final",
            "UltimaActualizacion": "ultima_actualizacion",
        },
    },
    "Reclamos": {
        "table": "commercial.reclamo",
        "id_py": "ReclamoID",
        "id_sql": "reclamo_id",
        "fields": {
            "ReclamoID": "reclamo_id",
            "Pedido": "pedido",
            "Remito": "remito",
            "Cliente": "cliente",
            "FechaReclamo": "fecha_reclamo",
            "TipoReclamo": "tipo_reclamo",
            "Descripcion": "descripcion",
            "Responsable": "responsable",
            "EstadoReclamo": "estado_reclamo",
            "Resolucion": "resolucion",
            "UsuarioCreador": "usuario_creador",
            "FechaCreacion": "fecha_creacion",
            "FechaCierre": "fecha_cierre",
        },
    },
    "ReclamosDetalle": {
        "table": "commercial.reclamo_detalle",
        "id_py": "ReclamoDetalleID",
        "id_sql": "reclamo_detalle_id",
        "fields": {
            "ReclamoDetalleID": "reclamo_detalle_id",
            "ReclamoID": "reclamo_id",
            "CodigoArticulo": "codigo_articulo",
            "DescripcionArticulo": "descripcion_articulo",
            "Cantidad": "cantidad",
            "Observacion": "observacion",
        },
    },
    "ReclamosFotos": {
        "table": "commercial.reclamo_foto",
        "id_py": "ReclamoFotoID",
        "id_sql": "reclamo_foto_id",
        "fields": {
            "ReclamoFotoID": "reclamo_foto_id",
            "ReclamoID": "reclamo_id",
            "NombreArchivo": "nombre_archivo",
            "DriveFileID": "drive_file_id",
            "URLArchivo": "url_archivo",
            "UsuarioCreador": "usuario_creador",
            "FechaCarga": "fecha_carga",
        },
    },
}

_DATE_FIELDS = {"fecha_habilitacion", "fecha_requerida"}
_TIMESTAMP_FIELDS = {
    "fecha_solicitud", "fecha_resolucion", "fecha_ejecucion_digip",
    "fecha_reclamo", "fecha_creacion", "fecha_cierre", "fecha_carga",
    "fecha_envio_whatsapp", "fecha_confirmacion", "fecha_ir",
    "fecha_reingreso", "fecha_inicio_gestion", "ultima_actualizacion",
}
_BOOLEAN_FIELDS = {"bloqueo_activo"}


def _config(nombre_hoja: str) -> dict[str, Any]:
    try:
        return ENTIDADES[nombre_hoja]
    except KeyError as exc:
        raise ValueError(f"Entidad SQL no soportada: {nombre_hoja}") from exc


def _coerce(sql_col: str, valor: Any) -> Any:
    if valor is None:
        return None

    if isinstance(valor, float) and pd.isna(valor):
        return None

    if sql_col in _BOOLEAN_FIELDS:
        if isinstance(valor, bool):
            return valor
        return str(valor).strip().upper() in {"SI", "SÍ", "TRUE", "1", "YES"}

    if sql_col in _DATE_FIELDS:
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        texto = str(valor).strip()
        if not texto:
            return None
        return pd.to_datetime(texto, errors="raise").date()

    if sql_col in _TIMESTAMP_FIELDS:
        if isinstance(valor, datetime):
            return valor
        texto = str(valor).strip()
        if not texto:
            return None
        ts = pd.to_datetime(texto, errors="raise")
        return ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

    if isinstance(valor, str):
        return valor.strip()

    return valor


@contextmanager
def transaccion() -> Iterator[Any]:
    with engine.begin() as conexion:
        yield conexion


def _registrar_evento(conexion: Any, nombre_hoja: str, entidad_id: str, accion: str) -> None:
    conexion.execute(
        sql_text(
            """
            INSERT INTO commercial.gestion_evento
                (entidad_tipo, entidad_id, accion, source_system, source_name)
            VALUES
                (:tipo, :id, :accion, 'HOST_LOCAL', :source_name)
            """
        ),
        {
            "tipo": nombre_hoja.upper(),
            "id": str(entidad_id),
            "accion": accion,
            "source_name": "Consultas Comerciales",
        },
    )


def leer_hoja(nombre_hoja: str, columnas: list[str] | None = None, **_: Any) -> pd.DataFrame:
    cfg = _config(nombre_hoja)
    fields = cfg["fields"]
    select = ",\n                ".join(
        f'{sql_col} AS "{py_col}"' for py_col, sql_col in fields.items()
    )
    consulta = f"SELECT {select} FROM {cfg['table']}"
    return pd.read_sql_query(sql_text(consulta), engine)


def asegurar_hoja(nombre_hoja: str, *_: Any, **__: Any) -> bool:
    _config(nombre_hoja)
    return True


def insertar_registro(
    nombre_hoja: str,
    registro: dict[str, Any],
    *,
    conexion: Any | None = None,
    registrar_evento: bool = True,
) -> dict[str, Any]:
    cfg = _config(nombre_hoja)
    fields = cfg["fields"]

    datos_sql: dict[str, Any] = {}
    for py_col, valor in registro.items():
        sql_col = fields.get(py_col)
        if sql_col:
            datos_sql[sql_col] = _coerce(sql_col, valor)

    if cfg["id_sql"] not in datos_sql or not datos_sql[cfg["id_sql"]]:
        raise ValueError(f"Falta {cfg['id_py']} para insertar {nombre_hoja}.")

    columnas = list(datos_sql)
    nombres = ", ".join(columnas)
    parametros = ", ".join(f":{col}" for col in columnas)

    consulta = sql_text(
        f"""
        INSERT INTO {cfg['table']} ({nombres}, source_system, source_sheet, synced_at, updated_at)
        VALUES ({parametros}, 'HOST_LOCAL', :_source_sheet, NOW(), NOW())
        """
    )
    params = {**datos_sql, "_source_sheet": "Consultas Comerciales"}

    def _ejecutar(conn: Any) -> None:
        conn.execute(consulta, params)
        if registrar_evento:
            _registrar_evento(
                conn,
                nombre_hoja,
                str(datos_sql[cfg["id_sql"]]),
                "INSERT",
            )

    if conexion is not None:
        _ejecutar(conexion)
    else:
        with engine.begin() as conn:
            _ejecutar(conn)

    return registro


def agregar_registro(nombre_hoja: str, registro: dict[str, Any], **_: Any) -> dict[str, Any]:
    return insertar_registro(nombre_hoja, registro)


def actualizar_registro(
    nombre_hoja: str,
    columna_id: str,
    valor_id: Any,
    cambios: dict[str, Any],
    *,
    conexion: Any | None = None,
    **_: Any,
) -> None:
    cfg = _config(nombre_hoja)
    fields = cfg["fields"]
    id_sql = fields.get(columna_id, cfg["id_sql"])

    datos_sql: dict[str, Any] = {}
    for py_col, valor in cambios.items():
        sql_col = fields.get(py_col)
        if sql_col:
            datos_sql[sql_col] = _coerce(sql_col, valor)

    if not datos_sql:
        return

    asignaciones = ", ".join(f"{col} = :{col}" for col in datos_sql)
    consulta = sql_text(
        f"""
        UPDATE {cfg['table']}
        SET {asignaciones},
            source_system = 'HOST_LOCAL',
            source_sheet = 'Consultas Comerciales',
            synced_at = NOW(),
            updated_at = NOW()
        WHERE {id_sql} = :_id
        """
    )
    params = {**datos_sql, "_id": str(valor_id).strip()}

    def _ejecutar(conn: Any) -> None:
        resultado = conn.execute(consulta, params)
        if resultado.rowcount == 0:
            raise ValueError(
                f"No se encontró {nombre_hoja} con {columna_id}={valor_id}."
            )
        _registrar_evento(conn, nombre_hoja, str(valor_id), "UPDATE")

    if conexion is not None:
        _ejecutar(conexion)
    else:
        with engine.begin() as conn:
            _ejecutar(conn)


def eliminar_registro(*_: Any, **__: Any) -> None:
    raise RuntimeError(
        "Consultas Comerciales conserva histórico: use cancelación lógica en lugar de DELETE."
    )
