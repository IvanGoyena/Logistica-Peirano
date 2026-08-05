from __future__ import annotations

import streamlit as st


MODO_PC = "💻 PC / notebook"
MODO_MONITOR = "🖥️ Monitor"
MODO_TV = "📺 TV depósito"


def selector_modo_visual() -> str:
    """Permite elegir la escala según la distancia y el tamaño de pantalla."""
    return st.radio(
        "Escala visual",
        options=[MODO_PC, MODO_MONITOR, MODO_TV],
        horizontal=False,
        key="tareas_modo_visual",
        help=(
            "PC: trabajo cercano. Monitor: pantalla externa de oficina. "
            "TV depósito: lectura a varios metros de distancia."
        ),
    )


def perfil_visual(modo: str) -> str:
    if modo == MODO_TV:
        return "tv"
    if modo == MODO_MONITOR:
        return "monitor"
    return "pc"


def es_modo_monitor(modo: str) -> bool:
    """Compatibilidad con imports anteriores."""
    return perfil_visual(modo) in {"monitor", "tv"}


def es_modo_tv(modo: str) -> bool:
    return perfil_visual(modo) == "tv"


def aplicar_estilo_pantalla(modo: str) -> None:
    perfil = perfil_visual(modo)

    perfiles = {
        "pc": {
            "kpi_label": "clamp(.86rem,.90vw,1rem)",
            "kpi_value": "clamp(2.15rem,2.35vw,2.85rem)",
            "kpi_detail": "clamp(.78rem,.82vw,.92rem)",
            "kpi_height": "126px",
            "panel_title": "clamp(1.08rem,1.14vw,1.30rem)",
            "caption": ".84rem",
            "table_font": ".84rem",
            "table_header": ".86rem",
            "row_height": "33px",
            "page_title": "clamp(1.72rem,1.88vw,2.22rem)",
            "gap": "12px",
            "padding": "15px 18px",
            "button_h": "39px",
            "button_font": ".86rem",
        },
        "monitor": {
            # Perfil intermedio deliberadamente compacto en altura.
            "kpi_label": "clamp(.94rem,1vw,1.12rem)",
            "kpi_value": "clamp(2.55rem,2.85vw,3.45rem)",
            "kpi_detail": "clamp(.86rem,.92vw,1.03rem)",
            "kpi_height": "138px",
            "panel_title": "clamp(1.16rem,1.25vw,1.46rem)",
            "caption": ".91rem",
            "table_font": ".91rem",
            "table_header": ".93rem",
            "row_height": "36px",
            "page_title": "clamp(1.88rem,2.08vw,2.52rem)",
            "gap": "13px",
            "padding": "16px 19px",
            "button_h": "42px",
            "button_font": ".91rem",
        },
        "tv": {
            "kpi_label": "clamp(1.08rem,1.18vw,1.38rem)",
            "kpi_value": "clamp(3.1rem,3.65vw,4.65rem)",
            "kpi_detail": "clamp(1rem,1.08vw,1.28rem)",
            "kpi_height": "172px",
            "panel_title": "clamp(1.38rem,1.52vw,1.82rem)",
            "caption": "1.06rem",
            "table_font": "1.02rem",
            "table_header": "1.06rem",
            "row_height": "44px",
            "page_title": "clamp(2.28rem,2.65vw,3.25rem)",
            "gap": "18px",
            "padding": "22px 25px",
            "button_h": "50px",
            "button_font": "1.02rem",
        },
    }
    p = perfiles[perfil]

    css = f"""
    <style>
    /* Centro de Control Operativo — perfiles PC / Monitor / TV */
    .block-container {{
        padding-top: 1.15rem !important;
        padding-bottom: 1.25rem !important;
        max-width: 100% !important;
    }}

    .tareas-kpi-grid {{
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:{p['gap']};
        margin:8px 0 14px 0;
    }}
    .tareas-kpi-card {{
        background:linear-gradient(145deg,#121923 0%,#0f151e 100%);
        border:1px solid #2a3442;
        border-radius:13px;
        padding:{p['padding']};
        min-height:{p['kpi_height']};
        display:flex;
        flex-direction:column;
        justify-content:flex-start;
        box-shadow:0 7px 22px rgba(0,0,0,.12);
    }}
    .tareas-kpi-label {{
        color:#D8DEE9;
        font-size:{p['kpi_label']};
        font-weight:700;
        line-height:1.15;
    }}
    .tareas-kpi-value {{
        color:#F8FAFC;
        font-size:{p['kpi_value']};
        font-weight:800;
        line-height:.98;
        margin:10px 0 8px 0;
        letter-spacing:-.025em;
    }}
    .tareas-kpi-detail {{
        color:#B8C4D3;
        font-size:{p['kpi_detail']};
        font-weight:550;
        line-height:1.30;
        margin-top:auto;
    }}

    h1 {{
        font-size:{p['page_title']} !important;
        line-height:1.08 !important;
        margin:0 0 .22rem 0 !important;
    }}
    h3 {{ margin-top:.55rem !important; margin-bottom:.35rem !important; }}

    div[data-testid="stVerticalBlockBorderWrapper"] h4,
    div[data-testid="stVerticalBlockBorderWrapper"] h3 {{
        font-size:{p['panel_title']} !important;
        line-height:1.15 !important;
        margin-top:0 !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background:rgba(15,23,34,.58);
        border-color:#2A3543;
        border-radius:13px;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] > div {{
        padding-top:.72rem !important;
        padding-bottom:.65rem !important;
    }}

    div[data-testid="stCaptionContainer"] p {{
        font-size:{p['caption']} !important;
        color:#AEBAC8 !important;
        line-height:1.25 !important;
        margin-bottom:.25rem !important;
    }}

    div[data-testid="stDataFrame"] {{ font-size:{p['table_font']} !important; }}
    div[data-testid="stDataFrame"] [role="columnheader"] {{
        font-size:{p['table_header']} !important;
        font-weight:700 !important;
        min-height:{p['row_height']} !important;
    }}
    div[data-testid="stDataFrame"] [role="gridcell"] {{
        font-size:{p['table_font']} !important;
        min-height:{p['row_height']} !important;
        line-height:1.18 !important;
    }}

    div[data-testid="stButton"] button {{
        min-height:{p['button_h']};
        font-size:{p['button_font']};
        font-weight:650;
    }}

    /* Reduce espacios verticales generales sin afectar lectura. */
    div[data-testid="stVerticalBlock"] {{ gap:.55rem; }}

    @media (max-width:1250px) {{
        .tareas-kpi-grid {{grid-template-columns:repeat(2,minmax(0,1fr));}}
    }}
    @media (max-width:700px) {{
        .tareas-kpi-grid {{grid-template-columns:1fr;}}
        .tareas-kpi-card {{min-height:116px;}}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
