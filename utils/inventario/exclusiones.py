from __future__ import annotations

import pandas as pd


ARTICULOS_FUERA_INVENTARIO: dict[str, str] = {
    "40013": "Cinta Impresa Griferia Peirano para Embalar",
    "40023": "FILM STREECH 0.50 cm MANUAL 23 MIC TRANSPARENTE",
    "90009": "RODILLO Cierre Broceado",
    "90017": "PLACA DE Melamina BLANCA de 18 mm 1.83 x2.62 metro",
    "90018": "PLACA de Melamina NEGRO18 mm 1.82 x 2.62 metros",
    "90023": "Perfil de aluminio Tipo J de 25 mm x 6000mm",
    "90027": "Canto faz de 22 mmm Blanco",
    "BR04": "BROCHES COBREADOS 5/8 x 5000 unid",
    "CE03": "CINTA ADHESIVA SCOTCH 48 mm x 40m",
    "CE08": "CINTA ADHESIVA SCOTCH 24 mm x 40m",
    "DE01": "Detergente 15% concentrado en bidones de 5 Litros",
    "DE02": "Desodorante de amb. v/ fragancias en bidones 5 Lts",
    "DE03": "Desinsectacion y desratización",
    "ES02": "ESCOBILLON DE CERDA NATURAL 30 CM",
    "ES03": "ESCOBILLON DE CERDA PLASTICA 90 cm SAMANTHA",
    "ET01": "ETIQUETA ILUSTRACION 85mm x 90mm CONO 40 x 400 UNIDADES",
    "FLETEINTER": "Flete Internacional",
    "FLETEINTERSEG": "FLETE INTERNACIONAL + SEGURO",
    "JL01": "JABON LIQUIDO DE MANOS x Bidon de 5 lts",
    "LA01": "Lavandina concentrada de 60 Gr. en bidon de 5 Lts",
    "MP03": "MATERIAL PROMOCIONAL",
    "MTO765": "Refugio mecánico para Dock Para bocas de descarga",
    "MUESTRAGRIF": "MUESTRA GRIFERIA",
    "PALLET": "Pallets normalizados semi nuevos 1 x 1.20",
    "PH01": "Rollo de higienico x 30 m PREMIUN hoj.simp X 48 u",
    "RC02": "ROLLO DE CORRUGADO DE 1,20 M X 25 M",
    "RC10": "RIBBON CERA 110mm X 360 metros CONO 25mm",
    "RMP01": "RACK METALICO PARA PALLET",
    "RP01": "Toalla en Rollo PREMIUN auto-cut de 6 Bobinas",
    "S153": "ETIQUETA ILUSTRACION BLANCA 60mm x 60mm x 1000 UNIDADES",
    "S154": "ETIQUETA ILUSTRACION BLANCA 60mm x 30mm x 1000 UNIDADES",
    "S155": "BOLSITA CRISTAL 13 X 21 X 100 mic IMP PEIRANO",
    "S162": "FOLLETO DE GARANTIA GENERICO",
    "S278": "ETIQUETA 32 x 14 x 1015 unidades FUERA DE AZULEJO",
    "S292": "CAJA NRO 4",
    "S328": "CAJA NRO 8",
    "S350": "CAJA NRO 5",
    "S351": "CAJA NRO 6",
    "S406": "CAJA NRO 4 GRIFERIA LAGO",
    "S436": "ROLLO FILM 750mm Ø250mm 80 micrones",
    "S445": "ROLLO FILM POLIETILENO 650 mm 80 um",
    "S461": "ETIQUETA ILUSTRACION 100mm x 80mm CONO 40 x 500 UNIDADES",
    "S462": "CAJA EXHIBICION 1210 X 310 X 300 mm",
    "S463": "CAJA EXHIBICION 1010 X 310 X 300 mm",
    "S464": "CAJA EXHIBICION 910 X 310 X 300 mm",
    "SE03": "Secador de 50 cm con palo",
    "TPA01": "TRAPO 100% algodon para limpieza de maquinas",
    "9999": "Varios",
    "PDU110": "COBERTOR DE DESAGUE P/PISO DE DUCHA BLANCO",
    "PDU110N": "COBERTOR DE DESAGUE P/PISO DE DUCHA BLANCO",
    "M91-006": "ARANDELA HIERRO ZINCADO MONOCOMANDO BIDE",
    "CMP01": "CAMPANA SLIM 60 CM 3 VELOCIDADES",
    "S233": "CARTON P/REPUESTO ORIGINAL",
    "S431": "ROLLO FILM POF 600 mm 25 um, CENTRO DOBLADO",
    "MP05": "BOTELLA PROMOCIONAL 1/2 LITRO NEGRA C/LOGO PEIRANO"
}


def codigos_fuera_inventario() -> set[str]:
    return set(ARTICULOS_FUERA_INVENTARIO)


def tabla_articulos_fuera_inventario() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ArticuloCodigo": codigo,
                "ArticuloDescripcion": descripcion,
                "Obs": "No aplica",
            }
            for codigo, descripcion in ARTICULOS_FUERA_INVENTARIO.items()
        ]
    ).sort_values("ArticuloCodigo").reset_index(drop=True)


def marcar_articulos_fuera_inventario(tabla: pd.DataFrame) -> pd.DataFrame:
    if tabla is None or tabla.empty or "ArticuloCodigo" not in tabla.columns:
        return tabla.copy() if tabla is not None else pd.DataFrame()

    salida = tabla.copy()
    codigos = (
        salida["ArticuloCodigo"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )
    salida["AplicaInventario"] = ~codigos.isin(codigos_fuera_inventario())
    salida["MotivoExclusionInventario"] = ""
    salida.loc[~salida["AplicaInventario"], "MotivoExclusionInventario"] = "No aplica"
    return salida


def filtrar_articulos_fuera_inventario(
    tabla: pd.DataFrame,
    *,
    ocultar: bool,
) -> pd.DataFrame:
    marcada = marcar_articulos_fuera_inventario(tabla)
    if ocultar and not marcada.empty:
        marcada = marcada.loc[marcada["AplicaInventario"]].copy()
    return marcada.reset_index(drop=True)
