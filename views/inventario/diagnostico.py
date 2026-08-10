from __future__ import annotations
import pandas as pd
import streamlit as st
from models.inventario.analisis import construir_resultado_inventario
from models.inventario.diagnostico import construir_diagnostico
from utils.inventario.persistencia import (
    leer_planes, leer_items, leer_conteos, leer_reconteos, leer_acciones,
    guardar_acciones_diagnostico, actualizar_acciones_desde_editor,
)
from utils.inventario.ubicaciones import enriquecer_detalle_ubicaciones


def render_diagnostico(tabla_viva: pd.DataFrame, detalle_vivo: pd.DataFrame, maestro_ubicaciones: pd.DataFrame | None=None) -> None:
    st.subheader("🧠 Diagnóstico y plan de acciones")
    st.caption("Localiza el próximo paso: Picking, Almacén, WMS o corrección del ERP.")
    planes=leer_planes()
    if planes.empty:
        st.info("No existen inventarios guardados."); return
    inv=st.selectbox("Inventario",planes["InventarioID"].astype(str).tolist(),key="diag_inv")
    items,conteos,reconteos=leer_items(),leer_conteos(),leer_reconteos()
    resultado,detalle_plan=construir_resultado_inventario(inventario_id=inv,items=items,conteos=conteos,reconteos=reconteos)
    if resultado.empty:
        st.info("El inventario todavía no tiene conteos para diagnosticar."); return
    detalle_plan=enriquecer_detalle_ubicaciones(detalle_plan,maestro_ubicaciones)
    detalle_vivo=enriquecer_detalle_ubicaciones(detalle_vivo,maestro_ubicaciones)
    diagnostico=construir_diagnostico(resultado,detalle_plan,detalle_vivo)
    pendientes=int(diagnostico["AccionSugerida"].ne("Sin acción").sum())
    erp=int(diagnostico["SistemaObjetivo"].eq("ERP").sum())
    wms=int(diagnostico["SistemaObjetivo"].eq("WMS").sum())
    contar=int(diagnostico["SistemaObjetivo"].eq("Conteo").sum())
    k1,k2,k3,k4=st.columns(4)
    k1.metric("Acciones sugeridas",pendientes); k2.metric("Nuevos conteos",contar); k3.metric("Correcciones WMS",wms); k4.metric("Correcciones ERP",erp)
    sistemas=st.multiselect("Sistema objetivo",sorted(diagnostico["SistemaObjetivo"].unique()),default=[x for x in ["Conteo","WMS","ERP"] if x in set(diagnostico["SistemaObjetivo"])])
    visual=diagnostico.loc[diagnostico["SistemaObjetivo"].isin(sistemas)].copy() if sistemas else diagnostico
    st.dataframe(visual,hide_index=True,width="stretch",height=430)
    if st.button("💾 Registrar / actualizar acciones sugeridas",type="primary",width="stretch"):
        guardar_acciones_diagnostico(inv,diagnostico); st.success("Acciones actualizadas."); st.rerun()

    st.markdown("### Seguimiento de acciones")
    acciones=leer_acciones()
    acciones=acciones.loc[acciones["InventarioID"].astype(str).eq(inv)].copy() if not acciones.empty else acciones
    if acciones.empty:
        st.info("Registrá las sugerencias para iniciar el seguimiento."); return
    edit=st.data_editor(
        acciones,hide_index=True,width="stretch",height=420,
        disabled=[c for c in acciones.columns if c not in {"EstadoAccion","Responsable","CausaRaiz","Resolucion","Observaciones"}],
        column_config={
            "EstadoAccion":st.column_config.SelectboxColumn("Estado",options=["Pendiente","En proceso","Ejecutada","Verificada","Descartada"]),
            "CausaRaiz":st.column_config.SelectboxColumn("Causa raíz",options=["","Picking","Almacén","Reposición","Recepción","Movimiento pendiente","Error ERP","Error WMS","Error de conteo","Otra"]),
        },key="editor_acciones_inv")
    if st.button("✅ Guardar seguimiento",width="stretch"):
        actualizar_acciones_desde_editor(edit); st.success("Seguimiento guardado."); st.rerun()
