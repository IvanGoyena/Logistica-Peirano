from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)


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

URL_HOME = f"{str(URL).rstrip('/')}/home"

TIMEOUT_MS = 30_000
ESPERA_ENTRE_PASOS_MS = 1_000
ESPERA_FILTRO_MS = 2_500

CallbackEstado = Callable[[str, str], None]


# ==========================================================
# UTILIDADES
# ==========================================================

def registrar_paso(
    mensaje: str,
    callback: CallbackEstado | None = None,
    etapa: str = "navegacion",
) -> None:
    print(mensaje, flush=True)

    if callback is not None:
        callback(etapa, mensaje)


def describir_pagina(page: Page) -> str:
    try:
        titulo = page.title()
    except Exception:
        titulo = "sin título"

    return f"URL={page.url} | título={titulo}"


def esperar_carga(
    page: Page,
    callback: CallbackEstado | None = None,
) -> None:
    """
    Espera la carga principal sin detener el proceso cuando DIGIP
    mantiene solicitudes abiertas y no alcanza networkidle.
    """

    try:
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        registrar_paso(
            "La página no llegó a domcontentloaded; se continúa.",
            callback,
        )

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=8_000,
        )
    except PlaywrightTimeoutError:
        registrar_paso(
            "La página no llegó a networkidle; se continúa.",
            callback,
        )


def primer_locator_visible(
    candidatos: list[Locator],
    descripcion: str,
    page: Page,
    callback: CallbackEstado | None = None,
    timeout_total_ms: int = TIMEOUT_MS,
) -> Locator:
    """
    Prueba varios selectores hasta encontrar un elemento visible.
    Esto evita depender de un único texto o rol exacto.
    """

    if not candidatos:
        raise ValueError("No se recibieron selectores candidatos.")

    espera_por_candidato = max(
        2_000,
        int(timeout_total_ms / len(candidatos)),
    )

    errores: list[str] = []

    for indice, candidato in enumerate(candidatos, start=1):
        try:
            if candidato.count() == 0:
                errores.append(f"selector {indice}: sin coincidencias")
                continue

            elemento = candidato.first

            elemento.wait_for(
                state="visible",
                timeout=espera_por_candidato,
            )

            registrar_paso(
                f"Elemento encontrado: {descripcion} "
                f"(estrategia {indice}).",
                callback,
            )

            return elemento

        except Exception as error:
            errores.append(
                f"selector {indice}: {type(error).__name__}"
            )

    detalle = " | ".join(errores)

    raise RuntimeError(
        f"No se encontró un elemento visible para '{descripcion}'. "
        f"{describir_pagina(page)}. Intentos: {detalle}"
    )


def click_reforzado(
    locator: Locator,
    page: Page,
    descripcion: str,
    callback: CallbackEstado | None = None,
) -> None:
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(250)

    errores: list[str] = []

    for nombre, accion in (
        ("clic normal", lambda: locator.click(timeout=5_000)),
        ("clic forzado", lambda: locator.click(force=True, timeout=5_000)),
        (
            "clic JavaScript",
            lambda: locator.evaluate("(elemento) => elemento.click()"),
        ),
    ):
        try:
            accion()
            page.wait_for_timeout(700)

            registrar_paso(
                f"{descripcion}: {nombre} realizado.",
                callback,
            )
            return

        except Exception as error:
            errores.append(
                f"{nombre}: {type(error).__name__}: {error}"
            )

    raise RuntimeError(
        f"No se pudo hacer clic en '{descripcion}'. "
        f"{describir_pagina(page)}. "
        + " | ".join(errores)
    )


