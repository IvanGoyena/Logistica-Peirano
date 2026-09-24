from __future__ import annotations

import re
import pandas as pd


def _texto(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    return re.sub(r"\.0$", "", texto)


def normalizar_pedido(valor: object) -> str:
    """Ej.: '0001  214624-1' -> '214624'."""
    texto = _texto(valor)
    if not texto:
        return ""
    ultimo = texto.split()[-1]
    return ultimo.split("-")[0].strip()


def normalizar_contenedor(valor: object) -> str:
    return _texto(valor).upper()


def es_contenedor_numerico(valor: object) -> bool:
    return normalizar_contenedor(valor).isdigit()


def construir_base_contenedores_controlados(
    df_filtrar_preparacion: pd.DataFrame,
    df_informe_tareas: pd.DataFrame,
    tabla_operativa: pd.DataFrame,
) -> pd.DataFrame:
    """
    Una fila por contenedor físico controlado.

    Regla operativa V1:
    - sólo contenedores numéricos;
    - deben poseer ControlContenedorId;
    - Filtrar Preparación define el control y el pedido;
    - Informe Tareas se usa para enriquecer/validar preparación y despacho;
    - tabla_operativa aporta planificación y datos consolidados del pedido.
    """
    fp = df_filtrar_preparacion.copy()

    requeridas = {
        "PedidoCodigos", "Contenedor", "ControlContenedorId",
        "ControlContenedorFechaHoraEstado", "DespachoDescripcion",
        "Codigo", "Cliente",
    }
    faltantes = requeridas - set(fp.columns)
    if faltantes:
        raise ValueError(
            "Filtrar Preparación no contiene columnas requeridas: "
            f"{sorted(faltantes)}"
        )

    fp["Contenedor"] = fp["Contenedor"].apply(normalizar_contenedor)
    fp["Pedido"] = fp["PedidoCodigos"].apply(normalizar_pedido)
    fp["ControlContenedorIdNorm"] = (
        fp["ControlContenedorId"].apply(_texto)
    )

    fp = fp.loc[
        fp["Contenedor"].apply(es_contenedor_numerico)
        & fp["ControlContenedorIdNorm"].ne("")
        & fp["Pedido"].ne("")
    ].copy()

    fp["FechaControl"] = pd.to_datetime(
        fp["ControlContenedorFechaHoraEstado"],
        errors="coerce",
        dayfirst=True,
    )

    # El reporte está a nivel detalle/artículo. Consolidamos a contenedor.
    base = (
        fp.sort_values("FechaControl")
        .groupby("Contenedor", as_index=False)
        .agg(
            Pedido=("Pedido", "last"),
            PreparacionID=("Id", lambda s: _texto(s.iloc[-1])),
            ClienteCodigo=("Codigo", lambda s: _texto(s.iloc[-1]).upper()),
            ClienteDescripcion=("Cliente", lambda s: _texto(s.iloc[-1])),
            DespachoControl=("DespachoDescripcion", lambda s: _texto(s.iloc[-1])),
            FechaControl=("FechaControl", "max"),
            UsuarioControl=(
                "ControlContenedorUsuarioCompleto",
                lambda s: _texto(s.dropna().iloc[-1]) if not s.dropna().empty else "",
            ) if "ControlContenedorUsuarioCompleto" in fp.columns else (
                "Cliente", lambda s: ""
            ),
            UnidadesContenedor=("ContenedorUnidades", "sum")
            if "ContenedorUnidades" in fp.columns else ("Contenedor", "size"),
        )
    )

    # Bultos controlados del pedido = contenedores únicos, nunca filas/unidades.
    bultos = (
        base.groupby("Pedido")["Contenedor"]
        .nunique()
        .rename("BultosControladosPedido")
        .reset_index()
    )
    base = base.merge(bultos, on="Pedido", how="left", validate="many_to_one")

    # Informe Tareas: enriquecimiento no destructivo.
    if df_informe_tareas is not None and not df_informe_tareas.empty:
        it = df_informe_tareas.copy()
        if "ContenedorNumero" in it.columns:
            it["Contenedor"] = it["ContenedorNumero"].apply(normalizar_contenedor)
            it = it.loc[it["Contenedor"].apply(es_contenedor_numerico)].copy()
            columnas = [c for c in [
                "Contenedor", "PreparacionId", "DespachoDescripcion",
                "AreaDescripcion", "VolumenText", "PesoText"
            ] if c in it.columns]
            if columnas:
                it = it[columnas].drop_duplicates("Contenedor", keep="last")
                ren = {
                    "PreparacionId": "PreparacionIDTarea",
                    "DespachoDescripcion": "DespachoTarea",
                    "AreaDescripcion": "AreaTarea",
                    "VolumenText": "VolumenTarea",
                    "PesoText": "PesoTarea",
                }
                base = base.merge(
                    it.rename(columns=ren), on="Contenedor", how="left",
                    validate="one_to_one"
                )

    # Tabla operativa: un registro por pedido para planificación/agrupador.
    if tabla_operativa is not None and not tabla_operativa.empty and "Pedido" in tabla_operativa.columns:
        op = tabla_operativa.copy()
        op["Pedido"] = op["Pedido"].apply(normalizar_pedido)
        cols = [c for c in [
            "Pedido", "ClienteCodigo", "ClienteDescripcion",
            "DespachoDescripcion", "Planificacion", "PreparacionID",
            "TotalM3", "TotalUnidades"
        ] if c in op.columns]
        op = op[cols].drop_duplicates("Pedido", keep="last")
        ren = {c: f"Operativa_{c}" for c in cols if c != "Pedido"}
        base = base.merge(
            op.rename(columns=ren), on="Pedido", how="left", validate="many_to_one"
        )

    # Campos finales visibles con fallback a Control.
    if "Operativa_ClienteDescripcion" in base.columns:
        base["ClienteDescripcion"] = base["Operativa_ClienteDescripcion"].fillna("").where(
            base["Operativa_ClienteDescripcion"].fillna("").astype(str).str.strip().ne(""),
            base["ClienteDescripcion"],
        )
    if "Operativa_DespachoDescripcion" in base.columns:
        base["Agrupador"] = base["Operativa_DespachoDescripcion"].fillna("").where(
            base["Operativa_DespachoDescripcion"].fillna("").astype(str).str.strip().ne(""),
            base["DespachoControl"],
        )
    else:
        base["Agrupador"] = base["DespachoControl"]

    base["Planificacion"] = base.get("Operativa_Planificacion", "")
    return base.sort_values(["FechaControl", "Contenedor"], ascending=[False, True]).reset_index(drop=True)
