from __future__ import annotations
import pandas as pd


def _sum(df, col):
    return float(pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce").fillna(0).sum())


def construir_diagnostico(articulos: pd.DataFrame, detalle_plan: pd.DataFrame, detalle_vivo: pd.DataFrame) -> pd.DataFrame:
    if articulos is None or articulos.empty:
        return pd.DataFrame()
    filas=[]
    for _, art in articulos.iterrows():
        codigo=str(art.get("ArticuloCodigo", ""))
        plan=detalle_plan.loc[detalle_plan["ArticuloCodigo"].astype(str).eq(codigo)].copy()
        vivo=detalle_vivo.loc[detalle_vivo["ArticuloCodigo"].astype(str).eq(codigo)].copy()
        pick_vivo=vivo.loc[vivo["TipoUbicacion"].eq("Picking")]
        alm_vivo=vivo.loc[vivo["TipoUbicacion"].eq("Almacén")]
        pick_plan=plan.loc[plan["TipoUbicacion"].eq("Picking")]
        alm_plan=plan.loc[plan["TipoUbicacion"].eq("Almacén")]
        sys_pick=_sum(pick_vivo,"Cantidad")
        sys_alm=_sum(alm_vivo,"Cantidad")
        cnt_pick=_sum(pick_plan,"CantidadFinalUbicacion")
        cnt_alm=_sum(alm_plan,"CantidadFinalUbicacion")
        pick_total=len(pick_vivo); alm_total=len(alm_vivo)
        pick_count=int(pick_plan.get("CantidadFinalUbicacion",pd.Series(dtype=float)).notna().sum())
        alm_count=int(alm_plan.get("CantidadFinalUbicacion",pd.Series(dtype=float)).notna().sum())
        pick_complete=pick_total>0 and pick_count>=pick_total
        alm_complete=alm_total>0 and alm_count>=alm_total
        dif_pick=cnt_pick-sys_pick if pick_complete else None
        dif_alm=cnt_alm-sys_alm if alm_complete else None
        erp=float(art.get("StockERPInicial", art.get("StockERP",0)) or 0)
        wms=float(art.get("StockWMSInicial", art.get("StockWMSResumen",0)) or 0)
        fisico=(cnt_pick if pick_complete else sys_pick)+(cnt_alm if alm_complete else sys_alm)
        dif_fis=wms and (fisico-wms) or (fisico-wms)

        if pick_total and not pick_complete:
            diag="Picking pendiente de validación"; accion="Contar ubicaciones de Picking"; sistema="Conteo"; tipo="Picking"
            sugeridas=", ".join(pick_vivo["Ubicacion"].astype(str).head(8))
        elif pick_complete and dif_pick != 0:
            diag="Diferencia localizada en Picking"; accion="Revisar movimientos y corregir WMS Picking; luego recontar"; sistema="WMS"; tipo="Picking"
            sugeridas=", ".join(pick_plan.loc[pick_plan["DiferenciaUbicacion"].fillna(0).ne(0),"Ubicacion"].astype(str).head(8))
        elif alm_total and not alm_complete:
            diag="Picking validado; falta confirmar Almacén"; accion="Contar ubicaciones de Almacén"; sistema="Conteo"; tipo="Almacén"
            sugeridas=", ".join(alm_vivo.sort_values("Cantidad",ascending=False)["Ubicacion"].astype(str).head(8))
        elif alm_complete and dif_alm != 0:
            diag="Diferencia localizada en Almacén"; accion="Revisar contenedores/movimientos y corregir WMS Almacén"; sistema="WMS"; tipo="Almacén"
            sugeridas=", ".join(alm_plan.loc[alm_plan["DiferenciaUbicacion"].fillna(0).ne(0),"Ubicacion"].astype(str).head(8))
        elif abs(fisico-wms) < 0.0001 and abs(erp-wms) > 0.0001:
            diag="Físico validado contra WMS; ERP desfasado"; accion="Corregir ERP y verificar en la próxima actualización"; sistema="ERP"; tipo=""
            sugeridas=""
        elif abs(fisico-wms) > 0.0001:
            diag="Físico no coincide con WMS"; accion="Investigar movimientos pendientes y ajustar WMS"; sistema="WMS"; tipo="General"
            sugeridas=", ".join(vivo.sort_values("Cantidad",ascending=False)["Ubicacion"].astype(str).head(8))
        else:
            diag="Artículo conciliado"; accion="Sin acción"; sistema="Ninguno"; tipo=""; sugeridas=""

        filas.append({
            "ArticuloCodigo":codigo,"ArticuloDescripcion":art.get("ArticuloDescripcion",""),
            "StockERP":erp,"StockWMS":wms,"StockFisicoEstimado":fisico,
            "DiferenciaERPvsWMS":wms-erp,"DiferenciaFisicavsWMS":fisico-wms,
            "PickingSistema":sys_pick,"PickingContado":cnt_pick if pick_complete else pd.NA,
            "AlmacenSistema":sys_alm,"AlmacenContado":cnt_alm if alm_complete else pd.NA,
            "PickingCompleto":pick_complete,"AlmacenCompleto":alm_complete,
            "Diagnostico":diag,"AccionSugerida":accion,"SistemaObjetivo":sistema,
            "TipoUbicacionObjetivo":tipo,"UbicacionesSugeridas":sugeridas,
        })
    return pd.DataFrame(filas)
