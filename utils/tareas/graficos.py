from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


FONDO = "rgba(0,0,0,0)"
TEXTO = "#F1F5F9"
TEXTO_SECUNDARIO = "#A8B5C5"


def _color_avance(avance: int) -> str:
    if avance <= 30:
        return "#EF4444"
    if avance <= 70:
        return "#F59E0B"
    return "#22C55E"


def _parametros(perfil: str) -> dict[str, int | float]:
    return {
        "pc": {
            "altura": 205,
            "titulo": 12,
            "porcentaje": 28,
            "detalle": 12,
            "hueco": .70,
            "margen_t": 43,
            "sector_altura": 405,
            "centro": 26,
            "unidad": 13,
            "leyenda": 11,
            "sector_hueco": .70,
        },
        "monitor": {
            # Más legible que PC, pero sin el exceso vertical del modo TV.
            "altura": 225,
            "titulo": 13,
            "porcentaje": 32,
            "detalle": 14,
            "hueco": .68,
            "margen_t": 46,
            "sector_altura": 430,
            "centro": 29,
            "unidad": 14,
            "leyenda": 12,
            "sector_hueco": .68,
        },
        "tv": {
            "altura": 285,
            "titulo": 16,
            "porcentaje": 41,
            "detalle": 18,
            "hueco": .64,
            "margen_t": 60,
            "sector_altura": 525,
            "centro": 37,
            "unidad": 18,
            "leyenda": 16,
            "sector_hueco": .62,
        },
    }[perfil]


def grafico_avance_despacho(
    fila: pd.Series,
    *,
    perfil: str = "pc",
    modo_monitor: bool | None = None,
) -> None:
    # Compatibilidad con llamadas anteriores.
    if modo_monitor is not None and perfil == "pc":
        perfil = "monitor" if modo_monitor else "pc"

    p = _parametros(perfil)
    avance = int(fila.get("Avance", 0))
    cerrados = int(fila.get("PreparacionesFinalizadas", 0))
    total = int(fila.get("TotalPreparaciones", 0))
    despacho = str(fila.get("Despacho", ""))

    figura = go.Figure(
        go.Pie(
            values=[avance, max(100 - avance, 0)],
            hole=p["hueco"],
            textinfo="none",
            showlegend=False,
            sort=False,
            direction="clockwise",
            marker={
                "colors": [_color_avance(avance), "#1E293B"],
                "line": {"color": "#0B1119", "width": 3},
            },
            hovertemplate=(
                f"<b>{despacho}</b><br>Avance: {avance}%<br>"
                f"Preparaciones cerradas: {cerrados}<br>"
                f"Preparaciones totales: {total}<extra></extra>"
            ),
        )
    )
    figura.update_layout(
        height=p["altura"],
        margin={"l": 2, "r": 2, "t": p["margen_t"], "b": 2},
        paper_bgcolor=FONDO,
        plot_bgcolor=FONDO,
        font={"color": TEXTO},
        annotations=[
            {
                "text": f"<b>{despacho}</b>",
                "x": .5, "y": 1.08, "showarrow": False,
                "font": {"size": p["titulo"], "color": TEXTO},
            },
            {
                "text": f"<b>{avance}%</b>",
                "x": .5, "y": .57, "showarrow": False,
                "font": {"size": p["porcentaje"], "color": TEXTO},
            },
            {
                "text": f"<b>{cerrados} / {total}</b>",
                "x": .5, "y": .35, "showarrow": False,
                "font": {"size": p["detalle"], "color": TEXTO_SECUNDARIO},
            },
        ],
    )
    st.plotly_chart(
        figura,
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )


def grafico_sectorizaciones(
    familias: pd.Series,
    *,
    perfil: str = "pc",
    modo_monitor: bool | None = None,
) -> None:
    if modo_monitor is not None and perfil == "pc":
        perfil = "monitor" if modo_monitor else "pc"
    if familias is None or familias.empty:
        st.info("No hay sectores activos para mostrar.")
        return

    p = _parametros(perfil)
    etiquetas = [
        f"{sector} — {int(unidades):,} u.".replace(",", ".")
        for sector, unidades in familias.items()
    ]

    figura = go.Figure(
        go.Pie(
            labels=etiquetas,
            values=familias.values,
            hole=p["sector_hueco"],
            textinfo="none",
            sort=False,
            marker={"line": {"color": "#0B1119", "width": 3}},
            hovertemplate="<b>%{label}</b><br>Participación: %{percent}<extra></extra>",
        )
    )
    figura.update_layout(
        height=p["sector_altura"],
        margin={"l": 4, "r": 6, "t": 8, "b": 4},
        paper_bgcolor=FONDO,
        plot_bgcolor=FONDO,
        font={"color": TEXTO},
        annotations=[{
            "text": (
                f"<b>{int(familias.sum()):,}</b><br>"
                f"<span style='font-size:{p['unidad']}px'>Unidades</span>"
            ).replace(",", "."),
            "x": .5, "y": .5, "showarrow": False,
            "font": {"size": p["centro"], "color": TEXTO},
        }],
        legend={
            "orientation": "v",
            "x": 1.01,
            "y": .95,
            "font": {"size": p["leyenda"], "color": TEXTO},
            "itemsizing": "constant",
        },
    )
    st.plotly_chart(
        figura,
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )
