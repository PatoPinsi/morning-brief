"""
Genera el audio semanal con TU voz (Chatterbox Multilingual, licencia MIT, gratis).
Control de calidad: cada frase se transcribe con Whisper y, si no coincide con el guion
(palabras cortadas, ruidos, frases incompletas), se vuelve a generar hasta 3 veces.
  python voz_chatterbox.py generar <parte> <total>
  python voz_chatterbox.py unir <total>
Si algo falla, queda el audio de respaldo con la voz de Tomás.
"""
import os, re, sys, base64, pathlib, subprocess, unicodedata, difflib

GUION = pathlib.Path("salida/guion.txt")
PARTES = pathlib.Path("partes")
INTENTOS = 3
UMBRAL = 0.85          # parecido mínimo entre lo que se dijo y lo que dice el guion


def sh(cmd):
    subprocess.run(cmd, shell=True, check=True)


def frases():
    texto = GUION.read_text(encoding="utf-8")
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]


def repartir(lista, total):
    tam = -(-len(lista) // total)
    return [lista[i * tam:(i + 1) * tam] for i in range(total)]


def muestra():
    datos = os.environ.get("VOZ_MUESTRA_1", "") + os.environ.get("VOZ_MUESTRA_2", "")
    if not datos:
        sys.exit("Faltan los secretos VOZ_MUESTRA_1 y VOZ_MUESTRA_2.")
    pathlib.Path("muestra.ogg").write_bytes(base64.b64decode(datos))
    sh("ffmpeg -loglevel error -y -i muestra.ogg -ac 1 -ar 24000 muestra.wav")
    return "muestra.wav"


# ---------- Comparación texto esperado vs. lo que se escuchó ----------
def _numeros_a_palabras(t):
    from num2words import num2words
    t = t.replace("%", " por ciento")
    t = re.sub(r"(\d+),(\d+)", lambda m: f"{m.group(1)} coma {m.group(2)}", t)
    t = re.sub(r"(\d)\.(\d{3})", r"\1\2", t)
    return re.sub(r"\d+", lambda m: num2words(int(m.group()), lang="es"), t)


def normalizar(t):
    t = _numeros_a_palabras(t.lower())
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z ]", " ", re.sub(r"\s+", " ", t)).split()


def parecido(esperado, escuchado):
    a, b = normalizar(esperado), normalizar(escuchado)
    if not a or not b:
        return 0.0
    base = difflib.SequenceMatcher(None, a, b).ratio()
    # castigo extra si falta el final de la frase (típico de palabras cortadas)
    final_ok = difflib.SequenceMatcher(None, a[-3:], b[-3:]).ratio()
    return round(0.8 * base + 0.2 * final_ok, 3)


def recortar_silencios(wav, sr, torch):
    """Saca silencios y ruidos sueltos al principio y al final de cada frase."""
    energia = wav.abs().squeeze()
    umbral = energia.max() * 0.02
    idx = (energia > umbral).nonzero()
    if len(idx) == 0:
        return wav
    ini = max(int(idx[0]) - int(0.05 * sr), 0)
    fin = min(int(idx[-1]) + int(0.12 * sr), wav.shape[-1])
    recorte = wav[..., ini:fin].clone()
    n = min(int(0.02 * sr), recorte.shape[-1] // 2)
    if n > 0:  # fundido corto para que no queden "clicks"
        rampa = torch.linspace(0, 1, n)
        recorte[..., :n] *= rampa
        recorte[..., -n:] *= rampa.flip(0)
    return recorte


def generar(parte, total):
    mias = repartir(frases(), total)[parte]
    if not mias:
        print("Esta parte no tiene frases.")
        return
    import torch, torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from faster_whisper import WhisperModel
    modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    oido = WhisperModel("small", device="cpu", compute_type="int8")
    ref = muestra()
    sr = modelo.sr
    silencio = torch.zeros(1, int(sr * 0.3))
    audio = []
    for n, frase in enumerate(mias):
        mejor, mejor_nota = None, -1
        for intento in range(INTENTOS):
            torch.manual_seed(1234 + intento * 97 + n)
            try:
                wav = modelo.generate(frase, language_id="es", audio_prompt_path=ref, temperature=0.6)
            except TypeError:
                wav = modelo.generate(frase, language_id="es", audio_prompt_path=ref)
            wav = recortar_silencios(wav, sr, torch)
            torchaudio.save("prueba.wav", wav, sr)
            segmentos, _ = oido.transcribe("prueba.wav", language="es", beam_size=1)
            escuchado = " ".join(s.text for s in segmentos)
            nota = parecido(frase, escuchado)
            print(f"  frase {n + 1}, intento {intento + 1}: {nota:.2f}")
            if nota > mejor_nota:
                mejor, mejor_nota = wav, nota
            if nota >= UMBRAL:
                break
        if mejor_nota < UMBRAL:
            print(f"  AVISO: la frase {n + 1} quedó con {mejor_nota:.2f} -> '{frase[:60]}...'")
        audio += [mejor, silencio]
    PARTES.mkdir(exist_ok=True)
    torchaudio.save(str(PARTES / f"parte_{parte:02d}.wav"), torch.cat(audio, dim=1), sr)
    print(f"Parte {parte}: {len(mias)} frases generadas.")


def unir(total):
    esperadas = sum(1 for g in repartir(frases(), total) if g)
    archivos = sorted(PARTES.glob("parte_*.wav")) if PARTES.exists() else []
    if len(archivos) != esperadas:
        print(f"Faltan partes de tu voz ({len(archivos)} de {esperadas}): se usa el audio de respaldo.")
        return
    pathlib.Path("lista.txt").write_text("".join(f"file '{a.resolve()}'\n" for a in archivos))
    # Reducción suave de ruido de fondo y volumen parejo en todo el audio
    sh("ffmpeg -loglevel error -y -f concat -safe 0 -i lista.txt "
       "-af \"afftdn=nf=-30,loudnorm=I=-16:TP=-1.5:LRA=11\" -ac 1 -b:a 96k voz.mp3")
    sh("python resumen_semanal.py reemplazar_audio voz.mp3")


if __name__ == "__main__":
    if sys.argv[1] == "generar":
        generar(int(sys.argv[2]), int(sys.argv[3]))
    else:
        unir(int(sys.argv[2]))
