"""
Morning Brief de mercados - versión 100% gratuita.
1) Datos duros gratis: Yahoo Finance, dolarapi, argentinadatos
2) Titulares gratis: Google News RSS
3) Guion: Gemini (plan gratuito de Google AI Studio) con búsqueda de Google
4) Voz: edge-tts (voces neuronales de Microsoft, acento argentino, sin clave)
5) Feed RSS en /docs (GitHub Pages)
"""
import os, re, json, html, time, asyncio, pathlib, datetime, urllib.parse
from zoneinfo import ZoneInfo

import requests
import feedparser
import edge_tts
from google import genai
from google.genai import types

# ---------------- Configuración ----------------
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime.datetime.now(TZ)
BASE_URL = os.environ["FEED_BASE_URL"].rstrip("/")
DOCS = pathlib.Path("docs")
EPIS = DOCS / "episodios"
MAX_EPISODIOS = 15
# Se prueban en orden: si uno está saturado o sin cupo, pasa al siguiente
MODELOS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
USAR_BUSQUEDA = False            # la búsqueda de Google no entra en el plan gratis
VOZ = "es-AR-TomasNeural"        # alternativa femenina: es-AR-ElenaNeural
VELOCIDAD = "+8%"                # más rápido o más lento: "+0%", "+15%"
PALABRAS_OBJETIVO = 1500         # ~9-10 minutos

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
FECHA_TXT = f"{DIAS[AHORA.weekday()]} {AHORA.day} de {MESES[AHORA.month-1]} de {AHORA.year}"

TICKERS = {
    "ES=F": "S&P 500 futuros", "NQ=F": "Nasdaq 100 futuros", "YM=F": "Dow Jones futuros",
    "^VIX": "VIX", "^TNX": "Tasa Treasury 10 años (%)", "DX-Y.NYB": "Índice dólar DXY",
    "CL=F": "Petróleo WTI", "BZ=F": "Petróleo Brent", "GC=F": "Oro", "BTC-USD": "Bitcoin",
    "^MERV": "Merval (último cierre)",
    "YPF": "ADR YPF", "GGAL": "ADR Galicia", "BMA": "ADR Macro", "PAM": "ADR Pampa",
    "VIST": "Vista", "TGS": "ADR TGS", "CEPU": "ADR Central Puerto", "MELI": "Mercado Libre",
}

# Panel líder del Merval y bonos en BYMA (variación de la última rueda)
PANEL_AR = ["GGAL", "YPFD", "PAMP", "BMA", "BBAR", "SUPV", "TXAR", "ALUA", "CEPU", "TGSU2",
            "TGNO4", "EDN", "TRAN", "LOMA", "CRES", "COME", "VALO", "BYMA", "METR", "TECO2",
            "MIRG", "CVH", "IRSA", "HARG"]
BONOS_AR = ["AL30", "GD30", "AL35", "GD35", "AE38", "GD38", "AL41", "GD41", "GD46"]

BUSQUEDAS_NOTICIAS = [
    ("Merval acciones cierre when:1d", "es-419", "AR"),
    ("mercados argentinos hoy when:1d", "es-419", "AR"),
    ("site:ambito.com finanzas when:1d", "es-419", "AR"),
    ("site:cronista.com finanzas-mercados when:1d", "es-419", "AR"),
    ("site:infobae.com economia when:1d", "es-419", "AR"),
    ("site:lanacion.com.ar economia when:1d", "es-419", "AR"),
    ("site:iprofesional.com finanzas when:1d", "es-419", "AR"),
    ("site:bloomberglinea.com argentina when:1d", "es-419", "AR"),
    ("Caputo ministro economía anuncio when:1d", "es-419", "AR"),
    ("Banco Central compró dólares reservas when:1d", "es-419", "AR"),
    ("inflación salarios actividad INDEC", "es-419", "AR"),
    ("FMI Argentina deuda pagos", "es-419", "AR"),
    ("bonos argentinos riesgo país", "es-419", "AR"),
    ("dólar MEP CCL BCRA reservas", "es-419", "AR"),
    ("caución tasas Lecap TAMAR", "es-419", "AR"),
    ("licitación Tesoro Secretaría de Finanzas", "es-419", "AR"),
    ("obligaciones negociables emisión licitación", "es-419", "AR"),
    ("INDEC dato hoy economía", "es-419", "AR"),
    ("agenda económica semana mercados", "es-419", "AR"),
    ("stock market futures Wall Street", "en-US", "US"),
    ("Fed Treasury yields", "en-US", "US"),
    ("economic calendar this week", "en-US", "US"),
    ("earnings today stocks", "en-US", "US"),
    ("bond sale emerging markets issuance", "en-US", "US"),
    ("Europe Asia markets today", "en-US", "US"),
]


