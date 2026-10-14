from __future__ import annotations

import pandas as pd
import streamlit as st

from config import (
    ES_STREAMLIT_CLOUD,
    CARPETA_ERP,
    CARPETA_MAESTROS,
    CARPETA_WMS,
)
from utils.leer_datos import leer_archivo


def _texto(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def _normalizar_pedido(serie: pd.Series) -> pd.Series:
    return (
        _texto(serie)
        .str.split()
        .str[-1]
        .str.split("-")
        .str[0]
        .str.strip()
    )


def _leer_sql(consulta: str) -> pd.DataFrame:
    # Importación diferida: Streamlit Cloud no intenta abrir PostgreSQL.
    from sqlalchemy import text as sql_text
    from database import engine

    with engine.connect() as conexion:
        return pd.read_sql_query(sql_text(consulta), conexion)


def _cargar_datos_sql() -> dict[str, pd.DataFrame]:
    pedidos = _leer_sql(
        '''
        SELECT
            "Pedido", "Fecha", "FechaCreacion", "FechaFinControl",
            "FechaTransmisionERP", "ClienteCodigo", "CodigoLogistico",
            "Cliente", "TotalUnidadesOperativas", "VolumenM3",
            "VolumetriaCompleta", "VolumetriaOrigen", "Planificacion",
            "CodigoDespacho", "Despacho", "Estado", "EstadoWMS",
            "EstadoPreparacion", "PreparacionID", "EstadoDatosERP",
            "PresenteWMSActual", "UltimaVezWMS", "EsMovimientoInterno",
            "NroEnvio"
        FROM analytics.vw_consultas_comerciales
        ORDER BY
            "FechaTransmisionERP" DESC NULLS LAST,
            "FechaCreacion" DESC NULLS LAST,
            "Pedido" DESC;
        '''
    )

    tareas = _leer_sql(
        '''
        WITH ultimo_run AS (
            SELECT run_id
            FROM raw.informe_tareas
            WHERE run_id IS NOT NULL
            ORDER BY loaded_at DESC NULLS LAST
            LIMIT 1
        )
        SELECT
            t.preparacion_id     AS "PreparacionId",
            t.contenedor_id      AS "ContenedorId",
            t.contenedor_numero  AS "ContenedorNumero",
            t.tarea_estado       AS "TareaEstado"
        FROM raw.informe_tareas t
        WHERE t.run_id = (SELECT run_id FROM ultimo_run)
          AND t.preparacion_id IS NOT NULL
          AND (
                t.contenedor_numero IS NOT NULL
                OR t.contenedor_id IS NOT NULL
              );
        '''
    )

    return {"pedidos": pedidos, "tareas": tareas}


def _cargar_maestros_sql() -> dict[str, pd.DataFrame]:
    clientes = _leer_sql(
        '''
        SELECT
            codigo_cliente AS "ClienteCodigo",
            nombre         AS "ClienteDescripcion"
        FROM analytics.vw_maestro_clientes
        WHERE codigo_cliente IS NOT NULL
        ORDER BY nombre, codigo_cliente;
        '''
    )

    articulos = _leer_sql(
        '''
        SELECT
            codigo_articulo AS "CodigoArticulo",
            descripcion     AS "ArticuloDescripcion"
        FROM analytics.vw_maestro_articulos
        WHERE codigo_articulo IS NOT NULL
        ORDER BY codigo_articulo;
        '''
    )

    return {"clientes": clientes, "articulos": articulos}


def _cargar_crudos_cloud() -> dict[str, pd.DataFrame]:
    # leer_archivo(): Cloud -> GitHub main; local -> archivo físico.
    return {
        "pedidos": leer_archivo(CARPETA_WMS, "Pedidos DIGIP", cache=False),
        "tareas": leer_archivo(CARPETA_WMS, "Informe Tareas", cache=False),
        "detalle": leer_archivo(CARPETA_ERP, "Detalle Pendientes", cache=False),
        "pendientes_erp": leer_archivo(CARPETA_ERP, "Pedidos Pendientes", cache=False),
        "transmisiones": leer_archivo(CARPETA_ERP, "Pedidos Transmicion", cache=False),
        "articulos": leer_archivo(CARPETA_MAESTROS, "Maestro Articulo", cache=True),
        "clientes": leer_archivo(CARPETA_MAESTROS, "Maestro Clientes", cache=True),
        "expresos": leer_archivo(CARPETA_MAESTROS, "Datos Expresos", cache=True),
        "volumetria": leer_archivo(CARPETA_MAESTROS, "Maestro Volumetria", cache=True),
    }


def _construir_pedidos_cloud(crudos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    # Reutiliza las transformaciones históricas ya existentes en el proyecto.
    from models.pedidos import construir_tabla_pedidos
    from models.pendiente import construir_tabla_pendientes
    from models.transmisiones import construir_tabla_transmisiones
    from models.clientes import construir_tabla_clientes
    from models.expresos import construir_tabla_expresos

    tabla = construir_tabla_pedidos(
        crudos["pedidos"].copy(),
        crudos["detalle"].copy(),
        crudos["articulos"].copy(),
        crudos["clientes"].copy(),
        crudos["volumetria"].copy(),
    )

    transmisiones = construir_tabla_transmisiones(crudos["transmisiones"].copy())
    pendientes = construir_tabla_pendientes(crudos["pendientes_erp"].copy())
    clientes = construir_tabla_clientes(crudos["clientes"].copy())
    expresos = construir_tabla_expresos(crudos["expresos"].copy())

    tabla["Pedido"] = _normalizar_pedido(tabla["Pedido"])
    for df in (transmisiones, pendientes):
        if "Pedido" in df.columns:
            df["Pedido"] = _normalizar_pedido(df["Pedido"])

    # Transmisiones ERP
    cols_trans = [c for c in [
        "Pedido", "NroEnvioERP", "EstadoTransmisionERP",
        "FechaTransmisionERP", "HoraTransmisionERP"
    ] if c in transmisiones.columns]
    if cols_trans:
        tabla = tabla.merge(
            transmisiones[cols_trans].drop_duplicates("Pedido", keep="last"),
            on="Pedido", how="left", validate="many_to_one"
        )

    # ERP pendiente / código logístico
    cols_pend = [c for c in [
        "Pedido", "CodigoSucursal", "CodigoExpreso", "ImporteERP",
        "EstadoERP", "FechaPedidoERP"
    ] if c in pendientes.columns]
    if cols_pend:
        tabla = tabla.merge(
            pendientes[cols_pend].drop_duplicates("Pedido", keep="first"),
            on="Pedido", how="left", validate="many_to_one"
        )

    # Planificación por cliente/expreso (misma regla histórica de Consultas).
    if "CodigoSucursal" not in tabla.columns:
        tabla["CodigoSucursal"] = ""
    tabla["CodigoSucursal"] = _texto(tabla["CodigoSucursal"]).str.upper()

    if not clientes.empty:
        cli = clientes[["CodigoSucursal", "FrecuenciaPreparacion", "FrecuenciaEntrega"]].copy()
        cli["CodigoSucursal"] = _texto(cli["CodigoSucursal"]).str.upper()
        cli = cli.drop_duplicates("CodigoSucursal", keep="first")
        tabla = tabla.merge(cli, on="CodigoSucursal", how="left", validate="many_to_one")
    else:
        tabla["FrecuenciaPreparacion"] = ""
        tabla["FrecuenciaEntrega"] = ""

    if "CodigoExpreso" not in tabla.columns:
        tabla["CodigoExpreso"] = ""
    tabla["CodigoExpreso"] = _texto(tabla["CodigoExpreso"]).str.upper()

    if not expresos.empty:
        exp = expresos[["CodigoExpreso", "LocalidadExpreso", "ZonaAgrupadorExpreso"]].copy()
        exp["CodigoExpreso"] = _texto(exp["CodigoExpreso"]).str.upper()
        exp = exp.drop_duplicates("CodigoExpreso", keep="first")
        tabla = tabla.merge(exp, on="CodigoExpreso", how="left", validate="many_to_one")
    else:
        tabla["LocalidadExpreso"] = ""
        tabla["ZonaAgrupadorExpreso"] = ""

    frecuencia = _texto(tabla.get("FrecuenciaEntrega", pd.Series("", index=tabla.index))).str.upper()
    zona_expreso = _texto(tabla.get("ZonaAgrupadorExpreso", pd.Series("", index=tabla.index))).str.upper()
    dias = {"LUNES", "MARTES", "MIERCOLES", "MIÉRCOLES", "JUEVES", "VIERNES"}
    tabla["Planificacion"] = frecuencia.where(
        frecuencia.isin(dias),
        zona_expreso.where(zona_expreso.ne(""), frecuencia),
    )

    # Contrato que consume models.consultas_comerciales.base_operativa.
    salida = pd.DataFrame(index=tabla.index)
    salida["Pedido"] = _normalizar_pedido(tabla["Pedido"])
    salida["Fecha"] = pd.to_datetime(tabla.get("Fecha"), errors="coerce")
    salida["FechaCreacion"] = salida["Fecha"]
    salida["FechaFinControl"] = pd.NaT
    salida["FechaTransmisionERP"] = pd.to_datetime(
        tabla.get("FechaTransmisionERP", pd.Series(pd.NaT, index=tabla.index)),
        errors="coerce",
    )
    salida["ClienteCodigo"] = _texto(
        tabla.get("ClienteCodigo", pd.Series("", index=tabla.index))
    ).str.upper()
    salida["CodigoLogistico"] = _texto(
        tabla.get("CodigoSucursal", pd.Series("", index=tabla.index))
    ).str.upper()
    salida["Cliente"] = _texto(
        tabla.get("ClienteDescripcion", pd.Series("", index=tabla.index))
    )

    pedidas = pd.to_numeric(
        tabla.get("UnidadesPedidas", pd.Series(pd.NA, index=tabla.index)),
        errors="coerce",
    )
    satisfechas = pd.to_numeric(
        tabla.get("UnidadesSatisfechas", pd.Series(pd.NA, index=tabla.index)),
        errors="coerce",
    )
    unidades_modelo = pd.to_numeric(
        tabla.get("TotalUnidades", pd.Series(0, index=tabla.index)),
        errors="coerce",
    ).fillna(0)
    unidades_wms = (pedidas.fillna(0) - satisfechas.fillna(0)).clip(lower=0)
    salida["TotalUnidadesOperativas"] = unidades_modelo.where(
        ~pedidas.notna(), unidades_wms
    ).fillna(0)

    salida["VolumenM3"] = pd.to_numeric(
        tabla.get("TotalM3", pd.Series(0.0, index=tabla.index)),
        errors="coerce",
    ).fillna(0.0)
    salida["VolumetriaCompleta"] = salida["VolumenM3"] > 0
    salida["VolumetriaOrigen"] = "ARCHIVO_VERSIONADO"
    salida.loc[salida["VolumenM3"].le(0), "VolumetriaOrigen"] = "SIN_DATOS_VOLUMETRIA"

    salida["Planificacion"] = _texto(tabla["Planificacion"])
    salida["CodigoDespacho"] = _texto(
        tabla.get("CodigoDespacho", pd.Series("", index=tabla.index))
    )
    salida["Despacho"] = _texto(
        tabla.get("DespachoDescripcion", pd.Series("", index=tabla.index))
    )
    salida["Estado"] = _texto(
        tabla.get("Estado", pd.Series("", index=tabla.index))
    )
    salida["EstadoWMS"] = salida["Estado"]
    salida["EstadoPreparacion"] = _texto(
        tabla.get("PreparacionEstado", pd.Series("", index=tabla.index))
    )
    salida["PreparacionID"] = _texto(
        tabla.get("PreparacionID", pd.Series("", index=tabla.index))
    )

    pedidos_erp = set(pendientes["Pedido"].astype(str)) if "Pedido" in pendientes.columns else set()
    salida["EstadoDatosERP"] = salida["Pedido"].map(
        lambda p: "CON_DATOS_ERP" if p in pedidos_erp else "SIN_DATOS_ERP"
    )

    # Pedidos DIGIP es snapshot actual: todas estas filas están presentes hoy.
    salida["PresenteWMSActual"] = True
    salida["UltimaVezWMS"] = salida["Fecha"].where(
        salida["Fecha"].notna(), pd.Timestamp.now()
    )
    salida["EsMovimientoInterno"] = False
    salida["NroEnvio"] = _texto(
        tabla.get("NroEnvioERP", pd.Series("", index=tabla.index))
    )

    return salida.reset_index(drop=True)


def _preparar_tareas_cloud(tareas: pd.DataFrame) -> pd.DataFrame:
    columnas_finales = ["PreparacionId", "ContenedorId", "ContenedorNumero", "TareaEstado"]
    if tareas is None or tareas.empty:
        return pd.DataFrame(columns=columnas_finales)

    salida = tareas.copy()
    if "PreparacionId" not in salida.columns and "PreparacionID" in salida.columns:
        salida = salida.rename(columns={"PreparacionID": "PreparacionId"})
    if "ContenedorId" not in salida.columns and "ContenedorID" in salida.columns:
        salida = salida.rename(columns={"ContenedorID": "ContenedorId"})

    for c in columnas_finales:
        if c not in salida.columns:
            salida[c] = ""

    salida = salida[columnas_finales].copy()
    prep = _texto(salida["PreparacionId"])
    cont_num = _texto(salida["ContenedorNumero"])
    cont_id = _texto(salida["ContenedorId"])
    salida = salida.loc[prep.ne("") & (cont_num.ne("") | cont_id.ne(""))].copy()
    return salida.reset_index(drop=True)


def _cargar_datos_cloud() -> dict[str, pd.DataFrame]:
    crudos = _cargar_crudos_cloud()
    return {
        "pedidos": _construir_pedidos_cloud(crudos),
        "tareas": _preparar_tareas_cloud(crudos["tareas"]),
    }


def _cargar_maestros_cloud() -> dict[str, pd.DataFrame]:
    return {
        "clientes": leer_archivo(CARPETA_MAESTROS, "Maestro Clientes", cache=True),
        "articulos": leer_archivo(CARPETA_MAESTROS, "Maestro Articulo", cache=True),
    }


@st.cache_data(ttl=45, max_entries=2, show_spinner="Cargando pedidos comerciales...")
def cargar_datos_consultas() -> dict[str, pd.DataFrame]:
    """Host/local -> PostgreSQL. Streamlit Cloud -> archivos versionados/GitHub."""
    if ES_STREAMLIT_CLOUD:
        return _cargar_datos_cloud()
    return _cargar_datos_sql()


@st.cache_data(ttl=600, max_entries=2, show_spinner="Cargando maestros para el reclamo...")
def cargar_maestros_reclamos() -> dict[str, pd.DataFrame]:
    """En Cloud los maestros de Reclamos tampoco dependen de PostgreSQL."""
    if ES_STREAMLIT_CLOUD:
        return _cargar_maestros_cloud()
    return _cargar_maestros_sql()


def limpiar_cache_datos_consultas() -> None:
    cargar_datos_consultas.clear()


def limpiar_cache_maestros_reclamos() -> None:
    cargar_maestros_reclamos.clear()
