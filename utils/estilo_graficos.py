from __future__ import annotations


PALETA_GRAFICOS = [
    "#1E5A8A",
    "#155E75",
    "#166534",
    "#854D0E",
    "#7C2D12",
    "#4C1D95",
    "#374151",
    "#0F766E",
]


def aplicar_formato_visual_plotly(
    figura,
    *,
    mostrar_valores: bool = True,
    altura: int | None = None,
):
    """
    Aplica la identidad visual compartida por todos los módulos.

    No renderiza el gráfico. Devuelve la figura para permitir ajustes
    adicionales antes de llamar a st.plotly_chart().
    """

    configuracion_layout = {
        "template": "plotly_dark",
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {
            "color": "#D8DEE9",
            "family": "Arial, sans-serif",
        },
        "colorway": PALETA_GRAFICOS,
        "margin": {
            "l": 18,
            "r": 28,
            "t": 30,
            "b": 20,
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"color": "#D8DEE9"},
        },
        "hoverlabel": {
            "bgcolor": "#111827",
            "bordercolor": "#334155",
            "font_color": "#F8FAFC",
        },
    }

    if altura is not None:
        configuracion_layout["height"] = altura

    figura.update_layout(**configuracion_layout)

    figura.update_xaxes(
        gridcolor="rgba(148,163,184,0.12)",
        zerolinecolor="rgba(148,163,184,0.22)",
        linecolor="rgba(148,163,184,0.22)",
        tickfont=dict(color="#B8C2D0"),
        title_font=dict(color="#D8DEE9"),
    )

    figura.update_yaxes(
        gridcolor="rgba(148,163,184,0.12)",
        zerolinecolor="rgba(148,163,184,0.22)",
        linecolor="rgba(148,163,184,0.22)",
        tickfont=dict(color="#B8C2D0"),
        title_font=dict(color="#D8DEE9"),
    )

    for traza in figura.data:
        tipo = getattr(traza, "type", "")

        if tipo == "pie":
            traza.update(
                hole=max(
                    float(
                        getattr(traza, "hole", 0) or 0
                    ),
                    0.56,
                ),
                textposition="auto",
                textinfo="label+percent",
                marker=dict(
                    line=dict(
                        color="#0B1119",
                        width=2,
                    )
                ),
                sort=False,
            )

        elif tipo == "bar" and mostrar_valores:
            orientacion = getattr(
                traza,
                "orientation",
                None,
            )

            if orientacion == "h":
                traza.update(
                    texttemplate="%{x:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                )
            else:
                traza.update(
                    texttemplate="%{y:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                )

        elif tipo == "scatter":
            modo = str(
                getattr(traza, "mode", "") or ""
            )

            if "lines" in modo:
                traza.update(
                    line=dict(width=3),
                    marker=dict(size=8),
                )

    return figura
