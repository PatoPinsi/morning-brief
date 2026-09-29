"""
Diccionario de pronunciación para que la voz lea la jerga del mercado como un argentino.
Se aplica sobre el guion justo antes de generar el audio (el panel y los textos no se tocan).
Para agregar un término: sumá una línea ("como está escrito", "como se tiene que decir").
El orden importa: primero van las expresiones más largas.
"""
import re

REEMPLAZOS = [
    # Red de seguridad de tono: si la IA igual usa estas expresiones, se reemplazan
    (r"\bOjo con el\b", "Atención al"),
    (r"\bojo con el\b", "atención al"),
    (r"\bOjo con\b", "Atención a"),
    (r"\bojo con\b", "atención a"),
    (r"\b[FfFf][ií]jate en\b", "Hay que seguir"),
    (r"\b[Ff][ií]jate\b", "Hay que ver"),
    (r"\bTené en cuenta\b", "Hay que tener en cuenta"),
    (r"\btené en cuenta\b", "hay que tener en cuenta"),
    # Índices y mercados
    (r"S&P\s?500", "ésanpi quinientos"),
    (r"S&P", "ésanpi"),
    (r"\bNasdaq\b", "násdak"),
    (r"\bDow Jones\b", "dau yons"),
    (r"\bMerval\b", "merval"),
    (r"\bWTI\b", "doble ve te i"),
    (r"\bWest Texas\b", "doble ve te i"),
    (r"\bEWZ\b", "el ETF de Brasil"),
    (r"\bMCHI\b", "el ETF de China"),
    (r"\bETFs?\b", "itiéfe"),
    (r"\bBTC\b", "bitcoin"),
    (r"\bETH\b", "ethereum"),
    # Empresas y especies
    (r"\bYPF\b", "ipeéfe"),
    (r"\bGGAL\b", "Galicia"),
    (r"\bBMA\b", "Macro"),
    (r"\bPAMP?\b", "Pampa"),
    (r"\bVIST\b", "Vista"),
    (r"\bTGS\b", "tegeése"),
    (r"\bCEPU\b", "Central Puerto"),
    (r"\bTXAR\b", "Ternium"),
    (r"\bALUA\b", "Aluar"),
    (r"\bADRs?\b", "adeérres"),
    (r"\bONs?\b", "obligaciones negociables"),
    (r"\bGD(\d{2})\b", r"ge de \1"),
    (r"\bAL(\d{2})\b", r"a ele \1"),
    (r"\bAE(\d{2})\b", r"a e \1"),
    # Dólares, tasas e instituciones
    (r"\bCCL\b", "contado con liqui"),
    (r"\bMEP\b", "mep"),
    (r"\bTNA\b", "tasa nominal anual"),
    (r"\bTEA\b", "tasa efectiva anual"),
    (r"\bTAMAR\b", "tamar"),
    (r"\bBADLAR\b", "badlar"),
    (r"\bLecaps?\b", "lecap"),
    (r"\bLECAPs?\b", "lecap"),
    (r"\bBoncaps?\b", "boncap"),
    (r"\bBCRA\b", "Banco Central"),
    (r"\bINDEC\b", "índec"),
    (r"\bIPC\b", "ipecé"),
    (r"\bPBI\b", "pebeí"),
    (r"\bPIB\b", "pebeí"),
    (r"\bFMI\b", "Fondo Monetario"),
    (r"\bFed\b", "fed"),
    (r"\bEE\.\s?UU\.(?=\s+[A-ZÁÉÍÓÚÑ]|\s*$)", "Estados Unidos."),
    (r"\bEE\.?\s?UU\.?", "Estados Unidos"),
    (r"\bUS\$\s?", "dólares "),
    (r"\bpb\b", "puntos básicos"),
    (r"\bbps\b", "puntos básicos"),
]


def adaptar(texto):
    for patron, reemplazo in REEMPLAZOS:
        texto = re.sub(patron, reemplazo, texto)
    return re.sub(r"\s{2,}", " ", texto).strip()
