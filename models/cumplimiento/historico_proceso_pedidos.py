from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st

EXTENSIONES = {".csv", ".xlsx", ".xls", ".xlsm", ".parquet"}
PREFIJOS = ("FILTRAR PREPARACION", "FILTRAR_PREPARACION")


def _normalizar_texto(valor: object) -> str:
    texto = "" if pd.isna(valor) else str(valor).strip().upper()
    texto = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", texto)


def normalizar_id(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    texto = re.sub(r"\.0$", "", texto)
    return texto


def normalizar_pedido(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if not texto:
        return ""
    coincidencia = re.search(r"^\s*\d{4}[-\s]+0*(\d+)(?:-\d+)?\s*$", texto)
    if coincidencia:
        return coincidencia.group(1)
    bloques = re.findall(r"\d+", texto)
    if len(bloques) >= 2:
        candidato = bloques[-2] if len(bloques) >= 3 else bloques[-1]
        return candidato.lstrip("0") or "0"
    if bloques:
        return bloques[-1].lstrip("0") or "0"
    return texto.upper()


def _a_datetime(serie: pd.Series) -> pd.Series:
    # Los archivos de ejemplo usan formato local D/M/YYYY HH:MM.
    resultado = pd.to_datetime(serie, errors="coerce", dayfirst=True)
    faltantes = resultado.isna() & serie.notna()
    if faltantes.any():
        resultado.loc[faltantes] = pd.to_datetime(
            serie.loc[faltantes], errors="coerce", dayfirst=True
        )
    return resultado


def _extraer_periodo(ruta: Path) -> tuple[int | None, int | None]:
    texto = _normalizar_texto(ruta.stem)
    meses = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
        "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
        "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
        "NOVIEMBRE": 11, "DICIEMBRE": 12,
    }
    anio_match = re.search(r"\b(20\d{2})\b", texto)
    anio = int(anio_match.group(1)) if anio_match else None
    mes = next((numero for nombre, numero in meses.items() if nombre in texto), None)
    if mes is None:
        numeros = re.findall(r"\b(0?[1-9]|1[0-2])\b", texto)
        mes = int(numeros[-1]) if numeros else None
    return anio, mes


def _es_mes_actual(ruta: Path, ahora: datetime | None = None) -> bool:
    ahora = ahora or datetime.now()
    anio, mes = _extraer_periodo(ruta)
    if anio is not None and mes is not None:
        return anio == ahora.year and mes == ahora.month
    modificado = datetime.fromtimestamp(ruta.stat().st_mtime)
    return modificado.year == ahora.year and modificado.month == ahora.month


def descubrir_archivos_proceso(carpeta_datos: str | Path) -> list[Path]:
    carpeta = Path(carpeta_datos)
    if not carpeta.exists():
        return []
    archivos = []
    for ruta in carpeta.rglob("*"):
        if not ruta.is_file() or ruta.suffix.lower() not in EXTENSIONES:
            continue
        nombre = _normalizar_texto(ruta.stem).replace("_", " ")
        if any(nombre.startswith(prefijo.replace("_", " ")) for prefijo in PREFIJOS):
            archivos.append(ruta)
    return sorted(archivos, key=lambda r: (_extraer_periodo(r), r.name))


def firma_archivos_proceso(carpeta_datos: str | Path) -> tuple:
    return tuple(
        (str(r.resolve()), int(r.stat().st_size), int(r.stat().st_mtime_ns))
        for r in descubrir_archivos_proceso(carpeta_datos)
    )


def _leer_sin_cache(ruta: str) -> pd.DataFrame:
    path = Path(ruta)
    extension = path.suffix.lower()
    if extension == ".csv":
        errores = []
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                return pd.read_csv(path, sep=None, engine="python", encoding=encoding)
            except Exception as exc:
                errores.append(str(exc))
        raise RuntimeError(f"No se pudo leer {path.name}: {' | '.join(errores)}")
    if extension == ".parquet":
        return pd.read_parquet(path)
    return pd.read_excel(path)


@st.cache_data(persist="disk", max_entries=120, show_spinner=False)
def _leer_mes_cerrado(ruta: str, tamanio: int, modificacion_ns: int) -> pd.DataFrame:
    _ = tamanio, modificacion_ns
    return _leer_sin_cache(ruta)


@st.cache_data(ttl=120, max_entries=12, show_spinner=False)
def _leer_mes_actual(ruta: str, tamanio: int, modificacion_ns: int) -> pd.DataFrame:
    _ = tamanio, modificacion_ns
    return _leer_sin_cache(ruta)


def leer_archivo_proceso(ruta: Path) -> pd.DataFrame:
    estado = ruta.stat()
    args = (str(ruta.resolve()), int(estado.st_size), int(estado.st_mtime_ns))
    return _leer_mes_actual(*args) if _es_mes_actual(ruta) else _leer_mes_cerrado(*args)


def preparar_historico_proceso(df: pd.DataFrame, archivo_origen: str = "") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    requeridas = [
        "PedidoCodigos", "TareaId", "TareaFechaHoraEstado",
        "ControlContenedorId", "ControlContenedorFechaHoraEstado",
        "FechaHoraEstado",
    ]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(
            f"{archivo_origen or 'Histórico de proceso'} no contiene columnas requeridas: {faltantes}"
        )

    base = df.copy()
    base["ArchivoProcesoOrigen"] = archivo_origen
    base["PedidoOriginalProceso"] = base["PedidoCodigos"].fillna("").astype(str).str.strip()
    base["Pedido"] = base["PedidoCodigos"].map(normalizar_pedido)
    base["TareaIdNormalizado"] = base["TareaId"].map(normalizar_id)
    base["ControlIdNormalizado"] = base["ControlContenedorId"].map(normalizar_id)

    for columna in [
        "TareaFechaHoraEstado", "FechaHoraEstado", "ControlContenedorFechaHoraEstado"
    ]:
        base[columna] = _a_datetime(base[columna])

    columnas_texto = [
        "Cliente", "Codigo", "Domicilio", "DespachoDescripcion",
        "TareaUsuarioCompleto", "ControlContenedorUsuarioCompleto",
    ]
    for columna in columnas_texto:
        if columna not in base.columns:
            base[columna] = ""
        base[columna] = base[columna].fillna("").astype(str).str.strip()

    # Cantidades para Fill Rate. UnidadesSatisfecha es la cantidad efectivamente
    # controlada; si la fuente no la expone se usa ContenedorUnidades y, como
    # último respaldo, Unidades.
    for columna in ["Unidades", "UnidadesReservada", "UnidadesSatisfecha", "ContenedorUnidades"]:
        if columna not in base.columns:
            base[columna] = 0
        base[columna] = pd.to_numeric(
            base[columna].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False),
            errors="coerce",
        ).fillna(0).clip(lower=0)

    base["UnidadesControladasLinea"] = base["UnidadesSatisfecha"]
    sin_satisfecha = base["UnidadesControladasLinea"].le(0)
    base.loc[sin_satisfecha, "UnidadesControladasLinea"] = base.loc[sin_satisfecha, "ContenedorUnidades"]
    sin_control = base["UnidadesControladasLinea"].le(0)
    base.loc[sin_control, "UnidadesControladasLinea"] = base.loc[sin_control, "Unidades"]

    base = base.loc[base["Pedido"].ne("")].copy()
    return base


