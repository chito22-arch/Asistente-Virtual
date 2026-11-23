# Asistente Virtual

Asistente personal para Windows controlado por texto y voz: abre aplicaciones, gestiona Gmail, Google Calendar y Spotify.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m asistente          # modo texto
python -m asistente --voz    # modo voz
```

En VS Code: botón ▶ sobre `asistente/__main__.py` = modo voz; F5 permite elegir "Jarvis (voz)" o "Jarvis (texto)".

Pruebas: `python -m unittest discover tests`

## Uso diario: icono en la bandeja

```bash
python -m asistente --instalar   # crea el acceso directo "Jarvis" en el menú Inicio y el escritorio
```

Abre **Jarvis** desde el acceso directo: funciona en segundo plano, sin ventanas, con un icono junto al reloj.

- Color del icono: 🟢 escuchando · 🟠 pensando · 🔵 hablando · ⚪ cargando / silenciado · 🔴 error.
- Menú (clic derecho): *Escribir una orden…* (también con doble clic), *Silenciar micrófono*,
  *Iniciar con Windows*, *Abrir registro* (`.jarvis/jarvis.log`), *Salir*.
- Solo puede haber un Jarvis a la vez (bandeja o voz), para que no se peleen por el micrófono.

## Modo voz

- Empieza cada orden con el nombre: *"Jarvis, pon música de Queen"*. Solo *"Jarvis"* → responde "¿Sí?".
- Mientras habla puedes cortarle diciendo *"Jarvis"* (o *"Jarvis, otra orden"*) o pulsando **Esc**.
- Confirmaciones (enviar correo, crear evento) se contestan diciendo "sí" o "no".
- Oído: Whisper `small` local (sin internet; la primera vez descarga ~460 MB). Voz: Helena (Windows).
- Ajustes en `.env`: `NOMBRE_ASISTENTE`, `WHISPER_MODELO` (base/small/medium), `VOZ` (Helena/Sabina).

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

## IA (frases libres)

Con [Ollama](https://ollama.com) instalado: `ollama pull qwen3:8b`. Jarvis arranca Ollama si está cerrado.

- Los comandos simples ("pausa", "qué hora es", "revisa mi correo") van directos, sin IA.
- El resto lo interpreta la IA, que elige una herramienta (Gmail, Calendar, Spotify, apps) y sus datos.
  El resultado de la herramienta es la respuesta, así el modelo no puede inventarse correos ni eventos.
- Si dices una fecha u hora explícita, la calcula el intérprete propio (los modelos pequeños fallan con los días).
- Si Ollama no está disponible, sigue funcionando con los comandos fijos. `--sin-ia` la desactiva.
- Ejemplos: *"ponme algo tranquilo para trabajar"*, *"mira si me ha escrito Amazon"* → *"¿y Ryanair?"*,
  *"apúntame cena con Ana el viernes a las 9 de la noche"*, *"¿tengo algo el sábado?"* → *"¿y el domingo?"*.

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
| v0.5 ✅ | Voz: palabra de activación, respuestas habladas e interrumpibles | `faster-whisper`, `sounddevice`, SAPI (`comtypes`) |
| v0.6 ✅ | Frases libres con IA local (Ollama + qwen3:8b) usando las skills como herramientas | `ollama` |
| v1.0 ✅ | Icono en la bandeja del sistema, segundo plano y arranque con Windows | `pystray`, `pillow` |
| v1.1 ✅ | Recordatorios y temporizadores con aviso hablado y notificación | — |

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
- `avísame en 20 minutos`, `pon un temporizador de 5 minutos`, `recuérdame llamar a mamá en una hora`
- `recuérdame mañana a las 9 pagar la luz`, `despiértame a las 7`, `qué recordatorios tengo`
- `cancela el temporizador`, `cancela el recordatorio 2`, `cancela todos los recordatorios`
- `ayuda`, `salir`

Los recordatorios se guardan en `.jarvis/recordatorios.json`: si Jarvis estaba cerrado cuando vencían,
te avisa al abrirlo ("era para las…"). Se dicen en voz alta aunque el micrófono esté silenciado.

Fechas que entiende: hoy, mañana, pasado mañana, el lunes…domingo, 3/12, 3/12/2027, 25 de diciembre.
Horas: a las 10, a las 17:30, a las 5 de la tarde, a las 9 y media.
