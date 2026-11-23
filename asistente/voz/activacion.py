"""Detecta la palabra de activación ("Jarvis") en lo que dices."""
from difflib import SequenceMatcher

RELLENO = {"oye", "hola", "hey", "ey", "eh", "ok", "okay", "buenas"}
SIMILITUD_MIN = 0.75  # tolera transcripciones como "Yarvis" o "Charvis"
PUNTUACION = " ,.;:!¡¿?"


def _es_palabra(token: str, palabra: str) -> bool:
    return SequenceMatcher(None, token.strip(PUNTUACION).lower(), palabra.lower()).ratio() >= SIMILITUD_MIN


def extraer_comando(frase: str, palabra: str) -> str | None:
    """Devuelve lo que va después de la palabra de activación, si la frase empieza por ella.

    None  -> la frase no iba dirigida al asistente.
    ""    -> solo dijiste la palabra (el asistente debe preguntar "¿sí?").
    """
    tokens = frase.split()
    for i, token in enumerate(tokens[:3]):
        if _es_palabra(token, palabra):
            return " ".join(tokens[i + 1:]).strip(PUNTUACION)
        if token.strip(PUNTUACION).lower() not in RELLENO:
            return None
    return None


def buscar_interrupcion(frase: str, palabra: str) -> str | None:
    """Como extraer_comando, pero la palabra puede estar en cualquier parte.

    Se usa mientras el asistente habla: el micrófono capta también su propia voz,
    así que tu "Jarvis" puede aparecer a mitad de la transcripción.
    """
    tokens = frase.split()
    for i in range(len(tokens) - 1, -1, -1):  # la última mención es la más reciente
        if _es_palabra(tokens[i], palabra):
            return " ".join(tokens[i + 1:]).strip(PUNTUACION)
    return None
