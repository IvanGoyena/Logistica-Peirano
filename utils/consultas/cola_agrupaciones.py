from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import text

from database import engine


TABLA_COLA = "execution.orden_agrupacion"

COLUMNAS_COLA = [
    "OrdenID",
    "FechaSolicitud",
    "UsuarioSolicitud",
    "Camioneta",
    "CodigoDespacho",
    "CodigosDespachoJSON",
    "UsarFiltroCodigoDespacho",
    "PedidosJSON",
    "CantidadPedidos",
    "Estado",
    "Etapa",
    "Mensaje",
    "FechaInicio",
    "FechaFin",
    "DuracionSegundos",
    "Intentos",
    "WorkerID",
    "UltimaActualizacion",
]

ESTADOS_TERMINALES = {"COMPLETADA", "ERROR", "CANCELADA"}

_SQL_A_LEGACY = {
    "orden_id": "OrdenID",
    "fecha_solicitud": "FechaSolicitud",
    "usuario_solicitud": "UsuarioSolicitud",
    "camioneta": "Camioneta",
    "codigo_despacho": "CodigoDespacho",
    "codigos_despacho_json": "CodigosDespachoJSON",
    "usar_filtro_codigo_despacho": "UsarFiltroCodigoDespacho",
    "pedidos_json": "PedidosJSON",
    "cantidad_pedidos": "CantidadPedidos",
    "estado": "Estado",
    "etapa": "Etapa",
    "mensaje": "Mensaje",
    "fecha_inicio": "FechaInicio",
    "fecha_fin": "FechaFin",
    "duracion_segundos": "DuracionSegundos",
    "intentos": "Intentos",
    "worker_id": "WorkerID",
    "ultima_actualizacion": "UltimaActualizacion",
}

_LEGACY_A_SQL = {v: k for k, v in _SQL_A_LEGACY.items()}

_COLUMNAS_JSON = {"CodigosDespachoJSON", "PedidosJSON"}
_COLUMNAS_FECHA = {
    "FechaSolicitud",
    "FechaInicio",
    "FechaFin",
    "UltimaActualizacion",
}
_COLUMNAS_ENTERAS = {"CantidadPedidos", "Intentos"}
_COLUMNAS_NUMERICAS = {"DuracionSegundos"}
_COLUMNAS_BOOLEANAS = {"UsarFiltroCodigoDespacho"}


def ahora_texto() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def limpiar_valor(valor: Any) -> str:
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"

    return str(valor).strip()


def _texto_fecha(valor: Any) -> str:
    if valor is None:
        return ""

    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")

    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")

    return limpiar_valor(valor)


def _json_texto(valor: Any) -> str:
    if valor is None or valor == "":
        return "[]"

    if isinstance(valor, str):
        texto_valor = valor.strip()
        if not texto_valor:
            return "[]"

        try:
            json.loads(texto_valor)
            return texto_valor
        except json.JSONDecodeError:
            return json.dumps(valor, ensure_ascii=False)

    return json.dumps(valor, ensure_ascii=False)


def _a_bool(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor

    return str(valor).strip().upper() in {
        "TRUE",
        "1",
        "SI",
        "SÍ",
        "YES",
    }


def _a_entero(valor: Any, defecto: int = 0) -> int:
    if valor is None or str(valor).strip() == "":
        return defecto

    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return defecto


def _a_numero_o_none(valor: Any) -> float | None:
    if valor is None or str(valor).strip() == "":
        return None

    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _a_datetime_o_none(valor: Any) -> datetime | None:
    if valor is None or str(valor).strip() == "":
        return None

    if isinstance(valor, datetime):
        return valor

    if isinstance(valor, date):
        return datetime.combine(valor, datetime.min.time())

    convertido = pd.to_datetime(valor, errors="coerce")
    if pd.isna(convertido):
        return None

    if hasattr(convertido, "to_pydatetime"):
        return convertido.to_pydatetime()

    return convertido


def _valor_sql(columna_legacy: str, valor: Any) -> Any:
    if columna_legacy in _COLUMNAS_JSON:
        if valor is None or valor == "":
            return []

        if isinstance(valor, str):
            try:
                return json.loads(valor)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSON inválido para {columna_legacy}: {valor}"
                ) from error

        return valor

    if columna_legacy in _COLUMNAS_BOOLEANAS:
        return _a_bool(valor)

    if columna_legacy in _COLUMNAS_ENTERAS:
        return _a_entero(valor)

    if columna_legacy in _COLUMNAS_NUMERICAS:
        return _a_numero_o_none(valor)

    if columna_legacy in _COLUMNAS_FECHA:
        return _a_datetime_o_none(valor)

    texto_valor = limpiar_valor(valor)
    return texto_valor if texto_valor else None


