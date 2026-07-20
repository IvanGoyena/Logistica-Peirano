from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Locator, Page


# ==========================================================
# RUTA DEL PROYECTO
# ==========================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from Automatizacion.digip_session import DigipSession
from Automatizacion.navegacion_digip import abrir_nueva_preparacion


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

TIMEOUT_MS = 30_000
ESPERA_ENTRE_PEDIDOS_MS = 500


# ==========================================================
# RESULTADO
# ==========================================================

@dataclass
class ResultadoSeleccion:
    solicitados: list[str] = field(default_factory=list)
    seleccionados: list[str] = field(default_factory=list)
    no_encontrados: list[str] = field(default_factory=list)
    no_seleccionados: list[str] = field(default_factory=list)

    @property
    def cantidad_solicitados(self) -> int:
        return len(self.solicitados)

    @property
    def cantidad_seleccionados(self) -> int:
        return len(self.seleccionados)

    @property
    def completo(self) -> bool:
        return (
            self.cantidad_solicitados > 0
            and self.cantidad_solicitados == self.cantidad_seleccionados
        )


# ==========================================================
# NORMALIZACIÓN
# ==========================================================

def normalizar_pedido(valor: object) -> str:
    if valor is None:
        return ""

    pedido = str(valor).strip()

    # Corrige números provenientes de Excel, por ejemplo 12345.0
    if pedido.endswith(".0"):
        posible_numero = pedido[:-2]

        if posible_numero.isdigit():
            pedido = posible_numero

    return pedido


def normalizar_pedidos(
    pedidos: Iterable[object],
) -> list[str]:
    resultado: list[str] = []

    for valor in pedidos:
        pedido = normalizar_pedido(valor)

        if pedido and pedido not in resultado:
            resultado.append(pedido)

    return resultado


# ==========================================================
# VALIDACIONES DE FILA
# ==========================================================

def fila_esta_seleccionada(fila: Locator) -> bool:
    try:
        checkbox = fila.locator(
            'input[type="checkbox"]'
        ).first

        if checkbox.count() == 0:
            return False

        return checkbox.is_checked()

    except Exception:
        return False


def obtener_fila_pedido(
    page: Page,
    pedido: str,
) -> Locator | None:
    """
    Busca una fila que contenga el pedido.

    Primero intenta coincidencia de texto en tbody.
    Después valida que la fila encontrada siga visible.
    """

    filas = page.locator("tbody tr").filter(
        has_text=pedido
    )

    cantidad = filas.count()

    if cantidad == 0:
        return None

    for indice in range(cantidad):
        fila = filas.nth(indice)

        try:
            if fila.is_visible():
                return fila
        except Exception:
            continue

    return None


# ==========================================================
# ESTRATEGIAS DE CLIC
# ==========================================================

def intentar_click_celda(
    fila: Locator,
    page: Page,
) -> bool:
    try:
        primera_celda = fila.locator("td").first

        primera_celda.wait_for(
            state="visible",
            timeout=3_000,
        )
        primera_celda.scroll_into_view_if_needed()

        page.wait_for_timeout(300)
        primera_celda.click(force=True)
        page.wait_for_timeout(800)

        return True

    except Exception:
        return False


def intentar_click_checkbox(
    fila: Locator,
    page: Page,
) -> bool:
    try:
        checkbox = fila.locator(
            'input[type="checkbox"]'
        ).first

        checkbox.wait_for(
            state="attached",
            timeout=3_000,
        )
        checkbox.scroll_into_view_if_needed()

        page.wait_for_timeout(200)
        checkbox.click(force=True)
        page.wait_for_timeout(800)

        return True

    except Exception:
        return False


def intentar_click_label(
    fila: Locator,
    page: Page,
) -> bool:
    candidatos = [
        fila.locator("span.label-text").first,
        fila.locator("label").first,
        fila.locator("span").first,
    ]

    for candidato in candidatos:
        try:
            if candidato.count() == 0:
                continue

            candidato.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            candidato.click(force=True)
            page.wait_for_timeout(800)

            return True

        except Exception:
            continue

    return False


def intentar_click_javascript(
    fila: Locator,
    page: Page,
) -> bool:
    try:
        checkbox = fila.locator(
            'input[type="checkbox"]'
        ).first

        handle = checkbox.element_handle()

        if handle is None:
            return False

        page.evaluate(
            "(elemento) => elemento.click()",
            handle,
        )
        page.wait_for_timeout(800)

        return True

    except Exception:
        return False


# ==========================================================
# SELECCIÓN
# ==========================================================

