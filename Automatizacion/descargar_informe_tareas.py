from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://app.digipwms.com"
URL_HOME = "https://app.digipwms.com/home"

USUARIO = "igoyena"
CLAVE = "0802"

CARPETA_DESTINO = Path(
    r"G:\Mi unidad\Sistema_Logistico_Peirano\data"
)

NOMBRE_ARCHIVO = "Informe Tareas"


# -------------------------------------------------------
# LOGIN
# -------------------------------------------------------

def hacer_login(page):

    print("1. Abriendo login DIGIP...")

    page.goto(URL_LOGIN, wait_until="domcontentloaded")

    page.wait_for_timeout(2500)

    print("2. Completando usuario...")

    page.locator(
        'input[name="username"], input[type="text"]'
    ).first.fill(USUARIO)

    print("3. Completando contraseña...")

    page.locator(
        'input[name="password"], input[type="password"]'
    ).first.fill(CLAVE)

    print("4. Haciendo click en INGRESAR...")

    page.get_by_role(
        "button",
        name="INGRESAR"
    ).click()

    print("5. Esperando ingreso...")

    page.wait_for_timeout(3500)

    page.goto(
        URL_HOME,
        wait_until="domcontentloaded"
    )

    page.wait_for_timeout(2000)


# -------------------------------------------------------
# IR A TAREAS
# -------------------------------------------------------

def abrir_tareas(page):

    print("6. Abriendo HOME...")
    page.goto(URL_HOME, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    print("7. Navegando a Tareas por JavaScript...")

    page.evaluate("""
        () => {
            window.location.href =
            '/Deposito/tarea?tareaestado=0&isdeleted=false';
        }
    """)

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(4000)

    print("8. Esperando filtro Estado...")

    page.locator("#TareaEstado").wait_for(
        state="visible",
        timeout=30000
    )

    print("Módulo Tareas abierto correctamente.")
# -------------------------------------------------------
# LIMPIAR ESTADO
# -------------------------------------------------------

def limpiar_estado(page):

    print("8. Dejando Estado en blanco...")

    select_estado = page.locator("#TareaEstado")

    select_estado.wait_for(
        state="visible",
        timeout=30000
    )

    # Intento principal
    try:

        select_estado.select_option(value="")

        page.wait_for_timeout(800)

        print("Estado limpiado.")

        return

    except:

        pass

    # Fallback
    try:

        page.evaluate("""

            () => {

                const sel = document.querySelector("#TareaEstado");

                sel.selectedIndex = 0;

                sel.dispatchEvent(
                    new Event(
                        "change",
                        { bubbles: true }
                    )
                );

            }

        """)

        page.wait_for_timeout(800)

        print("Estado limpiado por JS.")

        return

    except Exception as e:

        raise Exception(
            f"No se pudo limpiar Estado: {e}"
        )


# -------------------------------------------------------
# BUSCAR
# -------------------------------------------------------

def ejecutar_busqueda(page):

    print("9. Ejecutando búsqueda...")

    boton = page.locator(
        "button[name='accion'][value='consulta']"
    )

    boton.wait_for(
        state="visible",
        timeout=30000
    )

    boton.click()

    page.wait_for_timeout(5000)

    print("Búsqueda finalizada.")


# -------------------------------------------------------
# DESCARGA
# -------------------------------------------------------

def descargar_reporte(page):

    print("10. Descargando reporte...")

    boton = page.locator(
        "button[name='accion'][value='descarga']"
    )

    boton.wait_for(
        state="visible",
        timeout=30000
    )

    with page.expect_download(
        timeout=60000
    ) as download_info:

        boton.click()

    download = download_info.value

    extension = Path(
        download.suggested_filename
    ).suffix

    ruta_final = (
        CARPETA_DESTINO /
        f"{NOMBRE_ARCHIVO}{extension}"
    )

    download.save_as(
        str(ruta_final)
    )

    print("")

    print("Reporte descargado:")

    print(ruta_final)
# -------------------------------------------------------
# MAIN
# -------------------------------------------------------

def main():

    CARPETA_DESTINO.mkdir(
        parents=True,
        exist_ok=True
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            accept_downloads=True
        )

        page = context.new_page()

        try:

            hacer_login(page)

            abrir_tareas(page)

            limpiar_estado(page)

            ejecutar_busqueda(page)

            descargar_reporte(page)

            print("")
            print("========================================")
            print(" DESCARGA FINALIZADA CORRECTAMENTE ")
            print("========================================")

        except PlaywrightTimeoutError as e:

            print("")
            print("TIMEOUT")
            print(e)

            try:

                page.screenshot(
                    path="error_timeout_informe_tareas.png",
                    full_page=True
                )

                print("Captura guardada.")

            except:

                pass

        except Exception as e:

            print("")
            print("ERROR GENERAL")
            print(e)

            try:

                page.screenshot(
                    path="error_general_informe_tareas.png",
                    full_page=True
                )

                print("Captura guardada.")

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
