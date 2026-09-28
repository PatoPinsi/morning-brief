"""
Resumen Semanal - Toros Capital (viernes).
Genera el Panel Semanal (imagen), un audio corto (máx. ~4 min) y una página web con ambos.
Guarda lo que se anticipa para la semana siguiente y el viernes siguiente lo compara con lo que pasó.
El envío por mail lo hace enviar_mail.py.
"""
import os, re, json, html, time, asyncio, pathlib, datetime, urllib.parse
from zoneinfo import ZoneInfo

import requests
import feedparser
import edge_tts
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

# ================= Configuración =================
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
# FECHA_REPORTE (AAAA-MM-DD) permite generar el reporte de un viernes anterior; vacío = hoy
_FECHA = os.environ.get("FECHA_REPORTE", "").strip()
if _FECHA:
    HOY = datetime.date.fromisoformat(_FECHA)
    AHORA = datetime.datetime.combine(HOY, datetime.time(17, 30), TZ)
else:
    AHORA = datetime.datetime.now(TZ)
    HOY = AHORA.date()
LUNES = HOY - datetime.timedelta(days=HOY.weekday())
BASE_URL = os.environ["FEED_BASE_URL"].rstrip("/") + "/semanal"
CARPETA = pathlib.Path("docs") / "semanal"
MAX_EDICIONES = 26

MODELOS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
VOZ = "es-AR-TomasNeural"
VELOCIDAD = "+10%"
PALABRAS_MIN, PALABRAS_MAX = 380, 500      # ~3 a 3,5 minutos

# Canastas (vencimientos en la nota al pie del panel)
SOB_CORTO = ["AO27", "GD29", "AL29", "AN29", "GD30", "AL30"]            # 2027-2030
SOB_LARGO = ["GD35", "AL35", "GD38", "AE38", "GD41", "AL41", "GD46"]    # 2035-2046
ON_CORTO = ["VSCY", "TTC8"]                                             # 2026-2028
ON_LARGO = ["YMC1", "YMCI", "YM43", "YM39", "YMCU", "YMCX", "MGCT",
            "MGCM", "VSCZ", "TTCE", "TTCD", "PLC6"]                     # 2029-2031
ADRS = ["YPF", "GGAL", "BMA", "PAM", "VIST", "TGS", "CEPU", "SUPV",
        "BBAR", "CRESY", "EDN", "LOMA", "TEO", "IRS"]

NOTAS_PIE = [
    "Renta fija, corto y largo según vencimiento: Soberanos HD (Globales y Bonares) corto 2027-2030, largo 2035-2046.",
    "ON AAA (YPF, Pampa, Vista, Tecpetrol y Pluspetrol) corto 2026-2028, largo 2029-2031.",
    "La información es orientativa y no constituye una recomendación de inversión.",
]

# Colores del panel
FONDO = (16, 34, 63)
CARD = (28, 59, 103)
DORADO = (212, 170, 60)
GRIS = (170, 186, 208)
VERDE = (92, 214, 140)
ROJO = (255, 110, 110)

BUSQUEDAS = [
    ("Merval acciones semana when:7d", "es-419", "AR"),
    ("bonos argentinos riesgo país when:7d", "es-419", "AR"),
    ("dólar MEP CCL blue when:7d", "es-419", "AR"),
    ("caución tasa 7 días when:7d", "es-419", "AR"),
    ("BCRA reservas compras when:7d", "es-419", "AR"),
    ("licitación Tesoro Secretaría de Finanzas when:7d", "es-419", "AR"),
    ("obligaciones negociables emisión when:7d", "es-419", "AR"),
    ("INDEC inflación actividad when:7d", "es-419", "AR"),
    ("Caputo Milei economía when:7d", "es-419", "AR"),
    ("site:ambito.com finanzas when:7d", "es-419", "AR"),
    ("site:cronista.com finanzas-mercados when:7d", "es-419", "AR"),
    ("site:infobae.com economia when:7d", "es-419", "AR"),
    ("agenda económica próxima semana", "es-419", "AR"),
    ("Wall Street week stocks when:7d", "en-US", "US"),
    ("Federal Reserve rates Treasury when:7d", "en-US", "US"),
    ("oil prices week when:7d", "en-US", "US"),
    ("economic calendar next week", "en-US", "US"),
]


