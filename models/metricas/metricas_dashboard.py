from __future__ import annotations

import numpy as np
import pandas as pd

def preparar_base_analitica(
    tareas_enriquecidas: pd.DataFrame,
    detalle_enriquecido: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Deja lista la base operativa una sola vez.

    Las normalizaciones de sectorización y fecha ya no se
    repiten cada vez que el usuario cambia un filtro o una
    pestaña del dashboard.
    """

    tareas = tareas_enriquecidas.copy()
    detalle = detalle_enriquecido.copy()

    # Los registros sin clasificación deben conservarse: forman parte de la
    # actividad real y no pueden desaparecer de los KPI. Los vacíos se
    # identifican con categorías de control para que puedan filtrarse y
    # corregirse posteriormente en el Maestro de Artículos.
    categorias_tareas = {
        "FamiliaPrincipal": "SIN FAMILIA",
        "Familia2Principal": "SIN FAMILIA 2",
        "SectorizacionPrincipal": "SIN SECTORIZACIÓN",
        "RubroPrincipal": "SIN RUBRO",
        "OrigenPrincipal": "SIN ORIGEN",
        "MarcaPrincipal": "SIN MARCA",
        "GamaPrincipal": "SIN GAMA",
    }

    for columna, etiqueta in categorias_tareas.items():
        if columna not in tareas.columns:
            tareas[columna] = etiqueta
        tareas[columna] = (
            tareas[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", etiqueta)
        )

    categorias_detalle = {
        "FamiliaFinal": "SIN FAMILIA",
        "Familia2": "SIN FAMILIA 2",
        "Sectorizacion": "SIN SECTORIZACIÓN",
        "Rubro": "SIN RUBRO",
        "Origen": "SIN ORIGEN",
        "Marca": "SIN MARCA",
        "Gama": "SIN GAMA",
    }

    for columna, etiqueta in categorias_detalle.items():
        if columna not in detalle.columns:
            detalle[columna] = etiqueta
        detalle[columna] = (
            detalle[columna]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", etiqueta)
        )

    tareas["Fecha"] = pd.to_datetime(
        tareas["Fecha"],
        errors="coerce",
    )

    # Tipos numéricos utilizados repetidamente por los KPIs
    # y gráficos. Convertirlos aquí evita repetir coerciones.
    columnas_numericas_tareas = [
        "TiempoRealSegundos",
        "UnidadesAnalisis",
        "LineasDetalle",
        "VolumenTotalM3",
        "PesoTotalKg",
    ]

    for columna in columnas_numericas_tareas:
        if columna in tareas.columns:
            tareas[columna] = pd.to_numeric(
                tareas[columna],
                errors="coerce",
            ).fillna(0)

    columnas_numericas_detalle = [
        "UnidadesDetalle",
        "VolumenLineaM3",
        "PesoLineaKg",
    ]

    for columna in columnas_numericas_detalle:
        if columna in detalle.columns:
            detalle[columna] = pd.to_numeric(
                detalle[columna],
                errors="coerce",
            ).fillna(0)

    return tareas, detalle


def calcular_variacion(
    actual: float,
    anterior: float,
):

    if pd.isna(anterior) or anterior == 0:
        return None

    return (
        (actual - anterior)
        / abs(anterior)
        * 100
    )


def metricas_periodo(
    tareas: pd.DataFrame,
) -> dict:

    if tareas.empty:

        return {
            "Tareas": 0,
            "Unidades": 0,
            "Lineas": 0,
            "VolumenM3": 0,
            "PesoKg": 0,
            "Horas": 0,
            "UnidadesHora": 0,
            "UsuariosActivos": 0,
            "PromedioUnidadesLinea": 0,
        }

    horas = (
        pd.to_numeric(
            tareas["TiempoRealSegundos"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
        / 3600
    )

    unidades = (
        pd.to_numeric(
            tareas["UnidadesAnalisis"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    lineas = (
        pd.to_numeric(
            tareas["LineasDetalle"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    # ======================================================
    # USUARIOS ACTIVOS
    # ======================================================
    #
    # Un usuario se considera activo cuando las horas
    # registradas en tareas representan más del 60 % de las
    # horas de turno de los días en que tuvo actividad.
    #
    # Turnos utilizados:
    # - Lunes a viernes: 9 horas.
    # - Sábado: 6 horas.
    # - Domingo: no se computa.
    #
    # El usuario se identifica por UsuarioId y, cuando falta,
    # por el nombre estandarizado.
    # ======================================================

    base_usuarios = tareas.copy()

    usuario_id = (
        base_usuarios["UsuarioId"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            r"\\.0$",
            "",
            regex=True,
        )
    )

    usuario_nombre = (
        base_usuarios["Usuario"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    base_usuarios["ClaveUsuario"] = usuario_id.where(
        usuario_id.ne(""),
        "NOMBRE|" + usuario_nombre,
    )

    base_usuarios["FechaActividad"] = pd.to_datetime(
        base_usuarios["Fecha"],
        errors="coerce",
    ).dt.normalize()

    base_usuarios["HorasTarea"] = (
        pd.to_numeric(
            base_usuarios["TiempoRealSegundos"],
            errors="coerce",
        )
        .fillna(0)
        / 3600
    )

    base_usuarios["DiaSemanaNumero"] = (
        base_usuarios["FechaActividad"].dt.dayofweek
    )

    base_usuarios["HorasTurnoDia"] = np.select(
        [
            base_usuarios[
                "DiaSemanaNumero"
            ].between(0, 4),
            base_usuarios[
                "DiaSemanaNumero"
            ].eq(5),
        ],
        [
            9.0,
            6.0,
        ],
        default=0.0,
    )

    base_usuarios = base_usuarios[
        base_usuarios["ClaveUsuario"].ne("")
        & base_usuarios["ClaveUsuario"].ne(
            "NOMBRE|"
        )
        & base_usuarios["FechaActividad"].notna()
        & base_usuarios["HorasTurnoDia"].gt(0)
    ].copy()

    if base_usuarios.empty:

        usuarios_activos = 0

    else:

        # Primero consolidar todas las tareas de una persona
        # dentro del mismo día.
        usuarios_por_dia = (
            base_usuarios
            .groupby(
                [
                    "ClaveUsuario",
                    "FechaActividad",
                ],
                as_index=False,
            )
            .agg(
                HorasTarea=(
                    "HorasTarea",
                    "sum",
                ),
                HorasTurnoDia=(
                    "HorasTurnoDia",
                    "first",
                ),
            )
        )

        # Luego evaluar el porcentaje acumulado del período.
        usuarios_periodo = (
            usuarios_por_dia
            .groupby(
                "ClaveUsuario",
                as_index=False,
            )
            .agg(
                HorasTarea=(
                    "HorasTarea",
                    "sum",
                ),
                HorasTurno=(
                    "HorasTurnoDia",
                    "sum",
                ),
            )
        )

        usuarios_periodo["OcupacionTareasPct"] = (
            usuarios_periodo["HorasTarea"]
            / usuarios_periodo[
                "HorasTurno"
            ].replace(
                0,
                np.nan,
            )
            * 100
        )

        usuarios_activos = int(
            usuarios_periodo[
                "OcupacionTareasPct"
            ].gt(30)
            .sum()
        )

    return {
        "Tareas": tareas["ClaveTarea"].nunique(),
        "Unidades": unidades,
        "Lineas": lineas,
        "UsuariosActivos": usuarios_activos,
        "PromedioUnidadesLinea": (
            unidades / lineas
            if lineas > 0
            else 0
        ),
        "VolumenM3": (
            pd.to_numeric(
                tareas["VolumenTotalM3"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        ),
        "PesoKg": (
            pd.to_numeric(
                tareas["PesoTotalKg"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        ),
        "Horas": horas,
        "UnidadesHora": (
            unidades / horas
            if horas > 0
            else 0
        ),
    }


def aplicar_filtros(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
    fecha_desde,
    fecha_hasta,
    procesos,
    familias,
    sectorizaciones,
    usuarios,
    tipos,
):

    tareas_filtradas = tareas.copy()

    tareas_filtradas["Fecha"] = pd.to_datetime(
        tareas_filtradas["Fecha"],
        errors="coerce",
    )

    tareas_filtradas = tareas_filtradas[
        tareas_filtradas["Fecha"].between(
            pd.Timestamp(fecha_desde),
            pd.Timestamp(fecha_hasta),
            inclusive="both",
        )
    ]

    if procesos:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Proceso"].isin(
                procesos
            )
        ]

    if familias:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas[
                "FamiliaPrincipal"
            ].fillna("").isin(
                familias
            )
        ]

    if sectorizaciones:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas[
                "SectorizacionPrincipal"
            ].fillna("").isin(
                sectorizaciones
            )
        ]

    if usuarios:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Usuario"].isin(
                usuarios
            )
        ]

    if tipos:

        tareas_filtradas = tareas_filtradas[
            tareas_filtradas["Tipo"].isin(
                tipos
            )
        ]

    claves = set(
        tareas_filtradas["ClaveTarea"]
        .dropna()
        .astype(str)
    )

    detalle_filtrado = detalle[
        detalle["ClaveTarea"]
        .astype(str)
        .isin(claves)
    ].copy()

    return tareas_filtradas, detalle_filtrado


def construir_insights(
    tareas: pd.DataFrame,
    detalle: pd.DataFrame,
    indicadores_actuales: dict,
    indicadores_anteriores: dict,
) -> list[dict]:

    insights = []

    variacion_productividad = calcular_variacion(
        indicadores_actuales["UnidadesHora"],
        indicadores_anteriores["UnidadesHora"],
    )

    if variacion_productividad is not None:

        direccion = (
            "aumentó"
            if variacion_productividad >= 0
            else "disminuyó"
        )

        insights.append(
            {
                "tipo": (
                    "positivo"
                    if variacion_productividad >= 0
                    else "alerta"
                ),
                "titulo": "Productividad",
                "texto": (
                    f"La productividad {direccion} "
                    f"{abs(variacion_productividad):.1f}% "
                    "frente al período anterior."
                ),
            }
        )

    if not tareas.empty:

        familia = (
            tareas
            .groupby(
                "FamiliaPrincipal",
                dropna=False,
            )["UnidadesAnalisis"]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        if not familia.empty:

            nombre_familia = str(
                familia.index[0]
            )

            unidades_familia = float(
                familia.iloc[0]
            )

            participacion = (
                unidades_familia
                / max(
                    indicadores_actuales["Unidades"],
                    1,
                )
                * 100
            )

            insights.append(
                {
                    "tipo": "informativo",
                    "titulo": "Familia dominante",
                    "texto": (
                        f"{nombre_familia} concentra "
                        f"{participacion:.1f}% de las unidades "
                        "del período."
                    ),
                }
            )

        productividad_dia = (
            tareas
            .groupby(
                "DiaSemana",
                as_index=False,
            )
            .agg(
                Unidades=("UnidadesAnalisis", "sum"),
                Segundos=(
                    "TiempoRealSegundos",
                    "sum",
                ),
            )
        )

        productividad_dia["UnidadesHora"] = (
            productividad_dia["Unidades"]
            / (
                productividad_dia["Segundos"]
                / 3600
            ).replace(
                0,
                np.nan,
            )
        )

        productividad_dia = (
            productividad_dia
            .dropna(
                subset=["UnidadesHora"]
            )
            .sort_values(
                "UnidadesHora"
            )
        )

        if not productividad_dia.empty:

            peor = productividad_dia.iloc[0]

            insights.append(
                {
                    "tipo": "alerta",
                    "titulo": "Día de menor rendimiento",
                    "texto": (
                        f"{peor['DiaSemana']} presenta la "
                        f"menor productividad: "
                        f"{peor['UnidadesHora']:.1f} unidades/hora."
                    ),
                }
            )

    if not detalle.empty:

        top_articulo = (
            detalle
            .groupby(
                [
                    "CodigoArticulo",
                    "DescripcionFinal",
                ],
                as_index=False,
            )["UnidadesDetalle"]
            .sum()
            .sort_values(
                "UnidadesDetalle",
                ascending=False,
            )
        )

        if not top_articulo.empty:

            fila = top_articulo.iloc[0]

            insights.append(
                {
                    "tipo": "informativo",
                    "titulo": "Artículo más movilizado",
                    "texto": (
                        f"{fila['CodigoArticulo']} — "
                        f"{fila['DescripcionFinal']} lidera con "
                        f"{fila['UnidadesDetalle']:,.0f} unidades."
                    ),
                }
            )

    return insights[:5]
