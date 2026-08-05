import math
import pandas as pd
import altair as alt
import streamlit as st

from config import CARPETA_DATOS
from utils.confirmaciones_oc import guardar_confirmaciones_oc, eliminar_confirmaciones_oc
from utils.stock.helpers import dataframe_a_csv, formato_entero, aplicar_busqueda, dataframe_para_streamlit


CAPACIDADES_DESCARGA_M3 = {
    "CargaSuelta": 15.0,
    "20": 33.0,
    "40": 67.0,
    "40HQ": 75.0,
}

PREFIJOS_PIEZAS_REPUESTOS = ("R", "A", "U", "F", "S")


def _codigo_es_pieza_repuesto(codigo: object) -> bool:
    texto = str(codigo or "").strip().upper()
    return bool(texto) and texto.startswith(PREFIJOS_PIEZAS_REPUESTOS)


def preparar_volumetria_planificacion(
    tabla_pendientes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Usa volumetría real cuando existe. Para producto terminado sin dato,
    infiere por mediana de Familia, Sectorización y finalmente global.
    Piezas/repuestos no reciben una inferencia automática.
    """
    if tabla_pendientes is None or tabla_pendientes.empty:
        return (
            pd.DataFrame()
            if tabla_pendientes is None
            else tabla_pendientes.copy()
        )

    tabla = tabla_pendientes.copy()

    for columna in ["ArticuloCodigo", "Familia", "Sectorizacion"]:
        if columna not in tabla.columns:
            tabla[columna] = ""
        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabla["CantidadPendiente"] = pd.to_numeric(
        tabla.get("CantidadPendiente", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    tabla["VolumenUnitarioM3Original"] = pd.to_numeric(
        tabla.get("VolumenUnitarioM3", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    tabla["EsPiezaRepuesto"] = tabla[
        "ArticuloCodigo"
    ].map(_codigo_es_pieza_repuesto)

    referencias = tabla.loc[
        tabla["VolumenUnitarioM3Original"].gt(0)
        & ~tabla["EsPiezaRepuesto"]
    ].copy()

    medianas_familia = (
        referencias.loc[referencias["Familia"].ne("")]
        .groupby("Familia")["VolumenUnitarioM3Original"]
        .median()
        .to_dict()
    )
    medianas_sector = (
        referencias.loc[referencias["Sectorizacion"].ne("")]
        .groupby("Sectorizacion")["VolumenUnitarioM3Original"]
        .median()
        .to_dict()
    )
    mediana_global = (
        float(referencias["VolumenUnitarioM3Original"].median())
        if not referencias.empty
        else 0.0
    )

    def resolver(fila: pd.Series) -> tuple[float, str]:
        real = float(fila.get("VolumenUnitarioM3Original", 0) or 0)
        if real > 0:
            return real, "Real"

        if bool(fila.get("EsPiezaRepuesto", False)):
            return 0.0, "Piezas/Repuestos pendientes"

        familia = str(fila.get("Familia", "")).strip()
        sector = str(fila.get("Sectorizacion", "")).strip()

        por_familia = float(medianas_familia.get(familia, 0) or 0)
        if por_familia > 0:
            return por_familia, "Inferida por familia"

        por_sector = float(medianas_sector.get(sector, 0) or 0)
        if por_sector > 0:
            return por_sector, "Inferida por sectorización"

        if mediana_global > 0:
            return mediana_global, "Inferida global"

        return 0.0, "Sin referencia"

    resoluciones = tabla.apply(
        resolver,
        axis=1,
        result_type="expand",
    )
    resoluciones.columns = [
        "VolumenUnitarioPlanificadoM3",
        "OrigenVolumetria",
    ]
    tabla = pd.concat([tabla, resoluciones], axis=1)

    tabla["VolumenTotalM3Original"] = pd.to_numeric(
        tabla.get("VolumenTotalM3", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    tabla["VolumenTotalPlanificadoM3"] = (
        tabla["CantidadPendiente"]
        * tabla["VolumenUnitarioPlanificadoM3"]
    ).round(3)

    # Los gráficos actuales consumen estos nombres.
    tabla["VolumenUnitarioM3"] = tabla[
        "VolumenUnitarioPlanificadoM3"
    ]
    tabla["VolumenTotalM3"] = tabla[
        "VolumenTotalPlanificadoM3"
    ]
    tabla["TieneVolumetriaPlanificada"] = tabla[
        "VolumenUnitarioPlanificadoM3"
    ].gt(0)

    return tabla


def calcular_combinacion_descargas(
    volumen_m3: float,
    lineas_sin_referencia: int = 0,
) -> dict:
    """
    Hasta 15 m³ se considera Carga suelta. Para volúmenes mayores,
    busca la combinación con menor cantidad de unidades y menor
    capacidad ociosa.
    """
    volumen = max(float(volumen_m3 or 0), 0)
    pendientes = max(int(lineas_sin_referencia or 0), 0)

    base = {
        "CargasSueltas": 0,
        "Contenedores20": 0,
        "Contenedores40": 0,
        "Contenedores40HQ": 0,
        "CargasTotales": 0,
        "CapacidadAsignadaM3": 0.0,
        "CapacidadOciosaM3": 0.0,
        "CombinacionCarga": "Sin estimación",
        "VolumenIncompleto": pendientes > 0,
    }

    if volumen <= 0:
        if pendientes <= 0:
            base["CombinacionCarga"] = "Sin carga"
        return base

    if volumen <= CAPACIDADES_DESCARGA_M3["CargaSuelta"]:
        resultado = {
            **base,
            "CargasSueltas": 1,
            "CargasTotales": 1,
            "CapacidadAsignadaM3": CAPACIDADES_DESCARGA_M3["CargaSuelta"],
            "CapacidadOciosaM3": (
                CAPACIDADES_DESCARGA_M3["CargaSuelta"] - volumen
            ),
            "CombinacionCarga": "1 × Carga suelta",
        }
    else:
        max_unidades = (
            int(
                math.ceil(
                    volumen / CAPACIDADES_DESCARGA_M3["40HQ"]
                )
            )
            + 2
        )
        mejor = None

        for total in range(1, max_unidades + 1):
            candidatos = []

            for sueltas in range(total + 1):
                restante_1 = total - sueltas

                for cantidad_20 in range(restante_1 + 1):
                    restante_2 = restante_1 - cantidad_20

                    for cantidad_40 in range(restante_2 + 1):
                        cantidad_40hq = restante_2 - cantidad_40
                        capacidad = (
                            sueltas * CAPACIDADES_DESCARGA_M3["CargaSuelta"]
                            + cantidad_20 * CAPACIDADES_DESCARGA_M3["20"]
                            + cantidad_40 * CAPACIDADES_DESCARGA_M3["40"]
                            + cantidad_40hq * CAPACIDADES_DESCARGA_M3["40HQ"]
                        )

                        if capacidad < volumen:
                            continue

                        candidatos.append(
                            {
                                "criterio": (
                                    round(capacidad - volumen, 6),
                                    sueltas,
                                    cantidad_40hq,
                                    cantidad_40,
                                    cantidad_20,
                                ),
                                "CargasSueltas": sueltas,
                                "Contenedores20": cantidad_20,
                                "Contenedores40": cantidad_40,
                                "Contenedores40HQ": cantidad_40hq,
                                "CargasTotales": total,
                                "CapacidadAsignadaM3": capacidad,
                                "CapacidadOciosaM3": capacidad - volumen,
                            }
                        )

            if candidatos:
                mejor = min(candidatos, key=lambda item: item["criterio"])
                break

        if mejor is None:
            return base

        mejor.pop("criterio", None)
        resultado = {**base, **mejor}
        partes = []

        if resultado["CargasSueltas"]:
            partes.append(
                f'{resultado["CargasSueltas"]} × Carga suelta'
            )
        if resultado["Contenedores20"]:
            partes.append(f'{resultado["Contenedores20"]} × 20\'')
        if resultado["Contenedores40"]:
            partes.append(f'{resultado["Contenedores40"]} × 40\'')
        if resultado["Contenedores40HQ"]:
            partes.append(
                f'{resultado["Contenedores40HQ"]} × 40\' HQ'
            )

        resultado["CombinacionCarga"] = " + ".join(partes)

    if pendientes > 0:
        resultado["CombinacionCarga"] += (
            f" + {pendientes} línea(s) sin referencia"
        )

    return resultado


def _buscar_columna(
    tabla: pd.DataFrame,
    opciones: list[str],
) -> str | None:
    if tabla is None or tabla.empty:
        return None

    normalizadas = {
        str(columna).strip().lower().replace(" ", "").replace("_", ""): columna
        for columna in tabla.columns
    }

    for opcion in opciones:
        clave = (
            str(opcion)
            .strip()
            .lower()
            .replace(" ", "")
            .replace("_", "")
        )
        if clave in normalizadas:
            return normalizadas[clave]

    return None


def _serie_texto(
    tabla: pd.DataFrame,
    opciones: list[str],
) -> pd.Series:
    columna = _buscar_columna(tabla, opciones)

    if columna is None:
        return pd.Series(
            "",
            index=tabla.index,
            dtype="object",
        )

    return (
        tabla[columna]
        .fillna("")
        .astype(str)
        .str.strip()
    )


def _serie_numero(
    tabla: pd.DataFrame,
    opciones: list[str],
) -> pd.Series:
    columna = _buscar_columna(tabla, opciones)

    if columna is None:
        return pd.Series(
            0.0,
            index=tabla.index,
            dtype="float64",
        )

    return pd.to_numeric(
        tabla[columna],
        errors="coerce",
    ).fillna(0)


def _serie_fecha(
    tabla: pd.DataFrame,
    opciones: list[str],
) -> pd.Series:
    columna = _buscar_columna(tabla, opciones)

    if columna is None:
        return pd.Series(
            pd.NaT,
            index=tabla.index,
            dtype="datetime64[ns]",
        )

    return pd.to_datetime(
        tabla[columna],
        errors="coerce",
        dayfirst=True,
    )


def _clasificar_antiguedad_recepcion(
    dias: object,
) -> str:
    if pd.isna(dias):
        return "Sin fecha"

    dias_entero = int(dias)

    if dias_entero <= 0:
        return "🆕 Recién ingresado"
    if dias_entero == 1:
        return "🟢 En proceso"
    if dias_entero <= 3:
        return "🟡 Demorado"
    return "🔴 Crítico"


def _rango_antiguedad_recepcion(
    dias: object,
) -> str:
    if pd.isna(dias):
        return "Sin fecha"

    dias_entero = int(dias)

    if dias_entero <= 0:
        return "0 días"
    if dias_entero == 1:
        return "1 día"
    if dias_entero == 2:
        return "2 días"
    if dias_entero <= 5:
        return "3 a 5 días"
    return "Más de 5 días"


def construir_recepcion_operativa(
    tabla_stock_recepcion: pd.DataFrame,
    tabla_recepcion_agrupada: pd.DataFrame,
) -> pd.DataFrame:
    columnas_salida = [
        "ClaveRecepcion",
        "Ubicacion",
        "Contenedor",
        "ArticuloCodigo",
        "ArticuloDescripcion",
        "Familia",
        "Sectorizacion",
        "Unidades",
        "VolumenTotalM3",
        "Lote",
        "FechaVencimiento",
        "FechaAltaEstimada",
        "DiasEnRecepcion",
        "EstadoAntiguedad",
        "RangoAntiguedad",
    ]

    if (
        tabla_stock_recepcion is None
        or tabla_stock_recepcion.empty
    ):
        return pd.DataFrame(
            columns=columnas_salida
        )

    origen = tabla_stock_recepcion.copy()
    detalle = pd.DataFrame(index=origen.index)

    detalle["ArticuloCodigo"] = _serie_texto(
        origen,
        [
            "ArticuloCodigo",
            "CodigoArticulo",
            "codigo_articulo",
            "Codigo",
            "cod_art",
        ],
    )
    detalle["ArticuloDescripcion"] = _serie_texto(
        origen,
        [
            "ArticuloDescripcion",
            "Descripcion",
            "descrip",
        ],
    )
    detalle["Ubicacion"] = _serie_texto(
        origen,
        [
            "Ubicacion",
            "Ubicación",
            "CodigoUbicacion",
        ],
    )
    detalle["Contenedor"] = _serie_texto(
        origen,
        [
            "ContenedorNumero",
            "Contenedor",
            "NumeroContenedor",
            "CodigoContenedor",
            "LPN",
        ],
    )
    detalle["Lote"] = _serie_texto(
        origen,
        ["Lote"],
    )
    detalle["Unidades"] = _serie_numero(
        origen,
        [
            "Cantidad",
            "UnidadesSueltas",
            "Stock",
            "Unidades",
        ],
    )
    detalle["FechaVencimiento"] = _serie_fecha(
        origen,
        [
            "FechaVencimiento",
            "Fecha Vencimiento",
            "Vencimiento",
        ],
    )

    dias_restantes = _serie_numero(
        origen,
        [
            "DiasAlVencimiento",
            "DiasVencimiento",
            "Días vencimiento",
            "Dias",
            "Días",
        ],
    )

    # La regla operativa informada por el usuario es una vida estándar
    # de 2.000 días. La fecha de ingreso queda inferida desde el
    # vencimiento o, como respaldo, desde los días restantes.
    detalle["FechaAltaEstimada"] = (
        detalle["FechaVencimiento"]
        - pd.to_timedelta(
            2000,
            unit="D",
        )
    )

    hoy_normalizado = pd.Timestamp.today().normalize()
    fecha_por_dias = (
        hoy_normalizado
        - pd.to_timedelta(
            (2000 - dias_restantes)
            .clip(lower=0),
            unit="D",
        )
    )

    detalle["FechaAltaEstimada"] = (
        detalle["FechaAltaEstimada"]
        .where(
            detalle["FechaAltaEstimada"].notna(),
            fecha_por_dias,
        )
    )

    detalle = detalle.loc[
        detalle["ArticuloCodigo"].ne("")
        & detalle["Unidades"].gt(0)
    ].copy()

    if detalle.empty:
        return pd.DataFrame(
            columns=columnas_salida
        )

    # Metadatos enriquecidos ya calculados por artículo.
    if (
        tabla_recepcion_agrupada is not None
        and not tabla_recepcion_agrupada.empty
    ):
        columnas_meta = [
            columna
            for columna in [
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
                "VolumenUnitarioM3",
            ]
            if columna in tabla_recepcion_agrupada.columns
        ]

        metadata = (
            tabla_recepcion_agrupada[
                columnas_meta
            ]
            .drop_duplicates(
                "ArticuloCodigo"
            )
            .copy()
        )

        detalle = detalle.merge(
            metadata,
            on="ArticuloCodigo",
            how="left",
            suffixes=("", "_Meta"),
            validate="many_to_one",
        )

        if "ArticuloDescripcion_Meta" in detalle.columns:
            detalle["ArticuloDescripcion"] = (
                detalle["ArticuloDescripcion"]
                .where(
                    detalle[
                        "ArticuloDescripcion"
                    ].ne(""),
                    detalle[
                        "ArticuloDescripcion_Meta"
                    ],
                )
            )

    for columna in [
        "Familia",
        "Sectorizacion",
    ]:
        if columna not in detalle.columns:
            detalle[columna] = ""

        detalle[columna] = (
            detalle[columna]
            .fillna("")
            .astype(str)
        )

    if "VolumenUnitarioM3" not in detalle.columns:
        detalle["VolumenUnitarioM3"] = 0.0

    detalle["VolumenUnitarioM3"] = pd.to_numeric(
        detalle["VolumenUnitarioM3"],
        errors="coerce",
    ).fillna(0)

    detalle["VolumenTotalM3"] = (
        detalle["Unidades"]
        * detalle["VolumenUnitarioM3"]
    )

    detalle["ClaveRecepcion"] = (
        detalle["Ubicacion"]
        .where(
            detalle["Ubicacion"].ne(""),
            "SIN_UBICACION",
        )
        + "|"
        + detalle["Contenedor"]
        .where(
            detalle["Contenedor"].ne(""),
            "SIN_CONTENEDOR",
        )
    )

    resumen = (
        detalle.groupby(
            [
                "ClaveRecepcion",
                "Ubicacion",
                "Contenedor",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            Unidades=(
                "Unidades",
                "sum",
            ),
            VolumenTotalM3=(
                "VolumenTotalM3",
                "sum",
            ),
            Lote=(
                "Lote",
                lambda serie: " | ".join(
                    sorted(
                        {
                            str(valor)
                            for valor in serie
                            if str(valor).strip()
                        }
                    )
                ),
            ),
            FechaVencimiento=(
                "FechaVencimiento",
                "min",
            ),
            FechaAltaEstimada=(
                "FechaAltaEstimada",
                "min",
            ),
        )
    )

    resumen["DiasEnRecepcion"] = (
        hoy_normalizado
        - pd.to_datetime(
            resumen["FechaAltaEstimada"],
            errors="coerce",
        ).dt.normalize()
    ).dt.days

    resumen["DiasEnRecepcion"] = (
        resumen["DiasEnRecepcion"]
        .clip(lower=0)
    )

    resumen["EstadoAntiguedad"] = resumen[
        "DiasEnRecepcion"
    ].map(_clasificar_antiguedad_recepcion)

    resumen["RangoAntiguedad"] = resumen[
        "DiasEnRecepcion"
    ].map(_rango_antiguedad_recepcion)

    resumen["VolumenTotalM3"] = resumen[
        "VolumenTotalM3"
    ].round(3)

    return resumen[columnas_salida].sort_values(
        [
            "DiasEnRecepcion",
            "VolumenTotalM3",
            "Unidades",
        ],
        ascending=[
            False,
            False,
            False,
        ],
        na_position="last",
    ).reset_index(drop=True)


def asociar_oc_probable_recepcion(
    recepciones: pd.DataFrame,
    tabla_oc: pd.DataFrame,
) -> pd.DataFrame:
    salida = recepciones.copy()

    salida["OCProbable"] = ""
    salida["FechaReferenciaOC"] = pd.NaT
    salida["DiferenciaDiasOC"] = pd.NA
    salida["ConfianzaOC"] = "Sin coincidencia"

    if (
        salida.empty
        or tabla_oc is None
        or tabla_oc.empty
        or "ArticuloCodigo" not in tabla_oc.columns
    ):
        return salida

    oc = tabla_oc.copy()

    fecha_columna = next(
        (
            columna
            for columna in [
                "FechaConfirmadaIngreso",
                "FechaOperativaIngreso",
                "FechaIngresoEstimada",
                "FechaPuertoBuenosAires",
            ]
            if columna in oc.columns
        ),
        None,
    )

    if fecha_columna is None:
        return salida

    oc["ArticuloCodigo"] = (
        oc["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )
    oc["OrdenCompra"] = (
        oc.get(
            "OrdenCompra",
            pd.Series("", index=oc.index),
        )
        .fillna("")
        .astype(str)
        .str.strip()
    )
    oc["FechaReferenciaOC"] = pd.to_datetime(
        oc[fecha_columna],
        errors="coerce",
    )

    oc = oc.loc[
        oc["ArticuloCodigo"].ne("")
        & oc["OrdenCompra"].ne("")
        & oc["FechaReferenciaOC"].notna()
    ].copy()

    if oc.empty:
        return salida

    candidatos_por_codigo = {
        codigo: grupo[
            [
                "OrdenCompra",
                "FechaReferenciaOC",
            ]
        ].drop_duplicates()
        for codigo, grupo in oc.groupby(
            "ArticuloCodigo"
        )
    }

    for indice, fila in salida.iterrows():
        codigo = str(
            fila["ArticuloCodigo"]
        ).strip().upper()
        fecha_alta = pd.to_datetime(
            fila["FechaAltaEstimada"],
            errors="coerce",
        )

        candidatos = candidatos_por_codigo.get(
            codigo
        )

        if (
            candidatos is None
            or candidatos.empty
            or pd.isna(fecha_alta)
        ):
            continue

        candidatos = candidatos.copy()
        candidatos["DiferenciaDias"] = (
            candidatos["FechaReferenciaOC"]
            - fecha_alta
        ).abs().dt.days

        candidato = candidatos.sort_values(
            [
                "DiferenciaDias",
                "FechaReferenciaOC",
            ]
        ).iloc[0]

        diferencia = int(
            candidato["DiferenciaDias"]
        )

        if diferencia > 30:
            continue

        misma_distancia = int(
            candidatos[
                "DiferenciaDias"
            ].eq(diferencia).sum()
        )

        if diferencia <= 2 and misma_distancia == 1:
            confianza = "Alta"
        elif diferencia <= 7:
            confianza = "Media"
        else:
            confianza = "Baja"

        salida.at[
            indice,
            "OCProbable",
        ] = candidato["OrdenCompra"]
        salida.at[
            indice,
            "FechaReferenciaOC",
        ] = candidato["FechaReferenciaOC"]
        salida.at[
            indice,
            "DiferenciaDiasOC",
        ] = diferencia
        salida.at[
            indice,
            "ConfianzaOC",
        ] = confianza

    return salida




def render(contexto: dict) -> None:
    tabla_pendientes_oc = contexto["tabla_pendientes_oc"]
    tabla_recepcion_agrupada = contexto["tabla_recepcion_agrupada"]
    tabla_stock_recepcion = contexto["tabla_stock_recepcion"]
    tabla_stock_total_articulo = contexto["tabla_stock_total_articulo"]
    tabla_stock_total_detallado = contexto["tabla_stock_total_detallado"]
    tabla_articulos = contexto["tabla_articulos"]
    tabla_volumetria = contexto["tabla_volumetria"]
    tabla_max_min = contexto["tabla_max_min"]
    confirmaciones_oc = contexto.get("confirmaciones_oc", pd.DataFrame())
    st.subheader("🏭 Existencia física")
    st.caption(
        "Centro de control del ingreso y la existencia física del depósito."
    )

    vista_existencia = st.segmented_control(
        "Vista de existencia",
        options=["📥 Recepción", "📦 Stock consolidado"],
        default="📥 Recepción",
        key="vista_existencia_stock",
        label_visibility="collapsed",
    )

    if vista_existencia == "📥 Recepción":
        tabla_pendientes_oc = preparar_volumetria_planificacion(
            tabla_pendientes_oc
        )

        st.markdown("### 📥 Pendientes de ingreso")
        st.caption(
            "Mercadería pendiente informada por COMEX. Se excluyen las líneas "
            "que ya tienen fecha de ingreso. La fecha estimada considera Puerto "
            "Buenos Aires + 7 días de gestión aduanera."
        )

        # -----------------------------------------------------
        # FILTROS GENERALES DE OC
        # -----------------------------------------------------
        base_fechas_oc = tabla_pendientes_oc.loc[
            tabla_pendientes_oc["FechaOperativaIngreso"].notna()
        ].copy()

        fecha_min_oc = (
            base_fechas_oc["FechaOperativaIngreso"].min().date()
            if not base_fechas_oc.empty else None
        )
        fecha_max_oc = (
            base_fechas_oc["FechaOperativaIngreso"].max().date()
            if not base_fechas_oc.empty else None
        )

        hoy = pd.Timestamp.today().normalize().date()
        fecha_default_desde = hoy
        fecha_default_hasta = (
            pd.Timestamp(hoy) + pd.Timedelta(days=30)
        ).date()

        ordenes_disponibles = sorted(
            tabla_pendientes_oc["OrdenCompra"]
            .fillna("").astype(str).str.strip()
            .loc[lambda s: s.ne("")].drop_duplicates().tolist()
        ) if not tabla_pendientes_oc.empty else []

        familias_disponibles_oc = (
            tabla_pendientes_oc["Familia"]
            .fillna("").astype(str).str.strip()
            .loc[lambda s: s.ne("")].drop_duplicates().sort_values().tolist()
            if "Familia" in tabla_pendientes_oc.columns else []
        )

        prioridades_disponibles = [
            prioridad
            for prioridad in ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
            if prioridad in tabla_pendientes_oc.get(
                "SemaforoIngreso",
                pd.Series(dtype=str),
            ).astype(str).unique()
        ]

        defaults_filtros_recepcion = {
            "recepcion_aplicado_fechas": (
                fecha_default_desde,
                fecha_default_hasta,
            ),
            "recepcion_aplicado_ordenes": [],
            "recepcion_aplicado_familias": [],
            "recepcion_aplicado_prioridades": [],
            "recepcion_aplicado_sin_puerto": False,
            "recepcion_aplicado_piezas": False,
            "recepcion_aplicado_operarios": 3,
        }

        for clave, valor in defaults_filtros_recepcion.items():
            if clave not in st.session_state:
                st.session_state[clave] = valor

        claves_borrador_recepcion = {
            "fechas": "recepcion_borrador_fechas",
            "ordenes": "recepcion_borrador_ordenes",
            "familias": "recepcion_borrador_familias",
            "prioridades": "recepcion_borrador_prioridades",
            "sin_puerto": "recepcion_borrador_sin_puerto",
            "piezas": "recepcion_borrador_piezas",
            "operarios": "recepcion_borrador_operarios",
        }

        if claves_borrador_recepcion["fechas"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["fechas"]
            ] = st.session_state["recepcion_aplicado_fechas"]
        if claves_borrador_recepcion["ordenes"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["ordenes"]
            ] = st.session_state["recepcion_aplicado_ordenes"]
        if claves_borrador_recepcion["familias"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["familias"]
            ] = st.session_state["recepcion_aplicado_familias"]
        if claves_borrador_recepcion["prioridades"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["prioridades"]
            ] = st.session_state["recepcion_aplicado_prioridades"]
        if claves_borrador_recepcion["sin_puerto"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["sin_puerto"]
            ] = st.session_state["recepcion_aplicado_sin_puerto"]
        if claves_borrador_recepcion["piezas"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["piezas"]
            ] = st.session_state["recepcion_aplicado_piezas"]
        if claves_borrador_recepcion["operarios"] not in st.session_state:
            st.session_state[
                claves_borrador_recepcion["operarios"]
            ] = st.session_state["recepcion_aplicado_operarios"]

        def aplicar_filtros_recepcion() -> None:
            st.session_state["recepcion_aplicado_fechas"] = (
                st.session_state[
                    claves_borrador_recepcion["fechas"]
                ]
            )
            st.session_state["recepcion_aplicado_ordenes"] = list(
                st.session_state[
                    claves_borrador_recepcion["ordenes"]
                ]
            )
            st.session_state["recepcion_aplicado_familias"] = list(
                st.session_state[
                    claves_borrador_recepcion["familias"]
                ]
            )
            st.session_state["recepcion_aplicado_prioridades"] = list(
                st.session_state[
                    claves_borrador_recepcion["prioridades"]
                ]
            )
            st.session_state["recepcion_aplicado_sin_puerto"] = bool(
                st.session_state[
                    claves_borrador_recepcion["sin_puerto"]
                ]
            )
            st.session_state["recepcion_aplicado_piezas"] = bool(
                st.session_state[
                    claves_borrador_recepcion["piezas"]
                ]
            )
            st.session_state["recepcion_aplicado_operarios"] = int(
                st.session_state[
                    claves_borrador_recepcion["operarios"]
                ]
            )

        def borrar_filtros_recepcion() -> None:
            for clave, valor in defaults_filtros_recepcion.items():
                st.session_state[clave] = valor

            st.session_state[
                claves_borrador_recepcion["fechas"]
            ] = defaults_filtros_recepcion[
                "recepcion_aplicado_fechas"
            ]
            st.session_state[
                claves_borrador_recepcion["ordenes"]
            ] = []
            st.session_state[
                claves_borrador_recepcion["familias"]
            ] = []
            st.session_state[
                claves_borrador_recepcion["prioridades"]
            ] = []
            st.session_state[
                claves_borrador_recepcion["sin_puerto"]
            ] = False
            st.session_state[
                claves_borrador_recepcion["piezas"]
            ] = False
            st.session_state[
                claves_borrador_recepcion["operarios"]
            ] = 3

        with st.expander(
            "🔎 Filtros y planificación de descarga",
            expanded=True,
        ):
            with st.form(
                "form_filtros_recepcion_oc",
                clear_on_submit=False,
                border=False,
            ):
                f1, f2, f3 = st.columns(
                    [1.35, 1.1, 1.1],
                    vertical_alignment="bottom",
                )

                with f1:
                    st.date_input(
                        "Fecha operativa de ingreso",
                        key=claves_borrador_recepcion["fechas"],
                        help=(
                            "Por defecto muestra los próximos 30 días. "
                            "Usa la fecha confirmada cuando existe; "
                            "de lo contrario, la estimada."
                        ),
                    )

                with f2:
                    st.multiselect(
                        "Órdenes de compra",
                        options=ordenes_disponibles,
                        key=claves_borrador_recepcion["ordenes"],
                        placeholder="Todas las OC",
                        help=(
                            "Seleccioná una o varias OC para "
                            "planificar una jornada de descarga."
                        ),
                    )

                with f3:
                    st.multiselect(
                        "Familias",
                        options=familias_disponibles_oc,
                        key=claves_borrador_recepcion["familias"],
                        placeholder="Todas las familias",
                    )

                f4, f5, f6, f7 = st.columns(
                    [1.1, 1.1, 1.1, 1],
                    vertical_alignment="bottom",
                )

                with f4:
                    st.multiselect(
                        "Prioridad",
                        options=prioridades_disponibles,
                        key=claves_borrador_recepcion["prioridades"],
                        placeholder="Todas las prioridades",
                    )

                with f5:
                    st.toggle(
                        "Mostrar líneas sin fecha de puerto",
                        key=claves_borrador_recepcion["sin_puerto"],
                    )

                with f6:
                    st.toggle(
                        "Ver piezas y repuestos",
                        key=claves_borrador_recepcion["piezas"],
                        help=(
                            "Incluye códigos R, A, U, F y S. "
                            "Por defecto se analiza producto terminado."
                        ),
                    )

                with f7:
                    st.selectbox(
                        "Operarios por jornada",
                        options=[3, 4],
                        key=claves_borrador_recepcion["operarios"],
                        help=(
                            "La misma dotación atiende todos los "
                            "camiones programados para ese día."
                        ),
                    )

                boton_aplicar, boton_borrar, _ = st.columns(
                    [1, 1, 4],
                )

                boton_aplicar.form_submit_button(
                    "✅ Aplicar filtros",
                    type="primary",
                    width="stretch",
                    on_click=aplicar_filtros_recepcion,
                )

                boton_borrar.form_submit_button(
                    "🧹 Borrar filtros",
                    width="stretch",
                    on_click=borrar_filtros_recepcion,
                )

        rango_fechas_oc = st.session_state[
            "recepcion_aplicado_fechas"
        ]
        filtro_ordenes_oc = st.session_state[
            "recepcion_aplicado_ordenes"
        ]
        filtro_familias_oc = st.session_state[
            "recepcion_aplicado_familias"
        ]
        filtro_prioridades_general = st.session_state[
            "recepcion_aplicado_prioridades"
        ]
        mostrar_sin_puerto = st.session_state[
            "recepcion_aplicado_sin_puerto"
        ]
        mostrar_piezas_repuestos = bool(
            st.session_state["recepcion_aplicado_piezas"]
        )
        operarios_por_camion = int(
            st.session_state[
                "recepcion_aplicado_operarios"
            ]
        )

        vista_base_oc = tabla_pendientes_oc.copy()

        if (
            not mostrar_piezas_repuestos
            and not vista_base_oc.empty
        ):
            vista_base_oc = vista_base_oc.loc[
                ~vista_base_oc["EsPiezaRepuesto"].fillna(False)
            ].copy()

        if not mostrar_sin_puerto and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["FechaPuertoBuenosAires"].notna()
            ].copy()

        if filtro_ordenes_oc and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["OrdenCompra"]
                .astype(str)
                .isin(filtro_ordenes_oc)
            ].copy()

        if filtro_familias_oc and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["Familia"]
                .isin(filtro_familias_oc)
            ].copy()

        if filtro_prioridades_general and not vista_base_oc.empty:
            vista_base_oc = vista_base_oc.loc[
                vista_base_oc["SemaforoIngreso"]
                .isin(filtro_prioridades_general)
            ].copy()

        if (
            isinstance(rango_fechas_oc, (list, tuple))
            and len(rango_fechas_oc) == 2
            and not vista_base_oc.empty
        ):
            fecha_desde_oc = pd.Timestamp(
                rango_fechas_oc[0]
            )
            fecha_hasta_oc = pd.Timestamp(
                rango_fechas_oc[1]
            )
            mascara_fecha = vista_base_oc[
                "FechaOperativaIngreso"
            ].between(
                fecha_desde_oc,
                fecha_hasta_oc,
                inclusive="both",
            )

            if mostrar_sin_puerto:
                mascara_fecha = (
                    mascara_fecha
                    | vista_base_oc[
                        "FechaOperativaIngreso"
                    ].isna()
                )

            vista_base_oc = vista_base_oc.loc[
                mascara_fecha
            ].copy()

        oc_pendientes = int(vista_base_oc["OrdenCompra"].nunique()) if not vista_base_oc.empty else 0
        sku_oc = int(vista_base_oc["ArticuloCodigo"].nunique()) if not vista_base_oc.empty else 0
        unidades_oc = float(vista_base_oc["CantidadPendiente"].sum()) if not vista_base_oc.empty else 0
        volumen_oc = float(vista_base_oc["VolumenTotalM3"].sum()) if not vista_base_oc.empty else 0
        sin_fecha_puerto = int(tabla_pendientes_oc["FechaPuertoBuenosAires"].isna().sum()) if not tabla_pendientes_oc.empty else 0
        atrasadas = int(vista_base_oc["EstadoIngreso"].eq("Atrasado").sum()) if not vista_base_oc.empty else 0
        prioritarias = int(vista_base_oc["SemaforoIngreso"].isin(["Sin stock", "Crítico"]).sum()) if not vista_base_oc.empty else 0
        stock_disponible_total = float(vista_base_oc["StockDisponibleActual"].sum()) if not vista_base_oc.empty else 0
        impacto_global = unidades_oc / stock_disponible_total * 100 if stock_disponible_total > 0 else 0

        calidad_sku = (
            vista_base_oc[
                ["ArticuloCodigo", "OrigenVolumetria"]
            ]
            .drop_duplicates("ArticuloCodigo")
            if not vista_base_oc.empty
            else pd.DataFrame(
                columns=["ArticuloCodigo", "OrigenVolumetria"]
            )
        )
        sku_volumetria_real = int(
            calidad_sku["OrigenVolumetria"].eq("Real").sum()
        )
        sku_volumetria_inferida = int(
            calidad_sku["OrigenVolumetria"]
            .str.startswith("Inferida", na=False)
            .sum()
        )
        sku_volumetria_pendiente = int(
            calidad_sku["OrigenVolumetria"]
            .isin(
                [
                    "Sin referencia",
                    "Piezas/Repuestos pendientes",
                ]
            )
            .sum()
        )
        total_sku_calidad = int(len(calidad_sku))
        porcentaje_volumetria_real = (
            sku_volumetria_real / total_sku_calidad * 100
            if total_sku_calidad > 0
            else 0
        )

        resumen_camiones_oc = (
            vista_base_oc.groupby(
                [
                    "OrdenCompra",
                    "FechaOperativaIngreso",
                ],
                as_index=False,
                dropna=False,
            )
            .agg(
                VolumenOC=(
                    "VolumenTotalM3",
                    "sum",
                ),
                LineasSinReferencia=(
                    "TieneVolumetriaPlanificada",
                    lambda serie: int(
                        (~serie.fillna(False)).sum()
                    ),
                ),
            )
            if not vista_base_oc.empty
            else pd.DataFrame(
                columns=[
                    "OrdenCompra",
                    "FechaOperativaIngreso",
                    "VolumenOC",
                ]
            )
        )

        if not resumen_camiones_oc.empty:
            combinaciones_oc = resumen_camiones_oc.apply(
                lambda fila: calcular_combinacion_descargas(
                    fila["VolumenOC"],
                    fila["LineasSinReferencia"],
                ),
                axis=1,
                result_type="expand",
            )

            resumen_camiones_oc = pd.concat(
                [
                    resumen_camiones_oc.reset_index(drop=True),
                    combinaciones_oc.reset_index(drop=True),
                ],
                axis=1,
            )

            resumen_camiones_oc[
                "CamionesEstimados"
            ] = resumen_camiones_oc[
                "CargasTotales"
            ].astype(int)

        camiones_estimados = int(
            resumen_camiones_oc.get(
                "CargasTotales",
                pd.Series(dtype=int),
            ).sum()
        )

        total_carga_suelta = int(
            resumen_camiones_oc.get(
                "CargasSueltas",
                pd.Series(dtype=int),
            ).sum()
        )
        total_20 = int(
            resumen_camiones_oc.get(
                "Contenedores20",
                pd.Series(dtype=int),
            ).sum()
        )
        total_40 = int(
            resumen_camiones_oc.get(
                "Contenedores40",
                pd.Series(dtype=int),
            ).sum()
        )
        total_40hq = int(
            resumen_camiones_oc.get(
                "Contenedores40HQ",
                pd.Series(dtype=int),
            ).sum()
        )

        resumen_dotacion_diaria = (
            resumen_camiones_oc.loc[
                resumen_camiones_oc[
                    "FechaOperativaIngreso"
                ].notna()
                & resumen_camiones_oc[
                    "CamionesEstimados"
                ].gt(0)
            ]
            .groupby(
                "FechaOperativaIngreso",
                as_index=False,
            )
            .agg(
                Camiones=(
                    "CamionesEstimados",
                    "sum",
                )
            )
            if not resumen_camiones_oc.empty
            else pd.DataFrame(
                columns=[
                    "FechaOperativaIngreso",
                    "Camiones",
                ]
            )
        )

        dias_con_descarga = int(
            len(resumen_dotacion_diaria)
        )
        operarios_sugeridos = int(
            dias_con_descarga
            * operarios_por_camion
        )

        # -----------------------------------------------------
        # TARJETAS KPI — MISMO LENGUAJE VISUAL DEL SISTEMA
        # -----------------------------------------------------
        st.markdown(
            """
            <style>
            .recepcion-kpi-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 12px;
                margin: 10px 0 18px 0;
            }
            .recepcion-kpi-card {
                min-height: 118px;
                padding: 15px 17px;
                border: 1px solid rgba(148, 163, 184, 0.22);
                border-radius: 11px;
                background: linear-gradient(145deg, #121923 0%, #0f151e 100%);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
            }
            .recepcion-kpi-label {
                color: #d8dee9;
                font-size: 0.84rem;
                font-weight: 650;
            }
            .recepcion-kpi-value {
                color: #f8fafc;
                font-size: 1.82rem;
                font-weight: 750;
                line-height: 1.05;
                margin-top: 7px;
            }
            .recepcion-kpi-detail {
                color: #9ba8b7;
                font-size: 0.75rem;
                margin-top: 8px;
            }
            .recepcion-panel {
                border: 1px solid rgba(148, 163, 184, 0.20);
                border-radius: 12px;
                padding: 10px 14px 4px 14px;
                background: rgba(15, 23, 34, 0.58);
            }
            @media (max-width: 1100px) {
                .recepcion-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            }
            @media (max-width: 650px) {
                .recepcion-kpi-grid { grid-template-columns: 1fr; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        def _fmt_m3(valor):
            return (
                f"{float(valor):,.2f} m³"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        tarjetas_recepcion = [
            ("📥 OC pendientes", formato_entero(oc_pendientes),
             f"{formato_entero(sku_oc)} SKU · {formato_entero(atrasadas)} líneas atrasadas"),
            ("📦 Unidades pendientes", formato_entero(unidades_oc),
             "Mercadería todavía sin ingreso"),
            ("📐 Volumen estimado", _fmt_m3(volumen_oc),
             "Carga física pendiente de recibir"),
            ("🚛 Plan de descarga", formato_entero(camiones_estimados),
             (
                 f"{formato_entero(total_carga_suelta)} sueltas · "
                 f"{formato_entero(total_20)} × 20' · "
                 f"{formato_entero(total_40)} × 40' · "
                 f"{formato_entero(total_40hq)} × 40' HQ"
             )),
            ("👷 Operarios sugeridos", formato_entero(operarios_sugeridos),
             f"{formato_entero(dias_con_descarga)} jornadas × {operarios_por_camion} operarios"),
            ("🚨 Prioridad alta / crítica", formato_entero(prioritarias),
             "Líneas que requieren planificación"),
            ("❔ Sin fecha de puerto", formato_entero(sin_fecha_puerto),
             "Ocultas salvo que se habiliten"),
            ("📊 Ingreso vs disponible", f"{impacto_global:.1f} %".replace(".", ","),
             "Peso del ingreso frente al stock actual"),
            ("🧪 Calidad de volumetría",
             f"{porcentaje_volumetria_real:.1f} %".replace(".", ","),
             (
                 f"{formato_entero(sku_volumetria_real)} reales · "
                 f"{formato_entero(sku_volumetria_inferida)} inferidos · "
                 f"{formato_entero(sku_volumetria_pendiente)} pendientes"
             )),
        ]

        html_kpis = '<div class="recepcion-kpi-grid">'
        for etiqueta, valor, detalle in tarjetas_recepcion:
            html_kpis += (
                '<div class="recepcion-kpi-card">'
                f'<div class="recepcion-kpi-label">{etiqueta}</div>'
                f'<div class="recepcion-kpi-value">{valor}</div>'
                f'<div class="recepcion-kpi-detail">{detalle}</div>'
                '</div>'
            )
        html_kpis += '</div>'
        st.markdown(html_kpis, unsafe_allow_html=True)

        with st.expander("📅 Confirmar fecha exacta de ingreso", expanded=False):
            st.caption(
                "La confirmación se aplica a toda la OC y se guarda en "
                "Confirmaciones_Ingreso_OC.csv, sin modificar el reporte de COMEX."
            )
            c1, c2 = st.columns([1.6, 1], vertical_alignment="bottom")
            with c1:
                oc_confirmar = st.multiselect(
                    "OC a confirmar",
                    options=ordenes_disponibles,
                    default=filtro_ordenes_oc,
                    key="oc_confirmar_fecha_ingreso",
                    placeholder="Seleccioná una o varias OC",
                )
            with c2:
                fecha_confirmacion = st.date_input(
                    "Fecha confirmada",
                    value=pd.Timestamp.today().date(),
                    key="fecha_confirmada_ingreso_oc",
                )

            usuario_confirmacion = str(
                st.session_state.get("usuario")
                or st.session_state.get("username")
                or st.session_state.get("nombre_usuario")
                or ""
            )
            b1, b2 = st.columns(2)
            with b1:
                guardar_fecha = st.button(
                    "💾 Guardar confirmación",
                    type="primary",
                    width="stretch",
                    disabled=not oc_confirmar,
                    key="guardar_fecha_confirmada_oc",
                )
            with b2:
                quitar_fecha = st.button(
                    "🗑️ Quitar confirmación",
                    width="stretch",
                    disabled=not oc_confirmar,
                    key="quitar_fecha_confirmada_oc",
                )

            if guardar_fecha:
                try:
                    resumen_guardado = guardar_confirmaciones_oc(
                        CARPETA_DATOS,
                        oc_confirmar,
                        fecha_confirmacion,
                        usuario_confirmacion,
                    )
                    st.success(
                        f"Fecha {fecha_confirmacion.strftime('%d/%m/%Y')} confirmada "
                        f"para {resumen_guardado['cantidad']} OC."
                    )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as error:
                    st.error(f"No se pudo guardar la confirmación: {error}")

            if quitar_fecha:
                try:
                    resumen_eliminado = eliminar_confirmaciones_oc(
                        CARPETA_DATOS,
                        oc_confirmar,
                    )
                    st.success(
                        f"Se quitaron {resumen_eliminado['cantidad']} confirmaciones."
                    )
                    st.cache_data.clear()
                    st.rerun()
                except Exception as error:
                    st.error(f"No se pudo quitar la confirmación: {error}")

            confirmaciones_visibles = confirmaciones_oc.copy()
            if not confirmaciones_visibles.empty:
                st.dataframe(
                    dataframe_para_streamlit(confirmaciones_visibles),
                    hide_index=True,
                    width="stretch",
                    height=min(260, 75 + len(confirmaciones_visibles) * 34),
                    column_config={
                        "FechaConfirmadaIngreso": st.column_config.DateColumn(
                            "Fecha confirmada", format="DD/MM/YYYY"
                        ),
                        "FechaRegistro": st.column_config.DatetimeColumn(
                            "Registrado", format="DD/MM/YYYY HH:mm"
                        ),
                    },
                )

        if not vista_base_oc.empty:
            st.markdown("#### Lectura visual de los ingresos esperados")
            grafico_1, grafico_2 = st.columns(
                [1.05, 1],
                vertical_alignment="top",
            )

            with grafico_1:
                st.markdown("##### Evolución de OC esperadas")
                por_fecha = (
                    vista_base_oc.loc[
                        vista_base_oc["FechaOperativaIngreso"].notna()
                    ]
                    .groupby("FechaOperativaIngreso", as_index=False)
                    .agg(
                        Ordenes=("OrdenCompra", "nunique"),
                        Unidades=("CantidadPendiente", "sum"),
                        SKU=("ArticuloCodigo", "nunique"),
                        VolumenM3=("VolumenTotalM3", "sum"),
                    )
                    .sort_values("FechaOperativaIngreso")
                )

                if por_fecha.empty:
                    st.info("No hay fechas estimadas disponibles para graficar.")
                else:
                    por_fecha["FechaVisible"] = (
                        por_fecha["FechaOperativaIngreso"].dt.strftime("%d/%m")
                    )
                    orden_fechas = por_fecha["FechaVisible"].tolist()
                    por_fecha["EsMaximo"] = (
                        por_fecha["Ordenes"].eq(por_fecha["Ordenes"].max())
                    )

                    barras_oc = (
                        alt.Chart(por_fecha)
                        .mark_bar(
                            cornerRadiusTopLeft=5,
                            cornerRadiusTopRight=5,
                            size=26,
                        )
                        .encode(
                            x=alt.X(
                                "FechaVisible:N",
                                title=None,
                                sort=orden_fechas,
                                axis=alt.Axis(
                                    labelAngle=0,
                                    grid=False,
                                    labelColor="#CBD5E1",
                                    labelPadding=8,
                                    domainColor="#3B4655",
                                    tickColor="#3B4655",
                                ),
                            ),
                            y=alt.Y(
                                "Ordenes:Q",
                                title="Cantidad de OC",
                                scale=alt.Scale(zero=True),
                                axis=alt.Axis(
                                    tickMinStep=1,
                                    grid=True,
                                    gridColor="#26303D",
                                    labelColor="#CBD5E1",
                                    titleColor="#CBD5E1",
                                ),
                            ),
                            color=alt.condition(
                                alt.datum.EsMaximo,
                                alt.value("#2563EB"),
                                alt.value("#3B5F8A"),
                            ),
                            tooltip=[
                                alt.Tooltip("FechaVisible:N", title="Ingreso estimado"),
                                alt.Tooltip("Ordenes:Q", title="OC", format=",.0f"),
                                alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                                alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                                alt.Tooltip("VolumenM3:Q", title="Volumen m³", format=".2f"),
                            ],
                        )
                    )

                    etiquetas_oc = (
                        alt.Chart(por_fecha)
                        .mark_text(
                            align="center",
                            baseline="bottom",
                            dy=-7,
                            color="#F8FAFC",
                            fontSize=11,
                            fontWeight=700,
                        )
                        .encode(
                            x=alt.X("FechaVisible:N", sort=orden_fechas),
                            y="Ordenes:Q",
                            text=alt.Text("Ordenes:Q", format=",.0f"),
                        )
                    )

                    st.altair_chart(
                        (barras_oc + etiquetas_oc)
                        .properties(height=310)
                        .configure_view(strokeOpacity=0),
                        width="stretch",
                    )

            with grafico_2:
                st.markdown("##### Impacto esperado del ingreso")
                orden_prioridad = ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
                por_prioridad = (
                    vista_base_oc.groupby("SemaforoIngreso", as_index=False)
                    .agg(
                        Unidades=("CantidadPendiente", "sum"),
                        SKU=("ArticuloCodigo", "nunique"),
                    )
                )
                por_prioridad = por_prioridad.loc[
                    por_prioridad["SemaforoIngreso"].isin(orden_prioridad)
                ].copy()
                por_prioridad["Etiqueta"] = por_prioridad["Unidades"].map(
                    lambda valor: f"{int(valor):,}".replace(",", ".")
                )

                if por_prioridad.empty:
                    st.info("No hay prioridades disponibles para graficar.")
                else:
                    barras_prioridad = (
                        alt.Chart(por_prioridad)
                        .mark_bar(cornerRadiusEnd=5, size=24, color="#74B9E8")
                        .encode(
                            x=alt.X(
                                "Unidades:Q",
                                title="Unidades",
                                axis=alt.Axis(
                                    grid=True,
                                    gridColor="#26303D",
                                    labelColor="#CBD5E1",
                                    titleColor="#CBD5E1",
                                ),
                            ),
                            y=alt.Y(
                                "SemaforoIngreso:N",
                                title=None,
                                sort=orden_prioridad,
                                axis=alt.Axis(labelColor="#E2E8F0"),
                            ),
                            tooltip=[
                                alt.Tooltip("SemaforoIngreso:N", title="Prioridad"),
                                alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                                alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                            ],
                        )
                    )
                    etiquetas_prioridad = (
                        alt.Chart(por_prioridad)
                        .mark_text(
                            align="left",
                            baseline="middle",
                            dx=7,
                            color="#F8FAFC",
                            fontSize=11,
                            fontWeight=700,
                        )
                        .encode(
                            x="Unidades:Q",
                            y=alt.Y("SemaforoIngreso:N", sort=orden_prioridad),
                            text="Etiqueta:N",
                        )
                    )
                    st.altair_chart(
                        (barras_prioridad + etiquetas_prioridad)
                        .properties(height=310)
                        .configure_view(strokeOpacity=0),
                        width="stretch",
                    )

            st.markdown("##### OC con mayor volumen pendiente")
            por_oc = (
                vista_base_oc.groupby("OrdenCompra", as_index=False)
                .agg(
                    VolumenM3=("VolumenTotalM3", "sum"),
                    Unidades=("CantidadPendiente", "sum"),
                    SKU=("ArticuloCodigo", "nunique"),
                    FechaIngreso=("FechaOperativaIngreso", "min"),
                )
                .sort_values("VolumenM3", ascending=False)
                .head(10)
            )
            por_oc["OrdenCompra"] = por_oc["OrdenCompra"].astype(str)
            por_oc["EtiquetaVolumen"] = por_oc["VolumenM3"].map(
                lambda valor: f"{valor:.2f} m³".replace(".", ",")
            )
            por_oc["EsMaximo"] = por_oc["VolumenM3"].eq(por_oc["VolumenM3"].max())

            barras_oc_volumen = (
                alt.Chart(por_oc)
                .mark_bar(cornerRadiusEnd=5, size=22)
                .encode(
                    x=alt.X(
                        "VolumenM3:Q",
                        title="Volumen pendiente m³",
                        axis=alt.Axis(
                            grid=True,
                            gridColor="#26303D",
                            labelColor="#CBD5E1",
                            titleColor="#CBD5E1",
                        ),
                    ),
                    y=alt.Y(
                        "OrdenCompra:N",
                        title="OC",
                        sort="-x",
                        axis=alt.Axis(labelColor="#E2E8F0"),
                    ),
                    color=alt.condition(
                        alt.datum.EsMaximo,
                        alt.value("#2563EB"),
                        alt.value("#74B9E8"),
                    ),
                    tooltip=[
                        alt.Tooltip("OrdenCompra:N", title="OC"),
                        alt.Tooltip("VolumenM3:Q", title="Volumen m³", format=".2f"),
                        alt.Tooltip("Unidades:Q", title="Unidades", format=",.0f"),
                        alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                        alt.Tooltip("FechaIngreso:T", title="Ingreso", format="%d/%m/%Y"),
                    ],
                )
            )
            etiquetas_oc_volumen = (
                alt.Chart(por_oc)
                .mark_text(
                    align="left",
                    baseline="middle",
                    dx=7,
                    color="#F8FAFC",
                    fontSize=11,
                    fontWeight=700,
                )
                .encode(
                    x="VolumenM3:Q",
                    y=alt.Y("OrdenCompra:N", sort="-x"),
                    text="EtiquetaVolumen:N",
                )
            )
            st.altair_chart(
                (barras_oc_volumen + etiquetas_oc_volumen)
                .properties(height=max(260, len(por_oc) * 34))
                .configure_view(strokeOpacity=0),
                width="stretch",
            )

        if not resumen_camiones_oc.empty:
            st.markdown("#### Planificación de descarga por OC")
            resumen_descarga = (
                vista_base_oc.groupby("OrdenCompra", as_index=False)
                .agg(
                    FechaOperativa=("FechaOperativaIngreso", "min"),
                    TipoFecha=("TipoFechaIngreso", "first"),
                    SKU=("ArticuloCodigo", "nunique"),
                    Unidades=("CantidadPendiente", "sum"),
                    VolumenM3=("VolumenTotalM3", "sum"),
                    LineasSinReferencia=(
                        "TieneVolumetriaPlanificada",
                        lambda serie: int(
                            (~serie.fillna(False)).sum()
                        ),
                    ),
                    PrioridadAltaCritica=("SemaforoIngreso", lambda s: int(s.isin(["Sin stock", "Crítico"]).sum())),
                )
            )
            combinaciones_descarga = resumen_descarga.apply(
                lambda fila: calcular_combinacion_descargas(
                    fila["VolumenM3"],
                    fila["LineasSinReferencia"],
                ),
                axis=1,
                result_type="expand",
            )

            resumen_descarga = pd.concat(
                [
                    resumen_descarga.reset_index(drop=True),
                    combinaciones_descarga.reset_index(drop=True),
                ],
                axis=1,
            )

            resumen_descarga["Camiones"] = (
                resumen_descarga[
                    "CargasTotales"
                ]
                .fillna(0)
                .astype(int)
            )

            fechas_con_camiones = set(
                resumen_descarga.loc[
                    resumen_descarga["Camiones"].gt(0)
                    & resumen_descarga["FechaOperativa"].notna(),
                    "FechaOperativa",
                ].tolist()
            )

            resumen_descarga["Operarios"] = (
                resumen_descarga[
                    "FechaOperativa"
                ]
                .isin(fechas_con_camiones)
                .map(
                    {
                        True: operarios_por_camion,
                        False: 0,
                    }
                )
                .astype(int)
            )
            resumen_descarga = resumen_descarga.sort_values(
                ["FechaOperativa", "Camiones", "VolumenM3"],
                ascending=[True, False, False],
                na_position="last",
            )
            st.dataframe(
                dataframe_para_streamlit(resumen_descarga),
                hide_index=True,
                width="stretch",
                height=min(360, 80 + len(resumen_descarga) * 35),
                column_config={
                    "FechaOperativa": st.column_config.DateColumn("Ingreso", format="DD/MM/YYYY"),
                    "VolumenM3": st.column_config.NumberColumn(
                        "Volumen m³",
                        format="%.2f",
                    ),
                    "CombinacionCarga": st.column_config.TextColumn(
                        "Combinación estimada",
                        width="large",
                    ),
                    "CargasSueltas": st.column_config.NumberColumn(
                        "Carga suelta",
                        format="%d",
                    ),
                    "Contenedores20": st.column_config.NumberColumn(
                        "20'",
                        format="%d",
                    ),
                    "Contenedores40": st.column_config.NumberColumn(
                        "40'",
                        format="%d",
                    ),
                    "Contenedores40HQ": st.column_config.NumberColumn(
                        "40' HQ",
                        format="%d",
                    ),
                    "Camiones": st.column_config.NumberColumn(
                        "Cargas totales",
                        format="%d",
                    ),
                    "CapacidadAsignadaM3": st.column_config.NumberColumn(
                        "Capacidad asignada m³",
                        format="%.2f",
                    ),
                    "CapacidadOciosaM3": st.column_config.NumberColumn(
                        "Capacidad libre m³",
                        format="%.2f",
                    ),
                    "Operarios": st.column_config.NumberColumn(
                        "Operarios de la jornada",
                        format="%d",
                    ),
                },
            )

        st.markdown("#### Detalle operativo de OC pendientes")
        filtro_oc_1, filtro_oc_2, filtro_oc_3 = st.columns([2, 1, 1])
        with filtro_oc_1:
            buscar_oc = st.text_input(
                "Buscar en pendientes de OC",
                key="buscar_pendientes_oc",
                placeholder="OC, código, descripción, proforma...",
            )
        with filtro_oc_2:
            estados_oc = sorted(vista_base_oc["EstadoIngreso"].dropna().unique().tolist()) if not vista_base_oc.empty else []
            filtro_estado_oc = st.multiselect(
                "Estado de ingreso", estados_oc, key="estado_pendientes_oc"
            )
        with filtro_oc_3:
            prioridades_oc = [
                p for p in ["Sin stock", "Crítico", "Alto", "Medio", "Bajo"]
                if p in vista_base_oc.get("SemaforoIngreso", pd.Series(dtype=str)).unique()
            ]
            filtro_prioridad_oc = st.multiselect(
                "Prioridad", prioridades_oc, key="prioridad_pendientes_oc"
            )

        vista_oc = aplicar_busqueda(vista_base_oc, buscar_oc)
        if filtro_estado_oc:
            vista_oc = vista_oc.loc[vista_oc["EstadoIngreso"].isin(filtro_estado_oc)]
        if filtro_prioridad_oc:
            vista_oc = vista_oc.loc[vista_oc["SemaforoIngreso"].isin(filtro_prioridad_oc)]

        columnas_oc_vista = [
            "OrdenCompra", "ArticuloCodigo", "ArticuloDescripcion", "Familia",
            "CantidadPendiente", "FechaPuertoBuenosAires", "FechaIngresoEstimada",
            "FechaConfirmadaIngreso", "FechaOperativaIngreso", "EstadoFechaIngreso",
            "StockDisponibleActual", "PorcentajeSobreTotal",
            "PorcentajeSobreStockActual", "SemaforoIngreso", "AccionRecomendada",
            "VolumenUnitarioM3Original",
            "VolumenUnitarioPlanificadoM3",
            "VolumenTotalM3",
            "OrigenVolumetria",
            "EsPiezaRepuesto",
            "EstadoOC",
            "Proforma",
        ]
        columnas_oc_vista = [c for c in columnas_oc_vista if c in vista_oc.columns]

        st.download_button(
            "⬇️ Descargar pendientes de OC",
            data=dataframe_a_csv(vista_oc),
            file_name="Pendientes_OC_Enriquecidos.csv",
            mime="text/csv",
            key="descargar_pendientes_oc_enriquecidos",
        )
        st.dataframe(
            dataframe_para_streamlit(vista_oc[columnas_oc_vista]),
            hide_index=True,
            width="stretch",
            height=460,
            column_config={
                "OrdenCompra": st.column_config.TextColumn("Orden"),
                "ArticuloCodigo": st.column_config.TextColumn("Artículo"),
                "ArticuloDescripcion": st.column_config.TextColumn("Descripción"),
                "CantidadPendiente": st.column_config.NumberColumn("Cant.", format="%d"),
                "FechaPuertoBuenosAires": st.column_config.DateColumn("Puerto Bs.As.", format="DD/MM/YYYY"),
                "FechaIngresoEstimada": st.column_config.DateColumn("Estimado", format="DD/MM/YYYY"),
                "FechaConfirmadaIngreso": st.column_config.DateColumn("Confirmado", format="DD/MM/YYYY"),
                "FechaOperativaIngreso": st.column_config.DateColumn("Fecha operativa", format="DD/MM/YYYY"),
                "StockDisponibleActual": st.column_config.NumberColumn("Disponible", format="%d"),
                "PorcentajeSobreTotal": st.column_config.ProgressColumn(
                    "% sobre total", min_value=0, max_value=100, format="%.1f %%"
                ),
                "PorcentajeSobreStockActual": st.column_config.NumberColumn(
                    "% sobre actual", format="%.1f %%"
                ),
                "SemaforoIngreso": st.column_config.TextColumn("Semáforo"),
                "AccionRecomendada": st.column_config.TextColumn("Acción"),
                "VolumenUnitarioM3Original": st.column_config.NumberColumn(
                    "Vol. unitario real",
                    format="%.4f",
                ),
                "VolumenUnitarioPlanificadoM3": st.column_config.NumberColumn(
                    "Vol. unitario usado",
                    format="%.4f",
                ),
                "VolumenTotalM3": st.column_config.NumberColumn(
                    "Vol. planificado m³",
                    format="%.2f",
                ),
                "OrigenVolumetria": st.column_config.TextColumn(
                    "Origen volumetría",
                    width="medium",
                ),
                "EsPiezaRepuesto": st.column_config.CheckboxColumn(
                    "Pieza/Repuesto",
                ),
            },
        )

        st.markdown("---")
        st.markdown(
            "### 📦 Mercadería recibida pendiente de guardar"
        )
        st.caption(
            "Stock ya ingresado al WMS y ubicado en Recepción. "
            "La fecha de alta se estima restando los 2.000 días "
            "de vida estándar a la fecha de vencimiento."
        )

        recepcion_operativa = (
            construir_recepcion_operativa(
                tabla_stock_recepcion,
                tabla_recepcion_agrupada,
            )
        )

        recepcion_operativa = (
            asociar_oc_probable_recepcion(
                recepcion_operativa,
                tabla_pendientes_oc,
            )
        )

        unidades_rec = (
            recepcion_operativa["Unidades"].sum()
            if not recepcion_operativa.empty
            else 0
        )
        contenedores_rec = (
            recepcion_operativa.loc[
                recepcion_operativa[
                    "Contenedor"
                ].ne(""),
                "Contenedor",
            ].nunique()
            if not recepcion_operativa.empty
            else 0
        )
        sku_rec = (
            recepcion_operativa[
                "ArticuloCodigo"
            ].nunique()
            if not recepcion_operativa.empty
            else 0
        )
        volumen_rec = (
            recepcion_operativa[
                "VolumenTotalM3"
            ].sum()
            if not recepcion_operativa.empty
            else 0
        )
        recepciones_abiertas = (
            recepcion_operativa.loc[
                recepcion_operativa[
                    "Ubicacion"
                ].ne(""),
                "Ubicacion",
            ].nunique()
            if not recepcion_operativa.empty
            else 0
        )
        antiguedad_promedio = (
            recepcion_operativa[
                "DiasEnRecepcion"
            ].dropna().mean()
            if not recepcion_operativa.empty
            else 0
        )
        recepciones_demoradas = (
            recepcion_operativa[
                "DiasEnRecepcion"
            ].fillna(0).gt(1).sum()
            if not recepcion_operativa.empty
            else 0
        )
        recepciones_criticas = (
            recepcion_operativa[
                "DiasEnRecepcion"
            ].fillna(0).gt(3).sum()
            if not recepcion_operativa.empty
            else 0
        )

        kpis_recepcion_abierta = [
            (
                "📦 Unidades en Recepción",
                formato_entero(
                    unidades_rec
                ),
                "Mercadería pendiente de guardar",
            ),
            (
                "🧱 Contenedores",
                formato_entero(
                    contenedores_rec
                ),
                "Contenedores únicos activos",
            ),
            (
                "🏷️ SKU",
                formato_entero(
                    sku_rec
                ),
                "Artículos diferentes",
            ),
            (
                "📐 Volumen pendiente",
                _fmt_m3(
                    volumen_rec
                ),
                "Volumen actualmente en Recepción",
            ),
            (
                "🚪 Recepciones abiertas",
                formato_entero(
                    recepciones_abiertas
                ),
                "Ubicaciones únicas actualmente en uso",
            ),
            (
                "⏱️ Antigüedad promedio",
                (
                    f"{antiguedad_promedio:.1f} días"
                    .replace(".", ",")
                ),
                "Desde el alta estimada al WMS",
            ),
            (
                "🟡 Demoradas",
                formato_entero(
                    recepciones_demoradas
                ),
                "Más de 1 día en Recepción",
            ),
            (
                "🔴 Críticas",
                formato_entero(
                    recepciones_criticas
                ),
                "Más de 3 días en Recepción",
            ),
        ]

        html_recepcion_abierta = (
            '<div class="recepcion-kpi-grid">'
        )

        for (
            etiqueta,
            valor,
            detalle,
        ) in kpis_recepcion_abierta:
            html_recepcion_abierta += (
                '<div class="recepcion-kpi-card">'
                f'<div class="recepcion-kpi-label">'
                f'{etiqueta}</div>'
                f'<div class="recepcion-kpi-value">'
                f'{valor}</div>'
                f'<div class="recepcion-kpi-detail">'
                f'{detalle}</div>'
                '</div>'
            )

        html_recepcion_abierta += "</div>"

        st.markdown(
            html_recepcion_abierta,
            unsafe_allow_html=True,
        )

        if recepcion_operativa.empty:
            st.info(
                "No hay stock activo en el área Recepción."
            )
        else:
            st.markdown(
                "#### Lectura visual del pendiente de guardado"
            )

            grafico_antiguedad, grafico_volumen = (
                st.columns(
                    [1, 1],
                    vertical_alignment="top",
                )
            )

            orden_rangos = [
                "0 días",
                "1 día",
                "2 días",
                "3 a 5 días",
                "Más de 5 días",
                "Sin fecha",
            ]

            resumen_antiguedad = (
                recepcion_operativa.groupby(
                    "RangoAntiguedad",
                    as_index=False,
                    dropna=False,
                )
                .agg(
                    Recepciones=(
                        "ClaveRecepcion",
                        "nunique",
                    ),
                    Unidades=(
                        "Unidades",
                        "sum",
                    ),
                    VolumenM3=(
                        "VolumenTotalM3",
                        "sum",
                    ),
                )
            )

            resumen_antiguedad[
                "RangoAntiguedad"
            ] = pd.Categorical(
                resumen_antiguedad[
                    "RangoAntiguedad"
                ],
                categories=orden_rangos,
                ordered=True,
            )

            resumen_antiguedad = (
                resumen_antiguedad.sort_values(
                    "RangoAntiguedad"
                )
            )

            with grafico_antiguedad:
                st.markdown(
                    "##### Recepciones por antigüedad"
                )

                barras_antiguedad = (
                    alt.Chart(
                        resumen_antiguedad
                    )
                    .mark_bar(
                        cornerRadiusTopLeft=5,
                        cornerRadiusTopRight=5,
                        size=30,
                    )
                    .encode(
                        x=alt.X(
                            "RangoAntiguedad:N",
                            title=None,
                            sort=orden_rangos,
                            axis=alt.Axis(
                                labelAngle=0,
                                labelColor="#CBD5E1",
                                grid=False,
                            ),
                        ),
                        y=alt.Y(
                            "Recepciones:Q",
                            title="Recepciones",
                            axis=alt.Axis(
                                tickMinStep=1,
                                gridColor="#26303D",
                                labelColor="#CBD5E1",
                                titleColor="#CBD5E1",
                            ),
                        ),
                        color=alt.Color(
                            "RangoAntiguedad:N",
                            legend=None,
                            scale=alt.Scale(
                                domain=orden_rangos,
                                range=[
                                    "#22C55E",
                                    "#4ADE80",
                                    "#F59E0B",
                                    "#F97316",
                                    "#EF4444",
                                    "#64748B",
                                ],
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "RangoAntiguedad:N",
                                title="Antigüedad",
                            ),
                            alt.Tooltip(
                                "Recepciones:Q",
                                title="Recepciones",
                                format=",.0f",
                            ),
                            alt.Tooltip(
                                "Unidades:Q",
                                title="Unidades",
                                format=",.0f",
                            ),
                        ],
                    )
                )

                etiquetas_antiguedad = (
                    alt.Chart(
                        resumen_antiguedad
                    )
                    .mark_text(
                        dy=-7,
                        color="#F8FAFC",
                        fontSize=11,
                        fontWeight=700,
                    )
                    .encode(
                        x=alt.X(
                            "RangoAntiguedad:N",
                            sort=orden_rangos,
                        ),
                        y="Recepciones:Q",
                        text=alt.Text(
                            "Recepciones:Q",
                            format=",.0f",
                        ),
                    )
                )

                st.altair_chart(
                    (
                        barras_antiguedad
                        + etiquetas_antiguedad
                    )
                    .properties(
                        height=320
                    )
                    .configure_view(
                        strokeOpacity=0
                    ),
                    width="stretch",
                )

            with grafico_volumen:
                st.markdown(
                    "##### Volumen pendiente por antigüedad"
                )

                resumen_antiguedad[
                    "EtiquetaVolumen"
                ] = resumen_antiguedad[
                    "VolumenM3"
                ].map(
                    lambda valor: (
                        f"{float(valor):.2f} m³"
                        .replace(".", ",")
                    )
                )

                barras_volumen = (
                    alt.Chart(
                        resumen_antiguedad
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        size=25,
                        color="#74B9E8",
                    )
                    .encode(
                        x=alt.X(
                            "VolumenM3:Q",
                            title="Volumen m³",
                            axis=alt.Axis(
                                gridColor="#26303D",
                                labelColor="#CBD5E1",
                                titleColor="#CBD5E1",
                            ),
                        ),
                        y=alt.Y(
                            "RangoAntiguedad:N",
                            title=None,
                            sort=orden_rangos,
                            axis=alt.Axis(
                                labelColor="#E2E8F0"
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "RangoAntiguedad:N",
                                title="Antigüedad",
                            ),
                            alt.Tooltip(
                                "VolumenM3:Q",
                                title="Volumen m³",
                                format=".2f",
                            ),
                            alt.Tooltip(
                                "Unidades:Q",
                                title="Unidades",
                                format=",.0f",
                            ),
                        ],
                    )
                )

                etiquetas_volumen = (
                    alt.Chart(
                        resumen_antiguedad
                    )
                    .mark_text(
                        align="left",
                        baseline="middle",
                        dx=7,
                        color="#F8FAFC",
                        fontSize=11,
                        fontWeight=700,
                    )
                    .encode(
                        x="VolumenM3:Q",
                        y=alt.Y(
                            "RangoAntiguedad:N",
                            sort=orden_rangos,
                        ),
                        text="EtiquetaVolumen:N",
                    )
                )

                st.altair_chart(
                    (
                        barras_volumen
                        + etiquetas_volumen
                    )
                    .properties(
                        height=320
                    )
                    .configure_view(
                        strokeOpacity=0
                    ),
                    width="stretch",
                )

            st.markdown(
                "#### Tabla operativa de Recepción"
            )
            st.caption(
                "La OC es una asociación probable construida "
                "por código y cercanía de fechas. No reemplaza "
                "una referencia directa del WMS."
            )

            filtro_1, filtro_2, filtro_3 = (
                st.columns(
                    [2, 1, 1],
                    vertical_alignment="bottom",
                )
            )

            with filtro_1:
                buscar_rec = st.text_input(
                    "Buscar en recepción",
                    key="buscar_recepcion_operativa",
                    placeholder=(
                        "Código, descripción, ubicación, "
                        "contenedor u OC..."
                    ),
                )

            with filtro_2:
                estados_rec = [
                    estado
                    for estado in [
                        "🆕 Recién ingresado",
                        "🟢 En proceso",
                        "🟡 Demorado",
                        "🔴 Crítico",
                        "Sin fecha",
                    ]
                    if estado
                    in recepcion_operativa[
                        "EstadoAntiguedad"
                    ].unique()
                ]

                filtro_estado_rec = st.multiselect(
                    "Estado",
                    estados_rec,
                    key="estado_recepcion_operativa",
                )

            with filtro_3:
                confianza_rec = [
                    confianza
                    for confianza in [
                        "Alta",
                        "Media",
                        "Baja",
                        "Sin coincidencia",
                    ]
                    if confianza
                    in recepcion_operativa[
                        "ConfianzaOC"
                    ].unique()
                ]

                filtro_confianza_rec = (
                    st.multiselect(
                        "Confianza OC",
                        confianza_rec,
                        key=(
                            "confianza_oc_recepcion"
                        ),
                    )
                )

            vista_rec = aplicar_busqueda(
                recepcion_operativa,
                buscar_rec,
            )

            if filtro_estado_rec:
                vista_rec = vista_rec.loc[
                    vista_rec[
                        "EstadoAntiguedad"
                    ].isin(
                        filtro_estado_rec
                    )
                ].copy()

            if filtro_confianza_rec:
                vista_rec = vista_rec.loc[
                    vista_rec[
                        "ConfianzaOC"
                    ].isin(
                        filtro_confianza_rec
                    )
                ].copy()

            descargar, nota = st.columns(
                [1, 4],
                vertical_alignment="center",
            )

            descargar.download_button(
                "⬇️ Descargar recepción operativa",
                data=dataframe_a_csv(
                    vista_rec
                ),
                file_name=(
                    "Recepcion_Pendiente_Guardar.csv"
                ),
                mime="text/csv",
                key=(
                    "descargar_recepcion_operativa"
                ),
                width="stretch",
            )

            nota.caption(
                "El fin de guardado se podrá medir cuando "
                "incorporemos el histórico de capturas."
            )

            columnas_vista_rec = [
                "EstadoAntiguedad",
                "DiasEnRecepcion",
                "Ubicacion",
                "Contenedor",
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "Familia",
                "Sectorizacion",
                "Unidades",
                "VolumenTotalM3",
                "FechaAltaEstimada",
                "FechaVencimiento",
                "Lote",
                "OCProbable",
                "FechaReferenciaOC",
                "DiferenciaDiasOC",
                "ConfianzaOC",
            ]

            columnas_vista_rec = [
                columna
                for columna in columnas_vista_rec
                if columna in vista_rec.columns
            ]

            st.dataframe(
                dataframe_para_streamlit(
                    vista_rec[
                        columnas_vista_rec
                    ]
                ),
                hide_index=True,
                width="stretch",
                height=480,
                column_config={
                    "EstadoAntiguedad":
                        st.column_config.TextColumn(
                            "Estado",
                            width="medium",
                        ),
                    "DiasEnRecepcion":
                        st.column_config.NumberColumn(
                            "Días en Recepción",
                            format="%d",
                        ),
                    "Ubicacion":
                        st.column_config.TextColumn(
                            "Ubicación",
                        ),
                    "Contenedor":
                        st.column_config.TextColumn(
                            "Contenedor",
                        ),
                    "ArticuloCodigo":
                        st.column_config.TextColumn(
                            "Código",
                        ),
                    "ArticuloDescripcion":
                        st.column_config.TextColumn(
                            "Descripción",
                            width="large",
                        ),
                    "Unidades":
                        st.column_config.NumberColumn(
                            "Unidades",
                            format="%.0f",
                        ),
                    "VolumenTotalM3":
                        st.column_config.NumberColumn(
                            "Volumen m³",
                            format="%.3f",
                        ),
                    "FechaAltaEstimada":
                        st.column_config.DateColumn(
                            "Alta estimada WMS",
                            format="DD/MM/YYYY",
                        ),
                    "FechaVencimiento":
                        st.column_config.DateColumn(
                            "Vencimiento",
                            format="DD/MM/YYYY",
                        ),
                    "OCProbable":
                        st.column_config.TextColumn(
                            "OC probable",
                        ),
                    "FechaReferenciaOC":
                        st.column_config.DateColumn(
                            "Fecha OC",
                            format="DD/MM/YYYY",
                        ),
                    "DiferenciaDiasOC":
                        st.column_config.NumberColumn(
                            "Diferencia días",
                            format="%d",
                        ),
                    "ConfianzaOC":
                        st.column_config.TextColumn(
                            "Confianza",
                        ),
                },
            )




    else:
        st.markdown("### 🏭 Stock físico consolidado")
        st.caption(
            "Existencia física consolidada considerando Almacén/Picking y Recepción."
        )
        total_fisico = tabla_stock_total_articulo["StockFisicoTotal"].sum()
        total_almacen = tabla_stock_total_articulo["StockAlmacenPicking"].sum()
        total_recepcion = tabla_stock_total_articulo["StockRecepcion"].sum()
        articulos_stock = tabla_stock_total_articulo.loc[
            tabla_stock_total_articulo["StockFisicoTotal"].gt(0), "ArticuloCodigo"
        ].nunique()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Stock físico total", formato_entero(total_fisico))
        k2.metric("Almacén + Picking", formato_entero(total_almacen))
        k3.metric("Recepción", formato_entero(total_recepcion))
        k4.metric("Artículos con stock", formato_entero(articulos_stock))

        filtro_codigo = st.text_input(
            "Buscar artículo", key="buscar_stock_total_articulo",
            placeholder="Código o descripción...",
        )
        resumen_vista = aplicar_busqueda(tabla_stock_total_articulo, filtro_codigo)
        st.download_button(
            "⬇️ Descargar resumen", data=dataframe_a_csv(resumen_vista),
            file_name="Stock_Fisico_Por_Articulo.csv", mime="text/csv",
            key="descargar_stock_total_articulo",
        )
        st.dataframe(dataframe_para_streamlit(resumen_vista), hide_index=True, width="stretch", height=500)

        with st.expander("🔎 Ver detalle físico unificado"):
            filtro_detalle = st.text_input(
                "Buscar en el detalle físico", key="buscar_stock_total_detallado",
                placeholder="Código, descripción, área, ubicación o contenedor...",
            )
            detalle_vista = aplicar_busqueda(tabla_stock_total_detallado, filtro_detalle)
            st.dataframe(dataframe_para_streamlit(detalle_vista), hide_index=True, width="stretch", height=540)



