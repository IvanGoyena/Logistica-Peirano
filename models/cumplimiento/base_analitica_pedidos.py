from __future__ import annotations

import re
import unicodedata
from typing import Iterable

import numpy as np
import pandas as pd

from models.cumplimiento.historico_proceso_pedidos import resumir_hitos_pedido

MODELO_CICLO_VERSION = "2026-08-27-v8-digip-nuevo-reporte"


# ==========================================================
# UTILIDADES DE NORMALIZACIÓN
# ==========================================================


def _normalizar_texto(valor: object) -> str:
    texto = "" if pd.isna(valor) else str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texto.upper())




ESTADOS_PEDIDO_CERRADO = {
    "COMPLETO",
    "COMPLETADO",
    "CERRADO",
    "FINALIZADO",
    "FINAL",
}


def _normalizar_estado_pedido(valor: object) -> str:
    return _normalizar_texto(valor)


def _es_estado_pedido_cerrado(valor: object) -> bool:
    estado = _normalizar_estado_pedido(valor)
    return estado in ESTADOS_PEDIDO_CERRADO


def _estado_pedido_consolidado(serie: pd.Series):
    """Prioriza un estado cerrado cuando un pedido tiene varias transmisiones."""
    valores = [
        valor for valor in serie.dropna().tolist()
        if str(valor).strip()
    ]
    if not valores:
        return np.nan

    for valor in valores:
        if _es_estado_pedido_cerrado(valor):
            return valor

    return valores[0]


def _buscar_columna(df: pd.DataFrame, candidatos: Iterable[str]) -> str | None:
    if df is None or df.empty:
        return None

    mapa = {_normalizar_texto(c): c for c in df.columns}
    for candidato in candidatos:
        encontrado = mapa.get(_normalizar_texto(candidato))
        if encontrado is not None:
            return encontrado
    return None


def _buscar_columna_pedido(df: pd.DataFrame) -> str | None:
    """Detecta la columna de pedido aun cuando el reporte cambia el encabezado."""
    exactos = [
        # Reporte DIGIP actual (27/08/2026): esta es la clave logística/ERP.
        # Debe priorizarse sobre "Pedido Id", que es el ID interno de DIGIP.
        "Código pedido", "Codigo pedido", "Código Pedido", "Codigo Pedido",
        "CodigoPedido",
        # Formatos históricos / alternativos.
        "Pedido", "Numero", "Número", "NumeroPedido", "NúmeroPedido",
        "PedidoNumero", "Nro Pedido", "NroPedido", "Número de pedido",
        "Numero de pedido",
        "Documento", "NumeroDocumento", "Número Documento",
        "Pedido ERP", "Numero Pedido ERP", "Número Pedido ERP",
        "Pedido Externo", "Referencia Pedido",
        # IDs internos quedan como último recurso.
        "Pedido ID", "PedidoId", "IdPedido",
    ]
    encontrada = _buscar_columna(df, exactos)
    if encontrada is not None:
        return encontrada

    # Segunda pasada: acepta encabezados compuestos como
    # "Pedidos.Numero", "N° Pedido ERP" o "Número de Pedido Cliente".
    candidatos = []
    for columna in df.columns:
        normalizada = _normalizar_texto(columna)
        puntaje = 0
        if "PEDIDO" in normalizada:
            puntaje += 10
        if any(token in normalizada for token in ("NUMERO", "NRO", "ID", "DOCUMENTO")):
            puntaje += 3
        if any(token in normalizada for token in ("ESTADO", "FECHA", "CLIENTE", "TIPO", "CANTIDAD")):
            puntaje -= 8
        if "PREPARACION" in normalizada and "PEDIDO" not in normalizada:
            puntaje -= 10
        if puntaje > 0:
            candidatos.append((puntaje, str(columna)))

    if candidatos:
        candidatos.sort(key=lambda x: (-x[0], len(x[1])))
        return candidatos[0][1]
    return None


def _serie_texto(df: pd.DataFrame, columna: str | None) -> pd.Series:
    if columna is None:
        return pd.Series("", index=df.index, dtype="object")
    return df[columna].fillna("").astype(str).str.strip()


