from pathlib import Path
from datetime import datetime
import os
import pandas as pd


# =====================================================
# BUSCAR ARCHIVO
# =====================================================

def buscar_archivo(carpeta, nombre):

    carpeta = Path(carpeta)

    if not carpeta.exists():

        print(f"La carpeta no existe: {carpeta}")

        return None

    for archivo in carpeta.iterdir():

        if archivo.is_file():

            if archivo.stem.strip().lower() == nombre.strip().lower():

                print(f"Archivo encontrado: {archivo.name}")

                return archivo

    print("")
    print("=" * 60)
    print(f"No se encontró el archivo: {nombre}")
    print(f"Carpeta: {carpeta}")
    print("=" * 60)

    return None


# =====================================================
# LEER ARCHIVO
# =====================================================

def leer_archivo(carpeta, nombre):

    archivo = buscar_archivo(carpeta, nombre)

    if archivo is None:

        return pd.DataFrame()

    print(f"\nLeyendo archivo: {archivo.name}")

    try:

        # ---------------------------------------------
        # CSV
        # ---------------------------------------------

        if archivo.suffix.lower() == ".csv":

            configuraciones = [

                (";", "utf-8-sig"),

                (";", "cp1252"),

                (",", "utf-8-sig"),

                (",", "cp1252")

            ]

            ultimo_error = None

            for separador, encoding in configuraciones:

                try:

                    df = pd.read_csv(

                        archivo,

                        sep=separador,

                        encoding=encoding,

                        low_memory=False

                    )

                    print("CSV leído correctamente")
                    print(f"Separador : {separador}")
                    print(f"Encoding  : {encoding}")
                    print(f"Filas     : {len(df)}")
                    print(f"Columnas  : {len(df.columns)}")

                    return df

                except Exception as e:

                    ultimo_error = e

            print("")
            print("=" * 60)
            print("NO SE PUDO LEER EL CSV")
            print(ultimo_error)
            print("=" * 60)

            return pd.DataFrame()

        # ---------------------------------------------
        # EXCEL
        # ---------------------------------------------

        df = pd.read_excel(archivo)

        print(f"Excel leído correctamente ({len(df)} registros)")

        return df

    except Exception as e:

        print("")
        print("=" * 60)
        print("ERROR LEYENDO ARCHIVO")
        print(archivo)
        print(type(e).__name__)
        print(e)
        print("=" * 60)

        return pd.DataFrame()


# =====================================================
# FECHA DEL ARCHIVO
# =====================================================

def fecha_archivo(carpeta, nombre):

    archivo = buscar_archivo(carpeta, nombre)

    if archivo is None:

        return "--"

    fecha = datetime.fromtimestamp(

        os.path.getmtime(archivo)

    )

    return fecha.strftime("%d/%m/%Y %H:%M:%S")