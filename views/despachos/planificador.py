from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from models.despachos.planificacion import (
    construir_resumen_clientes_planificacion,
    asignar_camionetas,
    asignar_camioneta_a_pedidos,
)
from utils.cola_agrupaciones import crear_orden_agrupacion, obtener_orden


def render_planificador_despachos(
    *,
    tabla: pd.DataFrame,
    tabla_filtrada: pd.DataFrame,
    tabla_disponible_planificacion: pd.DataFrame,
    mascara_sin_preparacion: pd.Series,
    pedidos_bloqueados_gestion: set[str],
    pedidos_por_tipo_gestion: dict[str, set[str]],
) -> None:
    # =====================================================

    AGRUPADORES_DIGIP = {
        "LUNES": [
            "CAMIONETA LUN 1",
            "CAMIONETA LUN 2",
            "CAMIONETA LUN 3",
            "CAMIONETA LUN 4",
        ],
        "MARTES": [
            "CAMIONETA MAR 1",
            "CAMIONETA MAR 2",
            "CAMIONETA MAR 3",
        ],
        "MIERCOLES": [
            "CAMIONETA MIE 1",
            "CAMIONETA MIE 2",
            "CAMIONETA MIE 3"
            "CAMIONETA MIE 4",
        ],
        "JUEVES": [
            "CAMIONETA JUE 1",
            "CAMIONETA JUE 2",
            "CAMIONETA JUE 3",
        ],
        "VIERNES": [
            "CAMIONETA VIE 1",
            "CAMIONETA VIE 2",
            "CAMIONETA VIE 3",
        ],
        "DIARIOS": [
            "CAMIONETA DIARIOS 1",
        ],
        "RETIRA": [
            "RETIRA",
        ],
        "EXPRESOS": [
            "CAMIONETA EXP 1",
            "CAMIONETA EXP 2",
            "CAMIONETA EXP 3",
            "CAMIONETA EXP 4",
            "CAMIONETA EXP 5",
            "CAMIONETA EXP 6",
        ],
    }


    PLANIFICACIONES_SEMANALES = {
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "JUEVES",
        "VIERNES",
        "DIARIOS",
        "RETIRA",
    }


    def normalizar_planificacion(
        valor: object
    ) -> str:
        return (
            str(valor)
            .strip()
            .upper()
        )


    def obtener_pool_agrupador(
        planificacion: object
    ) -> str:
        """
        Las planificaciones semanales usan su propio pool.
        Todas las demás planificaciones operativas se consideran
        expresos: CABA SUR, CABA SUR II, CABA NORTE, etc.
        """

        planificacion_normalizada = (
            normalizar_planificacion(
                planificacion
            )
        )

        if (
            planificacion_normalizada
            in PLANIFICACIONES_SEMANALES
        ):
            return planificacion_normalizada

        return "EXPRESOS"


    def obtener_agrupadores_ocupados(
        tabla_pedidos: pd.DataFrame
    ) -> set[str]:
        """
        Considera ocupado un agrupador cuando existe al menos
        un pedido con PreparacionID no vacío y su descripción
        coincide con alguno de los agrupadores configurados.
        """

        columnas_requeridas = {
            "PreparacionID",
            "DespachoDescripcion",
        }

        if not columnas_requeridas.issubset(
            tabla_pedidos.columns
        ):
            return set()

        nombres_validos = {
            nombre
            for agrupadores in (
                AGRUPADORES_DIGIP.values()
            )
            for nombre in agrupadores
        }

        preparacion_activa = (
            tabla_pedidos["PreparacionID"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )

        despachos = (
            tabla_pedidos.loc[
                preparacion_activa,
                "DespachoDescripcion"
            ]
            .fillna("")
            .astype(str)
            .str.upper()
            .str.strip()
        )

        return {
            despacho
            for despacho in despachos.tolist()
            if despacho in nombres_validos
        }


    def asignar_agrupadores_disponibles(
        asignacion: pd.DataFrame,
        agrupadores_ocupados: set[str],
    ) -> pd.DataFrame:
        """
        Asigna nombres reales de agrupadores DIGIP.

        - LUNES usa CAMIONETA LUN N.
        - MARTES usa CAMIONETA MAR N.
        - etc.
        - CABA SUR, CABA NORTE y demás zonas comparten
          CAMIONETA EXP N.
        """

        if asignacion.empty:
            return asignacion.copy()

        resultado = asignacion.copy()

        resultado["PoolAgrupador"] = (
            resultado["Planificacion"]
            .apply(obtener_pool_agrupador)
        )

        vehiculos_logicos = (
            resultado[
                [
                    "PoolAgrupador",
                    "Planificacion",
                    "NumeroCamioneta",
                ]
            ]
            .drop_duplicates()
            .sort_values(
                by=[
                    "PoolAgrupador",
                    "Planificacion",
                    "NumeroCamioneta",
                ]
            )
            .reset_index(drop=True)
        )

        asignaciones_reales = []

        for pool, bloque in (
            vehiculos_logicos.groupby(
                "PoolAgrupador",
                sort=False
            )
        ):
            disponibles = [
                nombre
                for nombre in AGRUPADORES_DIGIP[
                    pool
                ]
                if nombre not in agrupadores_ocupados
            ]

            cantidad_necesaria = len(bloque)

            cantidad_faltante = max(
                cantidad_necesaria - len(disponibles),
                0
            )

            agrupadores_nuevos = []

            if cantidad_faltante > 0:

                numeros_existentes = []

                for nombre in AGRUPADORES_DIGIP[pool]:

                    coincidencia = re.search(
                        r"(\d+)$",
                        str(nombre).strip()
                    )

                    if coincidencia:
                        numeros_existentes.append(
                            int(coincidencia.group(1))
                        )

                siguiente_numero = (
                    max(numeros_existentes) + 1
                    if numeros_existentes
                    else 1
                )

                for numero in range(
                    siguiente_numero,
                    siguiente_numero
                    + cantidad_faltante
                ):

                    if pool == "EXPRESOS":
                        nombre_nuevo = (
                            f"CAMIONETA EXP {numero}"
                        )

                    elif pool == "LUNES":
                        nombre_nuevo = (
                            f"CAMIONETA LUN {numero}"
                        )

                    elif pool == "MARTES":
                        nombre_nuevo = (
                            f"CAMIONETA MAR {numero}"
                        )

                    elif pool == "MIERCOLES":
                        nombre_nuevo = (
                            f"CAMIONETA MIE {numero}"
                        )

                    elif pool == "JUEVES":
                        nombre_nuevo = (
                            f"CAMIONETA JUE {numero}"
                        )

                    elif pool == "VIERNES":
                        nombre_nuevo = (
                            f"CAMIONETA VIE {numero}"
                        )

                    elif pool == "DIARIOS":
                        nombre_nuevo = (
                            f"CAMIONETA DIARIOS {numero}"
                        )

                    else:
                        nombre_nuevo = (
                            f"CAMIONETA {pool} {numero}"
                        )

                    agrupadores_nuevos.append(
                        nombre_nuevo
                    )

                disponibles.extend(
                    agrupadores_nuevos
                )

            bloque = bloque.copy()

            bloque["DespachoDIGIP"] = (
                disponibles[:cantidad_necesaria]
            )

            bloque["AgrupadorNuevo"] = (
                bloque["DespachoDIGIP"].isin(
                    agrupadores_nuevos
                )
            )

            asignaciones_reales.append(bloque)

        mapa_agrupadores = pd.concat(
            asignaciones_reales,
            ignore_index=True
        )

        resultado = resultado.merge(
            mapa_agrupadores,
            on=[
                "PoolAgrupador",
                "Planificacion",
                "NumeroCamioneta",
            ],
            how="left",
            validate="many_to_one",
        )

        resultado[
            "NumeroCamionetaLogica"
        ] = resultado["NumeroCamioneta"]

        # El número visible normalmente se extrae del nombre real
        # del agrupador, por ejemplo "CAMIONETA LUN 2" -> 2.
        #
        # RETIRA es una excepción porque el agrupador se llama
        # simplemente "RETIRA" y no termina en un número. En ese caso
        # conservamos el número lógico generado por el planificador.
        numero_desde_despacho = pd.to_numeric(
            resultado["DespachoDIGIP"]
            .fillna("")
            .astype(str)
            .str.extract(
                r"(\d+)$",
                expand=False
            ),
            errors="coerce",
        )

        numero_logico = pd.to_numeric(
            resultado["NumeroCamionetaLogica"],
            errors="coerce",
        )

        resultado["NumeroCamioneta"] = (
            numero_desde_despacho
            .fillna(numero_logico)
            .fillna(1)
            .astype(int)
        )

        resultado["Camioneta"] = (
            resultado["Planificacion"]
            .astype(str)
            .str.strip()
            + " - "
            + resultado["DespachoDIGIP"]
        )

        return resultado



    # =====================================================
    # PLANIFICACIÓN DE CAMIONETAS
    # =====================================================

    st.markdown("---")

    st.subheader("🚚 Planificación de Camionetas")

    st.caption(
        "Asignación propuesta respetando planificación, "
        "antigüedad y cliente completo."
    )

    pedidos_excluidos_preparacion = int(
        tabla_filtrada.loc[
            ~mascara_sin_preparacion,
            "Pedido",
        ].nunique()
    )

    if pedidos_excluidos_preparacion:
        st.info(
            f"{pedidos_excluidos_preparacion} pedido(s) con preparación "
            "asignada se excluyen automáticamente del planificador.",
            icon="🚫",
        )

    if pedidos_bloqueados_gestion:

        detalle_bloqueos = " · ".join(
            f"{tipo}: {len(pedidos)}"
            for tipo, pedidos in pedidos_por_tipo_gestion.items()
            if pedidos
        )

        st.warning(
            (
                f"Hay {len(pedidos_bloqueados_gestion)} pedidos "
                "bloqueados para planificación porque tienen una "
                "gestión comercial abierta. "
                f"{detalle_bloqueos}"
            ),
            icon="🔒",
        )


    # =====================================================
    # FORMULARIO DE CONFIGURACIÓN
    # =====================================================

    with st.form(
        key="formulario_planificacion_camionetas",
        clear_on_submit=False
    ):

        col_plan1, col_plan2 = st.columns(
            [1, 1]
        )

        with col_plan1:

            capacidad_camioneta = st.number_input(
                "Capacidad por camioneta (m³)",
                min_value=0.1,
                value=8.0,
                step=0.5,
                format="%.1f"
            )

        with col_plan2:

            opciones_planificacion_camionetas = sorted(
                tabla_disponible_planificacion["Planificacion"]
                .dropna()
                .astype(str)
                .loc[
                    lambda serie:
                    serie.str.strip().ne("")
                ]
                .unique()
                .tolist()
            )

            planificaciones_camionetas = st.multiselect(
                "Planificaciones a procesar",
                options=opciones_planificacion_camionetas,
                default=[],
                placeholder="Seleccionar planificaciones..."
            )

        generar_planificacion = st.form_submit_button(
            "🚚 Generar propuesta de camionetas",
            type="primary",
            width="stretch"
        )


    # =====================================================
    # GENERAR PLANIFICACIÓN
    # =====================================================

    if generar_planificacion:

        if not planificaciones_camionetas:
            st.warning(
                "Seleccioná al menos una planificación para generar "
                "la propuesta de camionetas."
            )
            st.stop()

        base_planificacion = tabla_disponible_planificacion.copy()

        # Los pedidos con cualquier gestión comercial abierta
        # requieren revisión y no pueden asignarse a camionetas.
        if pedidos_bloqueados_gestion:

            base_planificacion["Pedido"] = (
                base_planificacion["Pedido"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.replace(r"\.0$", "", regex=True)
            )

            base_planificacion = base_planificacion[
                ~base_planificacion["Pedido"].isin(
                    pedidos_bloqueados_gestion
                )
            ].copy()

        if planificaciones_camionetas:

            base_planificacion = base_planificacion[
                base_planificacion["Planificacion"].isin(
                    planificaciones_camionetas
                )
            ].copy()

        if base_planificacion.empty:

            st.warning(
                "No quedaron pedidos disponibles para planificar. "
                "Los pedidos seleccionados ya tienen una preparación, "
                "poseen una gestión comercial abierta o fueron excluidos."
            )

            st.stop()

        resumen_clientes = (
            construir_resumen_clientes_planificacion(
                base_planificacion
            )
        )

        # Control de integridad: todos los pedidos seleccionados deben
        # quedar representados en el resumen que alimenta el motor.
        pedidos_base_planificador = set(
            base_planificacion["Pedido"]
            .fillna("")
            .astype(str)
            .str.strip()
            .loc[lambda serie: serie.ne("")]
            .tolist()
        )

        pedidos_resumen_planificador = set()

        if not resumen_clientes.empty and "Pedidos" in resumen_clientes.columns:
            for valor in resumen_clientes["Pedidos"].fillna("").astype(str):
                pedidos_resumen_planificador.update(
                    pedido.strip()
                    for pedido in valor.split("|")
                    if pedido.strip()
                )

        pedidos_no_incorporados = sorted(
            pedidos_base_planificador
            - pedidos_resumen_planificador
        )

        if pedidos_no_incorporados:
            st.error(
                "El motor no pudo incorporar "
                f"{len(pedidos_no_incorporados)} pedido(s). "
                "Se muestran abajo para corregir sus datos maestros.",
                icon="⚠️",
            )

            columnas_control = [
                columna
                for columna in [
                    "Pedido",
                    "ClienteCodigo",
                    "ClienteDescripcion",
                    "Planificacion",
                    "CodigoDespacho",
                    "ZonaExpreso",
                    "FrecuenciaEntrega",
                    "TotalUnidades",
                    "TotalM3",
                ]
                if columna in base_planificacion.columns
            ]

            with st.expander(
                "Ver pedidos no incorporados",
                expanded=False,
            ):
                st.dataframe(
                    base_planificacion.loc[
                        base_planificacion["Pedido"].isin(
                            pedidos_no_incorporados
                        ),
                        columnas_control,
                    ],
                    width="stretch",
                    hide_index=True,
                )

            st.warning(
                "La propuesta continuará con los pedidos que sí pudieron "
                "incorporarse. Los pedidos del control no se asignarán "
                "hasta corregir su dato faltante.",
                icon="ℹ️",
            )

        if resumen_clientes.empty:
            st.error(
                "No se pudo construir ninguna carga con los pedidos "
                "seleccionados. Revisá el control de datos mostrado arriba.",
                icon="⚠️",
            )
            st.stop()

        asignacion_logica = asignar_camionetas(
            resumen_clientes,
            capacidad_camioneta
        )

        agrupadores_ocupados = (
            obtener_agrupadores_ocupados(
                tabla
            )
        )

        try:

            asignacion_camionetas = (
                asignar_agrupadores_disponibles(
                    asignacion=asignacion_logica,
                    agrupadores_ocupados=(
                        agrupadores_ocupados
                    ),
                )
            )

        except ValueError as error:

            st.error(str(error))
            st.stop()

        agrupadores_a_crear = []

        if (
            not asignacion_camionetas.empty
            and "AgrupadorNuevo"
            in asignacion_camionetas.columns
        ):

            agrupadores_a_crear = sorted(
                asignacion_camionetas.loc[
                    asignacion_camionetas[
                        "AgrupadorNuevo"
                    ],
                    "DespachoDIGIP"
                ]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        st.session_state[
            "agrupadores_a_crear"
        ] = agrupadores_a_crear

        pedidos_planificados = asignar_camioneta_a_pedidos(
            base_planificacion,
            asignacion_camionetas
        )

        st.session_state[
            "asignacion_camionetas"
        ] = asignacion_camionetas

        st.session_state[
            "pedidos_planificados"
        ] = pedidos_planificados

        st.session_state[
            "capacidad_camioneta"
        ] = capacidad_camioneta

        st.session_state[
            "agrupadores_ocupados"
        ] = sorted(
            agrupadores_ocupados
        )


    # =====================================================
    # VALIDAR VERSIÓN DE LA PLANIFICACIÓN GUARDADA
    # =====================================================

    COLUMNAS_PLANIFICACION_ACTUAL = {
        "DespachoDIGIP",
        "PoolAgrupador",
    }

    asignacion_guardada = st.session_state.get(
        "asignacion_camionetas"
    )

    if (
        isinstance(
            asignacion_guardada,
            pd.DataFrame
        )
        and not asignacion_guardada.empty
        and not COLUMNAS_PLANIFICACION_ACTUAL.issubset(
            asignacion_guardada.columns
        )
    ):

        # La propuesta fue creada con una versión anterior
        # del módulo y no contiene los agrupadores reales.
        claves_planificacion_anterior = [
            "asignacion_camionetas",
            "pedidos_planificados",
            "capacidad_camioneta",
            "agrupadores_ocupados",
        ]

        for clave in claves_planificacion_anterior:
            st.session_state.pop(
                clave,
                None
            )

        claves_ejecucion_anterior = [
            clave
            for clave in list(
                st.session_state.keys()
            )
            if str(clave).startswith(
                "resultado_digip_"
            )
        ]

        for clave in claves_ejecucion_anterior:
            st.session_state.pop(
                clave,
                None
            )

        st.warning(
            "La planificación guardada pertenecía a una versión "
            "anterior. Fue eliminada para incorporar los nombres "
            "reales de los agrupadores DIGIP. Generá nuevamente "
            "la propuesta."
        )


    # =====================================================
    # MOSTRAR RESULTADO GUARDADO
    # =====================================================

    if (
        "asignacion_camionetas"
        in st.session_state
    ):

        asignacion_camionetas = st.session_state[
            "asignacion_camionetas"
        ]

        if asignacion_camionetas.empty:

            st.warning(
                "No existen pedidos disponibles para generar "
                "la planificación."
            )

        else:

            agrupadores_a_crear = (
                st.session_state.get(
                    "agrupadores_a_crear",
                    []
                )
            )

            if agrupadores_a_crear:

                st.warning(
                    "La propuesta utiliza agrupadores que todavía "
                    "no existen en DIGIP: "
                    + ", ".join(agrupadores_a_crear)
                    + ". Podés continuar con la planificación y "
                    "crearlos antes de ejecutar."
                )

            capacidad_utilizada = st.session_state.get(
                "capacidad_camioneta",
                0
            )

            resumen_camionetas = (
                asignacion_camionetas[
                    [
                        "Planificacion",
                        "NumeroCamioneta",
                        "Camioneta",
                        "DespachoDIGIP",
                        "PoolAgrupador",
                        "CapacidadM3",
                        "VolumenCamionetaM3",
                        "OcupacionCamionetaPct",
                        "DisponibleM3",
                        "ClientesCamioneta",
                        "PedidosCamioneta",
                        "UnidadesCamioneta",
                        "EstadoCapacidad",
                    ]
                ]
                .drop_duplicates(
                    subset=[
                        "Planificacion",
                        "NumeroCamioneta",
                    ]
                )
                .sort_values(
                    by=[
                        "Planificacion",
                        "NumeroCamioneta",
                    ]
                )
            )

            total_camionetas = len(
                resumen_camionetas
            )

            total_clientes_planificados = (
                asignacion_camionetas[
                    "ClienteCodigo"
                ].nunique()
            )

            total_pedidos_planificados = int(
                asignacion_camionetas[
                    "CantidadPedidos"
                ].sum()
            )

            volumen_planificado = float(
                asignacion_camionetas[
                    "TotalM3"
                ].sum()
            )

            ocupacion_promedio = float(
                resumen_camionetas[
                    "OcupacionCamionetaPct"
                ].mean()
            )

            # -------------------------------------------------
            # DISPONIBILIDAD DE AGRUPADORES
            # -------------------------------------------------

            agrupadores_ocupados_guardados = set(
                st.session_state.get(
                    "agrupadores_ocupados",
                    []
                )
            )

            agrupadores_asignados = sorted(
                resumen_camionetas[
                    "DespachoDIGIP"
                ]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

            todos_los_agrupadores = [
                nombre
                for lista in AGRUPADORES_DIGIP.values()
                for nombre in lista
            ]

            agrupadores_libres_restantes = [
                nombre
                for nombre in todos_los_agrupadores
                if (
                    nombre
                    not in agrupadores_ocupados_guardados
                    and nombre
                    not in set(
                        agrupadores_asignados
                    )
                )
            ]

            with st.expander(
                "🚦 Disponibilidad de agrupadores DIGIP",
                expanded=False
            ):

                disp_col1, disp_col2, disp_col3 = (
                    st.columns(3)
                )

                with disp_col1:
                    st.metric(
                        "Ocupados",
                        len(
                            agrupadores_ocupados_guardados
                        )
                    )

                    st.caption(
                        ", ".join(
                            sorted(
                                agrupadores_ocupados_guardados
                            )
                        )
                        or "Ninguno"
                    )

                with disp_col2:
                    st.metric(
                        "Asignados a la propuesta",
                        len(agrupadores_asignados)
                    )

                    st.caption(
                        ", ".join(
                            agrupadores_asignados
                        )
                        or "Ninguno"
                    )

                with disp_col3:
                    st.metric(
                        "Libres restantes",
                        len(
                            agrupadores_libres_restantes
                        )
                    )

                    st.caption(
                        ", ".join(
                            agrupadores_libres_restantes
                        )
                        or "Ninguno"
                    )

            # -------------------------------------------------
            # KPIs DE PLANIFICACIÓN
            # -------------------------------------------------

            plan_kpi1, plan_kpi2, plan_kpi3, plan_kpi4, plan_kpi5 = (
                st.columns(5)
            )

            with plan_kpi1:

                st.metric(
                    "🚚 Camionetas",
                    total_camionetas
                )

            with plan_kpi2:

                st.metric(
                    "👥 Clientes",
                    total_clientes_planificados
                )

            with plan_kpi3:

                st.metric(
                    "📦 Pedidos",
                    total_pedidos_planificados
                )

            with plan_kpi4:

                st.metric(
                    "📐 Volumen",
                    f"{volumen_planificado:,.3f} m³"
                    .replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )

            with plan_kpi5:

                st.metric(
                    "📊 Ocupación promedio",
                    f"{ocupacion_promedio:.1f}%"
                )

            # -------------------------------------------------
            # RESUMEN DE CAMIONETAS
            # -------------------------------------------------

            st.markdown("#### Resumen de cargas")

            st.dataframe(
                resumen_camionetas,
                width="stretch",
                hide_index=True,
                column_config={

                    "CapacidadM3": (
                        st.column_config.NumberColumn(
                            "Capacidad m³",
                            format="%.2f"
                        )
                    ),

                    "VolumenCamionetaM3": (
                        st.column_config.NumberColumn(
                            "Volumen asignado",
                            format="%.3f"
                        )
                    ),

                    "OcupacionCamionetaPct": (
                        st.column_config.ProgressColumn(
                            "Ocupación",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%"
                        )
                    ),

                    "DisponibleM3": (
                        st.column_config.NumberColumn(
                            "Disponible m³",
                            format="%.3f"
                        )
                    ),
                }
            )

            # -------------------------------------------------
            # EJECUCIÓN DIGIP
            # -------------------------------------------------

            st.markdown("#### 🚀 Ejecución DIGIP")

            st.caption(
                "Revisá el resumen y ejecutá únicamente la "
                "camioneta que quieras crear en DIGIP."
            )

            pedidos_planificados = st.session_state.get(
                "pedidos_planificados",
                pd.DataFrame()
            )

            # Estilo compacto del panel
            st.markdown(
                """
                <style>
                div[data-testid="stHorizontalBlock"] {
                    gap: 0.65rem;
                }

                div[data-testid="stButton"] > button {
                    min-height: 2.15rem;
                    padding-top: 0.25rem;
                    padding-bottom: 0.25rem;
                }

                div[data-testid="stAlert"] {
                    padding-top: 0.45rem;
                    padding-bottom: 0.45rem;
                    min-height: 2.15rem;
                }

                .digip-fila {
                    padding: 0.18rem 0;
                    line-height: 1.15;
                }

                .digip-nombre {
                    font-weight: 600;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }

                .digip-numero {
                    text-align: center;
                    font-weight: 600;
                }

                .digip-volumen {
                    text-align: right;
                    white-space: nowrap;
                }
                </style>
                """,
                unsafe_allow_html=True
            )

            # Encabezados
            encabezado_1, encabezado_2, encabezado_3, \
                encabezado_4, encabezado_5 = st.columns(
                    [3.2, 0.75, 1.05, 1.35, 1.15],
                    vertical_alignment="center"
                )

            with encabezado_1:
                st.caption("**Camioneta**")

            with encabezado_2:
                st.caption("**Pedidos**")

            with encabezado_3:
                st.caption("**Volumen**")

            with encabezado_4:
                st.caption("**Estado DIGIP**")

            with encabezado_5:
                st.caption("**Acción**")

            st.divider()

            for _, fila_camioneta in resumen_camionetas.iterrows():

                planificacion_fila = str(
                    fila_camioneta["Planificacion"]
                ).strip()

                numero_camioneta = int(
                    fila_camioneta["NumeroCamioneta"]
                )

                nombre_camioneta = str(
                    fila_camioneta["Camioneta"]
                ).strip()

                volumen_camioneta = float(
                    fila_camioneta["VolumenCamionetaM3"]
                )

                clave_ejecucion = (
                    f"{planificacion_fila}_"
                    f"{numero_camioneta}"
                )

                pedidos_camioneta = (
                    pedidos_planificados[
                        (
                            pedidos_planificados[
                                "Planificacion"
                            ].astype(str).str.strip()
                            == planificacion_fila
                        )
                        &
                        (
                            pd.to_numeric(
                                pedidos_planificados[
                                    "NumeroCamioneta"
                                ],
                                errors="coerce"
                            )
                            == numero_camioneta
                        )
                    ]
                    .copy()
                )

                lista_pedidos = (
                    pedidos_camioneta["Pedido"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.replace(
                        r"\.0$",
                        "",
                        regex=True
                    )
                    .loc[lambda serie: serie.ne("")]
                    .drop_duplicates()
                    .tolist()
                )

                codigos_despacho = (
                    pedidos_camioneta["CodigoDespacho"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.replace(
                        r"\.0$",
                        "",
                        regex=True
                    )
                    .loc[lambda serie: serie.ne("")]
                    .drop_duplicates()
                    .tolist()
                )

                codigo_despacho = (
                    codigos_despacho[0]
                    if codigos_despacho
                    else ""
                )

                usar_filtro_codigo_despacho = (
                    len(codigos_despacho) == 1
                )

                # RETIRA se agrupa por listado de pedidos, sin importar
                # el CodigoDespacho de cada registro.
                es_camioneta_retira = (
                    normalizar_planificacion(planificacion_fila) == "RETIRA"
                )

                if es_camioneta_retira:
                    codigo_despacho = ""
                    codigos_despacho = []
                    usar_filtro_codigo_despacho = False

                despacho_digip = str(
                    fila_camioneta[
                        "DespachoDIGIP"
                    ]
                ).strip()

                ejecucion_valida = bool(
                    lista_pedidos
                )

                clave_resultado_actual = (
                    f"resultado_digip_{clave_ejecucion}"
                )

                estado_guardado = st.session_state.get(
                    clave_resultado_actual
                )

                # Antes de dibujar la fila, sincroniza el estado
                # guardado con la orden real de Google Sheets.
                if (
                    estado_guardado
                    and estado_guardado.get("orden_id")
                ):

                    orden_sincronizada = obtener_orden(
                        estado_guardado["orden_id"]
                    )

                    if orden_sincronizada:

                        estado_worker = str(
                            orden_sincronizada.get(
                                "Estado",
                                "",
                            )
                        ).strip().upper()

                        mensaje_worker = str(
                            orden_sincronizada.get(
                                "Mensaje",
                                "",
                            )
                        ).strip()

                        etapa_worker = str(
                            orden_sincronizada.get(
                                "Etapa",
                                "",
                            )
                        ).strip()

                        if estado_worker == "COMPLETADA":

                            estado_guardado = {
                                "exito": True,
                                "pendiente": False,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        elif estado_worker == "ERROR":

                            estado_guardado = {
                                "exito": False,
                                "pendiente": False,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        else:

                            estado_guardado = {
                                "exito": False,
                                "pendiente": True,
                                "orden_id": orden_sincronizada.get(
                                    "OrdenID"
                                ),
                                "mensaje": mensaje_worker,
                                "etapa": etapa_worker,
                                "estado_worker": estado_worker,
                            }

                        st.session_state[
                            clave_resultado_actual
                        ] = estado_guardado

                fila_1, fila_2, fila_3, fila_4, fila_5 = (
                    st.columns(
                        [3.2, 0.75, 1.05, 1.35, 1.15],
                        vertical_alignment="center"
                    )
                )

                with fila_1:
                    st.markdown(
                        (
                            '<div class="digip-fila digip-nombre">'
                            f'🚚 {nombre_camioneta}'
                            '</div>'
                        ),
                        unsafe_allow_html=True
                    )

                with fila_2:
                    st.markdown(
                        (
                            '<div class="digip-fila digip-numero">'
                            f'{len(lista_pedidos)}'
                            '</div>'
                        ),
                        unsafe_allow_html=True
                    )

                with fila_3:
                    volumen_formateado = (
                        f"{volumen_camioneta:,.3f} m³"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", ".")
                    )

                    st.markdown(
                        (
                            '<div class="digip-fila digip-volumen">'
                            f'{volumen_formateado}'
                            '</div>'
                        ),
                        unsafe_allow_html=True
                    )

                with fila_4:

                    if len(codigos_despacho) > 1:

                        st.info(
                            f"{len(codigos_despacho)} códigos",
                            icon="ℹ️"
                        )

                        st.caption(
                            "Códigos encontrados: "
                            + ", ".join(codigos_despacho)
                        )

                    elif not codigo_despacho:
                        st.warning(
                            "Sin código",
                            icon="⚠️"
                        )

                    elif estado_guardado:

                        if bool(
                            estado_guardado.get(
                                "exito",
                                False
                            )
                        ):
                            st.success(
                                "Ejecutada",
                                icon="✅"
                            )

                        elif bool(
                            estado_guardado.get(
                                "pendiente",
                                False
                            )
                        ):
                            st.info(
                                "En proceso",
                                icon="⚙️"
                            )

                        else:
                            st.error(
                                "Error",
                                icon="❌"
                            )

                    else:
                        st.info(
                            "Pendiente",
                            icon="⏳"
                        )

                with fila_5:

                    texto_boton = (
                        "🔄 Reintentar"
                        if (
                            estado_guardado
                            and not bool(
                                estado_guardado.get(
                                    "exito",
                                    False
                                )
                            )
                            and not bool(
                                estado_guardado.get(
                                    "pendiente",
                                    False
                                )
                            )
                        )
                        else (
                            "✅ Ejecutada"
                            if (
                                estado_guardado
                                and bool(
                                    estado_guardado.get(
                                        "exito",
                                        False
                                    )
                                )
                            )
                            else "🚀 Ejecutar"
                        )
                    )

                    ejecutar = st.button(
                        texto_boton,
                        key=(
                            f"ejecutar_digip_"
                            f"{clave_ejecucion}"
                        ),
                        width="stretch",
                        type="primary",
                        disabled=bool(
                            (not ejecucion_valida)
                            or (
                                bool(estado_guardado)
                                and bool(
                                    estado_guardado.get(
                                        "exito",
                                        False
                                    )
                                )
                            )
                        )
                    )

                # -------------------------------------------------
                # DETALLE EXPANDIBLE DE LA CAMIONETA
                # -------------------------------------------------

                with st.expander(
                    f"🔎 Abrir detalle · {nombre_camioneta}",
                    expanded=False,
                ):

                    detalle_camioneta = pedidos_camioneta.copy()

                    # Una fila por pedido para evitar duplicaciones
                    # en los indicadores y en la tabla visible.
                    if "Pedido" in detalle_camioneta.columns:
                        detalle_camioneta = (
                            detalle_camioneta
                            .drop_duplicates(
                                subset=["Pedido"],
                                keep="first",
                            )
                            .reset_index(drop=True)
                        )

                    cantidad_clientes_detalle = (
                        detalle_camioneta["ClienteCodigo"].nunique()
                        if "ClienteCodigo" in detalle_camioneta.columns
                        else 0
                    )

                    cantidad_pedidos_detalle = (
                        detalle_camioneta["Pedido"].nunique()
                        if "Pedido" in detalle_camioneta.columns
                        else len(detalle_camioneta)
                    )

                    total_unidades_detalle = int(
                        pd.to_numeric(
                            detalle_camioneta.get(
                                "TotalUnidades",
                                pd.Series(dtype=float),
                            ),
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    )

                    total_m3_detalle = float(
                        pd.to_numeric(
                            detalle_camioneta.get(
                                "TotalM3",
                                pd.Series(dtype=float),
                            ),
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    )

                    detalle_kpi_1, detalle_kpi_2, \
                        detalle_kpi_3, detalle_kpi_4 = st.columns(4)

                    detalle_kpi_1.metric(
                        "👥 Clientes",
                        cantidad_clientes_detalle,
                    )

                    detalle_kpi_2.metric(
                        "📦 Pedidos",
                        cantidad_pedidos_detalle,
                    )

                    detalle_kpi_3.metric(
                        "🔢 Unidades",
                        f"{total_unidades_detalle:,}".replace(",", "."),
                    )

                    detalle_kpi_4.metric(
                        "📐 Volumen",
                        f"{total_m3_detalle:,.3f} m³"
                        .replace(",", "X")
                        .replace(".", ",")
                        .replace("X", "."),
                    )

                    columnas_detalle_preferidas = [
                        "Pedido",
                        "FechaTransmisionERP",
                        "ClienteCodigo",
                        "ClienteDescripcion",
                        "TotalUnidades",
                        "TotalM3",
                        "TotalSKUs",
                        "DetalleFamilias",
                        "CodigoDespacho",
                        "DespachoDescripcion",
                        "Planificacion",
                    ]

                    columnas_detalle_disponibles = [
                        columna
                        for columna in columnas_detalle_preferidas
                        if columna in detalle_camioneta.columns
                    ]

                    tabla_detalle_camioneta = detalle_camioneta[
                        columnas_detalle_disponibles
                    ].copy()

                    tabla_detalle_camioneta = (
                        tabla_detalle_camioneta.rename(
                            columns={
                                "ClienteCodigo": "Código cliente",
                                "ClienteDescripcion": "Cliente",
                                "TotalUnidades": "Unidades",
                                "TotalM3": "Volumen m³",
                                "TotalSKUs": "SKUs",
                                "DetalleFamilias": "Familias",
                                "CodigoDespacho": "Código despacho",
                                "DespachoDescripcion": "Despacho actual",
                                "Planificacion": "Planificación",
                            }
                        )
                    )

                    st.dataframe(
                        tabla_detalle_camioneta,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Volumen m³": st.column_config.NumberColumn(
                                "Volumen m³",
                                format="%.3f",
                            ),
                            "Unidades": st.column_config.NumberColumn(
                                "Unidades",
                                format="%d",
                            ),
                            "SKUs": st.column_config.NumberColumn(
                                "SKUs",
                                format="%d",
                            ),
                        },
                    )

                if (
                    estado_guardado
                    and not bool(
                        estado_guardado.get(
                            "exito",
                            False
                        )
                    )
                    and not bool(
                        estado_guardado.get(
                            "pendiente",
                            False
                        )
                    )
                ):

                    with st.expander(
                        f"❌ Ver error de {nombre_camioneta}",
                        expanded=True,
                    ):

                        st.error(
                            estado_guardado.get(
                                "mensaje",
                                "Error sin detalle."
                            )
                        )

                        detalle_guardado = estado_guardado.get(
                            "detalle",
                            ""
                        )

                        if detalle_guardado:

                            st.code(
                                detalle_guardado,
                                language="text",
                            )

                if ejecutar:

                    clave_resultado = (
                        f"resultado_digip_{clave_ejecucion}"
                    )

                    usuario_ejecucion = (
                        st.session_state.get("usuario")
                        or st.session_state.get("nombre_usuario")
                        or "Usuario app"
                    )

                    try:

                        orden_id = crear_orden_agrupacion(
                            camioneta=despacho_digip,
                            codigo_despacho=codigo_despacho,
                            codigos_despacho=codigos_despacho,
                            usar_filtro_codigo_despacho=(
                                usar_filtro_codigo_despacho
                            ),
                            pedidos=lista_pedidos,
                            usuario=usuario_ejecucion,
                        )

                        st.session_state[
                            clave_resultado
                        ] = {
                            "exito": False,
                            "pendiente": True,
                            "orden_id": orden_id,
                            "mensaje": (
                                "Orden enviada al worker de la PC."
                            ),
                        }

                        st.success(
                            f"Orden {orden_id} enviada al worker."
                        )

                        st.rerun()

                    except Exception as error:

                        st.session_state[
                            clave_resultado
                        ] = {
                            "exito": False,
                            "pendiente": False,
                            "mensaje": str(error),
                        }

                        st.error(
                            "No se pudo enviar la orden al worker: "
                            f"{error}"
                        )

                estado_cola = st.session_state.get(
                    f"resultado_digip_{clave_ejecucion}"
                )

                if estado_cola and estado_cola.get("orden_id"):

                    orden_actual = obtener_orden(
                        estado_cola["orden_id"]
                    )

                    if orden_actual:

                        estado_orden = str(
                            orden_actual.get("Estado", "")
                        ).strip().upper()

                        mensaje_orden = str(
                            orden_actual.get("Mensaje", "")
                        ).strip()

                        etapa_orden = str(
                            orden_actual.get("Etapa", "")
                        ).strip()

                        if estado_orden == "COMPLETADA":

                            st.session_state[
                                f"resultado_digip_{clave_ejecucion}"
                            ] = {
                                "exito": True,
                                "pendiente": False,
                                "orden_id": orden_actual.get("OrdenID"),
                                "mensaje": mensaje_orden,
                            }

                            st.success(
                                f"✅ {nombre_camioneta}: "
                                f"{mensaje_orden}"
                            )

                        elif estado_orden == "ERROR":

                            st.error(
                                f"❌ {nombre_camioneta}: "
                                f"{mensaje_orden}"
                            )

                        elif estado_orden == "EN_PROCESO":

                            st.info(
                                f"⚙️ {nombre_camioneta} en proceso — "
                                f"{etapa_orden}: {mensaje_orden}"
                            )

                        else:

                            st.warning(
                                f"🕒 {nombre_camioneta} pendiente "
                                "de ser tomada por el worker."
                            )

                        if estado_orden not in {
                            "COMPLETADA",
                            "ERROR",
                            "CANCELADA",
                        }:

                            if st.button(
                                "🔄 Consultar estado",
                                key=(
                                    "consultar_worker_"
                                    f"{clave_ejecucion}"
                                ),
                            ):
                                st.rerun()

