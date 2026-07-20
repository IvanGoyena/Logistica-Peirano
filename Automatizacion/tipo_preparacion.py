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


from Automatizacion.digip_session import DigipSession
from Automatizacion.navegacion_digip import abrir_nueva_preparacion
from Automatizacion.selector_pedidos import seleccionar_pedidos


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

TIMEOUT_MS = 30_000
ESPERA_CARGA_MS = 1_500


# ==========================================================
# UTILIDADES
# ==========================================================

def ir_arriba(page: Page) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1_000)


def bajar_hasta_tipo_preparacion(page: Page) -> None:
    page.evaluate(
        "window.scrollTo(0, document.body.scrollHeight * 0.35)"
    )
    page.wait_for_timeout(1_000)


def click_humano(
    locator,
    page: Page,
) -> bool:
    """
    Intenta un clic similar al ejecutador original.
    """

    locator.wait_for(
        state="visible",
        timeout=5_000,
    )

    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    try:
        locator.hover()
        page.wait_for_timeout(250)
    except Exception:
        pass

    try:
        caja = locator.bounding_box()

        if caja:
            x = caja["x"] + caja["width"] / 2
            y = caja["y"] + caja["height"] / 2

            page.mouse.move(
                x,
                y,
                steps=12,
            )

            page.wait_for_timeout(200)
            page.mouse.click(x, y)
            page.wait_for_timeout(900)

            return True

    except Exception:
        pass

    try:
        locator.click(force=True)
        page.wait_for_timeout(900)

        return True

    except Exception:
        return False


# ==========================================================
# TIPO DE PREPARACIÓN
# ==========================================================

def abrir_tipo_preparacion(page: Page) -> None:
    print("1. Abriendo la sección Tipo preparación...")

    ir_arriba(page)

    tab_tipo = page.locator(
        'a[href="#TipoPreparacion"]'
    ).first

    tab_tipo.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    tab_tipo.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    tab_tipo.click(force=True)

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        print(
            "   La sección no llegó a networkidle; "
            "se continúa."
        )

    page.wait_for_timeout(ESPERA_CARGA_MS)

    print("   Sección Tipo preparación abierta.")


def seleccionar_opcion_pedido(page: Page) -> None:
    print("2. Buscando el bloque Pedidos individuales...")

    bajar_hasta_tipo_preparacion(page)

    bloque = page.locator("div").filter(
        has_text="Pedidos individuales"
    ).first

    bloque.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    bloque.scroll_into_view_if_needed()
    page.wait_for_timeout(400)

    print("3. Seleccionando PEDIDO...")

    candidatos = [
        bloque.get_by_role(
            "button",
            name="PEDIDO",
        ).first,
        bloque.get_by_text(
            "PEDIDO",
            exact=True,
        ).first,
        bloque.locator("button").filter(
            has_text="PEDIDO"
        ).first,
        bloque.locator("a").filter(
            has_text="PEDIDO"
        ).first,
        bloque.locator("label").filter(
            has_text="PEDIDO"
        ).first,
        bloque.locator("span").filter(
            has_text="PEDIDO"
        ).first,
    ]

    for candidato in candidatos:
        try:
            if candidato.count() == 0:
                continue

            if click_humano(
                locator=candidato,
                page=page,
            ):
                print(
                    "   Opción PEDIDO seleccionada."
                )
                page.wait_for_timeout(1_200)
                return

        except Exception:
            continue

    try:
        radio = bloque.locator(
            'input[type="radio"]'
        ).first

        if radio.count() > 0:
            radio.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            radio.click(force=True)
            page.wait_for_timeout(1_200)

            print(
                "   Opción PEDIDO seleccionada por radio."
            )
            return

    except Exception:
        pass

    try:
        radio = bloque.locator(
            'input[type="radio"]'
        ).first

        handle = radio.element_handle()

        if handle:
            page.evaluate(
                "(elemento) => elemento.click()",
                handle,
            )

            page.wait_for_timeout(1_200)

            print(
                "   Opción PEDIDO seleccionada "
                "mediante JavaScript."
            )
            return

    except Exception:
        pass

    raise RuntimeError(
        "No se pudo seleccionar la opción PEDIDO "
        "en Tipo preparación."
    )


def seleccionar_tipo_preparacion_pedido(
    page: Page,
) -> None:
    """
    Ejecuta el paso completo para asignar el tipo PEDIDO.
    """

    abrir_tipo_preparacion(page)
    seleccionar_opcion_pedido(page)

    print("=" * 60)
    print("TIPO DE PREPARACIÓN SELECCIONADO: PEDIDO")
    print("=" * 60)


# ==========================================================
# PRUEBA DIRECTA
# ==========================================================

def solicitar_pedidos_prueba() -> list[str]:
    texto = input(
        "Ingresá los números de pedido separados por coma: "
    )

    return [
        pedido.strip()
        for pedido in texto.split(",")
        if pedido.strip()
    ]


def main() -> None:
    codigo_prueba = input(
        "Código de despacho para la prueba "
        "[0501]: "
    ).strip() or "0501"

    pedidos_prueba = solicitar_pedidos_prueba()

    if not pedidos_prueba:
        raise ValueError(
            "Tenés que ingresar al menos un pedido."
        )

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

        resultado = seleccionar_pedidos(
            page=page,
            pedidos=pedidos_prueba,
        )

        if not resultado.seleccionados:
            raise RuntimeError(
                "No se seleccionó ningún pedido. "
                "No se continuará con Tipo preparación."
            )

        seleccionar_tipo_preparacion_pedido(
            page=page
        )

        print()
        print(
            "La prueba quedó detenida después de "
            "seleccionar PEDIDO."
        )

        input(
            "Revisá la pantalla y presioná ENTER "
            "para cerrar..."
        )


if __name__ == "__main__":
    main()
