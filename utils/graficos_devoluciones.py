from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st


PALETA_CATEGORIAS = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
]

COLORES_BARRAS = {
    "Cliente": "#7E57C2",
    "Rango": "#F59E0B",
    "DiaSemana": "#22A06B",
    "HoraSolicitud": "#14B8A6",
}


def _sin_datos(
    df: pd.DataFrame,
    mensaje: str = "No hay datos para mostrar.",
) -> bool:
    if df is None or df.empty:
        st.info(mensaje)
        return True
    return False


def grafico_evolucion(df: pd.DataFrame) -> None:
    if _sin_datos(df):
        return

    orden_fechas = df["FechaEtiqueta"].tolist()

    grafico = (
        alt.Chart(df)
        .mark_line(
            point=alt.OverlayMarkDef(
                filled=True,
                size=60,
            ),
            strokeWidth=3,
            color="#F59E0B",
        )
        .encode(
            x=alt.X(
                "FechaEtiqueta:N",
                sort=orden_fechas,
                title="Fecha",
                axis=alt.Axis(
                    labelAngle=-35,
                    labelLimit=90,
                ),
            ),
            y=alt.Y(
                "Gestiones:Q",
                title="Cancelaciones",
                axis=alt.Axis(tickMinStep=1),
            ),
            tooltip=[
                alt.Tooltip(
                    "FechaVisible:N",
                    title="Fecha",
                ),
                alt.Tooltip(
                    "Gestiones:Q",
                    title="Gestiones",
                    format=".0f",
                ),
            ],
        )
        .properties(height=300)
        .interactive()
    )
    st.altair_chart(grafico, width="stretch")


def grafico_barras(
    df: pd.DataFrame,
    categoria: str,
    valor: str = "Gestiones",
    horizontal: bool = False,
    altura: int = 300,
) -> None:
    if _sin_datos(df):
        return

    color = COLORES_BARRAS.get(categoria, "#4C78A8")
    base = alt.Chart(df)

    if horizontal:
        barras = base.mark_bar(
            cornerRadiusEnd=4,
            color=color,
        ).encode(
            y=alt.Y(
                f"{categoria}:N",
                sort="-x",
                title=None,
            ),
            x=alt.X(
                f"{valor}:Q",
                title="Gestiones",
                axis=alt.Axis(tickMinStep=1),
            ),
            tooltip=[
                alt.Tooltip(
                    f"{categoria}:N",
                    title=categoria,
                ),
                alt.Tooltip(
                    f"{valor}:Q",
                    title=valor,
                    format=",.0f",
                ),
            ],
        )

        etiquetas = base.mark_text(
            align="left",
            baseline="middle",
            dx=6,
            fontWeight="bold",
            color="#E5E7EB",
        ).encode(
            y=alt.Y(
                f"{categoria}:N",
                sort="-x",
                title=None,
            ),
            x=alt.X(f"{valor}:Q"),
            text=alt.Text(
                f"{valor}:Q",
                format=",.0f",
            ),
        )
    else:
        barras = base.mark_bar(
            cornerRadiusEnd=4,
            color=color,
        ).encode(
            x=alt.X(
                f"{categoria}:N",
                sort="-y",
                title=None,
            ),
            y=alt.Y(
                f"{valor}:Q",
                title="Gestiones",
                axis=alt.Axis(tickMinStep=1),
            ),
            tooltip=[
                alt.Tooltip(
                    f"{categoria}:N",
                    title=categoria,
                ),
                alt.Tooltip(
                    f"{valor}:Q",
                    title=valor,
                    format=",.0f",
                ),
            ],
        )

        etiquetas = base.mark_text(
            align="center",
            baseline="bottom",
            dy=-5,
            fontWeight="bold",
            color="#E5E7EB",
        ).encode(
            x=alt.X(
                f"{categoria}:N",
                sort="-y",
                title=None,
            ),
            y=alt.Y(f"{valor}:Q"),
            text=alt.Text(
                f"{valor}:Q",
                format=",.0f",
            ),
        )

    grafico = (barras + etiquetas).properties(height=altura)
    st.altair_chart(grafico, width="stretch")

