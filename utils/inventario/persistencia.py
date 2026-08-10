from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from utils.google_sheets import (
    ESTRUCTURA_HOJAS,
    agregar_registro,
    agregar_registros,
    actualizar_registro,
    crear_hoja,
    escribir_encabezados,
    leer_encabezados,
    leer_hoja,
    obtener_nombres_hojas,
)
from utils.inventario.ids import (
    generar_accion_id,
    generar_conteo_id,
    generar_historial_id,
    generar_importacion_id,
    generar_inventario_id,
    generar_item_id,
    generar_reconteo_id,
)


HOJAS_INVENTARIO = (
    "InventarioPlanes",
    "InventarioItems",
    "InventarioConteos",
    "InventarioReconteos",
    "InventarioImportaciones",
    "InventarioAcciones",
    "InventarioHistorial",
)


def ahora_texto() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def obtener_usuario_actual() -> dict[str, str]:
    return {
        "usuario": str(
            st.session_state.get(
                "usuario",
                "",
            )
            or ""
        ),
        "nombre": str(
            st.session_state.get(
                "nombre_usuario",
                "",
            )
            or ""
        ),
        "rol": str(
            st.session_state.get(
                "rol",
                "",
            )
            or ""
        ),
    }


def inicializar_hojas_inventario(
    *,
    forzar: bool = False,
) -> None:
    """Inicializa las hojas una sola vez por sesión."""

    clave_sesion = "_inventario_hojas_inicializadas"

    if (
        not forzar
        and st.session_state.get(clave_sesion)
    ):
        return

    hojas_existentes = set(
        obtener_nombres_hojas()
    )

    for hoja in HOJAS_INVENTARIO:
        columnas = ESTRUCTURA_HOJAS[hoja]

        if hoja not in hojas_existentes:
            crear_hoja(hoja)
            escribir_encabezados(hoja, columnas)
            hojas_existentes.add(hoja)
            continue

        encabezados = leer_encabezados(hoja)

        if not encabezados:
            escribir_encabezados(hoja, columnas)
            continue

        if encabezados != columnas:
            if columnas[:len(encabezados)] == encabezados:
                escribir_encabezados(hoja, columnas)
                continue

            raise ValueError(
                f"La hoja '{hoja}' tiene encabezados "
                "diferentes a los esperados."
            )

    st.session_state[clave_sesion] = True


def leer_planes() -> pd.DataFrame:
    return leer_hoja("InventarioPlanes")


def leer_items() -> pd.DataFrame:
    return leer_hoja("InventarioItems")


def leer_conteos() -> pd.DataFrame:
    return leer_hoja("InventarioConteos")


def leer_reconteos() -> pd.DataFrame:
    return leer_hoja("InventarioReconteos")


def leer_importaciones() -> pd.DataFrame:
    return leer_hoja(
        "InventarioImportaciones"
    )


def leer_acciones() -> pd.DataFrame:
    return leer_hoja("InventarioAcciones")


def leer_historial() -> pd.DataFrame:
    return leer_hoja("InventarioHistorial")


def registrar_historial(
    *,
    inventario_id: str,
    accion: str,
    estado_anterior: str = "",
    estado_nuevo: str = "",
    item_id: str = "",
    articulo_codigo: str = "",
    detalle: str = "",
) -> None:
    usuario = obtener_usuario_actual()

    agregar_registro(
        "InventarioHistorial",
        {
            "HistorialID": (
                generar_historial_id()
            ),
            "InventarioID": inventario_id,
            "ItemID": item_id,
            "ArticuloCodigo": articulo_codigo,
            "Accion": accion,
            "EstadoAnterior": estado_anterior,
            "EstadoNuevo": estado_nuevo,
            "Usuario": usuario["usuario"],
            "UsuarioNombre": usuario["nombre"],
            "Fecha": ahora_texto(),
            "Detalle": detalle,
        },
    )


