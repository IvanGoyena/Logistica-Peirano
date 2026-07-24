from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


# ==========================================================
# RUTA DEL PROYECTO
# ==========================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from Automatizacion.asignador_despacho import (
    seleccionar_y_asignar_despacho,
)
from Automatizacion.digip_session import DigipSession
from Automatizacion.navegacion_digip import (
    abrir_nueva_preparacion,
)
from Automatizacion.selector_pedidos import (
    ResultadoSeleccion,
    normalizar_pedidos,
    seleccionar_pedidos,
)
from Automatizacion.tipo_preparacion import (
    seleccionar_tipo_preparacion_pedido,
)


# ==========================================================
# TIPOS
# ==========================================================

CallbackEstado = Callable[[str, str], None]


@dataclass
class Agrupacion:
    """
    Datos necesarios para crear una preparación en DIGIP.

    codigo_despacho:
        Código utilizado para filtrar pedidos en DIGIP.

    despacho:
        Nombre exacto del despacho/camioneta en DIGIP.

    pedidos:
        Números de pedido que formarán parte de la agrupación.
    """

    codigo_despacho: str
    despacho: str
    pedidos: list[str]
    identificador: str = ""
    codigos_despacho: list[str] = field(
        default_factory=list
    )
    usar_filtro_codigo_despacho: bool = True

    def validar(self) -> None:
        self.codigo_despacho = str(
            self.codigo_despacho
        ).strip()

        self.despacho = str(
            self.despacho
        ).strip()

        self.pedidos = normalizar_pedidos(
            self.pedidos
        )

        self.identificador = str(
            self.identificador
        ).strip()

        self.codigos_despacho = list(
            dict.fromkeys(
                str(codigo).strip()
                for codigo in self.codigos_despacho
                if str(codigo).strip()
            )
        )

        self.usar_filtro_codigo_despacho = bool(
            self.usar_filtro_codigo_despacho
        )

        if (
            not self.codigos_despacho
            and self.codigo_despacho
        ):
            self.codigos_despacho = [
                self.codigo_despacho
            ]

        if not self.codigo_despacho:
            raise ValueError(
                "La agrupación no tiene código de despacho."
            )

        if not self.despacho:
            raise ValueError(
                "La agrupación no tiene despacho asignado."
            )

        if not self.pedidos:
            raise ValueError(
                "La agrupación no contiene pedidos."
            )

        if not self.identificador:
            self.identificador = self.despacho


@dataclass
class ResultadoAgrupacion:
    identificador: str
    codigo_despacho: str
    despacho: str
    pedidos_solicitados: list[str] = field(
        default_factory=list
    )
    pedidos_seleccionados: list[str] = field(
        default_factory=list
    )
    pedidos_no_encontrados: list[str] = field(
        default_factory=list
    )
    pedidos_no_seleccionados: list[str] = field(
        default_factory=list
    )
    exito: bool = False
    mensaje: str = ""
    etapa: str = ""
    duracion_segundos: float = 0.0

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResultadoEjecucion:
    resultados: list[ResultadoAgrupacion]
    duracion_segundos: float

    @property
    def exito(self) -> bool:
        return bool(self.resultados) and all(
            resultado.exito
            for resultado in self.resultados
        )

    @property
    def cantidad_agrupaciones(self) -> int:
        return len(self.resultados)

    @property
    def cantidad_exitosas(self) -> int:
        return sum(
            resultado.exito
            for resultado in self.resultados
        )

    @property
    def cantidad_fallidas(self) -> int:
        return (
            self.cantidad_agrupaciones
            - self.cantidad_exitosas
        )

    @property
    def total_pedidos(self) -> int:
        return sum(
            len(resultado.pedidos_solicitados)
            for resultado in self.resultados
        )

    def como_dict(self) -> dict:
        return {
            "exito": self.exito,
            "cantidad_agrupaciones": (
                self.cantidad_agrupaciones
            ),
            "cantidad_exitosas": (
                self.cantidad_exitosas
            ),
            "cantidad_fallidas": (
                self.cantidad_fallidas
            ),
            "total_pedidos": self.total_pedidos,
            "duracion_segundos": (
                self.duracion_segundos
            ),
            "resultados": [
                resultado.como_dict()
                for resultado in self.resultados
            ],
        }


# ==========================================================
# MENSAJES Y CONVERSIÓN
# ==========================================================

def emitir_estado(
    callback: CallbackEstado | None,
    etapa: str,
    mensaje: str,
) -> None:
    print(f"[{etapa}] {mensaje}")

    if callback is not None:
        callback(etapa, mensaje)


