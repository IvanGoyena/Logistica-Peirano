from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd


DIAS_SEMANA = {
    "LUNES": 0,
    "MARTES": 1,
    "MIERCOLES": 2,
    "JUEVES": 3,
    "VIERNES": 4,
    "SABADO": 5,
    "DOMINGO": 6,
}

HORAS_ANTICIPACION_CICLO = 24
HORAS_SLA_EXPRESO = 96
HORAS_SLA_RETIRA = 48
# El maestro indica DIARIA/DIARIA, pero no define un desfase horario.
# Se deja parametrizado en un solo lugar para poder ajustarlo sin tocar el dashboard.
HORAS_SLA_DIARIO = 72
DIAS_ANTIGUEDAD_REFERENCIA_PROVISORIA = 10


def _sin_tildes(valor: object) -> str:
    texto = "" if pd.isna(valor) else str(valor).strip()
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def normalizar_texto(valor: object) -> str:
    return re.sub(r"\s+", " ", _sin_tildes(valor).upper()).strip()


def normalizar_codigo(valor: object) -> str:
    texto = normalizar_texto(valor)
    texto = re.sub(r"\.0$", "", texto)
    texto = re.sub(r"\s+", "", texto)
    return texto


def normalizar_nombre(valor: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalizar_texto(valor))


def _buscar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
    if df is None or df.empty:
        return None
    mapa = {normalizar_nombre(columna): columna for columna in df.columns}
    for candidato in candidatos:
        encontrada = mapa.get(normalizar_nombre(candidato))
        if encontrada is not None:
            return encontrada
    return None


def firma_maestro_clientes(carpeta_datos: str | Path) -> tuple:
    carpeta = Path(carpeta_datos)
    extensiones = {".xlsx", ".xlsm", ".xls"}
    candidatos: list[Path] = []

    if carpeta.exists():
        for ruta in carpeta.rglob("*"):
            if not ruta.is_file() or ruta.suffix.lower() not in extensiones:
                continue
            nombre = normalizar_nombre(ruta.stem)
            if nombre in {"MAESTROCLIENTES", "MAESTROCLIENTE"}:
                candidatos.append(ruta)

    if not candidatos:
        return ("MAESTRO_CLIENTES_NO_LOCALIZADO",)

    ruta = max(candidatos, key=lambda item: item.stat().st_mtime_ns)
    estado = ruta.stat()
    return (
        str(ruta.resolve()),
        int(estado.st_size),
        int(estado.st_mtime_ns),
    )


