from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from config import URL, USUARIO, PASSWORD, HEADLESS


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

URL_LOGIN = URL.rstrip("/")
URL_HOME = f"{URL_LOGIN}/home"

BASE_DIR = Path(__file__).resolve().parent
SESSION_DIR = BASE_DIR / "sessions"
LOG_DIR = BASE_DIR / "logs"
CAPTURAS_DIR = BASE_DIR / "capturas"

SESSION_FILE = SESSION_DIR / "digip.json"

TIMEOUT_MS = 30_000


# ==========================================================
# UTILIDADES
# ==========================================================

def crear_carpetas() -> None:
    for carpeta in (SESSION_DIR, LOG_DIR, CAPTURAS_DIR):
        carpeta.mkdir(parents=True, exist_ok=True)


def registrar_log(mensaje: str) -> None:
    crear_carpetas()

    fecha = datetime.now()
    archivo_log = LOG_DIR / f"{fecha:%Y-%m-%d}.log"

    linea = f"[{fecha:%Y-%m-%d %H:%M:%S}] {mensaje}\n"

    with archivo_log.open("a", encoding="utf-8") as archivo:
        archivo.write(linea)

    print(mensaje)


# ==========================================================
# SESIÓN DIGIP
# ==========================================================

class DigipSession:
    """
    Administra Playwright, navegador, contexto, sesión y login de DIGIP.

    Uso recomendado:

        with DigipSession(headless=False) as sesion:
            page = sesion.page

            if page is None:
                raise RuntimeError("No se pudo obtener la página DIGIP.")

            # Automatización...
    """

    def __init__(
        self,
        headless: bool = HEADLESS,
        timeout_ms: int = TIMEOUT_MS,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self) -> "DigipSession":
        self.iniciar()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_value is not None:
            self.guardar_captura_error("error_digip")

        self.cerrar()

    def iniciar(self) -> Page:
        """
        Inicia Playwright y devuelve una página autenticada en DIGIP.
        """

        crear_carpetas()

        registrar_log("Iniciando sesión DIGIP...")

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=self.headless
        )

        self.context = self._crear_contexto()
        self.context.set_default_timeout(self.timeout_ms)

        self.page = self.context.new_page()

        if not self._sesion_actual_valida():
            registrar_log("La sesión guardada no es válida. Se realizará login.")
            self._hacer_login()
        else:
            registrar_log("Sesión DIGIP reutilizada correctamente.")

        if self.page is None:
            raise RuntimeError("No se pudo crear la página de DIGIP.")

        return self.page

    def _crear_contexto(self) -> BrowserContext:
        """
        Crea el contexto reutilizando storage_state si existe.
        """

        if self.browser is None:
            raise RuntimeError("El navegador todavía no fue iniciado.")

        if SESSION_FILE.exists():
            try:
                registrar_log(
                    f"Intentando reutilizar sesión guardada: {SESSION_FILE}"
                )

                return self.browser.new_context(
                    storage_state=str(SESSION_FILE)
                )

            except Exception as error:
                registrar_log(
                    "No se pudo reutilizar la sesión guardada. "
                    f"Se creará un contexto nuevo. Error: {error}"
                )

        return self.browser.new_context()

    def _sesion_actual_valida(self) -> bool:
        """
        Comprueba si la sesión actual permite entrar al HOME sin volver al login.
        """

        if self.page is None:
            return False

        try:
            self.page.goto(
                URL_HOME,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )

            self.page.wait_for_timeout(1500)

            if "login" in self.page.url.lower():
                return False

            indicadores = [
                self.page.get_by_role(
                    "link",
                    name="Ir a Preparaciones",
                ),
                self.page.get_by_text(
                    "Preparaciones",
                    exact=False,
                ),
                self.page.get_by_role(
                    "button",
                    name="OPCIONES",
                ),
            ]

            for indicador in indicadores:
                try:
                    if indicador.count() > 0 and indicador.first.is_visible():
                        return True
                except Exception:
                    continue

            return False

        except PlaywrightTimeoutError:
            registrar_log("Timeout validando la sesión actual.")
            return False

        except Exception as error:
            registrar_log(
                f"Error validando la sesión actual: {error}"
            )
            return False

    def _hacer_login(self) -> None:
        """
        Realiza el login usando el mismo flujo que ya fue probado
        correctamente en login_digip.py.
        """

        if self.page is None or self.context is None:
            raise RuntimeError(
                "No se pudo iniciar el contexto de navegación."
            )

        usuario = str(USUARIO).strip()
        clave = str(PASSWORD).strip()

        if not usuario or not clave:
            raise ValueError(
                "Faltan USUARIO o PASSWORD en config.py."
            )

        registrar_log("Abriendo pantalla de login DIGIP.")

        self.page.goto(
            URL_LOGIN,
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )

        # Este wait estaba en el login original que funcionaba.
        try:
            self.page.wait_for_load_state(
                "networkidle",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError:
            registrar_log(
                "La pantalla de login no llegó a networkidle; "
                "se continúa igualmente."
            )

        registrar_log(
            f"Página de login abierta: {self.page.url}"
        )

        input_usuario = self.page.locator(
            'input[name="username"], input[type="text"]'
        ).first

        input_usuario.wait_for(
            state="visible",
            timeout=self.timeout_ms,
        )
        input_usuario.fill(usuario)

        registrar_log("Usuario completado.")

        input_clave = self.page.locator(
            'input[name="password"], input[type="password"]'
        ).first

        input_clave.wait_for(
            state="visible",
            timeout=self.timeout_ms,
        )
        input_clave.fill(clave)

        registrar_log("Contraseña completada.")

        # Se usa exactamente el selector del login que ya funcionaba.
        boton_ingresar = self.page.get_by_role(
            "button",
            name="INGRESAR",
        )

        boton_ingresar.wait_for(
            state="visible",
            timeout=self.timeout_ms,
        )

        registrar_log("Botón INGRESAR encontrado.")

        boton_ingresar.click()

        registrar_log("Click en INGRESAR.")

        self.page.wait_for_timeout(3000)

        try:
            self.page.wait_for_load_state(
                "networkidle",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError:
            registrar_log(
                "DIGIP no llegó a networkidle después del ingreso; "
                "se validará la pantalla actual."
            )

        # Validación mediante un elemento de la pantalla principal.
        indicador_home = self.page.get_by_role(
            "link",
            name="Ir a Preparaciones",
        ).first

        try:
            indicador_home.wait_for(
                state="visible",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError as error:
            self.guardar_captura_error(
                "login_no_ingreso"
            )

            raise RuntimeError(
                "Se hizo click en INGRESAR, pero no apareció "
                "la pantalla principal de DIGIP."
            ) from error

        registrar_log(
            f"Login correcto. URL actual: {self.page.url}"
        )

        self.context.storage_state(
            path=str(SESSION_FILE)
        )

        registrar_log(
            f"Sesión DIGIP guardada correctamente: {SESSION_FILE}"
        )

    def guardar_captura_error(
        self,
        prefijo: str = "error",
    ) -> Optional[Path]:
        """
        Guarda una captura de pantalla cuando ocurre un error.
        """

        if self.page is None:
            return None

        crear_carpetas()

        marca_tiempo = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        ruta = CAPTURAS_DIR / f"{prefijo}_{marca_tiempo}.png"

        try:
            self.page.screenshot(
                path=str(ruta),
                full_page=True,
            )

            registrar_log(
                f"Captura guardada: {ruta}"
            )

            return ruta

        except Exception as error:
            registrar_log(
                "No se pudo guardar la captura. "
                f"Error: {error}"
            )

            return None

    def guardar_sesion(self) -> None:
        """
        Permite guardar manualmente la sesión luego de cambios importantes.
        """

        if self.context is None:
            raise RuntimeError(
                "No hay un contexto activo para guardar."
            )

        crear_carpetas()

        self.context.storage_state(
            path=str(SESSION_FILE)
        )

        registrar_log(
            f"Sesión actualizada correctamente: {SESSION_FILE}"
        )

    def eliminar_sesion_guardada(self) -> None:
        """
        Elimina el archivo de sesión para forzar un login nuevo.
        """

        if SESSION_FILE.exists():
            SESSION_FILE.unlink()

            registrar_log(
                "Archivo de sesión DIGIP eliminado."
            )

    def cerrar(self) -> None:
        """
        Cierra página, contexto, navegador y Playwright.
        """

        if self.page is not None:
            try:
                self.page.close()
            except Exception:
                pass

        if self.context is not None:
            try:
                self.context.close()
            except Exception:
                pass

        if self.browser is not None:
            try:
                self.browser.close()
            except Exception:
                pass

        if self.playwright is not None:
            try:
                self.playwright.stop()
            except Exception:
                pass

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None

        registrar_log("Sesión DIGIP cerrada.")


# ==========================================================
# ATAJOS
# ==========================================================

def obtener_page(
    headless: bool = HEADLESS,
    timeout_ms: int = TIMEOUT_MS,
) -> tuple[DigipSession, Page]:
    """
    Inicia la sesión sin usar `with`.

    Importante:
    quien use esta función debe ejecutar `sesion.cerrar()` al terminar.
    """

    sesion = DigipSession(
        headless=headless,
        timeout_ms=timeout_ms,
    )

    page = sesion.iniciar()

    return sesion, page


# ==========================================================
# PRUEBA DIRECTA
# ==========================================================

def main() -> None:
    with DigipSession(
        headless=False
    ) as sesion:

        page = sesion.page

        if page is None:
            raise RuntimeError(
                "No se pudo obtener la página DIGIP."
            )

        print("=" * 60)
        print("SESIÓN DIGIP LISTA")
        print(f"URL actual: {page.url}")
        print("=" * 60)

        input(
            "Presioná ENTER para cerrar el navegador..."
        )


if __name__ == "__main__":
    main()