"""
Prueba de voz clonada (gratis, licencias MIT): genera el mismo texto con
  1) Tomás (voz actual), 2) tu voz con OpenVoice V2, 3) tu voz con Chatterbox Multilingual.
La muestra de tu voz viene de los secretos VOZ_MUESTRA_1 y VOZ_MUESTRA_2 y nunca se publica.
Uso: python probar_mi_voz.py [openvoice | chatterbox | pagina]
"""
import os, re, sys, base64, asyncio, pathlib, subprocess

TEXTO = ("Comenzamos con el cierre de la semana. Fue una rueda difícil para los activos argentinos: "
         "el Merval cayó cuatro por ciento en pesos y los ADRs retrocedieron más de cinco. "
         "El riesgo país cerró arriba de los seiscientos puntos básicos. "
         "En el frente internacional, el S&P 500 y el Nasdaq terminaron en alza. "
         "YPF, Galicia y Pampa estuvieron entre las más castigadas. "
         "Para la semana que viene, el dato a seguir es la inflación de septiembre y la licitación del Tesoro.")

SALIDA = pathlib.Path("salida")
PAGINA = pathlib.Path("docs") / "semanal" / "pruebas-voz"


def sh(cmd):
    subprocess.run(cmd, shell=True, check=True)


def muestra_wav(sr=24000):
    """Reconstruye tu muestra desde los secretos (solo en memoria del servidor, no se publica)."""
    datos = os.environ.get("VOZ_MUESTRA_1", "") + os.environ.get("VOZ_MUESTRA_2", "")
    if not datos:
        sys.exit("Faltan los secretos VOZ_MUESTRA_1 y VOZ_MUESTRA_2.")
    pathlib.Path("muestra.ogg").write_bytes(base64.b64decode(datos))
    sh(f"ffmpeg -loglevel error -y -i muestra.ogg -ac 1 -ar {sr} muestra.wav")
    return "muestra.wav"


def texto_adaptado():
    sys.path.insert(0, ".")
    from pronunciacion import adaptar
    return adaptar(TEXTO)


def tomas(destino_wav):
    import edge_tts
    asyncio.run(edge_tts.Communicate(texto_adaptado(), "es-AR-TomasNeural", rate="+8%").save("tomas.mp3"))
    sh(f"ffmpeg -loglevel error -y -i tomas.mp3 -ac 1 -ar 22050 {destino_wav}")


def a_mp3(wav, mp3):
    SALIDA.mkdir(exist_ok=True)
    sh(f"ffmpeg -loglevel error -y -i {wav} -ac 1 -b:a 96k {SALIDA / mp3}")


def openvoice():
    """Toma el audio de Tomás (con la pronunciación ya corregida) y le pone tu timbre."""
    import types
    from huggingface_hub import snapshot_download
    # OpenVoice intenta cargar una marca de agua (wavmark) que no necesitamos: se reemplaza por un módulo vacío
    falso = types.ModuleType("wavmark")

    class _SinMarca:
        def to(self, *a, **k):
            return None

    falso.load_model = lambda *a, **k: _SinMarca()
    sys.modules.setdefault("wavmark", falso)
    from openvoice.api import ToneColorConverter
    ckpt = snapshot_download("myshell-ai/OpenVoiceV2", allow_patterns=["converter/*"])
    conv = ToneColorConverter(f"{ckpt}/converter/config.json", device="cpu")
    conv.watermark_model = None
    conv.load_ckpt(f"{ckpt}/converter/checkpoint.pth")
    tomas("tomas.wav")
    muestra_wav(sr=22050)
    se_origen = conv.extract_se(["tomas.wav"])
    se_destino = conv.extract_se(["muestra.wav"])
    conv.convert(audio_src_path="tomas.wav", src_se=se_origen, tgt_se=se_destino,
                 output_path="openvoice.wav", tau=0.3)
    a_mp3("openvoice.wav", "openvoice.mp3")


def chatterbox():
    """Genera el audio directamente con tu voz, frase por frase."""
    import torch, torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    ref = muestra_wav(sr=24000)
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto_adaptado()) if f.strip()]
    partes = []
    silencio = torch.zeros(1, int(modelo.sr * 0.25))
    for f in frases:
        wav = modelo.generate(f, language_id="es", audio_prompt_path=ref)
        partes += [wav, silencio]
    torchaudio.save("chatterbox.wav", torch.cat(partes, dim=1), modelo.sr)
    a_mp3("chatterbox.wav", "chatterbox.mp3")


def pagina():
    """Arma la página de comparación con lo que se haya podido generar."""
    PAGINA.mkdir(parents=True, exist_ok=True)
    tomas("tomas.wav")
    a_mp3("tomas.wav", "tomas.mp3")
    opciones = [("1. Tomás (voz actual)", "tomas.mp3"),
                ("2. Tu voz con OpenVoice (misma pronunciación y ritmo que Tomás, con tu timbre)", "openvoice.mp3"),
                ("3. Tu voz con Chatterbox (genera todo con tu forma de hablar)", "chatterbox.mp3")]
    html = ""
    for titulo, archivo in opciones:
        origen = SALIDA / archivo
        if origen.exists():
            (PAGINA / archivo).write_bytes(origen.read_bytes())
            html += f'<h3>{titulo}</h3><audio controls src="{archivo}" style="width:100%"></audio>'
        else:
            html += f'<h3>{titulo}</h3><p>No se pudo generar esta versión (revisar el registro en GitHub).</p>'
    (PAGINA / "index.html").write_text(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Prueba de mi voz</title></head>
<body style="font-family:system-ui;max-width:700px;margin:auto;padding:16px;color:#1c3b67">
<h1>Prueba de voz clonada</h1><p>{TEXTO}</p>{html}</body></html>""", encoding="utf-8")


if __name__ == "__main__":
    {"openvoice": openvoice, "chatterbox": chatterbox, "pagina": pagina}[sys.argv[1]]()
