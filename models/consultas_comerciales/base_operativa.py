
from __future__ import annotations

import pandas as pd
import streamlit as st


DIAS_CERRADOS_VISIBLES = 30
DIAS_COMPLETOS_VISIBLES = 15

ESTADOS_TAREA_CONTROLADA = {
    "FINALIZADA", "FINALIZADO", "CONTROLADA", "CONTROLADO",
    "COMPLETADA", "COMPLETADO", "CERRADA", "CERRADO",
}


def _texto(serie: pd.Series) -> pd.Series:
    s = serie.fillna("").astype(str).str.strip()
    return s.mask(s.str.upper().isin({"NAN", "NONE", "<NA>", "NAT"}), "")


def _numero(serie: pd.Series, entero: bool = False) -> pd.Series:
    s = pd.to_numeric(serie, errors="coerce").fillna(0)
    return s.astype(int) if entero else s.astype(float)


def _bool(serie: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(serie):
        return serie.fillna(False)
    return (
        serie.fillna(False).astype(str).str.strip().str.upper()
        .isin({"TRUE", "1", "SI", "SÍ", "YES"})
    )


def _serie(tabla: pd.DataFrame, nombre: str, default="") -> pd.Series:
    if nombre in tabla.columns:
        return tabla[nombre]
    return pd.Series(default, index=tabla.index)


def _pedido_cerrado(fila: pd.Series) -> bool:
    presente = bool(fila.get("PresenteWMSActual", False))
    if not presente:
        return True

    textos = " ".join([
        str(fila.get("Estado", "") or ""),
        str(fila.get("EstadoWMS", "") or ""),
    ]).upper()

    return any(x in textos for x in (
        "CERRAD", "DESPACHAD", "ENTREGAD", "ANULAD", "CANCELAD"
    ))


def _resolver_estado_comercial(fila: pd.Series) -> tuple[str, str]:
    estado_pedido = str(fila.get("Estado", "") or "").strip()
    estado_wms = str(fila.get("EstadoWMS", "") or "").strip()
    estado_prep = str(fila.get("EstadoPreparacion", "") or "").strip()
    despacho = str(fila.get("Despacho", "") or "").strip()
    prep_id = str(fila.get("PreparacionID", "") or "").strip()
    datos_erp = str(fila.get("EstadoDatosERP", "") or "").strip().upper()
    presente_wms = bool(fila.get("PresenteWMSActual", False))

    combinado = " ".join([estado_pedido, estado_wms, estado_prep]).upper()

    if not presente_wms:
        return "Cerrado reciente", "Pedido cerrado recientemente"

    if datos_erp == "SIN_DATOS_ERP":
        return "Pedido recibido", "Información ERP todavía no disponible"

    if any(x in combinado for x in ("FINALIZ", "COMPLET", "CONTROLAD", "PREPARAD")):
        if despacho:
            return "Preparado", f"Preparación finalizada · {despacho}"
        return "Preparado", "Preparación finalizada"

    if any(x in combinado for x in ("EN PREPAR", "INICIAD", "PROCES")):
        return "En preparación", "Preparación en curso"

    if prep_id:
        return "Pendiente de iniciar", "Preparación creada"

    if despacho:
        return "Asignado a despacho", f"Asignado a {despacho}"

    return estado_pedido or estado_wms or "Pendiente", "Pendiente de preparación"


def _estado_tarea_controlada(valor: str) -> bool:
    texto = str(valor or "").strip().upper()
    return texto in ESTADOS_TAREA_CONTROLADA or any(
        x in texto for x in ("FINALIZ", "CONTROLAD", "COMPLET", "CERRAD")
    )


def _resolver_carros(
    pedidos: pd.DataFrame,
    tareas: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """
    Regla Comercial:
    - pedido cerrado: no mostrar carros;
    - preparación finalizada/controlada: no mostrar carros;
    - preparación pendiente/en curso: mostrar sólo carros todavía no controlados;
    - si la preparación mezcla controlados + pendientes: marcar 'Parcial'.
    """
    carros = pd.Series("", index=pedidos.index, dtype="object")
    situacion = pd.Series("", index=pedidos.index, dtype="object")

    if tareas is None or tareas.empty:
        return carros, situacion

    col_prep = next(
        (c for c in ("PreparacionId", "PreparacionID", "Preparación Id") if c in tareas.columns),
        None,
    )
    col_carro = next(
        (c for c in ("ContenedorNumero", "ContenedorId", "ContenedorID") if c in tareas.columns),
        None,
    )
    col_estado = next(
        (c for c in ("TareaEstado", "EstadoTarea", "Estado") if c in tareas.columns),
        None,
    )

    if col_prep is None or col_carro is None:
        return carros, situacion

    t = tareas.copy()
    t["_prep"] = _texto(t[col_prep])
    t["_carro"] = _texto(t[col_carro])
    t["_estado"] = _texto(t[col_estado]) if col_estado else ""
    t = t[(t["_prep"] != "") & (t["_carro"] != "")].copy()

    if t.empty:
        return carros, situacion

    t["_controlado"] = t["_estado"].map(_estado_tarea_controlada)

    resumen = {}
    for prep, grupo in t.groupby("_prep"):
        # Un mismo carro puede tener varias tareas. Se considera controlado
        # sólo cuando todas sus tareas están cerradas/controladas.
        por_carro = (
            grupo.groupby("_carro")["_controlado"]
            .all()
            .to_dict()
        )
        pendientes = [c for c, ctrl in por_carro.items() if not ctrl]
        controlados = [c for c, ctrl in por_carro.items() if ctrl]

        if pendientes and controlados:
            estado = f"🟡 Parcial · {len(controlados)} controlado(s) / {len(pendientes)} pendiente(s)"
        elif pendientes:
            estado = f"🟠 Pendiente · {len(pendientes)} carro(s)"
        elif controlados:
            estado = "🟢 Controlado"
        else:
            estado = ""

        resumen[prep] = {
            "carros_pendientes": " | ".join(pendientes),
            "situacion": estado,
        }

    for idx, fila in pedidos.iterrows():
        prep = str(fila.get("PreparacionID", "") or "").strip()
        if not prep or _pedido_cerrado(fila):
            continue

        estado_prep = str(fila.get("EstadoPreparacion", "") or "").upper()
        if any(x in estado_prep for x in ("FINALIZ", "COMPLET", "CONTROLAD", "CERRAD")):
            # Ya no interesa el carro físico en la consulta comercial.
            if prep in resumen and resumen[prep]["situacion"] == "🟢 Controlado":
                situacion.at[idx] = "🟢 Controlado"
            continue

        info = resumen.get(prep)
        if not info:
            continue

        # Mostrar solamente carros que todavía requieren control.
        carros.at[idx] = info["carros_pendientes"]
        situacion.at[idx] = info["situacion"]

    return carros, situacion


@st.cache_data(ttl=60, max_entries=2, show_spinner=False)
def construir_tabla_operativa(datos: dict[str, pd.DataFrame]) -> pd.DataFrame:
    tabla = datos.get("pedidos", pd.DataFrame()).copy()
    if tabla.empty:
        return tabla

    tabla = tabla.loc[~_bool(_serie(tabla, "EsMovimientoInterno", False))].copy()

    presente_wms = _bool(_serie(tabla, "PresenteWMSActual", False))
    ultima_wms = pd.to_datetime(
        _serie(tabla, "UltimaVezWMS", pd.NaT),
        errors="coerce",
        utc=True,
    )
    corte = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=DIAS_CERRADOS_VISIBLES)
    tabla = tabla.loc[presente_wms | (ultima_wms >= corte)].copy()

    tabla["Pedido"] = _texto(_serie(tabla, "Pedido", ""))
    tabla["ClienteCodigo"] = _texto(_serie(tabla, "ClienteCodigo", ""))
    tabla["CodigoLogistico"] = _texto(_serie(tabla, "CodigoLogistico", ""))
    tabla["Cliente"] = _texto(_serie(tabla, "Cliente", ""))
    tabla["Cliente"] = tabla["Cliente"].mask(
        tabla["Cliente"].eq(""), "Cliente sin identificar"
    )
    tabla["PreparacionID"] = _texto(_serie(tabla, "PreparacionID", ""))
    tabla["CodigoDespacho"] = _texto(_serie(tabla, "CodigoDespacho", ""))
    tabla["Despacho"] = _texto(_serie(tabla, "Despacho", ""))
    tabla["Planificacion"] = _texto(_serie(tabla, "Planificacion", ""))
    tabla["Planificacion"] = tabla["Planificacion"].mask(
        tabla["Planificacion"].eq(""), "Sin definir"
    )
    tabla["TotalUnidades"] = _numero(
        _serie(tabla, "TotalUnidadesOperativas", 0), entero=True
    )
    tabla["TotalM3"] = _numero(_serie(tabla, "VolumenM3", 0.0)).round(3)

    # Compatibilidad con otras acciones del módulo.
    tabla["ClienteDescripcion"] = tabla["Cliente"]
    tabla["DespachoDescripcion"] = tabla["Despacho"]
    tabla["DetalleFamilias"] = ""

    tabla["_activo"] = _bool(_serie(tabla, "PresenteWMSActual", False))
    tabla["_fecha_orden"] = pd.to_datetime(
        _serie(tabla, "FechaTransmisionERP", pd.NaT), errors="coerce"
    ).fillna(pd.to_datetime(_serie(tabla, "Fecha", pd.NaT), errors="coerce"))

    return (
        tabla.sort_values(
            ["_activo", "_fecha_orden"],
            ascending=[False, False],
            na_position="last",
        )
        .drop(columns=["_activo", "_fecha_orden"], errors="ignore")
        .reset_index(drop=True)
    )


@st.cache_data(ttl=60, max_entries=2, show_spinner=False)
def construir_tabla_consultas_cache(
    tabla_operativa: pd.DataFrame,
    df_tareas: pd.DataFrame,
) -> pd.DataFrame:
    if tabla_operativa is None or tabla_operativa.empty:
        return pd.DataFrame()

    t = tabla_operativa.copy()
    salida = pd.DataFrame(index=t.index)

    salida["Pedido"] = _texto(_serie(t, "Pedido", ""))
    salida["FechaCreacion"] = pd.to_datetime(
        _serie(t, "FechaCreacion", pd.NaT), errors="coerce"
    )
    salida["FechaTransmisionERP"] = pd.to_datetime(
        _serie(t, "FechaTransmisionERP", pd.NaT), errors="coerce"
    )
    salida["FechaFinControl"] = pd.to_datetime(
        _serie(t, "FechaFinControl", pd.NaT), errors="coerce"
    )
    salida["ClienteCodigo"] = _texto(_serie(t, "ClienteCodigo", ""))
    salida["CodigoLogistico"] = _texto(_serie(t, "CodigoLogistico", ""))
    salida["Cliente"] = _texto(_serie(t, "Cliente", ""))
    salida["Unidades"] = _numero(
        _serie(t, "TotalUnidadesOperativas", 0), entero=True
    )
    salida["M3"] = _numero(_serie(t, "VolumenM3", 0.0)).round(3)
    salida["VolumetriaOrigen"] = _texto(_serie(t, "VolumetriaOrigen", ""))
    salida["EstadoVolumetria"] = salida["VolumetriaOrigen"].map(
        lambda x: "⚠️ Pendiente" if str(x).strip().upper() == "SIN_DATOS_VOLUMETRIA" else "✅ Disponible"
    )
    salida["Planificacion"] = _texto(_serie(t, "Planificacion", ""))
    salida["Planificacion"] = salida["Planificacion"].mask(
        salida["Planificacion"].eq(""), "Sin definir"
    )
    salida["Despacho"] = _texto(_serie(t, "Despacho", ""))

    # Los dos estados pedidos por Comercial, directos desde la vista.
    salida["EstadoPedido"] = _texto(_serie(t, "Estado", ""))
    salida["EstadoPreparacion"] = _texto(_serie(t, "EstadoPreparacion", ""))

    # ==========================================================
    # UNIVERSO OPERATIVO PARA CONSULTAS COMERCIALES
    # ==========================================================
    # 1) Los pedidos eliminados no se muestran.
    # 2) Los completos históricos sin fecha de creación ni transmisión
    #    se consideran registros viejos ya resueltos y no se muestran.
    # 3) Los completos con FechaFinControl se mantienen visibles sólo
    #    durante los últimos 15 días desde el cierre real del control.
    # 4) Un completo sin FechaFinControl pero con trazabilidad válida
    #    se conserva para no ocultarlo por un faltante histórico.
    estado_norm = (
        salida["EstadoPedido"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    es_eliminado = estado_norm.eq("ELIMINADO")
    es_completo = estado_norm.isin(
        {"COMPLETO", "COMPLETADO", "FINALIZADO", "FINAL", "CERRADO"}
    )

    sin_fecha_creacion = salida["FechaCreacion"].isna()
    sin_fecha_transmision = salida["FechaTransmisionERP"].isna()
    # Si un pedido ya está Completo y no tiene FechaTransmisionERP,
    # Comercial lo considera cerrado/resuelto: ya no figura activo en ERP
    # y no debe permanecer en la bandeja operativa.
    completo_sin_transmision = (
        es_completo
        & sin_fecha_transmision
    )

    completo_huerfano = (
        es_completo
        & sin_fecha_creacion
        & sin_fecha_transmision
    )

    hoy = pd.Timestamp.now().normalize()
    corte_control = hoy - pd.Timedelta(days=DIAS_COMPLETOS_VISIBLES)
    completo_control_antiguo = (
        es_completo
        & salida["FechaFinControl"].notna()
        & (salida["FechaFinControl"] < corte_control)
    )

    # Fallback para históricos donde no llegó FechaFinControl:
    # un pedido completo no puede permanecer indefinidamente en Comercial.
    # Si no tiene cierre de control, usamos FechaCreacion como referencia
    # y lo mantenemos sólo durante la misma ventana de 15 días.
    completo_sin_control_creacion_antigua = (
        es_completo
        & salida["FechaFinControl"].isna()
        & salida["FechaCreacion"].notna()
        & (salida["FechaCreacion"] < corte_control)
    )

    mantener = ~(
        es_eliminado
        | completo_sin_transmision
        | completo_huerfano
        | completo_control_antiguo
        | completo_sin_control_creacion_antigua
    )

    salida = salida.loc[mantener].copy()
    t = t.loc[salida.index].copy()

    estados = t.apply(_resolver_estado_comercial, axis=1)
    salida["CategoriaComercial"] = [x[0] for x in estados]
    salida["EstadoComercial"] = [x[1] for x in estados]

    # Reindexar ambos dataframes juntos después del recorte para que
    # carros/estados sigan correspondiendo al mismo pedido.
    salida = salida.reset_index(drop=True)
    t = t.reset_index(drop=True)

    carros, situacion_carros = _resolver_carros(t, df_tareas)
    salida["Contenedor"] = carros
    salida["EstadoCarros"] = situacion_carros

    def _semaforo(fila):
        estado_pedido = str(fila.get("EstadoPedido", "") or "").upper()
        estado_prep = str(fila.get("EstadoPreparacion", "") or "").upper()
        estado_carro = str(fila.get("EstadoCarros", "") or "")

        if any(x in estado_pedido for x in ("ELIMIN", "ANULAD", "CANCELAD")):
            return "🔴 Eliminado"
        if "Parcial" in estado_carro:
            return "🟠 Control parcial"
        if any(x in estado_prep for x in ("ENPROCESO", "EN PROCESO", "INICIAD")):
            return "🔵 Preparando"
        if (
            "Controlado" in estado_carro
            or any(x in estado_prep for x in ("FINALIZ", "COMPLET", "CONTROLAD"))
        ):
            return "🟢 Controlado"
        return "🟡 Pendiente"

    salida["EstadoOperativo"] = salida.apply(_semaforo, axis=1)

    # Compatibilidad temporal con el detalle actual.
    salida["Fecha"] = pd.to_datetime(_serie(t, "Fecha", pd.NaT), errors="coerce")
    salida["HoraTransmisionERP"] = salida["FechaTransmisionERP"].dt.strftime("%H:%M").fillna("")
    salida["NroEnvioERP"] = _texto(_serie(t, "NroEnvio", ""))
    salida["Familias"] = ""

    return salida.reset_index(drop=True)


def limpiar_cache_modelo_consultas() -> None:
    construir_tabla_operativa.clear()
    construir_tabla_consultas_cache.clear()