# ================= 1. Datos =================
def historia(ticker):
    import yfinance as yf
    h = yf.Ticker(ticker).history(period="3mo", interval="1d")["Close"].dropna()
    h = h[[d.date() <= HOY for d in h.index]]
    if h.empty:
        return None
    fechas = [d.date() for d in h.index]
    previos = [i for i, d in enumerate(fechas) if d < LUNES]
    if not previos or fechas[-1] < LUNES:
        return None
    return float(h.iloc[-1]), float(h.iloc[previos[-1]])


def precio_y_var(ticker):
    try:
        r = historia(ticker)
        if r:
            ult, base = r
            return ult, round((ult / base - 1) * 100, 2)
    except Exception:
        pass
    return None, None


def var(ticker):
    return precio_y_var(ticker)[1]


def promedio(valores):
    v = [x for x in valores if x is not None]
    return round(sum(v) / len(v), 2) if v else None


DATA912 = "https://data912.com"
TODOS_RF = SOB_CORTO + SOB_LARGO + ON_CORTO + ON_LARGO


def var_data912(ticker):
    """Variación semanal con la serie histórica de data912 (bonos y ON)."""
    try:
        r = requests.get(f"{DATA912}/historical/bonds/{ticker}", timeout=20)
        if r.status_code != 200:
            return None
        filas = []
        for x in r.json():
            f = str(x.get("date") or x.get("fecha") or "")[:10]
            c = x.get("c") or x.get("close")
            if f and c:
                filas.append((f, float(c)))
        filas = sorted(t for t in filas if t[0] <= HOY.isoformat())
        prev = [t for t in filas if t[0] < LUNES.isoformat()]
        if not prev or filas[-1][0] < LUNES.isoformat():
            return None
        return round((filas[-1][1] / prev[-1][1] - 1) * 100, 2)
    except Exception:
        return None


def precios_en_vivo():
    """Último precio de bonos y ON en dólares MEP (panel en vivo de data912)."""
    precios = {}
    for panel in ("arg_bonds", "arg_corp"):
        try:
            for x in requests.get(f"{DATA912}/live/{panel}", timeout=20).json():
                sym, c = x.get("symbol"), x.get("c") or x.get("px_bid")
                if sym and c and sym.endswith("D") and sym[:-1] in TODOS_RF:
                    precios[sym] = float(c)
        except Exception:
            pass
    return precios


def fotos_semanales(precios_hoy):
    """Guarda la foto de precios de esta semana y devuelve la del viernes anterior."""
    archivo = CARPETA / "precios_semanales.json"
    fotos = json.loads(archivo.read_text()) if archivo.exists() else []
    anteriores = [f for f in fotos if f["semana"] < LUNES.isoformat()]
    if precios_hoy and not _FECHA:
        fotos = [f for f in fotos if f["semana"] != HOY.isoformat()]
        fotos.append({"semana": HOY.isoformat(), "precios": precios_hoy})
        archivo.write_text(json.dumps(fotos[-12:], ensure_ascii=False, indent=1))
    return anteriores[-1]["precios"] if anteriores else {}


def var_en_dolares(especie, mep_var, foto_hoy, foto_ant):
    v = var_data912(especie + "D")
    if v is None:
        vp = var_data912(especie)
        if vp is not None and mep_var is not None:
            v = round(((1 + vp / 100) / (1 + mep_var / 100) - 1) * 100, 2)
    if v is None and not _FECHA:
        hoy, ant = foto_hoy.get(especie + "D"), foto_ant.get(especie + "D")
        if hoy and ant:
            v = round((hoy / ant - 1) * 100, 2)
    return v


