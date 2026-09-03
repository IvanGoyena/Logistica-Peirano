from pathlib import Path
from datetime import datetime
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL_LOGIN = "https://app.digipwms.com"
URL_HOME = "https://app.digipwms.com/home"

USUARIO = "igoyena"
CLAVE = "0802"

CARPETA_DESTINO = Path(r"C:\Sistema_Logistico_Peirano\Data_WMS")

PROYECTO = Path(r"C:\Sistema_Logistico_Peirano")

if str(PROYECTO) not in sys.path:
    sys.path.insert(0, str(PROYECTO))

from utils.github_uploader import (
    GitHubUploaderError,
    subir_archivo_github,
)

MESES_ES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}


def elegir_mes_anio():
    hoy = datetime.now()

    print()
    print("=== DESCARGA HISTORICA PRODUCTIVIDAD ===")
    print("Elegí el mes que querés descargar/reemplazar:")
    for numero, nombre in MESES_ES.items():
        print(f"{numero:>2} - {nombre}")

    while True:
        valor_mes = input(f"Mes [1-12] (Enter = {hoy.month}): ").strip()
        if not valor_mes:
            numero_mes = hoy.month
            break
        try:
            numero_mes = int(valor_mes)
            if numero_mes in MESES_ES:
                break
        except ValueError:
            pass
        print("Mes inválido. Ingresá un número del 1 al 12.")

    while True:
        valor_anio = input(f"Año (Enter = {hoy.year}): ").strip()
        if not valor_anio:
            anio = hoy.year
            break
        try:
            anio = int(valor_anio)
            if 2000 <= anio <= 2100:
                break
        except ValueError:
            pass
        print("Año inválido. Ejemplo: 2026.")

    return numero_mes, MESES_ES[numero_mes], anio


def nombres_archivos_mes(mes, anio):
    return (
        f"Preparacion {mes} {anio}.csv",
        f"Control {mes} {anio}.csv",
    )


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


def abrir_analitico_desde_externos(page):
    print("6. Abriendo menú Externos...")
    menu_externos = page.get_by_role("link", name="Externos").first
    menu_externos.wait_for(state="visible", timeout=30000)
    menu_externos.hover()
    page.wait_for_timeout(1200)

    print("7. Haciendo click en Analitico...")
    enlace_analitico = page.get_by_text("Analitico", exact=True).first
    enlace_analitico.wait_for(state="visible", timeout=30000)

    with page.expect_popup(timeout=30000) as popup_info:
        enlace_analitico.click(force=True)

    pagina_analitico = popup_info.value
    pagina_analitico.wait_for_load_state("domcontentloaded")
    pagina_analitico.wait_for_load_state("networkidle")
    # La pantalla Analítico puede tardar en renderizar el menú de Tareas.
    pagina_analitico.wait_for_timeout(5000)

    pagina_analitico.get_by_text("Tareas (Beta)", exact=True).first.wait_for(
        state="visible",
        timeout=60000,
    )

    return pagina_analitico


def ir_a_tareas_beta(page):
    print("8. Abriendo Tareas (Beta)...")

    candidatos = [
        page.get_by_role("link", name="Tareas (Beta)").first,
        page.get_by_text("Tareas (Beta)", exact=True).first,
        page.locator('a[href="#tareas"]').first,
    ]

    for candidato in candidatos:
        try:
            if candidato.count() > 0:
                candidato.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                candidato.click(force=True)
                # Espera adicional para que carguen las tablas luego de abrir Tareas (Beta).
                page.wait_for_timeout(8000)
                return
        except:
            pass

    raise Exception("No se pudo abrir la sección Tareas (Beta).")


def obtener_tabla_por_titulo(page, titulo):
    posibles = [
        page.locator(f"text={titulo}").locator("xpath=following::table[1]").first,
        page.get_by_text(titulo, exact=True).locator("xpath=following::table[1]").first,
    ]

    for tabla in posibles:
        try:
            if tabla.count() > 0:
                tabla.wait_for(state="visible", timeout=60000)
                return tabla
        except:
            pass

    raise Exception(f"No se encontró la tabla de {titulo}.")


def obtener_fila_mes(tabla, mes, anio):
    filas = tabla.locator("tbody tr")
    total = filas.count()

    mes_upper = mes.upper()
    anio_texto = str(anio)

    # Primero intenta encontrar MES + AÑO, para evitar elegir una fila
    # del mismo mes correspondiente a otro año.
    for i in range(total):
        fila = filas.nth(i)
        texto = fila.inner_text().upper()
        if mes_upper in texto and anio_texto in texto:
            return fila

    # Compatibilidad por si DIGIP muestra únicamente el nombre del mes.
    coincidencias = []
    for i in range(total):
        fila = filas.nth(i)
        texto = fila.inner_text().upper()
        if mes_upper in texto:
            coincidencias.append(fila)

    if len(coincidencias) == 1:
        print(
            f"ADVERTENCIA: DIGIP no mostró el año en la fila. "
            f"Se utilizará la única coincidencia encontrada para {mes}."
        )
        return coincidencias[0]

    raise Exception(
        f"No se encontró una fila inequívoca para {mes} {anio}. "
        f"Coincidencias por mes: {len(coincidencias)}."
    )