def crear_agrupacion(
    agrupacion: Agrupacion | Mapping,
) -> Agrupacion:
    """
    Permite que la app envíe un objeto Agrupacion o un diccionario.

    Claves admitidas:
    - codigo_despacho
    - despacho
    - pedidos
    - identificador, opcional
    """

    if isinstance(agrupacion, Agrupacion):
        resultado = agrupacion

    elif isinstance(agrupacion, Mapping):
        resultado = Agrupacion(
            codigo_despacho=agrupacion.get(
                "codigo_despacho",
                "",
            ),
            despacho=agrupacion.get(
                "despacho",
                "",
            ),
            pedidos=list(
                agrupacion.get(
                    "pedidos",
                    [],
                )
            ),
            identificador=agrupacion.get(
                "identificador",
                "",
            ),
            codigos_despacho=list(
                agrupacion.get(
                    "codigos_despacho",
                    [],
                )
            ),
            usar_filtro_codigo_despacho=bool(
                agrupacion.get(
                    "usar_filtro_codigo_despacho",
                    True,
                )
            ),
        )

    else:
        raise TypeError(
            "Cada agrupación debe ser Agrupacion "
            "o un diccionario."
        )

    resultado.validar()

    return resultado


# ==========================================================
# FILTRO DE CÓDIGO DE DESPACHO
# ==========================================================

def limpiar_filtro_codigo_despacho(
    page,
) -> None:
    """
    Limpia el filtro CodigoDespacho antes de seleccionar pedidos.

    Se utiliza cuando una misma camioneta contiene pedidos de
    más de un código de despacho. El filtro se limpia una sola
    vez, antes de marcar cualquier pedido, para que DIGIP muestre
    la grilla completa y no pierda selecciones.
    """

    encabezado = page.get_by_text(
        "CodigoDespacho",
        exact=True,
    ).first

    encabezado.wait_for(
        state="visible",
        timeout=30_000,
    )

    input_codigo = (
        page.locator("thead tr")
        .nth(1)
        .locator("input")
        .nth(6)
    )

    input_codigo.wait_for(
        state="visible",
        timeout=30_000,
    )

    input_codigo.click()
    input_codigo.press("Control+A")
    input_codigo.press("Backspace")
    input_codigo.fill("")

    # Espera a que la tabla vuelva a mostrar todos los pedidos.
    page.wait_for_timeout(3_000)


# ==========================================================
# EJECUCIÓN DE UNA AGRUPACIÓN
# ==========================================================

def ejecutar_agrupacion_en_pagina(
    page,
    agrupacion: Agrupacion,
    callback: CallbackEstado | None = None,
) -> ResultadoAgrupacion:
    """
    Ejecuta una agrupación usando una página DIGIP ya abierta.

    Esta función no crea ni cierra el navegador. Es útil para
    procesar varias camionetas dentro de una misma sesión.
    """

    agrupacion.validar()
    inicio = time.perf_counter()

    resultado = ResultadoAgrupacion(
        identificador=agrupacion.identificador,
        codigo_despacho=agrupacion.codigo_despacho,
        despacho=agrupacion.despacho,
        pedidos_solicitados=agrupacion.pedidos.copy(),
    )

    seleccion: ResultadoSeleccion | None = None

    try:
        resultado.etapa = "navegacion"

        emitir_estado(
            callback,
            "navegacion",
            (
                f"{agrupacion.identificador}: "
                "abriendo Nueva preparación."
            ),
        )

        abrir_nueva_preparacion(
            page=page,
            codigo_despacho=(
                agrupacion.codigo_despacho
            ),
        )

        if not agrupacion.usar_filtro_codigo_despacho:

            emitir_estado(
                callback,
                "navegacion",
                (
                    f"{agrupacion.identificador}: "
                    "la camioneta contiene varios códigos "
                    "de despacho; se buscarán los pedidos "
                    "por número sin filtrar la grilla."
                ),
            )

            limpiar_filtro_codigo_despacho(
                page=page
            )

        resultado.etapa = "seleccion_pedidos"

        emitir_estado(
            callback,
            "seleccion_pedidos",
            (
                f"{agrupacion.identificador}: "
                f"seleccionando "
                f"{len(agrupacion.pedidos)} pedidos."
            ),
        )

        seleccion = seleccionar_pedidos(
            page=page,
            pedidos=agrupacion.pedidos,
            detener_si_hay_error=False,
        )

        resultado.pedidos_seleccionados = (
            seleccion.seleccionados.copy()
        )
        resultado.pedidos_no_encontrados = (
            seleccion.no_encontrados.copy()
        )
        resultado.pedidos_no_seleccionados = (
            seleccion.no_seleccionados.copy()
        )

        if not seleccion.completo:
            raise RuntimeError(
                "No se seleccionaron todos los pedidos. "
                "La asignación se canceló por seguridad."
            )

        resultado.etapa = "tipo_preparacion"

        emitir_estado(
            callback,
            "tipo_preparacion",
            (
                f"{agrupacion.identificador}: "
                "seleccionando tipo PEDIDO."
            ),
        )

        seleccionar_tipo_preparacion_pedido(
            page=page
        )

        resultado.etapa = "asignacion_despacho"

        emitir_estado(
            callback,
            "asignacion_despacho",
            (
                f"{agrupacion.identificador}: "
                f"asignando {agrupacion.despacho}."
            ),
        )

        seleccionar_y_asignar_despacho(
            page=page,
            despacho_objetivo=agrupacion.despacho,
        )

        resultado.etapa = "finalizado"
        resultado.exito = True
        resultado.mensaje = (
            "Agrupación creada correctamente."
        )

        emitir_estado(
            callback,
            "finalizado",
            (
                f"{agrupacion.identificador}: "
                "agrupación creada correctamente."
            ),
        )

    except Exception as error:
        resultado.exito = False
        resultado.mensaje = str(error)

        emitir_estado(
            callback,
            "error",
            (
                f"{agrupacion.identificador}: "
                f"{error}"
            ),
        )

    finally:
        resultado.duracion_segundos = round(
            time.perf_counter() - inicio,
            2,
        )

    return resultado