def _registro_legacy(fila: dict[str, Any]) -> dict[str, Any]:
    salida: dict[str, Any] = {}

    for columna_sql, columna_legacy in _SQL_A_LEGACY.items():
        valor = fila.get(columna_sql)

        if columna_legacy in _COLUMNAS_JSON:
            salida[columna_legacy] = _json_texto(valor)
        elif columna_legacy in _COLUMNAS_FECHA:
            salida[columna_legacy] = _texto_fecha(valor)
        elif columna_legacy in _COLUMNAS_BOOLEANAS:
            salida[columna_legacy] = bool(valor) if valor is not None else False
        elif isinstance(valor, Decimal):
            salida[columna_legacy] = float(valor)
        elif valor is None:
            salida[columna_legacy] = ""
        else:
            salida[columna_legacy] = valor

    return salida


def _select_base() -> str:
    return """
        SELECT
            orden_id,
            fecha_solicitud,
            usuario_solicitud,
            camioneta,
            codigo_despacho,
            codigos_despacho_json,
            usar_filtro_codigo_despacho,
            pedidos_json,
            cantidad_pedidos,
            estado,
            etapa,
            mensaje,
            fecha_inicio,
            fecha_fin,
            duracion_segundos,
            intentos,
            worker_id,
            ultima_actualizacion
        FROM execution.orden_agrupacion
    """


def asegurar_hoja_cola() -> None:
    """
    Compatibilidad con el nombre de la implementación anterior.

    La tabla execution.orden_agrupacion se crea por migración SQL/Alembic,
    por lo que esta función ya no crea ni modifica Google Sheets.
    """
    return None


def leer_cola() -> pd.DataFrame:
    consulta = text(
        _select_base()
        + """
        ORDER BY fecha_solicitud ASC, orden_id ASC
        """
    )

    with engine.connect() as conexion:
        filas = conexion.execute(consulta).mappings().all()

    if not filas:
        return pd.DataFrame(columns=COLUMNAS_COLA)

    registros = [
        _registro_legacy(dict(fila))
        for fila in filas
    ]

    return pd.DataFrame(registros, columns=COLUMNAS_COLA)


