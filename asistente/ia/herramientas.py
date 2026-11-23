"""Herramientas que la IA puede usar. Cada una llama a una skill existente.

Las definiciones siguen el formato JSON Schema de "function calling" que entienden
Ollama, OpenAI y (con una conversión mínima) Claude.
"""
import re
from datetime import date, datetime, time, timedelta

from ..core import normalizar
from ..skills import SKILLS
from ..skills.apps import AppsSkill
from ..skills.calendario import CalendarioSkill
from ..skills.gmail import GmailSkill
from ..skills.recordatorios import RecordatoriosSkill
from ..skills.spotify import SpotifySkill
from ..utils import fechas


def _skill(tipo):
    return next(s for s in SKILLS if isinstance(s, tipo))


def _funcion(nombre: str, descripcion: str, propiedades: dict, requeridos: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": nombre, "description": descripcion,
        "parameters": {"type": "object", "properties": propiedades, "required": requeridos},
    }}


TEXTO = {"type": "string"}
ENTERO = {"type": "integer"}

DEFINICIONES = [
    _funcion("abrir_aplicacion",
             "Abre cualquier programa instalado, una carpeta (descargas, documentos, escritorio...) o una web "
             "conocida (youtube, gmail). Si el usuario lo describe, deduce el nombre del programa "
             "(p. ej. 'el navegador de Mozilla' -> 'Firefox', 'el editor de código' -> 'Visual Studio Code').",
             {"nombre": {"type": "string", "description": "Nombre del programa, carpeta o web"}}, ["nombre"]),
    _funcion("spotify_reproducir",
             "Reproduce música en Spotify. Para peticiones de ambiente o estado de ánimo "
             "('algo tranquilo', 'música para correr') usa tipo=playlist con una búsqueda descriptiva.",
             {"tipo": {"type": "string", "enum": ["cancion", "artista", "album", "playlist"]},
              "consulta": {"type": "string", "description": "Lo que se busca, p. ej. 'Bohemian Rhapsody Queen'"}},
             ["tipo", "consulta"]),
    _funcion("spotify_control", "Controla la reproducción de Spotify.",
             {"accion": {"type": "string", "enum": ["pausa", "reanudar", "siguiente", "anterior", "que_suena",
                                                     "aleatorio_on", "aleatorio_off", "volumen"]},
              "volumen": {"type": "integer", "description": "0-100, solo para accion=volumen"}},
             ["accion"]),
    _funcion("calendario_consultar", "Muestra los eventos del calendario de Google.",
             {"fecha": {"type": "string", "description": "Primer día, formato AAAA-MM-DD"},
              "dias": {"type": "integer", "description": "Cuántos días mostrar (1 = solo ese día)"}},
             ["fecha"]),
    _funcion("calendario_crear",
             "Crea un evento en el calendario. El usuario confirmará antes de guardarlo.",
             {"titulo": TEXTO,
              "fecha": {"type": "string", "description": "AAAA-MM-DD"},
              "hora": {"type": "string", "description": "HH:MM en 24 h; omitir si es de día completo"},
              "duracion_minutos": ENTERO},
             ["titulo", "fecha"]),
    _funcion("gmail_buscar",
             "Lista correos de Gmail (máx. 5) usando la sintaxis de búsqueda de Gmail, "
             "p. ej. 'is:unread', 'from:amazon', 'is:important newer_than:1d', 'factura'.",
             {"consulta": TEXTO}, ["consulta"]),
    _funcion("gmail_leer", "Lee el correo número N de la última lista mostrada.",
             {"numero": ENTERO}, ["numero"]),
    _funcion("recordatorio_crear",
             "Crea un recordatorio o temporizador local: Jarvis avisará hablando cuando llegue la hora. "
             "Usa 'minutos' para 'dentro de X tiempo'; usa fecha/hora para un momento concreto.",
             {"mensaje": {"type": "string", "description": "Qué recordar; vacío para un temporizador simple"},
              "minutos": {"type": "number", "description": "Dentro de cuántos minutos avisar"},
              "fecha": {"type": "string", "description": "AAAA-MM-DD"},
              "hora": {"type": "string", "description": "HH:MM en 24 h"}},
             ["mensaje"]),
    _funcion("recordatorio_listar", "Lista los recordatorios y temporizadores pendientes.", {}, []),
    _funcion("recordatorio_cancelar", "Cancela recordatorios o temporizadores pendientes.",
             {"numero": {"type": "integer", "description": "Número en la lista; omitir si solo hay uno"},
              "todos": {"type": "boolean"}},
             []),
    _funcion("gmail_enviar",
             "Envía un correo. Solo si el usuario dio la dirección de email exacta. Pedirá confirmación.",
             {"para": TEXTO, "asunto": TEXTO, "mensaje": TEXTO}, ["para", "asunto", "mensaje"]),
]


# --- conversión de argumentos ------------------------------------------------

def _fecha(valor) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return fechas.buscar_fecha(str(valor), date.today())[0]


MOMENTOS = {"mañana": time(10), "mediodía": time(13), "mediodia": time(13), "tarde": time(17), "noche": time(21)}


def _hora(valor) -> time | None:
    if not valor:
        return None
    valor = str(valor).strip().lower()
    if m := re.fullmatch(r"(\d{1,2})[:.h](\d{2})", valor):
        return time(int(m.group(1)), int(m.group(2)))
    if hora := fechas.buscar_hora(f"a las {valor}")[0]:
        return hora
    return next((h for palabra, h in MOMENTOS.items() if palabra in valor), None)


def _por_texto(skill, comando: str) -> str:
    """Reutiliza el intérprete de texto de una skill (y su manejo de errores)."""
    return skill.ejecutar(normalizar(comando), comando)


