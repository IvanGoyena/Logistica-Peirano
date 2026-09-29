from __future__ import annotations

import pandas as pd
import re
import html
from pathlib import Path
from datetime import datetime
from io import BytesIO
import streamlit as st

from models.tareas_modulo.contexto import construir_contexto_tareas
from models.tareas import sugerir_equipamiento_operativo
from utils.rendimiento import medir_tiempo, mostrar_info_dataframe
from utils.tareas.carga import cargar_fuentes_tareas, invalidar_cache_tareas
from utils.tareas.formatos import preparar_tabla_operativa_visual, resaltar_carro
from utils.tareas.graficos import grafico_avance_despacho, grafico_sectorizaciones
from utils.tareas.estilo_pantalla import (
    aplicar_estilo_pantalla,
    perfil_visual,
    selector_modo_visual,
)



def _fmt_entero(valor: object) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _solo_nombre_controlador(valor: object) -> str:
    """Devuelve únicamente el primer nombre visible del controlador."""
    if valor is None or pd.isna(valor):
        return ""
    texto = re.sub(r"\\s+", " ", str(valor)).strip()
    if not texto or texto.lower() in {"nan", "none", "<na>"}:
        return ""
    return texto.split(" ", 1)[0]


def _detalle_control_finalizado(contexto: dict[str, object]) -> str:
    resumen = contexto["resumen"]
    control = contexto.get("control_dia_anterior", {})

    base = (
        f"Hoy {_fmt_entero(resumen['CarrosFinalizadosHoy'])} · "
        f"Ayer {_fmt_entero(resumen['CarrosFinalizadosAyer'])}"
    )

    if not control or not control.get("disponible"):
        return base + "<br>Control histórico sin datos"

    fecha = control.get("fecha")
    fecha_visible = (
        pd.Timestamp(fecha).strftime("%d/%m")
        if fecha is not None and pd.notna(fecha)
        else "Último cierre"
    )
    etiqueta_fecha = (
        "Ayer"
        if control.get("es_dia_calendario_anterior")
        else fecha_visible
    )

    return (
        base
        + "<br>"
        + f"📦 {etiqueta_fecha}: "
        + f"{_fmt_entero(control.get('unidades', 0))} unidades cerradas"
    )


