import pandas as pd


# ==========================================================
# NORMALIZACIÓN
# ==========================================================

def normalizar_pedido(serie: pd.Series) -> pd.Series:
    """Normaliza el número de pedido para permitir el merge."""

    return (
        serie
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.split("-")
        .str[0]
    )


# ==========================================================
# TABLA PEDIDOS TRANSMISIÓN ERP
# ==========================================================

def construir_tabla_transmisiones(
    df_transmisiones: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construye una fila por pedido con su última transmisión a DIGIP.

    Se conserva:
    - número de envío;
    - estado de transmisión;
    - fecha de transmisión;
    - hora de transmisión.
    """

    tabla = df_transmisiones.copy()

    columnas_requeridas = {
        "Pedido",
        "Nro Envio",
        "Estado",
        "F Envio Digip",
    }

    columnas_faltantes = sorted(
        columnas_requeridas.difference(tabla.columns)
    )

    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas en Pedidos Transmisión: "
            f"{columnas_faltantes}"
        )

    tabla = tabla.rename(
        columns={
            "Nro Envio": "NroEnvioERP",
            "Estado": "EstadoTransmisionERP",
            "F Envio Digip": "FechaHoraTransmisionERP",
        }
    )

    tabla["Pedido"] = normalizar_pedido(
        tabla["Pedido"]
    )

    tabla["NroEnvioERP"] = (
        tabla["NroEnvioERP"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    tabla["EstadoTransmisionERP"] = (
        tabla["EstadoTransmisionERP"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    tabla["FechaHoraTransmisionERP"] = pd.to_datetime(
        tabla["FechaHoraTransmisionERP"],
        dayfirst=True,
        errors="coerce",
    )

    # Una transmisión posterior reemplaza a las anteriores.
    # Los registros sin fecha quedan al final y no pisan una
    # transmisión válida que ya tenga fecha y hora.
    tabla = (
        tabla
        .sort_values(
            by=[
                "Pedido",
                "FechaHoraTransmisionERP",
                "NroEnvioERP",
            ],
            ascending=[
                True,
                False,
                False,
            ],
            na_position="last",
        )
        .drop_duplicates(
            subset=["Pedido"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    tabla["FechaTransmisionERP"] = (
        tabla["FechaHoraTransmisionERP"]
        .dt.normalize()
    )

    tabla["HoraTransmisionERP"] = (
        tabla["FechaHoraTransmisionERP"]
        .dt.strftime("%H:%M:%S")
        .fillna("")
    )

    return tabla[
        [
            "Pedido",
            "NroEnvioERP",
            "EstadoTransmisionERP",
            "FechaTransmisionERP",
            "HoraTransmisionERP",
        ]
    ].copy()
