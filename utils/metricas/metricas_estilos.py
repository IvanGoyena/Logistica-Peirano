import streamlit as st


def aplicar_estilos_metricas() -> None:
    # ==========================================================
    # ESTILO
    # ==========================================================


    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.15rem;
            padding-bottom: 3rem;
        }

        [data-testid="stMetric"] {
            background:
                linear-gradient(
                    145deg,
                    rgba(24, 34, 47, 0.98),
                    rgba(11, 17, 25, 0.98)
                );
            border: 1px solid #2A3543;
            border-radius: 12px;
            padding: 0.95rem 1rem;
            min-height: 122px;
        }

        [data-testid="stMetricLabel"] {
            color: #D8DEE9;
            font-weight: 600;
        }

        [data-testid="stMetricValue"] {
            color: #F8FAFC;
            font-size: 1.65rem;
            font-weight: 700;
        }

        [data-testid="stMetricDelta"] {
            font-size: 0.76rem;
            white-space: normal;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(15, 23, 34, 0.62);
            border-color: #2A3543;
            border-radius: 12px;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid #2A3543;
            border-radius: 10px;
            overflow: hidden;
        }

        button[data-baseweb="tab"] {
            font-weight: 600;
        }

        .operativo-kpi-grid {
            display: grid;
            grid-template-columns: repeat(6, minmax(0, 1fr));
            gap: 0.7rem;
            margin: 0.65rem 0 1.15rem 0;
        }

        .operativo-kpi-card {
            min-height: 126px;
            padding: 0.95rem 1rem;
            border: 1px solid #2A3543;
            border-radius: 12px;
            background:
                linear-gradient(
                    145deg,
                    rgba(24, 34, 47, 0.98),
                    rgba(11, 17, 25, 0.98)
                );
        }

        .operativo-kpi-label {
            color: #D8DEE9;
            font-size: 0.82rem;
            font-weight: 600;
            min-height: 2.1rem;
        }

        .operativo-kpi-value {
            color: #F8FAFC;
            font-size: 1.72rem;
            font-weight: 750;
            margin-top: 0.36rem;
            line-height: 1.05;
        }

        .operativo-kpi-detail {
            color: #93A4B8;
            font-size: 0.76rem;
            margin-top: 0.52rem;
            line-height: 1.25;
        }

        @media (max-width: 1100px) {
            .operativo-kpi-grid {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }
        }

        @media (max-width: 680px) {
            .operativo-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        .insight-card {
            display: flex;
            gap: 0.8rem;
            align-items: flex-start;
            padding: 0.95rem;
            border: 1px solid #2A3543;
            border-radius: 12px;
            margin-bottom: 0.7rem;
            background:
                linear-gradient(
                    145deg,
                    rgba(24, 34, 47, 0.96),
                    rgba(11, 17, 25, 0.96)
                );
        }

        .insight-icon {
            font-size: 1.28rem;
            line-height: 1.3;
        }

        .insight-title {
            color: #F8FAFC;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }

        .insight-text {
            color: #AAB7C7;
            font-size: 0.9rem;
        }

        .section-caption {
            color: #93A4B8;
            margin-top: -0.45rem;
            margin-bottom: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