def seleccionar_fila_reforzado(
    fila: Locator,
    pedido: str,
    page: Page,
) -> bool:
    """
    Prueba distintas formas de seleccionar la fila y valida
    después de cada intento que el checkbox haya quedado marcado.
    """

    if fila_esta_seleccionada(fila):
        print(f"      Ya estaba seleccionado: {pedido}")
        return True

    estrategias = [
        ("celda", intentar_click_celda),
        ("checkbox", intentar_click_checkbox),
        ("label", intentar_click_label),
        ("JavaScript", intentar_click_javascript),
    ]

    for nombre, estrategia in estrategias:
        try:
            click_realizado = estrategia(
                fila=fila,
                page=page,
            )

            if (
                click_realizado
                and fila_esta_seleccionada(fila)
            ):
                print(
                    f"      Seleccionado: {pedido} "
                    f"({nombre})"
                )
                return True

        except Exception:
            continue

    print(
        "      Se encontró la fila, pero no pudo "
        f"seleccionarse: {pedido}"
    )
    return False


def seleccionar_pedido(
    page: Page,
    pedido: object,
) -> bool | None:
    """
    Retorna:
    - True: pedido seleccionado.
    - False: fila encontrada, pero no seleccionada.
    - None: pedido no encontrado.
    """

    pedido_normalizado = normalizar_pedido(pedido)

    if not pedido_normalizado:
        raise ValueError(
            "El número de pedido no puede estar vacío."
        )

    print(f"   -> Buscando pedido {pedido_normalizado}")

    fila = obtener_fila_pedido(
        page=page,
        pedido=pedido_normalizado,
    )

    if fila is None:
        print(
            f"      No encontrado: {pedido_normalizado}"
        )
        return None

    return seleccionar_fila_reforzado(
        fila=fila,
        pedido=pedido_normalizado,
        page=page,
    )


def seleccionar_pedidos(
    page: Page,
    pedidos: Iterable[object],
    detener_si_hay_error: bool = False,
) -> ResultadoSeleccion:
    """
    Selecciona todos los pedidos recibidos y devuelve un resumen.
    """

    pedidos_normalizados = normalizar_pedidos(pedidos)

    if not pedidos_normalizados:
        raise ValueError(
            "No se recibieron pedidos válidos para seleccionar."
        )

    resultado = ResultadoSeleccion(
        solicitados=pedidos_normalizados
    )

    print("=" * 60)
    print(
        f"SELECCIÓN DE PEDIDOS: "
        f"{len(pedidos_normalizados)} solicitados"
    )
    print("=" * 60)

    for pedido in pedidos_normalizados:
        estado = seleccionar_pedido(
            page=page,
            pedido=pedido,
        )

        if estado is True:
            resultado.seleccionados.append(pedido)

        elif estado is None:
            resultado.no_encontrados.append(pedido)

            if detener_si_hay_error:
                break

        else:
            resultado.no_seleccionados.append(pedido)

            if detener_si_hay_error:
                break

        page.wait_for_timeout(
            ESPERA_ENTRE_PEDIDOS_MS
        )

    imprimir_resultado(resultado)

    return resultado


def imprimir_resultado(
    resultado: ResultadoSeleccion,
) -> None:
    print("=" * 60)
    print("RESULTADO DE SELECCIÓN")
    print(
        f"Solicitados:     "
        f"{resultado.cantidad_solicitados}"
    )
    print(
        f"Seleccionados:   "
        f"{resultado.cantidad_seleccionados}"
    )
    print(
        f"No encontrados:  "
        f"{len(resultado.no_encontrados)}"
    )
    print(
        f"No seleccionados:"
        f" {len(resultado.no_seleccionados)}"
    )

    if resultado.no_encontrados:
        print(
            "Lista no encontrados:",
            resultado.no_encontrados,
        )

    if resultado.no_seleccionados:
        print(
            "Lista no seleccionados:",
            resultado.no_seleccionados,
        )

    print("=" * 60)


# ==========================================================
# PRUEBA DIRECTA
# ==========================================================

def solicitar_pedidos_prueba() -> list[str]:
    texto = input(
        "Ingresá los números de pedido separados por coma: "
    )

    return normalizar_pedidos(
        texto.split(",")
    )


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

        print()
        print(
            "La prueba quedó detenida con los pedidos "
            "seleccionados."
        )
        print(
            f"Selección completa: "
            f"{'SÍ' if resultado.completo else 'NO'}"
        )

        input(
            "Revisá la pantalla y presioná ENTER "
            "para cerrar..."
        )


if __name__ == "__main__":
    main()