def preparar_maestro_clientes(df_clientes: pd.DataFrame | None) -> pd.DataFrame:
    columnas_salida = [
        "CodigoLogisticoMaestro",
        "CodigoClienteMaestro",
        "ClienteMaestro",
        "TipoCliente",
        "DireccionMaestro",
        "FleteMaestro",
        "DistritoMaestro",
        "LocalidadMaestro",
        "ProvinciaMaestro",
        "ZonaPlanificacion",
        "EntregaConfigurada",
        "PreparacionConfigurada",
        "ObservacionesPlanificacion",
        "ClaveCodigoLogistico",
        "ClaveCodigoCliente",
        "ClaveClienteLogistico",
        "ClaveClienteSucursal",
        "ClaveSufijoLogistico",
        "ClaveNombreCliente",
    ]
    if df_clientes is None or df_clientes.empty:
        return pd.DataFrame(columns=columnas_salida)

    base = df_clientes.copy()
    origenes = {
        "CodigoLogisticoMaestro": ["codigo_logistico", "Codigo Logistico", "Código logístico"],
        "CodigoClienteMaestro": ["Codigo_Cliente", "Codigo Cliente", "Código Cliente"],
        "ClienteMaestro": ["Cliente", "Razon Social", "Razón Social"],
        "TipoCliente": ["tipo", "Tipo"],
        "DireccionMaestro": ["Direccion", "Dirección"],
        "FleteMaestro": ["des_flete", "Flete", "Descripcion Flete"],
        "DistritoMaestro": ["Distrito"],
        "LocalidadMaestro": ["Localidad"],
        "ProvinciaMaestro": ["Provincia"],
        "ZonaPlanificacion": ["Zona"],
        "EntregaConfigurada": ["Entrega"],
        "PreparacionConfigurada": ["Preparacion2", "Preparacion", "Preparación"],
        "ObservacionesPlanificacion": ["Observaciones", "Observacion"],
    }

    salida = pd.DataFrame(index=base.index)
    for destino, candidatos in origenes.items():
        origen = _buscar_columna(base, candidatos)
        salida[destino] = base[origen] if origen else ""
        salida[destino] = salida[destino].fillna("").astype(str).str.strip()

    salida["ClaveCodigoLogistico"] = salida["CodigoLogisticoMaestro"].map(normalizar_codigo)
    salida["ClaveCodigoCliente"] = salida["CodigoClienteMaestro"].map(normalizar_codigo)
    salida["ClaveClienteLogistico"] = (
        salida["ClaveCodigoCliente"] + "|" + salida["ClaveCodigoLogistico"]
    )
    salida.loc[
        salida["ClaveCodigoCliente"].eq("") | salida["ClaveCodigoLogistico"].eq(""),
        "ClaveClienteLogistico",
    ] = ""
    # En Hoja de Ruta el punto de entrega suele venir solamente como sufijo
    # (1, 2, 23, 109). Esta clave permite resolver CE01 + 23 contra CE01-23.
    salida["ClaveSufijoLogistico"] = (
        salida["CodigoLogisticoMaestro"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.extract(r"-([A-Za-z0-9]+)$", expand=False)
        .fillna("")
        .map(normalizar_codigo)
    )
    salida["ClaveClienteSucursal"] = (
        salida["ClaveCodigoCliente"] + "|" + salida["ClaveSufijoLogistico"]
    )
    salida.loc[
        salida["ClaveCodigoCliente"].eq("") | salida["ClaveSufijoLogistico"].eq(""),
        "ClaveClienteSucursal",
    ] = ""
    salida["ClaveNombreCliente"] = salida["ClienteMaestro"].map(normalizar_nombre)

    salida = salida.loc[
        salida[["ClaveCodigoLogistico", "ClaveCodigoCliente", "ClaveNombreCliente"]]
        .ne("")
        .any(axis=1)
    ].copy()

    # El código logístico identifica la sucursal/punto de entrega y es la clave preferida.
    salida = salida.drop_duplicates(
        subset=["ClaveCodigoLogistico", "ClaveCodigoCliente", "ClaveNombreCliente"],
        keep="first",
    ).reset_index(drop=True)

    return salida[columnas_salida]


def _mapa_unico(maestro: pd.DataFrame, clave: str) -> pd.DataFrame:
    if maestro.empty or clave not in maestro.columns:
        return pd.DataFrame()
    base = maestro.loc[maestro[clave].ne("")].copy()
    conteo = base.groupby(clave)[clave].transform("size")
    return base.loc[conteo.eq(1)].drop_duplicates(clave).copy()


def _clasificar_circuito(
    preparacion: object,
    entrega: object,
    zona: object,
    cliente: object = "",
    despacho_descripcion: object = "",
) -> str:
    preparacion_n = normalizar_texto(preparacion)
    entrega_n = normalizar_texto(entrega)
    zona_n = normalizar_texto(zona)
    cliente_n = normalizar_texto(cliente)
    despacho_n = normalizar_texto(despacho_descripcion)
    combinado = " | ".join([preparacion_n, entrega_n, zona_n])

    # RETIRA se define por el agrupador de Pedidos DIGIP y no necesita HR.
    if "RETIRA" in despacho_n:
        return "RETIRA"
    # Solo los registros de CENCOSUD parametrizados como EASY son CON TURNO.
    # Las demás sucursales CENCOSUD conservan su circuito semanal o expreso.
    if "CENCOSUD" in cliente_n and (
        preparacion_n == "EASY" or entrega_n == "EASY"
    ):
        return "CON TURNO"
    if "TURNO" in combinado:
        return "CON TURNO"
    if "EXPRES" in combinado:
        return "EXPRESO"
    if preparacion_n in {"DIARIA", "DIARIO", "TODOS LOS DIAS"} or entrega_n in {
        "DIARIA", "DIARIO", "TODOS LOS DIAS"
    }:
        return "DIARIO"
    if preparacion_n in DIAS_SEMANA and entrega_n in DIAS_SEMANA:
        return "ZONA"
    return "SIN CONFIGURACION"


def _proxima_fecha_dia_semana(fecha_base: pd.Timestamp, dia_objetivo: int, incluir_mismo_dia: bool = True):
    if pd.isna(fecha_base):
        return pd.NaT
    fecha = pd.Timestamp(fecha_base).normalize()
    diferencia = (dia_objetivo - fecha.dayofweek) % 7
    if diferencia == 0 and not incluir_mismo_dia:
        diferencia = 7
    return fecha + pd.Timedelta(days=int(diferencia))


def _dia_habil_anterior(fecha: pd.Timestamp) -> pd.Timestamp:
    """Devuelve el día hábil anterior, omitiendo sábado y domingo."""
    if pd.isna(fecha):
        return pd.NaT
    resultado = pd.Timestamp(fecha).normalize() - pd.Timedelta(days=1)
    while resultado.dayofweek >= 5:
        resultado -= pd.Timedelta(days=1)
    return resultado


def _resolver_ciclo_zona(
    fecha_ingreso: pd.Timestamp,
    dia_preparacion: int,
    dia_entrega: int,
) -> dict:
    """Asigna el primer ciclo semanal cuyo corte operativo seguía abierto."""
    if pd.isna(fecha_ingreso):
        return {
            "fecha_preparacion": pd.NaT,
            "fecha_entrega": pd.NaT,
            "fecha_corte": pd.NaT,
            "cumple_corte": False,
        }

    ingreso = pd.Timestamp(fecha_ingreso)
    fecha_preparacion = _proxima_fecha_dia_semana(
        ingreso,
        dia_preparacion,
        incluir_mismo_dia=True,
    )
    fecha_corte = (
        _dia_habil_anterior(fecha_preparacion)
        + pd.Timedelta(days=1)
        - pd.Timedelta(microseconds=1)
    )

    if ingreso > fecha_corte:
        fecha_preparacion += pd.Timedelta(days=7)
        fecha_corte = (
            _dia_habil_anterior(fecha_preparacion)
            + pd.Timedelta(days=1)
            - pd.Timedelta(microseconds=1)
        )

    fecha_entrega = _proxima_fecha_dia_semana(
        fecha_preparacion + pd.Timedelta(days=1),
        dia_entrega,
        incluir_mismo_dia=True,
    )

    return {
        "fecha_preparacion": fecha_preparacion,
        "fecha_entrega": fecha_entrega,
        "fecha_corte": fecha_corte,
        "cumple_corte": bool(ingreso <= fecha_corte),
    }


def _calcular_fechas_planificadas(fila: pd.Series) -> pd.Series:
    creacion = pd.to_datetime(fila.get("FechaHoraCreacion"), errors="coerce")
    transmision = pd.to_datetime(fila.get("FechaHoraTransmision"), errors="coerce")
    inicio_preparacion = pd.to_datetime(
        fila.get("FechaHoraInicioPreparacion"),
        errors="coerce",
    )

    dias_espera_preparacion = (
        (inicio_preparacion - creacion).total_seconds() / 86400
        if pd.notna(inicio_preparacion) and pd.notna(creacion)
        else np.nan
    )
    usa_referencia_provisoria = bool(
        pd.isna(transmision)
        and pd.notna(inicio_preparacion)
        and pd.notna(creacion)
        and dias_espera_preparacion > DIAS_ANTIGUEDAD_REFERENCIA_PROVISORIA
    )

    if pd.notna(transmision):
        fecha_ingreso = transmision
        origen_ingreso = "TRANSMISION"
    elif usa_referencia_provisoria:
        fecha_ingreso = inicio_preparacion
        origen_ingreso = "INICIO PREPARACION · REGLA PROVISORIA 10D"
    elif pd.notna(creacion):
        fecha_ingreso = creacion
        origen_ingreso = "CREACION"
    else:
        fecha_ingreso = pd.NaT
        origen_ingreso = "SIN FECHA"

    circuito = str(fila.get("TipoCircuito", ""))
    prep = normalizar_texto(fila.get("PreparacionConfigurada", ""))
    entrega = normalizar_texto(fila.get("EntregaConfigurada", ""))

    corte = (
        fecha_ingreso + pd.Timedelta(hours=HORAS_ANTICIPACION_CICLO)
        if pd.notna(fecha_ingreso) else pd.NaT
    )
    fecha_prep = pd.NaT
    fecha_entrega = pd.NaT
    fecha_corte_ingreso = pd.NaT
    cumple_corte_ingreso = False
    criterio = ""

    if circuito == "ZONA" and pd.notna(fecha_ingreso):
        if usa_referencia_provisoria:
            fecha_prep = pd.Timestamp(inicio_preparacion).normalize()
            fecha_entrega = _proxima_fecha_dia_semana(
                fecha_prep + pd.Timedelta(days=1),
                DIAS_SEMANA[entrega],
                incluir_mismo_dia=True,
            )
            fecha_corte_ingreso = inicio_preparacion
            cumple_corte_ingreso = True
            criterio = (
                f"{prep} → {entrega}; referencia provisoria desde inicio "
                f"de preparación por antigüedad > "
                f"{DIAS_ANTIGUEDAD_REFERENCIA_PROVISORIA} días"
            )
        else:
            ciclo = _resolver_ciclo_zona(
                fecha_ingreso,
                DIAS_SEMANA[prep],
                DIAS_SEMANA[entrega],
            )
            fecha_prep = ciclo["fecha_preparacion"]
            fecha_entrega = ciclo["fecha_entrega"]
            fecha_corte_ingreso = ciclo["fecha_corte"]
            cumple_corte_ingreso = ciclo["cumple_corte"]
            criterio = (
                f"{prep} → {entrega}; corte al cierre del día hábil anterior "
                f"({origen_ingreso.lower()})"
            )

    elif circuito == "DIARIO" and pd.notna(fecha_ingreso):
        fecha_prep = pd.Timestamp(fecha_ingreso).normalize()
        fecha_entrega = fecha_ingreso + pd.Timedelta(hours=HORAS_SLA_DIARIO)
        fecha_corte_ingreso = corte
        cumple_corte_ingreso = True
        criterio = (
            f"DIARIO: {HORAS_SLA_DIARIO} horas corridas desde "
            f"{origen_ingreso.lower()}"
        )

    elif circuito == "EXPRESO" and pd.notna(fecha_ingreso):
        fecha_prep = pd.Timestamp(fecha_ingreso).normalize()
        fecha_entrega = fecha_ingreso + pd.Timedelta(hours=HORAS_SLA_EXPRESO)
        fecha_corte_ingreso = corte
        cumple_corte_ingreso = True
        criterio = (
            f"{HORAS_SLA_EXPRESO} horas corridas desde "
            f"{origen_ingreso.lower()}"
        )

    elif circuito == "RETIRA" and pd.notna(fecha_ingreso):
        fecha_prep = fecha_ingreso + pd.Timedelta(hours=HORAS_SLA_RETIRA)
        fecha_entrega = fecha_prep
        fecha_corte_ingreso = corte
        cumple_corte_ingreso = True
        criterio = (
            f"RETIRA: control cerrado dentro de {HORAS_SLA_RETIRA} horas "
            f"desde {origen_ingreso.lower()}"
        )

    elif circuito == "CON TURNO":
        criterio = "Excluido: fecha definida por turno"
    else:
        criterio = "Sin configuración válida"

    semana_ciclo = (
        pd.Timestamp(fecha_prep).strftime("%G-S%V")
        if pd.notna(fecha_prep) else ""
    )

    return pd.Series({
        "FechaReferenciaIngresoCiclo": fecha_ingreso,
        "OrigenFechaIngresoCiclo": origen_ingreso,
        "UsaReferenciaInicioPreparacion": usa_referencia_provisoria,
        "DiasCreacionHastaInicioPreparacion": dias_espera_preparacion,
        "UmbralAntiguedadReferenciaDias": DIAS_ANTIGUEDAD_REFERENCIA_PROVISORIA,
        "FechaCorteCiclo": corte,
        "FechaCorteIngresoCiclo": fecha_corte_ingreso,
        "CumpleCorteIngresoCiclo": cumple_corte_ingreso,
        "SemanaCiclo": semana_ciclo,
        "FechaObjetivoPreparacion": fecha_prep,
        "FechaObjetivoEntrega": fecha_entrega,
        "CriterioPlanificacion": criterio,
    })


def enriquecer_ciclo_con_planificacion(
    ciclo: pd.DataFrame | None,
    df_clientes: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    if ciclo is None or ciclo.empty:
        return pd.DataFrame() if ciclo is None else ciclo.copy(), {
            "pedidos": 0,
            "con_maestro_cliente": 0,
            "con_planificacion": 0,
            "sin_planificacion": 0,
            "aplica_otif_base": 0,
        }

    salida = ciclo.copy()
    maestro = preparar_maestro_clientes(df_clientes)

    # La función puede ejecutarse más de una vez sobre la misma base (por
    # ejemplo, después de heredar una HR a cuenta 0008). Antes de recalcular,
    # se eliminan las columnas generadas por una ejecución anterior. Esto la
    # vuelve idempotente y evita etiquetas duplicadas al concatenar fechas.
    columnas_generadas = [
        "CodigoLogisticoMaestro", "CodigoClienteMaestro", "ClienteMaestro",
        "TipoCliente", "DireccionMaestro", "FleteMaestro", "DistritoMaestro",
        "LocalidadMaestro", "ProvinciaMaestro", "ZonaPlanificacion",
        "EntregaConfigurada", "PreparacionConfigurada",
        "ObservacionesPlanificacion", "OrigenCruceCliente",
        "TieneMaestroCliente", "TipoCircuito", "GrupoEntrega", "TipoCumplimiento",
        "FechaReferenciaIngresoCiclo", "OrigenFechaIngresoCiclo",
        "UsaReferenciaInicioPreparacion",
        "DiasCreacionHastaInicioPreparacion",
        "UmbralAntiguedadReferenciaDias",
        "FechaCorteCiclo", "FechaCorteIngresoCiclo",
        "CumpleCorteIngresoCiclo", "SemanaCiclo",
        "FechaObjetivoPreparacion", "FechaObjetivoEntrega", "CriterioPlanificacion",
        "HorasAnticipacionCreacion", "CumpleAnticipacion24h",
        "PlanificacionValida", "ExcluidoOTIF", "MotivoExclusionOTIF",
        "AplicaOTIFBase", "EstadoPlanificacion",
    ]
    salida = salida.drop(columns=columnas_generadas, errors="ignore")

    salida["_ClaveCodigoEntrega"] = salida.get(
        "CodigoEntrega", pd.Series("", index=salida.index)
    ).map(normalizar_codigo)
    salida["_ClaveCodigoLogisticoPedido"] = salida.get(
        "CodigoLogisticoPedido", pd.Series("", index=salida.index)
    ).map(normalizar_codigo)
    salida["_ClaveCodigoDespacho"] = salida.get(
        "CodigoDespacho", pd.Series("", index=salida.index)
    ).map(normalizar_codigo)
    salida["_ClaveClienteCodigoHR"] = salida.get(
        "ClienteCodigoHR", pd.Series("", index=salida.index)
    ).map(normalizar_codigo)
    salida["_ClaveClienteCodigo"] = salida.get(
        "ClienteCodigo", pd.Series("", index=salida.index)
    ).map(normalizar_codigo)
    salida["_ClaveClienteNombre"] = salida.get(
        "ClienteFinal", pd.Series("", index=salida.index)
    ).map(normalizar_nombre)

    # La HR es la fuente más confiable para identificar el cliente y el punto
    # exacto de entrega. Se arma una clave compuesta antes de usar alternativas.
    salida["_ClaveClientePreferida"] = salida["_ClaveClienteCodigoHR"].where(
        salida["_ClaveClienteCodigoHR"].ne(""),
        salida["_ClaveClienteCodigo"],
    )
    salida["_ClaveEntregaPreferida"] = salida["_ClaveCodigoEntrega"].where(
        salida["_ClaveCodigoEntrega"].ne(""),
        salida["_ClaveCodigoDespacho"],
    )
    salida["_ClaveClienteLogistico"] = (
        salida["_ClaveClientePreferida"] + "|" + salida["_ClaveEntregaPreferida"]
    )
    salida.loc[
        salida["_ClaveClientePreferida"].eq("") | salida["_ClaveEntregaPreferida"].eq(""),
        "_ClaveClienteLogistico",
    ] = ""
    salida["_ClaveClienteSucursal"] = (
        salida["_ClaveClientePreferida"] + "|" + salida["_ClaveCodigoEntrega"]
    )
    salida.loc[
        salida["_ClaveClientePreferida"].eq("") | salida["_ClaveCodigoEntrega"].eq(""),
        "_ClaveClienteSucursal",
    ] = ""

    columnas_maestro = [
        "CodigoLogisticoMaestro", "CodigoClienteMaestro", "ClienteMaestro",
        "TipoCliente", "DireccionMaestro", "FleteMaestro", "DistritoMaestro",
        "LocalidadMaestro", "ProvinciaMaestro", "ZonaPlanificacion",
        "EntregaConfigurada", "PreparacionConfigurada",
        "ObservacionesPlanificacion",
    ]
    for columna in columnas_maestro:
        salida[columna] = ""
    salida["OrigenCruceCliente"] = "SIN CRUCE"

    estrategias = [
        # 1) Código logístico explícito informado por Pedidos DIGIP.
        ("_ClaveCodigoLogisticoPedido", "ClaveCodigoLogistico", "CÓDIGO LOGÍSTICO PEDIDO"),
        # 2) Cliente + sufijo de punto de entrega (ej.: CE01 + 23 -> CE01-23).
        ("_ClaveClienteSucursal", "ClaveClienteSucursal", "CLIENTE + SUCURSAL HR"),
        # 3) Cruce exacto recomendado cuando el reporte trae el código completo.
        ("_ClaveClienteLogistico", "ClaveClienteLogistico", "CLIENTE HR + CÓDIGO ENTREGA"),
        # 4) El código logístico del maestro es único y puede resolver por sí solo.
        ("_ClaveCodigoEntrega", "ClaveCodigoLogistico", "CÓDIGO ENTREGA HR"),
        # 3) Algunos reportes llevan el código logístico en el campo despacho.
        ("_ClaveCodigoDespacho", "ClaveCodigoLogistico", "CÓDIGO DESPACHO/ENTREGA"),
        # 4) Código de cliente solo cuando identifica una única fila del maestro.
        ("_ClaveClienteCodigoHR", "ClaveCodigoCliente", "CÓDIGO CLIENTE HR"),
        ("_ClaveClienteCodigo", "ClaveCodigoCliente", "CÓDIGO CLIENTE PEDIDO"),
        # 5) Último respaldo: nombre único.
        ("_ClaveClienteNombre", "ClaveNombreCliente", "NOMBRE CLIENTE"),
    ]

    pendientes = salida.index
    for clave_salida, clave_maestro, origen in estrategias:
        mapa = _mapa_unico(maestro, clave_maestro)
        if mapa.empty or len(pendientes) == 0:
            continue
        candidatos = salida.loc[pendientes, [clave_salida]].merge(
            mapa[[clave_maestro, *columnas_maestro]],
            left_on=clave_salida,
            right_on=clave_maestro,
            how="left",
        )
        candidatos.index = pendientes
        encontrados = candidatos["ClienteMaestro"].fillna("").astype(str).str.strip().ne("")
        indices = candidatos.index[encontrados]
        if len(indices):
            for columna in columnas_maestro:
                salida.loc[indices, columna] = candidatos.loc[indices, columna].fillna("").values
            salida.loc[indices, "OrigenCruceCliente"] = origen
        pendientes = salida.index[salida["OrigenCruceCliente"].eq("SIN CRUCE")]

    salida["TieneMaestroCliente"] = salida["OrigenCruceCliente"].ne("SIN CRUCE")
    salida["TipoCircuito"] = [
        _clasificar_circuito(prep, entrega, zona, cliente, despacho)
        for prep, entrega, zona, cliente, despacho in zip(
            salida["PreparacionConfigurada"],
            salida["EntregaConfigurada"],
            salida["ZonaPlanificacion"],
            salida.get("ClienteMaestro", salida.get("ClienteFinal", "")),
            salida.get("DespachoDescripcion", pd.Series("", index=salida.index)),
        )
    ]
    salida["GrupoEntrega"] = np.where(
        salida["TipoCircuito"].eq("ZONA"),
        "ZONA · " + salida["EntregaConfigurada"].map(normalizar_texto),
        salida["TipoCircuito"],
    )
    salida["TipoCumplimiento"] = np.select(
        [
            salida["TipoCircuito"].eq("RETIRA"),
            salida["TipoCircuito"].eq("EXPRESO"),
            salida["TipoCircuito"].eq("DIARIO"),
            salida["TipoCircuito"].eq("CON TURNO"),
        ],
        ["PREPARACION RETIRA", "DESPACHO EXPRESO", "DESPACHO DIARIO", "CON TURNO"],
        default="DESPACHO ZONA",
    )
    mascara_retira_etapa = salida["TipoCircuito"].eq("RETIRA")
    if "UltimaEtapaRegistrada" not in salida.columns:
        salida["UltimaEtapaRegistrada"] = ""
    fin_prep_retira = pd.to_datetime(
        salida.get("FechaHoraFinPreparacion", pd.Series(pd.NaT, index=salida.index)),
        errors="coerce",
    )
    salida.loc[
        mascara_retira_etapa & fin_prep_retira.notna(),
        "UltimaEtapaRegistrada",
    ] = "RETIRA FINALIZADO"
    salida.loc[
        mascara_retira_etapa & fin_prep_retira.isna(),
        "UltimaEtapaRegistrada",
    ] = "RETIRA CERRADO SIN PREPARACION"

    fechas = salida.apply(_calcular_fechas_planificadas, axis=1)
    # Asignación explícita para garantizar nombres únicos, aun cuando el
    # modelo se vuelva a ejecutar sobre una base previamente enriquecida.
    for columna in fechas.columns:
        salida[columna] = fechas[columna].values

    inicio_prep = pd.to_datetime(salida.get("FechaHoraInicioPreparacion"), errors="coerce")
    creacion = pd.to_datetime(salida.get("FechaHoraCreacion"), errors="coerce")
    salida["HorasAnticipacionCreacion"] = (
        inicio_prep - creacion
    ).dt.total_seconds().div(3600)
    salida["CumpleAnticipacion24h"] = (
        salida["HorasAnticipacionCreacion"]
        .ge(HORAS_ANTICIPACION_CICLO)
        .astype("boolean")
    )
    salida.loc[
        inicio_prep.isna() | creacion.isna(),
        "CumpleAnticipacion24h",
    ] = pd.NA

    salida["PlanificacionValida"] = salida["TipoCircuito"].isin(
        ["ZONA", "DIARIO", "EXPRESO", "CON TURNO", "RETIRA"]
    )
    salida["ExcluidoOTIF"] = salida["TipoCircuito"].isin(
        ["CON TURNO", "SIN CONFIGURACION"]
    )
    salida["MotivoExclusionOTIF"] = np.select(
        [
            salida["TipoCircuito"].eq("CON TURNO"),
            salida["TipoCircuito"].eq("SIN CONFIGURACION"),
            salida["TieneMaestroCliente"].eq(False),
        ],
        [
            "Entrega con turno específico",
            "Planificación no configurada",
            "Cliente no encontrado en maestro",
        ],
        default="",
    )
    salida["AplicaOTIFBase"] = (
        salida["PlanificacionValida"]
        & ~salida["ExcluidoOTIF"]
        & salida["FechaReferenciaIngresoCiclo"].notna()
        & salida["FechaObjetivoEntrega"].notna()
    )
    salida["CumpleSlaRetira"] = pd.Series(pd.NA, index=salida.index, dtype="boolean")
    mascara_retira = salida["TipoCircuito"].eq("RETIRA")
    fin_control_retira = pd.to_datetime(
        salida.get("FechaHoraFinControl", pd.Series(pd.NaT, index=salida.index)),
        errors="coerce",
    )
    objetivo_retira = pd.to_datetime(salida["FechaObjetivoPreparacion"], errors="coerce")
    salida.loc[mascara_retira, "CumpleSlaRetira"] = (
        fin_control_retira.loc[mascara_retira].notna()
        & objetivo_retira.loc[mascara_retira].notna()
        & fin_control_retira.loc[mascara_retira].le(objetivo_retira.loc[mascara_retira])
    ).astype("boolean")
    salida["EstadoPlanificacion"] = np.select(
        [
            salida["TipoCircuito"].eq("RETIRA"),
            salida["TipoCircuito"].eq("CON TURNO"),
            ~salida["TieneMaestroCliente"],
            salida["TipoCircuito"].eq("SIN CONFIGURACION"),
            salida["AplicaOTIFBase"],
        ],
        [
            "CONFIGURADO RETIRA",
            "EXCLUIDO POR TURNO",
            "SIN MAESTRO",
            "SIN CONFIGURACIÓN",
            "CONFIGURADO",
        ],
        default="INCOMPLETO",
    )

    salida = salida.drop(
        columns=[
            "_ClaveCodigoEntrega", "_ClaveCodigoLogisticoPedido", "_ClaveCodigoDespacho",
            "_ClaveClienteCodigoHR", "_ClaveClienteCodigo",
            "_ClaveClienteNombre", "_ClaveClientePreferida",
            "_ClaveEntregaPreferida", "_ClaveClienteLogistico", "_ClaveClienteSucursal",
        ],
        errors="ignore",
    )

    diagnostico = {
        "pedidos": int(len(salida)),
        "clientes_maestro": int(len(maestro)),
        "con_maestro_cliente": int(salida["TieneMaestroCliente"].sum()),
        "con_planificacion": int(salida["PlanificacionValida"].sum()),
        "sin_planificacion": int((~salida["PlanificacionValida"]).sum()),
        "excluidos_turno": int(salida["TipoCircuito"].eq("CON TURNO").sum()),
        "aplica_otif_base": int(salida["AplicaOTIFBase"].sum()),
        "circuito_zona": int(salida["TipoCircuito"].eq("ZONA").sum()),
        "circuito_diario": int(salida["TipoCircuito"].eq("DIARIO").sum()),
        "circuito_expreso": int(salida["TipoCircuito"].eq("EXPRESO").sum()),
        "circuito_retira": int(salida["TipoCircuito"].eq("RETIRA").sum()),
        "cencosud_easy_turno": int((
            salida["TipoCircuito"].eq("CON TURNO")
            & salida["ClienteMaestro"].map(normalizar_texto).str.contains("CENCOSUD", na=False)
        ).sum()),
    }
    return salida, diagnostico