def obtener_input_codigo_despacho(
    page: Page,
    callback: CallbackEstado | None = None,
) -> Locator:
    """
    Localiza el filtro de CodigoDespacho con varias estrategias.
    """

    registrar_paso(
        "Buscando el filtro CodigoDespacho...",
        callback,
    )

    encabezados = [
        page.get_by_text(
            "CodigoDespacho",
            exact=True,
        ),
        page.get_by_text(
            "CódigoDespacho",
            exact=True,
        ),
        page.get_by_text(
            "Código Despacho",
            exact=False,
        ),
        page.locator("th").filter(
            has_text="CodigoDespacho"
        ),
    ]

    primer_locator_visible(
        candidatos=encabezados,
        descripcion="encabezado CodigoDespacho",
        page=page,
        callback=callback,
    )

    candidatos_input = [
        page.locator(
            'thead input[name*="CodigoDespacho" i]'
        ),
        page.locator(
            'thead input[placeholder*="CodigoDespacho" i]'
        ),
        page.locator("thead tr").nth(1).locator("input").nth(6),
        page.locator("thead input").nth(6),
    ]

    return primer_locator_visible(
        candidatos=candidatos_input,
        descripcion="filtro CodigoDespacho",
        page=page,
        callback=callback,
    )


# ==========================================================
# NAVEGACIÓN
# ==========================================================

def ir_a_home(
    page: Page,
    callback: CallbackEstado | None = None,
) -> None:
    registrar_paso(
        "1/5 — Abriendo HOME de DIGIP...",
        callback,
    )

    try:
        page.goto(
            URL_HOME,
            wait_until="domcontentloaded",
            timeout=TIMEOUT_MS,
        )

        esperar_carga(page, callback)
        page.wait_for_timeout(ESPERA_ENTRE_PASOS_MS)

        if "login" in page.url.lower():
            raise RuntimeError(
                "DIGIP redirigió nuevamente al login."
            )

        registrar_paso(
            f"HOME abierto correctamente. {describir_pagina(page)}",
            callback,
        )

    except Exception as error:
        raise RuntimeError(
            "Falló el ingreso al HOME de DIGIP. "
            f"{describir_pagina(page)}. Error: {error}"
        ) from error


def abrir_preparaciones(
    page: Page,
    callback: CallbackEstado | None = None,
) -> None:
    registrar_paso(
        "2/5 — Buscando acceso a Preparaciones...",
        callback,
    )

    candidatos = [
        page.get_by_role(
            "link",
            name="Ir a Preparaciones",
            exact=False,
        ),
        page.get_by_role(
            "link",
            name="Preparaciones",
            exact=False,
        ),
        page.get_by_text(
            "Ir a Preparaciones",
            exact=False,
        ),
        page.get_by_text(
            "Preparaciones",
            exact=True,
        ),
        page.locator(
            'a[href*="preparacion" i]'
        ),
    ]

    try:
        boton = primer_locator_visible(
            candidatos=candidatos,
            descripcion="acceso a Preparaciones",
            page=page,
            callback=callback,
        )

        click_reforzado(
            locator=boton,
            page=page,
            descripcion="Acceso a Preparaciones",
            callback=callback,
        )

        esperar_carga(page, callback)
        page.wait_for_timeout(ESPERA_ENTRE_PASOS_MS)

        registrar_paso(
            f"Módulo Preparaciones abierto. "
            f"{describir_pagina(page)}",
            callback,
        )

    except Exception as error:
        raise RuntimeError(
            "Falló el ingreso al módulo Preparaciones. "
            f"{describir_pagina(page)}. Error: {error}"
        ) from error


def abrir_menu_opciones(
    page: Page,
    callback: CallbackEstado | None = None,
) -> None:
    registrar_paso(
        "3/5 — Buscando el menú OPCIONES...",
        callback,
    )

    candidatos = [
        page.get_by_role(
            "button",
            name="OPCIONES",
            exact=False,
        ),
        page.get_by_text(
            "OPCIONES",
            exact=True,
        ),
        page.locator("button").filter(
            has_text="OPCIONES"
        ),
        page.locator(
            '[aria-label*="OPCIONES" i]'
        ),
    ]

    try:
        boton = primer_locator_visible(
            candidatos=candidatos,
            descripcion="botón OPCIONES",
            page=page,
            callback=callback,
        )

        click_reforzado(
            locator=boton,
            page=page,
            descripcion="Menú OPCIONES",
            callback=callback,
        )

        page.wait_for_timeout(800)

        registrar_paso(
            "Menú OPCIONES abierto.",
            callback,
        )

    except Exception as error:
        raise RuntimeError(
            "Falló la apertura del menú OPCIONES. "
            f"{describir_pagina(page)}. Error: {error}"
        ) from error


