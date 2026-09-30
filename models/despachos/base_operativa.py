from __future__ import annotations

import pandas as pd

from config_planificacion import (
    ZONAS_PLANIFICACION,
    PLANIFICACION_FALLBACK_EXPRESOS,
    obtener_planificacion_expreso,
)


COLUMNAS_FINALES_DESPACHOS = [
    "Pedido",
    "Fecha",
    "FechaTransmisionERP",
    "HoraTransmisionERP",
    "ClienteCodigo",
    "ClienteDescripcion",
    "Estado",
    "PreparacionEstado",
    "PreparacionID",
    "CodigoDespacho",
    "DespachoDescripcion",
    "CodigoExpreso",
    "FrecuenciaEntrega",
    "DiaEntrega",
    "LocalidadExpreso",
    "ZonaAgrupadorExpreso",
    "ZonaExpreso",
    "Planificacion",
    "UnidadesPedido",
    "TotalUnidades",
    "TotalM3",
    "TotalSKUs",
    "DetalleFamilias",
    "ImporteERP",
]


def _normalizar_pedido(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def construir_tabla_operativa_despachos(
    tabla_pedidos: pd.DataFrame,
    tabla_transmisiones: pd.DataFrame,
    tabla_pendientes_erp: pd.DataFrame,
    tabla_clientes: pd.DataFrame,
    tabla_expresos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Consolida la tabla operativa final utilizada por Dashboard y Planificador.

    Esta función no lee archivos ni toca Streamlit. Solo transforma DataFrames.
    """

    tabla = tabla_pedidos.copy()
    transmisiones = tabla_transmisiones.copy()
    pendientes_erp = tabla_pendientes_erp.copy()
    clientes = tabla_clientes.copy()
    expresos = tabla_expresos.copy()

    # =====================================================
    # EXCLUSIONES OPERATIVAS
    # =====================================================
    # Los códigos DEP_ corresponden a movimientos internos.
    # No son pedidos de reparto y no deben consumir planificación,
    # volumen, unidades ni capacidad de vehículos.
    if "ClienteCodigo" in tabla.columns:
        mascara_movimiento_interno = (
            tabla["ClienteCodigo"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .str.startswith("DEP_")
        )
        tabla = tabla.loc[~mascara_movimiento_interno].copy()

    # =====================================================
    # CLAVES DE PEDIDO
    # =====================================================

    tabla["Pedido"] = _normalizar_pedido(tabla["Pedido"])
    pendientes_erp["Pedido"] = _normalizar_pedido(
        pendientes_erp["Pedido"]
    )

    transmisiones["Pedido"] = (
        _normalizar_pedido(transmisiones["Pedido"])
        .str.split("-")
        .str[0]
    )

    # =====================================================
    # ÚLTIMA TRANSMISIÓN ERP
    # =====================================================

    tabla = tabla.merge(
        transmisiones,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    for columna in [
        "NroEnvioERP",
        "EstadoTransmisionERP",
        "HoraTransmisionERP",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabla["FechaTransmisionERP"] = pd.to_datetime(
        tabla["FechaTransmisionERP"],
        errors="coerce",
    )

    # =====================================================
    # PENDIENTES ERP
    # =====================================================

    columnas_pendientes = [
        "Pedido",
        "CodigoSucursal",
        "CodigoExpreso",
        "UnidadesPendientesERP",
        "VolumenPendienteERP",
        "ImporteERP",
    ]

    faltantes_pendientes = [
        columna
        for columna in columnas_pendientes
        if columna not in pendientes_erp.columns
    ]

    if faltantes_pendientes:
        raise ValueError(
            "Pedidos Pendientes no contiene las columnas requeridas: "
            f"{faltantes_pendientes}"
        )

    pendientes_planificacion = (
        pendientes_erp[columnas_pendientes]
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        pendientes_planificacion,
        on="Pedido",
        how="left",
        validate="many_to_one",
    )

    # La planificación trabaja sobre la cantidad que continúa pendiente.
    unidades_totales_originales = (
        pd.to_numeric(
            tabla["TotalUnidades"],
            errors="coerce",
        )
        .fillna(0)
    )

    # Unidades originales del pedido según la construcción base
    # utilizada también por el módulo Pedidos.
    # Se preservan para visualización y control cruzado.
    tabla["UnidadesPedido"] = (
        unidades_totales_originales
        .round(0)
        .astype(int)
    )

    volumen_total_original = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
    )

    tabla["UnidadesPendientesERP"] = (
        pd.to_numeric(
            tabla["UnidadesPendientesERP"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    proporcion_pendiente = (
        tabla["UnidadesPendientesERP"]
        .div(
            unidades_totales_originales.replace(
                0,
                pd.NA,
            )
        )
        .fillna(0)
        .clip(lower=0, upper=1)
    )

    tabla["TotalUnidades"] = (
        tabla["UnidadesPendientesERP"]
    )

    tabla["TotalM3"] = (
        volumen_total_original
        * proporcion_pendiente
    ).round(3)

    # =====================================================
    # CLAVES DE PLANIFICACIÓN
    # =====================================================

    for columna in [
        "CodigoSucursal",
        "CodigoExpreso",
    ]:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

    clientes["CodigoSucursal"] = (
        clientes["CodigoSucursal"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    expresos["CodigoExpreso"] = (
        expresos["CodigoExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # =====================================================
    # MAESTRO CLIENTES
    # =====================================================

    clientes_planificacion = (
        clientes[
            [
                "CodigoSucursal",
                "FrecuenciaPreparacion",
                "FrecuenciaEntrega",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoSucursal"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        clientes_planificacion,
        on="CodigoSucursal",
        how="left",
        validate="many_to_one",
    )

    # =====================================================
    # MAESTRO EXPRESOS
    # =====================================================

    expresos_planificacion = (
        expresos[
            [
                "CodigoExpreso",
                "LocalidadExpreso",
                "ZonaAgrupadorExpreso",
            ]
        ]
        .drop_duplicates(
            subset=["CodigoExpreso"],
            keep="first",
        )
        .copy()
    )

    tabla = tabla.merge(
        expresos_planificacion,
        on="CodigoExpreso",
        how="left",
        validate="many_to_one",
    )

    columnas_planificacion = [
        "FrecuenciaPreparacion",
        "FrecuenciaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
    ]

    for columna in columnas_planificacion:
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # =====================================================
    # PLANIFICACIÓN FINAL
    # =====================================================

    zona_expreso = (
        tabla["ZonaAgrupadorExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Normaliza variantes antes de resolver la planificación.
    # Ej.: GBA OESTE II -> GBA OESTE.
    zona_expreso = zona_expreso.map(
        lambda valor: obtener_planificacion_expreso(valor).get(
            "ZonaExpresoNormalizada",
            valor,
        )
    )

    localidad_expreso = (
        tabla["LocalidadExpreso"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frecuencia_entrega = (
        tabla["FrecuenciaEntrega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    es_retira = zona_expreso.eq("RETIRA")

    tabla["DiaEntrega"] = frecuencia_entrega.where(
        ~es_retira,
        "RETIRA",
    )

    tabla["ZonaExpreso"] = zona_expreso

    dias_entrega_semanal = {
        "LUNES", "MARTES", "MIERCOLES", "MIÉRCOLES", "JUEVES", "VIERNES",
    }

    es_entrega_semanal = frecuencia_entrega.isin(dias_entrega_semanal)

    # Índice de localidades/zonas normales. Se construye desde la misma
    # configuración que usa el resto del motor para no duplicar reglas.
    indice_localidades_zona: dict[str, dict] = {}
    for codigo_zona, cfg_zona in ZONAS_PLANIFICACION.items():
        descripcion = str(cfg_zona.get("descripcion", "")).strip().upper()
        if descripcion:
            indice_localidades_zona.setdefault(
                descripcion,
                {
                    "codigo": str(codigo_zona).strip(),
                    "planificacion": str(cfg_zona.get("planificacion", "")).strip().upper(),
                    "grupo": str(cfg_zona.get("grupo", "")).strip(),
                },
            )

    def resolver_planificacion_expreso(zona: str, localidad: str) -> str:
        resolucion = obtener_planificacion_expreso(zona, localidad)

        # Excepciones explícitas (ej. VALENTIN ALSINA -> MARTES).
        planificacion_directa = str(
            resolucion.get("PlanificacionExpreso", "")
        ).strip().upper()
        if planificacion_directa:
            return planificacion_directa

        # GBA NORTE/OESTE/SUR y CABA NORTE deben integrarse a la zona
        # normal correspondiente a la localidad del maestro de Expresos.
        if resolucion.get("IntegrarAZona", False):
            cfg_localidad = indice_localidades_zona.get(localidad)
            if cfg_localidad:
                return cfg_localidad["planificacion"]

            # Si no hay equivalencia exacta, aplicar el día operativo
            # de respaldo parametrizado para la familia (ej. GBA OESTE -> VIERNES).
            planificacion_fallback = PLANIFICACION_FALLBACK_EXPRESOS.get(zona, "")
            if planificacion_fallback:
                return planificacion_fallback

            # Para familias sin fallback explícito, conservamos la clasificación
            # para hacer visible el dato faltante y no inventar una zona.
            return zona

        # Los circuitos CABA SUR / I / II permanecen separados como Expresos.
        if resolucion.get("MotivoPlanificacionExpreso") == "CIRCUITO_EXPRESO":
            return zona

        return zona

    tabla["Planificacion"] = ""
    tabla.loc[es_retira, "Planificacion"] = "RETIRA"

    mascara_no_retira = ~es_retira

    # Los circuitos CABA SUR / CABA SUR I / CABA SUR II tienen prioridad
    # sobre FrecuenciaEntrega: deben conservarse como circuitos EXPRESOS
    # aunque el maestro del cliente tenga LUNES/JUEVES/etc.
    circuitos_expresos_separados = {"CABA SUR", "CABA SUR I", "CABA SUR II"}
    mascara_circuito_expreso = (
        mascara_no_retira
        & zona_expreso.isin(circuitos_expresos_separados)
    )
    tabla.loc[mascara_circuito_expreso, "Planificacion"] = (
        zona_expreso.loc[mascara_circuito_expreso]
    )

    # Para el resto, un día semanal informado se conserva. Las zonas que
    # requieren integración (GBA/CABA NORTE) se resolverán luego por localidad.
    mascara_integrar_zona = (
        zona_expreso.eq("CABA NORTE")
        | zona_expreso.str.startswith("GBA NORTE")
        | zona_expreso.str.startswith("GBA OESTE")
        | zona_expreso.str.startswith("GBA SUR")
        | localidad_expreso.eq("VALENTIN ALSINA")
    )

    mascara_dia_semanal = (
        mascara_no_retira
        & ~mascara_circuito_expreso
        & ~mascara_integrar_zona
        & es_entrega_semanal
    )
    tabla.loc[mascara_dia_semanal, "Planificacion"] = (
        frecuencia_entrega.loc[mascara_dia_semanal]
    )

    # Las filas todavía sin resolver pasan por la lógica de Expresos.
    mascara_resolver_expreso = (
        mascara_no_retira
        & tabla["Planificacion"].eq("")
        & zona_expreso.ne("")
    )

    tabla.loc[mascara_resolver_expreso, "Planificacion"] = [
        resolver_planificacion_expreso(zona, localidad)
        for zona, localidad in zip(
            zona_expreso.loc[mascara_resolver_expreso],
            localidad_expreso.loc[mascara_resolver_expreso],
        )
    ]

    # =====================================================
    # RESPALDO POR CÓDIGO DE DESPACHO NORMAL
    # =====================================================
    # Para pedidos comerciales no Expreso, el Código Despacho del pedido es
    # una clave operativa válida. Si existe en ZONAS_PLANIFICACION, se usa su
    # planificación aunque el cruce con Maestro Clientes no haya aportado
    # FrecuenciaEntrega.
    codigo_despacho_normalizado = (
        tabla["CodigoDespacho"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.upper()
    )

    indice_codigo_despacho: dict[str, str] = {}
    for codigo_zona, cfg_zona in ZONAS_PLANIFICACION.items():
        codigo_norm = str(codigo_zona).strip().upper()
        planificacion_cfg = str(
            cfg_zona.get("planificacion", "")
        ).strip().upper()

        if codigo_norm and planificacion_cfg:
            indice_codigo_despacho[codigo_norm] = planificacion_cfg

        # Compatibilidad entre códigos guardados con/sin cero inicial.
        codigo_sin_ceros = codigo_norm.lstrip("0") or "0"
        if codigo_sin_ceros and planificacion_cfg:
            indice_codigo_despacho.setdefault(
                codigo_sin_ceros,
                planificacion_cfg,
            )

    codigo_expreso_universal = "05010001"
    mascara_codigo_despacho_normal = (
        mascara_no_retira
        & tabla["Planificacion"].eq("")
        & codigo_despacho_normalizado.ne("")
        & ~codigo_despacho_normalizado.isin(
            {codigo_expreso_universal, codigo_expreso_universal.lstrip("0")}
        )
    )

    planificacion_por_codigo = codigo_despacho_normalizado.map(
        indice_codigo_despacho
    ).fillna("")

    mascara_codigo_resuelto = (
        mascara_codigo_despacho_normal
        & planificacion_por_codigo.ne("")
    )

    tabla.loc[
        mascara_codigo_resuelto,
        "Planificacion",
    ] = planificacion_por_codigo.loc[mascara_codigo_resuelto]

    # Compatibilidad final: si todavía no se resolvió y existe una frecuencia
    # de entrega válida, conservar el comportamiento anterior.
    mascara_sin_planificacion = (
        mascara_no_retira
        & tabla["Planificacion"].eq("")
    )
    tabla.loc[mascara_sin_planificacion, "Planificacion"] = (
        frecuencia_entrega.loc[mascara_sin_planificacion]
    )

    # =====================================================
    # TIPOS
    # =====================================================

    columnas_texto = [
        "Pedido",
        "ClienteCodigo",
        "ClienteDescripcion",
        "Estado",
        "PreparacionEstado",
        "PreparacionID",
        "CodigoDespacho",
        "CodigoExpreso",
        "FrecuenciaEntrega",
        "DiaEntrega",
        "LocalidadExpreso",
        "ZonaAgrupadorExpreso",
        "ZonaExpreso",
        "Planificacion",
        "DetalleFamilias",
    ]

    for columna in columnas_texto:
        if columna in tabla.columns:
            tabla[columna] = (
                tabla[columna]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(
                    r"\.0$",
                    "",
                    regex=True,
                )
            )

    tabla["Fecha"] = (
        pd.to_datetime(
            tabla["Fecha"],
            errors="coerce",
            utc=True,
        )
        .dt.tz_localize(None)
    )

    tabla["FechaTransmisionERP"] = (
        pd.to_datetime(
            tabla["FechaTransmisionERP"],
            errors="coerce",
        )
        .dt.date
    )

    for columna in [
        "UnidadesPedido",
        "TotalUnidades",
        "TotalSKUs",
        "ImporteERP",
    ]:
        tabla[columna] = (
            pd.to_numeric(
                tabla[columna],
                errors="coerce",
            )
            .fillna(0)
            .astype(int)
        )

    tabla["TotalM3"] = (
        pd.to_numeric(
            tabla["TotalM3"],
            errors="coerce",
        )
        .fillna(0)
        .round(3)
    )

    columnas_faltantes = [
        columna
        for columna in COLUMNAS_FINALES_DESPACHOS
        if columna not in tabla.columns
    ]

    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas en la tabla operativa de Despachos: "
            f"{columnas_faltantes}"
        )

    return tabla[
        COLUMNAS_FINALES_DESPACHOS
    ].copy()