# --- ejecución -------------------------------------------------------------

def ejecutar(nombre: str, args: dict, peticion: str = "") -> str:
    """Ejecuta una herramienta y devuelve el resultado en texto.

    `peticion` es la frase original del usuario: si menciona una fecha u hora explícita,
    manda sobre lo que calculó la IA (los modelos pequeños se equivocan con los días de la semana).
    """
    try:
        return _ejecutar(nombre, _corregir_con_peticion(nombre, dict(args or {}), peticion))
    except Exception as e:  # la IA debe recibir el error para poder explicarlo
        return f"Error al ejecutar {nombre}: {e}"


def _corregir_con_peticion(nombre: str, a: dict, peticion: str) -> dict:
    if nombre == "recordatorio_crear" and peticion:
        duracion, _ = fechas.buscar_duracion_relativa(peticion)
        if duracion:  # "en 20 minutos" dicho por el usuario manda sobre lo calculado
            a.update(minutos=duracion.total_seconds() / 60, fecha=None, hora=None)
            return a
        nombre = "calendario_crear"  # misma corrección de fecha y hora que un evento
        a = _corregir_con_peticion(nombre, a, peticion)
        a.pop("duracion_minutos", None)
        return a
    if nombre not in ("calendario_crear", "calendario_consultar") or not peticion:
        return a
    if "semana" not in peticion.lower():
        dia, _ = fechas.buscar_fecha(peticion, date.today())
        if dia:
            a["fecha"] = dia.isoformat()
    if nombre == "calendario_crear":
        hora, _ = fechas.buscar_hora(peticion)
        if hora:
            a["hora"] = f"{hora:%H:%M}"
        duracion, _ = fechas.buscar_duracion(peticion)
        a["duracion_minutos"] = int(duracion.total_seconds() // 60) if duracion else None  # sin inventar
    return a


def _ejecutar(nombre: str, a: dict) -> str:
    if nombre == "abrir_aplicacion":
        return _por_texto(_skill(AppsSkill), f"abre {str(a['nombre']).lower()}")

    if nombre == "spotify_reproducir":
        consulta = a["consulta"]
        comando = {"artista": f"pon música de {consulta}", "album": f"pon el álbum {consulta}",
                   "playlist": f"pon la playlist {consulta}"}.get(a.get("tipo"), f"pon {consulta}")
        return _por_texto(_skill(SpotifySkill), comando)

    if nombre == "spotify_control":
        accion = a["accion"]
        comando = {"pausa": "pausa", "reanudar": "reanuda", "siguiente": "siguiente", "anterior": "anterior",
                   "que_suena": "qué suena", "aleatorio_on": "activa aleatorio",
                   "aleatorio_off": "quita aleatorio", "volumen": f"volumen {a.get('volumen', 50)}"}.get(accion)
        return _por_texto(_skill(SpotifySkill), comando) if comando else f"Acción desconocida: {accion}"

    if nombre == "calendario_consultar":
        desde = _fecha(a.get("fecha")) or date.today()
        return _skill(CalendarioSkill).consultar(desde, max(1, min(int(a.get("dias") or 1), 31)))

    if nombre == "calendario_crear":
        dia = _fecha(a.get("fecha"))
        if dia is None:
            return "Falta la fecha del evento."
        duracion = timedelta(minutes=int(a["duracion_minutos"])) if a.get("duracion_minutos") else None
        return _skill(CalendarioSkill).crear_evento(a["titulo"], dia, _hora(a.get("hora")), duracion)

    if nombre == "gmail_buscar":
        return _skill(GmailSkill).listar(a["consulta"], "Correos")

    if nombre == "gmail_leer":
        return _skill(GmailSkill).leer(int(a["numero"]))

    if nombre == "recordatorio_crear":
        skill = _skill(RecordatoriosSkill)
        mensaje = str(a.get("mensaje") or "").strip()
        if a.get("minutos"):
            duracion = timedelta(minutes=float(a["minutos"]))
            tipo = "recordatorio" if mensaje else "temporizador"
            return skill.crear(datetime.now() + duracion, mensaje, tipo, duracion if tipo == "temporizador" else None)
        dia, hora = _fecha(a.get("fecha")), _hora(a.get("hora"))
        if dia is None and hora is None:
            return "¿Cuándo te aviso?"
        cuando = datetime.combine(dia or date.today(), hora or time(9, 0))
        if dia is None and cuando <= datetime.now():
            cuando += timedelta(days=1)
        return skill.crear(cuando, mensaje, "recordatorio")

    if nombre == "recordatorio_listar":
        return _skill(RecordatoriosSkill).listar()

    if nombre == "recordatorio_cancelar":
        numero = a.get("numero")
        return _skill(RecordatoriosSkill).cancelar(int(numero) if numero else None, bool(a.get("todos")))

    if nombre == "gmail_enviar":
        if "@" not in str(a.get("para", "")):
            return "No tengo la dirección de correo. Pídesela al usuario."
        return _skill(GmailSkill).enviar(a["para"], a["asunto"], a["mensaje"])

    return f"Herramienta desconocida: {nombre}"


def contexto_fechas(hoy: date | None = None) -> str:
    """Tabla de los próximos 14 días para que el modelo no se equivoque calculando fechas."""
    hoy = hoy or date.today()
    dias = [f"{fechas.DIAS[(hoy + timedelta(d)).weekday()]} {(hoy + timedelta(d)).isoformat()}"
            for d in range(14)]
    return (f"Ahora: {fechas.DIAS[hoy.weekday()]} {hoy.isoformat()} {datetime.now():%H:%M}.\n"
            f"Próximos días: {', '.join(dias)}.")