def descargar_desde_fila(page, fila, ruta_destino, nombre_archivo, titulo):
    ruta_destino.mkdir(parents=True, exist_ok=True)
    ruta_final = ruta_destino / nombre_archivo

    # Reemplaza el archivo del mes si ya existe.
    if ruta_final.exists():
        ruta_final.unlink()

    print(f"Descargando {titulo}...")

    candidatos = [
        fila.locator("a").first,
        fila.locator("button").first,
        fila.locator("svg").first,
        fila.locator("i").first,
    ]

    for candidato in candidatos:
        try:
            if candidato.count() > 0:
                with page.expect_download(timeout=60000) as download_info:
                    candidato.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    try:
                        candidato.click(force=True)
                    except:
                        box = candidato.bounding_box()
                        if box:
                            x = box["x"] + box["width"] / 2
                            y = box["y"] + box["height"] / 2
                            page.mouse.move(x, y, steps=10)
                            page.wait_for_timeout(200)
                            page.mouse.click(x, y)
                        else:
                            raise

                download = download_info.value
                download.save_as(str(ruta_final))
                print(f"{titulo} descargado en: {ruta_final}")
                return ruta_final
        except:
            pass

    raise Exception(f"No se pudo descargar {titulo}.")



def publicar_github(ruta_local: Path, titulo: str) -> None:
    ruta_github = f"Data_WMS/{ruta_local.name}"

    print()
    print(f"Publicando {titulo} en GitHub...")

    resultado = subir_archivo_github(
        archivo_local=ruta_local,
        ruta_github=ruta_github,
        mensaje_commit=(
            "Actualización automática WMS - "
            f"{titulo} - {datetime.now():%d/%m/%Y %H:%M:%S}"
        ),
    )

    if not resultado.get("ok"):
        raise GitHubUploaderError(
            f"GitHub no confirmó la actualización de {titulo}."
        )

    print("GitHub actualizado correctamente.")
    print(f"HTTP: {resultado['status']}")
    print(f"Commit: {resultado['commit_sha'][:12]}")



def main():
    numero_mes, mes_elegido, anio_elegido = elegir_mes_anio()
    nombre_preparacion, nombre_control = nombres_archivos_mes(
        mes_elegido,
        anio_elegido,
    )

    print()
    print(f"Mes seleccionado: {mes_elegido} {anio_elegido}")
    print(f"Archivo de Preparacion: {nombre_preparacion}")
    print(f"Archivo de Control: {nombre_control}")
    print(
        "IMPORTANTE: si esos archivos ya existen localmente o en GitHub, "
        "serán reemplazados."
    )

    confirmar = input("¿Continuar? [S/n]: ").strip().lower()
    if confirmar not in ("", "s", "si", "sí"):
        print("Proceso cancelado.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            hacer_login(page)

            pagina_analitico = abrir_analitico_desde_externos(page)
            ir_a_tareas_beta(pagina_analitico)

            print("9. Buscando tabla de Tareas...")
            tabla_tareas = obtener_tabla_por_titulo(pagina_analitico, "Tareas")
            fila_tareas = obtener_fila_mes(tabla_tareas, mes_elegido, anio_elegido)

            ruta_preparacion = descargar_desde_fila(
                page=pagina_analitico,
                fila=fila_tareas,
                ruta_destino=CARPETA_DESTINO,
                nombre_archivo=nombre_preparacion,
                titulo="Preparacion"
            )

            publicar_github(
                ruta_preparacion,
                "Preparacion",
            )

            pagina_analitico.wait_for_timeout(1500)

            print("10. Buscando tabla de Control...")
            tabla_control = obtener_tabla_por_titulo(pagina_analitico, "Control")
            fila_control = obtener_fila_mes(tabla_control, mes_elegido, anio_elegido)

            ruta_control = descargar_desde_fila(
                page=pagina_analitico,
                fila=fila_control,
                ruta_destino=CARPETA_DESTINO,
                nombre_archivo=nombre_control,
                titulo="Control"
            )

            publicar_github(
                ruta_control,
                "Control",
            )

            print("Proceso finalizado correctamente.")

        except PlaywrightTimeoutError as e:
            print("Timeout durante la automatización.")
            print(e)
            try:
                page.screenshot(path="error_timeout_productividad_analitico.png", full_page=True)
                print("Se guardó captura: error_timeout_productividad_analitico.png")
            except:
                pass
            raise

        except Exception as e:
            print("Ocurrió un error durante la automatización.")
            print(e)
            try:
                page.screenshot(path="error_general_productividad_analitico.png", full_page=True)
                print("Se guardó captura: error_general_productividad_analitico.png")
            except:
                pass
            raise

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