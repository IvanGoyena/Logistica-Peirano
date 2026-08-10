from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from utils.inventario.normalizacion import (
    buscar_columna,
    convertir_numero,
    normalizar_codigo,
)
from utils.inventario.ubicaciones import (
    enriquecer_detalle_ubicaciones,
    normalizar_ubicacion,
)


@dataclass(frozen=True)
class ConfiguracionDiagnosticoPreventivo:
    tolerancia_estandar_porcentaje: float = 0.05
    umbral_residual_porcentaje: float = 0.20
    minimo_lineas_estandar: int = 2
    maximo_ubicaciones_sugeridas: int = 5


def obtener_ubicaciones_picking_configuradas(
    dataframe: pd.DataFrame | None,
) -> set[str]:
    """
    Devuelve todas las ubicaciones presentes en Max & Min.

    La pertenencia al archivo de configuración prevalece sobre
    el prefijo físico de la ubicación.
    """

    if dataframe is None or dataframe.empty:
        return set()

    ubicacion = buscar_columna(
        dataframe,
        [
            "Ubicacion",
            "Ubicación",
            "ClaveUbicacion",
        ],
    )

    if not ubicacion:
        return set()

    return {
        normalizar_ubicacion(valor)
        for valor in dataframe[ubicacion]
        if normalizar_ubicacion(valor)
    }