def ejecutar_agrupacion(
    agrupacion: Agrupacion | Mapping,
    headless: bool = True,
    callback: CallbackEstado | None = None,
) -> ResultadoAgrupacion:
    """
    Ejecuta una sola camioneta desde la app.

    Ejemplo:

        resultado = ejecutar_agrupacion({
            "codigo_despacho": "0501",
            "despacho": "CAMIONETA 1",
            "pedidos": ["123", "124"],
        })
    """

    agrupacion_normalizada = crear_agrupacion(
        agrupacion
    )

    with DigipSession(
        headless=headless
    ) as sesion:

        page = sesion.page

        if page is None:
            raise RuntimeError(
                "No se pudo obtener la página DIGIP."
            )

        return ejecutar_agrupacion_en_pagina(
            page=page,
            agrupacion=agrupacion_normalizada,
            callback=callback,
        )


# ==========================================================
# EJECUCIÓN DE VARIAS AGRUPACIONES
# ==========================================================

def ejecutar_agrupaciones(
    agrupaciones: Sequence[
        Agrupacion | Mapping
    ],
    headless: bool = True,
    detener_ante_error: bool = True,
    callback: CallbackEstado | None = None,
) -> ResultadoEjecucion:
    """
    Ejecuta una o varias camionetas dentro de una única
    sesión DIGIP.

    detener_ante_error=True:
        Si una agrupación falla, no continúa con las siguientes.
        Es la opción recomendada inicialmente por seguridad.
    """

    inicio_general = time.perf_counter()

    agrupaciones_normalizadas = [
        crear_agrupacion(agrupacion)
        for agrupacion in agrupaciones
    ]

    if not agrupaciones_normalizadas:
        raise ValueError(
            "No se recibieron agrupaciones para ejecutar."
        )

    resultados: list[ResultadoAgrupacion] = []

    with DigipSession(
        headless=headless
    ) as sesion:

        page = sesion.page

        if page is None:
            raise RuntimeError(
                "No se pudo obtener la página DIGIP."
            )

        for indice, agrupacion in enumerate(
            agrupaciones_normalizadas,
            start=1,
        ):
            emitir_estado(
                callback,
                "inicio",
                (
                    f"Agrupación {indice}/"
                    f"{len(agrupaciones_normalizadas)}: "
                    f"{agrupacion.identificador}"
                ),
            )

            resultado = ejecutar_agrupacion_en_pagina(
                page=page,
                agrupacion=agrupacion,
                callback=callback,
            )

            resultados.append(resultado)

            if (
                detener_ante_error
                and not resultado.exito
            ):
                emitir_estado(
                    callback,
                    "detenido",
                    (
                        "La ejecución se detuvo porque "
                        "una agrupación falló."
                    ),
                )
                break

    duracion = round(
        time.perf_counter() - inicio_general,
        2,
    )

    return ResultadoEjecucion(
        resultados=resultados,
        duracion_segundos=duracion,
    )
