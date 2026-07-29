from __future__ import annotations

import re
import unicodedata
import pandas as pd


def _clave(texto: object) -> str:
    valor = unicodedata.normalize('NFKD', str(texto))
    valor = ''.join(c for c in valor if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', valor.lower())


def _buscar_columna(df: pd.DataFrame, alias: list[str]) -> str | None:
    mapa = {_clave(c): c for c in df.columns}
    for nombre in alias:
        if _clave(nombre) in mapa:
            return mapa[_clave(nombre)]
    return None


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    return (serie.fillna('').astype(str).str.strip().str.upper()
            .str.replace(r'\.0$', '', regex=True))


def normalizar_pedido(serie: pd.Series) -> pd.Series:
    return (serie.fillna('').astype(str).str.strip()
            .str.replace(r'\.0$', '', regex=True))


def pedido_digip_desde_codigo(valor: object) -> str:
    texto = str(valor or '').strip()
    if not texto:
        return ''
    partes = texto.split()
    if len(partes) >= 2:
        texto = partes[1]
    return texto.split('-')[0].strip()


def construir_disponible_por_articulo(df_disponible: pd.DataFrame) -> pd.DataFrame:
    columnas = ['ArticuloCodigo', 'StockDisponible']
    if df_disponible is None or df_disponible.empty:
        return pd.DataFrame(columns=columnas)

    tabla = df_disponible.copy()
    tabla.columns = [str(c).strip() for c in tabla.columns]

    col_codigo = _buscar_columna(tabla, [
        'CodigoArticulo', 'ArticuloCodigo', 'codigo_articulo', 'Código artículo',
        'Codigo', 'Código', 'Articulo', 'Artículo', 'CodArticulo',
    ])
    col_disponible = _buscar_columna(tabla, [
        'Disponible', 'StockDisponible', 'Stock Disponible', 'UnidadesDisponibles',
        'Unidades Disponibles', 'unidades_disponibles', 'CantidadDisponible',
    ])

    if col_codigo is None or col_disponible is None:
        raise ValueError(
            'No se pudieron identificar las columnas de código y disponible en '
            f'Disponible DIGIP. Columnas recibidas: {list(tabla.columns)}'
        )

    salida = pd.DataFrame({
        'ArticuloCodigo': normalizar_codigo(tabla[col_codigo]),
        'StockDisponible': pd.to_numeric(tabla[col_disponible], errors='coerce').fillna(0),
    })
    salida = salida.loc[salida['ArticuloCodigo'].ne('')]
    return (salida.groupby('ArticuloCodigo', as_index=False)
            .agg(StockDisponible=('StockDisponible', 'sum')))


def obtener_pedidos_activos_digip(df_pedidos_digip: pd.DataFrame) -> set[str]:
    """Devuelve pedidos que tienen al menos una transmisión activa en DIGIP.

    Una transmisión con Estado COMPLETO o COMPLETADO se considera histórica y
    no excluye al pedido del análisis ERP. Si el mismo número posee otra
    transmisión con un estado no finalizado, el pedido sí se considera activo.
    """
    if df_pedidos_digip is None or df_pedidos_digip.empty:
        return set()

    tabla = df_pedidos_digip.copy()

    if 'Codigo' in tabla.columns:
        tabla['_PedidoCobertura'] = tabla['Codigo'].apply(
            pedido_digip_desde_codigo
        )
    elif 'Pedido' in tabla.columns:
        tabla['_PedidoCobertura'] = normalizar_pedido(tabla['Pedido'])
    else:
        return set()

    tabla = tabla.loc[tabla['_PedidoCobertura'].ne('')].copy()
    if tabla.empty:
        return set()

    # Si no existe Estado, se conserva el criterio seguro anterior:
    # cualquier aparición actual en el reporte se considera activa.
    if 'Estado' not in tabla.columns:
        return set(tabla['_PedidoCobertura'].tolist())

    tabla['_EstadoCobertura'] = (
        tabla['Estado']
        .fillna('')
        .astype(str)
        .str.strip()
        .str.upper()
    )

    estados_completados = {
        'COMPLETO',
        'COMPLETADO',
    }

    tabla['_EsTransmisionActiva'] = ~tabla['_EstadoCobertura'].isin(
        estados_completados
    )

    # Basta con una transmisión vigente para considerar activo al pedido.
    actividad = (
        tabla.groupby('_PedidoCobertura')['_EsTransmisionActiva']
        .any()
    )

    return set(actividad.loc[actividad].index.tolist())

def analizar_cobertura_pedidos_erp(
    tabla_detalle_erp: pd.DataFrame,
    tabla_pendientes_erp: pd.DataFrame,
    df_pedidos_digip: pd.DataFrame,
    df_disponible: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evalúa únicamente pedidos pendientes ERP que no están activos hoy en DIGIP.

    Las transmisiones históricas no excluyen pedidos. El stock se asigna de forma
    acumulativa por fecha y número de pedido para evitar duplicar disponibilidad.
    """
    columnas_linea = [
        'Pedido', 'Fecha', 'Cliente', 'ArticuloCodigo', 'ArticuloDescripcion',
        'CantidadSolicitada', 'StockDisponibleInicial', 'CantidadCubierta',
        'CantidadFaltante', 'StockRestanteArticulo', 'EstadoCoberturaLinea',
    ]
    columnas_resumen = [
        'Pedido', 'Fecha', 'Cliente', 'TotalUnidades', 'TotalSKUs',
        'LineasSinCobertura', 'UnidadesCubiertas', 'UnidadesFaltantes',
        'PorcentajeCobertura', 'EstadoCobertura',
    ]
    if tabla_detalle_erp is None or tabla_detalle_erp.empty:
        return pd.DataFrame(columns=columnas_linea), pd.DataFrame(columns=columnas_resumen)

    detalle = tabla_detalle_erp.copy()
    detalle['Pedido'] = normalizar_pedido(detalle['Pedido'])
    detalle['ArticuloCodigo'] = normalizar_codigo(detalle['ArticuloCodigo'])
    detalle['Cantidad'] = pd.to_numeric(detalle['Cantidad'], errors='coerce').fillna(0)

    activos = obtener_pedidos_activos_digip(df_pedidos_digip)
    detalle = detalle.loc[~detalle['Pedido'].isin(activos)].copy()
    if detalle.empty:
        return pd.DataFrame(columns=columnas_linea), pd.DataFrame(columns=columnas_resumen)

    pendientes = tabla_pendientes_erp.copy() if tabla_pendientes_erp is not None else pd.DataFrame()
    if not pendientes.empty and 'Pedido' in pendientes.columns:
        pendientes['Pedido'] = normalizar_pedido(pendientes['Pedido'])
        col_fecha = _buscar_columna(pendientes, [
            'FechaPedidoERP', 'Fecha', 'FechaPedido', 'Fecha Pedido',
            'fec_com', 'Fecha de creación', 'Fecha Creacion',
        ])
        col_cliente = _buscar_columna(pendientes, [
            'ClienteDescripcionERP', 'Cliente', 'ClienteDescripcion',
            'Razón Social', 'Razon Social', 'nombre',
        ])
        meta = pd.DataFrame({'Pedido': pendientes['Pedido']})
        meta['Fecha'] = pd.to_datetime(pendientes[col_fecha], errors='coerce', dayfirst=True) if col_fecha else pd.NaT
        meta['Cliente'] = pendientes[col_cliente].fillna('').astype(str) if col_cliente else ''
        meta = meta.drop_duplicates('Pedido', keep='first')
        detalle = detalle.merge(meta, on='Pedido', how='left', validate='many_to_one')
    else:
        detalle['Fecha'] = pd.NaT
        detalle['Cliente'] = ''

    disponibilidad = construir_disponible_por_articulo(df_disponible)
    disponible_dict = dict(zip(disponibilidad['ArticuloCodigo'], disponibilidad['StockDisponible']))
    detalle['_orden_original'] = range(len(detalle))
    detalle = detalle.sort_values(['Fecha', 'Pedido', '_orden_original'], na_position='last').reset_index(drop=True)

    filas = []
    restante = {codigo: float(cant) for codigo, cant in disponible_dict.items()}
    for _, fila in detalle.iterrows():
        codigo = fila['ArticuloCodigo']
        solicitado = max(float(fila['Cantidad']), 0)
        inicial = max(float(disponible_dict.get(codigo, 0)), 0)
        disponible_actual = max(float(restante.get(codigo, 0)), 0)
        cubierto = min(solicitado, disponible_actual)
        faltante = max(solicitado - cubierto, 0)
        restante[codigo] = max(disponible_actual - cubierto, 0)
        if faltante <= 0:
            estado = 'Cubierto'
        elif cubierto > 0:
            estado = 'Parcial'
        else:
            estado = 'Sin cobertura'
        filas.append({
            'Pedido': fila['Pedido'], 'Fecha': fila.get('Fecha'), 'Cliente': fila.get('Cliente', ''),
            'ArticuloCodigo': codigo,
            'ArticuloDescripcion': fila.get('ArticuloDescripcion', ''),
            'CantidadSolicitada': solicitado, 'StockDisponibleInicial': inicial,
            'CantidadCubierta': cubierto, 'CantidadFaltante': faltante,
            'StockRestanteArticulo': restante[codigo], 'EstadoCoberturaLinea': estado,
        })

    lineas = pd.DataFrame(filas)
    numericas = ['CantidadSolicitada','StockDisponibleInicial','CantidadCubierta','CantidadFaltante','StockRestanteArticulo']
    for c in numericas:
        lineas[c] = pd.to_numeric(lineas[c], errors='coerce').fillna(0).round(2)

    resumen = (lineas.groupby('Pedido', as_index=False).agg(
        Fecha=('Fecha','first'), Cliente=('Cliente','first'),
        TotalUnidades=('CantidadSolicitada','sum'), TotalSKUs=('ArticuloCodigo','nunique'),
        LineasSinCobertura=('CantidadFaltante', lambda s: int((s > 0).sum())),
        UnidadesCubiertas=('CantidadCubierta','sum'), UnidadesFaltantes=('CantidadFaltante','sum'),
    ))
    resumen['PorcentajeCobertura'] = (
        resumen['UnidadesCubiertas'] / resumen['TotalUnidades'].replace(0, pd.NA) * 100
    ).fillna(0).round(1)
    resumen['EstadoCobertura'] = 'Cubierto'
    resumen.loc[resumen['UnidadesFaltantes'].gt(0) & resumen['UnidadesCubiertas'].gt(0), 'EstadoCobertura'] = 'Cobertura parcial'
    resumen.loc[resumen['UnidadesFaltantes'].gt(0) & resumen['UnidadesCubiertas'].le(0), 'EstadoCobertura'] = 'Sin cobertura'
    resumen = resumen.sort_values(['UnidadesFaltantes','Fecha'], ascending=[False, True], na_position='last').reset_index(drop=True)
    return lineas[columnas_linea], resumen[columnas_resumen]