def guardar_plan(
    *,
    fecha_planificada: str,
    tipo_inventario: str,
    grupo_inventario: str,
    responsable: str,
    responsable_nombre: str,
    observaciones: str,
    items_plan: pd.DataFrame,
) -> str:
    inicializar_hojas_inventario()

    if items_plan is None or items_plan.empty:
        raise ValueError(
            "No hay ubicaciones para guardar."
        )

    usuario = obtener_usuario_actual()
    inventario_id = generar_inventario_id()

    cantidad_articulos = int(
        items_plan[
            "ArticuloCodigo"
        ].nunique()
    )
    cantidad_ubicaciones = len(items_plan)

    agregar_registro(
        "InventarioPlanes",
        {
            "InventarioID": inventario_id,
            "FechaCreacion": ahora_texto(),
            "FechaPlanificada": fecha_planificada,
            "TipoInventario": tipo_inventario,
            "GrupoInventario": grupo_inventario,
            "Responsable": responsable,
            "ResponsableNombre": (
                responsable_nombre
            ),
            "Estado": "Planificado",
            "CantidadArticulos": (
                cantidad_articulos
            ),
            "CantidadUbicaciones": (
                cantidad_ubicaciones
            ),
            "UsuarioCreacion": (
                usuario["usuario"]
            ),
            "UsuarioCreacionNombre": (
                usuario["nombre"]
            ),
            "Observaciones": observaciones,
            "FechaInicio": "",
            "FechaFinalizacion": "",
        },
    )

    registros_items = []

    for _, fila in items_plan.iterrows():
        registros_items.append({
            "ItemID": generar_item_id(),
            "InventarioID": inventario_id,
            "ArticuloCodigo": fila.get(
                "ArticuloCodigo",
                "",
            ),
            "ArticuloDescripcion": fila.get(
                "ArticuloDescripcion",
                "",
            ),
            "GrupoInventario": fila.get(
                "GrupoInventario",
                "",
            ),
            "Familia": fila.get(
                "Familia",
                "",
            ),
            "Familia2": fila.get(
                "Familia2",
                "",
            ),
            "Sectorizacion": fila.get(
                "Sectorizacion",
                "",
            ),
            "Ubicacion": fila.get(
                "Ubicacion",
                "",
            ),
            "Contenedor": fila.get(
                "Contenedor",
                "",
            ),
            "FuenteDetalle": fila.get(
                "FuenteDetalle",
                "",
            ),
            "CantidadSistemaUbicacion": (
                fila.get("Cantidad", 0)
            ),
            "StockERPInicial": fila.get(
                "StockERP",
                0,
            ),
            "StockWMSInicial": fila.get(
                "StockWMSResumen",
                0,
            ),
            "DiferenciaInicial": fila.get(
                "DiferenciaERPvsWMS",
                0,
            ),
            "PrioridadInicial": fila.get(
                "PrioridadInventario",
                "",
            ),
            "ScorePrioridad": fila.get(
                "ScorePrioridad",
                0,
            ),
            "MotivoPrioridad": fila.get(
                "MotivoPrioridad",
                "",
            ),
            "EstadoItem": "Pendiente",
            "OrdenConteo": fila.get(
                "OrdenConteo",
                "",
            ),
            "TipoUbicacion": fila.get("TipoUbicacion", "Sin clasificar"),
            "AreaUbicacion": fila.get("AreaUbicacion", ""),
            "PasilloUbicacion": fila.get("PasilloUbicacion", ""),
        })

    agregar_registros(
        "InventarioItems",
        registros_items,
    )

    registrar_historial(
        inventario_id=inventario_id,
        accion="CREAR_PLAN",
        estado_nuevo="Planificado",
        detalle=(
            f"{cantidad_articulos} artículos · "
            f"{cantidad_ubicaciones} ubicaciones"
        ),
    )

    return inventario_id


