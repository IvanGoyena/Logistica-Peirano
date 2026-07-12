from pathlib import Path
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://app.digipwms.com"
URL_HOME = "https://app.digipwms.com/home"
USUARIO = "igoyena"
CLAVE = "0802"

CARPETA_DESCARGAS = Path(
    r"G:\Mi unidad\Sistema_Logistico_Peirano\data"
)

NOMBRE_TEMPORAL = "pedidos_digip_temp"
NOMBRE_FINAL = "Pedidos DIGIP.xlsx"


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


def limpiar_filtro_estados(page):
    print("8. Dejando 'Estados' en blanco para bajar todo el reporte...")

    select_estados = page.locator("#PedidoEstado")
    select_estados.wait_for(state="visible", timeout=30000)

    # 1) intento directo por value vacío
    try:
        select_estados.select_option(value="")
        page.wait_for_timeout(800)
        print("   Estados limpiado con value vacío.")
        return
    except:
        pass

    # 2) intento por label vacío
    try:
        select_estados.select_option(label="")
        page.wait_for_timeout(800)
        print("   Estados limpiado con label vacío.")
        return
    except:
        pass

    # 3) intento seleccionando la primera opción del combo
    try:
        opciones = select_estados.locator("option")
        cantidad = opciones.count()

        if cantidad > 0:
            primer_valor = opciones.nth(0).get_attribute("value")
            if primer_valor is None:
                primer_valor = ""
            select_estados.select_option(value=primer_valor)
            page.wait_for_timeout(800)
            print("   Estados limpiado con la primera opción del combo.")
            return
    except:
        pass

    # 4) fallback por JS
    try:
        page.evaluate("""
            () => {
                const sel = document.querySelector('#PedidoEstado');
                if (!sel) throw new Error('No se encontró #PedidoEstado');
                sel.selectedIndex = 0;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        page.wait_for_timeout(800)
        print("   Estados limpiado por JavaScript.")
        return
    except Exception as e:
        raise Exception(f"No se pudo limpiar el filtro de Estados: {e}")


def main():
    CARPETA_DESCARGAS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            hacer_login(page)

            print("6. Abriendo HOME...")
            page.goto(URL_HOME, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

            print("7. Haciendo click en Ir a Pedidos...")
            boton_ir_pedidos = page.get_by_role("link", name="Ir a Pedidos").first
            boton_ir_pedidos.wait_for(state="visible", timeout=30000)
            boton_ir_pedidos.click()

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            limpiar_filtro_estados(page)

            print("9. Abriendo menú Opciones...")
            page.get_by_role("button", name="OPCIONES").click()
            page.wait_for_timeout(1000)

            print("10. Haciendo click en Descargar...")
            with page.expect_download(timeout=60000) as download_info:
                page.get_by_text("Descargar", exact=True).click()

            download = download_info.value
            nombre_sugerido = download.suggested_filename
            extension = Path(nombre_sugerido).suffix if nombre_sugerido else ".csv"

            ruta_temporal = CARPETA_DESCARGAS / f"{NOMBRE_TEMPORAL}{extension}"
            ruta_final = CARPETA_DESCARGAS / NOMBRE_FINAL

            download.save_as(str(ruta_temporal))
            print(f"Descarga temporal completada: {ruta_temporal}")

            print("11. Generando Excel final para BI...")
            convertir_a_excel_final(ruta_temporal, ruta_final)

            print(f"Proceso finalizado. Archivo listo para BI: {ruta_final}")

        except PlaywrightTimeoutError as e:
            print("Timeout: no se encontró un elemento o no terminó la descarga.")
            print(e)
            try:
                page.screenshot(path="error_timeout_pedidos.png", full_page=True)
                print("Se guardó captura: error_timeout_pedidos.png")
            except:
                pass

        except Exception as e:
            print("Ocurrió un error durante la automatización.")
            print(e)
            try:
                page.screenshot(path="error_general_pedidos.png", full_page=True)
                print("Se guardó captura: error_general_pedidos.png")
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