def preparar_configuracion_picking(
    dataframe: pd.DataFrame | None,
    maestro_ubicaciones: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Normaliza Max & Min y consolida capacidades por artículo.

    El archivo puede tener varias ubicaciones para el mismo código.
    Solo se consideran ubicaciones clasificadas como Picking.
    """

    columnas_salida = [
        "ArticuloCodigo",
        "PickingMinimoConfigurado",
        "PickingMaximoConfigurado",
        "UnidadesMinimasAPickear",
        "UnidadesMaximasAPickear",
        "CantidadUbicacionesPickingConfiguradas",
    ]

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=columnas_salida)

    codigo = buscar_columna(
        dataframe,
        [
            "Codigo",
            "Código",
            "ArticuloCodigo",
            "CodigoArticulo",
        ],
    )
    ubicacion = buscar_columna(
        dataframe,
        [
            "Ubicacion",
            "Ubicación",
            "ClaveUbicacion",
        ],
    )

    if not codigo or not ubicacion:
        return pd.DataFrame(columns=columnas_salida)

    stock_minimo = buscar_columna(
        dataframe,
        [
            "StockMinimo",
            "Stock Minimo",
            "Mínimo",
            "Minimo",
        ],
    )
    stock_maximo = buscar_columna(
        dataframe,
        [
            "StockMaximo",
            "Stock Maximo",
            "Máximo",
            "Maximo",
        ],
    )
    unidades_minimas = buscar_columna(
        dataframe,
        [
            "UnidadesMinimasAPickear",
            "Unidades Minimas A Pickear",
        ],
    )
    unidades_maximas = buscar_columna(
        dataframe,
        [
            "UnidadesMaximasAPickear",
            "Unidades Maximas A Pickear",
        ],
    )

    salida = pd.DataFrame({
        "ArticuloCodigo": normalizar_codigo(
            dataframe[codigo]
        ),
        "Ubicacion": (
            dataframe[ubicacion]
            .map(normalizar_ubicacion)
        ),
        "PickingMinimoConfigurado": (
            convertir_numero(dataframe[stock_minimo])
            if stock_minimo
            else 0.0
        ),
        "PickingMaximoConfigurado": (
            convertir_numero(dataframe[stock_maximo])
            if stock_maximo
            else 0.0
        ),
        "UnidadesMinimasAPickear": (
            convertir_numero(dataframe[unidades_minimas])
            if unidades_minimas
            else 0.0
        ),
        "UnidadesMaximasAPickear": (
            convertir_numero(dataframe[unidades_maximas])
            if unidades_maximas
            else 0.0
        ),
    })

    ubicaciones_picking = (
        obtener_ubicaciones_picking_configuradas(
            dataframe
        )
    )

    salida = enriquecer_detalle_ubicaciones(
        salida,
        maestro_ubicaciones,
        ubicaciones_picking=(
            ubicaciones_picking
        ),
    )

    salida = salida.loc[
        salida["ArticuloCodigo"].ne("")
        & salida["TipoUbicacion"].eq("Picking")
    ].copy()

    if salida.empty:
        return pd.DataFrame(columns=columnas_salida)

    return (
        salida.groupby(
            "ArticuloCodigo",
            as_index=False,
        )
        .agg(
            PickingMinimoConfigurado=(
                "PickingMinimoConfigurado",
                "sum",
            ),
            PickingMaximoConfigurado=(
                "PickingMaximoConfigurado",
                "sum",
            ),
            UnidadesMinimasAPickear=(
                "UnidadesMinimasAPickear",
                "sum",
            ),
            UnidadesMaximasAPickear=(
                "UnidadesMaximasAPickear",
                "sum",
            ),
            CantidadUbicacionesPickingConfiguradas=(
                "Ubicacion",
                "nunique",
            ),
        )
    )


def _inferir_estandar(
    cantidades: Iterable[float],
    config: ConfiguracionDiagnosticoPreventivo,
) -> tuple[float, float, int, str]:
    """
    Infiere el pallet estándar por agrupación de cantidades cercanas.

    Se evita el promedio. Para cada cantidad observada se calcula
    cuántas líneas caen dentro de ±5%. Se elige el candidato con
    mayor soporte y, ante empate, el de mayor cantidad.
    """

    valores = pd.Series(
        list(cantidades),
        dtype="float64",
    )
    valores = valores.loc[
        valores.notna() & valores.gt(0)
    ].round(6)

    if valores.empty:
        return 0.0, 0.0, 0, "Sin datos"

    if len(valores) == 1:
        return (
            float(valores.iloc[0]),
            1.0,
            1,
            "Baja",
        )

    mejor_candidato = 0.0
    mejor_soporte = -1
    mejor_desvio = float("inf")

    for candidato in sorted(
        valores.unique(),
        reverse=True,
    ):
        tolerancia = max(
            1.0,
            abs(float(candidato))
            * config.tolerancia_estandar_porcentaje,
        )
        cercanos = valores.loc[
            (valores - candidato).abs()
            <= tolerancia
        ]

        soporte = len(cercanos)
        desvio = float(
            (cercanos - candidato).abs().mean()
        ) if soporte else float("inf")

        if (
            soporte > mejor_soporte
            or (
                soporte == mejor_soporte
                and desvio < mejor_desvio
            )
            or (
                soporte == mejor_soporte
                and np.isclose(
                    desvio,
                    mejor_desvio,
                )
                and candidato > mejor_candidato
            )
        ):
            mejor_candidato = float(candidato)
            mejor_soporte = soporte
            mejor_desvio = desvio

    confianza = (
        mejor_soporte / len(valores)
        if len(valores)
        else 0.0
    )

    if mejor_soporte >= 3 and confianza >= 0.50:
        nivel = "Alta"
    elif mejor_soporte >= 2:
        nivel = "Media"
    else:
        nivel = "Baja"

    return (
        mejor_candidato,
        float(confianza),
        int(mejor_soporte),
        nivel,
    )


def _clasificar_lineas_almacen(
    detalle: pd.DataFrame,
    estandares: pd.DataFrame,
    config: ConfiguracionDiagnosticoPreventivo,
) -> pd.DataFrame:
    salida = detalle.merge(
        estandares[
            [
                "ArticuloCodigo",
                "PalletEstandarInferido",
            ]
        ],
        on="ArticuloCodigo",
        how="left",
    )

    salida["PalletEstandarInferido"] = (
        pd.to_numeric(
            salida["PalletEstandarInferido"],
            errors="coerce",
        ).fillna(0.0)
    )
    salida["Cantidad"] = pd.to_numeric(
        salida["Cantidad"],
        errors="coerce",
    ).fillna(0.0)

    estandar = salida[
        "PalletEstandarInferido"
    ]
    cantidad = salida["Cantidad"]

    porcentaje = cantidad.div(
        estandar.where(estandar.gt(0))
    )

    salida["PorcentajeDelEstandar"] = (
        porcentaje.mul(100).fillna(0)
    )

    salida["ClasificacionContenedor"] = (
        "Sin estándar"
    )

    tiene_estandar = estandar.gt(0)

    salida.loc[
        tiene_estandar
        & porcentaje.le(
            config.umbral_residual_porcentaje
        ),
        "ClasificacionContenedor",
    ] = "Residual"

    salida.loc[
        tiene_estandar
        & porcentaje.gt(
            config.umbral_residual_porcentaje
        )
        & porcentaje.lt(
            1
            - config.tolerancia_estandar_porcentaje
        ),
        "ClasificacionContenedor",
    ] = "Parcial"

    salida.loc[
        tiene_estandar
        & porcentaje.between(
            1
            - config.tolerancia_estandar_porcentaje,
            1
            + config.tolerancia_estandar_porcentaje,
        ),
        "ClasificacionContenedor",
    ] = "Completo"

    salida.loc[
        tiene_estandar
        & porcentaje.gt(
            1
            + config.tolerancia_estandar_porcentaje
        ),
        "ClasificacionContenedor",
    ] = "Sobre estándar"

    return salida


def _descripcion_ubicacion(
    fila: pd.Series,
) -> str:
    ubicacion = str(
        fila.get("Ubicacion", "")
    ).strip()
    cantidad = float(
        fila.get("Cantidad", 0) or 0
    )
    clasificacion = str(
        fila.get(
            "ClasificacionContenedor",
            "",
        )
    ).strip()

    return (
        f"{ubicacion} ({cantidad:,.0f} u. · "
        f"{clasificacion})"
    ).replace(",", ".")


def _seleccionar_ubicaciones(
    grupo: pd.DataFrame,
    *,
    diferencia_absoluta: float,
    maximo: int,
) -> str:
    if grupo.empty:
        return ""

    prioridad = {
        "Sobre estándar": 0,
        "Residual": 1,
        "Parcial": 2,
        "Sin estándar": 3,
        "Completo": 4,
    }

    salida = grupo.copy()
    salida["_PrioridadClase"] = (
        salida["ClasificacionContenedor"]
        .map(prioridad)
        .fillna(5)
    )
    salida["_CercaniaDiferencia"] = (
        salida["Cantidad"]
        .sub(diferencia_absoluta)
        .abs()
    )

    salida = salida.sort_values(
        [
            "_PrioridadClase",
            "_CercaniaDiferencia",
            "Cantidad",
        ],
        ascending=[
            True,
            True,
            False,
        ],
    )

    return " | ".join(
        salida.head(maximo)
        .apply(
            _descripcion_ubicacion,
            axis=1,
        )
        .tolist()
    )


def construir_diagnostico_preventivo(
    tabla_conciliacion: pd.DataFrame,
    detalle_ubicaciones: pd.DataFrame,
    *,
    maestro_ubicaciones: pd.DataFrame | None = None,
    configuracion_picking: pd.DataFrame | None = None,
    configuracion: ConfiguracionDiagnosticoPreventivo | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Construye diagnóstico inicial antes de realizar un conteo.

    Retorna:
    - tabla de conciliación enriquecida;
    - detalle enriquecido y clasificado.
    """

    config = (
        configuracion
        or ConfiguracionDiagnosticoPreventivo()
    )

    tabla = tabla_conciliacion.copy()
    ubicaciones_picking = (
        obtener_ubicaciones_picking_configuradas(
            configuracion_picking
        )
    )

    detalle = enriquecer_detalle_ubicaciones(
        detalle_ubicaciones,
        maestro_ubicaciones,
        ubicaciones_picking=(
            ubicaciones_picking
        ),
    )

    if detalle.empty:
        return tabla, detalle

    detalle["Cantidad"] = pd.to_numeric(
        detalle["Cantidad"],
        errors="coerce",
    ).fillna(0.0)

    almacen = detalle.loc[
        detalle["TipoUbicacion"].eq("Almacén")
        & detalle["Cantidad"].gt(0)
    ].copy()

    estandares_registros = []

    for articulo, grupo in almacen.groupby(
        "ArticuloCodigo"
    ):
        (
            estandar,
            confianza,
            soporte,
            nivel,
        ) = _inferir_estandar(
            grupo["Cantidad"],
            config,
        )

        estandares_registros.append({
            "ArticuloCodigo": articulo,
            "PalletEstandarInferido": estandar,
            "ConfianzaEstandar": (
                confianza * 100
            ),
            "SoporteEstandar": soporte,
            "NivelConfianzaEstandar": nivel,
        })

    estandares = pd.DataFrame(
        estandares_registros,
        columns=[
            "ArticuloCodigo",
            "PalletEstandarInferido",
            "ConfianzaEstandar",
            "SoporteEstandar",
            "NivelConfianzaEstandar",
        ],
    )

    if estandares.empty:
        estandares = pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "PalletEstandarInferido",
                "ConfianzaEstandar",
                "SoporteEstandar",
                "NivelConfianzaEstandar",
            ]
        )

    detalle = _clasificar_lineas_almacen(
        detalle,
        estandares,
        config,
    )

    resumen_tipo = (
        detalle.groupby(
            [
                "ArticuloCodigo",
                "TipoUbicacion",
            ],
            as_index=False,
        )
        .agg(
            StockTipo=("Cantidad", "sum"),
            UbicacionesTipo=(
                "Ubicacion",
                "nunique",
            ),
            ContenedoresTipo=(
                "Contenedor",
                lambda serie: int(
                    serie.astype(str)
                    .str.strip()
                    .replace("", pd.NA)
                    .dropna()
                    .nunique()
                ),
            ),
        )
    )

    stock_pivot = resumen_tipo.pivot(
        index="ArticuloCodigo",
        columns="TipoUbicacion",
        values="StockTipo",
    ).fillna(0)

    ubicaciones_pivot = resumen_tipo.pivot(
        index="ArticuloCodigo",
        columns="TipoUbicacion",
        values="UbicacionesTipo",
    ).fillna(0)

    resumen = pd.DataFrame(
        index=sorted(
            detalle[
                "ArticuloCodigo"
            ].dropna().astype(str).unique()
        )
    )
    resumen.index.name = "ArticuloCodigo"

    for tipo, destino in {
        "Picking": "StockPicking",
        "Almacén": "StockAlmacen",
        "Recepción": "StockRecepcionDetalle",
    }.items():
        resumen[destino] = (
            stock_pivot[tipo]
            if tipo in stock_pivot.columns
            else 0.0
        )

    for tipo, destino in {
        "Picking": "UbicacionesPicking",
        "Almacén": "UbicacionesAlmacen",
        "Recepción": "UbicacionesRecepcion",
    }.items():
        resumen[destino] = (
            ubicaciones_pivot[tipo]
            if tipo in ubicaciones_pivot.columns
            else 0.0
        )

    resumen = resumen.reset_index()

    if not estandares.empty:
        resumen = resumen.merge(
            estandares,
            on="ArticuloCodigo",
            how="left",
        )

    almacen_clasificado = detalle.loc[
        detalle["TipoUbicacion"].eq("Almacén")
    ]

    if not almacen_clasificado.empty:
        conteos_clase = (
            almacen_clasificado.pivot_table(
                index="ArticuloCodigo",
                columns="ClasificacionContenedor",
                values="Ubicacion",
                aggfunc="count",
                fill_value=0,
            )
            .reset_index()
        )

        conteos_clase = conteos_clase.rename(
            columns={
                "Completo": "PalletsCompletos",
                "Parcial": "PalletsParciales",
                "Residual": "ContenedoresResiduales",
                "Sobre estándar": "ContenedoresSobreEstandar",
                "Sin estándar": "ContenedoresSinEstandar",
            }
        )

        resumen = resumen.merge(
            conteos_clase,
            on="ArticuloCodigo",
            how="left",
        )

    picking = detalle.loc[
        detalle["TipoUbicacion"].eq("Picking")
    ]

    sugerencias_picking = (
        picking.groupby(
            "ArticuloCodigo"
        )
        .apply(
            lambda grupo: " | ".join(
                grupo.sort_values(
                    "Cantidad",
                    ascending=False,
                )
                .head(
                    config.maximo_ubicaciones_sugeridas
                )
                .apply(
                    lambda fila: (
                        f"{fila['Ubicacion']} "
                        f"({fila['Cantidad']:,.0f} u.)"
                    ).replace(",", "."),
                    axis=1,
                )
                .tolist()
            ),
            include_groups=False,
        )
        .rename("UbicacionesPickingSugeridas")
        .reset_index()
        if not picking.empty
        else pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "UbicacionesPickingSugeridas",
            ]
        )
    )

    sugerencias_almacen = []

    diferencia_por_articulo = (
        tabla.set_index(
            "ArticuloCodigo"
        )["DiferenciaAbsoluta"]
        .to_dict()
        if "DiferenciaAbsoluta" in tabla.columns
        else {}
    )

    for articulo, grupo in almacen_clasificado.groupby(
        "ArticuloCodigo"
    ):
        sugerencias_almacen.append({
            "ArticuloCodigo": articulo,
            "UbicacionesAlmacenSugeridas": (
                _seleccionar_ubicaciones(
                    grupo,
                    diferencia_absoluta=float(
                        diferencia_por_articulo.get(
                            articulo,
                            0,
                        )
                    ),
                    maximo=(
                        config.maximo_ubicaciones_sugeridas
                    ),
                )
            ),
        })

    sugerencias_almacen_df = pd.DataFrame(
        sugerencias_almacen,
        columns=[
            "ArticuloCodigo",
            "UbicacionesAlmacenSugeridas",
        ],
    )

    resumen = resumen.merge(
        sugerencias_picking,
        on="ArticuloCodigo",
        how="left",
    )
    resumen = resumen.merge(
        sugerencias_almacen_df,
        on="ArticuloCodigo",
        how="left",
    )

    picking_config = preparar_configuracion_picking(
        configuracion_picking,
        maestro_ubicaciones,
    )

    if not picking_config.empty:
        resumen = resumen.merge(
            picking_config,
            on="ArticuloCodigo",
            how="left",
        )

    tabla = tabla.merge(
        resumen,
        on="ArticuloCodigo",
        how="left",
    )

    columnas_cero = [
        "StockPicking",
        "StockAlmacen",
        "StockRecepcionDetalle",
        "UbicacionesPicking",
        "UbicacionesAlmacen",
        "UbicacionesRecepcion",
        "PalletEstandarInferido",
        "ConfianzaEstandar",
        "SoporteEstandar",
        "PalletsCompletos",
        "PalletsParciales",
        "ContenedoresResiduales",
        "ContenedoresSobreEstandar",
        "ContenedoresSinEstandar",
        "PickingMinimoConfigurado",
        "PickingMaximoConfigurado",
        "UnidadesMinimasAPickear",
        "UnidadesMaximasAPickear",
        "CantidadUbicacionesPickingConfiguradas",
    ]

    for columna in columnas_cero:
        if columna not in tabla.columns:
            tabla[columna] = 0.0

        tabla[columna] = pd.to_numeric(
            tabla[columna],
            errors="coerce",
        ).fillna(0.0)

    for columna in [
        "NivelConfianzaEstandar",
        "UbicacionesPickingSugeridas",
        "UbicacionesAlmacenSugeridas",
    ]:
        if columna not in tabla.columns:
            tabla[columna] = ""

        tabla[columna] = (
            tabla[columna]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    tabla["PickingSobreMaximo"] = (
        tabla["PickingMaximoConfigurado"].gt(0)
        & tabla["StockPicking"].gt(
            tabla["PickingMaximoConfigurado"]
        )
    )
    tabla["PickingBajoMinimo"] = (
        tabla["PickingMinimoConfigurado"].gt(0)
        & tabla["StockPicking"].lt(
            tabla["PickingMinimoConfigurado"]
        )
    )

    tabla["FragmentacionAlmacen"] = (
        tabla["PalletsParciales"]
        + tabla["ContenedoresResiduales"]
    )

    tabla["ScoreRiesgoPreventivo"] = 0.0

    max_diferencia = max(
        float(
            tabla[
                "DiferenciaAbsoluta"
            ].max()
        ),
        1.0,
    )

    tabla["ScoreRiesgoPreventivo"] += (
        tabla["DiferenciaAbsoluta"]
        .div(max_diferencia)
        .mul(30)
        .clip(0, 30)
    )
    tabla["ScoreRiesgoPreventivo"] += (
        tabla["ContenedoresSobreEstandar"]
        .clip(0, 2)
        .mul(10)
    )
    tabla["ScoreRiesgoPreventivo"] += (
        tabla["ContenedoresResiduales"]
        .clip(0, 3)
        .mul(5)
    )
    tabla["ScoreRiesgoPreventivo"] += (
        tabla["PalletsParciales"]
        .clip(0, 3)
        .mul(4)
    )
    tabla["ScoreRiesgoPreventivo"] += (
        tabla["PickingSobreMaximo"]
        .astype(int)
        .mul(12)
    )
    tabla["ScoreRiesgoPreventivo"] += (
        tabla["UbicacionesAlmacen"]
        .sub(3)
        .clip(lower=0, upper=5)
        .mul(2)
    )

    tabla["ScoreRiesgoPreventivo"] = (
        tabla["ScoreRiesgoPreventivo"]
        .clip(0, 100)
        .round(1)
    )

    tabla["OrigenProbableInicial"] = (
        "Sin diagnóstico"
    )
    tabla["DiagnosticoInicial"] = (
        "Distribución sin alertas relevantes."
    )
    tabla["AccionInicialSugerida"] = (
        "Sin acción preventiva."
    )
    tabla["TipoConteoSugerido"] = "General"
    tabla["UbicacionesSugeridas"] = ""

    for indice, fila in tabla.iterrows():
        diferencia = float(
            fila.get(
                "DiferenciaERPvsWMS",
                0,
            )
        )
        diferencia_abs = abs(diferencia)

        stock_picking = float(
            fila.get("StockPicking", 0)
        )
        max_picking = float(
            fila.get(
                "PickingMaximoConfigurado",
                0,
            )
        )

        sobre_estandar = int(
            fila.get(
                "ContenedoresSobreEstandar",
                0,
            )
        )
        residuales = int(
            fila.get(
                "ContenedoresResiduales",
                0,
            )
        )
        parciales = int(
            fila.get(
                "PalletsParciales",
                0,
            )
        )

        variabilidad_almacen = (
            sobre_estandar
            + residuales
            + parciales
        )

        picking_excedido = bool(
            max_picking > 0
            and stock_picking > max_picking
        )

        if np.isclose(diferencia_abs, 0):
            if picking_excedido:
                tabla.at[
                    indice,
                    "OrigenProbableInicial",
                ] = "Picking"
                tabla.at[
                    indice,
                    "DiagnosticoInicial",
                ] = (
                    "ERP y WMS coinciden, pero Picking "
                    "supera el máximo configurado."
                )
                tabla.at[
                    indice,
                    "AccionInicialSugerida",
                ] = (
                    "Revisar Picking por posible exceso "
                    "de reposición o movimiento duplicado."
                )
                tabla.at[
                    indice,
                    "TipoConteoSugerido",
                ] = "Picking"

            elif variabilidad_almacen > 0:
                tabla.at[
                    indice,
                    "OrigenProbableInicial",
                ] = "Distribución WMS"
                tabla.at[
                    indice,
                    "DiagnosticoInicial",
                ] = (
                    "ERP y WMS coinciden, pero Almacén "
                    "presenta cantidades fuera del patrón "
                    "estadístico."
                )
                tabla.at[
                    indice,
                    "AccionInicialSugerida",
                ] = (
                    "Realizar control preventivo sobre "
                    "contenedores atípicos de Almacén."
                )
                tabla.at[
                    indice,
                    "TipoConteoSugerido",
                ] = "Almacén"

            else:
                tabla.at[
                    indice,
                    "OrigenProbableInicial",
                ] = "Conciliado"
                tabla.at[
                    indice,
                    "DiagnosticoInicial",
                ] = (
                    "ERP y WMS coinciden y la distribución "
                    "no presenta anomalías relevantes."
                )
                tabla.at[
                    indice,
                    "AccionInicialSugerida",
                ] = "Sin acción inmediata."
                tabla.at[
                    indice,
                    "TipoConteoSugerido",
                ] = "Sin conteo"

        elif picking_excedido:
            tabla.at[
                indice,
                "OrigenProbableInicial",
            ] = "Picking"
            tabla.at[
                indice,
                "DiagnosticoInicial",
            ] = (
                "Picking supera el máximo configurado "
                "y puede contener una reposición duplicada "
                "o un movimiento incorrecto."
            )
            tabla.at[
                indice,
                "AccionInicialSugerida",
            ] = (
                "Contar y revisar primero las ubicaciones "
                "de Picking excedidas."
            )
            tabla.at[
                indice,
                "TipoConteoSugerido",
            ] = "Picking"

        elif sobre_estandar > 0:
            tabla.at[
                indice,
                "OrigenProbableInicial",
            ] = "Almacén"
            tabla.at[
                indice,
                "DiagnosticoInicial",
            ] = (
                f"Se detectaron {sobre_estandar} contenedores "
                "de Almacén por encima del estándar inferido."
            )
            tabla.at[
                indice,
                "AccionInicialSugerida",
            ] = (
                "Contar primero los contenedores sobre "
                "estándar y validar sus movimientos."
            )
            tabla.at[
                indice,
                "TipoConteoSugerido",
            ] = "Almacén"

        elif residuales > 0 or parciales > 0:
            tabla.at[
                indice,
                "OrigenProbableInicial",
            ] = "Almacén"
            tabla.at[
                indice,
                "DiagnosticoInicial",
            ] = (
                "La distribución de Almacén presenta "
                f"{parciales} pallets parciales y "
                f"{residuales} remanentes."
            )
            tabla.at[
                indice,
                "AccionInicialSugerida",
            ] = (
                "Contar primero pallets parciales y "
                "remanentes, antes que pallets completos."
            )
            tabla.at[
                indice,
                "TipoConteoSugerido",
            ] = "Almacén"

        else:
            tabla.at[
                indice,
                "OrigenProbableInicial",
            ] = "ERP / Sin patrón físico"
            tabla.at[
                indice,
                "DiagnosticoInicial",
            ] = (
                "Existe diferencia ERP–WMS, pero Picking "
                "no está excedido y Almacén no presenta "
                "una anomalía estadística concluyente."
            )
            tabla.at[
                indice,
                "AccionInicialSugerida",
            ] = (
                "Validar una muestra de Almacén y, si el "
                "físico coincide con WMS, corregir el ERP."
            )
            tabla.at[
                indice,
                "TipoConteoSugerido",
            ] = "Almacén"

        tipo = tabla.at[
            indice,
            "TipoConteoSugerido",
        ]

        if tipo == "Picking":
            sugeridas = fila.get(
                "UbicacionesPickingSugeridas",
                "",
            )
        elif tipo == "Almacén":
            sugeridas = fila.get(
                "UbicacionesAlmacenSugeridas",
                "",
            )
        else:
            sugeridas = ""

        tabla.at[
            indice,
            "UbicacionesSugeridas",
        ] = sugeridas

    tabla = tabla.sort_values(
        [
            "ScoreRiesgoPreventivo",
            "DiferenciaAbsoluta",
        ],
        ascending=False,
    ).reset_index(drop=True)

    return tabla, detalle
