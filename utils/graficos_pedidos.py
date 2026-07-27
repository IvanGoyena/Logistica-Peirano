from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st


PALETA = [
    "#2563EB",
    "#F59E0B",
    "#22C55E",
    "#EF4444",
    "#8B5CF6",
    "#06B6D4",
    "#EC4899",
    "#84CC16",
]


def _vacio(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        st.info("No hay datos para mostrar.")
        return True
    return False


def evolucion(df: pd.DataFrame) -> None:
    if _vacio(df):
        return

    orden = df["FechaEtiqueta"].tolist()

    chart = (
        alt.Chart(df)
        .mark_line(
            point=True,
            strokeWidth=3,
            color="#F59E0B",
        )
        .encode(
            x=alt.X(
                "FechaEtiqueta:N",
                sort=orden,
                title="Fecha",
                axis=alt.Axis(labelAngle=-35),
            ),
            y=alt.Y(
                "Unidades:Q",
                title="Unidades",
                axis=alt.Axis(
                    tickMinStep=1,
                    labelExpr=(
                        "replace(format(datum.value, ',.0f'), ',', '.')"
                    ),
                ),
            ),
            tooltip=[
                alt.Tooltip(
                    "FechaVisible:N",
                    title="Fecha",
                ),
                alt.Tooltip(
                    "Unidades:Q",
                    title="Unidades",
                    format=",.0f",
                ),
            ],
        )
        .properties(height=300)
    )

    st.altair_chart(
        chart,
        width="stretch",
    )


def donut(
    df: pd.DataFrame,
    categoria: str,
    valor: str = "Pedidos",
) -> None:
    if _vacio(df):
        return

    datos = df.copy()
    total = float(datos[valor].sum())
    datos["Porcentaje"] = (
        datos[valor] / total * 100
        if total
        else 0
    )
    datos["Etiqueta"] = datos.apply(
        lambda f: (
            f"{int(f[valor])} "
            f"({f['Porcentaje']:.0f}%)"
        ),
        axis=1,
    )

    base = alt.Chart(datos).encode(
        theta=alt.Theta(f"{valor}:Q"),
        color=alt.Color(
            f"{categoria}:N",
            title=None,
            scale=alt.Scale(range=PALETA),
        ),
    )
    arcos = base.mark_arc(
        innerRadius=60,
        outerRadius=105,
    ).encode(
        tooltip=[
            alt.Tooltip(
                f"{categoria}:N",
                title=categoria,
            ),
            alt.Tooltip(
                f"{valor}:Q",
                title=valor,
                format=".0f",
            ),
        ]
    )
    etiquetas = base.mark_text(
        radius=83,
        color="white",
        fontWeight="bold",
        fontSize=11,
    ).encode(text="Etiqueta:N")
    st.altair_chart(
        (arcos + etiquetas).properties(height=290),
        width="stretch",
    )


def barras(
    df: pd.DataFrame,
    categoria: str,
    valor: str,
    horizontal: bool = True,
    color: str = "#7E57C2",
    altura: int = 320,
) -> None:
    if _vacio(df):
        return

    base = alt.Chart(df)

    if horizontal:
        barras_chart = base.mark_bar(
            color=color,
            cornerRadiusEnd=4,
        ).encode(
            y=alt.Y(
                f"{categoria}:N",
                sort="-x",
                title=None,
            ),
            x=alt.X(
                f"{valor}:Q",
                title=valor,
            ),
            tooltip=[
                alt.Tooltip(
                    f"{categoria}:N",
                    title=categoria,
                ),
                alt.Tooltip(
                    f"{valor}:Q",
                    title=valor,
                    format=",.2f"
                    if valor == "Volumen"
                    else ",.0f",
                ),
            ],
        )
        etiquetas = base.mark_text(
            align="left",
            baseline="middle",
            dx=6,
            color="white",
            fontWeight="bold",
        ).encode(
            y=alt.Y(
                f"{categoria}:N",
                sort="-x",
            ),
            x=alt.X(f"{valor}:Q"),
            text=alt.Text(
                f"{valor}:Q",
                format=".2f"
                if valor == "Volumen"
                else ".0f",
            ),
        )
    else:
        barras_chart = base.mark_bar(
            color=color,
            cornerRadiusEnd=4,
        ).encode(
            x=alt.X(
                f"{categoria}:N",
                sort="-y",
                title=None,
            ),
            y=alt.Y(
                f"{valor}:Q",
                title=valor,
            ),
            tooltip=[
                alt.Tooltip(f"{categoria}:N"),
                alt.Tooltip(f"{valor}:Q"),
            ],
        )
        etiquetas = base.mark_text(
            dy=-6,
            color="white",
            fontWeight="bold",
        ).encode(
            x=alt.X(
                f"{categoria}:N",
                sort="-y",
            ),
            y=alt.Y(f"{valor}:Q"),
            text=alt.Text(
                f"{valor}:Q",
                format=".2f"
                if valor == "Volumen"
                else ".0f",
            ),
        )

    st.altair_chart(
        (barras_chart + etiquetas).properties(
            height=altura
        ),
        width="stretch",
    )

def donut_composicion(
    df: pd.DataFrame,
    categoria: str,
    valor: str = "Unidades",
) -> None:
    """
    Donut optimizado para composición de unidades:
    - leyenda inferior;
    - total en el centro;
    - etiquetas sólo en porciones relevantes;
    - sin superposición de textos.
    """
    if _vacio(df):
        return

    datos = df.copy()
    datos[valor] = pd.to_numeric(
        datos[valor],
        errors="coerce",
    ).fillna(0)

    total = float(datos[valor].sum())
    if total <= 0:
        st.info("No hay unidades para mostrar.")
        return

    datos["Porcentaje"] = datos[valor] / total * 100
    datos["Etiqueta"] = datos.apply(
        lambda fila: (
            f"{int(fila[valor]):,}".replace(",", ".")
            + f" · {fila['Porcentaje']:.0f}%"
            if fila["Porcentaje"] >= 7
            else ""
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
            scale=alt.Scale(range=PALETA),
            legend=alt.Legend(
                orient="bottom",
                direction="horizontal",
                columns=3,
                labelLimit=150,
                symbolType="circle",
                offset=12,
            ),
        ),
    )

    sectores = base.mark_arc(
        innerRadius=78,
        outerRadius=132,
        stroke="#111827",
        strokeWidth=2,
    ).encode(
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
            alt.Tooltip(
                "Porcentaje:Q",
                title="Participación",
                format=".1f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        radius=106,
        color="#FFFFFF",
        fontWeight="bold",
        fontSize=11,
    ).encode(
        text=alt.Text("Etiqueta:N"),
    )

    centro_total = (
        alt.Chart(
            pd.DataFrame(
                {
                    "texto": [
                        f"{int(total):,}".replace(",", ".")
                    ]
                }
            )
        )
        .mark_text(
            fontSize=22,
            fontWeight="bold",
            color="#FFFFFF",
            dy=-7,
        )
        .encode(text="texto:N")
    )

    centro_subtitulo = (
        alt.Chart(pd.DataFrame({"texto": ["unidades"]}))
        .mark_text(
            fontSize=12,
            color="#AAB2C0",
            dy=16,
        )
        .encode(text="texto:N")
    )

    grafico = (
        sectores
        + etiquetas
        + centro_total
        + centro_subtitulo
    ).properties(
        height=390,
        padding={
            "top": 5,
            "left": 10,
            "right": 10,
            "bottom": 5,
        },
    )

    st.altair_chart(
        grafico,
        width="stretch",
    )

def pareto_clientes(
    df: pd.DataFrame,
) -> None:
    """
    Barras de unidades por cliente y línea de participación acumulada.
    """
    if _vacio(df):
        return

    base = alt.Chart(df)

    barras_chart = base.mark_bar(
        color="#7E57C2",
        cornerRadiusEnd=4,
    ).encode(
        x=alt.X(
            "Cliente:N",
            sort="-y",
            title=None,
            axis=alt.Axis(
                labelAngle=-35,
                labelLimit=110,
            ),
        ),
        y=alt.Y(
            "Unidades:Q",
            title="Unidades",
            axis=alt.Axis(
                labelExpr=(
                    "replace(format(datum.value, ',.0f'), ',', '.')"
                ),
            ),
        ),
        tooltip=[
            alt.Tooltip("Cliente:N", title="Cliente"),
            alt.Tooltip(
                "Pedidos:Q",
                title="Pedidos",
                format=".0f",
            ),
            alt.Tooltip(
                "Unidades:Q",
                title="Unidades",
                format=",.0f",
            ),
            alt.Tooltip(
                "Participacion:Q",
                title="Participación",
                format=".1f",
            ),
        ],
    )

    linea = base.mark_line(
        color="#F59E0B",
        point=True,
        strokeWidth=3,
    ).encode(
        x=alt.X(
            "Cliente:N",
            sort="-y",
        ),
        y=alt.Y(
            "Acumulado:Q",
            title="% acumulado",
            scale=alt.Scale(
                domain=[0, 100],
            ),
            axis=alt.Axis(
                orient="right",
                format=".0f",
            ),
        ),
        tooltip=[
            alt.Tooltip("Cliente:N", title="Cliente"),
            alt.Tooltip(
                "Acumulado:Q",
                title="% acumulado",
                format=".1f",
            ),
        ],
    )

    grafico = alt.layer(
        barras_chart,
        linea,
    ).resolve_scale(
        y="independent"
    ).properties(
        height=360
    )

    st.altair_chart(
        grafico,
        width="stretch",
    )


def barras_antiguedad_unidades(
    df: pd.DataFrame,
) -> None:
    if _vacio(df):
        return

    orden = [
        "Hoy",
        "1 día",
        "2 días",
        "3 a 5 días",
        "Más de 5 días",
    ]

    base = alt.Chart(df)

    barras_chart = base.mark_bar(
        cornerRadiusEnd=4,
        color="#EF4444",
    ).encode(
        x=alt.X(
            "Antigüedad:N",
            sort=orden,
            title=None,
        ),
        y=alt.Y(
            "Unidades:Q",
            title="Unidades",
            axis=alt.Axis(
                labelExpr=(
                    "replace(format(datum.value, ',.0f'), ',', '.')"
                ),
            ),
        ),
        tooltip=[
            alt.Tooltip(
                "Antigüedad:N",
                title="Antigüedad",
            ),
            alt.Tooltip(
                "Unidades:Q",
                title="Unidades",
                format=",.0f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        dy=-7,
        color="white",
        fontWeight="bold",
    ).encode(
        x=alt.X(
            "Antigüedad:N",
            sort=orden,
        ),
        y=alt.Y("Unidades:Q"),
        text=alt.Text(
            "Unidades:Q",
            format=".0f",
        ),
    )

    st.altair_chart(
        (barras_chart + etiquetas).properties(
            height=320
        ),
        width="stretch",
    )

def grafico_abc(
    df: pd.DataFrame,
    categoria: str,
) -> None:
    if _vacio(df):
        return

    colores = {
        "A": "#22C55E",
        "B": "#F59E0B",
        "C": "#EF4444",
    }

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y(
                f"{categoria}:N",
                sort="-x",
                title=None,
            ),
            x=alt.X(
                "Unidades:Q",
                title="Unidades",
                axis=alt.Axis(
                    labelExpr=(
                        "replace(format(datum.value, ',.0f'), ',', '.')"
                    ),
                ),
            ),
            color=alt.Color(
                "ClaseABC:N",
                title="Clase ABC",
                scale=alt.Scale(
                    domain=list(colores.keys()),
                    range=list(colores.values()),
                ),
            ),
            tooltip=[
                alt.Tooltip(
                    f"{categoria}:N",
                    title=categoria,
                ),
                alt.Tooltip(
                    "ClaseABC:N",
                    title="Clase",
                ),
                alt.Tooltip(
                    "Unidades:Q",
                    title="Unidades",
                    format=",.0f",
                ),
                alt.Tooltip(
                    "Volumen:Q",
                    title="Volumen m³",
                    format=".2f",
                ),
                alt.Tooltip(
                    "Participación:Q",
                    title="Participación",
                    format=".1f",
                ),
                alt.Tooltip(
                    "Acumulado:Q",
                    title="Acumulado",
                    format=".1f",
                ),
            ],
        )
        .properties(height=390)
    )
    st.altair_chart(chart, width="stretch")


def grafico_impacto_clientes(
    df: pd.DataFrame,
) -> None:
    if _vacio(df):
        return

    base = alt.Chart(df)

    barras_chart = base.mark_bar(
        color="#EC4899",
        cornerRadiusEnd=4,
    ).encode(
        y=alt.Y(
            "Cliente:N",
            sort="-x",
            title=None,
        ),
        x=alt.X(
            "Impacto:Q",
            title="Índice de impacto",
            scale=alt.Scale(domain=[0, 100]),
        ),
        tooltip=[
            alt.Tooltip("Cliente:N", title="Cliente"),
            alt.Tooltip(
                "Impacto:Q",
                title="Impacto",
                format=".1f",
            ),
            alt.Tooltip(
                "Pedidos:Q",
                title="Pedidos",
                format=".0f",
            ),
            alt.Tooltip(
                "Unidades:Q",
                title="Unidades",
                format=",.0f",
            ),
            alt.Tooltip(
                "Volumen:Q",
                title="Volumen m³",
                format=".2f",
            ),
            alt.Tooltip(
                "Importe:Q",
                title="Importe",
                format=",.0f",
            ),
        ],
    )

    etiquetas = base.mark_text(
        align="left",
        baseline="middle",
        dx=6,
        color="white",
        fontWeight="bold",
    ).encode(
        y=alt.Y("Cliente:N", sort="-x"),
        x=alt.X("Impacto:Q"),
        text=alt.Text("Impacto:Q", format=".1f"),
    )

    st.altair_chart(
        (barras_chart + etiquetas).properties(height=390),
        width="stretch",
    )