# ---------------- 1. Datos duros ----------------
def datos_duros():
    datos = {}
    try:
        import yfinance as yf
        for t, nombre in TICKERS.items():
            try:
                h = yf.Ticker(t).history(period="5d", interval="1d")["Close"].dropna()
                if len(h) >= 2:
                    ult, prev = float(h.iloc[-1]), float(h.iloc[-2])
                    datos[nombre] = {"valor": round(ult, 2),
                                     "var_%": round((ult / prev - 1) * 100, 2)}
            except Exception:
                pass
    except Exception as e:
        datos["error_yfinance"] = str(e)

    try:
        r = requests.get("https://dolarapi.com/v1/dolares", timeout=15).json()
        datos["dolares_ARS"] = {d["nombre"]: {"compra": d.get("compra"), "venta": d.get("venta")}
                                for d in r}
    except Exception:
        pass

    try:
        datos["riesgo_pais"] = requests.get(
            "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo",
            timeout=15).json()
    except Exception:
        pass
    return datos


def variacion(ticker):
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="7d", interval="1d")["Close"].dropna()
    if len(h) >= 2:
        ult, prev = float(h.iloc[-1]), float(h.iloc[-2])
        return {"precio": round(ult, 2), "var_%": round((ult / prev - 1) * 100, 2)}
    return None


def datos_argentina():
    ar = {}
    # Acciones del panel líder y bonos en pesos (BYMA vía Yahoo)
    for grupo, lista in (("acciones_panel_lider_BYMA", PANEL_AR), ("bonos_soberanos_BYMA", BONOS_AR)):
        res = {}
        for t in lista:
            try:
                v = variacion(t + ".BA")
                if v:
                    res[t] = v
            except Exception:
                pass
        if res:
            ar[grupo] = dict(sorted(res.items(), key=lambda x: x[1]["var_%"], reverse=True))

    # Variables del BCRA: reservas, tasas, tipo de cambio mayorista
    try:
        import urllib3
        urllib3.disable_warnings()
        r = requests.get("https://api.bcra.gob.ar/estadisticas/v3.0/monetarias",
                         timeout=25, verify=False).json()
        claves = ("reservas", "badlar", "tamar", "mayorista", "base monetaria",
                  "plazo fijo", "política monetaria", "inflación", "cer", "uva")
        ar["bcra"] = [{"dato": v.get("descripcion"), "fecha": v.get("fecha"), "valor": v.get("valor")}
                      for v in r.get("results", [])
                      if any(c in (v.get("descripcion") or "").lower() for c in claves)][:25]
    except Exception:
        pass

    # Tasas de plazo fijo de los principales bancos
    try:
        pf = requests.get("https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo",
                          timeout=15).json()
        ar["plazo_fijo_bancos"] = [{"banco": b.get("entidad"), "tna_clientes": b.get("tnaClientes")}
                                   for b in pf][:8]
    except Exception:
        pass
    return ar


# ---------------- 2. Titulares (Google News RSS) ----------------
def titulares(max_por_busqueda=8, horas=36):
    limite = time.time() - horas * 3600
    salida = []
    for q, idioma, pais in BUSQUEDAS_NOTICIAS:
        tope = 10 if pais == "AR" else max_por_busqueda
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
               f"&hl={idioma}&gl={pais}&ceid={pais}:{idioma.split('-')[0]}")
        try:
            n = 0
            for e in feedparser.parse(url).entries:
                pub = e.get("published_parsed")
                if pub and time.mktime(pub) < limite:
                    continue
                salida.append(e.title)
                n += 1
                if n >= tope:
                    break
        except Exception:
            pass
    return list(dict.fromkeys(salida))  # sin duplicados