def normalizar_clave_pedido(valor: object) -> str:
    """
    Unifica formatos como 0001-00202684, 202684, 202684.0 o PED-202684.
    Se conserva el último bloque numérico sin ceros a la izquierda.
    """
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    if not texto:
        return ""

    texto = re.sub(r"\.0$", "", texto)
    bloques = re.findall(r"\d+", texto)
    if not bloques:
        return _normalizar_texto(texto)

    ultimo = bloques[-1].lstrip("0")
    return ultimo or "0"


def normalizar_codigo_pedido_digip(valor: object) -> str:
    """
    Convierte códigos DIGIP como:
    - 0001  213038-1 -> 213038
    - 0008  2767-1   -> 2767
    """
    if pd.isna(valor):
        return ""

    texto = str(valor).strip()
    if not texto:
        return ""

    # Quita el prefijo de cuatro dígitos y toma el número anterior
    # al sufijo de transmisión.
    coincidencia = re.search(r"^\s*\d{4}[-\s]+0*(\d+)(?:-\d+)?\s*$", texto)
    if coincidencia:
        return coincidencia.group(1)

    # Formato alternativo: toma el bloque central y descarta el último
    # bloque cuando funciona como número de transmisión.
    bloques = re.findall(r"\d+", texto)
    if len(bloques) >= 2:
        candidato = bloques[-2] if len(bloques) >= 3 else bloques[-1]
        return candidato.lstrip("0") or "0"

    return normalizar_clave_pedido(valor)


def _a_datetime(serie: pd.Series) -> pd.Series:
    """Convierte fechas y elimina la zona horaria sin romper fechas locales."""

    def convertir(valor):
        if pd.isna(valor) or str(valor).strip() == "":
            return pd.NaT

        try:
            fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
            if pd.isna(fecha):
                fecha = pd.to_datetime(valor, errors="coerce", dayfirst=True)
            if pd.isna(fecha):
                return pd.NaT

            fecha = pd.Timestamp(fecha)

            # Las fechas con zona se convierten a Buenos Aires y luego
            # se dejan sin timezone para poder compararlas y exportarlas.
            if fecha.tzinfo is not None:
                fecha = fecha.tz_convert("America/Argentina/Buenos_Aires")
                fecha = fecha.tz_localize(None)

            return fecha

        except Exception:
            return pd.NaT

    return serie.map(convertir).astype("datetime64[ns]")


def _combinar_fecha_hora(
    df: pd.DataFrame,
    candidatos_datetime: Iterable[str],
    candidatos_fecha: Iterable[str],
    candidatos_hora: Iterable[str],
) -> pd.Series:
    columna_datetime = _buscar_columna(df, candidatos_datetime)
    if columna_datetime:
        return _a_datetime(df[columna_datetime])

    columna_fecha = _buscar_columna(df, candidatos_fecha)
    columna_hora = _buscar_columna(df, candidatos_hora)

    if columna_fecha is None:
        return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")

    fecha = _serie_texto(df, columna_fecha)
    if columna_hora is None:
        return _a_datetime(fecha)

    hora = _serie_texto(df, columna_hora).replace("", "00:00:00")
    return _a_datetime(fecha + " " + hora)


def _primero_no_vacio(serie: pd.Series):
    valores = serie.dropna()
    if valores.empty:
        return np.nan
    if valores.dtype == "object":
        valores = valores[valores.astype(str).str.strip().ne("")]
    return valores.iloc[0] if not valores.empty else np.nan


# ==========================================================
# PREPARACIÓN DE FUENTES
# ==========================================================