def _render_kpis(contexto: dict[str, object]) -> None:
    resumen = contexto["resumen"]
    pendiente_pick = contexto["pendiente_pick"]

    tarjetas = [
        (
            "📦 Pedidos pendientes",
            _fmt_entero(contexto["pedidos_pendientes"]),
            f"{_fmt_entero(contexto['unidades_pendientes'])} unidades",
        ),
        (
            "📥 Pendiente de pickear",
            _fmt_entero(pendiente_pick["Preparaciones"]),
            f"{_fmt_entero(pendiente_pick['Unidades'])} unidades",
        ),
        (
            "🛒 Carros en curso",
            _fmt_entero(resumen["CarrosEnCurso"]),
            f"{_fmt_entero(contexto['unidades_carros_curso'])} unidades",
        ),
        (
            "✅ Carros finalizados",
            _fmt_entero(resumen["CarrosFinalizados"]),
            _detalle_control_finalizado(contexto),
        ),
    ]

    # st.columns garantiza que las cuatro tarjetas ocupen TODO el ancho.
    columnas = st.columns(4, gap="medium")

    for columna, (etiqueta, valor, detalle) in zip(columnas, tarjetas):
        with columna:
            html = (
                '<div class="tareas-kpi-card tareas-kpi-card-principal">'
                f'<div class="tareas-kpi-label">{etiqueta}</div>'
                f'<div class="tareas-kpi-value">{valor}</div>'
                f'<div class="tareas-kpi-detail">{detalle}</div>'
                '</div>'
            )
            st.markdown(html, unsafe_allow_html=True)

    # Más presencia visual sin alterar el resto del estilo de la app.
    st.markdown(
        """
        <style>
        .tareas-kpi-card-principal {
            width: 100% !important;
            min-height: 150px !important;
            padding: 20px 22px !important;
            box-sizing: border-box !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-label {
            font-size: clamp(1rem, 1.08vw, 1.18rem) !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-value {
            font-size: clamp(2.8rem, 3.15vw, 3.75rem) !important;
        }
        .tareas-kpi-card-principal .tareas-kpi-detail {
            font-size: clamp(.9rem, .97vw, 1.08rem) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


_ARCHIVO_CIERRES_AGRUPACION = Path(__file__).resolve().parent / "data" / "agrupadores_finalizados.csv"


def _leer_agrupadores_finalizados() -> pd.DataFrame:
    columnas = ["Agrupador", "FechaHoraCierre"]
    if not _ARCHIVO_CIERRES_AGRUPACION.exists():
        return pd.DataFrame(columns=columnas)
    try:
        df = pd.read_csv(_ARCHIVO_CIERRES_AGRUPACION, dtype=str)
        for c in columnas:
            if c not in df.columns:
                df[c] = ""
        return df[columnas].copy()
    except Exception:
        return pd.DataFrame(columns=columnas)


def _estado_cierres_agrupacion(
    horas_visibilidad: int = 8,
) -> tuple[set[str], set[str]]:
    """Devuelve (cerrados_visibles, cerrados_expirados).

    - cerrados_visibles: ya se finalizó manualmente, pero aún no pasaron 8 h.
    - cerrados_expirados: ya pasaron 8 h y deben ocultarse de la tabla operativa.

    El CSV se conserva como histórico; no se borra ningún cierre.
    """
    df = _leer_agrupadores_finalizados()
    if df.empty:
        return set(), set()

    df = df.copy()
    df["Agrupador"] = (
        df["Agrupador"].fillna("").astype(str).str.strip()
    )
    df["FechaHoraCierre_dt"] = pd.to_datetime(
        df["FechaHoraCierre"],
        errors="coerce",
    )
    df = df.loc[
        df["Agrupador"].ne("") & df["FechaHoraCierre_dt"].notna()
    ].copy()

    if df.empty:
        return set(), set()

    ahora = pd.Timestamp.now()
    limite = ahora - pd.Timedelta(hours=horas_visibilidad)

    visibles = set(
        df.loc[df["FechaHoraCierre_dt"].gt(limite), "Agrupador"].tolist()
    )
    expirados = set(
        df.loc[df["FechaHoraCierre_dt"].le(limite), "Agrupador"].tolist()
    )
    return visibles, expirados


def _agrupadores_cerrados() -> set[str]:
    """Compatibilidad: sólo devuelve los cierres que ya cumplieron 8 horas."""
    _, expirados = _estado_cierres_agrupacion(horas_visibilidad=8)
    return expirados


def _agrupador_cerrado_visible(agrupador: str) -> bool:
    """Indica si fue finalizado manualmente y sigue dentro de sus 8 h visibles."""
    visibles, _ = _estado_cierres_agrupacion(horas_visibilidad=8)
    return str(agrupador).strip() in visibles

def _cerrar_agrupador_manual(agrupador: str) -> None:
    agrupador = str(agrupador).strip()
    if not agrupador:
        return
    _ARCHIVO_CIERRES_AGRUPACION.parent.mkdir(parents=True, exist_ok=True)
    df = _leer_agrupadores_finalizados()
    df = df.loc[df["Agrupador"].fillna("").astype(str).str.strip().ne(agrupador)].copy()
    nuevo = pd.DataFrame([{
        "Agrupador": agrupador,
        "FechaHoraCierre": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }])
    pd.concat([df, nuevo], ignore_index=True).to_csv(
        _ARCHIVO_CIERRES_AGRUPACION, index=False, encoding="utf-8-sig"
    )


def _mapa_controladores_por_preparacion_area(
    contexto: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    """(Preparacion, Area) -> usuario + hora del control real.

    Cruce principal: PreparacionId + ContenedorId.
    Fallback: PreparacionId + TareaId.
    """
    control = contexto.get("_control_historico_raw")
    tareas = contexto.get("_tareas_raw")
    if not isinstance(control, pd.DataFrame) or control.empty:
        return {}
    if not isinstance(tareas, pd.DataFrame) or tareas.empty:
        return {}

    c = control.copy()
    t = tareas.copy()
    c.columns = [str(x).replace("\ufeff", "").strip() for x in c.columns]
    t.columns = [str(x).replace("\ufeff", "").strip() for x in t.columns]

    if "Id" not in c.columns or "PreparacionId" not in t.columns or "AreaDescripcion" not in t.columns:
        return {}

    def _key(serie):
        return (
            serie.astype("string").fillna("").str.strip()
            .str.replace(r"\.0+$", "", regex=True)
        )

    c["_PrepKey"] = _key(c["Id"])
    t["_PrepKey"] = _key(t["PreparacionId"])

    usuario_col = "ControlContenedorUsuarioCompleto"
    if usuario_col not in c.columns:
        return {}

    fecha_cols = [
        "ControlContenedorFechaHoraEstado",
        "ControlContenedorFechaHora",
        "FechaHoraControl",
        "FechaHoraEstado",
        "FechaHora",
    ]
    fecha_col = next((x for x in fecha_cols if x in c.columns), None)

    c["_Usuario"] = c[usuario_col].astype("string").fillna("").str.strip()
    c["_FechaControl"] = (
        pd.to_datetime(c[fecha_col], errors="coerce", dayfirst=True)
        if fecha_col else pd.NaT
    )

    cruces = []

    # 1) Principal: Preparación + Contenedor.
    if "ContenedorId" in c.columns and "ContenedorId" in t.columns:
        cc = c.copy()
        tt = t.copy()
        cc["_ContKey"] = _key(cc["ContenedorId"])
        tt["_ContKey"] = _key(tt["ContenedorId"])
        m = cc.loc[
            cc["_PrepKey"].ne("") & cc["_ContKey"].ne("") & cc["_Usuario"].ne(""),
            ["_PrepKey", "_ContKey", "_Usuario", "_FechaControl"],
        ].merge(
            tt.loc[
                tt["_PrepKey"].ne("") & tt["_ContKey"].ne(""),
                ["_PrepKey", "_ContKey", "AreaDescripcion"],
            ],
            on=["_PrepKey", "_ContKey"],
            how="inner",
        )
        if not m.empty:
            cruces.append(m)

    # 2) Fallback: Preparación + Tarea.
    if "TareaId" in c.columns and "TareaId" in t.columns:
        cc = c.copy()
        tt = t.copy()
        cc["_TareaKey"] = _key(cc["TareaId"])
        tt["_TareaKey"] = _key(tt["TareaId"])
        m = cc.loc[
            cc["_PrepKey"].ne("") & cc["_TareaKey"].ne("") & cc["_Usuario"].ne(""),
            ["_PrepKey", "_TareaKey", "_Usuario", "_FechaControl"],
        ].merge(
            tt.loc[
                tt["_PrepKey"].ne("") & tt["_TareaKey"].ne(""),
                ["_PrepKey", "_TareaKey", "AreaDescripcion"],
            ],
            on=["_PrepKey", "_TareaKey"],
            how="inner",
        )
        if not m.empty:
            cruces.append(m)

    if not cruces:
        return {}

    m = pd.concat(cruces, ignore_index=True, sort=False)
    m["_Area"] = (
        m["AreaDescripcion"].astype("string").fillna("").str.strip().str.upper()
    )
    m = m.loc[m["_PrepKey"].ne("") & m["_Area"].ne("") & m["_Usuario"].ne("")].copy()
    m = (
        m.sort_values("_FechaControl", na_position="first")
        .drop_duplicates(["_PrepKey", "_Area"], keep="last")
    )

    return {
        (r["_PrepKey"], r["_Area"]): {
            "usuario": str(r["_Usuario"]).strip(),
            "fecha_hora": r["_FechaControl"],
        }
        for _, r in m.iterrows()
    }


def _despachos_id_expirados_por_ultimo_control(
    contexto: dict[str, object],
    horas: int = 8,
) -> set[str]:
    """DespachoId cerrados en DIGIP cuyo último control real ya superó `horas`.

    Fuentes:
    - Informe Tareas: define qué PreparacionId pertenecen a cada DespachoId.
    - Pedidos DIGIP: confirma que TODAS esas preparaciones están cerradas
      (Estado Completo/Completado o Estado preparación Completa/Completada).
    - Filtrar Preparaciones: aporta la fecha/hora REAL del último control.

    Nunca se vence por DespachoDescripcion, porque ese nombre se reutiliza.
    """
    tareas = contexto.get("_tareas_raw")
    pedidos = contexto.get("_pedidos_raw")
    control = contexto.get("_control_historico_raw")

    if (
        not isinstance(tareas, pd.DataFrame) or tareas.empty
        or not isinstance(pedidos, pd.DataFrame) or pedidos.empty
        or not isinstance(control, pd.DataFrame) or control.empty
    ):
        return set()

    t = tareas.copy()
    p = pedidos.copy()
    c = control.copy()

    t.columns = [str(x).replace("\ufeff", "").strip() for x in t.columns]
    p.columns = [str(x).replace("\ufeff", "").strip() for x in p.columns]
    c.columns = [str(x).replace("\ufeff", "").strip() for x in c.columns]

    def _key(serie: pd.Series) -> pd.Series:
        return (
            serie.astype("string")
            .fillna("")
            .str.strip()
            .str.replace(r"\.0+$", "", regex=True)
        )

    # ---------------- Informe Tareas ----------------
    if not {"DespachoId", "PreparacionId"}.issubset(t.columns):
        return set()

    t["_DespachoIdKey"] = _key(t["DespachoId"])
    t["_PrepKey"] = _key(t["PreparacionId"])
    t = t.loc[
        t["_DespachoIdKey"].ne("") & t["_PrepKey"].ne(""),
        ["_DespachoIdKey", "_PrepKey"],
    ].drop_duplicates()

    if t.empty:
        return set()

    # ---------------- Pedidos DIGIP ----------------
    prep_col = next(
        (
            x for x in [
                "Preparación Id",
                "Preparacion Id",
                "PreparacionId",
                "PreparaciónId",
            ]
            if x in p.columns
        ),
        None,
    )
    if not prep_col:
        return set()

    p["_PrepKey"] = _key(p[prep_col])

    estado_pedido_col = next(
        (x for x in ["Estado", "Estado pedido", "Estado Pedido"] if x in p.columns),
        None,
    )
    estado_prep_col = next(
        (
            x for x in [
                "Estado preparación",
                "Estado preparacion",
                "EstadoPreparacion",
                "Estado Preparación",
            ]
            if x in p.columns
        ),
        None,
    )

    if not estado_pedido_col and not estado_prep_col:
        return set()

    cerrados = {"COMPLETO", "COMPLETADO", "COMPLETA", "COMPLETADA"}

    estado_pedido = (
        p[estado_pedido_col]
        .astype("string").fillna("").str.strip().str.upper()
        if estado_pedido_col
        else pd.Series("", index=p.index, dtype="string")
    )
    estado_prep = (
        p[estado_prep_col]
        .astype("string").fillna("").str.strip().str.upper()
        if estado_prep_col
        else pd.Series("", index=p.index, dtype="string")
    )

    # Cerrada si DIGIP confirma cierre a nivel pedido O preparación.
    p["_CerradaDIGIP"] = estado_pedido.isin(cerrados) | estado_prep.isin(cerrados)

    # Una preparación puede repetirse en el archivo: si existe una fila no cerrada,
    # no la damos por cerrada.
    estado_por_prep = (
        p.loc[p["_PrepKey"].ne("")]
        .groupby("_PrepKey")["_CerradaDIGIP"]
        .all()
    )

    t["_CerradaDIGIP"] = t["_PrepKey"].map(estado_por_prep).fillna(False)

    resumen_digip = (
        t.groupby("_DespachoIdKey", as_index=False)
        .agg(
            Preparaciones=("_PrepKey", "nunique"),
            PreparacionesCerradas=("_CerradaDIGIP", "sum"),
        )
    )

    ids_cerrados = set(
        resumen_digip.loc[
            resumen_digip["Preparaciones"].gt(0)
            & resumen_digip["PreparacionesCerradas"].eq(
                resumen_digip["Preparaciones"]
            ),
            "_DespachoIdKey",
        ].tolist()
    )

    if not ids_cerrados:
        return set()

    # ---------------- Filtrar Preparaciones ----------------
    if "Id" not in c.columns:
        return set()

    fecha_control_col = next(
        (
            x for x in [
                "ControlContenedorFechaHoraEstado",
                "ControlContenedorFechaHora",
                "FechaHoraControl",
            ]
            if x in c.columns
        ),
        None,
    )
    if not fecha_control_col:
        return set()

    c["_PrepKey"] = _key(c["Id"])
    c["_FechaControl"] = pd.to_datetime(
        c[fecha_control_col],
        errors="coerce",
        dayfirst=True,
    )

    ultimo_control_prep = (
        c.loc[
            c["_PrepKey"].ne("") & c["_FechaControl"].notna(),
            ["_PrepKey", "_FechaControl"],
        ]
        .groupby("_PrepKey")["_FechaControl"]
        .max()
    )

    t["_FechaControl"] = t["_PrepKey"].map(ultimo_control_prep)

    # Para cada DespachoId cerrado por DIGIP, la hora de cierre operativo
    # es el último control real de cualquiera de sus preparaciones.
    ultimo_por_despacho = (
        t.loc[t["_DespachoIdKey"].isin(ids_cerrados)]
        .groupby("_DespachoIdKey")["_FechaControl"]
        .max()
        .dropna()
    )

    if ultimo_por_despacho.empty:
        return set()

    limite = pd.Timestamp.now() - pd.Timedelta(hours=horas)

    return set(
        ultimo_por_despacho.loc[
            ultimo_por_despacho.le(limite)
        ].index.astype(str).tolist()
    )



def _render_indicadores(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    # 1) Avance de despachos arriba, ocupando todo el ancho.
    with st.container(border=True):
        st.markdown("#### 🚛 Avance de despachos")
        sin_iniciar = contexto["despachos_sin_iniciar"]
        if sin_iniciar:
            st.caption(
                f"Sin iniciar ({len(sin_iniciar)}): " + " · ".join(sin_iniciar)
            )

        avance = contexto["avance_despachos"].copy()

        # Solo mostrar agrupadores que ya tengan avance (> 0%).
        # Este filtro es únicamente visual y no modifica el resto del tablero.
        if not avance.empty:
            if "Porcentaje" in avance.columns:
                porcentaje = pd.to_numeric(
                    avance["Porcentaje"], errors="coerce"
                ).fillna(0)
                avance = avance.loc[porcentaje.gt(0)].copy()
            elif "TareasFinalizadas" in avance.columns:
                finalizadas = pd.to_numeric(
                    avance["TareasFinalizadas"], errors="coerce"
                ).fillna(0)
                avance = avance.loc[finalizadas.gt(0)].copy()

        if avance.empty:
            st.info("No hay despachos con avance iniciado.")
        else:
            # Carrusel horizontal: una sola fila, ordenada por mayor avance.
            avance = avance.copy()

            if "Porcentaje" in avance.columns:
                avance["_OrdenAvance"] = pd.to_numeric(
                    avance["Porcentaje"], errors="coerce"
                ).fillna(0.0)
            elif {"TareasFinalizadas", "TareasTotales"}.issubset(avance.columns):
                _fin = pd.to_numeric(avance["TareasFinalizadas"], errors="coerce").fillna(0.0)
                _tot = pd.to_numeric(avance["TareasTotales"], errors="coerce").fillna(0.0)
                avance["_OrdenAvance"] = (
                    _fin.div(_tot.where(_tot.gt(0))).fillna(0.0) * 100.0
                )
            else:
                avance["_OrdenAvance"] = 0.0

            avance["_OrdenOriginal"] = range(len(avance))
            avance = avance.sort_values(
                ["_OrdenAvance", "_OrdenOriginal"],
                ascending=[False, True],
                kind="stable",
            ).reset_index(drop=True)

            visibles = 5 if perfil == "tv" else 4
            visibles = max(1, min(visibles, len(avance)))
            max_inicio = max(0, len(avance) - visibles)

            clave_inicio = f"avance_despachos_inicio_{perfil}"
            if clave_inicio not in st.session_state:
                st.session_state[clave_inicio] = 0
            st.session_state[clave_inicio] = min(
                max(int(st.session_state[clave_inicio]), 0), max_inicio
            )

            if len(avance) > visibles:
                _, nav_izq, nav_der = st.columns([12, 0.55, 0.55])
                with nav_izq:
                    if st.button(
                        "←",
                        key=f"avance_despachos_anterior_{perfil}",
                        help="Ver agrupadores más avanzados",
                        disabled=st.session_state[clave_inicio] <= 0,
                        use_container_width=True,
                    ):
                        st.session_state[clave_inicio] = max(
                            0, st.session_state[clave_inicio] - 1
                        )
                with nav_der:
                    if st.button(
                        "→",
                        key=f"avance_despachos_siguiente_{perfil}",
                        help="Ver agrupadores menos avanzados",
                        disabled=st.session_state[clave_inicio] >= max_inicio,
                        use_container_width=True,
                    ):
                        st.session_state[clave_inicio] = min(
                            max_inicio, st.session_state[clave_inicio] + 1
                        )

            inicio = st.session_state[clave_inicio]
            avance_visible = avance.iloc[inicio:inicio + visibles].copy()

            # Siempre una única fila.
            columnas = st.columns(len(avance_visible))
            for columna, (_, fila) in zip(columnas, avance_visible.iterrows()):
                with columna:
                    grafico_avance_despacho(
                        fila.drop(
                            labels=["_OrdenAvance", "_OrdenOriginal"],
                            errors="ignore",
                        ),
                        perfil=perfil,
                    )

    # 2) Debajo: Estado de Preparaciones / Control a todo el ancho.
    with st.container(border=True):
        st.markdown("#### 🚨 Estado de Preparaciones / Control")

        control_base = contexto["tabla_operativa"].copy()

        # INTERPLANTA no forma parte de esta visual operativa.
        # Se excluye sólo de Estado de Preparaciones / Control.
        if not control_base.empty and "Despacho" in control_base.columns:
            _despacho_control = (
                control_base["Despacho"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            control_base = control_base.loc[
                ~_despacho_control.eq("INTERPLANTA")
            ].copy()

        # ------------------------------------------------------
        # INSTANCIA ACTUAL DE CADA AGRUPADOR
        # ------------------------------------------------------
        # DespachoDescripcion es reutilizable. Antes de calcular selector/KPIs,
        # dejamos en la visual solamente el DespachoId más reciente de cada nombre.
        # La vigencia se resuelve con Informe Tareas crudo, donde DespachoId sí
        # identifica una instancia concreta del agrupador.
        _tareas_raw_instancia = contexto.get("_tareas_raw")
        if (
            isinstance(_tareas_raw_instancia, pd.DataFrame)
            and not _tareas_raw_instancia.empty
            and {"DespachoId", "DespachoDescripcion", "FechaHoraEstado"}.issubset(
                _tareas_raw_instancia.columns
            )
            and "DespachoId" in control_base.columns
            and "Despacho" in control_base.columns
        ):
            _ti = _tareas_raw_instancia[
                ["DespachoId", "DespachoDescripcion", "FechaHoraEstado"]
            ].copy()

            _ti["_DespachoIdKey"] = (
                _ti["DespachoId"]
                .astype("string")
                .fillna("")
                .str.strip()
                .str.replace(r"\.0+$", "", regex=True)
            )
            _ti["_DespachoNombreKey"] = (
                _ti["DespachoDescripcion"]
                .astype("string")
                .fillna("")
                .str.strip()
            )
            _ti["_FechaActividad"] = pd.to_datetime(
                _ti["FechaHoraEstado"],
                errors="coerce",
                dayfirst=True,
            )

            _ti = _ti.loc[
                _ti["_DespachoIdKey"].ne("")
                & _ti["_DespachoNombreKey"].ne("")
                & _ti["_FechaActividad"].notna()
            ].copy()

            if not _ti.empty:
                # Una fila por instancia: última actividad registrada para ese DespachoId.
                _instancias = (
                    _ti.groupby(
                        ["_DespachoNombreKey", "_DespachoIdKey"],
                        as_index=False,
                    )["_FechaActividad"]
                    .max()
                    .sort_values(
                        ["_DespachoNombreKey", "_FechaActividad", "_DespachoIdKey"],
                        kind="stable",
                    )
                )

                # Para cada nombre reutilizable, conservar exclusivamente el ID vigente.
                _vigentes = (
                    _instancias
                    .drop_duplicates("_DespachoNombreKey", keep="last")
                    .set_index("_DespachoNombreKey")["_DespachoIdKey"]
                    .to_dict()
                )

                _cb_nombre = (
                    control_base["Despacho"]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                )
                _cb_id = (
                    control_base["DespachoId"]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .str.replace(r"\.0+$", "", regex=True)
                )
                _id_vigente = _cb_nombre.map(_vigentes)

                # Si conocemos el ID vigente del nombre, exigimos coincidencia exacta.
                # Si no está en el crudo, no alteramos esa fila por seguridad.
                _mask_instancia_actual = (
                    _id_vigente.isna()
                    | _id_vigente.eq("")
                    | _cb_id.eq(_id_vigente)
                )
                control_base = control_base.loc[_mask_instancia_actual].copy()

        # La tabla de Preparaciones / Control debe mostrar solamente
        # agrupadores que siguen operativamente abiertos (< 100%).
        # `avance_despachos` ya excluye los despachos al 100%, mientras que
        # `despachos_sin_iniciar` conserva los que siguen activos al 0%.
        # De esta forma un agrupador totalmente cerrado (p. ej. CAMION MAR 1)
        # desaparece aunque sus carros finalizados sigan dentro de la ventana
        # histórica de `tabla_operativa`.
        despachos_activos = set()
        avance_activo = contexto.get("avance_despachos")
        if isinstance(avance_activo, pd.DataFrame) and not avance_activo.empty:
            if "Despacho" in avance_activo.columns:
                despachos_activos.update(
                    avance_activo["Despacho"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .loc[lambda x: x.ne("")]
                    .tolist()
                )

        despachos_activos.update(
            str(x).strip()
            for x in contexto.get("despachos_sin_iniciar", [])
            if str(x).strip()
        )

        # NUEVO: un agrupador al 100% sigue visible hasta que Operaciones lo cierre
        # manualmente con "Agrupación Finalizada". tabla_operativa conserva la ventana
        # histórica necesaria para mantenerlo en pantalla.
        if not control_base.empty and "Despacho" in control_base.columns:
            despachos_activos.update(
                control_base["Despacho"].fillna("").astype(str).str.strip()
                .loc[lambda x: x.ne("")].tolist()
            )
        # IMPORTANTE:
        # No excluir por el histórico permanente del botón de cierre.
        # Los nombres de agrupador se reutilizan (p. ej. CAMIONETA EXP 4,
        # CAMIONETA DIARIOS 1), por lo que un cierre viejo no puede bloquear
        # una reutilización nueva del mismo nombre.
        #
        # La vigencia se resuelve abajo exclusivamente contra el último
        # control REAL del agrupador.

        # CIERRE AUTOMÁTICO REAL POR DESPACHOID.
        #
        # Dos evidencias válidas de cierre:
        # 1) DIGIP confirma todas las preparaciones del DespachoId como cerradas.
        # 2) La MISMA tabla que alimenta esta visual está al 100% para ese DespachoId.
        #
        # En ambos casos, las 8 h se cuentan desde el ÚLTIMO CONTROL REAL.
        despachos_id_expirados = set(
            _despachos_id_expirados_por_ultimo_control(contexto, horas=8)
        )

        if not control_base.empty and "DespachoId" in control_base.columns:
            _cb_cierre = control_base.copy()
            _cb_cierre["_DespachoIdKey"] = (
                _cb_cierre["DespachoId"]
                .astype("string")
                .fillna("")
                .str.strip()
                .str.replace(r"\.0+$", "", regex=True)
            )

            # El avance que ve el usuario se calcula con Categoria.
            # Por eso el 100% automático debe usar exactamente la misma base.
            if "Categoria" in _cb_cierre.columns:
                _cb_cierre["_Finalizado"] = (
                    _cb_cierre["Categoria"]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .str.upper()
                    .eq("FINALIZADO")
                )

                _estado_por_id = (
                    _cb_cierre.loc[_cb_cierre["_DespachoIdKey"].ne("")]
                    .groupby("_DespachoIdKey")["_Finalizado"]
                    .agg(["count", "sum"])
                )
                _ids_100 = set(
                    _estado_por_id.loc[
                        (_estado_por_id["count"] > 0)
                        & (_estado_por_id["sum"] == _estado_por_id["count"])
                    ].index.astype(str)
                )

                if _ids_100:
                    # Fecha/hora real de control. Primero usamos la que ya resolvió
                    # tabla_operativa; si faltara, recuperamos el máximo desde
                    # Filtrar Preparaciones por PreparacionId.
                    _cb_cierre["_FechaControlReal"] = pd.NaT
                    if "ControlFechaHora" in _cb_cierre.columns:
                        _cb_cierre["_FechaControlReal"] = pd.to_datetime(
                            _cb_cierre["ControlFechaHora"],
                            errors="coerce",
                            dayfirst=True,
                        )

                    if "Preparacion" in _cb_cierre.columns:
                        _control_raw = contexto.get("_control_historico_raw")
                        if isinstance(_control_raw, pd.DataFrame) and not _control_raw.empty:
                            _cr = _control_raw.copy()
                            _cr.columns = [
                                str(c).replace("\ufeff", "").strip()
                                for c in _cr.columns
                            ]
                            _fecha_col = next(
                                (
                                    c for c in [
                                        "ControlContenedorFechaHoraEstado",
                                        "ControlContenedorFechaHora",
                                        "FechaHoraControl",
                                    ]
                                    if c in _cr.columns
                                ),
                                None,
                            )
                            if "Id" in _cr.columns and _fecha_col:
                                _cr["_PrepKey"] = (
                                    _cr["Id"].astype("string").fillna("").str.strip()
                                    .str.replace(r"\.0+$", "", regex=True)
                                )
                                _cr["_FechaControlRaw"] = pd.to_datetime(
                                    _cr[_fecha_col],
                                    errors="coerce",
                                    dayfirst=True,
                                )
                                _max_control_prep = (
                                    _cr.loc[
                                        _cr["_PrepKey"].ne("")
                                        & _cr["_FechaControlRaw"].notna()
                                    ]
                                    .groupby("_PrepKey")["_FechaControlRaw"]
                                    .max()
                                )
                                _prep_visual = (
                                    _cb_cierre["Preparacion"]
                                    .astype("string")
                                    .fillna("")
                                    .str.strip()
                                    .str.replace(r"\.0+$", "", regex=True)
                                )
                                _fecha_fallback = _prep_visual.map(_max_control_prep)
                                _cb_cierre["_FechaControlReal"] = (
                                    _cb_cierre["_FechaControlReal"]
                                    .fillna(_fecha_fallback)
                                )

                    _ultimo_control_id = (
                        _cb_cierre.loc[
                            _cb_cierre["_DespachoIdKey"].isin(_ids_100)
                            & _cb_cierre["_FechaControlReal"].notna()
                        ]
                        .groupby("_DespachoIdKey")["_FechaControlReal"]
                        .max()
                    )

                    _limite_8h = pd.Timestamp.now() - pd.Timedelta(hours=8)
                    despachos_id_expirados.update(
                        _ultimo_control_id.loc[
                            _ultimo_control_id.le(_limite_8h)
                        ].index.astype(str).tolist()
                    )

            if despachos_id_expirados:
                _id_visual = _cb_cierre["_DespachoIdKey"]
                control_base = control_base.loc[
                    ~_id_visual.isin(despachos_id_expirados)
                ].copy()

        # Después aplicamos el universo de nombres activos.
        # Como las instancias vencidas ya fueron retiradas por ID, un nombre
        # reutilizado conserva solamente su DespachoId actual.
        if not control_base.empty and "Despacho" in control_base.columns:
            control_base = control_base.loc[
                control_base["Despacho"]
                .fillna("")
                .astype(str)
                .str.strip()
                .isin(despachos_activos)
            ].copy()

        if control_base.empty:
            st.info("No hay preparaciones operativas para mostrar.")
        else:
            # Normalización visual.
            for col in ["Despacho", "Cliente", "Preparacion", "Area", "Carro", "Categoria"]:
                if col not in control_base.columns:
                    control_base[col] = ""
                control_base[col] = (
                    control_base[col]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                )

            control_base["Preparacion"] = (
                control_base["Preparacion"]
                .str.replace(r"\\.0+$", "", regex=True)
            )
            control_base["Area"] = control_base["Area"].str.upper()

            # Mostrar Pedido en lugar del ID interno de Preparación.
            # El ID de Preparación se conserva internamente para todos los cruces.
            _pedidos_raw = contexto.get("_pedidos_raw")
            _mapa_pedido_por_preparacion = {}

            if isinstance(_pedidos_raw, pd.DataFrame) and not _pedidos_raw.empty:
                _p = _pedidos_raw.copy()
                _p.columns = [str(c).replace("\ufeff", "").strip() for c in _p.columns]

                _col_prep = next(
                    (c for c in ["Preparación Id", "Preparacion Id", "PreparacionId", "PreparaciónId"]
                     if c in _p.columns),
                    None,
                )
                _col_pedido = next(
                    (c for c in ["Código pedido", "Codigo pedido", "Código Pedido", "Codigo Pedido"]
                     if c in _p.columns),
                    None,
                )

                if _col_prep and _col_pedido:
                    _p["_PrepKey"] = (
                        _p[_col_prep].astype("string").fillna("").str.strip()
                        .str.replace(r"\.0+$", "", regex=True)
                    )

                    # Ej.: "0001  215889-3" -> "215889"
                    _pedido_txt = (
                        _p[_col_pedido].astype("string").fillna("").str.strip()
                    )
                    _p["_PedidoVisible"] = (
                        _pedido_txt
                        .str.extract(r"(\d+)(?:-\d+)?\s*$", expand=False)
                        .fillna("")
                    )

                    _mapa_pedido_por_preparacion = (
                        _p.loc[
                            _p["_PrepKey"].ne("") & _p["_PedidoVisible"].ne(""),
                            ["_PrepKey", "_PedidoVisible"],
                        ]
                        .drop_duplicates("_PrepKey", keep="last")
                        .set_index("_PrepKey")["_PedidoVisible"]
                        .to_dict()
                    )

            control_base["_PedidoVisible"] = (
                control_base["Preparacion"].map(_mapa_pedido_por_preparacion)
                .fillna("")
                .astype(str)
                .str.strip()
            )

            # Fallback seguro: si por algún motivo no encontramos el pedido,
            # mostramos la Preparación para no dejar una celda vacía.
            control_base.loc[
                control_base["_PedidoVisible"].eq(""),
                "_PedidoVisible",
            ] = control_base.loc[
                control_base["_PedidoVisible"].eq(""),
                "Preparacion",
            ]

            # La persona ya viene correctamente resuelta en ControlUsuario.
            # Para la hora usamos el histórico crudo como fallback SIN tocar el usuario.
            mapa_control_hora = _mapa_controladores_por_preparacion_area(contexto)

            def _hora_desde_mapa(fila):
                clave = (
                    str(fila.get("Preparacion", "")).strip(),
                    str(fila.get("Area", "")).strip().upper(),
                )
                dato = mapa_control_hora.get(clave)
                if not dato:
                    return ""

                # La función puede devolver dict (versión nueva) o texto
                # "Nombre · dd/mm HH:MM" (versión anterior).
                if isinstance(dato, dict):
                    fecha = dato.get("fecha_hora", pd.NaT)
                    fecha = pd.to_datetime(fecha, errors="coerce", dayfirst=True)
                    return fecha.strftime("%H:%M") if pd.notna(fecha) else ""

                texto = str(dato)
                coincidencias = re.findall(r"(?<!\d)([0-2]\d:[0-5]\d)(?!\d)", texto)
                return coincidencias[-1] if coincidencias else ""

            control_base["_HoraControlMapa"] = control_base.apply(
                _hora_desde_mapa, axis=1
            )


            # Filtro propio de esta tabla por Agrupador / Camioneta.
            opciones_control = sorted(
                x for x in control_base["Despacho"].unique().tolist() if x
            )
            col_filtro, col_cierre = st.columns([2.2, 1.0], vertical_alignment="bottom")
            with col_filtro:
                filtro_control = st.selectbox(
                    "Agrupador / Camioneta",
                    ["Todos"] + opciones_control,
                    key="control_filtro_agrupador_camioneta",
                )
            with col_cierre:
                ya_finalizado = (
                    filtro_control != "Todos"
                    and _agrupador_cerrado_visible(filtro_control)
                )
                cerrar_deshabilitado = filtro_control == "Todos" or ya_finalizado

                if st.button(
                    "✅ Agrupación Finalizada" if ya_finalizado else "🔒 Agrupación Finalizada",
                    key="control_cerrar_agrupador",
                    disabled=cerrar_deshabilitado,
                    width="stretch",
                    help=(
                        "Seleccioná un agrupador para cerrarlo."
                        if filtro_control == "Todos"
                        else (
                            "Este agrupador ya fue finalizado. Permanecerá visible "
                            "hasta completar 8 horas desde el cierre."
                            if ya_finalizado
                            else f"Finalizar manualmente {filtro_control}"
                        )
                    ),
                ):
                    _cerrar_agrupador_manual(filtro_control)
                    st.success(
                        f"Agrupación finalizada: {filtro_control}. "
                        "Seguirá visible durante 8 horas."
                    )
                    invalidar_cache_tareas()
                    construir_contexto_tareas.clear()
                    st.rerun()

            if filtro_control != "Todos":
                control_base = control_base.loc[
                    control_base["Despacho"].eq(filtro_control)
                ].copy()

            def _datos_carro(fila):
                categoria = str(fila.get("Categoria", "")).strip()
                area = str(fila.get("Area", "")).strip().upper() or "SIN ÁREA"
                carro = str(fila.get("Carro", "")).strip()
                unidades = int(round(float(pd.to_numeric(pd.Series([fila.get("Unidades", 0)]), errors="coerce").fillna(0).iloc[0])))
                siglas = {"IMPORTADO":"IMP", "NACIONAL":"NAC", "SANITARIOS":"SAN", "INTERPLANTA":"INT"}
                area_corta = siglas.get(area, area[:3] if area else "S/A")
                numero = re.sub(r"CARRO", "", carro, flags=re.IGNORECASE).strip()
                m = re.search(r"\d+", numero); numero = m.group(0) if m else ""
                usuario = _solo_nombre_controlador(fila.get("ControlUsuario", ""))
                picker = _solo_nombre_controlador(fila.get("Usuario", ""))
                fecha = fila.get("ControlFechaHora", pd.NaT)
                if not isinstance(fecha, pd.Timestamp):
                    fecha = pd.to_datetime(fecha, errors="coerce", dayfirst=True)
                hora = fecha.strftime("%H:%M") if pd.notna(fecha) else ""
                if not hora:
                    hora = str(fila.get("_HoraControlMapa", "") or "").strip()
                if categoria == "Finalizado":
                    return f"{area_corta} - {unidades} u.", "finalizado", usuario, hora, picker
                if numero and "SIN ASIGNAR" not in carro.upper() and carro.lower() != "nan":
                    return f"{numero} ({area_corta} - {unidades} u.)", "curso", "", "", picker
                return f"{area_corta} - {unidades} u.", "pendiente", "", "", picker

            control_base[["_TituloCarro","_EstadoCarro","_Controlador","_HoraControl","_Picker"]] = control_base.apply(
                lambda r: pd.Series(_datos_carro(r)), axis=1
            )
            st.caption(f"{control_base['Preparacion'].nunique()} preparación(es) visibles" + (f" · {filtro_control}" if filtro_control != "Todos" else ""))

            # KPIs del agrupador seleccionado.
            pedidos_kpi = int(control_base["Preparacion"].nunique())
            carros_kpi = int(len(control_base))
            unidades_kpi = int(
                pd.to_numeric(control_base["Unidades"], errors="coerce")
                .fillna(0).sum()
            )

            # La tabla operativa ya viene enriquecida con la volumetría del módulo.
            # Informe Tareas normaliza Volumen (mm³) -> VolumenM3 en models/tareas.py.
            volumen_kpi = float(
                pd.to_numeric(
                    control_base["VolumenM3"]
                    if "VolumenM3" in control_base.columns
                    else pd.Series(0.0, index=control_base.index),
                    errors="coerce",
                ).fillna(0.0).sum()
            )

            controlados_kpi = int(
                control_base["Categoria"].astype(str).eq("Finalizado").sum()
            )
            avance_kpi = (
                100.0 * controlados_kpi / carros_kpi
                if carros_kpi else 0.0
            )

            unidades_txt = f"{unidades_kpi:,}".replace(",", ".")
            volumen_txt = f"{volumen_kpi:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            # Mismo concepto visual que los KPI-card de los otros módulos:
            # tarjeta, título pequeño, valor grande y detalle inferior.
            st.markdown(
                """
                <style>
                .control-kpi-grid{
                    display:grid;
                    grid-template-columns:repeat(5,minmax(0,1fr));
                    gap:10px;
                    margin:6px 0 14px 0;
                }
                .control-kpi-card{
                    border:1px solid #303b49;
                    border-radius:12px;
                    background:#111821;
                    padding:12px 14px 10px 14px;
                    min-height:104px;
                    box-sizing:border-box;
                }
                .control-kpi-title{
                    font-size:.78rem;
                    font-weight:700;
                    color:#f1f5f9;
                    white-space:nowrap;
                }
                .control-kpi-value{
                    margin-top:7px;
                    font-size:1.72rem;
                    line-height:1.05;
                    font-weight:800;
                    color:#ffffff;
                }
                .control-kpi-detail{
                    margin-top:8px;
                    font-size:.72rem;
                    color:#9fb0c3;
                }
                .control-kpi-progress{
                    height:8px;
                    margin-top:8px;
                    background:#202c3b;
                    border-radius:20px;
                    overflow:hidden;
                }
                .control-kpi-progress > div{
                    height:100%;
                    background:#22c55e;
                    border-radius:20px;
                }
                @media (max-width: 1000px){
                    .control-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(
                f"""
                <div class="control-kpi-grid">
                  <div class="control-kpi-card">
                    <div class="control-kpi-title">📄 Pedidos</div>
                    <div class="control-kpi-value">{pedidos_kpi}</div>
                    <div class="control-kpi-detail">preparaciones visibles</div>
                  </div>
                  <div class="control-kpi-card">
                    <div class="control-kpi-title">🛒 Carros</div>
                    <div class="control-kpi-value">{carros_kpi}</div>
                    <div class="control-kpi-detail">carros del agrupador</div>
                  </div>
                  <div class="control-kpi-card">
                    <div class="control-kpi-title">📦 Unidades</div>
                    <div class="control-kpi-value">{unidades_txt}</div>
                    <div class="control-kpi-detail">unidades totales</div>
                  </div>
                  <div class="control-kpi-card">
                    <div class="control-kpi-title">🧊 Volumen</div>
                    <div class="control-kpi-value">{volumen_txt} m³</div>
                    <div class="control-kpi-detail">volumen total</div>
                  </div>
                  <div class="control-kpi-card">
                    <div class="control-kpi-title">📊 Avance control</div>
                    <div class="control-kpi-value">{avance_kpi:.0f}%</div>
                    <div class="control-kpi-progress">
                      <div style="width:{min(max(avance_kpi,0),100):.1f}%"></div>
                    </div>
                    <div class="control-kpi-detail">{controlados_kpi} / {carros_kpi} carros</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown(f"### 🚚 {filtro_control} — Carros en preparación" if filtro_control != "Todos" else "### 🚚 Todos los agrupadores — Carros en preparación")

            # Una fila visual = una PreparacionID/Pedido.
            # Orden visual: Cliente A-Z y, dentro de cada cliente, Preparación.
            # No se consolidan preparaciones distintas del mismo cliente.
            control_base = control_base.sort_values(
                ["Cliente", "Preparacion"],
                ascending=[True, True],
                kind="stable",
                na_position="last",
            ).reset_index(drop=True)

            filas_html = []
            claves_fila = ["Preparacion", "Cliente"]
            for (preparacion, cliente), grupo in control_base.groupby(claves_fila, sort=False, dropna=False):
                # Seguridad: si por cualquier motivo la tabla operativa trae repetida
                # exactamente la misma tarea, conservar una sola tarjeta.
                if "TareaId" in grupo.columns:
                    _tk = grupo["TareaId"].astype("string").fillna("").str.strip()
                    con_id = grupo.loc[_tk.ne("")].drop_duplicates("TareaId", keep="last")
                    sin_id = grupo.loc[_tk.eq("")]
                    grupo = pd.concat([con_id, sin_id], ignore_index=False).sort_index()

                tarjetas, total_unidades = [], 0
                for _, r in grupo.iterrows():
                    titulo, estado = html.escape(str(r["_TituloCarro"])), str(r["_EstadoCarro"])
                    usuario = html.escape(str(r["_Controlador"])) if str(r["_Controlador"]).strip() else ""
                    picker = html.escape(str(r["_Picker"])) if str(r["_Picker"]).strip() else ""
                    hora = html.escape(str(r["_HoraControl"])) if str(r["_HoraControl"]).strip() else ""
                    total_unidades += int(round(float(pd.to_numeric(pd.Series([r.get("Unidades",0)]), errors="coerce").fillna(0).iloc[0])))
                    detalle_picker = f'<div class="carro-picker">🛒 {picker}</div>' if picker else '<div class="carro-picker sin-dato">🛒 Sin dato</div>'
                    if estado == "finalizado":
                        detalle = detalle_picker
                        detalle += f'<div class="carro-control">👤 {usuario}</div>' if usuario else '<div class="carro-control sin-dato">👤 Sin dato</div>'
                        if hora: detalle += f'<div class="carro-hora">🕒 {hora}</div>'
                        tarjetas.append(f'<div class="carro-card finalizado"><div class="carro-titulo">✅ {titulo}</div>{detalle}</div>')
                    else:
                        icono = "🕒" if estado == "curso" else "⏳"
                        tarjetas.append(f'<div class="carro-card curso"><div class="carro-titulo">{icono} {titulo}</div>{detalle_picker}</div>')

                _pedido_grupo = (
                    grupo["_PedidoVisible"].iloc[0]
                    if "_PedidoVisible" in grupo.columns and not grupo.empty
                    else preparacion
                )
                prep_visible = html.escape(str(_pedido_grupo)) if str(_pedido_grupo).strip() else "—"
                cliente_visible = html.escape(str(cliente))
                filas_html.append(
                    '<div class="control-row">'
                    + f'<div class="control-prep">{prep_visible}</div>'
                    + f'<div class="control-cliente">{cliente_visible}</div>'
                    + f'<div class="control-carros">{"".join(tarjetas)}</div>'
                    + f'<div class="control-total">{len(grupo)}</div>'
                    + f'<div class="control-total">{total_unidades:,}</div></div>'
                )

            st.markdown("""
<style>
.control-grid{border:1px solid #30363d;border-radius:8px;overflow:hidden;margin:.35rem 0 .65rem}.control-head,.control-row{display:grid;grid-template-columns:9% 16% 1fr 7% 8%;align-items:stretch}.control-head{background:#1d222b;font-weight:700;color:#b9c0ca;font-size:.83rem}.control-head>div,.control-row>div{padding:8px 10px;border-right:1px solid #30363d;border-bottom:1px solid #30363d}.control-row:last-child>div{border-bottom:0}.control-head>div:last-child,.control-row>div:last-child{border-right:0}.control-prep,.control-cliente{font-weight:700;display:flex;align-items:center}.control-prep{color:#8fd0ff}.control-carros{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.control-total{display:flex;align-items:center;justify-content:center;font-weight:700}.carro-card{min-width:150px;padding:6px 10px;border-radius:7px;background:#151a21;border:1px solid #39414c;line-height:1.15}.carro-card.finalizado{border-color:#168c4b}.carro-titulo{font-weight:700;font-size:.84rem;white-space:nowrap}.carro-picker{font-size:.76rem;margin-top:4px;color:#c9d1d9}.carro-control{font-size:.76rem;margin-top:2px;color:#8fd0ff}.carro-hora{font-size:.74rem;color:#9aa4b2;margin-top:1px}.sin-dato{color:#8b949e}
</style><div class="control-grid"><div class="control-head"><div>Pedido</div><div>Cliente</div><div>Carros (sector - unidades)</div><div>Total carros</div><div>Total unidades</div></div>""" + "".join(filas_html) + "</div>", unsafe_allow_html=True)

            # Descarga agrupada: una fila por preparación, sin IDs visibles.
            detalle_descarga = control_base.copy()
            detalle_descarga["Agrupador"] = detalle_descarga["Despacho"].astype("string").fillna("").str.strip()
            detalle_descarga["ID Preparación"] = detalle_descarga["Preparacion"].astype("string").fillna("").str.strip()
            detalle_descarga["Sector"] = detalle_descarga["Area"].astype("string").fillna("").str.strip().str.upper()
            detalle_descarga["Unidades"] = pd.to_numeric(detalle_descarga["Unidades"], errors="coerce").fillna(0).round().astype(int)
            detalle_descarga["Controló"] = detalle_descarga["_Controlador"].map(_solo_nombre_controlador)
            detalle_descarga["Hora control"] = detalle_descarga["_HoraControl"].astype("string").fillna("").str.strip()

            abreviar_sector = {
                "IMPORTADO": "IMP", "NACIONAL": "NAC",
                "SANITARIOS": "SAN", "SANITARIO": "SAN",
                "INTERPLANTA": "INT",
            }

            def _detalle_carro(fila):
                sector = abreviar_sector.get(
                    str(fila["Sector"]).strip().upper(),
                    str(fila["Sector"]).strip().upper()[:3]
                )
                usuario = str(fila["Controló"]).strip()
                hora = str(fila["Hora control"]).strip()

                # Replicar en Excel la misma lectura visual de las tarjetas.
                controlado = bool(usuario)
                if controlado:
                    texto = f"✅ {sector} - {int(fila['Unidades'])} u. · 👤 {usuario}"
                    if hora:
                        texto += f" · 🕒 {hora}"
                else:
                    texto = f"🕒 {sector} - {int(fila['Unidades'])} u. · —"

                return texto

            detalle_descarga["_DetalleCarro"] = detalle_descarga.apply(_detalle_carro, axis=1)

            tabla_descarga = (
                detalle_descarga
                .groupby(["Agrupador", "ID Preparación", "Cliente"], as_index=False, sort=False)
                .agg({
                    "_DetalleCarro": lambda x: " - ".join(str(v).strip() for v in x if str(v).strip()),
                    "Unidades": "sum",
                })
                .rename(columns={"_DetalleCarro": "Carros / Control", "Unidades": "Total unidades"})
            )

            # ID Preparación sólo agrupa; no se muestra.
            tabla_descarga = tabla_descarga[
                ["Agrupador", "Cliente", "Carros / Control", "Total unidades"]
            ].copy()


            salida_excel = BytesIO()
            with pd.ExcelWriter(salida_excel, engine="openpyxl") as writer:
                tabla_descarga.to_excel(writer, index=False, sheet_name="Carros")
                ws = writer.book["Carros"]
                ws.freeze_panes = "A2"
                ws.auto_filter.ref = ws.dimensions

                from openpyxl.styles import Alignment, Font, PatternFill

                encabezado_fill = PatternFill("solid", fgColor="1F4E78")
                encabezado_font = Font(color="FFFFFF", bold=True)
                for celda in ws[1]:
                    celda.fill = encabezado_fill
                    celda.font = encabezado_font
                    celda.alignment = Alignment(horizontal="center", vertical="center")

                anchos = {"A": 28, "B": 42, "C": 95, "D": 16}
                for columna, ancho in anchos.items():
                    ws.column_dimensions[columna].width = ancho

                for fila in ws.iter_rows(min_row=2):
                    for celda in fila:
                        celda.alignment = Alignment(vertical="top", wrap_text=True)

            salida_excel.seek(0)
            nombre_filtro = (
                "TODOS" if filtro_control == "Todos"
                else re.sub(r"[^A-Za-z0-9_-]+", "_", filtro_control.strip())
            )
            st.download_button(
                "⬇️ Descargar carros",
                data=salida_excel.getvalue(),
                file_name=f"carros_control_{nombre_filtro}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="descargar_carros_control",
                width="stretch",
            )


def _render_tabla(
    contexto: dict[str, object],
    *,
    perfil: str,
) -> None:
    tabla_base = contexto["tabla_operativa"].copy()

    # INTERPLANTA queda excluido del módulo operativo.
    if not tabla_base.empty and "Despacho" in tabla_base.columns:
        _despacho_modulo = (
            tabla_base["Despacho"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )
        tabla_base = tabla_base.loc[
            ~_despacho_modulo.eq("INTERPLANTA")
        ].copy()

    tabla = preparar_tabla_operativa_visual(tabla_base)

    # Mostrar explícitamente la división operativa antes de que exista el carro.
    # El modelo mantiene el orden por Preparación y Área, de modo que las tareas
    # de un mismo cliente/preparación quedan juntas sin ordenar por Cliente.
    if len(tabla) == len(tabla_base):
        tabla = tabla.reset_index(drop=True)
        tabla_base = tabla_base.reset_index(drop=True)

        if "Preparacion" in tabla_base.columns:
            tabla.insert(1, "Preparación", tabla_base["Preparacion"])

        if "Area" in tabla_base.columns:
            area_visible = (
                tabla_base["Area"]
                .astype("string")
                .fillna("")
                .str.strip()
                .str.upper()
            )
            tabla.insert(3 if "Preparación" in tabla.columns else 2, "Área", area_visible)

        # Si todavía no fue tomada, el carro no existe. Lo dejamos explícito
        # para diferenciar una tarea pendiente sectorizada de un dato faltante.
        if "Carro" in tabla.columns and "Categoria" in tabla_base.columns:
            pendiente = tabla_base["Categoria"].astype(str).eq("Pendiente")
            carro_vacio = tabla["Carro"].astype("string").fillna("").str.strip().eq("")
            tabla.loc[pendiente & carro_vacio, "Carro"] = "⏳ Sin asignar"

    st.markdown("### 📋 Operación en curso")

    # Filtro operativo por despacho. Solo afecta la tabla visible.
    columna_despacho = None
    if "Despacho" in tabla.columns:
        columna_despacho = "Despacho"
    elif "DespachoDescripcion" in tabla.columns:
        columna_despacho = "DespachoDescripcion"

    despacho_seleccionado = "Todos"
    if columna_despacho is not None:
        opciones_despacho = (
            tabla[columna_despacho]
            .fillna("")
            .astype(str)
            .str.strip()
        )
        opciones_despacho = sorted(
            valor for valor in opciones_despacho.unique().tolist() if valor
        )

        despacho_seleccionado = st.selectbox(
            "Filtrar por despacho",
            ["Todos"] + opciones_despacho,
            key="operacion_filtro_despacho",
        )

        if despacho_seleccionado != "Todos":
            tabla = tabla.loc[
                tabla[columna_despacho]
                .astype("string")
                .fillna("")
                .str.strip()
                .eq(despacho_seleccionado)
            ].copy()

            # Aplicar el mismo filtro sobre la tabla operativa original.
            # La inteligencia necesita columnas técnicas como Preparacion,
            # Area y Categoria que la tabla visual renombra/oculta.
            if "Despacho" in tabla_base.columns:
                tabla_base = tabla_base.loc[
                    tabla_base["Despacho"]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .eq(despacho_seleccionado)
                ].copy()
            elif "DespachoDescripcion" in tabla_base.columns:
                tabla_base = tabla_base.loc[
                    tabla_base["DespachoDescripcion"]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .eq(despacho_seleccionado)
                ].copy()

    if despacho_seleccionado == "Todos":
        st.caption(f"{len(tabla)} registros activos")
    else:
        st.caption(f"{len(tabla)} registros · Despacho: {despacho_seleccionado}")

    if tabla.empty:
        st.info("No hay tareas operativas para mostrar con el despacho seleccionado.")
        return

    # ======================================================
    # INTELIGENCIA OPERATIVA: TAREAS QUE CIERRAN PREPARACIONES
    # ======================================================
    # IMPORTANTE: usar tabla_base, no la tabla visual.
    # preparar_tabla_operativa_visual renombra Preparacion -> Preparación
    # y Area -> Área, por eso la versión anterior producía KeyError.
    intel = tabla_base.copy()
    intel["_Prep"] = intel["Preparacion"].astype("string").fillna("").str.strip()
    intel["_Area"] = intel["Area"].astype("string").fillna("").str.strip().str.upper()
    intel["_Categoria"] = intel["Categoria"].astype(str).str.strip()
    intel["_Resuelta"] = intel["_Categoria"].eq("Finalizado")

    carro_intel = (
        intel["Carro"].astype("string").fillna("").str.strip()
        if "Carro" in intel.columns
        else pd.Series("", index=intel.index, dtype="object")
    )
    sin_carro = (
        carro_intel.eq("")
        | carro_intel.str.contains("SIN ASIGNAR", case=False, na=False)
    )

    # Remanente real: solo tareas que todavía no fueron tomadas.
    intel["_Pendiente"] = (
        ~intel["_Resuelta"]
        & ~intel["_Categoria"].eq("En Curso")
        & sin_carro
    )

    for c in ["Unidades", "SKUs", "VolumenM3", "PesoKg"]:
        if c not in intel.columns:
            intel[c] = 0.0
        intel[c] = pd.to_numeric(intel[c], errors="coerce").fillna(0.0)

    # Estado real de cada preparación según sus áreas.
    prep_estado = (
        intel.groupby("_Prep", as_index=False)
        .agg(AreasTotales=("_Area", "nunique"))
    )
    areas_pend = (
        intel.loc[intel["_Pendiente"]]
        .groupby("_Prep")["_Area"].nunique()
        .rename("AreasPendientes")
    )
    areas_res = (
        intel.loc[intel["_Resuelta"]]
        .groupby("_Prep")["_Area"].nunique()
        .rename("AreasResueltas")
    )
    prep_estado = prep_estado.merge(areas_pend, on="_Prep", how="left").merge(
        areas_res, on="_Prep", how="left"
    )
    prep_estado[["AreasPendientes", "AreasResueltas"]] = (
        prep_estado[["AreasPendientes", "AreasResueltas"]].fillna(0).astype(int)
    )

    pendientes_i = intel.loc[intel["_Pendiente"]].merge(
        prep_estado, on="_Prep", how="left"
    )

    if not pendientes_i.empty:
        agg = {
            "Cliente": "first",
            "Despacho": "first",
            "Unidades": "max",
            "SKUs": "max",
            "VolumenM3": "max",
            "PesoKg": "max",
            "AreasTotales": "max",
            "AreasResueltas": "max",
            "AreasPendientes": "max",
            "Categoria": "first",
        }
        if "Vehiculo" in pendientes_i.columns:
            agg["Vehiculo"] = "first"

        prioridad = (
            pendientes_i.groupby(["_Prep", "_Area"], as_index=False).agg(agg)
        )

        # 45% cierre inmediato + 25% cercanía al cierre +
        # 20% quick win físico + 10% continuidad de una tarea ya tomada.
        prioridad["CierraPreparacion"] = prioridad["AreasPendientes"].eq(1)
        prioridad["CercaniaCierre"] = (
            1.0 - (
                (prioridad["AreasPendientes"] - 1).clip(lower=0)
                / prioridad["AreasTotales"].clip(lower=1)
            )
        ).clip(0, 1)

        vol = prioridad["VolumenM3"].clip(lower=0)
        uni = prioridad["Unidades"].clip(lower=0)
        max_vol = float(vol.max()) if len(vol) else 0.0
        max_uni = float(uni.max()) if len(uni) else 0.0
        facilidad_vol = 1 - (vol / max_vol) if max_vol > 0 else 1.0
        facilidad_uni = 1 - (uni / max_uni) if max_uni > 0 else 1.0
        prioridad["QuickWin"] = (facilidad_vol * 0.6 + facilidad_uni * 0.4).clip(0, 1)
        prioridad["ScorePrioridad"] = (
            prioridad["CierraPreparacion"].astype(float) * 50
            + prioridad["CercaniaCierre"] * 30
            + prioridad["QuickWin"] * 20
        ).clip(0, 100).round().astype(int)

        prioridad["Accion"] = "🟡 SIGUIENTE"
        prioridad.loc[prioridad["ScorePrioridad"].lt(50), "Accion"] = "⚪ COLA"
        prioridad.loc[prioridad["ScorePrioridad"].ge(70), "Accion"] = "🟠 ALTA"
        prioridad.loc[prioridad["CierraPreparacion"], "Accion"] = "🔥 CERRAR YA"

        prioridad = prioridad.sort_values(
            ["CierraPreparacion", "ScorePrioridad", "AreasPendientes", "VolumenM3"],
            ascending=[False, False, True, True],
        ).reset_index(drop=True)

        impacto_area = (
            prioridad.groupby("_Area", as_index=False)
            .agg(
                Tareas=("_Prep", "nunique"),
                CierraAhora=("CierraPreparacion", "sum"),
                ScoreProm=("ScorePrioridad", "mean"),
                VolPend=("VolumenM3", "sum"),
            )
            .sort_values(
                ["CierraAhora", "ScoreProm", "Tareas"],
                ascending=[False, False, False],
            )
        )

        st.markdown("#### 🎯 Tareas que cierran Preparaciones")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Preparaciones por cerrar", int(prioridad["_Prep"].nunique()))
        k2.metric(
            "Cerrables ahora",
            int(prioridad.loc[prioridad["CierraPreparacion"], "_Prep"].nunique()),
        )
        k3.metric("Tareas / áreas pendientes", int(len(prioridad)))
        k4.metric("Volumen pendiente", f"{prioridad['VolumenM3'].sum():.2f} m³")

        if not impacto_area.empty:
            top = impacto_area.iloc[0]
            area_top = str(top["_Area"]).strip()
            cierres_top = int(top["CierraAhora"])
            tareas_top = int(top["Tareas"])
            if cierres_top:
                st.success(
                    f"**Prioridad ahora: {area_top}.** "
                    f"Atacar {tareas_top} tarea(s) de esta área permite cerrar "
                    f"**{cierres_top} preparación(es) inmediatamente**."
                )
            else:
                st.info(
                    f"**Prioridad ahora: {area_top}.** "
                    "Es el área con mejor combinación entre cercanía al cierre, "
                    "esfuerzo restante y continuidad operativa."
                )

        c1, c2 = st.columns([1.0, 2.0], vertical_alignment="top")
        with c1:
            st.markdown("**Orden recomendado por área**")
            ta = impacto_area.copy()
            ta["Score"] = ta["ScoreProm"].round().astype(int)
            ta["Vol. pend."] = ta["VolPend"].round(2)
            ta = ta.rename(columns={"_Area": "Área", "CierraAhora": "Cierra prep."})
            st.dataframe(
                ta[["Área", "Tareas", "Cierra prep.", "Score", "Vol. pend."]],
                hide_index=True, width="stretch", height=275,
            )

        with c2:
            st.markdown("**Qué conviene sacar primero**")
            tm = prioridad.copy()
            tm["Preparación"] = tm["_Prep"]
            tm["Área"] = tm["_Area"]
            tm["Áreas listas"] = tm["AreasResueltas"].astype(int)
            tm["Faltan"] = tm["AreasPendientes"].astype(int)
            tm["Vol. m³"] = tm["VolumenM3"].round(3)
            tm["Prioridad"] = tm["ScorePrioridad"]
            cols = [
                "Accion", "Prioridad", "Preparación", "Cliente", "Área",
                "Áreas listas", "Faltan", "Unidades", "SKUs", "Vol. m³",
            ]
            # Sugerencia NUESTRA por volumetría; no usa Vehiculo de DIGIP.
            tm["Vehículo sugerido"] = tm["VolumenM3"].apply(
                sugerir_equipamiento_operativo
            )
            cols.insert(5, "Vehículo sugerido")
            st.dataframe(
                tm[cols].head(15), hide_index=True, width="stretch", height=275,
            )

        st.caption(
            "Prioridad: cierre inmediato de preparación → cercanía al cierre → "
            "quick win por volumen/unidades. Las tareas ya tomadas salen de esta propuesta."
        )
        st.divider()

    # ======================================================
    # ORGANIZACIÓN FÍSICA PRE POR DESPACHO / CAMIONETA
    # ======================================================
    organizacion_pre = contexto.get("organizacion_pre", pd.DataFrame()).copy()

    # Respetar el mismo filtro de despacho seleccionado en la pantalla.
    if (
        not organizacion_pre.empty
        and despacho_seleccionado != "Todos"
        and "Despacho / Camioneta" in organizacion_pre.columns
    ):
        organizacion_pre = organizacion_pre.loc[
            organizacion_pre["Despacho / Camioneta"]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq(despacho_seleccionado)
        ].copy()

    st.markdown("#### 📍 Organización de posiciones PRE")

    if organizacion_pre.empty:
        st.info("No hay Despachos/Camionetas activos para asignar a PRE.")
    else:
        # Completar visualmente las cuatro posiciones cuando se mira el tablero general.
        if despacho_seleccionado == "Todos":
            usados = set(organizacion_pre["PRE"].astype(str))
            libres = []
            for numero in range(1, 5):
                pre = f"PRE {numero}"
                if pre not in usados:
                    libres.append({
                        "PRE": pre,
                        "Despacho / Camioneta": "—",
                        "Estado": "⚪ LIBRE",
                        "Preparaciones": 0,
                        "Áreas pendientes": 0,
                        "Áreas controladas": 0,
                        "Vol. pendiente m³": 0.0,
                        "Área sugerida": "—",
                        "Equipamiento sugerido": "—",
                    })
            if libres:
                organizacion_pre = pd.concat(
                    [organizacion_pre, pd.DataFrame(libres)],
                    ignore_index=True,
                )

        st.dataframe(
            organizacion_pre,
            hide_index=True,
            width="stretch",
            column_config={
                "PRE": st.column_config.TextColumn("PRE", width="small"),
                "Despacho / Camioneta": st.column_config.TextColumn(
                    "Despacho / Camioneta", width="medium"
                ),
                "Área sugerida": st.column_config.TextColumn(
                    "Área sugerida", width="medium"
                ),
                "Equipamiento sugerido": st.column_config.TextColumn(
                    "Equipamiento sugerido", width="large"
                ),
                "Vol. pendiente m³": st.column_config.NumberColumn(
                    "Vol. pendiente m³", format="%.2f"
                ),
            },
        )

        sin_pre = organizacion_pre[
            organizacion_pre["PRE"].astype(str).str.contains("SIN PRE", na=False)
        ]
        if not sin_pre.empty:
            st.warning(
                f"⚠️ Hay {len(sin_pre)} Despacho(s)/Camioneta(s) activos sin posición PRE disponible."
            )

    st.caption(
        "PRE organiza físicamente el Despacho/Camioneta. "
        "El equipamiento es una sugerencia propia calculada por volumen y no depende de DIGIP."
    )
    st.divider()

    st.dataframe(
        tabla.style.format({"Unidades": "{:.0f}", "SKUs": "{:.0f}"}).apply(
            resaltar_carro, axis=1
        ),
        width="stretch",
        hide_index=True,
        height={"pc": 560, "monitor": 620, "tv": 790}[perfil],
    )


@st.fragment(run_every="5m")
def _render_fragmento_operativo(perfil: str) -> None:
    carga = cargar_fuentes_tareas()
    fuentes = carga["fuentes"]

    faltantes = [
        nombre
        for nombre, clave in [
            ("Informe Tareas", "tareas"),
            ("Pedidos DIGIP", "pedidos"),
            ("Detalle Pendientes", "detalle"),
            ("Maestro Clientes", "clientes"),
            ("Maestro Artículo", "articulos"),
            ("Maestro Volumetría", "volumetria"),
        ]
        if fuentes[clave] is None or fuentes[clave].empty
    ]

    if faltantes:
        st.error("No se puede construir el tablero. Faltan: " + ", ".join(faltantes))
        return

    if carga["actualizacion_completa"]:
        st.caption(
            f"✅ Datos actualizados: {carga['hora_actualizacion']} · "
            "actualización automática cada 5 minutos"
        )
    else:
        st.caption(
            f"⚠️ Último intento: {carga['hora_actualizacion']} · "
            "se conserva información válida anterior"
        )

    if carga["mensajes"]:
        with st.expander("⚠️ Detalle de actualización", expanded=False):
            for mensaje in carga["mensajes"]:
                st.caption(f"• {mensaje}")

    with medir_tiempo("Construir contexto operativo"):
        contexto = construir_contexto_tareas(
            fuentes["tareas"],
            fuentes["pedidos"],
            fuentes["detalle"],
            fuentes["clientes"],
            fuentes["articulos"],
            fuentes["volumetria"],
            fuentes.get("control_historico"),
            fuentes.get("preparaciones_historico"),
        )
        # Fuentes crudas necesarias para asociar cada control al carro/sector correcto.
        # Fuente real de Filtrar Preparaciones: contiene fecha/hora de control.
        # Antes se buscaba "control_historico", clave que no corresponde a la
        # fuente cargada por carga.py; por eso la limpieza automática de 8 h
        # no podía determinar el último control en Streamlit.
        # Para hora/usuario de control priorizamos la ventana reciente DIRECTA.
        # Evita que una consolidación/deduplicación histórica elimine el registro
        # que contiene ControlContenedorFechaHoraEstado.
        _control_reciente = fuentes.get("preparaciones_recientes")
        if isinstance(_control_reciente, pd.DataFrame) and not _control_reciente.empty:
            contexto["_control_historico_raw"] = _control_reciente
        else:
            contexto["_control_historico_raw"] = fuentes.get("preparaciones_historico")

        contexto["_tareas_raw"] = fuentes.get("tareas")
        contexto["_pedidos_raw"] = fuentes.get("pedidos")

    mostrar_info_dataframe("Tabla pedidos", contexto["tabla_pedidos"])
    mostrar_info_dataframe("Tabla tareas", contexto["tabla_tareas"])
    mostrar_info_dataframe("Tabla operativa", contexto["tabla_operativa"])

    _render_kpis(contexto)
    _render_indicadores(contexto, perfil=perfil)
    _render_tabla(contexto, perfil=perfil)

    # ======================================================
    # DATOS CENCOSUD PARA APP DE ETIQUETAS
    # ======================================================
    pedidos_cencosud = fuentes["pedidos"].copy()

    def _buscar_columna(df: pd.DataFrame, candidatos: list[str]) -> str | None:
        mapa = {str(c).strip().lower(): c for c in df.columns}
        for candidato in candidatos:
            col = mapa.get(candidato.strip().lower())
            if col is not None:
                return col
        return None

    col_pedido = _buscar_columna(
        pedidos_cencosud,
        ["Código pedido", "Codigo pedido", "Código Pedido", "Codigo Pedido",
         "Número", "Numero", "Pedido", "Nro Pedido", "Nro. Pedido"]
    )
    col_observacion = _buscar_columna(
        pedidos_cencosud, ["Observación", "Observacion", "Observaciones"]
    )
    col_despacho = _buscar_columna(
        pedidos_cencosud, ["Despacho", "Agrupador", "Agrupador / Camioneta"]
    )

    with st.container(border=True):
        st.markdown("#### 🏷️ Datos CENCOSUD para etiquetas")

        if not all([col_pedido, col_observacion, col_despacho]):
            st.warning(
                "No se encontraron en Pedidos DIGIP las columnas necesarias: "
                "Pedido, Observación y Despacho."
            )
        else:
            despacho_txt = (
                pedidos_cencosud[col_despacho]
                .astype("string")
                .fillna("")
                .str.strip()
            )

            # Los agrupadores CENCOSUD se identifican operativamente como EASY + fecha.
            tabla_cencosud = pedidos_cencosud.loc[
                despacho_txt.str.match(r"(?i)^EASY(?:\s|$)")
            , [col_pedido, col_observacion, col_despacho]].copy()

            if tabla_cencosud.empty:
                st.info("No hay pedidos CENCOSUD / EASY disponibles en Pedidos DIGIP.")
            else:
                # Pedido: quitar retransmisiones/sufijos de DIGIP (-1, -2, etc.).
                tabla_cencosud["Pedido"] = (
                    tabla_cencosud[col_pedido]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    # El crudo llega como, por ejemplo, "0001  215188-1".
                    # Nos quedamos con el número real del pedido y quitamos -1/-2.
                    .str.extract(r"(\d+(?:-\d+)?)\s*$", expand=False)
                    .fillna("")
                    .str.replace(r"-\d+$", "", regex=True)
                    .str.replace(r"\.0+$", "", regex=True)
                )

                tabla_cencosud["Orden de Compra"] = (
                    tabla_cencosud[col_observacion]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                )

                tabla_cencosud["Fecha de entrega"] = (
                    tabla_cencosud[col_despacho]
                    .astype("string")
                    .fillna("")
                    .str.strip()
                    .str.replace(r"(?i)^EASY\s*", "", regex=True)
                    .str.strip(" -")
                )

                # Mostrar únicamente entregas de hoy en adelante.
                # La fecha viene del agrupador EASY en formato DD-MM.
                hoy = pd.Timestamp.now().normalize()

                def _fecha_entrega_futura(valor: object) -> pd.Timestamp:
                    texto = str(valor).strip()
                    match = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})", texto)
                    if not match:
                        return pd.NaT

                    dia, mes = map(int, match.groups())
                    try:
                        fecha = pd.Timestamp(year=hoy.year, month=mes, day=dia)
                    except ValueError:
                        return pd.NaT

                    # Cambio de año: estando en los últimos meses del año,
                    # una fecha de enero/febrero corresponde al año siguiente.
                    if fecha < hoy and (hoy - fecha).days > 180:
                        try:
                            fecha = pd.Timestamp(year=hoy.year + 1, month=mes, day=dia)
                        except ValueError:
                            return pd.NaT

                    return fecha

                tabla_cencosud["_FechaEntregaOrden"] = (
                    tabla_cencosud["Fecha de entrega"].map(_fecha_entrega_futura)
                )

                tabla_cencosud = (
                    tabla_cencosud
                    .loc[
                        tabla_cencosud["Pedido"].ne("")
                        & tabla_cencosud["_FechaEntregaOrden"].notna()
                        & tabla_cencosud["_FechaEntregaOrden"].ge(hoy)
                    ]
                    .sort_values(["_FechaEntregaOrden", "Pedido"], kind="stable")
                    [["Pedido", "Orden de Compra", "Fecha de entrega"]]
                    .drop_duplicates()
                    .reset_index(drop=True)
                )

                # ------------------------------------------------------
                # CARROS ASOCIADOS AL PEDIDO (Informe Tareas)
                # ------------------------------------------------------
                # Usamos la tabla normalizada del contexto porque allí Informe
                # Tareas ya está cruzado con Pedidos DIGIP y cada preparación
                # conoce su Pedido. Esto evita depender de que el CSV crudo de
                # tareas traiga directamente una columna Pedido.
                tareas_cencosud = contexto["tabla_operativa"].copy()

                def _normalizar_pedido(valor: object) -> str:
                    if pd.isna(valor):
                        return ""
                    texto = str(valor).strip()
                    if not texto:
                        return ""
                    encontrado = re.search(r"(\d+(?:-\d+)?)\s*$", texto)
                    if encontrado:
                        texto = encontrado.group(1)
                    texto = re.sub(r"-\d+$", "", texto)
                    texto = re.sub(r"\.0+$", "", texto)
                    return texto.strip()

                # ------------------------------------------------------
                # DETALLE OPERATIVO PARA ETIQUETAS
                # ------------------------------------------------------
                # Carros = número + sector + unidades.
                # Si ya pasó a contenedor numérico, mostramos CONTROLADO.
                tabla_cencosud["Carros"] = ""
                tabla_cencosud["Estado"] = "SIN INICIAR"

                if (
                    not tareas_cencosud.empty
                    and "Pedido" in tareas_cencosud.columns
                    and "Carro" in tareas_cencosud.columns
                ):
                    columnas_detalle = ["Pedido", "Carro"]
                    for col in ["Area", "Unidades", "Categoria", "FechaHora"]:
                        if col in tareas_cencosud.columns:
                            columnas_detalle.append(col)

                    tareas_detalle = tareas_cencosud[columnas_detalle].copy()
                    tareas_detalle["_PedidoKey"] = tareas_detalle["Pedido"].map(
                        _normalizar_pedido
                    )

                    for col in ["Area", "Categoria"]:
                        if col not in tareas_detalle.columns:
                            tareas_detalle[col] = ""
                    if "Unidades" not in tareas_detalle.columns:
                        tareas_detalle["Unidades"] = 0

                    tareas_detalle["_Carro"] = (
                        tareas_detalle["Carro"].astype("string").fillna("")
                        .str.replace(r"^[^A-Za-z0-9]*", "", regex=True)
                        .str.strip().str.upper()
                    )
                    tareas_detalle["_Area"] = (
                        tareas_detalle["Area"].astype("string").fillna("")
                        .str.strip().str.upper()
                    )
                    tareas_detalle["_Unidades"] = (
                        pd.to_numeric(tareas_detalle["Unidades"], errors="coerce")
                        .fillna(0).round().astype(int)
                    )

                    siglas_area = {
                        "IMPORTADO": "IMP",
                        "NACIONAL": "NAC",
                        "SANITARIOS": "SAN",
                        "INTERPLANTA": "INT",
                    }
                    tareas_detalle["_Sector"] = tareas_detalle["_Area"].map(
                        lambda x: siglas_area.get(x, x[:3] if x else "S/A")
                    )

                    if "FechaHora" in tareas_detalle.columns:
                        tareas_detalle["FechaHora"] = pd.to_datetime(
                            tareas_detalle["FechaHora"], errors="coerce"
                        )
                        tareas_detalle = tareas_detalle.sort_values("FechaHora")

                    def _detalle_cencosud(fila):
                        carro = str(fila["_Carro"]).strip().upper()
                        detalle = f'{fila["_Sector"]} - {int(fila["_Unidades"])} u.'

                        match_carro = re.match(r"^CARRO\s*(\d+)", carro)
                        if match_carro:
                            return f"🚧 {match_carro.group(1)} ({detalle})"

                        if re.fullmatch(r"\d+", carro):
                            return f"✅ CONTROLADO ({detalle})"

                        return f"⏳ SIN ASIGNAR ({detalle})"

                    tareas_detalle["_Detalle"] = tareas_detalle.apply(
                        _detalle_cencosud, axis=1
                    )

                    tareas_detalle["_Clave"] = (
                        tareas_detalle["_PedidoKey"] + "|"
                        + tareas_detalle["_Carro"] + "|"
                        + tareas_detalle["_Sector"]
                    )
                    tareas_detalle = tareas_detalle.drop_duplicates(
                        subset=["_Clave"], keep="last"
                    )

                    detalles_por_pedido = (
                        tareas_detalle.loc[tareas_detalle["_PedidoKey"].ne("")]
                        .groupby("_PedidoKey")["_Detalle"]
                        .agg(lambda s: " · ".join(dict.fromkeys(s.astype(str))))
                    )

                    def _estado_pedido_cencosud(grupo):
                        carros = grupo["_Carro"].astype(str)
                        tiene_carro = carros.str.match(r"^CARRO\s*\d+", na=False).any()
                        tiene_pendiente = (
                            carros.eq("")
                            | carros.str.contains("SIN ASIGNAR", case=False, na=False)
                        ).any()
                        tiene_controlado = carros.str.fullmatch(r"\d+", na=False).any()

                        if tiene_carro:
                            return "EN PREPARACIÓN"
                        if tiene_pendiente:
                            return "SIN INICIAR"
                        if tiene_controlado:
                            return "CONTROLADO"
                        return "SIN INICIAR"

                    # Calcular el estado sin DataFrameGroupBy.apply.
                    # Evita el FutureWarning de pandas manteniendo la misma prioridad.
                    _estado_base = tareas_detalle.loc[
                        tareas_detalle["_PedidoKey"].ne(""),
                        ["_PedidoKey", "_Carro"],
                    ].copy()

                    _carros_estado = _estado_base["_Carro"].astype("string").fillna("")
                    _estado_base["_TieneCarro"] = _carros_estado.str.match(
                        r"^CARRO\s*\d+", na=False
                    )
                    _estado_base["_TienePendiente"] = (
                        _carros_estado.eq("")
                        | _carros_estado.str.contains("SIN ASIGNAR", case=False, na=False)
                    )
                    _estado_base["_TieneControlado"] = _carros_estado.str.fullmatch(
                        r"\d+", na=False
                    )

                    _estado_resumen = (
                        _estado_base.groupby("_PedidoKey", sort=False)[
                            ["_TieneCarro", "_TienePendiente", "_TieneControlado"]
                        ]
                        .any()
                    )

                    estado_por_pedido = pd.Series(
                        "SIN INICIAR", index=_estado_resumen.index, dtype="object"
                    )
                    estado_por_pedido.loc[_estado_resumen["_TieneControlado"]] = "CONTROLADO"
                    estado_por_pedido.loc[_estado_resumen["_TienePendiente"]] = "SIN INICIAR"
                    estado_por_pedido.loc[_estado_resumen["_TieneCarro"]] = "EN PREPARACIÓN"

                    pedido_key_tabla = tabla_cencosud["Pedido"].map(_normalizar_pedido)
                    tabla_cencosud["Carros"] = (
                        pedido_key_tabla.map(detalles_por_pedido).fillna("")
                    )
                    tabla_cencosud["Estado"] = (
                        pedido_key_tabla.map(estado_por_pedido).fillna("SIN INICIAR")
                    )

                st.dataframe(
                    tabla_cencosud,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Pedido": st.column_config.TextColumn("Pedido", width="medium"),
                        "Orden de Compra": st.column_config.TextColumn(
                            "Orden de Compra", width="medium"
                        ),
                        "Fecha de entrega": st.column_config.TextColumn(
                            "Fecha de entrega", width="small"
                        ),
                        "Carros": st.column_config.TextColumn(
                            "Carros", width="large"
                        ),
                        "Estado": st.column_config.TextColumn(
                            "Estado", width="small"
                        ),
                    },
                )

                salida_cencosud = BytesIO()
                with pd.ExcelWriter(salida_cencosud, engine="openpyxl") as writer:
                    tabla_cencosud.to_excel(
                        writer, index=False, sheet_name="CENCOSUD"
                    )
                    ws = writer.book["CENCOSUD"]
                    ws.freeze_panes = "A2"
                    ws.auto_filter.ref = ws.dimensions

                    from openpyxl.styles import Alignment, Font, PatternFill

                    encabezado_fill = PatternFill("solid", fgColor="1F4E78")
                    encabezado_font = Font(color="FFFFFF", bold=True)
                    for celda in ws[1]:
                        celda.fill = encabezado_fill
                        celda.font = encabezado_font
                        celda.alignment = Alignment(
                            horizontal="center", vertical="center"
                        )

                    for columna, ancho in {"A": 20, "B": 28, "C": 20, "D": 52, "E": 20}.items():
                        ws.column_dimensions[columna].width = ancho

                    for fila in ws.iter_rows(min_row=2):
                        for celda in fila:
                            celda.alignment = Alignment(
                                vertical="center", wrap_text=True
                            )

                salida_cencosud.seek(0)
                st.download_button(
                    "⬇️ Descargar datos CENCOSUD",
                    data=salida_cencosud.getvalue(),
                    file_name="datos_cencosud_etiquetas.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key="descargar_datos_cencosud_etiquetas",
                    width="stretch",
                )


def render_tareas() -> None:
    with st.sidebar:
        st.markdown("### Visualización")
        modo = selector_modo_visual()
        st.toggle("Diagnóstico de rendimiento", key="debug_rendimiento")

    perfil = perfil_visual(modo)
    aplicar_estilo_pantalla(modo)

    encabezado, acciones = st.columns([5, 1], vertical_alignment="center")
    with encabezado:
        st.title("📋 Centro de Control Operativo")
        st.caption("Seguimiento en vivo de pedidos, carros, despachos y sectores")
    with acciones:
        if st.button("🔄 Actualizar ahora", width="stretch"):
            invalidar_cache_tareas()
            construir_contexto_tareas.clear()
            st.rerun()

    # Navegación con carga bajo demanda: a diferencia de st.tabs,
    # solamente se ejecuta la vista seleccionada. Esto evita construir
    # Estadísticas mientras el usuario está trabajando en Operación en vivo.
    vista = st.segmented_control(
        "Vista del módulo",
        options=["⚡ Operación en vivo", "📊 Estadísticas"],
        default="⚡ Operación en vivo",
        key="tareas_vista_modulo",
        label_visibility="collapsed",
    )

    if vista == "📊 Estadísticas":
        from views.tareas.estadisticas import render_estadisticas_tareas

        render_estadisticas_tareas()
    else:
        _render_fragmento_operativo(perfil)