def dolar(casa):
    try:
        hist = requests.get(f"https://api.argentinadatos.com/v1/cotizaciones/dolares/{casa}",
                            timeout=20).json()
        hist = sorted([x for x in hist if x["fecha"] <= HOY.isoformat()], key=lambda x: x["fecha"])
        ult = hist[-1]
        previos = [x for x in hist if x["fecha"] < LUNES.isoformat()]
        v = (round((ult["venta"] / previos[-1]["venta"] - 1) * 100, 2)
             if previos and ult["fecha"] >= LUNES.isoformat() else None)
        return ult["venta"], v
    except Exception:
        return None, None


def bcra():
    salida = {"reservas": None, "var_reservas": None, "tamar": None}
    try:
        import urllib3
        urllib3.disable_warnings()
        base = "https://api.bcra.gob.ar/estadisticas/v3.0/monetarias"
        lista = requests.get(base, timeout=25, verify=False).json().get("results", [])
        id_res = next((v["idVariable"] for v in lista
                       if "reservas internacionales" in (v.get("descripcion") or "").lower()), 1)
        tamar = next((v for v in lista if "tamar" in (v.get("descripcion") or "").lower()), None)
        if tamar and tamar.get("valor") is not None:
            salida["tamar"] = f"{float(tamar['valor']):.1f}%".replace(".", ",")
        desde = (LUNES - datetime.timedelta(days=14)).isoformat()
        serie = requests.get(f"{base}/{id_res}?desde={desde}&hasta={HOY.isoformat()}",
                             timeout=25, verify=False).json().get("results", [])
        if serie and "detalle" in serie[0]:
            serie = serie[0]["detalle"]
        serie = sorted(serie, key=lambda x: x["fecha"])
        if serie:
            ult = serie[-1]["valor"]
            prev = [x for x in serie if x["fecha"] < LUNES.isoformat()]
            salida["reservas"] = ult
            salida["var_reservas"] = ult - prev[-1]["valor"] if prev else None
    except Exception as e:
        print("Aviso BCRA:", e)
    return salida


def plazo_fijo():
    try:
        pf = requests.get("https://api.argentinadatos.com/v1/finanzas/tasas/plazoFijo", timeout=20).json()
        tasas = [b["tnaClientes"] for b in pf if b.get("tnaClientes")]
        tasas = [t * 100 if t < 1 else t for t in tasas][:10]
        return f"{sum(tasas) / len(tasas):.1f}%".replace(".", ",") if tasas else None
    except Exception:
        return None


def riesgo_pais():
    try:
        r = requests.get("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", timeout=20).json()
        r = sorted([x for x in r if x["fecha"] <= HOY.isoformat()], key=lambda x: x["fecha"])
        prev = [x for x in r if x["fecha"] < LUNES.isoformat()]
        actual = r[-1]["valor"]
        v = round((actual / prev[-1]["valor"] - 1) * 100, 2) if prev else None
        return {"valor": actual, "var": v}
    except Exception:
        return {"valor": None, "var": None}


def datos_semana():
    dol = {n: dolar(c) for n, c in (("Mayorista", "mayorista"), ("Oficial", "oficial"),
                                     ("Blue", "blue"), ("MEP", "bolsa"), ("CCL", "contadoconliqui"))}
    mep_var, ccl_var = dol["MEP"][1], dol["CCL"][1]
    merval = var("^MERV")
    merval_usd = (round(((1 + merval / 100) / (1 + ccl_var / 100) - 1) * 100, 2)
                  if merval is not None and ccl_var is not None else None)
    b = bcra()
    foto_hoy = {} if _FECHA else precios_en_vivo()
    foto_ant = fotos_semanales(foto_hoy)

    def canasta(lista):
        return promedio([var_en_dolares(t, mep_var, foto_hoy, foto_ant) for t in lista])

    btc, eth = precio_y_var("BTC-USD"), precio_y_var("ETH-USD")
    wti, brent = precio_y_var("CL=F"), precio_y_var("BZ=F")
    return {
        "dolar": [(n, p, v) for n, (p, v) in dol.items()],
        "mercados": [("Merval (ARS)", merval), ("Merval (USD)", merval_usd),
                     ("ADRs", promedio([var(t) for t in ADRS]))],
        "riesgo_pais": riesgo_pais(),
        "bcra": {"reservas": b["reservas"], "var_reservas": b["var_reservas"],
                 "caucion": None, "tamar": b["tamar"], "plazo_fijo": plazo_fijo()},
        "renta_fija": [
            ("Soberanos HD corto", canasta(SOB_CORTO)),
            ("Soberanos HD largo", canasta(SOB_LARGO)),
            ("ON AAA corto", canasta(ON_CORTO)),
            ("ON AAA largo", canasta(ON_LARGO)),
        ],
        "wall_street": [("Dow Jones", var("^DJI")), ("S&P 500", var("^GSPC")), ("Nasdaq", var("^IXIC"))],
        "emergentes": [("Brasil", var("EWZ"), "ETF EWZ"), ("China", var("MCHI"), "ETF MCHI")],
        "cripto": [("BTC", btc[1], f"US${num(btc[0])}"), ("ETH", eth[1], f"US${num(eth[0])}")],
        "petroleo": [("WTI", wti[1], f"US${num(wti[0], 1)}"), ("Brent", brent[1], f"US${num(brent[0], 1)}")],
    }


