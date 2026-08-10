from __future__ import annotations

import streamlit as st


def aplicar_estilo_inventario() -> None:
    st.markdown(
        """
        <style>
        .inv-kpi-grid {
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:12px;
            margin:10px 0 18px 0;
        }

        .inv-kpi {
            border:1px solid #2a3442;
            border-radius:12px;
            padding:16px 18px;
            min-height:116px;
            background:
                linear-gradient(
                    145deg,
                    #121923,
                    #0d141d
                );
        }

        .inv-label {
            color:#cbd5e1;
            font-size:.86rem;
            font-weight:650;
        }

        .inv-value {
            color:#f8fafc;
            font-size:2rem;
            font-weight:750;
            margin-top:8px;
        }

        .inv-detail {
            color:#94a3b8;
            font-size:.78rem;
            margin-top:8px;
        }

        .inv-ok {
            border-left:4px solid #22c55e;
        }

        .inv-warn {
            border-left:4px solid #f59e0b;
        }

        .inv-bad {
            border-left:4px solid #ef4444;
        }

        .inv-info {
            border-left:4px solid #3b82f6;
        }

        @media(max-width:1100px) {
            .inv-kpi-grid {
                grid-template-columns:
                    repeat(2,minmax(0,1fr));
            }
        }

        @media(max-width:650px) {
            .inv-kpi-grid {
                grid-template-columns:1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