def grafico_donut(
    df: pd.DataFrame,
    categoria: str,
    valor: str = "Gestiones",
) -> None:
    if _sin_datos(df):
        return

    datos = df.copy()
    datos[valor] = pd.to_numeric(
        datos[valor],
        errors="coerce",
    ).fillna(0)

    total = float(datos[valor].sum())
    if total <= 0:
        st.info("No hay valores para mostrar.")
        return

    datos["Porcentaje"] = datos[valor] / total * 100
    datos["Etiqueta"] = datos.apply(
        lambda fila: (
            f"{int(fila[valor])} "
            f"({fila['Porcentaje']:.0f}%)"
        ),
        axis=1,
    )

    base = alt.Chart(datos).encode(
        theta=alt.Theta(
            f"{valor}:Q",
            stack=True,
        ),
        color=alt.Color(
            f"{categoria}:N",
            title=None,
            scale=alt.Scale(range=PALETA_CATEGORIAS),
        ),
    )

    sectores = base.mark_arc(
        innerRadius=65,
        outerRadius=110,
        stroke="#111827",
        strokeWidth=1,
    ).encode(
        tooltip=[
            alt.Tooltip(
                f"{categoria}:N",
                title=categoria,
            ),
            alt.Tooltip(
                f"{valor}:Q",
                title="Gestiones",
                format=".0f",
            ),
            alt.Tooltip(
                "Porcentaje:Q",
                title="Participación",
                format=".1f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        radius=88,
        fontSize=12,
        fontWeight="bold",
        color="#FFFFFF",
    ).encode(
        text=alt.Text("Etiqueta:N"),
    )

    grafico = (sectores + etiquetas).properties(height=300)
    st.altair_chart(grafico, width="stretch")

def grafico_embudo(df: pd.DataFrame) -> None:
    if _sin_datos(df):
        return

    base = alt.Chart(df)

    barras = base.mark_bar(
        cornerRadiusEnd=5,
    ).encode(
        y=alt.Y(
            "Etapa:N",
            sort=None,
            title=None,
        ),
        x=alt.X(
            "Gestiones:Q",
            title="Gestiones",
            axis=alt.Axis(tickMinStep=1),
        ),
        color=alt.Color(
            "Etapa:N",
            title=None,
            legend=None,
            scale=alt.Scale(
                domain=df["Etapa"].tolist(),
                range=[
                    "#2563EB",
                    "#0EA5E9",
                    "#14B8A6",
                    "#22C55E",
                    "#84CC16",
                    "#F59E0B",
                    "#8B5CF6",
                ][: len(df)],
            ),
        ),
        tooltip=[
            alt.Tooltip("Etapa:N", title="Etapa"),
            alt.Tooltip(
                "Gestiones:Q",
                title="Gestiones",
                format=".0f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        align="left",
        baseline="middle",
        dx=6,
        fontWeight="bold",
        color="#E5E7EB",
    ).encode(
        y=alt.Y(
            "Etapa:N",
            sort=None,
            title=None,
        ),
        x=alt.X("Gestiones:Q"),
        text=alt.Text(
            "Gestiones:Q",
            format=".0f",
        ),
    )

    grafico = (barras + etiquetas).properties(height=330)
    st.altair_chart(grafico, width="stretch")

def grafico_responsables(df: pd.DataFrame) -> None:
    if _sin_datos(df):
        return

    base = alt.Chart(df)

    barras = base.mark_bar(
        cornerRadiusEnd=4,
        color="#EC4899",
    ).encode(
        y=alt.Y(
            "ResponsableGestion:N",
            sort="-x",
            title=None,
        ),
        x=alt.X(
            "Gestiones:Q",
            title="Gestiones",
            axis=alt.Axis(tickMinStep=1),
        ),
        tooltip=[
            alt.Tooltip(
                "ResponsableGestion:N",
                title="Responsable",
            ),
            alt.Tooltip(
                "Gestiones:Q",
                title="Gestiones",
                format=".0f",
            ),
            alt.Tooltip(
                "TiempoPromedioHoras:Q",
                title="Promedio cierre (h)",
                format=".2f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        align="left",
        baseline="middle",
        dx=6,
        fontWeight="bold",
        color="#E5E7EB",
    ).encode(
        y=alt.Y(
            "ResponsableGestion:N",
            sort="-x",
            title=None,
        ),
        x=alt.X("Gestiones:Q"),
        text=alt.Text(
            "Gestiones:Q",
            format=".0f",
        ),
    )

    grafico = (barras + etiquetas).properties(height=320)
    st.altair_chart(grafico, width="stretch")

def grafico_tiempos_etapa(df: pd.DataFrame) -> None:
    if _sin_datos(df):
        return

    base = alt.Chart(df)

    barras = base.mark_bar(
        cornerRadiusEnd=4,
    ).encode(
        y=alt.Y(
            "Etapa:N",
            sort=None,
            title=None,
        ),
        x=alt.X(
            "HorasPromedio:Q",
            title="Horas promedio",
        ),
        color=alt.Color(
            "Etapa:N",
            title=None,
            legend=None,
            scale=alt.Scale(
                range=[
                    "#06B6D4",
                    "#22C55E",
                    "#F59E0B",
                    "#F97316",
                    "#EF4444",
                ],
            ),
        ),
        tooltip=[
            alt.Tooltip(
                "Etapa:N",
                title="Etapa",
            ),
            alt.Tooltip(
                "HorasPromedio:Q",
                title="Horas",
                format=".2f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        align="left",
        baseline="middle",
        dx=6,
        fontWeight="bold",
        color="#E5E7EB",
    ).encode(
        y=alt.Y(
            "Etapa:N",
            sort=None,
            title=None,
        ),
        x=alt.X("HorasPromedio:Q"),
        text=alt.Text(
            "HorasPromedio:Q",
            format=".1f",
        ),
    )

    grafico = (barras + etiquetas).properties(height=300)
    st.altair_chart(grafico, width="stretch")

