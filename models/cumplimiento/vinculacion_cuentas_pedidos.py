from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd


CAMPOS_HR = [
    "FechaHoraPrimeraHojaRuta",
    "FechaHoraUltimaHojaRuta",
    "CantidadHojasRuta",
    "HojaRuta",
    "ZonaHR",
    "Flete",
    "Expreso",
    "LugarEntrega",
    "Localidad",
    "CodigoEntrega",
    "UnidadesHR",
    "BultosHR",
    "PesoHR",
    "VolumenHR",
]


def _texto(valor: object) -> str:
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _normalizar_texto(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", _texto(valor).upper())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texto)


def _normalizar_codigo(valor: object) -> str:
    texto = _texto(valor).upper()
    texto = re.sub(r"\.0$", "", texto)
    return re.sub(r"[^A-Z0-9]", "", texto)


def _extraer_cuenta(pedido: object) -> str:
    """Reconoce cuentas DIGIP 0001 y 0008 aun con espacios o guiones."""
    texto = _texto(pedido)
    coincidencia = re.match(r"^\s*(\d{4})(?:\D|$)", texto)
    return coincidencia.group(1) if coincidencia else ""


def _serie(dataframe: pd.DataFrame, columna: str, valor="") -> pd.Series:
    if columna in dataframe.columns:
        return dataframe[columna]
    return pd.Series(valor, index=dataframe.index)


def _clave_cliente(dataframe: pd.DataFrame) -> pd.Series:
    """Usa códigos antes que nombres para no vincular homónimos."""
    candidatos = [
        "CodigoClienteMaestro",
        "ClienteCodigoHR",
        "ClienteCodigo",
    ]
    clave = pd.Series("", index=dataframe.index, dtype="object")
    for columna in candidatos:
        valor = _serie(dataframe, columna).map(_normalizar_codigo)
        clave = clave.where(clave.ne(""), valor)

    nombres = ["ClienteMaestro", "ClienteFinal"]
    for columna in nombres:
        valor = _serie(dataframe, columna).map(_normalizar_texto)
        clave = clave.where(clave.ne(""), valor)
    return clave


def _clave_logistica(dataframe: pd.DataFrame) -> pd.Series:
    candidatos = [
        "CodigoLogisticoMaestro",
        "CodigoEntrega",
        "CodigoDespacho",
    ]
    clave = pd.Series("", index=dataframe.index, dtype="object")
    for columna in candidatos:
        valor = _serie(dataframe, columna).map(_normalizar_codigo)
        clave = clave.where(clave.ne(""), valor)
    return clave


def _fecha_referencia(dataframe: pd.DataFrame) -> pd.Series:
    columnas = [
        "FechaHoraFinControl",
        "FechaHoraFinPreparacion",
        "FechaHoraInicioPreparacion",
        "FechaHoraCreacion",
    ]
    salida = pd.Series(pd.NaT, index=dataframe.index, dtype="datetime64[ns]")
    for columna in columnas:
        valor = pd.to_datetime(_serie(dataframe, columna, pd.NaT), errors="coerce")
        salida = salida.combine_first(valor)
    return salida


def _horas_diferencia(a: object, b: object) -> float:
    if pd.isna(a) or pd.isna(b):
        return np.nan
    return abs((pd.Timestamp(a) - pd.Timestamp(b)).total_seconds()) / 3600


def _clasificar_confianza(horas: float, coincidencia_logistica: bool) -> str:
    if pd.isna(horas):
        return "BAJA"
    if coincidencia_logistica and horas <= 24:
        return "ALTA"
    if horas <= 24:
        return "ALTA"
    if horas <= 48:
        return "MEDIA"
    return "BAJA"


def _recalcular_estado_ciclo(tabla: pd.DataFrame) -> pd.DataFrame:
    salida = tabla.copy()
    salida["TieneHojaRutaOriginal"] = salida["FechaHoraPrimeraHojaRutaOriginal"].notna()
    salida["TieneHojaRutaHeredada"] = salida["FechaHoraPrimeraHojaRutaAsignada"].notna()
    salida["TieneHojaRuta"] = salida["FechaHoraPrimeraHojaRuta"].notna()

    inicio_control = pd.to_datetime(
        salida.get("FechaHoraFinControl", pd.Series(pd.NaT, index=salida.index)),
        errors="coerce",
    )
    fecha_hr = pd.to_datetime(salida["FechaHoraPrimeraHojaRuta"], errors="coerce")
    salida["HorasControlHojaRuta"] = (
        fecha_hr - inicio_control
    ).dt.total_seconds().div(3600)
    salida.loc[salida["HorasControlHojaRuta"].lt(0), "HorasControlHojaRuta"] = np.nan

    creacion = pd.to_datetime(
        salida.get("FechaHoraCreacion", pd.Series(pd.NaT, index=salida.index)),
        errors="coerce",
    )
    salida["HorasCicloHastaHojaRuta"] = (
        fecha_hr - creacion
    ).dt.total_seconds().div(3600)
    salida.loc[salida["HorasCicloHastaHojaRuta"].lt(0), "HorasCicloHastaHojaRuta"] = np.nan

    tiene_control = salida.get(
        "TieneControl",
        pd.to_datetime(salida.get("FechaHoraFinControl"), errors="coerce").notna(),
    ).fillna(False)
    tiene_preparacion = salida.get(
        "TienePreparacion",
        pd.to_datetime(salida.get("FechaHoraFinPreparacion"), errors="coerce").notna(),
    ).fillna(False)

    salida["UltimaEtapaRegistrada"] = np.select(
        [salida["TieneHojaRuta"], tiene_control, tiene_preparacion],
        [
            "CERRADO CON HOJA DE RUTA",
            "CERRADO SIN HOJA DE RUTA",
            "CERRADO SIN CONTROL",
        ],
        default="CERRADO SIN PREPARACION",
    )
    return salida


def asignar_hr_pedidos_cuenta_2(
    base_ciclo: pd.DataFrame | None,
    ventana_maxima_horas: int = 72,
    ventana_cliente_dias: int = 7,
    margen_ambiguedad_horas: int = 6,
) -> tuple[pd.DataFrame, dict]:
    """
    Completa la salida logística de pedidos cuenta 0008.

    Prioridad:
    1. HR propia.
    2. HR de pedido hermano 0001 del mismo cliente dentro de 72 horas.
    3. Última HR conocida del mismo cliente dentro de 7 días corridos.
    4. Si no existe referencia, el pedido 0008 queda igualmente cerrado,
       identificado como cuenta 2 sin HR de referencia.
    """
    if base_ciclo is None or base_ciclo.empty:
        return pd.DataFrame() if base_ciclo is None else base_ciclo.copy(), {
            "cuenta_2_analizados": 0,
            "hr_heredadas": 0,
            "hr_heredadas_hermano": 0,
            "hr_heredadas_cliente_7d": 0,
            "cuenta_2_cerrada_sin_hr": 0,
            "alta_confianza": 0,
            "media_confianza": 0,
            "baja_confianza": 0,
            "ambiguos": 0,
            "sin_candidato": 0,
        }

    tabla = base_ciclo.copy()
    tabla["CuentaPedido"] = tabla.get("Pedido", pd.Series("", index=tabla.index)).map(_extraer_cuenta)
    tabla["ClaveClienteVinculacion"] = _clave_cliente(tabla)
    tabla["ClaveLogisticaVinculacion"] = _clave_logistica(tabla)
    tabla["FechaReferenciaVinculacion"] = _fecha_referencia(tabla)

    for campo in CAMPOS_HR:
        if campo not in tabla.columns:
            tabla[campo] = pd.NaT if campo.startswith("FechaHora") else np.nan
        tabla[f"{campo}Original"] = tabla[campo]
        if campo.startswith("FechaHora"):
            tabla[f"{campo}Asignada"] = pd.Series(pd.NaT, index=tabla.index, dtype="datetime64[ns]")
        elif campo in {"CantidadHojasRuta", "UnidadesHR", "BultosHR", "PesoHR", "VolumenHR"}:
            tabla[f"{campo}Asignada"] = pd.Series(np.nan, index=tabla.index, dtype="float64")
        else:
            tabla[f"{campo}Asignada"] = pd.Series("", index=tabla.index, dtype="object")

    tabla["PedidoCuenta1Relacionado"] = ""
    tabla["TipoAsignacionHR"] = np.where(
        tabla["FechaHoraPrimeraHojaRutaOriginal"].notna(), "HR PROPIA", "SIN HR"
    )
    tabla["HorasDiferenciaPedidoHermano"] = np.nan
    tabla["DiasDiferenciaUltimaHRCliente"] = np.nan
    tabla["ConfianzaAsignacionHR"] = ""
    tabla["MotivoNoAsignacionHR"] = ""
    tabla["CantidadCandidatosHR"] = 0
    tabla["CierreOperativoCuenta2"] = tabla["CuentaPedido"].eq("0008")

    candidatos_con_hr = tabla.loc[
        tabla["FechaHoraPrimeraHojaRutaOriginal"].notna()
        & tabla["ClaveClienteVinculacion"].ne("")
    ].copy()
    candidatos_cuenta_1 = candidatos_con_hr.loc[
        candidatos_con_hr["CuentaPedido"].eq("0001")
    ].copy()

    objetivos = tabla.index[
        tabla["CuentaPedido"].eq("0008")
        & tabla["FechaHoraPrimeraHojaRutaOriginal"].isna()
    ]

    def asignar_desde_candidato(
        indice: int,
        candidato: pd.Series,
        tipo: str,
        confianza: str,
        horas: float | None = None,
    ) -> None:
        for campo in CAMPOS_HR:
            valor = candidato.get(f"{campo}Original", candidato.get(campo, np.nan))
            tabla.at[indice, f"{campo}Asignada"] = valor
            tabla.at[indice, campo] = valor
        tabla.at[indice, "PedidoCuenta1Relacionado"] = _texto(candidato.get("Pedido", ""))
        tabla.at[indice, "TipoAsignacionHR"] = tipo
        tabla.at[indice, "ConfianzaAsignacionHR"] = confianza
        tabla.at[indice, "MotivoNoAsignacionHR"] = ""
        if horas is not None and pd.notna(horas):
            tabla.at[indice, "HorasDiferenciaPedidoHermano"] = round(float(horas), 2)
            tabla.at[indice, "DiasDiferenciaUltimaHRCliente"] = round(float(horas) / 24, 2)

    def intentar_ultima_hr_cliente(indice: int, cliente: str, fecha_objetivo) -> bool:
        if not cliente or pd.isna(fecha_objetivo):
            return False
        candidatos = candidatos_con_hr.loc[
            candidatos_con_hr["ClaveClienteVinculacion"].eq(cliente)
            & (candidatos_con_hr.index != indice)
        ].copy()
        if candidatos.empty:
            return False

        fecha_hr = pd.to_datetime(
            candidatos["FechaHoraPrimeraHojaRutaOriginal"], errors="coerce"
        )
        candidatos["_FechaHR"] = fecha_hr
        candidatos["_HorasHR"] = fecha_hr.map(
            lambda fecha: _horas_diferencia(fecha_objetivo, fecha)
        )
        limite = float(ventana_cliente_dias * 24)
        candidatos = candidatos.loc[
            candidatos["_HorasHR"].notna() & candidatos["_HorasHR"].le(limite)
        ].copy()
        if candidatos.empty:
            return False

        # "Última HR del cliente": dentro de la ventana se prioriza la fecha
        # más reciente. A igualdad, la más cercana al cierre del pedido.
        candidatos = candidatos.sort_values(
            ["_FechaHR", "_HorasHR"], ascending=[False, True]
        )
        mejor = candidatos.iloc[0]
        asignar_desde_candidato(
            indice,
            mejor,
            "HR HEREDADA ULTIMA CLIENTE 7D",
            "REFERENCIA 7D",
            float(mejor["_HorasHR"]),
        )
        return True

    for indice in objetivos:
        cliente = tabla.at[indice, "ClaveClienteVinculacion"]
        fecha_objetivo = tabla.at[indice, "FechaReferenciaVinculacion"]
        logistica_objetivo = tabla.at[indice, "ClaveLogisticaVinculacion"]

        asignado = False
        candidatos = candidatos_cuenta_1.loc[
            candidatos_cuenta_1["ClaveClienteVinculacion"].eq(cliente)
        ].copy() if cliente else pd.DataFrame()

        if not candidatos.empty and pd.notna(fecha_objetivo):
            candidatos["_Horas"] = candidatos["FechaReferenciaVinculacion"].map(
                lambda fecha: _horas_diferencia(fecha_objetivo, fecha)
            )
            candidatos = candidatos.loc[
                candidatos["_Horas"].notna()
                & candidatos["_Horas"].le(float(ventana_maxima_horas))
            ].copy()

            if not candidatos.empty:
                candidatos["_MismaLogistica"] = (
                    logistica_objetivo != ""
                ) & candidatos["ClaveLogisticaVinculacion"].eq(logistica_objetivo)
                candidatos = candidatos.sort_values(
                    ["_MismaLogistica", "_Horas", "FechaHoraPrimeraHojaRutaOriginal"],
                    ascending=[False, True, False],
                )
                tabla.at[indice, "CantidadCandidatosHR"] = int(len(candidatos))

                mejor = candidatos.iloc[0]
                ambiguo = False
                if len(candidatos) > 1:
                    segundo = candidatos.iloc[1]
                    misma_prioridad = bool(mejor["_MismaLogistica"]) == bool(
                        segundo["_MismaLogistica"]
                    )
                    ambiguo = (
                        misma_prioridad
                        and float(segundo["_Horas"] - mejor["_Horas"])
                        < margen_ambiguedad_horas
                    )

                if not ambiguo:
                    horas = float(mejor["_Horas"])
                    confianza = _clasificar_confianza(
                        horas, bool(mejor["_MismaLogistica"])
                    )
                    asignar_desde_candidato(
                        indice,
                        mejor,
                        "HR HEREDADA CUENTA 1",
                        confianza,
                        horas,
                    )
                    asignado = True

        if not asignado:
            asignado = intentar_ultima_hr_cliente(indice, cliente, fecha_objetivo)

        if not asignado:
            tabla.at[indice, "TipoAsignacionHR"] = "CUENTA 2 CERRADA SIN HR REFERENCIA"
            if not cliente:
                motivo = "Cliente sin clave comparable"
            elif pd.isna(fecha_objetivo):
                motivo = "Pedido sin fecha de referencia"
            else:
                motivo = f"Sin HR del cliente dentro de {ventana_cliente_dias} días"
            tabla.at[indice, "MotivoNoAsignacionHR"] = motivo

    tabla["HojaRutaFinal"] = tabla["HojaRuta"]
    tabla["FechaHoraPrimeraHojaRutaFinal"] = tabla["FechaHoraPrimeraHojaRuta"]
    tabla["FechaHoraUltimaHojaRutaFinal"] = tabla["FechaHoraUltimaHojaRuta"]
    tabla["OrigenHojaRutaFinal"] = np.select(
        [
            tabla["FechaHoraPrimeraHojaRutaOriginal"].notna(),
            tabla["TipoAsignacionHR"].eq("HR HEREDADA CUENTA 1"),
            tabla["TipoAsignacionHR"].eq("HR HEREDADA ULTIMA CLIENTE 7D"),
            tabla["TipoAsignacionHR"].eq("CUENTA 2 CERRADA SIN HR REFERENCIA"),
        ],
        ["PROPIA", "HEREDADA CUENTA 1", "ULTIMA HR CLIENTE 7D", "CUENTA 2 SIN HR"],
        default="SIN HR",
    )

    tabla = _recalcular_estado_ciclo(tabla)
    mascara_cuenta2_sin_hr = (
        tabla["CuentaPedido"].eq("0008")
        & tabla["FechaHoraPrimeraHojaRuta"].isna()
    )
    tabla.loc[
        mascara_cuenta2_sin_hr, "UltimaEtapaRegistrada"
    ] = "CUENTA 2 CERRADA SIN HR REFERENCIA"

    diagnostico = {
        "cuenta_2_analizados": int(len(objetivos)),
        "hr_heredadas": int(tabla["TipoAsignacionHR"].isin([
            "HR HEREDADA CUENTA 1", "HR HEREDADA ULTIMA CLIENTE 7D"
        ]).sum()),
        "hr_heredadas_hermano": int(tabla["TipoAsignacionHR"].eq("HR HEREDADA CUENTA 1").sum()),
        "hr_heredadas_cliente_7d": int(tabla["TipoAsignacionHR"].eq("HR HEREDADA ULTIMA CLIENTE 7D").sum()),
        "cuenta_2_cerrada_sin_hr": int(tabla["TipoAsignacionHR"].eq("CUENTA 2 CERRADA SIN HR REFERENCIA").sum()),
        "alta_confianza": int(tabla["ConfianzaAsignacionHR"].eq("ALTA").sum()),
        "media_confianza": int(tabla["ConfianzaAsignacionHR"].eq("MEDIA").sum()),
        "baja_confianza": int(tabla["ConfianzaAsignacionHR"].eq("BAJA").sum()),
        "ambiguos": int(tabla["TipoAsignacionHR"].eq("AMBIGUO — REVISAR").sum()),
        "sin_candidato": int(tabla["TipoAsignacionHR"].eq("CUENTA 2 CERRADA SIN HR REFERENCIA").sum()),
    }
    return tabla.reset_index(drop=True), diagnostico
