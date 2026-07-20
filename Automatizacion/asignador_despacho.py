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
from Automatizacion.tipo_preparacion import (
    seleccionar_tipo_preparacion_pedido,
)


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

TIMEOUT_MS = 30_000
ESPERA_CARGA_MS = 1_500
ESPERA_POST_ASIGNACION_MS = 10_000


# ==========================================================
# UTILIDADES DE NAVEGACIÓN
# ==========================================================

def ir_arriba(page: Page) -> None:
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1_200)


def bajar_hasta_tabla_despachos(page: Page) -> None:
    page.evaluate(
        "window.scrollTo(0, document.body.scrollHeight * 0.55)"
    )
    page.wait_for_timeout(1_200)


def bajar_al_final(page: Page) -> None:
    page.evaluate(
        "window.scrollTo(0, document.body.scrollHeight)"
    )
    page.wait_for_timeout(1_500)


def esperar_networkidle(page: Page) -> None:
    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        print(
            "   La página no llegó a networkidle; "
            "se continúa."
        )


# ==========================================================
# CLICS REFORZADOS
# ==========================================================

def click_humano(
    locator,
    page: Page,
) -> bool:
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


def click_relativo(
    locator,
    page: Page,
    x_ratio: float = 0.5,
    y_ratio: float = 0.5,
) -> None:
    locator.wait_for(
        state="visible",
        timeout=5_000,
    )

    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    caja = locator.bounding_box()

    if not caja:
        raise RuntimeError(
            "No se pudo obtener la posición del elemento."
        )

    x = caja["x"] + caja["width"] * x_ratio
    y = caja["y"] + caja["height"] * y_ratio

    page.mouse.move(
        x,
        y,
        steps=15,
    )
    page.wait_for_timeout(250)
    page.mouse.click(x, y)
    page.wait_for_timeout(1_000)


# ==========================================================
# SELECCIÓN DEL DESPACHO
# ==========================================================

def radio_despacho_esta_seleccionado(
    fila,
) -> bool:
    try:
        radio = fila.locator(
            'input[type="radio"]'
        ).first

        if radio.count() == 0:
            return False

        return radio.is_checked()

    except Exception:
        return False


def seleccionar_radio_despacho_reforzado(
    fila,
    despacho_objetivo: str,
    page: Page,
) -> bool:
    if radio_despacho_esta_seleccionado(fila):
        print(
            f"   El despacho ya estaba seleccionado: "
            f"{despacho_objetivo}"
        )
        return True

    # Estrategia 1: clic relativo en la primera celda.
    try:
        primera_celda = fila.locator("td").first

        click_relativo(
            locator=primera_celda,
            page=page,
            x_ratio=0.25,
            y_ratio=0.50,
        )

        if radio_despacho_esta_seleccionado(fila):
            print(
                f"   Despacho seleccionado: "
                f"{despacho_objetivo} (celda)"
            )
            return True

    except Exception:
        pass

    # Estrategia 2: clic directo sobre el radio.
    try:
        radio = fila.locator(
            'input[type="radio"]'
        ).first

        if radio.count() > 0:
            radio.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            radio.click(force=True)
            page.wait_for_timeout(1_000)

            if radio_despacho_esta_seleccionado(fila):
                print(
                    f"   Despacho seleccionado: "
                    f"{despacho_objetivo} (radio)"
                )
                return True

    except Exception:
        pass

    # Estrategia 3: primer input de la fila.
    try:
        input_fila = fila.locator("input").first

        if input_fila.count() > 0:
            input_fila.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            input_fila.click(force=True)
            page.wait_for_timeout(1_000)

            if radio_despacho_esta_seleccionado(fila):
                print(
                    f"   Despacho seleccionado: "
                    f"{despacho_objetivo} (input)"
                )
                return True

    except Exception:
        pass

    # Estrategia 4: JavaScript.
    try:
        radio = fila.locator(
            'input[type="radio"]'
        ).first

        handle = radio.element_handle()

        if handle:
            page.evaluate(
                "(elemento) => elemento.click()",
                handle,
            )
            page.wait_for_timeout(1_000)

            if radio_despacho_esta_seleccionado(fila):
                print(
                    f"   Despacho seleccionado: "
                    f"{despacho_objetivo} (JavaScript)"
                )
                return True

    except Exception:
        pass

    print(
        "   Se encontró el despacho, pero no pudo "
        f"seleccionarse: {despacho_objetivo}"
    )

    return False


def abrir_seccion_despacho(page: Page) -> None:
    print("1. Abriendo la sección Despacho...")

    ir_arriba(page)

    tab_despacho = page.locator(
        'a[href="#Despacho"]'
    ).first

    tab_despacho.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    tab_despacho.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    tab_despacho.click(force=True)

    esperar_networkidle(page)
    page.wait_for_timeout(ESPERA_CARGA_MS)

    print("   Sección Despacho abierta.")


