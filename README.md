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

Pruebas: `python -m unittest discover tests`

## Configurar Google (Gmail y Calendar)

Se hace una sola vez:

1. Entra en <https://console.cloud.google.com/> y crea un proyecto (p. ej. "Asistente Virtual").
2. **APIs y servicios → Biblioteca**: habilita **Gmail API** y **Google Calendar API**.
3. **APIs y servicios → Pantalla de consentimiento de OAuth** (o "Google Auth Platform"):
   tipo **Externo**, rellena nombre y tu correo, y en **Usuarios de prueba** añade tu cuenta de Gmail.
4. **Credenciales → Crear credenciales → ID de cliente de OAuth**, tipo **Aplicación de escritorio**.
5. Descarga el JSON, renómbralo a `credentials.json` y ponlo en la raíz del proyecto.
6. Ejecuta el asistente y escribe `revisa mi correo`: se abrirá el navegador para autorizar
   (aparecerá "Google no ha verificado esta app": pulsa *Continuar*, es tu propia app).
   Se crea `token.json` y no volverá a preguntar.

`credentials.json` y `token.json` están en `.gitignore`: **nunca los subas a GitHub**.

## Configurar Spotify

Controlar la reproducción requiere **Spotify Premium**.

1. Entra en <https://developer.spotify.com/dashboard> con tu cuenta de Spotify y pulsa **Create app**.
2. Nombre y descripción: "Asistente Virtual". **Redirect URI**: `http://127.0.0.1:8888/callback` (pulsa *Add*).
   En "Which API/SDKs are you planning to use?" marca **Web API**. Acepta los términos y guarda.
3. En la app, ve a **Settings** y copia el **Client ID** y el **Client secret** (*View client secret*).
4. Pégalos en `.env` (`SPOTIFY_CLIENT_ID=` y `SPOTIFY_CLIENT_SECRET=`).
5. Abre la app de Spotify en el PC, ejecuta el asistente y escribe `qué suena`: se abrirá el navegador para autorizar.
   El token se guarda en `.cache-spotify` (ignorado por git).

## Arquitectura

Cada integración es una **Skill** (`asistente/skills/`) con dos métodos: `puede_manejar(texto)` y `ejecutar(texto, original)`.
`core.py` recibe el texto (escrito o transcrito de voz) y lo envía a la primera skill que lo entienda.
Añadir una función nueva = crear una skill y registrarla en `skills/__init__.py`.
Los clientes de APIs externas viven en `asistente/servicios/`.

```
entrada (texto / voz) -> core.procesar() -> Skill -> respuesta (texto / voz)
```

## Hoja de ruta

| Versión | Funcionalidad | Librerías |
|---|---|---|
| v0.1 ✅ | Núcleo + comandos de texto + abrir apps/webs | `python-dotenv` |
| v0.2 ✅ | Gmail: no leídos, leer, buscar, enviar (con confirmación) | `google-api-python-client`, `google-auth-oauthlib` |
| v0.3 ✅ | Google Calendar: ver agenda, crear eventos (con confirmación) | (mismas que Gmail) |
| v0.4 ✅ | Spotify: canción/artista/álbum/playlist, pausa, siguiente, volumen | `spotipy` |
| v0.5 | Voz: escuchar (palabra de activación) y hablar | `faster-whisper` / `SpeechRecognition`, `pyttsx3` |
| v0.6 | Lenguaje natural con IA (entender frases libres) | API de Claude con *tool use* |
| v1.0 | Icono en bandeja del sistema + arranque con Windows | `pystray` |

## Comandos actuales

- `abre calculadora`, `abre bloc de notas`, `abre spotify`, `abre youtube`
- `qué hora es`, `qué día es`
- `revisa mi correo` — últimos 5 no leídos
- `lee el correo 2` — abre el nº 2 de la última lista y lo marca como leído
- `busca correos de juan` / `busca correos sobre factura`
- `envía un correo a alguien@mail.com asunto: Hola mensaje: ¿Quedamos mañana?` — pide confirmación
- `qué tengo hoy`, `qué tengo mañana`, `qué tengo el viernes`, `agenda de esta semana`
- `crea una reunión con Ana mañana a las 10` — 1 hora por defecto, pide confirmación
- `crea un evento Dentista el 3/12 a las 5 de la tarde durante 30 minutos`
- `añade un evento Vacaciones el 25 de diciembre` — sin hora = todo el día
- `pon Bohemian Rhapsody`, `pon despacito de luis fonsi`, `pon música de Bad Bunny`
- `pon la playlist Gym`, `pon el álbum Abbey Road`, `pon música` (reanuda)
- `pausa`, `siguiente`, `anterior`, `qué suena`, `volumen 40`, `sube el volumen`, `activa aleatorio`
- `ayuda`, `salir`

Fechas que entiende: hoy, mañana, pasado mañana, el lunes…domingo, 3/12, 3/12/2027, 25 de diciembre.
Horas: a las 10, a las 17:30, a las 5 de la tarde, a las 9 y media.