def titulares_noticias():
    salida = []
    rango = (f"after:{(LUNES - datetime.timedelta(days=2)).isoformat()} "
             f"before:{(HOY + datetime.timedelta(days=1)).isoformat()}")
    for q, idioma, pais in BUSQUEDAS:
        q = q.replace("when:7d", rango)
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
               f"&hl={idioma}&gl={pais}&ceid={pais}:{idioma.split('-')[0]}")
        try:
            salida += [e.title for e in feedparser.parse(url).entries[:10]]
        except Exception:
            pass
    return list(dict.fromkeys(salida))


# ================= 2. Contenido con Gemini =================
PEDIDO = """Sos el analista de Toros Capital, agente productor argentino, y preparás el cierre semanal
para la comunidad de inversores. Hoy es viernes {fecha}; la semana va desde el lunes {lunes}.

Datos de la semana (variaciones % semanales; usalos como fuente de las cifras):
{datos}

Titulares de la semana:
{titulares}

Lo que anticipamos el viernes pasado para esta semana:
{previos}

Devolvé SOLO un JSON válido:
{{
 "titulares": ["5 titulares de la semana, estilo diario financiero, máximo 65 caracteres cada uno,
               mezclando Argentina e internacional, del más al menos relevante"],
 "caucion_7d_tna": "tasa de caución a 7 días (TNA) si figura en los titulares, ej. '20,3%'; si no, null",
 "evaluacion": [{{"tema": "...", "expectativa": "...", "resultado": "Se cumplió" | "Se cumplió parcialmente" |
                 "No se cumplió" | "Sin datos suficientes", "comentario": "una oración"}}],
 "proxima_semana": [{{"tema": "...", "expectativa": "concreta y verificable el viernes que viene"}}],
 "guion": "texto para leer en voz alta"
}}

Reglas:
- "evaluacion": una entrada por cada punto anticipado; si no hubo, lista vacía.
- "proxima_semana": entre 3 y 5 puntos.
- Nunca inventes números: si un dato no está, no lo menciones.
- "guion": ENTRE {pmin} Y {pmax} PALABRAS, NUNCA MÁS. Español rioplatense, frases cortas, ritmo ágil y
  con punch, como un cierre radial. Sin símbolos ni markdown; números escritos como se dicen y
  redondeados. Estructura:
  1. Apertura de Toros Capital en una frase con gancho.
  2. Los temas que marcaron la semana, rápido y al grano (los 5 titulares, una o dos frases cada uno).
  3. Los números clave en tres o cuatro frases: dólar, riesgo país, Merval y bonos.
  4. Si hubo pronósticos: en una o dos frases, qué anticipamos y si se cumplió.
  5. Lo que se viene la próxima semana.
  6. Cierre: tres puntos concretos para tener en el radar y despedida corta."""