def abrir_nueva(
    page: Page,
    callback: CallbackEstado | None = None,
) -> None:
    registrar_paso(
        "4/5 — Buscando la opción Nueva...",
        callback,
    )

    candidatos = [
        page.get_by_role(
            "menuitem",
            name="Nueva",
            exact=False,
        ),
        page.get_by_role(
            "link",
            name="Nueva",
            exact=False,
        ),
        page.get_by_text(
            "Nueva",
            exact=True,
        ),
        page.locator("a").filter(
            has_text="Nueva"
        ),
        page.locator("button").filter(
            has_text="Nueva"
        ),
    ]

    try:
        opcion = primer_locator_visible(
            candidatos=candidatos,
            descripcion="opción Nueva",
            page=page,
            callback=callback,
        )

        click_reforzado(
            locator=opcion,
            page=page,
            descripcion="Opción Nueva",
            callback=callback,
        )

        esperar_carga(page, callback)
        page.wait_for_timeout(1_500)

        registrar_paso(
            f"Pantalla Nueva preparación abierta. "
            f"{describir_pagina(page)}",
            callback,
        )

    except Exception as error:
        raise RuntimeError(
            "Falló la apertura de Nueva preparación. "
            f"{describir_pagina(page)}. Error: {error}"
        ) from error


def filtrar_codigo_despacho(
    page: Page,
    codigo_despacho: str,
    callback: CallbackEstado | None = None,
) -> None:
    codigo = str(codigo_despacho).strip()

    if not codigo:
        raise ValueError(
            "El código de despacho no puede estar vacío."
        )

    registrar_paso(
        f"5/5 — Filtrando CodigoDespacho = {codigo}...",
        callback,
    )

    try:
        input_codigo = obtener_input_codigo_despacho(
            page=page,
            callback=callback,
        )

        input_codigo.scroll_into_view_if_needed()
        input_codigo.click(force=True)

        try:
            input_codigo.press("Control+A")
        except Exception:
            input_codigo.press("Meta+A")

        input_codigo.press("Backspace")
        input_codigo.fill(codigo)
        input_codigo.press("Enter")

        page.wait_for_timeout(ESPERA_FILTRO_MS)

        valor_actual = input_codigo.input_value().strip()

        if valor_actual != codigo:
            raise RuntimeError(
                "El filtro no conservó el valor esperado. "
                f"Esperado={codigo} | Actual={valor_actual}"
            )

        registrar_paso(
            f"Filtro CodigoDespacho aplicado correctamente: {codigo}.",
            callback,
        )

    except Exception as error:
        raise RuntimeError(
            "Falló la aplicación del filtro CodigoDespacho. "
            f"{describir_pagina(page)}. Error: {error}"
        ) from error


def abrir_nueva_preparacion(
    page: Page,
    codigo_despacho: str,
    callback: CallbackEstado | None = None,
) -> None:
    """
    Ejecuta el recorrido completo:

    HOME
    -> Preparaciones
    -> OPCIONES
    -> Nueva
    -> filtro CodigoDespacho

    El callback es opcional para conservar compatibilidad con
    las llamadas existentes.
    """

    try:
        ir_a_home(
            page=page,
            callback=callback,
        )

        abrir_preparaciones(
            page=page,
            callback=callback,
        )

        abrir_menu_opciones(
            page=page,
            callback=callback,
        )

        abrir_nueva(
            page=page,
            callback=callback,
        )

        filtrar_codigo_despacho(
            page=page,
            codigo_despacho=codigo_despacho,
            callback=callback,
        )

        registrar_paso(
            "NAVEGACIÓN COMPLETADA — "
            f"CodigoDespacho filtrado: {codigo_despacho}",
            callback,
        )

    except Exception as error:
        registrar_paso(
            f"ERROR DE NAVEGACIÓN — {error}",
            callback,
        )
        raise


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