def iniciar_plan(
    inventario_id: str,
) -> None:
    actualizar_registro(
        "InventarioPlanes",
        "InventarioID",
        inventario_id,
        {
            "Estado": "En conteo",
            "FechaInicio": ahora_texto(),
        },
    )

    registrar_historial(
        inventario_id=inventario_id,
        accion="INICIAR_CONTEO",
        estado_anterior="Planificado",
        estado_nuevo="En conteo",
    )


def guardar_conteo(
    *,
    inventario_id: str,
    item_id: str,
    articulo_codigo: str,
    ubicacion: str,
    contenedor: str,
    cantidad: float,
    observacion: str,
) -> None:
    usuario = obtener_usuario_actual()

    agregar_registro(
        "InventarioConteos",
        {
            "ConteoID": generar_conteo_id(),
            "InventarioID": inventario_id,
            "ItemID": item_id,
            "ArticuloCodigo": articulo_codigo,
            "Ubicacion": ubicacion,
            "Contenedor": contenedor,
            "CantidadContada": cantidad,
            "UsuarioConteo": usuario["usuario"],
            "UsuarioConteoNombre": (
                usuario["nombre"]
            ),
            "FechaConteo": ahora_texto(),
            "Observacion": observacion,
            "OrigenConteo": "Manual",
            "ImportacionID": "",
            "ArchivoOrigen": "",
            "FilaArchivo": "",
            "CantidadFotoUnidades": "",
            "CantidadFotoCajas": "",
            "CantidadRelevadaUnidades": cantidad,
            "CantidadRelevadaCajas": "",
            "DiferenciaArchivo": "",
            "FotoPertenece": "",
            "ClaveImportacion": "",
            "EstadoValidacion": "Válido",
        },
    )

    actualizar_registro(
        "InventarioItems",
        "ItemID",
        item_id,
        {
            "EstadoItem": "Contado",
        },
    )

    registrar_historial(
        inventario_id=inventario_id,
        item_id=item_id,
        articulo_codigo=articulo_codigo,
        accion="REGISTRAR_CONTEO",
        estado_anterior="Pendiente",
        estado_nuevo="Contado",
        detalle=(
            f"Ubicación {ubicacion}"
        ),
    )


def guardar_reconteo(
    *,
    inventario_id: str,
    item_id: str,
    articulo_codigo: str,
    ubicacion: str,
    contenedor: str,
    cantidad: float,
    observacion: str,
) -> None:
    usuario = obtener_usuario_actual()

    agregar_registro(
        "InventarioReconteos",
        {
            "ReconteoID": (
                generar_reconteo_id()
            ),
            "InventarioID": inventario_id,
            "ItemID": item_id,
            "ArticuloCodigo": articulo_codigo,
            "Ubicacion": ubicacion,
            "Contenedor": contenedor,
            "CantidadRecontada": cantidad,
            "UsuarioReconteo": (
                usuario["usuario"]
            ),
            "UsuarioReconteoNombre": (
                usuario["nombre"]
            ),
            "FechaReconteo": ahora_texto(),
            "Observacion": observacion,
        },
    )

    actualizar_registro(
        "InventarioItems",
        "ItemID",
        item_id,
        {
            "EstadoItem": "Recontado",
        },
    )

    registrar_historial(
        inventario_id=inventario_id,
        item_id=item_id,
        articulo_codigo=articulo_codigo,
        accion="REGISTRAR_RECONTEO",
        estado_anterior="Contado",
        estado_nuevo="Recontado",
        detalle=(
            f"Ubicación {ubicacion}"
        ),
    )


def actualizar_estado_plan(
    inventario_id: str,
    estado: str,
    *,
    finalizar: bool = False,
) -> None:
    cambios: dict[str, Any] = {
        "Estado": estado,
    }

    if finalizar:
        cambios["FechaFinalizacion"] = (
            ahora_texto()
        )

    actualizar_registro(
        "InventarioPlanes",
        "InventarioID",
        inventario_id,
        cambios,
    )

    registrar_historial(
        inventario_id=inventario_id,
        accion="ACTUALIZAR_ESTADO_PLAN",
        estado_nuevo=estado,
    )