def generar_contenido(datos, heads, previos):
    client = genai.Client()
    pedido = PEDIDO.format(
        fecha=HOY.strftime("%d/%m/%Y"), lunes=LUNES.strftime("%d/%m/%Y"),
        datos=json.dumps(datos, ensure_ascii=False, indent=1),
        titulares="\n".join(f"- {t}" for t in heads) or "(sin titulares)",
        previos=json.dumps(previos, ensure_ascii=False, indent=1) if previos else "(ninguno)",
        pmin=PALABRAS_MIN, pmax=PALABRAS_MAX)
    config = types.GenerateContentConfig(response_mime_type="application/json")
    # Si los modelos están saturados, reintenta durante ~12 minutos antes de rendirse
    for ronda, espera in enumerate((0, 60, 120, 240, 300)):
        time.sleep(espera)
        for modelo in MODELOS:
            try:
                texto = client.models.generate_content(model=modelo, contents=pedido,
                                                       config=config).text or ""
                c = json.loads(texto[texto.index("{"): texto.rindex("}") + 1])
                palabras = len(c.get("guion", "").split())
                if palabras > 150:
                    print(f"Contenido generado con {modelo} ({palabras} palabras)")
                    return c
            except Exception as e:
                print(f"Aviso Gemini ({modelo}, ronda {ronda + 1}):", str(e)[:200])
    print("Gemini no respondió: se genera la versión básica.")
    return contenido_basico(datos, heads)


def _mov(v, sujeto, plural=False):
    if v is None:
        return ""
    if abs(v) < 0.05:
        return f"{sujeto} {'quedaron' if plural else 'quedó'} sin cambios. "
    verbo = ("subieron" if v > 0 else "bajaron") if plural else ("subió" if v > 0 else "bajó")
    return f"{sujeto} {verbo} {abs(v):.1f} por ciento. ".replace(".", ",", 1)


def contenido_basico(d, heads):
    """Plan B si la IA no responde: titulares de las noticias y un audio corto armado con los datos."""
    tits = []
    for t in heads:
        t = t.rsplit(" - ", 1)[0].strip()
        if 15 < len(t) <= 75 and t not in tits:
            tits.append(t)
        if len(tits) == 5:
            break
    dol = {n: v for n, _, v in d["dolar"]}
    merc = dict(d["mercados"])
    rf = dict(d["renta_fija"])
    ws = {n: v for n, v in d["wall_street"]}
    rp = d["riesgo_pais"]["valor"]
    guion = ("Hola, este es el resumen semanal de Toros Capital. Vamos con los números de la semana. "
             + _mov(dol.get("MEP"), "El dólar MEP") + _mov(dol.get("CCL"), "El contado con liqui")
             + (f"El riesgo país cerró en {int(rp)} puntos básicos. " if rp else "")
             + _mov(merc.get("Merval (USD)"), "El Merval en dólares")
             + _mov(rf.get("Soberanos HD corto"), "Los soberanos cortos", True)
             + _mov(rf.get("Soberanos HD largo"), "Los soberanos largos", True)
             + _mov(ws.get("S&P 500"), "En Wall Street, el S&P 500")
             + ("Los temas que marcaron la semana: " + ". ".join(tits[:3]) + ". " if tits else "")
             + "Todo el detalle está en el panel semanal. Buen fin de semana.")
    return {"titulares": tits, "caucion_7d_tna": None, "evaluacion": [], "proxima_semana": [],
            "guion": guion, "basico": True}


def recortar_guion(guion, maximo=560):
    """Red de seguridad para que el audio nunca pase los 4 minutos."""
    palabras = guion.split()
    if len(palabras) <= maximo:
        return guion
    corte = " ".join(palabras[:maximo])
    return corte[: corte.rfind(".") + 1] if "." in corte else corte


# ================= 3. Formatos =================
def pct(v, dec=1):
    return "s/d" if v is None else f"{v:+.{dec}f}%".replace(".", ",")


def num(v, dec=0):
    if v is None:
        return "s/d"
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def color(v):
    return "white" if v is None else VERDE if v > 0 else ROJO if v < 0 else GRIS