# ---------------- 3. Guion con Gemini ----------------
SISTEMA = f"""Sos el conductor de un podcast matinal de mercados para un gerente comercial
de un agente productor argentino. Hablás en español rioplatense, tono radial, claro y ágil.
El texto va a ser leído por una voz sintética: NO uses markdown, viñetas, tablas ni símbolos.
Escribí los números como se dicen ("cero coma ocho por ciento", "mil doscientos puntos básicos").
Largo: entre {PALABRAS_OBJETIVO} y {PALABRAS_OBJETIVO + 200} palabras, nunca menos. La mitad del
episodio tiene que ser sobre Argentina. Nunca inventes datos: si algo no lo pudiste
confirmar, decilo o omitilo. Priorizá lo que un asesor financiero necesita saber antes de la rueda."""

PEDIDO = """Hoy es {fecha}. Armá el episodio de hoy.

Datos de mercado ya relevados (fuente principal para las cifras):
{datos}

Titulares de las últimas horas:
{titulares}

Con los datos y titulares de arriba (y la búsqueda de Google si está disponible), cubrí:
- Internacional: cómo cerró Wall Street ayer, cómo operan Asia y Europa hoy, noticias financieras
  y macro relevantes (EE.UU., Europa, China, Brasil, commodities), Fed y Treasuries.
- Argentina, RUEDA DE AYER (último día hábil): cierre del Merval en pesos y en dólares, acciones
  líderes que más subieron y bajaron, ADRs en Wall Street, bonos soberanos (Globales y Bonares),
  riesgo país, dólar oficial, MEP y CCL, tasas de caución, TAMAR/BADLAR y Lecaps, volumen operado,
  compras o ventas de dólares del BCRA y variación de reservas, y las noticias que explicaron el día.
- Argentina, AGENDA DE HOY: datos que publica el INDEC o el BCRA, licitaciones del Tesoro,
  obligaciones negociables que licitan o se emiten hoy, vencimientos o pagos de bonos, balances,
  anuncios oficiales o eventos políticos previstos.
- Internacional, AGENDA DE HOY: datos macro, discursos de la Fed, subastas del Tesoro de EE.UU.,
  emisiones soberanas y corporativas relevantes (incluidas de emergentes), balances importantes.

Estructura del episodio:
1. Saludo breve con la fecha y los tres titulares del día.
2. Apertura global: futuros de EE.UU., Asia, Europa, dólar, petróleo, oro, Treasuries.
3. Lo más importante del mundo.
4. Argentina, cómo cerró ayer (bloque largo, el más importante del episodio):
   - Merval y panel líder: nombrá las 3 o 4 acciones que más subieron y las que más bajaron
     con su variación, y explicá por qué si los titulares lo permiten.
   - ADRs en Wall Street, destacando los movimientos más fuertes.
   - Bonos soberanos (Bonares y Globales) y riesgo país.
   - Dólar oficial, mayorista, MEP y CCL, y la brecha.
   - Tasas: caución, TAMAR/BADLAR, plazo fijo, Lecaps.
   - BCRA: compras o ventas de dólares y reservas.
   - Las 3 o 4 noticias locales más importantes (gobierno, economía, empresas, FMI), cada una
     con contexto y por qué le importa al mercado.
5. Argentina, qué trae hoy: agenda local, datos del INDEC o BCRA, licitaciones, ONs y emisiones,
   y qué esperar para la rueda.
6. Agenda internacional del día: datos, emisiones y eventos.
7. Cierre: "qué mirar hoy" en tres puntos y despedida corta. Mantené siempre este cierre
   con el mismo estilo: tres puntos concretos y accionables para la jornada.

Devolvé SOLO el guion final entre las etiquetas <guion> y </guion>."""