def archivo_ya_importado(
    *,
    inventario_id: str,
    hash_archivo: str,
) -> bool:
    importaciones = leer_importaciones()

    if importaciones.empty:
        return False

    return bool(
        (
            importaciones["InventarioID"]
            .astype(str)
            .eq(str(inventario_id))
            & importaciones["HashArchivo"]
            .astype(str)
            .eq(str(hash_archivo))
            & importaciones[
                "EstadoImportacion"
            ]
            .astype(str)
            .eq("Confirmada")
        ).any()
    )


def guardar_importacion_conteos(
    *,
    inventario_id: str,
    nombre_archivo: str,
    hash_archivo: str,
    validacion: pd.DataFrame,
    resumen: Any,
) -> str:
    """
    Guarda las filas válidas de una importación DIGIP.
    """

    validos = validacion.loc[
        validacion[
            "EstadoValidacion"
        ].eq("Válido")
    ].copy()

    if validos.empty:
        raise ValueError(
            "La importación no contiene registros válidos."
        )

    if archivo_ya_importado(
        inventario_id=inventario_id,
        hash_archivo=hash_archivo,
    ):
        raise ValueError(
            "Este archivo ya fue importado para el plan."
        )

    usuario = obtener_usuario_actual()
    importacion_id = generar_importacion_id()

    registros = []

    for _, fila in validos.iterrows():
        registros.append({
            "ConteoID": generar_conteo_id(),
            "InventarioID": inventario_id,
            "ItemID": fila.get("ItemID", ""),
            "ArticuloCodigo": fila.get(
                "ArticuloCodigo",
                "",
            ),
            "Ubicacion": fila.get(
                "Ubicacion",
                "",
            ),
            "Contenedor": fila.get(
                "Contenedor",
                "",
            ),
            "CantidadContada": fila.get(
                "CantidadRelevadaUnidades",
                0,
            ),
            "UsuarioConteo": (
                usuario["usuario"]
            ),
            "UsuarioConteoNombre": (
                fila.get(
                    "UsuarioRelevamiento",
                    "",
                )
                or usuario["nombre"]
            ),
            "FechaConteo": (
                fila.get(
                    "FechaRelevamiento",
                    "",
                )
                or ahora_texto()
            ),
            "Observacion": (
                "Importado desde archivo DIGIP"
            ),
            "OrigenConteo": "Archivo DIGIP",
            "ImportacionID": importacion_id,
            "ArchivoOrigen": nombre_archivo,
            "FilaArchivo": fila.get(
                "FilaArchivo",
                "",
            ),
            "CantidadFotoUnidades": fila.get(
                "CantidadFotoUnidades",
                "",
            ),
            "CantidadFotoCajas": fila.get(
                "CantidadFotoCajas",
                "",
            ),
            "CantidadRelevadaUnidades": (
                fila.get(
                    "CantidadRelevadaUnidades",
                    "",
                )
            ),
            "CantidadRelevadaCajas": fila.get(
                "CantidadRelevadaCajas",
                "",
            ),
            "DiferenciaArchivo": fila.get(
                "DiferenciaArchivo",
                "",
            ),
            "FotoPertenece": fila.get(
                "FotoPertenece",
                "",
            ),
            "ClaveImportacion": fila.get(
                "ClaveImportacion",
                "",
            ),
            "EstadoValidacion": "Válido",
        })

    agregar_registros(
        "InventarioConteos",
        registros,
    )

    for item_id in validos[
        "ItemID"
    ].dropna().astype(str).unique():
        actualizar_registro(
            "InventarioItems",
            "ItemID",
            item_id,
            {
                "EstadoItem": "Contado",
            },
        )

    agregar_registro(
        "InventarioImportaciones",
        {
            "ImportacionID": importacion_id,
            "InventarioID": inventario_id,
            "TipoImportacion": "Conteo inicial",
            "NombreArchivo": nombre_archivo,
            "HashArchivo": hash_archivo,
            "FechaCarga": ahora_texto(),
            "UsuarioCarga": usuario["usuario"],
            "UsuarioCargaNombre": (
                usuario["nombre"]
            ),
            "RegistrosOriginales": (
                resumen.registros_originales
            ),
            "RegistrosValidos": (
                resumen.registros_validos
            ),
            "DuplicadosArchivo": (
                resumen.duplicados_archivo
            ),
            "FueraDelPlan": (
                resumen.fuera_del_plan
            ),
            "Ambiguos": resumen.ambiguos,
            "Errores": resumen.errores,
            "EstadoImportacion": "Confirmada",
        },
    )

    registrar_historial(
        inventario_id=inventario_id,
        accion="IMPORTAR_CONTEO_DIGIP",
        estado_nuevo="Conteos importados",
        detalle=(
            f"{nombre_archivo} · "
            f"{resumen.registros_validos} válidos"
        ),
    )

    return importacion_id



