# Morning Brief de Mercados (versión gratuita)

Podcast automático de lunes a viernes, listo antes de las 7:30 (hora Argentina). Costo: cero.

## Puesta en marcha (una sola vez, desde una computadora)

1. **Clave gratuita de Gemini**: entrá a aistudio.google.com con tu cuenta de Google →
   "Get API key" → "Create API key". No pide tarjeta. Copiala.
2. **Repositorio**: creá cuenta en github.com → "New repository" → nombre `morning-brief`,
   **Public** (así Pages y Actions son gratis) → Create.
3. **Archivos**: "Add file → Upload files" y subí `morning_brief.py`, `requirements.txt` y `README.md`.
4. **Horario**: "Add file → Create new file", nombre `.github/workflows/morning-brief.yml`,
   y pegá el contenido de ese archivo del zip (abrilo con el Bloc de notas).
5. **Claves**: Settings → Secrets and variables → Actions.
   - Secrets: `GEMINI_API_KEY` con tu clave.
   - Variables: `FEED_BASE_URL` = `https://TU-USUARIO.github.io/morning-brief`
6. **Primer episodio**: Actions → "Morning brief" → "Run workflow". Esperá el tilde verde.
7. **Publicación**: Settings → Pages → Branch `main`, carpeta `/docs` → Save.
8. **Celular**: en Pocket Casts o Apple Podcasts, agregar podcast por URL:
   `https://TU-USUARIO.github.io/morning-brief/feed.xml` y activar descarga automática.

## Ajustes (en `morning_brief.py`)
- `VOZ`: `es-AR-TomasNeural` (masculina) o `es-AR-ElenaNeural` (femenina).
- `VELOCIDAD`: ritmo de lectura.
- `PALABRAS_OBJETIVO`: 1000 ≈ 7 min, 1300 ≈ 9 min.
- `TICKERS` y `BUSQUEDAS_NOTICIAS`: qué activos y temas seguir.