def cargar_historico_proceso(carpeta_datos: str | Path) -> dict:
    archivos = descubrir_archivos_proceso(carpeta_datos)
    tablas = []
    errores = []
    for ruta in archivos:
        try:
            tablas.append(preparar_historico_proceso(leer_archivo_proceso(ruta), ruta.name))
        except Exception as exc:
            errores.append({"archivo": ruta.name, "error": str(exc)})

    detalle = pd.concat(tablas, ignore_index=True) if tablas else pd.DataFrame()
    if not detalle.empty:
        # La fila física puede repetirse por artículo; conservamos una sola por
        # combinación pedido/tarea/control/artículo/contenedor-detalle.
        claves = [
            c for c in [
                "Pedido", "TareaIdNormalizado", "ControlIdNormalizado",
                "CodigoArticulo", "ContenedorDetalleId", "ArchivoProcesoOrigen",
            ] if c in detalle.columns
        ]
        detalle = detalle.drop_duplicates(claves, keep="last").reset_index(drop=True)

    return {
        "detalle": detalle,
        "archivos": [ruta.name for ruta in archivos],
        "errores": errores,
    }


def construir_puentes_pedido(detalle: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if detalle is None or detalle.empty:
        vacio = pd.DataFrame(columns=["IdNormalizado", "Pedido", "PedidoOriginalProceso"])
        return {"preparacion": vacio.copy(), "control": vacio.copy()}

    comunes = ["Pedido", "PedidoOriginalProceso", "Cliente", "Codigo", "Domicilio"]

    prep = detalle.loc[detalle["TareaIdNormalizado"].ne(""), comunes + ["TareaIdNormalizado"]].copy()
    prep = prep.rename(columns={"TareaIdNormalizado": "IdNormalizado"})
    prep = prep.sort_values(["IdNormalizado", "Pedido"]).drop_duplicates("IdNormalizado", keep="first")

    control = detalle.loc[detalle["ControlIdNormalizado"].ne(""), comunes + ["ControlIdNormalizado"]].copy()
    control = control.rename(columns={"ControlIdNormalizado": "IdNormalizado"})
    control = control.sort_values(["IdNormalizado", "Pedido"]).drop_duplicates("IdNormalizado", keep="first")

    return {"preparacion": prep.reset_index(drop=True), "control": control.reset_index(drop=True)}


def enriquecer_metricas_con_pedido(
    tareas: pd.DataFrame,
    detalle_metricas: pd.DataFrame,
    detalle_proceso: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    tareas_salida = tareas.copy()
    detalle_salida = detalle_metricas.copy()
    puentes = construir_puentes_pedido(detalle_proceso)

    def aplicar(tabla: pd.DataFrame) -> pd.DataFrame:
        if tabla is None or tabla.empty or "TareaId" not in tabla.columns:
            return tabla.copy()
        salida = tabla.copy()
        salida["IdNormalizado"] = salida["TareaId"].map(normalizar_id)
        proceso = salida.get("Proceso", pd.Series("", index=salida.index)).fillna("").astype(str).str.upper()
        partes = []
        for nombre, mascara in [
            ("preparacion", proceso.str.contains("PREPAR", na=False)),
            ("control", proceso.str.contains("CONTROL", na=False)),
        ]:
            parte = salida.loc[mascara].merge(puentes[nombre], on="IdNormalizado", how="left")
            partes.append(parte)
        resto = salida.loc[~(proceso.str.contains("PREPAR", na=False) | proceso.str.contains("CONTROL", na=False))].copy()
        for columna in ["Pedido", "PedidoOriginalProceso", "Cliente", "Codigo", "Domicilio"]:
            if columna not in resto.columns:
                resto[columna] = pd.NA
        partes.append(resto)
        salida = pd.concat(partes, ignore_index=True, sort=False)
        salida = salida.drop(columns=["IdNormalizado"], errors="ignore")
        return salida

    tareas_salida = aplicar(tareas_salida)
    detalle_salida = aplicar(detalle_salida)

    diagnostico = {
        "registros_proceso": int(len(detalle_proceso)) if detalle_proceso is not None else 0,
        "pedidos_proceso": int(detalle_proceso["Pedido"].nunique()) if detalle_proceso is not None and not detalle_proceso.empty else 0,
        "tareas_preparacion_mapeadas": int(tareas_salida.loc[tareas_salida.get("Proceso", "").astype(str).str.contains("PREPAR", case=False, na=False), "Pedido"].notna().sum()) if not tareas_salida.empty and "Pedido" in tareas_salida.columns else 0,
        "tareas_control_mapeadas": int(tareas_salida.loc[tareas_salida.get("Proceso", "").astype(str).str.contains("CONTROL", case=False, na=False), "Pedido"].notna().sum()) if not tareas_salida.empty and "Pedido" in tareas_salida.columns else 0,
    }
    return tareas_salida, detalle_salida, diagnostico


def resumir_hitos_pedido(detalle: pd.DataFrame) -> pd.DataFrame:
    """Consolida hitos y cantidades del reporte Filtrar Preparación.

    Fill Rate usa esta misma fuente para ambos lados del indicador:
    ``Unidades`` como cantidad pedida y ``UnidadesSatisfecha`` como cantidad
    controlada. El agrupamiento por pedido y artículo evita duplicar el
    denominador cuando una línea se distribuyó en varios contenedores.
    """
    if detalle is None or detalle.empty:
        return pd.DataFrame(columns=["ClavePedido"])

    base = detalle.copy()
    base["ClavePedido"] = base["Pedido"]

    for columna in ["Unidades", "UnidadesSatisfecha", "ContenedorUnidades"]:
        if columna not in base.columns:
            base[columna] = 0.0
        base[columna] = pd.to_numeric(
            base[columna], errors="coerce"
        ).fillna(0).clip(lower=0)

    if "CodigoArticulo" not in base.columns:
        base["CodigoArticulo"] = "SIN ARTICULO"
    base["CodigoArticulo"] = (
        base["CodigoArticulo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", "SIN ARTICULO")
    )

    if "ControlContenedorFechaHoraEstado" not in base.columns:
        base["ControlContenedorFechaHoraEstado"] = pd.NaT
    if "ControlIdNormalizado" not in base.columns:
        base["ControlIdNormalizado"] = ""

    base["TieneControlLinea"] = (
        base["ControlContenedorFechaHoraEstado"].notna()
        | base["ControlIdNormalizado"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    lineas = (
        base.groupby(
            ["ClavePedido", "CodigoArticulo"],
            as_index=False,
            dropna=False,
        )
        .agg(
            UnidadesPedidasLinea=("Unidades", "max"),
            UnidadesSatisfechasLinea=("UnidadesSatisfecha", "max"),
            UnidadesContenedorLinea=("ContenedorUnidades", "sum"),
            TieneControlLinea=("TieneControlLinea", "max"),
        )
    )

    lineas["UnidadesControladasLinea"] = lineas[
        "UnidadesSatisfechasLinea"
    ]
    usar_respaldo = (
        lineas["UnidadesControladasLinea"].le(0)
        & lineas["TieneControlLinea"]
    )
    lineas.loc[usar_respaldo, "UnidadesControladasLinea"] = lineas.loc[
        usar_respaldo, "UnidadesContenedorLinea"
    ]
    lineas["UnidadesControladasLinea"] = np.minimum(
        lineas["UnidadesControladasLinea"],
        lineas["UnidadesPedidasLinea"],
    )
    lineas["LineaCompletaProceso"] = (
        lineas["UnidadesPedidasLinea"].gt(0)
        & lineas["UnidadesControladasLinea"].ge(
            lineas["UnidadesPedidasLinea"]
        )
    )

    cantidades = (
        lineas.groupby("ClavePedido", as_index=False)
        .agg(
            UnidadesPedidasProceso=("UnidadesPedidasLinea", "sum"),
            UnidadesControladasProceso=(
                "UnidadesControladasLinea", "sum"
            ),
            LineasPedidasProceso=("CodigoArticulo", "size"),
            LineasCompletasProceso=("LineaCompletaProceso", "sum"),
        )
    )

    hitos = (
        base.groupby("ClavePedido", as_index=False)
        .agg(
            PedidoProceso=("PedidoOriginalProceso", "first"),
            ClienteProceso=("Cliente", "first"),
            ClienteCodigoProceso=("Codigo", "first"),
            DespachoDescripcionProceso=("DespachoDescripcion", "first"),
            CodigoDespachoProceso=("DespachoCodigo", "first"),
            FechaHoraInicioPreparacionProceso=(
                "TareaFechaHoraEstado", "min"
            ),
            FechaHoraFinPreparacionProceso=("FechaHoraEstado", "max"),
            FechaHoraInicioControlProceso=(
                "ControlContenedorFechaHoraEstado", "min"
            ),
            FechaHoraFinControlProceso=(
                "ControlContenedorFechaHoraEstado", "max"
            ),
            CantidadTareasPreparacionProceso=(
                "TareaIdNormalizado",
                lambda serie: serie[serie.ne("")].nunique(),
            ),
            CantidadControlesProceso=(
                "ControlIdNormalizado",
                lambda serie: serie[serie.ne("")].nunique(),
            ),
        )
    )

    return hitos.merge(cantidades, on="ClavePedido", how="left")

def limpiar_cache_historico_proceso() -> None:
    _leer_mes_actual.clear()
