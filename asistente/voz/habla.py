"""Texto a voz con las voces de Windows (SAPI), interrumpible.

Se usa SAPI directamente (vía comtypes) en lugar de pyttsx3 porque permite hablar
de forma asíncrona y cortar la frase a mitad cuando el usuario dice "Jarvis".
"""
import msvcrt
import os
import re
import threading

import comtypes.client

from ..utils.fechas import DIAS, DIAS_CORTOS, MESES

SVSF_ASYNC = 1
SVSF_PURGAR = 2
VELOCIDAD = 1  # SAPI: de -10 a 10
TECLAS_SILENCIO = {b"\x1b", b" "}  # Esc o espacio en la consola


def limpiar_para_voz(texto: str) -> str:
    """Adapta el texto de pantalla para que suene natural al leerlo en voz alta."""
    for corto, largo in zip(DIAS_CORTOS, DIAS):
        texto = re.sub(rf"\b{corto}(?= \d)", largo, texto)
    texto = re.sub(r"\b(\d{1,2})/(\d{1,2})\b",
                   lambda m: f"{int(m.group(1))} de {MESES[int(m.group(2)) - 1]}"
                   if 1 <= int(m.group(2)) <= 12 else m.group(0), texto)
    texto = re.sub(r"(\d{1,2}:\d{2})–(\d{1,2}:\d{2})", r"de \1 a \2", texto)
    texto = re.sub(r"(\d{1,2}):00\b", r"\1", texto)
    texto = re.sub(r"^\s*(?:-|\d+\.)\s+", "", texto, flags=re.M)
    texto = texto.replace("—", ",").replace("\n", ". ")
    return re.sub(r"\.\s*\.", ".", texto)


class Hablante:
    def __init__(self) -> None:
        self.sapi = comtypes.client.CreateObject("SAPI.SpVoice")
        if voz := self._voz_espanola():
            self.sapi.Voice = voz
        self.sapi.Rate = VELOCIDAD

    def _voz_espanola(self):
        preferida = os.getenv("VOZ", "").lower()
        voces = [self.sapi.GetVoices().Item(i) for i in range(self.sapi.GetVoices().Count)]
        for v in voces:
            if preferida and preferida in v.GetDescription().lower():
                return v
        return next((v for v in voces if "spanish" in v.GetDescription().lower()), None)

    def decir(self, texto: str, parar: threading.Event | None = None) -> bool:
        """Habla y espera a terminar. Devuelve True si se cortó (evento `parar` o tecla Esc/espacio)."""
        self.sapi.Speak(limpiar_para_voz(texto), SVSF_ASYNC | SVSF_PURGAR)
        while not self.sapi.WaitUntilDone(50):
            if (parar and parar.is_set()) or _tecla_silencio():
                self.callar()
                return True
        return False

    def callar(self) -> None:
        self.sapi.Speak("", SVSF_ASYNC | SVSF_PURGAR)


def _tecla_silencio() -> bool:
    while msvcrt.kbhit():
        if msvcrt.getch() in TECLAS_SILENCIO:
            return True
    return False
