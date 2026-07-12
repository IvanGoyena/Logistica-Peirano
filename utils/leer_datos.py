from pathlib import Path
import pandas as pd

from utils.google_drive import (
    leer_excel,
    leer_csv,
    buscar_archivo
)

# =====================================================
# RESOLVER NOMBRE DEL ARCHIVO
# =====================================================

def resolver_nombre(nombre):

    if Path(nombre).suffix != "":
        return nombre

    nombre_lower = nombre.strip().lower()

    if nombre_lower == "informe tareas":
        return "Informe Tareas.csv"

    if nombre_lower == "maestro clientes":
        return "Maestro Clientes.xlsm"

    return f"{nombre}.xlsx"


# =====================================================
# LEER ARCHIVO
# =====================================================

def leer_archivo(carpeta, nombre):

    try:

        nombre = resolver_nombre(nombre)

        extension = Path(nombre).suffix.lower()

        print(f"Leyendo desde Google Drive: {nombre}")

        if extension == ".csv":

            return leer_csv(nombre)

        elif extension in [".xlsx", ".xls", ".xlsm"]:

            return leer_excel(nombre)

        else:

            print(f"Formato no soportado: {nombre}")

            return pd.DataFrame()

    except Exception as e:

        print("")
        print("=" * 60)
        print("ERROR LEYENDO DESDE GOOGLE DRIVE")
        print(type(e).__name__)
        print(e)
        print("=" * 60)

        return pd.DataFrame()


# =====================================================
# FECHA ARCHIVO
# =====================================================

def fecha_archivo(carpeta, nombre):

    try:

        nombre = resolver_nombre(nombre)

        buscar_archivo(nombre)

        return "Google Drive"

    except:

        return "--"