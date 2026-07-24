from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Automatizacion.ejecutar_agrupaciones import ejecutar_agrupacion
from utils.cola_agrupaciones import (
    actualizar_orden,
    marcar_en_proceso,
    obtener_siguiente_pendiente,
    worker_id_local,
)


INTERVALO_SEGUNDOS = 10
HEADLESS_WORKER = True


def texto_a_bool(valor: object) -> bool:
    return str(valor).strip().upper() in {
        "TRUE",
        "1",
        "SI",
        "SÍ",
        "YES",
    }


def numero_entero(valor: object, defecto: int = 0) -> int:
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return defecto


def procesar_orden(orden: dict) -> None:
    orden_id = str(orden.get("OrdenID", "")).strip()

    if not orden_id:
        raise ValueError("La orden pendiente no tiene OrdenID.")

    worker_id = worker_id_local()
    intentos = numero_entero(orden.get("Intentos"), 0) + 1

    marcar_en_proceso(
        orden_id=orden_id,
        worker_id=worker_id,
        intentos=intentos,
    )

    print(
        f"\n[{orden_id}] Ejecutando "
        f"{orden.get('Camioneta', '')}",
        flush=True,
    )

    def callback(etapa: str, mensaje: str) -> None:
        print(f"[{orden_id}] [{etapa}] {mensaje}", flush=True)

        actualizar_orden(
            orden_id,
            {
                "Etapa": etapa,
                "Mensaje": mensaje,
            },
        )

    try:
        pedidos = json.loads(
            str(orden.get("PedidosJSON", "[]") or "[]")
        )

        codigos_despacho = json.loads(
            str(
                orden.get(
                    "CodigosDespachoJSON",
                    "[]",
                )
                or "[]"
            )
        )

        resultado = ejecutar_agrupacion(
            {
                "codigo_despacho": str(
                    orden.get("CodigoDespacho", "")
                ).strip(),
                "codigos_despacho": codigos_despacho,
                "usar_filtro_codigo_despacho": texto_a_bool(
                    orden.get("UsarFiltroCodigoDespacho")
                ),
                "despacho": str(
                    orden.get("Camioneta", "")
                ).strip(),
                "pedidos": pedidos,
                "identificador": str(
                    orden.get("Camioneta", "")
                ).strip(),
            },
            headless=HEADLESS_WORKER,
            callback=callback,
        )

        estado_final = (
            "COMPLETADA"
            if resultado.exito
            else "ERROR"
        )

        actualizar_orden(
            orden_id,
            {
                "Estado": estado_final,
                "Etapa": resultado.etapa,
                "Mensaje": resultado.mensaje,
                "FechaFin": time.strftime("%Y-%m-%d %H:%M:%S"),
                "DuracionSegundos": resultado.duracion_segundos,
            },
        )

        print(
            f"[{orden_id}] Resultado: "
            f"{estado_final} - {resultado.mensaje}",
            flush=True,
        )

    except Exception as error:
        detalle = traceback.format_exc()
        mensaje = f"{type(error).__name__}: {error}"

        actualizar_orden(
            orden_id,
            {
                "Estado": "ERROR",
                "Etapa": "error_worker",
                "Mensaje": mensaje,
                "FechaFin": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

        print(f"[{orden_id}] {mensaje}", flush=True)
        print(detalle, flush=True)


def main() -> None:
    print("=" * 70)
    print("WORKER DE AGRUPACIONES DIGIP")
    print(f"Revisión cada {INTERVALO_SEGUNDOS} segundos")
    print("Presioná Ctrl+C para detenerlo.")
    print("=" * 70, flush=True)

    while True:
        try:
            orden = obtener_siguiente_pendiente()

            if orden is None:
                time.sleep(INTERVALO_SEGUNDOS)
                continue

            procesar_orden(orden)

        except KeyboardInterrupt:
            print("\nWorker detenido.", flush=True)
            break

        except Exception:
            traceback.print_exc()
            time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    main()