def buscar_y_seleccionar_despacho(
    page: Page,
    despacho_objetivo: str,
) -> None:
    despacho = str(despacho_objetivo).strip()

    if not despacho:
        raise ValueError(
            "El despacho objetivo no puede estar vacío."
        )

    print(
        f"2. Buscando despacho: {despacho}..."
    )

    bajar_hasta_tabla_despachos(page)

    filas = page.locator("tbody tr").filter(
        has_text=despacho
    )

    cantidad = filas.count()

    if cantidad == 0:
        raise RuntimeError(
            f"No se encontró el despacho: {despacho}"
        )

    fila_visible = None

    for indice in range(cantidad):
        fila = filas.nth(indice)

        try:
            if fila.is_visible():
                fila_visible = fila
                break
        except Exception:
            continue

    if fila_visible is None:
        raise RuntimeError(
            f"El despacho existe, pero no está visible: {despacho}"
        )

    fila_visible.scroll_into_view_if_needed()
    page.wait_for_timeout(500)

    print(
        f"3. Seleccionando despacho: {despacho}..."
    )

    seleccionado = seleccionar_radio_despacho_reforzado(
        fila=fila_visible,
        despacho_objetivo=despacho,
        page=page,
    )

    if not seleccionado:
        raise RuntimeError(
            f"No se pudo seleccionar el despacho: {despacho}"
        )


def seleccionar_despacho(
    page: Page,
    despacho_objetivo: str,
) -> None:
    abrir_seccion_despacho(page)

    buscar_y_seleccionar_despacho(
        page=page,
        despacho_objetivo=despacho_objetivo,
    )

    print("=" * 60)
    print(
        f"DESPACHO SELECCIONADO: {despacho_objetivo}"
    )
    print("=" * 60)


# ==========================================================
# ASIGNACIÓN MANUAL
# ==========================================================

def asignar_despacho_manual(
    page: Page,
) -> None:
    print(
        "4. Buscando botón Asigna Despacho Manual..."
    )

    bajar_al_final(page)

    dialogo_detectado = {
        "aceptado": False,
        "mensaje": "",
    }

    def manejar_dialogo(dialog) -> None:
        dialogo_detectado["mensaje"] = dialog.message

        print(
            f"   Diálogo detectado: {dialog.message}"
        )

        dialog.accept()
        dialogo_detectado["aceptado"] = True

    page.once(
        "dialog",
        manejar_dialogo,
    )

    boton_manual = page.locator(
        "#btnDespachoManual"
    ).first

    boton_manual.wait_for(
        state="visible",
        timeout=TIMEOUT_MS,
    )

    boton_manual.scroll_into_view_if_needed()
    page.wait_for_timeout(300)

    print(
        "5. Ejecutando Asigna Despacho Manual..."
    )

    click_realizado = False

    try:
        click_realizado = click_humano(
            locator=boton_manual,
            page=page,
        )
    except Exception:
        pass

    if not click_realizado:
        try:
            boton_manual.click(force=True)
            page.wait_for_timeout(1_000)
            click_realizado = True
        except Exception:
            pass

    if not click_realizado:
        try:
            handle = boton_manual.element_handle()

            if handle:
                page.evaluate(
                    "(elemento) => elemento.click()",
                    handle,
                )
                page.wait_for_timeout(1_000)
                click_realizado = True

        except Exception:
            pass

    if not click_realizado:
        raise RuntimeError(
            "No se pudo hacer clic en "
            "Asigna Despacho Manual."
        )

    print(
        "6. Esperando confirmación del sistema..."
    )

    page.wait_for_timeout(2_000)

    if not dialogo_detectado["aceptado"]:
        print(
            "   No se detectó diálogo automáticamente. "
            "Se enviará ENTER como respaldo."
        )

        try:
            page.keyboard.press("Enter")
            page.wait_for_timeout(1_000)
        except Exception:
            pass

    print(
        f"7. Esperando "
        f"{ESPERA_POST_ASIGNACION_MS // 1000} segundos "
        "a que DIGIP termine el proceso..."
    )

    page.wait_for_timeout(
        ESPERA_POST_ASIGNACION_MS
    )

    print("=" * 60)
    print("ASIGNACIÓN MANUAL EJECUTADA")
    print("=" * 60)


def seleccionar_y_asignar_despacho(
    page: Page,
    despacho_objetivo: str,
) -> None:
    """
    Selecciona el despacho y confirma la asignación manual.
    """

    seleccionar_despacho(
        page=page,
        despacho_objetivo=despacho_objetivo,
    )

    asignar_despacho_manual(
        page=page
    )


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

    despacho_prueba = input(
        "Despacho DIGIP para asignar "
        "[CAMIONETA 1]: "
    ).strip() or "CAMIONETA 1"

    print()
    print("=" * 60)
    print("ATENCIÓN")
    print(
        "Esta prueba ejecutará la asignación real "
        "en DIGIP."
    )
    print(
        f"Despacho objetivo: {despacho_prueba}"
    )
    print("=" * 60)

    confirmacion = input(
        "Escribí CONFIRMAR para continuar: "
    ).strip().upper()

    if confirmacion != "CONFIRMAR":
        print("Prueba cancelada.")
        return

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

        if not resultado.completo:
            raise RuntimeError(
                "No se seleccionaron todos los pedidos. "
                "La asignación fue cancelada por seguridad."
            )

        seleccionar_tipo_preparacion_pedido(
            page=page
        )

        seleccionar_y_asignar_despacho(
            page=page,
            despacho_objetivo=despacho_prueba,
        )

        print()
        print(
            "Prueba completa finalizada correctamente."
        )

        input(
            "Presioná ENTER para cerrar el navegador..."
        )


if __name__ == "__main__":
    main()
