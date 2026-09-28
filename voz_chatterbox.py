"""
Genera el audio semanal con TU voz (Chatterbox Multilingual, licencia MIT, gratis).
El guion se reparte en partes que se generan en paralelo y después se unen.
  python voz_chatterbox.py generar <parte> <total>
  python voz_chatterbox.py unir <total>
Si algo falla, queda el audio de respaldo con la voz de Tomás.
"""
import os, re, sys, base64, pathlib, subprocess

GUION = pathlib.Path("salida/guion.txt")
PARTES = pathlib.Path("partes")


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


def generar(parte, total):
    mias = repartir(frases(), total)[parte]
    if not mias:
        print("Esta parte no tiene frases.")
        return
    import torch, torchaudio
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    torch.manual_seed(1234)   # misma semilla en todas las partes para que la voz sea pareja
    modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    ref = muestra()
    silencio = torch.zeros(1, int(modelo.sr * 0.25))
    audio = []
    for f in mias:
        audio += [modelo.generate(f, language_id="es", audio_prompt_path=ref), silencio]
    PARTES.mkdir(exist_ok=True)
    torchaudio.save(str(PARTES / f"parte_{parte:02d}.wav"), torch.cat(audio, dim=1), modelo.sr)
    print(f"Parte {parte}: {len(mias)} frases generadas.")


def unir(total):
    esperadas = sum(1 for g in repartir(frases(), total) if g)
    archivos = sorted(PARTES.glob("parte_*.wav")) if PARTES.exists() else []
    if len(archivos) != esperadas:
        print(f"Faltan partes de tu voz ({len(archivos)} de {esperadas}): se usa el audio de respaldo.")
        return
    lista = pathlib.Path("lista.txt")
    lista.write_text("".join(f"file '{a.resolve()}'\n" for a in archivos))
    sh("ffmpeg -loglevel error -y -f concat -safe 0 -i lista.txt -ac 1 -b:a 96k voz.mp3")
    sh("python resumen_semanal.py reemplazar_audio voz.mp3")


if __name__ == "__main__":
    if sys.argv[1] == "generar":
        generar(int(sys.argv[2]), int(sys.argv[3]))
    else:
        unir(int(sys.argv[2]))