# ================= 4. Panel semanal (imagen) =================
def fuente(nombre, tamanio):
    for ruta in (nombre, f"/tmp/{nombre}"):
        if os.path.exists(ruta):
            return ImageFont.truetype(ruta, tamanio)
    try:
        r = requests.get(f"https://github.com/google/fonts/raw/main/ofl/poppins/{nombre}", timeout=20)
        pathlib.Path(f"/tmp/{nombre}").write_bytes(r.content)
        return ImageFont.truetype(f"/tmp/{nombre}", tamanio)
    except Exception:
        return ImageFont.load_default()


def dibujar_panel(p, destino):
    W = 1600
    img = Image.new("RGB", (W, 2200), FONDO)
    dr = ImageDraw.Draw(img)
    F = fuente
    fT, fSub, fSec = F("Poppins-Bold.ttf", 64), F("Poppins-Medium.ttf", 28), F("Poppins-Bold.ttf", 38)
    fL, fV, fS = F("Poppins-Medium.ttf", 32), F("Poppins-Bold.ttf", 32), F("Poppins-Medium.ttf", 22)
    fBig, fVar, fN = F("Poppins-Bold.ttf", 46), F("Poppins-Bold.ttf", 42), F("Poppins-Medium.ttf", 20)

    def card(x, y, w, h):
        dr.rounded_rectangle((x, y, x + w, y + h), radius=22, fill=CARD)

    def titulo(t, x, y):
        dr.rectangle((x, y + 10, x + 7, y + 44), fill=DORADO)
        dr.text((x + 20, y), t, font=fSec, fill=DORADO)

    def fila(x, y, w, nombre, valor, v, sub=None):
        dr.text((x, y), nombre, font=fL, fill="white")
        if valor:
            dr.text((x + w * 0.68 - dr.textlength(valor, font=fV), y), valor, font=fV, fill="white")
        t = pct(v)
        dr.text((x + w - dr.textlength(t, font=fV), y), t, font=fV, fill=color(v))
        if sub:
            dr.text((x + w - dr.textlength(sub, font=fS), y + 38), sub, font=fS, fill=GRIS)

    M, G = 36, 28
    # Encabezado
    card(M, 30, W - 2 * M, 160)
    if os.path.exists("logo.png"):
        logo = Image.open("logo.png").convert("RGB")
        logo.thumbnail((230, 125))
        img.paste(logo, (M + 30, 30 + (160 - logo.height) // 2))
        x0 = M + 30 + logo.width + 40
    else:
        x0 = M + 40
    dr.line((x0 - 20, 60, x0 - 20, 160), fill=DORADO, width=3)
    dr.text((x0, 52), "PANEL SEMANAL", font=fT, fill="white")
    rango = f"SEMANA DEL {LUNES.strftime('%d/%m')} AL {HOY.strftime('%d/%m')}"
    dr.text((x0, 128), "RESUMEN DE MERCADOS · " + rango, font=fSub, fill=GRIS)
    fecha = HOY.strftime("%d.%m.%Y")
    dr.text((W - M - 30 - dr.textlength(fecha, font=fSec), 78), fecha, font=fSec, fill=DORADO)

    # Fila 1: Dólar | Acciones | BCRA y tasas
    y = 220
    w3 = (W - 2 * M - 2 * G) // 3
    xs = [M, M + w3 + G, M + 2 * (w3 + G)]
    hc = 340
    for x, t in zip(xs, ("Dólar", "Acciones", "BCRA y tasas")):
        titulo(t, x, y)
    yc = y + 62
    for x in xs:
        card(x, yc, w3, hc)
    pad, ww = 26, w3 - 52
    yy = yc + 28
    for n, precio, v in p["dolar"]:
        fila(xs[0] + pad, yy, ww, n, "$" + num(precio), v)
        yy += 62
    yy = yc + 24
    for n, v in p["mercados"]:
        fila(xs[1] + pad, yy, ww, n, None, v)
        yy += 52
    yy += 4
    rp = p["riesgo_pais"]
    dr.text((xs[1] + pad, yy), "Riesgo País", font=fL, fill="white")
    val = f"{num(rp['valor'])} pb"
    dr.text((xs[1] + pad + ww - dr.textlength(val, font=fV), yy), val, font=fV, fill="white")
    if rp["var"] is not None:
        t = pct(rp["var"]) + " en la semana"
        dr.text((xs[1] + pad + ww - dr.textlength(t, font=fS), yy + 40), t, font=fS, fill=color(-rp["var"]))

    b = p["bcra"]
    x = xs[2] + pad
    dr.text((x, yc + 22), "Reservas brutas", font=fS, fill=GRIS)
    dr.text((x, yc + 48), f"US${num(b['reservas'])} M", font=fBig, fill="white")
    vr = b["var_reservas"]
    if vr is not None:
        signo = "+" if vr >= 0 else "-"
        dr.text((x, yc + 108), f"{signo}US${num(abs(vr))} M en la semana", font=fS,
                fill=VERDE if vr >= 0 else ROJO)
    dr.line((x, yc + 158, x + ww, yc + 158), fill=GRIS, width=1)
    yy = yc + 178
    for n, v in (("Caución 7d (TNA)", b["caucion"]), ("TAMAR (TNA)", b["tamar"]),
                 ("Plazo fijo (TNA)", b["plazo_fijo"])):
        dr.text((x, yy), n, font=fL, fill="white")
        dr.text((x + ww - dr.textlength(v or "s/d", font=fV), yy), v or "s/d", font=fV, fill="white")
        yy += 50

    # Renta fija: franja compacta
    y = yc + hc + 36
    titulo("Renta fija en dólares", M, y)
    ycr = y + 62
    wr, hr = W - 2 * M, 124
    card(M, ycr, wr, hr)
    wcel = wr / 4
    for i, (nombre, v) in enumerate(p["renta_fija"]):
        cx = M + i * wcel
        if i:
            dr.line((cx, ycr + 22, cx, ycr + hr - 22), fill=GRIS, width=1)
        dr.text((cx + (wcel - dr.textlength(nombre, font=fS)) / 2, ycr + 20), nombre, font=fS, fill=GRIS)
        t = pct(v)
        dr.text((cx + (wcel - dr.textlength(t, font=fVar)) / 2, ycr + 52), t, font=fVar, fill=color(v))

    # Fila 2: Wall Street | Emergentes | Cripto | Petróleo
    y = ycr + hr + 36
    w4 = (W - 2 * M - 3 * G) // 4
    xs4 = [M + i * (w4 + G) for i in range(4)]
    for x, t in zip(xs4, ("Wall Street", "Emergentes", "Cripto", "Petróleo")):
        titulo(t, x, y)
    yc2, hc2 = y + 62, 220
    for x in xs4:
        card(x, yc2, w4, hc2)
    for i, clave in enumerate(("wall_street", "emergentes", "cripto", "petroleo")):
        yy = yc2 + 26
        filas = p[clave]
        paso = 62 if len(filas) == 3 else 88
        for f in filas:
            fila(xs4[i] + 26, yy, w4 - 52, f[0], None, f[1], f[2] if len(f) > 2 else None)
            yy += paso

    # Titulares
    y = yc2 + hc2 + 36
    titulo("Titulares de la semana", M, y)
    yc3 = y + 62
    card(M, yc3, W - 2 * M, 5 * 52 + 44)
    yy = yc3 + 26
    for i, t in enumerate(p["titulares"][:5]):
        dr.text((M + 30, yy), f"#{i + 1}", font=fV, fill=DORADO)
        dr.text((M + 100, yy), t, font=fL, fill="white")
        yy += 52
    for k, n in enumerate(NOTAS_PIE):
        dr.text((M + 6, yc3 + 5 * 52 + 58 + k * 28), n, font=fN, fill=GRIS)
    img.crop((0, 0, W, yc3 + 5 * 52 + 44 + 124)).save(destino)


# ================= 6. Pronósticos, audio y publicación =================
def cargar_pronosticos():
    a = CARPETA / "pronosticos.json"
    return json.loads(a.read_text()) if a.exists() else []


def guardar_pronosticos(lista, items):
    lista = [x for x in lista if x["semana"] != HOY.isoformat()]
    lista.append({"semana": HOY.isoformat(), "items": items})
    (CARPETA / "pronosticos.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1))


def generar_audio(guion, destino):
    asyncio.run(edge_tts.Communicate(guion, VOZ, rate=VELOCIDAD).save(str(destino)))


def publicar(ed):
    indice = CARPETA / "ediciones.json"
    lista = json.loads(indice.read_text()) if indice.exists() else []
    lista = [e for e in lista if e["fecha"] != ed["fecha"]]
    lista.insert(0, ed)
    for vieja in lista[MAX_EDICIONES:]:
        for sufijo in (".mp3", ".png"):
            (CARPETA / f"panel-{vieja['fecha']}{sufijo}").unlink(missing_ok=True)
    lista = lista[:MAX_EDICIONES]
    indice.write_text(json.dumps(lista, ensure_ascii=False, indent=1))

    items = "".join(f"""
  <item>
    <title>{html.escape(e['titulo'])}</title>
    <description>{html.escape(e['resumen'])}</description>
    <enclosure url="{BASE_URL}/panel-{e['fecha']}.mp3" length="{e['bytes']}" type="audio/mpeg"/>
    <guid>{BASE_URL}/panel-{e['fecha']}.mp3</guid>
    <pubDate>{e['fecha_rfc']}</pubDate>
  </item>""" for e in lista)
    (CARPETA / "feed.xml").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Resumen Semanal - Toros Capital</title>
  <link>{BASE_URL}</link>
  <language>es-ar</language>
  <description>Cierre semanal de mercados de Toros Capital.</description>
  <itunes:block>Yes</itunes:block>{items}
</channel>
</rss>""", encoding="utf-8")

    f = ed["fecha"]
    ant = "".join(f'<li>{e["fecha"]}: <a href="panel-{e["fecha"]}.png">panel</a> · '
                  f'<a href="panel-{e["fecha"]}.mp3">audio</a></li>' for e in lista[1:])
    (CARPETA / "index.html").write_text(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Panel Semanal - Toros Capital</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:auto;padding:16px;color:#1c3b67}}
img{{max-width:100%;border-radius:8px}}
a.b{{background:#1c3b67;color:#fff;padding:10px 14px;border-radius:8px;text-decoration:none;display:inline-block;margin:4px 0}}</style>
</head><body><h1>Panel Semanal · {f}</h1>
<img src="panel-{f}.png" alt="Panel semanal"><br><a class="b" href="panel-{f}.png" download>Descargar panel</a>
<h2>Audio</h2><audio controls src="panel-{f}.mp3" style="width:100%"></audio><br>
<a class="b" href="panel-{f}.mp3" download>Descargar audio</a>
<h2>Ediciones anteriores</h2><ul>{ant or '<li>Todavía no hay.</li>'}</ul></body></html>""", encoding="utf-8")


def main():
    CARPETA.mkdir(parents=True, exist_ok=True)
    p = datos_semana()
    pronosticos = cargar_pronosticos()
    previos = [x for x in pronosticos if x["semana"] < HOY.isoformat()]
    previos = previos[-1]["items"] if previos else []

    c = generar_contenido(p, titulares_noticias(), previos)
    p["titulares"] = c.get("titulares", [])[:5]
    p["bcra"]["caucion"] = c.get("caucion_7d_tna")
    f = HOY.isoformat()

    dibujar_panel(p, CARPETA / f"panel-{f}.png")
    guion = recortar_guion(re.sub(r"[*#_`>]", "", c["guion"]).strip())
    generar_audio(guion, CARPETA / f"panel-{f}.mp3")
    if not c.get("basico"):
        guardar_pronosticos(pronosticos, c.get("proxima_semana", []))
    publicar({"fecha": f, "titulo": f"Resumen Semanal - {HOY.strftime('%d/%m/%Y')}",
              "resumen": " | ".join(p["titulares"]),
              "bytes": (CARPETA / f"panel-{f}.mp3").stat().st_size,
              "fecha_rfc": AHORA.strftime("%a, %d %b %Y %H:%M:%S %z")})
    print(f"Panel semanal listo: {f} ({len(guion.split())} palabras de audio)")


if __name__ == "__main__":
    main()
