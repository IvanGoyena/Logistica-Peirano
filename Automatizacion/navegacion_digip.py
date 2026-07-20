from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


# ==========================================================
# RUTA DEL PROYECTO
# ==========================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from config import URL
from Automatizacion.digip_session import DigipSession


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

URL_HOME = f"{URL.rstrip('/')}/home"

TIMEOUT_MS = 30_000
ESPERA_ENTRE_PASOS_MS = 1_000
ESPERA_FILTRO_MS = 2_500


# ==========================================================
# UTILIDADES
# ==========================================================

def registrar_paso(mensaje: str) -> None:
    print(mensaje)


def esperar_carga(page: Page) -> None:
    """
    Espera la carga principal, pero no detiene el proceso si DIGIP
    mantiene solicitudes abiertas y no llega a networkidle.
    """

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        registrar_paso(
            "La página no llegó a networkidle; se continúa."
        )


def obtener_input_codigo_despacho(page: Page):
    """
    Devuelve el campo de filtro correspondiente a CodigoDespacho.

    Se conserva la estrategia que funcionó en los ejecutadores:
    encabezado CodigoDespacho + fila de filtros + séptimo input.
    """

    encabezado = page.get_by_text(
        "CodigoDespacho",
        exact=True,
    ).first

    encabezado.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    fila_filtros = page.locator("thead tr").nth(1)

    fila_filtros.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    input_codigo = fila_filtros.locator("input").nth(6)

    input_codigo.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    return input_codigo


# ==========================================================
# NAVEGACIÓN
# ==========================================================

def ir_a_home(page: Page) -> None:
    registrar_paso("1. Abriendo HOME de DIGIP...")

    page.goto(
        URL_HOME,
        wait_until="domcontentloaded",
        timeout=TIMEOUT_MS,
    )

    esperar_carga(page)
    page.wait_for_timeout(ESPERA_ENTRE_PASOS_MS)

    registrar_paso(f"   HOME abierto: {page.url}")


def abrir_preparaciones(page: Page) -> None:
    registrar_paso("2. Ingresando a Preparaciones...")

    boton_preparaciones = page.get_by_role(
        "link",
        name="Ir a Preparaciones",
    ).first

    boton_preparaciones.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    boton_preparaciones.click()

    esperar_carga(page)
    page.wait_for_timeout(ESPERA_ENTRE_PASOS_MS)

    registrar_paso("   Módulo Preparaciones abierto.")


def abrir_menu_opciones(page: Page) -> None:
    registrar_paso("3. Abriendo menú OPCIONES...")

    boton_opciones = page.get_by_role(
        "button",
        name="OPCIONES",
    ).first

    boton_opciones.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    boton_opciones.click()
    page.wait_for_timeout(800)

    registrar_paso("   Menú OPCIONES abierto.")


def abrir_nueva(page: Page) -> None:
    registrar_paso("4. Abriendo Nueva preparación...")

    opcion_nueva = page.get_by_text(
        "Nueva",
        exact=True,
    ).first

    opcion_nueva.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    opcion_nueva.click()

    esperar_carga(page)
    page.wait_for_timeout(1_500)

    registrar_paso("   Pantalla Nueva preparación abierta.")


def filtrar_codigo_despacho(
    page: Page,
    codigo_despacho: str,
) -> None:
    codigo = str(codigo_despacho).strip()

    if not codigo:
        raise ValueError(
            "El código de despacho no puede estar vacío."
        )

    registrar_paso(
        f"5. Filtrando por CodigoDespacho = {codigo}..."
    )

    input_codigo = obtener_input_codigo_despacho(page)

    input_codigo.click()
    input_codigo.press("Control+A")
    input_codigo.press("Backspace")
    input_codigo.fill(codigo)

    page.wait_for_timeout(ESPERA_FILTRO_MS)

    valor_actual = input_codigo.input_value().strip()

    if valor_actual != codigo:
        raise RuntimeError(
            "El filtro CodigoDespacho no quedó cargado correctamente. "
            f"Esperado: {codigo} | Actual: {valor_actual}"
        )

    registrar_paso(
        f"   Filtro aplicado correctamente: {codigo}"
    )


def abrir_nueva_preparacion(
    page: Page,
    codigo_despacho: str,
) -> None:
    """
    Ejecuta el recorrido completo:

    HOME
    -> Ir a Preparaciones
    -> OPCIONES
    -> Nueva
    -> filtro CodigoDespacho
    """

    ir_a_home(page)
    abrir_preparaciones(page)
    abrir_menu_opciones(page)
    abrir_nueva(page)
    filtrar_codigo_despacho(
        page=page,
        codigo_despacho=codigo_despacho,
    )

    registrar_paso("=" * 60)
    registrar_paso("NAVEGACIÓN COMPLETADA")
    registrar_paso(
        f"CodigoDespacho filtrado: {codigo_despacho}"
    )
    registrar_paso("=" * 60)


# ==========================================================
# PRUEBA DIRECTA
# ==========================================================

def main() -> None:
    codigo_prueba = "0501"

    with DigipSession(
        headless=False
    ) as sesion:

        page = sesion.page

        if page is None:
            raise RuntimeError(
                "No se pudo obtener la página DIGIP."
            )

        abrir_nueva_preparacion(
            page=page,
            codigo_despacho=codigo_prueba,
        )

        print()
        print(
            "La prueba quedó detenida en Nueva preparación "
            f"con CodigoDespacho = {codigo_prueba}."
        )

        input(
            "Revisá la pantalla y presioná ENTER para cerrar..."
        )


if __name__ == "__main__":
    main()
