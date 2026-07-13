from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://app.digipwms.com"
USUARIO = "igoyena"
CLAVE = "0802"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
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

        # Guardar sesión
        context.storage_state(path="digip_session.json")
        print("Sesión guardada en digip_session.json")

    except PlaywrightTimeoutError as e:
        print("Timeout durante el login.")
        print(e)
        try:
            page.screenshot(path="error_login_timeout.png", full_page=True)
            print("Se guardó captura: error_login_timeout.png")
        except:
            pass

    except Exception as e:
        print("Ocurrió un error durante el login.")
        print(e)
        try:
            page.screenshot(path="error_login_general.png", full_page=True)
            print("Se guardó captura: error_login_general.png")
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