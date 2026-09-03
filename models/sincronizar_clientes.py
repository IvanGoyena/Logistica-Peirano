"""Validación de altas pendientes para el Maestro de Clientes.

MODO PRUEBA
-----------
Este módulo detecta códigos logísticos presentes en Pedidos Pendientes ERP
que todavía no existen en el Maestro Clientes y propone su planificación.
No escribe ni modifica ningún archivo.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from config_planificacion import ZONAS_PLANIFICACION
from models.pedidos import normalizar_pedidos_digip


ESTADOS_LISTOS = {
    "LISTO_HISTORICO",
    "LISTO_CONFIGURACION",
}

# Relación operativa utilizada cuando la zona solamente informa el día de
# entrega. La referencia histórica del propio maestro siempre tiene prioridad.
PREPARACION_POR_ENTREGA = {
    "LUNES": "JUEVES",
    "MARTES": "VIERNES",
    "MIERCOLES": "LUNES",
    "JUEVES": "MARTES",
    "VIERNES": "MIERCOLES",
    "DIARIA": "DIARIA",
    "DIARIOS": "DIARIA",
    "EXPRESO": "EXPRESO",
    "EXPRESOS": "EXPRESO",
}


def normalizar_valor(valor: object) -> str:
    """Normaliza una celda individual sin perder ceros iniciales existentes."""

    if pd.isna(valor):
        return ""

    texto = str(valor).strip()

    if texto.lower() == "nan":
        return ""

    if texto.endswith(".0"):
        texto = texto[:-2]

    return texto.upper()


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    """Normaliza una serie utilizada como clave."""

    return serie.apply(normalizar_valor)


def texto_limpio(valor: object) -> str:
    """Devuelve texto visible evitando valores nan/None."""

    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    return "" if texto.lower() == "nan" else texto


def normalizar_texto(valor: object) -> str:
    """Normaliza categorías para poder comparar días y planificaciones."""

    texto = normalizar_valor(valor)
    texto = "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_pedido_desde_codigo(valor: object) -> str:
    """Obtiene el número ERP desde el campo Codigo de Pedidos DIGIP.

    Ejemplos:
        ``9999 70-1`` -> ``70``
        ``70-1``      -> ``70``
    """

    texto = normalizar_valor(valor)

    if not texto:
        return ""

    partes = texto.split()

    if len(partes) >= 2:
        texto = partes[1]

    return texto.split("-")[0].strip()


def codigo_despacho_comparable(valor: object) -> str:
    """Compara códigos de despacho tolerando ceros iniciales distintos."""

    codigo = normalizar_valor(valor)
    return codigo.lstrip("0") or ("0" if codigo else "")


def obtener_configuracion_zona(codigo_despacho: object) -> dict[str, str]:
    """Busca una zona tolerando diferencias de formato en el código."""

    codigo = normalizar_valor(codigo_despacho)

    if not codigo:
        return {}

    configuracion = ZONAS_PLANIFICACION.get(codigo)

    if configuracion is not None:
        return configuracion

    comparable = codigo_despacho_comparable(codigo)

    for codigo_configurado, datos in ZONAS_PLANIFICACION.items():
        if codigo_despacho_comparable(codigo_configurado) == comparable:
            return datos

    return {}



def preparar_pendientes_erp(df_pendientes: pd.DataFrame) -> pd.DataFrame:
    """Normaliza el reporte ERP crudo sin depender de su tabla reducida."""

    tabla = df_pendientes.copy()

    if {"nro_com", "cod_cli", "cod_dist", "nombre"}.issubset(tabla.columns):
        tabla = tabla.rename(
            columns={
                "nro_com": "Pedido",
                "cod_cli": "ClienteCodigoERP",
                "cod_dist": "DistribuidorCodigoERP",
                "nombre": "ClienteDescripcionERP",
                "nom_dist": "DistribuidorERP",
                "cod_flete": "CodigoFleteERP",
                "des_flete": "FleteERP",
            }
        )

        tabla["Pedido"] = normalizar_codigo(tabla["Pedido"]).str.split("-").str[0]
        tabla["ClienteCodigoERP"] = normalizar_codigo(tabla["ClienteCodigoERP"])
        tabla["DistribuidorCodigoERP"] = normalizar_codigo(
            tabla["DistribuidorCodigoERP"]
        )
        tabla["CodigoSucursal"] = (
            tabla["ClienteCodigoERP"]
            + "-"
            + tabla["DistribuidorCodigoERP"]
        )
    else:
        requeridas = {
            "Pedido",
            "CodigoSucursal",
            "ClienteCodigoERP",
            "ClienteDescripcionERP",
        }
        faltantes = requeridas.difference(tabla.columns)
        if faltantes:
            raise ValueError(
                "Faltan columnas en Pedidos Pendientes ERP: "
                f"{sorted(faltantes)}"
            )
        tabla["Pedido"] = normalizar_codigo(tabla["Pedido"])
        tabla["CodigoSucursal"] = normalizar_codigo(tabla["CodigoSucursal"])
        tabla["ClienteCodigoERP"] = normalizar_codigo(tabla["ClienteCodigoERP"])

    for columna in [
        "ClienteDescripcionERP",
        "DistribuidorERP",
        "CodigoFleteERP",
        "FleteERP",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""
        tabla[columna] = tabla[columna].fillna("").astype(str).str.strip()

    return tabla


def preparar_pedidos_digip(df_pedidos_digip: pd.DataFrame) -> pd.DataFrame:
    """Reduce el crudo DIGIP a una fila útil por pedido.

    Usa el normalizador central de models.pedidos para soportar tanto
    el formato histórico como el formato nuevo del reporte DIGIP.
    """

    if df_pedidos_digip is None or df_pedidos_digip.empty:
        return pd.DataFrame(
            columns=[
                "Pedido",
                "CodigoDespacho",
                "DespachoDescripcion",
                "Domicilio",
                "Localidad",
                "Provincia",
                "ClienteCodigo",
                "ClienteDescripcion",
            ]
        )

    crudo = df_pedidos_digip.copy()

    # Campos geográficos que Maestro Clientes necesita y que no forman
    # parte obligatoria del contrato central de Pedidos.
    aliases_maestro = {
        "Dirección": "Domicilio",
        "Direccion": "Domicilio",
        "Provincia": "Provincia",
    }

    for origen, destino in aliases_maestro.items():
        if origen in crudo.columns and destino not in crudo.columns:
            crudo = crudo.rename(columns={origen: destino})

    # En el reporte nuevo, "Despacho Id.1" contiene la localidad visible
    # (ej.: CABA, CASEROS), no un identificador numérico.
    if "Localidad" not in crudo.columns and "Despacho Id.1" in crudo.columns:
        crudo["Localidad"] = crudo["Despacho Id.1"]

    tabla = normalizar_pedidos_digip(crudo)

    # El normalizador central resuelve, entre otros:
    # Código pedido -> Codigo -> Pedido
    # Código cliente -> ClienteCodigo
    # Código despacho -> CodigoDespacho
    # Despacho -> DespachoDescripcion
    for columna in [
        "CodigoDespacho",
        "DespachoDescripcion",
        "Domicilio",
        "Localidad",
        "Provincia",
        "ClienteCodigo",
        "ClienteDescripcion",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.replace(r"\.0$", "", regex=True)
        )

    tabla["Pedido"] = normalizar_codigo(tabla["Pedido"])
    tabla["CodigoDespacho"] = normalizar_codigo(tabla["CodigoDespacho"])

    # Se prioriza una fila que sí tenga código de despacho.
    tabla["_tiene_despacho"] = tabla["CodigoDespacho"].ne("")
    tabla = (
        tabla.sort_values(
            ["Pedido", "_tiene_despacho"],
            ascending=[True, False],
        )
        .drop_duplicates(subset=["Pedido"], keep="first")
        .drop(columns="_tiene_despacho")
        .reset_index(drop=True)
    )

    return tabla[
        [
            "Pedido",
            "CodigoDespacho",
            "DespachoDescripcion",
            "Domicilio",
            "Localidad",
            "Provincia",
            "ClienteCodigo",
            "ClienteDescripcion",
        ]
    ].copy()

def construir_referencia_historica(
    tabla_clientes: pd.DataFrame,
    tabla_pendientes: pd.DataFrame,
    pedidos_digip: pd.DataFrame,
) -> pd.DataFrame:
    """Relaciona despachos actuales con clientes ya planificados.

    La referencia sale exclusivamente de registros existentes en el maestro.
    Esto permite saber qué combinación Entrega/Preparación se usó con cada
    código de despacho.
    """

    columnas_cliente = {
        "CodigoSucursal",
        "FrecuenciaEntrega",
        "FrecuenciaPreparacion",
    }

    if not columnas_cliente.issubset(tabla_clientes.columns):
        return pd.DataFrame()

    columnas_pendiente = {"Pedido", "CodigoSucursal"}

    if not columnas_pendiente.issubset(tabla_pendientes.columns):
        return pd.DataFrame()

    clientes = tabla_clientes.copy()
    pendientes = tabla_pendientes.copy()

    clientes["CodigoSucursal"] = normalizar_codigo(clientes["CodigoSucursal"])
    pendientes["CodigoSucursal"] = normalizar_codigo(pendientes["CodigoSucursal"])
    pendientes["Pedido"] = normalizar_codigo(pendientes["Pedido"])

    referencia = pendientes[["Pedido", "CodigoSucursal"]].merge(
        pedidos_digip[["Pedido", "CodigoDespacho"]],
        on="Pedido",
        how="inner",
    )

    referencia = referencia.merge(
        clientes[
            [
                "CodigoSucursal",
                "FrecuenciaEntrega",
                "FrecuenciaPreparacion",
            ]
        ],
        on="CodigoSucursal",
        how="inner",
    )

    referencia["Entrega"] = referencia["FrecuenciaEntrega"].apply(normalizar_texto)
    referencia["Preparacion"] = referencia["FrecuenciaPreparacion"].apply(
        normalizar_texto
    )
    referencia["CodigoDespachoComparable"] = referencia["CodigoDespacho"].apply(
        codigo_despacho_comparable
    )

    referencia = referencia[
        referencia["CodigoDespachoComparable"].ne("")
        & referencia["Entrega"].ne("")
        & referencia["Preparacion"].ne("")
    ].copy()

    if referencia.empty:
        return pd.DataFrame()

    conteo = (
        referencia.groupby(
            ["CodigoDespachoComparable", "Entrega", "Preparacion"],
            dropna=False,
        )
        .size()
        .reset_index(name="CantidadReferencias")
    )

    totales = (
        conteo.groupby("CodigoDespachoComparable")["CantidadReferencias"]
        .sum()
        .rename("TotalReferencias")
        .reset_index()
    )

    conteo = conteo.merge(totales, on="CodigoDespachoComparable", how="left")
    conteo["Confianza"] = (
        conteo["CantidadReferencias"] / conteo["TotalReferencias"] * 100
    ).round(1)

    conteo = conteo.sort_values(
        ["CodigoDespachoComparable", "CantidadReferencias", "Entrega"],
        ascending=[True, False, True],
    )

    conteo["Posicion"] = conteo.groupby("CodigoDespachoComparable").cumcount() + 1
    conteo["CantidadCombinaciones"] = conteo.groupby(
        "CodigoDespachoComparable"
    )["Entrega"].transform("size")

    return conteo.reset_index(drop=True)


def inferir_planificacion(
    codigo_despacho: object,
    referencia_historica: pd.DataFrame,
) -> dict[str, object]:
    """Propone la planificación y explica el origen del resultado."""

    codigo = normalizar_valor(codigo_despacho)
    comparable = codigo_despacho_comparable(codigo)

    resultado: dict[str, object] = {
        "Estado": "SIN_CODIGO_DESPACHO",
        "MetodoInferencia": "SIN INFORMACION",
        "Grupo": "",
        "Zona": "",
        "Entrega": "",
        "Preparacion": "",
        "ClientesReferencia": 0,
        "CombinacionesDetectadas": 0,
        "Confianza": 0.0,
        "ObservacionValidacion": (
            "El pedido no tiene un código de despacho disponible en DIGIP."
        ),
    }

    if not codigo:
        return resultado

    configuracion = obtener_configuracion_zona(codigo)
    resultado["Grupo"] = str(configuracion.get("grupo", "")).strip()
    resultado["Zona"] = str(configuracion.get("descripcion", "")).strip()

    coincidencias = pd.DataFrame()

    if not referencia_historica.empty:
        coincidencias = referencia_historica.loc[
            referencia_historica["CodigoDespachoComparable"].eq(comparable)
        ].copy()

    if not coincidencias.empty:
        principal = coincidencias.iloc[0]
        cantidad_combinaciones = int(principal["CantidadCombinaciones"])
        confianza = float(principal["Confianza"])

        resultado.update(
            {
                "MetodoInferencia": "CLIENTES SIMILARES",
                "Entrega": principal["Entrega"],
                "Preparacion": principal["Preparacion"],
                "ClientesReferencia": int(principal["TotalReferencias"]),
                "CombinacionesDetectadas": cantidad_combinaciones,
                "Confianza": confianza,
            }
        )

        if cantidad_combinaciones == 1:
            resultado["Estado"] = "LISTO_HISTORICO"
            resultado["ObservacionValidacion"] = (
                "Todos los antecedentes encontrados utilizan la misma "
                "planificación."
            )
            return resultado

        if confianza >= 80.0 and int(principal["CantidadReferencias"]) >= 3:
            resultado["Estado"] = "LISTO_HISTORICO"
            resultado["ObservacionValidacion"] = (
                "Existe más de una combinación, pero la principal es "
                "claramente dominante."
            )
            return resultado

        resultado["Estado"] = "REVISAR_PLANIFICACION"
        alternativas = coincidencias.apply(
            lambda fila: (
                f"{fila['Entrega']} / {fila['Preparacion']} "
                f"({int(fila['CantidadReferencias'])})"
            ),
            axis=1,
        ).tolist()
        resultado["ObservacionValidacion"] = (
            "El código de despacho tiene antecedentes diferentes: "
            + " | ".join(alternativas)
        )
        return resultado

    if configuracion:
        entrega = normalizar_texto(configuracion.get("planificacion", ""))
        preparacion = PREPARACION_POR_ENTREGA.get(entrega, "")

        resultado.update(
            {
                "MetodoInferencia": "CONFIGURACION DE ZONA",
                "Entrega": entrega,
                "Preparacion": preparacion,
                "Confianza": 70.0 if preparacion else 0.0,
            }
        )

        if entrega and preparacion:
            resultado["Estado"] = "LISTO_CONFIGURACION"
            resultado["ObservacionValidacion"] = (
                "No hay clientes similares en los pedidos actuales; se usó "
                "la configuración de zona y la equivalencia operativa."
            )
        else:
            resultado["Estado"] = "REVISAR_PLANIFICACION"
            resultado["ObservacionValidacion"] = (
                "La zona existe, pero no permite determinar una combinación "
                "completa de entrega y preparación."
            )

        return resultado

    resultado["Estado"] = "CODIGO_DESPACHO_SIN_REFERENCIA"
    resultado["MetodoInferencia"] = "SIN REFERENCIA"
    resultado["ObservacionValidacion"] = (
        "El código de despacho no tiene antecedentes ni configuración de zona."
    )
    return resultado


def validar_maestro_clientes(
    tabla_clientes: pd.DataFrame,
    tabla_pendientes: pd.DataFrame,
    df_pedidos_digip: pd.DataFrame,
) -> pd.DataFrame:
    """Devuelve una vista previa de altas pendientes, sin escribir archivos."""

    columnas_clientes = {"CodigoSucursal"}
    faltantes_clientes = columnas_clientes.difference(tabla_clientes.columns)

    if faltantes_clientes:
        raise ValueError(
            "Faltan columnas en la tabla de clientes: "
            f"{sorted(faltantes_clientes)}"
        )

    clientes = tabla_clientes.copy()
    pendientes = preparar_pendientes_erp(tabla_pendientes)
    pedidos_digip = preparar_pedidos_digip(df_pedidos_digip)

    clientes["CodigoSucursal"] = normalizar_codigo(clientes["CodigoSucursal"])
    pendientes["CodigoSucursal"] = normalizar_codigo(pendientes["CodigoSucursal"])
    pendientes["Pedido"] = normalizar_codigo(pendientes["Pedido"])

    nuevos = pendientes.loc[
        pendientes["CodigoSucursal"].ne("")
        & ~pendientes["CodigoSucursal"].isin(clientes["CodigoSucursal"])
    ].copy()

    if nuevos.empty:
        return pd.DataFrame()

    nuevos = nuevos.merge(pedidos_digip, on="Pedido", how="left", suffixes=("", "_DIGIP"))

    # Conserva un registro por código logístico y prioriza pedidos con despacho.
    nuevos["CodigoDespacho"] = normalizar_codigo(nuevos["CodigoDespacho"])
    nuevos["_tiene_despacho"] = nuevos["CodigoDespacho"].ne("")
    nuevos = (
        nuevos.sort_values(
            ["CodigoSucursal", "_tiene_despacho", "Pedido"],
            ascending=[True, False, True],
        )
        .drop_duplicates(subset=["CodigoSucursal"], keep="first")
        .drop(columns="_tiene_despacho")
        .reset_index(drop=True)
    )

    referencia = construir_referencia_historica(
        tabla_clientes=clientes,
        tabla_pendientes=pendientes,
        pedidos_digip=pedidos_digip,
    )

    salida: list[dict[str, object]] = []

    for _, fila in nuevos.iterrows():
        plan = inferir_planificacion(fila.get("CodigoDespacho", ""), referencia)

        codigo_cliente = normalizar_valor(fila.get("ClienteCodigoERP", ""))
        descripcion = texto_limpio(fila.get("ClienteDescripcionERP", ""))
        codigo_sucursal = normalizar_valor(fila.get("CodigoSucursal", ""))

        estado = str(plan["Estado"])
        observacion = str(plan["ObservacionValidacion"])

        if not codigo_cliente or not descripcion or not codigo_sucursal:
            estado = "DATOS_INCOMPLETOS"
            observacion = (
                "Falta código de cliente, descripción o código logístico. "
                + observacion
            )

        salida.append(
            {
                "Estado": estado,
                "ListoParaAlta": estado in ESTADOS_LISTOS,
                "CodigoLogistico": codigo_sucursal,
                "CodigoCliente": codigo_cliente,
                "Cliente": descripcion,
                "Distribuidor": texto_limpio(fila.get("DistribuidorERP", "")),
                "PedidoReferencia": normalizar_valor(fila.get("Pedido", "")),
                "CodigoDespacho": normalizar_valor(fila.get("CodigoDespacho", "")),
                "DespachoDescripcion": texto_limpio(
                    fila.get("DespachoDescripcion", "")
                ),
                "Zona": plan["Zona"],
                "Grupo": plan["Grupo"],
                "EntregaPropuesta": plan["Entrega"],
                "PreparacionPropuesta": plan["Preparacion"],
                "MetodoInferencia": plan["MetodoInferencia"],
                "ClientesReferencia": plan["ClientesReferencia"],
                "CombinacionesDetectadas": plan["CombinacionesDetectadas"],
                "ConfianzaPorcentaje": plan["Confianza"],
                "DomicilioDIGIP": texto_limpio(fila.get("Domicilio", "")),
                "LocalidadDIGIP": texto_limpio(fila.get("Localidad", "")),
                "ProvinciaDIGIP": texto_limpio(fila.get("Provincia", "")),
                "CodigoFleteERP": normalizar_valor(fila.get("CodigoFleteERP", "")),
                "FleteERP": texto_limpio(fila.get("FleteERP", "")),
                "ObservacionValidacion": observacion,
            }
        )

    resultado = pd.DataFrame(salida)

    orden_estado = {
        "REVISAR_PLANIFICACION": 1,
        "SIN_CODIGO_DESPACHO": 2,
        "CODIGO_DESPACHO_SIN_REFERENCIA": 3,
        "DATOS_INCOMPLETOS": 4,
        "LISTO_HISTORICO": 5,
        "LISTO_CONFIGURACION": 6,
    }

    resultado["_orden"] = resultado["Estado"].map(orden_estado).fillna(99)
    resultado = (
        resultado.sort_values(["_orden", "Cliente", "CodigoLogistico"])
        .drop(columns="_orden")
        .reset_index(drop=True)
    )

    return resultado

# ==========================================================
# ACTUALIZACIÓN CONTROLADA DEL ARCHIVO XLSM
# ==========================================================

from datetime import datetime
from pathlib import Path
import shutil


COLUMNAS_MAESTRO = {
    "codigo_logistico": "CodigoLogistico",
    "Codigo_Cliente": "CodigoCliente",
    "Cliente": "Cliente",
    "tipo": "TipoClientePropuesto",
    "Direccion": "DomicilioDIGIP",
    "cod_flete": "CodigoFleteERP",
    "des_flete": "FleteERP",
    "Distrito": "Distribuidor",
    "Localidad": "LocalidadDIGIP",
    "CP": "CodigoPostalDIGIP",
    "Provincia": "ProvinciaDIGIP",
    "Zona": "Zona",
    "chofer_hr": "ChoferPropuesto",
    "patente_hr": "PatentePropuesta",
    "Entrega": "EntregaPropuesta",
    "Preparacion2": "PreparacionPropuesta",
    "Observaciones": "ObservacionesAlta",
}


def localizar_archivo_maestro(
    carpeta_datos: str | Path,
    nombre_base: str = "Maestro Clientes",
) -> Path:
    """Localiza el maestro evitando respaldos y archivos temporales."""

    carpeta = Path(carpeta_datos)

    if not carpeta.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de datos configurada: {carpeta}"
        )

    extensiones = {".xlsm", ".xlsx"}
    nombre_normalizado = nombre_base.strip().lower()

    candidatos = [
        archivo
        for archivo in carpeta.iterdir()
        if archivo.is_file()
        and archivo.suffix.lower() in extensiones
        and archivo.stem.strip().lower().startswith(nombre_normalizado)
        and "respaldo" not in archivo.stem.lower()
        and not archivo.name.startswith("~$")
    ]

    if not candidatos:
        raise FileNotFoundError(
            f"No se encontró '{nombre_base}.xlsm' en {carpeta}."
        )

    # Se prioriza XLSM para conservar macros y luego el nombre exacto.
    candidatos.sort(
        key=lambda archivo: (
            archivo.suffix.lower() != ".xlsm",
            archivo.stem.strip().lower() != nombre_normalizado,
            -archivo.stat().st_mtime,
        )
    )

    return candidatos[0]


def preparar_registros_para_alta(
    registros_seleccionados: pd.DataFrame,
) -> list[dict[str, str]]:
    """Convierte la selección validada al esquema físico del maestro."""

    if registros_seleccionados is None or registros_seleccionados.empty:
        raise ValueError("No hay clientes seleccionados para actualizar.")

    requeridas = {
        "CodigoLogistico",
        "CodigoCliente",
        "Cliente",
        "EntregaPropuesta",
        "PreparacionPropuesta",
        "ListoParaAlta",
    }
    faltantes = requeridas.difference(registros_seleccionados.columns)

    if faltantes:
        raise ValueError(
            "Faltan columnas en la selección: "
            f"{sorted(faltantes)}"
        )

    no_listos = registros_seleccionados.loc[
        ~registros_seleccionados["ListoParaAlta"].fillna(False)
    ]

    if not no_listos.empty:
        codigos = ", ".join(
            no_listos["CodigoLogistico"].astype(str).tolist()
        )
        raise ValueError(
            "Solo se pueden actualizar registros listos para alta. "
            f"Revisar: {codigos}"
        )

    registros: list[dict[str, str]] = []

    for _, fila in registros_seleccionados.iterrows():
        codigo = normalizar_valor(fila.get("CodigoLogistico", ""))
        cliente_codigo = normalizar_valor(fila.get("CodigoCliente", ""))
        cliente = texto_limpio(fila.get("Cliente", ""))
        entrega = normalizar_texto(fila.get("EntregaPropuesta", ""))
        preparacion = normalizar_texto(
            fila.get("PreparacionPropuesta", "")
        )

        if not all([codigo, cliente_codigo, cliente, entrega, preparacion]):
            raise ValueError(
                f"El registro {codigo or '(sin código)'} tiene datos "
                "obligatorios incompletos."
            )

        metodo = texto_limpio(fila.get("MetodoInferencia", ""))
        pedido = normalizar_valor(fila.get("PedidoReferencia", ""))
        despacho = normalizar_valor(fila.get("CodigoDespacho", ""))

        registros.append(
            {
                "codigo_logistico": codigo,
                "Codigo_Cliente": cliente_codigo,
                "Cliente": cliente,
                # No se inventa la clasificación comercial.
                "tipo": texto_limpio(
                    fila.get("TipoClientePropuesto", "")
                ),
                "Direccion": texto_limpio(
                    fila.get("DomicilioDIGIP", "")
                ),
                "cod_flete": normalizar_valor(
                    fila.get("CodigoFleteERP", "")
                ),
                "des_flete": texto_limpio(fila.get("FleteERP", "")),
                "Distrito": texto_limpio(
                    fila.get("Distribuidor", "")
                ),
                "Localidad": texto_limpio(
                    fila.get("LocalidadDIGIP", "")
                ),
                "CP": texto_limpio(fila.get("CodigoPostalDIGIP", "")),
                "Provincia": texto_limpio(
                    fila.get("ProvinciaDIGIP", "")
                ),
                "Zona": texto_limpio(fila.get("Zona", "")),
                "chofer_hr": texto_limpio(
                    fila.get("ChoferPropuesto", "Otros")
                ) or "Otros",
                "patente_hr": texto_limpio(
                    fila.get("PatentePropuesta", "Otros")
                ) or "Otros",
                "Entrega": entrega,
                "Preparacion2": preparacion,
                "Observaciones": (
                    "Alta automática desde Pedidos Pendientes"
                    f" | Pedido {pedido}"
                    f" | Despacho {despacho}"
                    f" | {metodo}"
                ).strip(" |"),
            }
        )

    # Protección adicional contra una selección duplicada.
    unicos: dict[str, dict[str, str]] = {}
    for registro in registros:
        unicos[registro["codigo_logistico"]] = registro

    return list(unicos.values())


def crear_respaldo_maestro(ruta_maestro: Path) -> Path:
    """Genera una copia previa a cada escritura."""

    carpeta_respaldo = ruta_maestro.parent / "respaldos_maestro_clientes"
    carpeta_respaldo.mkdir(parents=True, exist_ok=True)

    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_respaldo = carpeta_respaldo / (
        f"{ruta_maestro.stem}_respaldo_{marca_tiempo}"
        f"{ruta_maestro.suffix}"
    )

    shutil.copy2(ruta_maestro, ruta_respaldo)
    return ruta_respaldo


def actualizar_maestro_clientes(
    registros_seleccionados: pd.DataFrame,
    carpeta_datos: str | Path,
    nombre_base: str = "Maestro Clientes",
) -> dict[str, object]:
    """Agrega filas al maestro mediante Excel COM.

    Se utiliza Excel de escritorio para conservar macros, tablas, fórmulas y
    formato del archivo XLSM. La función nunca reemplaza códigos existentes.
    """

    registros = preparar_registros_para_alta(registros_seleccionados)
    ruta_maestro = localizar_archivo_maestro(carpeta_datos, nombre_base)

    try:
        import comtypes
        import comtypes.client
    except ImportError as error:
        raise RuntimeError(
            "Falta la dependencia 'comtypes'. Instalá el requirements del "
            "proyecto antes de actualizar el maestro."
        ) from error

    excel = None
    libro = None
    com_inicializado = False
    ruta_respaldo = None
    agregados: list[str] = []
    omitidos: list[str] = []

    try:
        # Streamlit ejecuta las acciones en hilos de trabajo. Cada hilo que
        # utiliza automatización COM debe inicializar COM explícitamente.
        comtypes.CoInitialize()
        com_inicializado = True

        # El respaldo se crea después de inicializar COM y antes de abrir
        # Excel. De esta manera cualquier escritura queda protegida.
        ruta_respaldo = crear_respaldo_maestro(ruta_maestro)

        excel = comtypes.client.CreateObject("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False

        libro = excel.Workbooks.Open(
            str(ruta_maestro.resolve()),
            UpdateLinks=0,
            ReadOnly=False,
        )

        hoja_objetivo = None
        tabla_objetivo = None

        # El archivo real contiene la hoja ``Maestro Clientes`` y la tabla
        # estructurada ``Maestro_Clientes``. Toda la lectura y escritura se
        # realiza a través de esa tabla para no depender de cómo COM devuelve
        # los valores de las celdas del encabezado.
        try:
            hoja_objetivo = libro.Worksheets.Item("Maestro Clientes")
        except Exception:
            hoja_objetivo = None

        if hoja_objetivo is None:
            for indice_hoja in range(1, int(libro.Worksheets.Count) + 1):
                hoja = libro.Worksheets.Item(indice_hoja)
                if texto_limpio(hoja.Name).casefold() == "maestro clientes":
                    hoja_objetivo = hoja
                    break

        if hoja_objetivo is None:
            raise RuntimeError(
                "No se encontró la hoja 'Maestro Clientes' dentro del archivo."
            )

        try:
            tabla_objetivo = hoja_objetivo.ListObjects.Item("Maestro_Clientes")
        except Exception:
            tabla_objetivo = None

        if tabla_objetivo is None:
            for indice_tabla in range(
                1,
                int(hoja_objetivo.ListObjects.Count) + 1,
            ):
                tabla = hoja_objetivo.ListObjects.Item(indice_tabla)
                nombre_tabla = texto_limpio(tabla.Name).casefold()
                if nombre_tabla == "maestro_clientes":
                    tabla_objetivo = tabla
                    break

        if tabla_objetivo is None:
            raise RuntimeError(
                "No se encontró la tabla estructurada 'Maestro_Clientes'."
            )

        def normalizar_encabezado_excel(valor: object) -> str:
            texto = texto_limpio(valor)
            texto = unicodedata.normalize("NFD", texto)
            texto = "".join(
                caracter
                for caracter in texto
                if unicodedata.category(caracter) != "Mn"
            )
            return re.sub(r"[^a-z0-9]", "", texto.casefold())

        # Nombre canónico utilizado por el registro -> índice dentro de la
        # tabla. ListColumns.Name devuelve exactamente los nombres declarados
        # por Excel, aunque el rango visible tenga estilos o formatos.
        nombres_canonicos = {
            "codigologistico": "codigo_logistico",
            "codigocliente": "Codigo_Cliente",
            "cliente": "Cliente",
            "tipo": "tipo",
            "direccion": "Direccion",
            "codflete": "cod_flete",
            "desflete": "des_flete",
            "distrito": "Distrito",
            "localidad": "Localidad",
            "cp": "CP",
            "provincia": "Provincia",
            "zona": "Zona",
            "choferhr": "chofer_hr",
            "patentehr": "patente_hr",
            "entrega": "Entrega",
            "preparacion2": "Preparacion2",
            "observaciones": "Observaciones",
        }

        columnas_tabla: dict[str, int] = {}
        cantidad_columnas = int(tabla_objetivo.ListColumns.Count)

        for indice_columna in range(1, cantidad_columnas + 1):
            columna_tabla = tabla_objetivo.ListColumns.Item(indice_columna)
            nombre_visible = texto_limpio(columna_tabla.Name)
            clave = normalizar_encabezado_excel(nombre_visible)
            nombre_canonico = nombres_canonicos.get(clave)

            if nombre_canonico:
                columnas_tabla[nombre_canonico] = indice_columna

        encabezados_requeridos = {
            "codigo_logistico",
            "Codigo_Cliente",
            "Cliente",
            "Entrega",
            "Preparacion2",
        }
        faltantes = encabezados_requeridos.difference(columnas_tabla)

        if faltantes:
            columnas_detectadas = [
                texto_limpio(
                    tabla_objetivo.ListColumns.Item(indice).Name
                )
                for indice in range(1, cantidad_columnas + 1)
            ]
            raise RuntimeError(
                "La tabla 'Maestro_Clientes' no contiene los encabezados "
                f"requeridos: {sorted(faltantes)}. "
                f"Columnas detectadas: {columnas_detectadas}."
            )

        indice_codigo = columnas_tabla["codigo_logistico"]
        existentes: set[str] = set()

        cuerpo_tabla = tabla_objetivo.DataBodyRange
        if cuerpo_tabla is not None:
            cantidad_filas = int(cuerpo_tabla.Rows.Count)
            for indice_fila in range(1, cantidad_filas + 1):
                celda_codigo = cuerpo_tabla.Cells(
                    indice_fila,
                    indice_codigo,
                )
                valor_codigo = celda_codigo.Value[()]
                codigo_existente = normalizar_valor(valor_codigo)
                if codigo_existente:
                    existentes.add(codigo_existente)

        for registro in registros:
            codigo = normalizar_valor(registro["codigo_logistico"])

            if codigo in existentes:
                omitidos.append(codigo)
                continue

            nueva_fila = tabla_objetivo.ListRows.Add()
            rango_nueva_fila = nueva_fila.Range

            for encabezado, valor in registro.items():
                indice_columna = columnas_tabla.get(encabezado)
                if indice_columna is None:
                    continue

                celda_destino = rango_nueva_fila.Cells(
                    1,
                    indice_columna,
                )
                celda_destino.Value[()] = valor

            existentes.add(codigo)
            agregados.append(codigo)

        if agregados:
            libro.Save()

        libro.Close(SaveChanges=False)
        libro = None

    except Exception as error:
        if libro is not None:
            try:
                libro.Close(SaveChanges=False)
            except Exception:
                pass

        raise RuntimeError(
            "No se pudo actualizar Maestro Clientes. Verificá que el archivo "
            "no esté abierto por otro usuario. No se guardaron cambios. "
            f"Detalle: {error}"
        ) from error

    finally:
        if excel is not None:
            try:
                excel.ScreenUpdating = True
                excel.Quit()
            except Exception:
                pass

        if com_inicializado:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    return {
        "archivo": str(ruta_maestro),
        "respaldo": str(ruta_respaldo) if ruta_respaldo else "",
        "agregados": agregados,
        "omitidos": omitidos,
        "cantidad_agregados": len(agregados),
        "cantidad_omitidos": len(omitidos),
    }
