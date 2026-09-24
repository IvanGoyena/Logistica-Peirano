from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import pandas as pd

# V1 de prueba. Cambiar por almacenamiento compartido/persistente antes de producción.
ARCHIVO_UBICACIONES = Path("data/ubicaciones_despacho.csv")
COLUMNAS = ["Contenedor", "Ubicacion", "FechaUbicacion", "Usuario"]


def _asegurar_archivo() -> None:
    ARCHIVO_UBICACIONES.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVO_UBICACIONES.exists():
        pd.DataFrame(columns=COLUMNAS).to_csv(
            ARCHIVO_UBICACIONES, index=False, encoding="utf-8-sig"
        )


def normalizar_ubicacion(valor: object) -> str:
    texto = str(valor or "").strip().upper().replace(" ", "")
    if texto.isdigit():
        texto = f"D{int(texto):03d}"
    coincidencia = re.fullmatch(r"D(\d{1,3})", texto)
    if not coincidencia:
        raise ValueError("Ubicación inválida. Use D001 a D060.")
    numero = int(coincidencia.group(1))
    if not 1 <= numero <= 60:
        raise ValueError("Ubicación fuera de rango. Use D001 a D060.")
    return f"D{numero:03d}"


def leer_ubicaciones() -> pd.DataFrame:
    _asegurar_archivo()
    try:
        df = pd.read_csv(ARCHIVO_UBICACIONES, dtype=str).fillna("")
    except pd.errors.EmptyDataError:
        df = pd.DataFrame(columns=COLUMNAS)
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNAS].copy()


def guardar_ubicacion(contenedor: str, ubicacion: str, usuario: str = "Tablet Despacho") -> tuple[str, str]:
    contenedor = str(contenedor).strip()
    ubicacion = normalizar_ubicacion(ubicacion)
    df = leer_ubicaciones()

    anterior = ""
    mascara = df["Contenedor"].astype(str).eq(contenedor)
    if mascara.any():
        anterior = str(df.loc[mascara, "Ubicacion"].iloc[-1])
        df = df.loc[~mascara].copy()

    nueva = pd.DataFrame([{
        "Contenedor": contenedor,
        "Ubicacion": ubicacion,
        "FechaUbicacion": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Usuario": usuario,
    }])
    pd.concat([df, nueva], ignore_index=True).to_csv(
        ARCHIVO_UBICACIONES, index=False, encoding="utf-8-sig"
    )
    return anterior, ubicacion



def guardar_ubicaciones_lote(
    contenedores: list[str],
    ubicacion: str,
    usuario: str = "Tablet Despacho",
) -> int:
    """Guarda varios contenedores en una sola escritura."""
    ubicacion = normalizar_ubicacion(ubicacion)
    contenedores = list(dict.fromkeys(
        str(c).strip() for c in contenedores if str(c).strip()
    ))

    if not contenedores:
        return 0

    df = leer_ubicaciones()
    df = df.loc[
        ~df["Contenedor"].astype(str).isin(contenedores)
    ].copy()

    fecha = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    nuevas = pd.DataFrame([
        {
            "Contenedor": contenedor,
            "Ubicacion": ubicacion,
            "FechaUbicacion": fecha,
            "Usuario": usuario,
        }
        for contenedor in contenedores
    ])

    pd.concat([df, nuevas], ignore_index=True).to_csv(
        ARCHIVO_UBICACIONES,
        index=False,
        encoding="utf-8-sig",
    )
    return len(contenedores)




def reiniciar_ubicaciones() -> int:
    """Elimina todas las ubicaciones cargadas. Uso exclusivo de pruebas."""
    df = leer_ubicaciones()
    cantidad = int(len(df))
    pd.DataFrame(
        columns=["Contenedor", "Ubicacion", "FechaUbicacion", "Usuario"]
    ).to_csv(
        ARCHIVO_UBICACIONES,
        index=False,
        encoding="utf-8-sig",
    )
    return cantidad


def liberar_contenedores(contenedores: list[str]) -> int:
    """Quita en lote las ubicaciones de los contenedores indicados."""
    contenedores = list(dict.fromkeys(
        str(c).strip() for c in contenedores if str(c).strip()
    ))
    if not contenedores:
        return 0

    df = leer_ubicaciones()
    if df.empty:
        return 0

    mascara = df["Contenedor"].astype(str).isin(contenedores)
    cantidad = int(mascara.sum())

    df.loc[~mascara].to_csv(
        ARCHIVO_UBICACIONES,
        index=False,
        encoding="utf-8-sig",
    )
    return cantidad


def quitar_ubicacion(contenedor: str) -> str:
    contenedor = str(contenedor).strip()
    df = leer_ubicaciones()
    mascara = df["Contenedor"].astype(str).eq(contenedor)
    if not mascara.any():
        return ""
    anterior = str(df.loc[mascara, "Ubicacion"].iloc[-1])
    df.loc[~mascara].to_csv(ARCHIVO_UBICACIONES, index=False, encoding="utf-8-sig")
    return anterior
