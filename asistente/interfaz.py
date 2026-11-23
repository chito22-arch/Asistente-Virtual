"""Cómo habla el asistente con el usuario: por teclado (por defecto), por voz o con ventanas.

Las skills usan `obtener().preguntar(...)` para pedir confirmaciones, así funcionan igual
en modo texto, en modo voz y desde el icono de la bandeja.
"""
import re
import threading

AFIRMATIVOS = {
    "s", "si", "sí", "vale", "ok", "okay", "claro", "adelante", "dale", "correcto", "venga",
    "hazlo", "envíalo", "envialo", "añádelo", "anadelo", "confirmo", "yes", "por supuesto",
}


def es_afirmativo(respuesta: str) -> bool:
    palabras = re.findall(r"[a-záéíóúñü]+", respuesta.lower())
    return bool(palabras) and (palabras[0] in AFIRMATIVOS or " ".join(palabras[:2]) in AFIRMATIVOS)


class Teclado:
    def mostrar(self, texto: str) -> None:
        print(texto)

    def preguntar(self, pregunta: str) -> str:
        return input(f"{pregunta} (s/n) ")


actual = Teclado()
_hilo = threading.local()


def usar(interfaz) -> None:
    """Interfaz por defecto para todo el programa."""
    global actual
    actual = interfaz


def usar_en_este_hilo(interfaz) -> None:
    """Interfaz solo para el hilo actual (p. ej. una orden escrita desde el icono mientras la voz sigue)."""
    _hilo.interfaz = interfaz


def obtener():
    return getattr(_hilo, "interfaz", None) or actual
