"""Cómo habla el asistente con el usuario: por teclado (por defecto) o por voz.

Las skills usan `actual.preguntar(...)` para pedir confirmaciones, así funcionan igual
en modo texto y en modo voz.
"""
import re

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


def usar(interfaz) -> None:
    global actual
    actual = interfaz
