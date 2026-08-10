from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from config import (
    CARPETA_WMS,
    CARPETA_ERP,
    CARPETA_MAESTROS,
)
from utils.github_uploader import (
    GitHubUploaderError,
    obtener_sha_remoto,
    subir_archivo_github,
)


EXTENSIONES = (
    ".xlsx",
    ".xlsm",
    ".xls",
    ".csv",
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


GRUPOS_PUBLICACION = {
    "maestros": {
        "titulo": "Maestros",
        "carpeta": CARPETA_MAESTROS,
        "destino": "Data_Maestros",
        "archivos": (
            "Datos Expresos",
            "Maestro Articulo",
            "Maestro Clientes",
            "Maestro Ubicaciones",
            "Maestro Volumetria",
            "Max & Min",
            "Stock_Estandar",
        ),
    },
    "erp": {
        "titulo": "ERP manual",
        "carpeta": CARPETA_ERP,
        "destino": "Data_ERP",
        "archivos": (
            "Hojas de Ruta",
            "info stock total",
            "Informe Stock Sanitarios",
            "Pendientes OC",
        ),
    },
}


def nombre_filtro_preparacion_actual() -> str:
    hoy = datetime.now()

    return (
        f"Filtrar Preparacion "
        f"{MESES_ES[hoy.month]} "
        f"{hoy.year}"
    )


def _buscar_por_base(
    carpeta: Path,
    nombre_base: str,
) -> Path | None:
    """
    Busca una fuente sin depender de la extensión exacta
    y tolerando diferencias de mayúsculas/minúsculas.
    """

    if not carpeta.exists():
        return None

    nombre_objetivo = (
        str(nombre_base)
        .strip()
        .lower()
    )

    # Primero prueba los nombres exactos esperados.
    for extension in EXTENSIONES:
        candidato = (
            carpeta
            / f"{nombre_base}{extension}"
        )

        if candidato.exists():
            return candidato

    # Fallback tolerante a mayúsculas/minúsculas.
    for archivo in carpeta.iterdir():
        if not archivo.is_file():
            continue

        if (
            archivo.suffix.lower()
            not in EXTENSIONES
        ):
            continue

        if (
            archivo.stem
            .strip()
            .lower()
            == nombre_objetivo
        ):
            return archivo

    return None


def _sha_git_archivo(
    ruta: Path,
) -> str:
    """
    Calcula el SHA de blob Git del archivo local.
    Permite compararlo con el SHA informado por
    la API de Contents de GitHub.
    """

    contenido = ruta.read_bytes()

    cabecera = (
        f"blob {len(contenido)}\0"
        .encode("utf-8")
    )

    return hashlib.sha1(
        cabecera + contenido
    ).hexdigest()


def _publicar_archivo(
    archivo: Path,
    carpeta_github: str,
    grupo: str,
) -> dict:
    ruta_github = (
        f"{carpeta_github}/"
        f"{archivo.name}"
    )

    resultado = {
        "archivo": archivo.name,
        "ruta_local": str(archivo),
        "ruta_github": ruta_github,
        "estado": "",
        "detalle": "",
        "commit": "",
    }

    try:
        if not archivo.exists():
            resultado["estado"] = "ERROR"
            resultado["detalle"] = (
                "Archivo local no encontrado."
            )
            return resultado

        if archivo.stat().st_size <= 0:
            resultado["estado"] = "ERROR"
            resultado["detalle"] = (
                "Archivo local vacío."
            )
            return resultado

        sha_local = _sha_git_archivo(
            archivo
        )

        sha_remoto = obtener_sha_remoto(
            ruta_github
        )

        if (
            sha_remoto
            and sha_local == sha_remoto
        ):
            resultado["estado"] = (
                "SIN CAMBIOS"
            )
            resultado["detalle"] = (
                "GitHub ya tiene esta versión."
            )
            return resultado

        subida = subir_archivo_github(
            archivo_local=archivo,
            ruta_github=ruta_github,
            mensaje_commit=(
                f"Actualización manual {grupo} - "
                f"{archivo.name} - "
                f"{datetime.now():%d/%m/%Y %H:%M:%S}"
            ),
        )

        if subida.get("ok"):
            resultado["estado"] = (
                "ACTUALIZADO"
            )
            resultado["detalle"] = (
                f"HTTP {subida['status']}"
            )
            resultado["commit"] = (
                subida.get(
                    "commit_sha",
                    "",
                )[:12]
            )
        else:
            resultado["estado"] = "ERROR"
            resultado["detalle"] = (
                "GitHub no confirmó la subida."
            )

    except GitHubUploaderError as error:
        resultado["estado"] = "ERROR"
        resultado["detalle"] = str(error)

    except Exception as error:
        resultado["estado"] = "ERROR"
        resultado["detalle"] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

    return resultado


def publicar_grupo(
    grupo: str,
) -> list[dict]:
    if grupo not in GRUPOS_PUBLICACION:
        raise ValueError(
            "Grupo de publicación "
            f"no reconocido: {grupo}"
        )

    config = GRUPOS_PUBLICACION[
        grupo
    ]

    carpeta = Path(
        config["carpeta"]
    )

    resultados = []

    for nombre_base in config["archivos"]:
        archivo = _buscar_por_base(
            carpeta,
            nombre_base,
        )

        if archivo is None:
            resultados.append(
                {
                    "archivo": nombre_base,
                    "ruta_local": "",
                    "ruta_github": (
                        f"{config['destino']}/"
                        f"{nombre_base}"
                    ),
                    "estado": "ERROR",
                    "detalle": (
                        "No se encontró la fuente "
                        "en la carpeta local."
                    ),
                    "commit": "",
                }
            )
            continue

        resultados.append(
            _publicar_archivo(
                archivo=archivo,
                carpeta_github=(
                    config["destino"]
                ),
                grupo=(
                    config["titulo"]
                ),
            )
        )

    return resultados


def publicar_wms_manual() -> list[dict]:
    nombre_base = (
        nombre_filtro_preparacion_actual()
    )

    archivo = _buscar_por_base(
        Path(CARPETA_WMS),
        nombre_base,
    )

    if archivo is None:
        return [
            {
                "archivo": nombre_base,
                "ruta_local": "",
                "ruta_github": (
                    f"Data_WMS/{nombre_base}"
                ),
                "estado": "ERROR",
                "detalle": (
                    "No se encontró el archivo "
                    "del mes actual."
                ),
                "commit": "",
            }
        ]

    return [
        _publicar_archivo(
            archivo=archivo,
            carpeta_github="Data_WMS",
            grupo="WMS manual",
        )
    ]


def resumir_publicacion(
    resultados: list[dict],
) -> dict[str, int]:
    return {
        "total": len(resultados),
        "actualizados": sum(
            r["estado"] == "ACTUALIZADO"
            for r in resultados
        ),
        "sin_cambios": sum(
            r["estado"] == "SIN CAMBIOS"
            for r in resultados
        ),
        "errores": sum(
            r["estado"] == "ERROR"
            for r in resultados
        ),
    }
