# components/reclamos.py

from __future__ import annotations

from typing import Any
import logging

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


from utils.consultas.gestion_reclamos import (
    guardar_reclamo_entrega,
)


INCIDENCIAS_RECLAMO = [
    "Faltante de mercaderÃ­a",
    "Sobrante de mercaderÃ­a",
    "Producto incorrecto",
    "Producto daÃ±ado",
    "Cruce de mercaderÃ­a",
    "Diferencia de cantidad",
    "Error de documentaciÃ³n",
    "Otros",
]

ESTADOS_RECLAMO = [
    "Pendiente",
    "En revisiÃ³n",
    "En gestiÃ³n",
    "Resuelto",
    "Rechazado",
]


def _texto(serie: pd.Series) -> pd.Series:
    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )


def _buscar_columna(
    dataframe: pd.DataFrame,
    candidatos: list[str],
) -> str | None:
    mapa = {
        str(columna).strip().lower(): columna
        for columna in dataframe.columns
    }

    for candidato in candidatos:
        encontrada = mapa.get(
            candidato.strip().lower()
        )

        if encontrada is not None:
            return encontrada

    return None


def preparar_clientes(
    df_clientes: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza el maestro de clientes para usarlo como selector.
    """

    if df_clientes is None or df_clientes.empty:
        return pd.DataFrame(
            columns=[
                "ClienteCodigo",
                "ClienteDescripcion",
                "ClienteOpcion",
            ]
        )

    codigo_col = _buscar_columna(
        df_clientes,
        [
            "ClienteCodigo",
            "Codigo_Cliente",
            "CÃ³digo Cliente",
            "Codigo Cliente",
            "codigo_logistico",
            "CodigoSucursal",
        ],
    )

    descripcion_col = _buscar_columna(
        df_clientes,
        [
            "ClienteDescripcion",
            "Cliente",
            "RazonSocial",
            "RazÃ³n Social",
            "Descripcion",
        ],
    )

    if codigo_col is None or descripcion_col is None:
        raise ValueError(
            "No se pudieron identificar las columnas "
            "de cÃ³digo y descripciÃ³n del Maestro Clientes."
        )

    clientes = pd.DataFrame(
        {
            "ClienteCodigo": _texto(
                df_clientes[codigo_col]
            ),
            "ClienteDescripcion": _texto(
                df_clientes[descripcion_col]
            ),
        }
    )

    clientes = clientes[
        clientes["ClienteCodigo"].ne("")
        & clientes["ClienteDescripcion"].ne("")
    ].copy()

    clientes = (
        clientes
        .drop_duplicates(
            subset=[
                "ClienteCodigo",
                "ClienteDescripcion",
            ]
        )
        .sort_values(
            [
                "ClienteDescripcion",
                "ClienteCodigo",
            ]
        )
        .reset_index(drop=True)
    )

    clientes["ClienteOpcion"] = (
        clientes["ClienteCodigo"]
        + " - "
        + clientes["ClienteDescripcion"]
    )

    return clientes


def preparar_articulos(
    df_articulos: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza el Maestro de ArtÃ­culos para el data editor.
    """

    if df_articulos is None or df_articulos.empty:
        return pd.DataFrame(
            columns=[
                "ArticuloCodigo",
                "ArticuloDescripcion",
                "ArticuloOpcion",
            ]
        )

    codigo_col = _buscar_columna(
        df_articulos,
        [
            "CodigoArticulo",
            "ArticuloCodigo",
            "CÃ³digo",
            "Codigo",
            "cod_art",
            "ArtÃ­culo",
            "Articulo",
        ],
    )

    descripcion_col = _buscar_columna(
        df_articulos,
        [
            "ArticuloDescripcion",
            "DescripcionArticulo",
            "DescripciÃ³n",
            "Descripcion",
            "desc_art",
            "Producto",
        ],
    )

    if codigo_col is None:
        raise ValueError(
            "No se pudo identificar la columna de cÃ³digo "
            "del Maestro ArtÃ­culo."
        )

    articulos = pd.DataFrame(
        {
            "ArticuloCodigo": _texto(
                df_articulos[codigo_col]
            ),
        }
    )

    if descripcion_col is not None:
        articulos["ArticuloDescripcion"] = _texto(
            df_articulos[descripcion_col]
        )
    else:
        articulos["ArticuloDescripcion"] = ""

    articulos = articulos[
        articulos["ArticuloCodigo"].ne("")
    ].copy()

    articulos = (
        articulos
        .drop_duplicates(
            subset=["ArticuloCodigo"]
        )
        .sort_values("ArticuloCodigo")
        .reset_index(drop=True)
    )

    articulos["ArticuloOpcion"] = (
        articulos["ArticuloCodigo"]
        + articulos["ArticuloDescripcion"].where(
            articulos["ArticuloDescripcion"].eq(""),
            " - " + articulos[
                "ArticuloDescripcion"
            ],
        )
    )

    return articulos


def _obtener_usuario() -> str:
    return str(
        st.session_state.get("usuario")
        or st.session_state.get(
            "nombre_usuario"
        )
        or "Usuario no identificado"
    ).strip()


@st.dialog(
    "ðŸ§¾ Cargar reclamo de entrega",
    width="large",
)
def abrir_carga_reclamo(
    df_clientes: pd.DataFrame,
    df_articulos: pd.DataFrame,
) -> None:
    """
    Formulario independiente para reclamos de pedidos
    ya entregados.
    """

    clientes = preparar_clientes(
        df_clientes
    )
    articulos = preparar_articulos(
        df_articulos
    )

    if clientes.empty:
        st.error(
            "El Maestro Clientes no tiene opciones disponibles."
        )
        return

    if articulos.empty:
        st.error(
            "El Maestro ArtÃ­culo no tiene opciones disponibles."
        )
        return

    mapa_clientes = (
        clientes
        .set_index("ClienteOpcion")[
            [
                "ClienteCodigo",
                "ClienteDescripcion",
            ]
        ]
        .to_dict("index")
    )

    mapa_articulos = (
        articulos
        .set_index("ArticuloOpcion")[
            [
                "ArticuloCodigo",
                "ArticuloDescripcion",
            ]
        ]
        .to_dict("index")
    )

    st.caption(
        "Carga manual para pedidos ya entregados. "
        "Puede incluir uno o varios artÃ­culos."
    )

    with st.form(
        "form_nuevo_reclamo_entrega",
        clear_on_submit=False,
    ):
        datos_1, datos_2 = st.columns(2)

        with datos_1:
            numero_pedido = st.text_input(
                "NÃºmero de pedido *",
                placeholder="Ej.: 212240",
            )

            numero_remito = st.text_input(
                "NÃºmero de remito *",
                placeholder="Ej.: 0001-00012345",
            )

            fecha_reclamo = st.date_input(
                "Fecha del reclamo",
            )

        with datos_2:
            cliente_opcion = st.selectbox(
                "Cliente *",
                options=clientes[
                    "ClienteOpcion"
                ].tolist(),
                index=None,
                placeholder=(
                    "Buscar por cÃ³digo o cliente..."
                ),
            )

            incidencia = st.selectbox(
                "Incidencia *",
                options=INCIDENCIAS_RECLAMO,
                index=None,
                placeholder=(
                    "Seleccionar incidencia..."
                ),
            )

            estado_reclamo = st.selectbox(
                "Estado del reclamo *",
                options=ESTADOS_RECLAMO,
                index=0,
            )

        responsable = "Logistica"

        st.text_input(
            "Responsable",
            value=responsable,
            disabled=True,
        )

        observaciones = st.text_area(
            "Observaciones *",
            placeholder=(
                "DescribÃ­ quÃ© informÃ³ el cliente y cualquier "
                "dato relevante para analizar el reclamo..."
            ),
            height=110,
        )

        fotos_cargadas = st.file_uploader(
            "Fotos del reclamo",
            type=[
                "jpg",
                "jpeg",
                "png",
                "webp",
            ],
            accept_multiple_files=True,
            help=(
                "Campo opcional. PodÃ©s adjuntar varias fotos "
                "del producto, embalaje, remito o mercaderÃ­a recibida."
            ),
        )

        if fotos_cargadas:
            st.caption(
                f"Se adjuntarÃ¡n {len(fotos_cargadas)} foto(s)."
            )

        st.markdown("#### ArtÃ­culos reclamados")
        st.caption(
            "PodÃ©s agregar o eliminar filas. Se permite "
            "cargar 0 remitido y una cantidad recibida mayor "
            "a cero para registrar cruces de mercaderÃ­a."
        )

        detalle_inicial = pd.DataFrame(
            [
                {
                    "ArtÃ­culo": None,
                    "Cantidad remitida": 0.0,
                    "Cantidad recibida": 0.0,
                }
            ]
        )

        detalle_editado = st.data_editor(
            detalle_inicial,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "ArtÃ­culo": st.column_config.SelectboxColumn(
                    "ArtÃ­culo *",
                    options=articulos[
                        "ArticuloOpcion"
                    ].tolist(),
                    required=True,
                    width="large",
                ),
                "Cantidad remitida": (
                    st.column_config.NumberColumn(
                        "Cantidad remitida",
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        required=True,
                    )
                ),
                "Cantidad recibida": (
                    st.column_config.NumberColumn(
                        "Cantidad recibida",
                        min_value=0.0,
                        step=1.0,
                        format="%.2f",
                        required=True,
                    )
                ),
            },
            key="editor_detalle_reclamo",
        )

        guardar = st.form_submit_button(
            "ðŸ’¾ Registrar reclamo",
            type="primary",
            width="stretch",
        )

    if not guardar:
        return

    try:
        if cliente_opcion is None:
            raise ValueError(
                "Debe seleccionar un cliente."
            )

        filas_validas = detalle_editado[
            detalle_editado["ArtÃ­culo"].notna()
        ].copy()

        filas_validas["ArtÃ­culo"] = (
            filas_validas["ArtÃ­culo"]
            .astype(str)
            .str.strip()
        )

        filas_validas = filas_validas[
            filas_validas["ArtÃ­culo"].ne("")
        ]

        if filas_validas.empty:
            raise ValueError(
                "Debe seleccionar al menos un artÃ­culo."
            )

        articulos_reclamo: list[
            dict[str, Any]
        ] = []

        for _, fila in filas_validas.iterrows():
            opcion_articulo = fila["ArtÃ­culo"]
            datos_articulo = mapa_articulos.get(
                opcion_articulo
            )

            if datos_articulo is None:
                raise ValueError(
                    f"El artÃ­culo {opcion_articulo} "
                    "no se encuentra en el maestro."
                )

            articulos_reclamo.append(
                {
                    **datos_articulo,
                    "CantidadRemitida": fila.get(
                        "Cantidad remitida",
                        0,
                    ),
                    "CantidadRecibida": fila.get(
                        "Cantidad recibida",
                        0,
                    ),
                }
            )

        datos_cliente = mapa_clientes[
            cliente_opcion
        ]

        fotos_para_guardar = [
            {
                "nombre": foto.name,
                "tipo_contenido": foto.type,
                "contenido": foto.getvalue(),
            }
            for foto in (
                fotos_cargadas or []
            )
        ]

        resultado = guardar_reclamo_entrega(
            numero_pedido=numero_pedido,
            numero_remito=numero_remito,
            cliente_codigo=datos_cliente[
                "ClienteCodigo"
            ],
            cliente_descripcion=datos_cliente[
                "ClienteDescripcion"
            ],
            incidencia=incidencia,
            estado_reclamo=estado_reclamo,
            observaciones=observaciones,
            usuario_registro=_obtener_usuario(),
            articulos=articulos_reclamo,
            responsable=responsable,
            fecha_reclamo=(
                fecha_reclamo.strftime(
                    "%Y-%m-%d"
                )
            ),
            fotos=fotos_para_guardar,
        )

        mensaje_exito = resultado["mensaje"]

        if resultado.get("cantidad_fotos", 0):
            mensaje_exito += (
                f" Se guardaron "
                f"{resultado['cantidad_fotos']} foto(s)."
            )

        st.success(
            mensaje_exito
        )

        st.toast(
            "Reclamo registrado correctamente.",
            icon="ðŸ§¾",
        )

    except Exception:
        logger.exception(
            "Error al registrar un reclamo comercial."
        )
        st.error(
            "No se pudo registrar el reclamo. "
            "RevisÃ¡ los datos e intentÃ¡ nuevamente."
        )


def mostrar_boton_carga_reclamo(
    df_clientes: pd.DataFrame,
    df_articulos: pd.DataFrame,
) -> None:
    """
    Dibuja el acceso independiente a la carga de reclamos.
    """

    if st.button(
        "🧾 Cargar reclamo",
        type="primary",
        width="stretch",
        key="abrir_carga_reclamo",
    ):
        abrir_carga_reclamo(
            df_clientes=df_clientes,
            df_articulos=df_articulos,
        )

