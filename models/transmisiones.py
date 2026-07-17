import pandas as pd


# ==========================================================
# TABLA PEDIDOS TRANSMISIÓN ERP
# ==========================================================

def construir_tabla_transmisiones(df_transmisiones):

    # ------------------------------------------------------
    # COPIA
    # ------------------------------------------------------

    tabla = df_transmisiones.copy()


    # ------------------------------------------------------
# RENOMBRAR COLUMNAS
# ------------------------------------------------------

    tabla = tabla.rename(
    columns={
        "Pedido": "Pedido",
        "Nro Envio": "NroEnvioERP",
        "Estado": "EstadoTransmisionERP",
        "F Envio Digip": "FechaHoraTransmisionERP"
    }
    )

# ------------------------------------------------------
# FECHA Y HORA TRANSMISIÓN
# ------------------------------------------------------

    tabla["FechaHoraTransmisionERP"] = pd.to_datetime(
    tabla["FechaHoraTransmisionERP"],
    dayfirst=True,
    errors="coerce"
    )    

    tabla["FechaTransmisionERP"] = (
    tabla["FechaHoraTransmisionERP"]
    .dt.date
    )

    tabla["HoraTransmisionERP"] = (
    tabla["FechaHoraTransmisionERP"]
    .dt.strftime("%H:%M:%S")
    )

# ------------------------------------------------------
# TABLA SATÉLITE FINAL
# ------------------------------------------------------

    tabla = tabla[
    [
        "Pedido",
        "NroEnvioERP",
        "EstadoTransmisionERP",
        "FechaTransmisionERP",
        "HoraTransmisionERP"
    ]
].copy()

    return tabla