def escribir_guion(datos, heads):
    client = genai.Client()  # usa la variable GEMINI_API_KEY
    pedido = PEDIDO.format(fecha=FECHA_TXT,
                           datos=json.dumps(datos, ensure_ascii=False, indent=1),
                           titulares="\n".join(f"- {t}" for t in heads) or "(sin titulares)")
    herramientas = [types.Tool(google_search=types.GoogleSearch())] if USAR_BUSQUEDA else None
    texto = ""
    for modelo in MODELOS:
        for intento in range(3):  # reintenta si el modelo está saturado
            try:
                config = types.GenerateContentConfig(system_instruction=SISTEMA,
                                                     tools=herramientas)
                texto = client.models.generate_content(model=modelo, contents=pedido,
                                                       config=config).text or ""
                if texto.strip():
                    print(f"Guion generado con {modelo}")
                    break
            except Exception as e:
                print(f"Aviso Gemini ({modelo}, intento {intento + 1}):", str(e)[:300])
                if "429" in str(e) or "404" in str(e):
                    break  # sin cupo o no disponible: pasar al siguiente modelo
                time.sleep(30)
        if texto.strip():
            break

    m = re.search(r"<guion>(.*?)</guion>", texto, re.S)
    guion = (m.group(1) if m else texto).strip()
    guion = re.sub(r"\[\d+(,\s*\d+)*\]", "", guion)  # saca marcas de citas
    return re.sub(r"[*#_`>]", "", guion)


# ---------------- 4. Audio con edge-tts ----------------
def generar_audio(guion, destino):
    asyncio.run(edge_tts.Communicate(guion, VOZ, rate=VELOCIDAD).save(str(destino)))


# ---------------- 5. Feed RSS ----------------
def actualizar_feed(nuevo):
    indice = DOCS / "episodios.json"
    lista = json.loads(indice.read_text()) if indice.exists() else []
    lista = [e for e in lista if e["archivo"] != nuevo["archivo"]]
    lista.insert(0, nuevo)
    for viejo in lista[MAX_EPISODIOS:]:
        (EPIS / viejo["archivo"]).unlink(missing_ok=True)
        (EPIS / viejo["archivo"].replace(".mp3", ".txt")).unlink(missing_ok=True)
    lista = lista[:MAX_EPISODIOS]
    indice.write_text(json.dumps(lista, ensure_ascii=False, indent=1))

    items = ""
    for e in lista:
        url = f"{BASE_URL}/episodios/{e['archivo']}"
        items += f"""
  <item>
    <title>{html.escape(e['titulo'])}</title>
    <description>{html.escape(e['resumen'])}</description>
    <enclosure url="{url}" length="{e['bytes']}" type="audio/mpeg"/>
    <guid>{url}</guid>
    <pubDate>{e['fecha_rfc']}</pubDate>
    <itunes:duration>{e['duracion']}</itunes:duration>
  </item>"""

    (DOCS / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Morning Brief de Mercados</title>
  <link>{BASE_URL}</link>
  <language>es-ar</language>
  <description>Resumen diario de mercados argentinos e internacionales.</description>
  <itunes:author>Morning Brief</itunes:author>
  <itunes:block>Yes</itunes:block>{items}
</channel>
</rss>""", encoding="utf-8")


# ---------------- Main ----------------
def main():
    EPIS.mkdir(parents=True, exist_ok=True)
    datos = datos_duros()
    datos["argentina"] = datos_argentina()
    guion = escribir_guion(datos, titulares())
    if len(guion.split()) < 200:
        raise SystemExit("El guion salió vacío o muy corto; no se publica el episodio.")

    archivo = f"brief-{AHORA:%Y-%m-%d}.mp3"
    generar_audio(guion, EPIS / archivo)
    (EPIS / archivo.replace(".mp3", ".txt")).write_text(guion, encoding="utf-8")

    minutos = len(guion.split()) / 150
    actualizar_feed({
        "archivo": archivo,
        "titulo": f"Morning Brief - {FECHA_TXT.capitalize()}",
        "resumen": guion[:300] + "...",
        "bytes": (EPIS / archivo).stat().st_size,
        "fecha_rfc": AHORA.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "duracion": f"{int(minutos):02d}:{int((minutos % 1) * 60):02d}",
    })
    print(f"Listo: {archivo} (~{minutos:.1f} min)")


if __name__ == "__main__":
    main()