def preparar_pedidos_digip(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ClavePedido"])

    base = df.copy()
    # El reporte DIGIP nuevo separa "Pedido Id" (ID interno) de
    # "Código pedido" (código real del pedido). Siempre priorizamos el segundo.
    col_pedido = _buscar_columna(
        base,
        [
            "Código pedido", "Codigo pedido", "Código Pedido",
            "Codigo Pedido", "CodigoPedido", "Codigo",
        ],
    ) or _buscar_columna_pedido(base)
    if col_pedido is None:
        # Último recurso: analiza el contenido de cada columna. Se priorizan
        # campos con valores numéricos o códigos del tipo 0001-00202684.
        candidatos_contenido = []
        for columna in base.columns:
            serie = base[columna].dropna().astype(str).str.strip()
            if serie.empty:
                continue
            muestra = serie.head(500)
            proporcion_codigo = muestra.str.match(
                r"^(?:[A-Z]{0,4}[-_/ ]*)?\d+(?:[-_/ ]\d+)*(?:\.0)?$",
                case=False,
                na=False,
            ).mean()
            proporcion_fecha = pd.to_datetime(
                muestra, errors="coerce", dayfirst=True
            ).notna().mean()
            unicos = muestra.nunique(dropna=True) / max(len(muestra), 1)
            nombre = _normalizar_texto(columna)
            penalizacion = 0
            if any(x in nombre for x in (
                "FECHA", "HORA", "CLIENTE", "ESTADO", "CANTIDAD",
                "UNIDAD", "PESO", "VOLUMEN", "PREPARACIONID", "TAREAID"
            )):
                penalizacion += 0.45
            puntaje = proporcion_codigo * 0.70 + unicos * 0.30 - proporcion_fecha * 0.65 - penalizacion
            candidatos_contenido.append((puntaje, proporcion_codigo, str(columna)))

        candidatos_contenido.sort(reverse=True)
        if candidatos_contenido and candidatos_contenido[0][0] >= 0.30:
            col_pedido = candidatos_contenido[0][2]
        else:
            columnas = ", ".join(map(str, base.columns.tolist()))
            muestra_columnas = {
                str(c): base[c].dropna().astype(str).head(3).tolist()
                for c in base.columns[:20]
            }
            raise ValueError(
                f"[{MODELO_CICLO_VERSION}] No se pudo identificar la columna "
                "de pedido en Pedidos DIGIP. "
                f"Columnas recibidas: {columnas}. "
                f"Muestras: {muestra_columnas}"
            )

    if _normalizar_texto(col_pedido) in {"CODIGO", "CODIGOPEDIDO"}:
        base["ClavePedido"] = base[col_pedido].map(normalizar_codigo_pedido_digip)
    else:
        base["ClavePedido"] = base[col_pedido].map(normalizar_clave_pedido)
    base = base[base["ClavePedido"].ne("")].copy()

    base["FechaHoraCreacion"] = _combinar_fecha_hora(
        base,
        ["FechaHoraCreacion", "Fecha Creacion", "Fecha creación", "Creado", "CreatedAt"],
        ["FechaCreacion", "Fecha creación", "Fecha Alta", "Fecha"],
        ["HoraCreacion", "Hora creación", "Hora Alta", "Hora"],
    )
    base["FechaHoraTransmision"] = _combinar_fecha_hora(
        base,
        ["FechaHoraTransmision", "Fecha Transmision", "Fecha transmisión", "Transmitido"],
        ["FechaTransmision", "Fecha transmisión", "Fecha Transmisión"],
        ["HoraTransmision", "Hora transmisión", "Hora Transmisión"],
    )

    campos = {
        "PedidoOriginal": [col_pedido],
        "ClienteCodigo": ["ClienteCodigo", "Código Cliente", "Código cliente", "Codigo cliente", "Cod Cliente"],
        "Cliente": ["ClienteDescripcion", "Cliente", "Razón Social", "Razon Social"],
        "EstadoPedido": ["Estado", "PedidoEstado", "Estado Pedido"],
        "EstadoPreparacion": ["PreparacionEstado", "Estado Preparacion", "Estado preparación"],
        "TipoPreparacion": ["TipoPreparacion", "Tipo Preparacion", "Tipo preparación"],
        "DespachoDescripcion": [
            "DespachoDescripcion", "Despacho Descripcion", "Despacho Descripción",
            "DescripcionDespacho", "Descripción Despacho", "AgrupadorDespacho",
            "Agrupador", "Despacho",
        ],
        "CodigoLogisticoPedido": [
            "CodigoLogistico", "Código Logístico", "Codigo Logistico",
            "codigo_logistico", "CodigoEntregaCliente", "Código Entrega Cliente",
            "ClienteCodigoLogistico", "CodigoSucursalEntrega",
        ],
        "CodigoDespacho": [
            "CodigoDespacho", "Codigo Despacho", "Código Despacho",
            "Codigo de despacho", "Código de despacho", "DespachoCodigo",
            "CodigoEntrega", "Codigo Entrega", "Código Entrega",
        ],
        "UnidadesPedidas": [
            # Reporte DIGIP actual.
            "Unidades pedidas", "Unidades Pedidas", "UnidadesPedidas",
            # Encabezados históricos / alternativos.
            "TotalUnidades", "Total Unidades", "UnidadesTotales",
            "Unidades Totales", "Unidades", "CantidadTotal",
            "Cantidad Total", "TotalCantidad", "Total Cantidad",
        ],
    }

    salida = pd.DataFrame(index=base.index)
    salida["ClavePedido"] = base["ClavePedido"]
    salida["FechaHoraCreacion"] = base["FechaHoraCreacion"]
    salida["FechaHoraTransmision"] = base["FechaHoraTransmision"]

    for destino, candidatos in campos.items():
        origen = _buscar_columna(base, candidatos)
        salida[destino] = base[origen] if origen else np.nan

    salida["UnidadesPedidas"] = pd.to_numeric(
        salida.get("UnidadesPedidas", 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    pedidos = (
        salida.sort_values(["ClavePedido", "FechaHoraCreacion"], na_position="last")
        .groupby("ClavePedido", as_index=False)
        .agg(
            PedidoOriginal=("PedidoOriginal", _primero_no_vacio),
            ClienteCodigo=("ClienteCodigo", _primero_no_vacio),
            Cliente=("Cliente", _primero_no_vacio),
            EstadoPedido=("EstadoPedido", _estado_pedido_consolidado),
            EstadoPreparacion=("EstadoPreparacion", _primero_no_vacio),
            TipoPreparacion=("TipoPreparacion", _primero_no_vacio),
            DespachoDescripcion=("DespachoDescripcion", _primero_no_vacio),
            CodigoLogisticoPedido=("CodigoLogisticoPedido", _primero_no_vacio),
            CodigoDespacho=("CodigoDespacho", _primero_no_vacio),
            UnidadesPedidas=("UnidadesPedidas", "max"),
            FechaHoraCreacion=("FechaHoraCreacion", "min"),
            FechaHoraTransmision=("FechaHoraTransmision", "min"),
        )
    )

    pedidos["EstadoPedidoNormalizado"] = pedidos[
        "EstadoPedido"
    ].map(_normalizar_estado_pedido)
    pedidos["EsPedidoCerrado"] = pedidos[
        "EstadoPedido"
    ].map(_es_estado_pedido_cerrado)

    return pedidos


def preparar_metricas_pedidos(df_tareas: pd.DataFrame | None) -> pd.DataFrame:
    if df_tareas is None or df_tareas.empty:
        return pd.DataFrame(columns=["ClavePedido"])

    base = df_tareas.copy()
    col_pedido = _buscar_columna(
        base,
        ["Pedido", "NumeroPedido", "Número Pedido", "PedidoNumero", "Numero", "Documento"],
    )
    if col_pedido is None:
        return pd.DataFrame(columns=["ClavePedido"])

    col_proceso = _buscar_columna(base, ["Proceso", "TipoProceso", "Actividad"])
    if col_proceso is None:
        return pd.DataFrame(columns=["ClavePedido"])

    base["ClavePedido"] = base[col_pedido].map(normalizar_clave_pedido)
    base["ProcesoNormalizado"] = _serie_texto(base, col_proceso).map(_normalizar_texto)

    inicio = _combinar_fecha_hora(
        base,
        ["FechaHoraInicio", "Inicio", "Fecha Inicio", "FechaInicio", "InicioTarea"],
        ["FechaInicio", "Fecha Inicio", "Fecha"],
        ["HoraInicio", "Hora Inicio"],
    )
    fin = _combinar_fecha_hora(
        base,
        ["FechaHoraFin", "Fin", "Fecha Fin", "FechaFin", "FinTarea"],
        ["FechaFin", "Fecha Fin", "Fecha"],
        ["HoraFin", "Hora Fin"],
    )

    # Si la ETL expone una única fecha/hora por tarea, se usa como hito.
    if inicio.isna().all():
        inicio = _combinar_fecha_hora(
            base,
            ["FechaHora", "Fecha", "Timestamp"],
            ["Fecha"],
            ["Hora"],
        )
    if fin.isna().all():
        fin = inicio.copy()

    base["InicioEtapa"] = inicio
    base["FinEtapa"] = fin

    preparacion = base[base["ProcesoNormalizado"].str.contains("PREPAR", na=False)].copy()
    control = base[base["ProcesoNormalizado"].str.contains("CONTROL", na=False)].copy()

    def consolidar(etapa: pd.DataFrame, prefijo: str) -> pd.DataFrame:
        if etapa.empty:
            return pd.DataFrame(columns=["ClavePedido"])
        return (
            etapa.groupby("ClavePedido", as_index=False)
            .agg(
                **{
                    f"FechaHoraInicio{prefijo}": ("InicioEtapa", "min"),
                    f"FechaHoraFin{prefijo}": ("FinEtapa", "max"),
                    f"CantidadTareas{prefijo}": ("ClavePedido", "size"),
                }
            )
        )

    prep = consolidar(preparacion, "Preparacion")
    ctrl = consolidar(control, "Control")

    if prep.empty:
        return ctrl
    if ctrl.empty:
        return prep
    return prep.merge(ctrl, on="ClavePedido", how="outer")


def preparar_hojas_ruta(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ClavePedido"])

    base = df.copy()
    col_pedido = _buscar_columna(base, ["Pedido", "NumeroPedido", "Número Pedido"])
    if col_pedido is None:
        raise ValueError("Hojas de Ruta no contiene la columna Pedido.")

    base["ClavePedido"] = base[col_pedido].map(normalizar_clave_pedido)
    base = base[base["ClavePedido"].ne("")].copy()

    col_fecha = _buscar_columna(base, ["Fecha Hr", "FechaHojaRuta", "Fecha Hoja Ruta"])
    base["FechaHoraHojaRuta"] = (
        _a_datetime(base[col_fecha]) if col_fecha else pd.NaT
    )

    columnas = {
        "HojaRuta": ["Hoja Ruta", "HojaRuta"],
        "ClienteHR": ["Cliente"],
        "ClienteCodigoHR": [
            "ClienteCodigo", "Cliente Codigo", "Código Cliente", "Codigo Cliente",
            "Codigo_Cliente", "Cod Cliente", "Código de cliente", "Codigo de cliente",
        ],
        "ZonaHR": ["Zona"],
        "Flete": ["Flete"],
        "Expreso": ["Expreso"],
        "LugarEntrega": ["Lugar Entrega"],
        "Localidad": ["Localidad"],
        "CodigoEntrega": [
            "CodigoEntrega", "Codigo Entrega", "Código Entrega",
            "Codigo de entrega", "Código de entrega", "Cod Entrega",
            "Codigo Logistico", "Código Logístico", "codigo_logistico",
        ],
        "BultosHR": ["Bultos"],
        "PesoHR": ["Peso"],
        "VolumenHR": ["Volumen"],
        "UnidadesHR": ["Cantidad"],
    }

    salida = pd.DataFrame(index=base.index)
    salida["ClavePedido"] = base["ClavePedido"]
    salida["PedidoHojaRuta"] = base[col_pedido]
    salida["FechaHoraHojaRuta"] = base["FechaHoraHojaRuta"]

    for destino, candidatos in columnas.items():
        origen = _buscar_columna(base, candidatos)
        salida[destino] = base[origen] if origen else np.nan

    for numerica in ["BultosHR", "PesoHR", "VolumenHR", "UnidadesHR"]:
        salida[numerica] = pd.to_numeric(
            salida[numerica].astype(str)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )

    primera = (
        salida.sort_values("FechaHoraHojaRuta")
        .groupby("ClavePedido", as_index=False)
        .agg(
            PedidoHojaRuta=("PedidoHojaRuta", _primero_no_vacio),
            FechaHoraPrimeraHojaRuta=("FechaHoraHojaRuta", "min"),
            FechaHoraUltimaHojaRuta=("FechaHoraHojaRuta", "max"),
            CantidadHojasRuta=("FechaHoraHojaRuta", "size"),
            HojaRuta=("HojaRuta", _primero_no_vacio),
            ClienteHR=("ClienteHR", _primero_no_vacio),
            ClienteCodigoHR=("ClienteCodigoHR", _primero_no_vacio),
            ZonaHR=("ZonaHR", _primero_no_vacio),
            Flete=("Flete", _primero_no_vacio),
            Expreso=("Expreso", _primero_no_vacio),
            LugarEntrega=("LugarEntrega", _primero_no_vacio),
            Localidad=("Localidad", _primero_no_vacio),
            CodigoEntrega=("CodigoEntrega", _primero_no_vacio),
            BultosHR=("BultosHR", "sum"),
            PesoHR=("PesoHR", "sum"),
            VolumenHR=("VolumenHR", "sum"),
            UnidadesHR=("UnidadesHR", "sum"),
        )
    )
    return primera


# ==========================================================
# BASE ANALÍTICA
# ==========================================================


def construir_ciclo_vida_pedidos(
    df_pedidos: pd.DataFrame | None,
    df_tareas: pd.DataFrame | None,
    df_hojas_ruta: pd.DataFrame | None,
    df_proceso_pedidos: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    pedidos_todos = preparar_pedidos_digip(df_pedidos)
    metricas = preparar_metricas_pedidos(df_tareas)
    hojas = preparar_hojas_ruta(df_hojas_ruta)
    proceso = resumir_hitos_pedido(df_proceso_pedidos)

    # Pedidos DIGIP es la fuente maestra del dashboard. Solo ingresan pedidos
    # cuyo estado final está cerrado/completo. Las demás fuentes enriquecen
    # mediante LEFT JOIN y nunca crean registros nuevos.
    pedidos = pedidos_todos.loc[
        pedidos_todos.get(
            "EsPedidoCerrado",
            pd.Series(False, index=pedidos_todos.index),
        ).fillna(False)
    ].copy()

    if pedidos.empty:
        return pd.DataFrame(), {
            "pedidos_digip": int(pedidos_todos["ClavePedido"].nunique())
            if not pedidos_todos.empty else 0,
            "pedidos_digip_cerrados": 0,
            "pedidos_digip_excluidos_estado": int(
                pedidos_todos["ClavePedido"].nunique()
            ) if not pedidos_todos.empty else 0,
            "pedidos_metricas": int(metricas["ClavePedido"].nunique())
            if not metricas.empty else 0,
            "pedidos_hoja_ruta": int(hojas["ClavePedido"].nunique())
            if not hojas.empty else 0,
            "pedidos_proceso_mensual": int(proceso["ClavePedido"].nunique())
            if not proceso.empty else 0,
            "pedidos_base": 0,
        }

    ciclo = pedidos.copy()
    for fuente in (metricas, proceso, hojas):
        if not fuente.empty:
            ciclo = ciclo.merge(fuente, on="ClavePedido", how="left")

    ciclo["Pedido"] = ciclo.get("PedidoOriginal", pd.Series(index=ciclo.index)).fillna(
        ciclo.get("PedidoHojaRuta", pd.Series(index=ciclo.index))
    )
    ciclo["ClienteFinal"] = ciclo.get("Cliente", pd.Series(index=ciclo.index)).fillna(
        ciclo.get("ClienteHR", pd.Series(index=ciclo.index))
    )
    if "ClienteProceso" in ciclo.columns:
        ciclo["ClienteFinal"] = ciclo["ClienteFinal"].fillna(ciclo["ClienteProceso"])
    if "PedidoProceso" in ciclo.columns:
        ciclo["Pedido"] = ciclo["Pedido"].fillna(ciclo["PedidoProceso"])

    # El reporte mensual de proceso contiene los hitos exactos. Cuando existe,
    # prevalece sobre las fechas derivadas de los históricos de tareas.
    reemplazos_proceso = {
        "FechaHoraInicioPreparacion": "FechaHoraInicioPreparacionProceso",
        "FechaHoraFinPreparacion": "FechaHoraFinPreparacionProceso",
        "FechaHoraInicioControl": "FechaHoraInicioControlProceso",
        "FechaHoraFinControl": "FechaHoraFinControlProceso",
    }
    for destino, origen in reemplazos_proceso.items():
        if origen in ciclo.columns:
            if destino not in ciclo.columns:
                ciclo[destino] = pd.NaT
            ciclo[destino] = ciclo[origen].combine_first(ciclo[destino])

    # Fill Rate: las unidades pedidas y controladas salen de Filtrar
    # Preparación. Pedidos DIGIP se conserva como universo maestro.
    ciclo["UnidadesPedidas"] = pd.to_numeric(
        ciclo.get("UnidadesPedidasProceso", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)
    ciclo["UnidadesControladasProceso"] = pd.to_numeric(
        ciclo.get("UnidadesControladasProceso", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    hitos = [
        "FechaHoraCreacion",
        "FechaHoraTransmision",
        "FechaHoraInicioPreparacion",
        "FechaHoraFinPreparacion",
        "FechaHoraInicioControl",
        "FechaHoraFinControl",
        "FechaHoraPrimeraHojaRuta",
        "FechaHoraUltimaHojaRuta",
    ]
    for columna in hitos:
        if columna not in ciclo.columns:
            ciclo[columna] = pd.NaT
        ciclo[columna] = _a_datetime(ciclo[columna])

    intervalos = {
        "HorasCreacionTransmision": ("FechaHoraCreacion", "FechaHoraTransmision"),
        "HorasTransmisionPreparacion": ("FechaHoraTransmision", "FechaHoraInicioPreparacion"),
        "HorasPreparacion": ("FechaHoraInicioPreparacion", "FechaHoraFinPreparacion"),
        "HorasEsperaControl": ("FechaHoraFinPreparacion", "FechaHoraInicioControl"),
        "HorasControl": ("FechaHoraInicioControl", "FechaHoraFinControl"),
        "HorasControlHojaRuta": ("FechaHoraFinControl", "FechaHoraPrimeraHojaRuta"),
        "HorasCicloHastaHojaRuta": ("FechaHoraCreacion", "FechaHoraPrimeraHojaRuta"),
    }
    def calcular_horas_seguras(valor_inicio, valor_fin):
        if pd.isna(valor_inicio) or pd.isna(valor_fin):
            return np.nan
        try:
            inicio_ts = pd.Timestamp(valor_inicio)
            fin_ts = pd.Timestamp(valor_fin)
            if inicio_ts.tzinfo is not None:
                inicio_ts = inicio_ts.tz_convert("America/Argentina/Buenos_Aires").tz_localize(None)
            if fin_ts.tzinfo is not None:
                fin_ts = fin_ts.tz_convert("America/Argentina/Buenos_Aires").tz_localize(None)
            horas = (fin_ts - inicio_ts).total_seconds() / 3600
            return horas if horas >= 0 else np.nan
        except Exception:
            return np.nan

    for destino, (inicio, fin) in intervalos.items():
        ciclo[destino] = [
            calcular_horas_seguras(valor_inicio, valor_fin)
            for valor_inicio, valor_fin in zip(ciclo[inicio], ciclo[fin])
        ]

    ciclo["TieneCreacion"] = ciclo["FechaHoraCreacion"].notna()
    ciclo["TieneTransmision"] = ciclo["FechaHoraTransmision"].notna()
    ciclo["TienePreparacion"] = ciclo["FechaHoraFinPreparacion"].notna()
    ciclo["TieneControl"] = ciclo["FechaHoraFinControl"].notna()
    ciclo["TieneHojaRuta"] = ciclo["FechaHoraPrimeraHojaRuta"].notna()

    # Como el universo ya contiene únicamente pedidos cerrados de DIGIP,
    # la etapa se expresa como control de integridad del ciclo.
    condiciones = [
        ciclo["TieneHojaRuta"],
        ciclo["TieneControl"],
        ciclo["TienePreparacion"],
    ]
    estados = [
        "CERRADO CON HOJA DE RUTA",
        "CERRADO SIN HOJA DE RUTA",
        "CERRADO SIN CONTROL",
    ]
    ciclo["UltimaEtapaRegistrada"] = np.select(
        condiciones,
        estados,
        default="CERRADO SIN PREPARACION",
    )

    orden = [
        "Pedido", "ClavePedido", "ClienteCodigo", "ClienteCodigoHR", "ClienteFinal",
        "CodigoDespacho", "CodigoLogisticoPedido", "DespachoDescripcion",
        "EstadoPedido", "EstadoPedidoNormalizado",
        "EsPedidoCerrado", "EstadoPreparacion", "TipoPreparacion",
        "FechaHoraCreacion", "FechaHoraTransmision",
        "FechaHoraInicioPreparacion", "FechaHoraFinPreparacion",
        "FechaHoraInicioControl", "FechaHoraFinControl",
        "FechaHoraPrimeraHojaRuta", "FechaHoraUltimaHojaRuta",
        "CantidadHojasRuta", "HojaRuta", "ZonaHR", "Flete", "Expreso",
        "LugarEntrega", "Localidad", "CodigoEntrega",
        "UnidadesPedidas", "UnidadesPedidasProceso",
        "UnidadesControladasProceso", "LineasPedidasProceso",
        "LineasCompletasProceso",
        "UnidadesHR", "BultosHR", "PesoHR", "VolumenHR",
        "HorasCreacionTransmision", "HorasTransmisionPreparacion",
        "HorasPreparacion", "HorasEsperaControl", "HorasControl",
        "HorasControlHojaRuta", "HorasCicloHastaHojaRuta",
        "UltimaEtapaRegistrada", "TieneCreacion", "TieneTransmision",
        "TienePreparacion", "TieneControl", "TieneHojaRuta",
    ]
    ciclo = ciclo[[c for c in orden if c in ciclo.columns]].sort_values(
        ["FechaHoraCreacion", "Pedido"], ascending=[False, True], na_position="last"
    )

    total_digip = int(pedidos_todos["ClavePedido"].nunique()) if not pedidos_todos.empty else 0
    total_cerrados = int(pedidos["ClavePedido"].nunique()) if not pedidos.empty else 0

    diagnostico = {
        "pedidos_digip": total_digip,
        "pedidos_digip_cerrados": total_cerrados,
        "pedidos_digip_excluidos_estado": max(total_digip - total_cerrados, 0),
        "pedidos_metricas": int(metricas["ClavePedido"].nunique()) if not metricas.empty else 0,
        "pedidos_hoja_ruta": int(hojas["ClavePedido"].nunique()) if not hojas.empty else 0,
        "pedidos_proceso_mensual": int(proceso["ClavePedido"].nunique()) if not proceso.empty else 0,
        "pedidos_base": int(ciclo["ClavePedido"].nunique()),
        "con_creacion": int(ciclo["TieneCreacion"].sum()),
        "con_transmision": int(ciclo["TieneTransmision"].sum()),
        "con_preparacion": int(ciclo["TienePreparacion"].sum()),
        "con_control": int(ciclo["TieneControl"].sum()),
        "con_hoja_ruta": int(ciclo["TieneHojaRuta"].sum()),
    }
    return ciclo.reset_index(drop=True), diagnostico
