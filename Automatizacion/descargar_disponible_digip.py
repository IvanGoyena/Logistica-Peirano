from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://app.digipwms.com"
URL_STOCK = "https://app.digipwms.com/Reportes/Stock"
USUARIO = "igoyena"
CLAVE = "0802"

CARPETA_DESCARGAS = Path(r"C:\Automatizacion_WMS\descargas\disponible_digip")
NOMBRE_TEMPORAL = "disponible_digip_temp"
NOMBRE_FINAL = "Disponible Digip.xlsx"
ESPERA_STOCK_TIPO_MS = 15000

def hacer_login(page):
    print("1. Abriendo login DIGIP...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    print("2. Completando usuario...")
    page.locator('input[name="username"], input[type="text"]').first.fill(USUARIO)

    print("3. Completando contraseña...")
    page.locator('input[name="password"], input[type="password"]').first.fill(CLAVE)

    print("4. Haciendo click en INGRESAR...")
    page.get_by_role("button", name="INGRESAR").click()

    print("5. Esperando ingreso al sistema...")
    page.wait_for_timeout(3000)
    page.wait_for_load_state("networkidle")

def leer_archivo_tolerante(ruta_origen):
    extension = ruta_origen.suffix.lower()

    if extension == ".csv":
        df = pd.read_csv(
            ruta_origen,
            dtype=str,
            encoding="utf-8-sig",
            sep=",",
            engine="python",
            on_bad_lines="skip"
        )

        if len(df.columns) == 1 and ";" in str(df.columns[0]):
            df = pd.read_csv(
                ruta_origen,
                dtype=str,
                encoding="utf-8-sig",
                sep=";",
                engine="python",
                on_bad_lines="skip"
            )
        return df

    if extension in [".xlsx", ".xls"]:
        return pd.read_excel(ruta_origen, dtype=str)

    raise ValueError(f"Extensión no soportada: {extension}")

def convertir_a_excel_final(ruta_origen, ruta_destino):
    try:
        print(f"Leyendo archivo descargado: {ruta_origen.name}")
        df = leer_archivo_tolerante(ruta_origen)

        if df.empty:
            print("El archivo descargado quedó vacío.")
            return

        df.columns = [str(col).strip() for col in df.columns]

        with pd.ExcelWriter(ruta_destino, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)

        print(f"Archivo final generado: {ruta_destino}")

    except Exception as e:
        print(f"Error al convertir el archivo a Excel: {e}")

def main():
    CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            hacer_login(page)

            print("6. Abriendo reporte de stock...")
            page.goto(URL_STOCK, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")

            print("7. Click en Filtrar...")
            boton_filtrar = page.get_by_role("button", name="Filtrar")
            boton_filtrar.wait_for(state="visible", timeout=30000)
            boton_filtrar.click()
            page.wait_for_timeout(3000)

            print("8. Click en Stock por Tipo...")
            tab_stock_tipo = page.get_by_text("Stock por Tipo", exact=True)
            tab_stock_tipo.wait_for(state="visible", timeout=30000)
            tab_stock_tipo.click(force=True)

            print(f"9. Esperando {ESPERA_STOCK_TIPO_MS / 1000:.0f} segundos para que cargue...")
            page.wait_for_timeout(ESPERA_STOCK_TIPO_MS)

            print("10. Buscando botón Descargar...")
            boton_descargar = page.get_by_role("link", name="Descargar")
            boton_descargar.wait_for(state="visible", timeout=30000)

            print("11. Iniciando descarga...")
            with page.expect_download(timeout=60000) as download_info:
                boton_descargar.click()

            download = download_info.value
            nombre_sugerido = download.suggested_filename
            extension = Path(nombre_sugerido).suffix if nombre_sugerido else ".csv"

            ruta_temporal = CARPETA_DESCARGAS / f"{NOMBRE_TEMPORAL}{extension}"
            ruta_final = CARPETA_DESCARGAS / NOMBRE_FINAL

            download.save_as(str(ruta_temporal))
            print(f"Descarga temporal completada: {ruta_temporal}")

            print("12. Generando Excel final para BI...")
            convertir_a_excel_final(ruta_temporal, ruta_final)

            print(f"Proceso finalizado. Archivo listo para BI: {ruta_final}")

        except PlaywrightTimeoutError as e:
            print("Timeout: no se encontró un elemento o no terminó la descarga.")
            print(e)
            try:
                page.screenshot(path="error_timeout_disponible.png", full_page=True)
                print("Se guardó captura: error_timeout_disponible.png")
            except:
                pass

        except Exception as e:
            print("Ocurrió un error durante la automatización.")
            print(e)
            try:
                page.screenshot(path="error_general_disponible.png", full_page=True)
                print("Se guardó captura: error_general_disponible.png")
            except:
                pass

        finally:
            try:
                context.close()
            except:
                pass
            try:
                browser.close()
            except:
                pass

if __name__ == "__main__":
    main()