def agregar_fila(registro: dict[str, Any]) -> None:
    orden_id = limpiar_valor(registro.get("OrdenID"))

    if not orden_id:
        raise ValueError("La orden debe tener OrdenID.")

    valores = {
        columna_sql: _valor_sql(
            columna_legacy,
            registro.get(columna_legacy),
        )
        for columna_legacy, columna_sql in _LEGACY_A_SQL.items()
    }

    if valores["fecha_solicitud"] is None:
        valores["fecha_solicitud"] = datetime.now()

    if valores["ultima_actualizacion"] is None:
        valores["ultima_actualizacion"] = datetime.now()

    if not valores["estado"]:
        valores["estado"] = "PENDIENTE"

    consulta = text(
        """
        INSERT INTO execution.orden_agrupacion (
            orden_id,
            fecha_solicitud,
            usuario_solicitud,
            camioneta,
            codigo_despacho,
            codigos_despacho_json,
            usar_filtro_codigo_despacho,
            pedidos_json,
            cantidad_pedidos,
            estado,
            etapa,
            mensaje,
            fecha_inicio,
            fecha_fin,
            duracion_segundos,
            intentos,
            worker_id,
            ultima_actualizacion
        )
        VALUES (
            :orden_id,
            :fecha_solicitud,
            :usuario_solicitud,
            :camioneta,
            :codigo_despacho,
            CAST(:codigos_despacho_json AS jsonb),
            :usar_filtro_codigo_despacho,
            CAST(:pedidos_json AS jsonb),
            :cantidad_pedidos,
            :estado,
            :etapa,
            :mensaje,
            :fecha_inicio,
            :fecha_fin,
            :duracion_segundos,
            :intentos,
            :worker_id,
            :ultima_actualizacion
        )
        """
    )

    parametros = dict(valores)
    parametros["codigos_despacho_json"] = json.dumps(
        valores["codigos_despacho_json"],
        ensure_ascii=False,
    )
    parametros["pedidos_json"] = json.dumps(
        valores["pedidos_json"],
        ensure_ascii=False,
    )

    with engine.begin() as conexion:
        conexion.execute(consulta, parametros)


def buscar_fila_orden(orden_id: str) -> int | None:
    """
    Compatibilidad con la función anterior.

    En PostgreSQL ya no existe un número físico de fila de Sheets.
    Devuelve 1 si la orden existe y None si no existe.
    """
    consulta = text(
        """
        SELECT 1
        FROM execution.orden_agrupacion
        WHERE orden_id = :orden_id
        LIMIT 1
        """
    )

    with engine.connect() as conexion:
        existe = conexion.execute(
            consulta,
            {"orden_id": str(orden_id).strip()},
        ).scalar_one_or_none()

    return 1 if existe is not None else None


def actualizar_orden(
    orden_id: str,
    cambios: dict[str, Any],
) -> None:
    orden_id = str(orden_id).strip()

    if not orden_id:
        raise ValueError("OrdenID vacío.")

    if not cambios:
        return

    columnas_sql: list[str] = []
    parametros: dict[str, Any] = {"orden_id": orden_id}

    for indice, (columna_legacy, valor) in enumerate(cambios.items()):
        if columna_legacy not in COLUMNAS_COLA:
            raise ValueError(
                f"Columna inválida en cola: {columna_legacy}"
            )

        if columna_legacy in {"OrdenID", "UltimaActualizacion"}:
            if columna_legacy == "OrdenID":
                raise ValueError("OrdenID no puede modificarse.")
            continue

        columna_sql = _LEGACY_A_SQL[columna_legacy]
        nombre_parametro = f"valor_{indice}"
        valor_sql = _valor_sql(columna_legacy, valor)

        if columna_legacy in _COLUMNAS_JSON:
            columnas_sql.append(
                f"{columna_sql} = CAST(:{nombre_parametro} AS jsonb)"
            )
            parametros[nombre_parametro] = json.dumps(
                valor_sql,
                ensure_ascii=False,
            )
        else:
            columnas_sql.append(
                f"{columna_sql} = :{nombre_parametro}"
            )
            parametros[nombre_parametro] = valor_sql

    columnas_sql.append("ultima_actualizacion = NOW()")

    consulta = text(
        f"""
        UPDATE execution.orden_agrupacion
        SET {", ".join(columnas_sql)}
        WHERE orden_id = :orden_id
        """
    )

    with engine.begin() as conexion:
        resultado = conexion.execute(consulta, parametros)

        if resultado.rowcount == 0:
            raise ValueError(f"No existe la orden {orden_id}.")


