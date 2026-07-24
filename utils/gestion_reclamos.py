# utils/gestion_reclamos.py

from __future__ import annotations

import mimetypes
import uuid

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.http import MediaIoBaseUpload

from utils.google_sheets import (
    agregar_registro,
    crear_servicio_drive_escritura,
)


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

ZONA_HORARIA = ZoneInfo(
    "America/Argentina/Buenos_Aires"
)

NOMBRE_CARPETA_GESTION = (
    "Gestion_Comercial_Logistica"
)

NOMBRE_CARPETA_FOTOS = (
    "Reclamos_Fotos"
)

MIME_TYPE_CARPETA = (
    "application/vnd.google-apps.folder"
)

EXTENSIONES_PERMITIDAS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


# ==========================================================
# FUNCIONES GENERALES
# ==========================================================

def _ahora() -> str:
    """
    Devuelve fecha y hora de Argentina.
    """

    return datetime.now(
        ZONA_HORARIA
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _limpiar_texto(
    valor: Any,
) -> str:
    """
    Convierte un valor en texto limpio.
    """

    if valor is None:
        return ""

    texto = str(valor).strip()

    if texto.endswith(".0"):

        numero = texto[:-2]

        if numero.replace("-", "").isdigit():
            return numero

    return texto


def _normalizar_pedido(
    pedido: Any,
) -> str:
    """
    Normaliza el número de pedido.
    """

    return _limpiar_texto(
        pedido
    )


def _numero_no_negativo(
    valor: Any,
    nombre: str,
) -> float:
    """
    Valida que una cantidad sea numérica y no negativa.
    """

    try:
        numero = float(valor)

    except (TypeError, ValueError) as error:

        raise ValueError(
            f"{nombre} debe ser un número."
        ) from error

    if numero < 0:

        raise ValueError(
            f"{nombre} no puede ser negativa."
        )

    return numero


def _formatear_cantidad(
    valor: float,
) -> str:
    """
    Evita mostrar decimales innecesarios.
    """

    if float(valor).is_integer():
        return str(int(valor))

    return str(round(valor, 2))


def _generar_reclamo_id() -> str:
    """
    Genera un identificador único para el reclamo.
    """

    fecha = datetime.now(
        ZONA_HORARIA
    ).strftime(
        "%Y%m%d%H%M%S"
    )

    codigo = (
        uuid.uuid4()
        .hex[:6]
        .upper()
    )

    return (
        f"REC-{fecha}-{codigo}"
    )


def _nombre_archivo_seguro(
    nombre: Any,
) -> str:
    """
    Limpia el nombre de una fotografía.
    """

    nombre_original = Path(
        _limpiar_texto(nombre)
    ).name

    caracteres = []

    for caracter in nombre_original:

        if (
            caracter.isalnum()
            or caracter in {
                ".",
                "-",
                "_",
            }
        ):
            caracteres.append(
                caracter
            )

        else:
            caracteres.append("_")

    resultado = "".join(
        caracteres
    ).strip("._")

    return resultado or "foto.jpg"


def _escapar_consulta_drive(
    texto: str,
) -> str:
    """
    Escapa texto utilizado en consultas de Google Drive.
    """

    return (
        texto
        .replace("\\", "\\\\")
        .replace("'", "\\'")
    )


# ==========================================================
# GOOGLE DRIVE
# ==========================================================

def _buscar_carpeta_drive(
    nombre: str,
    parent_id: str | None = None,
) -> str | None:
    """
    Busca una carpeta de Google Drive.

    Cuando se informa parent_id, busca únicamente dentro
    de esa carpeta.
    """

    servicio = (
        crear_servicio_drive_escritura()
    )

    nombre_seguro = (
        _escapar_consulta_drive(nombre)
    )

    condiciones = [
        f"name = '{nombre_seguro}'",
        (
            f"mimeType = "
            f"'{MIME_TYPE_CARPETA}'"
        ),
        "trashed = false",
    ]

    if parent_id:

        condiciones.append(
            f"'{parent_id}' in parents"
        )

    consulta = " and ".join(
        condiciones
    )

    respuesta = (
        servicio
        .files()
        .list(
            q=consulta,
            spaces="drive",
            fields=(
                "files("
                "id,"
                "name,"
                "parents,"
                "driveId"
                ")"
            ),
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )

    carpetas = respuesta.get(
        "files",
        [],
    )

    if not carpetas:
        return None

    return carpetas[0]["id"]


def _crear_carpeta_drive(
    nombre: str,
    parent_id: str | None = None,
) -> str:
    """
    Crea una carpeta en Google Drive.
    """

    servicio = (
        crear_servicio_drive_escritura()
    )

    metadata: dict[str, Any] = {
        "name": nombre,
        "mimeType": MIME_TYPE_CARPETA,
    }

    if parent_id:

        metadata["parents"] = [
            parent_id
        ]

    carpeta = (
        servicio
        .files()
        .create(
            body=metadata,
            fields="id,name",
            supportsAllDrives=True,
        )
        .execute()
    )

    return carpeta["id"]


def _obtener_o_crear_carpeta(
    nombre: str,
    parent_id: str | None = None,
) -> str:
    """
    Devuelve una carpeta existente o la crea.
    """

    carpeta_id = (
        _buscar_carpeta_drive(
            nombre=nombre,
            parent_id=parent_id,
        )
    )

    if carpeta_id:
        return carpeta_id

    return _crear_carpeta_drive(
        nombre=nombre,
        parent_id=parent_id,
    )


def _obtener_carpeta_reclamo(
    reclamo_id: str,
) -> str:
    """
    Obtiene la estructura:

    Gestion_Comercial_Logistica/
        Reclamos_Fotos/
            REC-.../
    """

    carpeta_gestion_id = (
        _obtener_o_crear_carpeta(
            NOMBRE_CARPETA_GESTION
        )
    )

    carpeta_fotos_id = (
        _obtener_o_crear_carpeta(
            nombre=NOMBRE_CARPETA_FOTOS,
            parent_id=carpeta_gestion_id,
        )
    )

    return _obtener_o_crear_carpeta(
        nombre=reclamo_id,
        parent_id=carpeta_fotos_id,
    )


def _subir_foto_drive(
    contenido: bytes,
    nombre_archivo: str,
    tipo_contenido: str,
    carpeta_id: str,
) -> dict[str, str]:
    """
    Sube una fotografía y devuelve su ID y URL.
    """

    if not contenido:
        raise ValueError(
            "La fotografía está vacía."
        )

    servicio = (
        crear_servicio_drive_escritura()
    )

    tipo_mime = (
        _limpiar_texto(
            tipo_contenido
        )
        or mimetypes.guess_type(
            nombre_archivo
        )[0]
        or "application/octet-stream"
    )

    archivo_memoria = BytesIO(
        contenido
    )

    media = MediaIoBaseUpload(
        archivo_memoria,
        mimetype=tipo_mime,
        resumable=False,
    )

    metadata = {
        "name": nombre_archivo,
        "parents": [
            carpeta_id
        ],
    }

    archivo_drive = (
        servicio
        .files()
        .create(
            body=metadata,
            media_body=media,
            fields=(
                "id,"
                "name,"
                "webViewLink,"
                "webContentLink"
            ),
            supportsAllDrives=True,
        )
        .execute()
    )

    file_id = archivo_drive["id"]

    url = (
        archivo_drive.get(
            "webViewLink"
        )
        or (
            "https://drive.google.com/"
            f"file/d/{file_id}/view"
        )
    )

    return {
        "file_id": file_id,
        "nombre": archivo_drive.get(
            "name",
            nombre_archivo,
        ),
        "url": url,
    }


# ==========================================================
# PREPARACIÓN DEL DETALLE
# ==========================================================

def _preparar_detalle_reclamo(
    reclamo_id: str,
    articulos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convierte los artículos del formulario a la estructura
    de la hoja ReclamosDetalle.
    """

    if not articulos:

        raise ValueError(
            "Debe cargar al menos un artículo."
        )

    registros: list[
        dict[str, Any]
    ] = []

    for posicion, articulo in enumerate(
        articulos,
        start=1,
    ):

        codigo = _limpiar_texto(
            articulo.get(
                "ArticuloCodigo"
            )
        )

        descripcion = _limpiar_texto(
            articulo.get(
                "ArticuloDescripcion"
            )
        )

        if not codigo:
            continue

        cantidad_remitida = (
            _numero_no_negativo(
                articulo.get(
                    "CantidadRemitida",
                    0,
                ),
                "La cantidad remitida",
            )
        )

        cantidad_recibida = (
            _numero_no_negativo(
                articulo.get(
                    "CantidadRecibida",
                    0,
                ),
                "La cantidad recibida",
            )
        )

        diferencia = (
            cantidad_recibida
            - cantidad_remitida
        )

        cantidad_reclamada = abs(
            diferencia
        )

        # Si ambas cantidades son iguales, conserva igualmente
        # una cantidad representativa para reclamos por daños,
        # producto incorrecto u otras incidencias.
        if cantidad_reclamada == 0:

            cantidad_reclamada = max(
                cantidad_remitida,
                cantidad_recibida,
            )

        observacion = (
            "Cantidad remitida: "
            f"{_formatear_cantidad(cantidad_remitida)}"
            " | Cantidad recibida: "
            f"{_formatear_cantidad(cantidad_recibida)}"
            " | Diferencia: "
            f"{_formatear_cantidad(diferencia)}"
        )

        registros.append({
            "ReclamoDetalleID": (
                f"{reclamo_id}-"
                f"{posicion:03d}"
            ),
            "ReclamoID": reclamo_id,
            "CodigoArticulo": codigo,
            "DescripcionArticulo": (
                descripcion
            ),
            "Cantidad": (
                cantidad_reclamada
            ),
            "Observacion": observacion,
        })

    if not registros:

        raise ValueError(
            "Debe seleccionar al menos un artículo válido."
        )

    return registros


# ==========================================================
# GUARDADO DE FOTOS
# ==========================================================

def _guardar_fotos_reclamo(
    reclamo_id: str,
    fotos: list[dict[str, Any]],
    usuario_creador: str,
) -> list[dict[str, str]]:
    """
    Sube las fotografías a Google Drive y registra cada
    archivo en la hoja ReclamosFotos.
    """

    if not fotos:
        return []

    carpeta_reclamo_id = (
        _obtener_carpeta_reclamo(
            reclamo_id
        )
    )

    registros_guardados = []

    for posicion, foto in enumerate(
        fotos,
        start=1,
    ):

        contenido = foto.get(
            "contenido",
            b"",
        )

        if not isinstance(
            contenido,
            (bytes, bytearray),
        ):

            raise ValueError(
                "El contenido de una fotografía no es válido."
            )

        if not contenido:
            continue

        nombre_original = (
            _nombre_archivo_seguro(
                foto.get("nombre")
            )
        )

        extension = Path(
            nombre_original
        ).suffix.lower()

        if extension not in (
            EXTENSIONES_PERMITIDAS
        ):
            extension = ".jpg"

        nombre_drive = (
            f"{posicion:03d}_"
            f"{uuid.uuid4().hex[:8]}"
            f"{extension}"
        )

        resultado_drive = (
            _subir_foto_drive(
                contenido=bytes(
                    contenido
                ),
                nombre_archivo=nombre_drive,
                tipo_contenido=(
                    _limpiar_texto(
                        foto.get(
                            "tipo_contenido"
                        )
                    )
                ),
                carpeta_id=(
                    carpeta_reclamo_id
                ),
            )
        )

        registro = {
            "ReclamoFotoID": (
                "FOT-"
                + uuid.uuid4()
                .hex[:12]
                .upper()
            ),
            "ReclamoID": reclamo_id,
            "NombreArchivo": (
                nombre_original
            ),
            "DriveFileID": (
                resultado_drive[
                    "file_id"
                ]
            ),
            "URLArchivo": (
                resultado_drive["url"]
            ),
            "UsuarioCreador": (
                usuario_creador
            ),
            "FechaCarga": _ahora(),
        }

        agregar_registro(
            nombre_hoja=(
                "ReclamosFotos"
            ),
            registro=registro,
        )

        registros_guardados.append(
            registro
        )

    return registros_guardados


# ==========================================================
# GUARDAR RECLAMO
# ==========================================================

def guardar_reclamo_entrega(
    numero_pedido: Any,
    numero_remito: Any,
    cliente_codigo: Any,
    cliente_descripcion: Any,
    incidencia: Any,
    estado_reclamo: Any,
    observaciones: Any,
    usuario_registro: Any,
    articulos: list[dict[str, Any]],
    responsable: Any = "",
    fecha_reclamo: Any = "",
    fotos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Registra un reclamo de entrega en:

    - Reclamos
    - ReclamosDetalle
    - ReclamosFotos
    - Google Drive
    """

    pedido = _normalizar_pedido(
        numero_pedido
    )

    remito = _limpiar_texto(
        numero_remito
    )

    codigo_cliente = _limpiar_texto(
        cliente_codigo
    )

    descripcion_cliente = (
        _limpiar_texto(
            cliente_descripcion
        )
    )

    incidencia_limpia = (
        _limpiar_texto(
            incidencia
        )
    )

    estado_limpio = (
        _limpiar_texto(
            estado_reclamo
        )
    )

    observaciones_limpias = (
        _limpiar_texto(
            observaciones
        )
    )

    usuario_limpio = (
        _limpiar_texto(
            usuario_registro
        )
        or "Usuario no identificado"
    )

    responsable_limpio = (
        _limpiar_texto(
            responsable
        )
    )

    if not pedido:

        raise ValueError(
            "El número de pedido es obligatorio."
        )

    if not remito:

        raise ValueError(
            "El número de remito es obligatorio."
        )

    if not codigo_cliente:

        raise ValueError(
            "Debe seleccionar un cliente."
        )

    if not incidencia_limpia:

        raise ValueError(
            "Debe seleccionar una incidencia."
        )

    if not estado_limpio:

        raise ValueError(
            "Debe seleccionar el estado del reclamo."
        )

    if not observaciones_limpias:

        raise ValueError(
            "Las observaciones son obligatorias."
        )

    reclamo_id = (
        _generar_reclamo_id()
    )

    fecha_actual = _ahora()

    detalle = (
        _preparar_detalle_reclamo(
            reclamo_id=reclamo_id,
            articulos=articulos,
        )
    )


    descripcion_reclamo = (
        f"Remito: {remito}\n"
        f"{observaciones_limpias}"
    )

    cabecera = {
        "ReclamoID": reclamo_id,
        "Pedido": pedido,
        "NumeroRemito": remito,
        "ClienteCodigo": codigo_cliente,
        "ClienteDescripcion": descripcion_cliente,
        "FechaReclamo": (
            _limpiar_texto(fecha_reclamo)
            or fecha_actual
        ),
        "TipoReclamo": incidencia_limpia,
        "Descripcion": observaciones_limpias,
        "Responsable": responsable_limpio,
        "EstadoReclamo": estado_limpio,
        "Resolucion": "",
        "UsuarioCreador": usuario_limpio,
        "FechaCreacion": fecha_actual,
        "FechaCierre": "",
    }

    # Primero se guarda la cabecera.
    agregar_registro(
        nombre_hoja="Reclamos",
        registro=cabecera,
    )

    # Luego se guarda una fila por cada artículo.
    for registro_detalle in detalle:

        agregar_registro(
            nombre_hoja=(
                "ReclamosDetalle"
            ),
            registro=(
                registro_detalle
            ),
        )

    fotos_guardadas = (
        _guardar_fotos_reclamo(
            reclamo_id=reclamo_id,
            fotos=fotos or [],
            usuario_creador=(
                usuario_limpio
            ),
        )
    )

    return {
        "ok": True,
        "reclamo_id": reclamo_id,
        "id": reclamo_id,
        "pedido": pedido,
        "cantidad_articulos": len(
            detalle
        ),
        "cantidad_fotos": len(
            fotos_guardadas
        ),
        "mensaje": (
            f"Reclamo {reclamo_id} "
            "registrado correctamente."
        ),
    }