from __future__ import annotations

import shutil
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

from config import HEADLESS, PASSWORD, URL, USUARIO


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

URL_LOGIN = str(URL).rstrip("/")
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
    """Crea las carpetas de trabajo de la automatización."""
    for carpeta in (SESSION_DIR, LOG_DIR, CAPTURAS_DIR):
        carpeta.mkdir(parents=True, exist_ok=True)


def registrar_log(mensaje: str) -> None:
    """Guarda el mensaje en archivo y también lo muestra en consola."""
    crear_carpetas()

    fecha = datetime.now()
    archivo_log = LOG_DIR / f"{fecha:%Y-%m-%d}.log"
    linea = f"[{fecha:%Y-%m-%d %H:%M:%S}] {mensaje}\n"

    try:
        with archivo_log.open("a", encoding="utf-8") as archivo:
            archivo.write(linea)
    except Exception:
        # En caso de que el filesystem temporal no permita escribir,
        # el proceso continúa y el mensaje queda al menos en consola.
        pass

    print(mensaje, flush=True)


# ==========================================================
# SESIÓN DIGIP
# ==========================================================

class DigipSession:
    """
    Administra Playwright, Chromium, contexto, sesión y login de DIGIP.

    Ejemplo:

        with DigipSession(headless=True) as sesion:
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
        self.headless = bool(headless)
        self.timeout_ms = int(timeout_ms)

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self) -> "DigipSession":
        self.iniciar()
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        if exc_value is not None:
            self.guardar_captura_error("error_digip")

        self.cerrar()

    def iniciar(self) -> Page:
        """
        Inicia Playwright, abre Chromium y devuelve una página
        autenticada en DIGIP.
        """
        crear_carpetas()
        registrar_log("Iniciando sesión DIGIP...")

        try:
            self.playwright = sync_playwright().start()

            ruta_chromium = (
                shutil.which("chromium")
                or shutil.which("chromium-browser")
            )

            argumentos_navegador = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--no-first-run",
            ]

            opciones_launch = {
                "headless": self.headless,
                "args": argumentos_navegador,
            }

            if ruta_chromium:
                opciones_launch["executable_path"] = ruta_chromium
                registrar_log(
                    f"Chromium del sistema encontrado: {ruta_chromium}"
                )
            else:
                registrar_log(
                    "No se encontró Chromium del sistema. "
                    "Se intentará usar el navegador instalado por Playwright."
                )

            self.browser = self.playwright.chromium.launch(
                **opciones_launch
            )

            registrar_log("Navegador iniciado correctamente.")

            self.context = self._crear_contexto()
            self.context.set_default_timeout(self.timeout_ms)
            self.context.set_default_navigation_timeout(self.timeout_ms)

            self.page = self.context.new_page()

            registrar_log("Página de navegador creada.")

            if not self._sesion_actual_valida():
                registrar_log(
                    "La sesión guardada no es válida. "
                    "Se realizará login."
                )
                self._hacer_login()
            else:
                registrar_log(
                    "Sesión DIGIP reutilizada correctamente."
                )

            if self.page is None:
                raise RuntimeError(
                    "No se pudo crear la página de DIGIP."
                )

            return self.page

        except Exception as error:
            registrar_log(
                f"Error iniciando la sesión DIGIP: {error}"
            )
            self.guardar_captura_error("error_inicio_digip")
            self.cerrar()
            raise

    def _crear_contexto(self) -> BrowserContext:
        """
        Crea un contexto compatible con Windows y
        Streamlit Community Cloud.
        """
        if self.browser is None:
            raise RuntimeError(
                "El navegador todavía no fue iniciado."
            )

        opciones_contexto = {
            "viewport": {
                "width": 1920,
                "height": 1080,
            },
            "locale": "es-AR",
            "timezone_id": "America/Argentina/Buenos_Aires",
            "ignore_https_errors": True,
        }

        if SESSION_FILE.exists():
            try:
                registrar_log(
                    "Intentando reutilizar sesión guardada: "
                    f"{SESSION_FILE}"
                )

                return self.browser.new_context(
                    storage_state=str(SESSION_FILE),
                    **opciones_contexto,
                )

            except Exception as error:
                registrar_log(
                    "No se pudo reutilizar la sesión guardada. "
                    f"Se creará un contexto nuevo. Error: {error}"
                )

        return self.browser.new_context(
            **opciones_contexto
        )

    def _sesion_actual_valida(self) -> bool:
        """
        Comprueba si el contexto actual permite entrar al HOME
        sin volver al login.
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
                    if (
                        indicador.count() > 0
                        and indicador.first.is_visible()
                    ):
                        return True
                except Exception:
                    continue

            return False

        except PlaywrightTimeoutError:
            registrar_log(
                "Timeout validando la sesión actual."
            )
            return False

        except Exception as error:
            registrar_log(
                f"Error validando la sesión actual: {error}"
            )
            return False

    def _hacer_login(self) -> None:
        """Realiza el login automático en DIGIP."""
        if self.page is None or self.context is None:
            raise RuntimeError(
                "No se pudo iniciar el contexto de navegación."
            )

        usuario = str(USUARIO).strip()
        clave = str(PASSWORD).strip()

        if not usuario or not clave:
            raise ValueError(
                "Faltan USUARIO o PASSWORD en la configuración."
            )

        registrar_log("Abriendo pantalla de login DIGIP.")

        self.page.goto(
            URL_LOGIN,
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )

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

        try:
            self.context.storage_state(
                path=str(SESSION_FILE)
            )

            registrar_log(
                "Sesión DIGIP guardada correctamente: "
                f"{SESSION_FILE}"
            )

        except Exception as error:
            registrar_log(
                "El login fue correcto, pero no se pudo guardar "
                f"la sesión. Error: {error}"
            )

    def guardar_captura_error(
        self,
        prefijo: str = "error",
    ) -> Optional[Path]:
        """Guarda una captura de pantalla cuando ocurre un error."""
        if self.page is None:
            return None

        crear_carpetas()

        marca_tiempo = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        ruta = CAPTURAS_DIR / (
            f"{prefijo}_{marca_tiempo}.png"
        )

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
        """Guarda manualmente el storage_state actual."""
        if self.context is None:
            raise RuntimeError(
                "No hay un contexto activo para guardar."
            )

        crear_carpetas()

        self.context.storage_state(
            path=str(SESSION_FILE)
        )

        registrar_log(
            "Sesión actualizada correctamente: "
            f"{SESSION_FILE}"
        )

    def eliminar_sesion_guardada(self) -> None:
        """Elimina el archivo de sesión para forzar un login nuevo."""
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()

            registrar_log(
                "Archivo de sesión DIGIP eliminado."
            )

    def cerrar(self) -> None:
        """Cierra página, contexto, navegador y Playwright."""
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
# ATAJO SIN WITH
# ==========================================================

def obtener_page(
    headless: bool = HEADLESS,
    timeout_ms: int = TIMEOUT_MS,
) -> tuple[DigipSession, Page]:
    """
    Inicia la sesión sin usar `with`.

    Quien use esta función debe ejecutar:
        sesion.cerrar()
    al terminar.
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
        headless=True
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


if __name__ == "__main__":
    main()