def guardar_acciones_diagnostico(inventario_id: str, acciones: pd.DataFrame) -> None:
    if acciones is None or acciones.empty:
        return
    existentes = leer_acciones()
    usuario = obtener_usuario_actual()
    ahora = ahora_texto()
    mapa = {}
    if not existentes.empty:
        for _, fila in existentes.iterrows():
            mapa[(str(fila.get("InventarioID", "")), str(fila.get("ArticuloCodigo", "")))] = str(fila.get("AccionID", ""))

    nuevos = []
    for _, fila in acciones.iterrows():
        clave = (str(inventario_id), str(fila.get("ArticuloCodigo", "")))
        datos = {
            "InventarioID": inventario_id,
            "ArticuloCodigo": fila.get("ArticuloCodigo", ""),
            "ArticuloDescripcion": fila.get("ArticuloDescripcion", ""),
            "Diagnostico": fila.get("Diagnostico", ""),
            "AccionSugerida": fila.get("AccionSugerida", ""),
            "SistemaObjetivo": fila.get("SistemaObjetivo", ""),
            "TipoUbicacion": fila.get("TipoUbicacionObjetivo", ""),
            "UbicacionesSugeridas": fila.get("UbicacionesSugeridas", ""),
            "DiferenciaERPvsWMS": fila.get("DiferenciaERPvsWMS", 0),
            "DiferenciaFisicavsWMS": fila.get("DiferenciaFisicavsWMS", 0),
            "FechaActualizacion": ahora,
            "UsuarioUltimaActualizacion": usuario["nombre"] or usuario["usuario"],
        }
        if clave in mapa and mapa[clave]:
            actualizar_registro("InventarioAcciones", "AccionID", mapa[clave], datos)
        else:
            datos.update({
                "AccionID": generar_accion_id(), "EstadoAccion": "Pendiente",
                "Responsable": "", "FechaCreacion": ahora, "CausaRaiz": "",
                "Resolucion": "", "Observaciones": "",
            })
            nuevos.append(datos)
    if nuevos:
        agregar_registros("InventarioAcciones", nuevos)


def actualizar_acciones_desde_editor(tabla: pd.DataFrame) -> None:
    if tabla is None or tabla.empty:
        return
    usuario = obtener_usuario_actual()
    for _, fila in tabla.iterrows():
        accion_id = str(fila.get("AccionID", "")).strip()
        if not accion_id:
            continue
        actualizar_registro(
            "InventarioAcciones", "AccionID", accion_id,
            {
                "EstadoAccion": fila.get("EstadoAccion", "Pendiente"),
                "Responsable": fila.get("Responsable", ""),
                "CausaRaiz": fila.get("CausaRaiz", ""),
                "Resolucion": fila.get("Resolucion", ""),
                "Observaciones": fila.get("Observaciones", ""),
                "FechaActualizacion": ahora_texto(),
                "UsuarioUltimaActualizacion": usuario["nombre"] or usuario["usuario"],
            },
        )
