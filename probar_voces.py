"""Genera muestras de voz para comparar (se publican en /semanal/pruebas/)."""
import asyncio, pathlib, edge_tts
from pronunciacion import adaptar

TEXTO = ("Arrancamos con el cierre de la semana. Fue una rueda complicada para los papeles argentinos: "
         "el Merval cayó cuatro por ciento en pesos y los ADRs se hundieron más de cinco. "
         "Ojo con el riesgo país, que cerró arriba de los seiscientos puntos básicos. "
         "Afuera, el S&P 500 y el Nasdaq cerraron en verde, y el WTI se desplomó casi ocho por ciento. "
         "YPF, Galicia y Pampa, entre las que más sufrieron. El BCRA frenó las compras, "
         "el CCL y el MEP subieron apenas, y la caución a siete días quedó cerca del veinte por ciento TNA. "
         "Para la semana que viene, fijate en el dato de inflación del INDEC y en la licitación del Tesoro.")

VOCES = {"tomas": "es-AR-TomasNeural", "elena": "es-AR-ElenaNeural"}
VELOCIDADES = {"normal": "+0%", "agil": "+8%"}
CARPETA = pathlib.Path("docs") / "semanal" / "pruebas"


async def main():
    CARPETA.mkdir(parents=True, exist_ok=True)
    filas = []
    for nombre, voz in VOCES.items():
        for vel_nombre, vel in VELOCIDADES.items():
            archivo = f"{nombre}-{vel_nombre}.mp3"
            await edge_tts.Communicate(adaptar(TEXTO), voz, rate=vel).save(str(CARPETA / archivo))
            filas.append((f"{nombre.capitalize()} · ritmo {vel_nombre}", archivo))
    await edge_tts.Communicate(TEXTO, VOCES["tomas"], rate="+5%").save(str(CARPETA / "sin-corregir.mp3"))
    filas.append(("Tomás SIN el diccionario (como sonaba antes)", "sin-corregir.mp3"))
    items = "".join(f'<h3>{t}</h3><audio controls src="{a}" style="width:100%"></audio>' for t, a in filas)
    (CARPETA / "index.html").write_text(f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Prueba de voces</title></head>
<body style="font-family:system-ui;max-width:700px;margin:auto;padding:16px;color:#1c3b67">
<h1>Prueba de voces</h1><p>{TEXTO}</p>{items}</body></html>""", encoding="utf-8")


asyncio.run(main())
