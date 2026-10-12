"""
Generación de audio con respaldo automático.

Orden de intento:
1) edge-tts (voz de Microsoft, Tomás). Desde el 10/10/2026 Microsoft rechaza las
   conexiones de edge-tts con error 403; se sigue probando primero por si lo arreglan.
2) Gemini TTS (con la misma GEMINI_API_KEY). Elige solo un modelo TTS disponible.
3) gTTS (voz de Google Traductor, gratis y sin clave). Último recurso.

Siempre deja un .mp3 en `destino`; si las tres fallan, levanta el error.
"""
import os, re, io, time, wave, asyncio, pathlib

VOZ_EDGE = "es-AR-TomasNeural"
VELOCIDAD_EDGE = "+8%"
VOZ_GEMINI = os.environ.get("VOZ_GEMINI", "Charon")   # voz masculina, tono informativo
ESTILO_GEMINI = ("Leé el siguiente texto en español rioplatense de Argentina, como locutor "
                 "de un podcast matinal de mercados: tono radial, claro, ágil y natural.")


# ---------------- 1. edge-tts ----------------
def _edge(guion, destino, voz, velocidad):
    import edge_tts
    for intento in range(2):
        try:
            asyncio.run(edge_tts.Communicate(guion, voz, rate=velocidad).save(str(destino)))
            if pathlib.Path(destino).stat().st_size > 10_000:
                return
            raise RuntimeError("edge-tts devolvió un audio vacío")
        except Exception as e:
            print(f"Aviso edge-tts (intento {intento + 1}):", str(e)[:200])
            if "403" in str(e):
                break  # bloqueo de Microsoft: reintentar no sirve
            time.sleep(5)
    raise RuntimeError("edge-tts no disponible")


# ---------------- 2. Gemini TTS ----------------
def _partes(texto, max_palabras=220):
    """Corta el guion en bloques de frases completas para no pasar el límite del modelo."""
    frases = [f for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    bloques, actual = [], []
    for f in frases:
        if actual and len(" ".join(actual + [f]).split()) > max_palabras:
            bloques.append(" ".join(actual))
            actual = []
        actual.append(f)
    if actual:
        bloques.append(" ".join(actual))
    return bloques


def _modelos_tts(client):
    try:
        nombres = [m.name.split("/")[-1] for m in client.models.list() if "tts" in m.name]
    except Exception:
        nombres = []
    preferidos = sorted(nombres, key=lambda n: ("pro" in n, "preview" in n))  # flash primero
    return preferidos or ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]


def _pcm_a_mp3(pcm, destino, frecuencia=24000):
    import lameenc
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(frecuencia)
    enc.set_channels(1)
    enc.set_quality(2)
    pathlib.Path(destino).write_bytes(enc.encode(pcm) + enc.flush())


def _gemini(guion, destino):
    from google import genai
    from google.genai import types
    client = genai.Client()
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOZ_GEMINI))))
    bloques = _partes(guion)
    for modelo in _modelos_tts(client):
        pcm = b""
        try:
            for i, bloque in enumerate(bloques):
                for intento in range(3):
                    try:
                        r = client.models.generate_content(
                            model=modelo, contents=f"{ESTILO_GEMINI}\n\n{bloque}", config=config)
                        datos = r.candidates[0].content.parts[0].inline_data.data
                        if not datos:
                            raise RuntimeError("respuesta sin audio")
                        pcm += datos
                        break
                    except Exception as e:
                        if "404" in str(e) or intento == 2:
                            raise
                        print(f"Aviso Gemini TTS ({modelo}, parte {i + 1}):", str(e)[:200])
                        time.sleep(20 if "429" in str(e) else 5)
            _pcm_a_mp3(pcm, destino)
            print(f"Audio generado con {modelo} (voz {VOZ_GEMINI})")
            return
        except Exception as e:
            print(f"Aviso Gemini TTS ({modelo}):", str(e)[:300])
    raise RuntimeError("Gemini TTS no disponible")


# ---------------- 3. gTTS ----------------
def _gtts(guion, destino):
    from gtts import gTTS
    gTTS(guion, lang="es", tld="com.ar").save(str(destino))
    print("Audio generado con gTTS (voz de respaldo)")


# ---------------- Entrada ----------------
def generar_audio(guion, destino, voz=VOZ_EDGE, velocidad=VELOCIDAD_EDGE):
    errores = []
    for nombre, motor in (("edge-tts", lambda: _edge(guion, destino, voz, velocidad)),
                          ("Gemini TTS", lambda: _gemini(guion, destino)),
                          ("gTTS", lambda: _gtts(guion, destino))):
        try:
            motor()
            if nombre == "edge-tts":
                print(f"Audio generado con edge-tts ({voz})")
            return nombre
        except Exception as e:
            errores.append(f"{nombre}: {str(e)[:200]}")
            pathlib.Path(destino).unlink(missing_ok=True)
    raise RuntimeError("No se pudo generar el audio. " + " | ".join(errores))