def crear_orden_agrupacion(
    *,
    camioneta: str,
    codigo_despacho: str,
    codigos_despacho: list[str],
    usar_filtro_codigo_despacho: bool,
    pedidos: list[str],
    usuario: str,
) -> str:
    pedidos_normalizados = list(
        dict.fromkeys(
            str(pedido).strip()
            for pedido in pedidos
            if str(pedido).strip()
        )
    )

    codigos_normalizados = list(
        dict.fromkeys(
            str(codigo).strip()
            for codigo in codigos_despacho
            if str(codigo).strip()
        )
    )

    if not pedidos_normalizados:
        raise ValueError("La orden no contiene pedidos.")

    orden_id = (
        f"AGR-{datetime.now():%Y%m%d%H%M%S}-"
        f"{uuid.uuid4().hex[:6].upper()}"
    )

    consulta = text(
        """
        INSERT INTO execution.orden_agrupacion (
            orden_id,
            fecha_solicitud,
            usuario_solicitud,
            camioneta,
            codigo_despacho,
            codigos_despacho_json,
            usar_filtro_codigo_despacho,
            pedidos_json,
            cantidad_pedidos,
            estado,
            etapa,
            mensaje,
            intentos,
            ultima_actualizacion
        )
        VALUES (
            :orden_id,
            NOW(),
            :usuario_solicitud,
            :camioneta,
            :codigo_despacho,
            CAST(:codigos_despacho_json AS jsonb),
            :usar_filtro_codigo_despacho,
            CAST(:pedidos_json AS jsonb),
            :cantidad_pedidos,
            'PENDIENTE',
            'encolada',
            'Orden recibida y pendiente de ejecución.',
            0,
            NOW()
        )
        """
    )

    parametros = {
        "orden_id": orden_id,
        "usuario_solicitud": limpiar_valor(usuario) or None,
        "camioneta": limpiar_valor(camioneta),
        "codigo_despacho": limpiar_valor(codigo_despacho) or None,
        "codigos_despacho_json": json.dumps(
            codigos_normalizados,
            ensure_ascii=False,
        ),
        "usar_filtro_codigo_despacho": bool(
            usar_filtro_codigo_despacho
        ),
        "pedidos_json": json.dumps(
            pedidos_normalizados,
            ensure_ascii=False,
        ),
        "cantidad_pedidos": len(pedidos_normalizados),
    }

    with engine.begin() as conexion:
        conexion.execute(consulta, parametros)

    return orden_id


def obtener_orden(orden_id: str) -> dict[str, Any] | None:
    consulta = text(
        _select_base()
        + """
        WHERE orden_id = :orden_id
        LIMIT 1
        """
    )

    with engine.connect() as conexion:
        fila = conexion.execute(
            consulta,
            {"orden_id": str(orden_id).strip()},
        ).mappings().first()

    if fila is None:
        return None

    return _registro_legacy(dict(fila))


def obtener_siguiente_pendiente() -> dict[str, Any] | None:
    consulta = text(
        _select_base()
        + """
        WHERE UPPER(TRIM(estado)) = 'PENDIENTE'
        ORDER BY fecha_solicitud ASC, orden_id ASC
        LIMIT 1
        """
    )

    with engine.connect() as conexion:
        fila = conexion.execute(consulta).mappings().first()

    if fila is None:
        return None

    return _registro_legacy(dict(fila))


def marcar_en_proceso(
    orden_id: str,
    worker_id: str,
    intentos: int,
) -> None:
    consulta = text(
        """
        UPDATE execution.orden_agrupacion
        SET
            estado = 'EN_PROCESO',
            etapa = 'inicio',
            mensaje = 'El worker tomó la orden.',
            fecha_inicio = NOW(),
            worker_id = :worker_id,
            intentos = :intentos,
            ultima_actualizacion = NOW()
        WHERE orden_id = :orden_id
        """
    )

    with engine.begin() as conexion:
        resultado = conexion.execute(
            consulta,
            {
                "orden_id": str(orden_id).strip(),
                "worker_id": limpiar_valor(worker_id) or None,
                "intentos": _a_entero(intentos),
            },
        )

        if resultado.rowcount == 0:
            raise ValueError(f"No existe la orden {orden_id}.")


def worker_id_local() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"
