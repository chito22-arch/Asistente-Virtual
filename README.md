# Asistente Virtual

Asistente personal para Windows controlado por texto y voz: abre aplicaciones, gestiona Gmail, Google Calendar y Spotify.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m asistente
```

## Arquitectura

Cada integración es una **Skill** (`asistente/skills/`) con dos métodos: `puede_manejar(texto)` y `ejecutar(texto)`.
`core.py` recibe el texto (escrito o transcrito de voz) y lo envía a la primera skill que lo entienda.
Añadir una función nueva = crear una skill y registrarla en `skills/__init__.py`.

```
entrada (texto / voz) -> core.procesar() -> Skill -> respuesta (texto / voz)
```

## Hoja de ruta

| Versión | Funcionalidad | Librerías |
|---|---|---|
| v0.1 ✅ | Núcleo + comandos de texto + abrir apps/webs | `python-dotenv` |
| v0.2 | Voz: escuchar (palabra de activación) y hablar | `faster-whisper` / `SpeechRecognition`, `pyttsx3` |
| v0.3 | Gmail: leer no leídos, buscar, enviar | `google-api-python-client`, `google-auth-oauthlib` |
| v0.4 | Google Calendar: ver agenda, crear eventos | (mismas que Gmail) |
| v0.5 | Spotify: play/pausa, siguiente, buscar canción | `spotipy` |
| v0.6 | Lenguaje natural con IA (entender frases libres) | API de Claude con *tool use* |
| v1.0 | Icono en bandeja del sistema + arranque con Windows | `pystray` |

## Comandos actuales

- `abre calculadora`, `abre bloc de notas`, `abre spotify`, `abre youtube`
- `qué hora es`, `qué día es`
- `ayuda`, `salir`
