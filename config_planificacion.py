"""Configuraciones internas para el motor de planificación de cargas.

Este archivo reemplaza los Excel auxiliares de zonas y prioridades.
Todos los códigos deben mantenerse como texto para conservar ceros iniciales.
"""


# ==========================================================
# ZONAS Y GRUPOS DE DESPACHO
# ==========================================================

ZONAS_PLANIFICACION = {
    "05020004": {
        "descripcion": 'COMUNA 4',
        "grupo": '1',
        "planificacion": 'DIARIOS',
    },
    "05020008": {
        "descripcion": 'COMUNA 8',
        "grupo": '1',
        "planificacion": 'DIARIOS',
    },
    "05010001": {
        "descripcion": 'TRANSPORTES CAP FED',
        "grupo": '1',
        "planificacion": 'EXPRESOS',
    },
    "02010001": {
        "descripcion": 'HURLINGHAM',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010002": {
        "descripcion": 'ITUZAINGO',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010004": {
        "descripcion": 'MERLO',
        "grupo": '2',
        "planificacion": 'VIERNES',
    },
    "02010005": {
        "descripcion": 'MORENO',
        "grupo": '2',
        "planificacion": 'VIERNES',
    },
    "02010006": {
        "descripcion": 'MORON',
        "grupo": '2',
        "planificacion": 'VIERNES',
    },
    "02010007": {
        "descripcion": 'LUJAN',
        "grupo": '2',
        "planificacion": 'VIERNES',
    },
    "02010008": {
        "descripcion": 'LOMAS DEL MIRADOR',
        "grupo": '1',
        "planificacion": 'DIARIOS',
    },
    "02010010": {
        "descripcion": 'RAMOS MEJIA',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010011": {
        "descripcion": 'CIUDADELA',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010012": {
        "descripcion": 'CASEROS',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010013": {
        "descripcion": 'VILLA BOSCH',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "02010014": {
        "descripcion": 'HAEDO',
        "grupo": '1',
        "planificacion": 'VIERNES',
    },
    "01010001": {
        "descripcion": '3 DE FEBRERO',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010002": {
        "descripcion": 'CAMPANA - ZARATE',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010003": {
        "descripcion": 'ESCOBAR - GARIN - PILAR',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010004": {
        "descripcion": 'SAN FERNANDO',
        "grupo": '2',
        "planificacion": 'LUNES',
    },
    "01010005": {
        "descripcion": 'SAN ISIDRO',
        "grupo": '2',
        "planificacion": 'LUNES',
    },
    "01010006": {
        "descripcion": 'SAN MARTIN',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010007": {
        "descripcion": 'SAN MIGUEL',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010008": {
        "descripcion": 'TIGRE',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010009": {
        "descripcion": 'VICENTE LOPEZ',
        "grupo": '2',
        "planificacion": 'LUNES',
    },
    "01010010": {
        "descripcion": 'MALVINAS ARGENTINAS',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010011": {
        "descripcion": 'JOSE C PAZ',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010012": {
        "descripcion": 'POLVORINES-DEL VISO-TORTUGUITAS',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010013": {
        "descripcion": 'BENAVIDEZ',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "01010014": {
        "descripcion": 'DERQUI',
        "grupo": '1',
        "planificacion": 'LUNES',
    },
    "05020002": {
        "descripcion": 'COMUNA 2',
        "grupo": '3',
        "planificacion": 'LUNES',
    },
    "05020012": {
        "descripcion": 'COMUNA 12',
        "grupo": '3',
        "planificacion": 'LUNES',
    },
    "05020013": {
        "descripcion": 'COMUNA 13',
        "grupo": '3',
        "planificacion": 'LUNES',
    },
    "05020014": {
        "descripcion": 'COMUNA 14',
        "grupo": '3',
        "planificacion": 'LUNES',
    },
    "05020015": {
        "descripcion": 'COMUNA 15',
        "grupo": '3',
        "planificacion": 'LUNES',
    },
    "03010001": {
        "descripcion": 'A. KORN - GUERNICA',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010002": {
        "descripcion": 'ESTEBAN ECHEVERRIA',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010003": {
        "descripcion": 'EZEIZA',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010004": {
        "descripcion": 'LANUS',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010005": {
        "descripcion": 'LOMAS DE ZAMORA',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010007": {
        "descripcion": 'LONGCHAMPS',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010008": {
        "descripcion": 'MONTE GRANDE',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010009": {
        "descripcion": 'BANFIELD',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "03010010": {
        "descripcion": 'TRISTAN SUAREZ',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "04010001": {
        "descripcion": 'ALTE. BROWN',
        "grupo": '1',
        "planificacion": 'MARTES',
    },
    "05020001": {
        "descripcion": 'COMUNA 1',
        "grupo": '2',
        "planificacion": 'MARTES',
    },
    "05020003": {
        "descripcion": 'COMUNA 3',
        "grupo": '2',
        "planificacion": 'MARTES',
    },
    "05020005": {
        "descripcion": 'COMUNA 5',
        "grupo": '2',
        "planificacion": 'MARTES',
    },
    "05020006": {
        "descripcion": 'COMUNA 6',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "05020007": {
        "descripcion": 'COMUNA 7',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "05020009": {
        "descripcion": 'COMUNA 9',
        "grupo": '2',
        "planificacion": 'MARTES',
    },
    "05020010": {
        "descripcion": 'COMUNA 10',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "05020011": {
        "descripcion": 'COMUNA 11',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "0601": {
        "descripcion": 'ISIDRO CASANOVA',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0602": {
        "descripcion": 'RAFAEL CASTILO',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0603": {
        "descripcion": 'CIUDAD EVITA',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0604": {
        "descripcion": 'LAFERRERE',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0605": {
        "descripcion": 'GONZALEZ CATAN',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0606": {
        "descripcion": 'VIRREY DEL PINO',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "0607": {
        "descripcion": 'SAN JUSTO',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "0608": {
        "descripcion": 'CAÑUELAS',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "02010003": {
        "descripcion": 'VILLA MADERO',
        "grupo": '1',
        "planificacion": 'MIERCOLES',
    },
    "02010009": {
        "descripcion": 'SAN JUSTO',
        "grupo": '2',
        "planificacion": 'MIERCOLES',
    },
    "04010002": {
        "descripcion": 'AVELLANEDA',
        "grupo": '2',
        "planificacion": 'JUEVES',
    },
    "04010003": {
        "descripcion": 'BERAZATEGUI',
        "grupo": '2',
        "planificacion": 'JUEVES',
    },
    "04010004": {
        "descripcion": 'BERISSO - CITY BELL - LA PLATA',
        "grupo": '1',
        "planificacion": 'JUEVES',
    },
    "04010005": {
        "descripcion": 'FLORENCIO VARELA',
        "grupo": '1',
        "planificacion": 'JUEVES',
    },
    "04010006": {
        "descripcion": 'QUILMES',
        "grupo": '2',
        "planificacion": 'JUEVES',
    },
    "04010007": {
        "descripcion": 'BERNAL',
        "grupo": '2',
        "planificacion": 'JUEVES',
    },
}


# ==========================================================
# PLANIFICACIÓN ESPECÍFICA DE EXPRESOS
# ==========================================================
#
# El código 05010001 identifica que el pedido se envía por
# expreso, pero no define por sí solo el día ni el grupo.
#
# Para esos pedidos se usa la zona obtenida desde el maestro
# de expresos (ZonaAgrupadorExpreso) y se la relaciona con:
#
# - planificacion: día operativo en que debe prepararse;
# - grupo: grupo zonal al que se incorpora;
# - codigos_despacho: códigos de zona que componen el grupo.
#
# IMPORTANTE:
# Las claves deben coincidir con ZonaAgrupadorExpreso luego
# de normalizar el texto a mayúsculas y quitar espacios.
# ==========================================================

PLANIFICACION_EXPRESOS = {

    "CABA SUR": {
        "planificacion": "JUEVES",
        "grupo": "2",
        "codigos_despacho": [
            "04010002",  # AVELLANEDA
            "04010003",  # BERAZATEGUI
            "04010006",  # QUILMES
            "04010007",  # BERNAL
        ],
    },

    "CABA SUR I": {
        "planificacion": "JUEVES",
        "grupo": "2",
        "codigos_despacho": [
            "04010002",
            "04010003",
            "04010006",
            "04010007",
        ],
    },

    "CABA SUR II": {
        "planificacion": "JUEVES",
        "grupo": "1",
        "codigos_despacho": [
            "04010004",  # BERISSO - CITY BELL - LA PLATA
            "04010005",  # FLORENCIO VARELA
        ],
    },

    "CABA NORTE": {
        "planificacion": "LUNES",
        "grupo": "3",
        "codigos_despacho": [
            "05020002",  # COMUNA 2
            "05020012",  # COMUNA 12
            "05020013",  # COMUNA 13
            "05020014",  # COMUNA 14
            "05020015",  # COMUNA 15
        ],
    },
}


# Alias para absorber diferencias de escritura provenientes
# del maestro de expresos.
ALIAS_ZONAS_EXPRESOS = {
    "CABA SUR 1": "CABA SUR I",
    "CABA SUR1": "CABA SUR I",
    "CABA SUR 2": "CABA SUR II",
    "CABA SUR2": "CABA SUR II",
    "SUR": "CABA SUR",
    "NORTE": "CABA NORTE",
}


def normalizar_zona_expreso(valor) -> str:
    """
    Normaliza una zona de expreso para buscarla en la
    configuración.
    """

    if valor is None:
        return ""

    zona = " ".join(
        str(valor)
        .strip()
        .upper()
        .split()
    )

    return ALIAS_ZONAS_EXPRESOS.get(
        zona,
        zona,
    )


def obtener_planificacion_expreso(
    zona_expreso
) -> dict:
    """
    Devuelve la configuración operativa de una zona de expreso.

    Nunca inventa una asignación. Si la zona no está configurada,
    devuelve valores vacíos y ZonaExpresoConfigurada=False para
    que el motor pueda mostrarla como pendiente de parametrizar.
    """

    zona_normalizada = normalizar_zona_expreso(
        zona_expreso
    )

    configuracion = PLANIFICACION_EXPRESOS.get(
        zona_normalizada
    )

    if configuracion is None:

        return {
            "ZonaExpresoNormalizada": zona_normalizada,
            "PlanificacionExpreso": "",
            "GrupoExpreso": "",
            "CodigosDespachoExpreso": [],
            "ZonaExpresoConfigurada": False,
        }

    return {
        "ZonaExpresoNormalizada": zona_normalizada,
        "PlanificacionExpreso": str(
            configuracion.get(
                "planificacion",
                ""
            )
        ).strip().upper(),
        "GrupoExpreso": str(
            configuracion.get(
                "grupo",
                ""
            )
        ).strip(),
        "CodigosDespachoExpreso": [
            str(codigo).strip()
            for codigo in configuracion.get(
                "codigos_despacho",
                []
            )
            if str(codigo).strip()
        ],
        "ZonaExpresoConfigurada": True,
    }


# ==========================================================
# CLIENTES PRIORITARIOS
# ==========================================================

CLIENTES_PRIORITARIOS = {
    "SA40": {
        "prioridad": 1,
        "cliente": 'SANICENTRO S.A. SANITARIOS',
        "tipo_entrega": 'Expreso',
        "responsable": 'Sanchez Roberto',
    },
    "AB08": {
        "prioridad": 2,
        "cliente": 'ABELSON S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Catanzariti Claudio',
    },
    "DF07": {
        "prioridad": 3,
        "cliente": 'DISTR. DE SANITARIOS FRANCO FIA S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "TB02": {
        "prioridad": 4,
        "cliente": 'IT BROKERS S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "CO22": {
        "prioridad": 5,
        "cliente": 'COPMACO LTDA.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Pizarro Laureano',
    },
    "SA60": {
        "prioridad": 6,
        "cliente": 'SANTAGAL S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "MC28": {
        "prioridad": 7,
        "cliente": 'MI CASA Y YO S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Catanzariti Claudio',
    },
    "BA30": {
        "prioridad": 8,
        "cliente": 'BARUGEL AZULAY Y CIA SAIC',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "CE23": {
        "prioridad": 9,
        "cliente": 'CEFALU S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Figueirido Matias',
    },
    "KN01": {
        "prioridad": 10,
        "cliente": 'KALFAIAN HNOS. S.R.L',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "GF09": {
        "prioridad": 11,
        "cliente": 'GILLI FAUDIN LUIS V. -GILCOMAT',
        "tipo_entrega": 'Expreso',
        "responsable": 'Directos',
    },
    "DM20": {
        "prioridad": 12,
        "cliente": 'DECO MIRACEMA SAS',
        "tipo_entrega": 'Zona',
        "responsable": 'Bellanza Hernan',
    },
    "CO28": {
        "prioridad": 13,
        "cliente": 'CONSTRUDISENO S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Catanzariti Claudio',
    },
    "DA11": {
        "prioridad": 14,
        "cliente": 'DAFYS S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "CP29": {
        "prioridad": 15,
        "cliente": 'CASA PICK S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "LG10": {
        "prioridad": 16,
        "cliente": 'LOPEZ GAS ONLINE S.A',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "AC02": {
        "prioridad": 17,
        "cliente": 'ACCESANIGA S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Mestre Horacio',
    },
    "DA18": {
        "prioridad": 18,
        "cliente": 'DADDONA S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Catanzariti Claudio',
    },
    "ED04": {
        "prioridad": 19,
        "cliente": 'EDIFICOR S.R.L.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Directos',
    },
    "KG04": {
        "prioridad": 20,
        "cliente": 'KATSUDA GUSTAVO ALEJANDRO',
        "tipo_entrega": 'Expreso',
        "responsable": 'Figueirido Matias',
    },
    "PL21": {
        "prioridad": 21,
        "cliente": 'PINTO LEONEL E. -SANIT. BRONCESUR',
        "tipo_entrega": 'Zona',
        "responsable": 'Bellanza Hernan',
    },
    "SS45": {
        "prioridad": 22,
        "cliente": 'SANITARIOS SAN MARTIN S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "ZE02": {
        "prioridad": 23,
        "cliente": 'ZERAMIKO DE MARIA R.O.CABRERA',
        "tipo_entrega": 'Expreso',
        "responsable": 'Nicolas Ruhl',
    },
    "EP08": {
        "prioridad": 24,
        "cliente": 'EL MUNDO DEL PLOMERO S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Nicolas Ruhl',
    },
    "MN04": {
        "prioridad": 25,
        "cliente": 'MATERIALES C. NUCIARI SRL',
        "tipo_entrega": 'Zona',
        "responsable": 'Merler Luis',
    },
    "JA01": {
        "prioridad": 26,
        "cliente": 'JOSE ANACLETO E HIJOS S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Sanchez Roberto',
    },
    "SC33": {
        "prioridad": 27,
        "cliente": 'SANITARIOS CAMPANA S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Catanzariti Claudio',
    },
    "TU03": {
        "prioridad": 28,
        "cliente": 'TUBONOR S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Directos',
    },
    "CT06": {
        "prioridad": 29,
        "cliente": 'COMERCIAL TUCSON S.A.',
        "tipo_entrega": 'Zona',
        "responsable": 'Merler Luis',
    },
    "LE14": {
        "prioridad": 30,
        "cliente": 'L.E.CER S.R.L.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Nicolas Ruhl',
    },
    "NA09": {
        "prioridad": 31,
        "cliente": 'NAVARRO ACHE S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Bellanza Hernan',
    },
    "SS43": {
        "prioridad": 32,
        "cliente": 'SANITARIOS SIONE S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Crespo Nicolas',
    },
    "BA41": {
        "prioridad": 33,
        "cliente": 'BALCARCE 54 S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Nicolas Ruhl',
    },
    "CP19": {
        "prioridad": 34,
        "cliente": 'CERAMICOS PELLEGRINI S.R.L.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Mestre Horacio',
    },
    "CR23": {
        "prioridad": 35,
        "cliente": 'CRETA PORCELLANATOS S.A. -CRETA DISEGNO',
        "tipo_entrega": 'Zona',
        "responsable": 'Directos',
    },
    "SS41": {
        "prioridad": 36,
        "cliente": 'SANITARIOS SANJUAN S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Merler Luis',
    },
    "CI03": {
        "prioridad": 37,
        "cliente": 'CARLOS ISLA Y CIA. S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Carreño Nestor',
    },
    "IC01": {
        "prioridad": 38,
        "cliente": 'IMPORTADORA COMERCIAL FUEGUINA',
        "tipo_entrega": 'Expreso',
        "responsable": 'Daniel Nuñez',
    },
    "CP02": {
        "prioridad": 39,
        "cliente": 'CASA PALM S.A.',
        "tipo_entrega": 'Expreso',
        "responsable": 'Carreño Nestor',
    },
    "HO07": {
        "prioridad": 40,
        "cliente": 'HOKAMAT SRL',
        "tipo_entrega": 'Zona',
        "responsable": 'Merler Luis',
    },
    "DA28": {
        "prioridad": 41,
        "cliente": 'DAPESOL S.A. -MATERIALES ACON',
        "tipo_entrega": 'Zona',
        "responsable": 'Figueirido Matias',
    },
    "VM15": {
        "prioridad": 42,
        "cliente": 'VILANOVA DE MEIA S.R.L.',
        "tipo_entrega": 'Zona',
        "responsable": 'Nicolas Ruhl',
    },
}


# ==========================================================
# VEHÍCULOS
# Ajustables cuando cambie la operación
# ==========================================================

TIPOS_VEHICULOS = {
    "Camioneta": {
        "capacidad_m3": 8.0,
    },
    "Camion": {
        "capacidad_m3": 15.0,
    },
}


# Valor usado para clientes sin prioridad configurada.
PRIORIDAD_GENERAL = 9999

# Los grupos marcados como NO quedan fuera de la asignación automática.
GRUPOS_EXCLUIDOS = {"NO", "", None}