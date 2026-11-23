"""Escucha el micrófono y transcribe con Whisper (faster-whisper, funciona sin internet).

La primera vez descarga el modelo (small ≈ 460 MB) y lo guarda en caché.
"""
import collections
import os
import threading
import time

import numpy as np
import sounddevice as sd

from ..servicios import microfonos

TASA = 16000
BLOQUE = 480  # 30 ms
PRE_ROLL = 10  # bloques guardados antes de detectar voz (300 ms), para no cortar el inicio
SILENCIO_FIN = 0.8  # segundos de silencio que cierran la frase
DURACION_MAX = 15.0
DURACION_MIN = 0.35
UMBRAL_MIN = 0.006
UMBRAL_MAX = 0.025

# Frases que Whisper "inventa" a veces con ruido de fondo.
ALUCINACIONES = ("amara.org", "subtítulos", "gracias por ver", "suscríbete")


class Oido:
    def __init__(self, palabra_activacion: str = "") -> None:
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # aviso inofensivo en Windows
        from faster_whisper import WhisperModel  # importación lenta: solo en modo voz

        modelo = os.getenv("WHISPER_MODELO", "small")
        print(f"Cargando modelo de voz '{modelo}' (la primera vez se descarga)...")
        self.modelo = WhisperModel(modelo, device="cpu", compute_type="int8")
        p = palabra_activacion
        self.prompt = f"{p}, abre Spotify. {p}, pon música de Queen. {p}, ¿qué tengo hoy? {p}, revisa mi correo."
        self.umbral = 0.01
        self.sin_senal = False

    @property
    def nombre_micro(self) -> str:
        return microfonos.nombre_en_uso()

    def calibrar(self, segundos: float = 1.0) -> None:
        """Mide el ruido ambiente para saber a partir de qué volumen hay voz."""
        with microfonos.EN_USO:
            audio = sd.rec(int(segundos * TASA), samplerate=TASA, channels=1, dtype="float32",
                           device=microfonos.indice())
            sd.wait()
        bloques = audio[: len(audio) // BLOQUE * BLOQUE, 0].reshape(-1, BLOQUE)
        ruido = float(np.median(np.sqrt(np.mean(bloques ** 2, axis=1))))  # mediana: ignora golpes sueltos
        self.sin_senal = float(np.abs(audio).max()) == 0.0  # silencio digital: micro virtual sin conectar
        # Con límite superior: si al calibrar hay ruido (música, alguien hablando) no se queda sordo.
        self.umbral = min(max(ruido * 3, UMBRAL_MIN), UMBRAL_MAX)

    def grabar_frase(self, espera_max: float | None = None, duracion_max: float = DURACION_MAX,
                     detener: threading.Event | None = None) -> np.ndarray | None:
        """Graba desde que empiezas a hablar hasta que te callas.

        Devuelve None si nadie habla en `espera_max` segundos o si se activa `detener`.
        """
        previo = collections.deque(maxlen=PRE_ROLL)
        frase: list[np.ndarray] = []
        silencio = 0.0
        inicio = time.monotonic()
        dur_bloque = BLOQUE / TASA

        with microfonos.EN_USO, sd.InputStream(samplerate=TASA, channels=1, dtype="float32", blocksize=BLOQUE,
                                               device=microfonos.indice()) as flujo:
            while True:
                if detener and detener.is_set():
                    return None
                bloque, _ = flujo.read(BLOQUE)
                bloque = bloque[:, 0].copy()
                hay_voz = float(np.sqrt(np.mean(bloque ** 2))) > self.umbral

                if not frase:
                    previo.append(bloque)
                    if hay_voz:
                        frase.extend(previo)
                    elif espera_max and time.monotonic() - inicio > espera_max:
                        return None
                    continue

                frase.append(bloque)
                silencio = 0.0 if hay_voz else silencio + dur_bloque
                if silencio >= SILENCIO_FIN or len(frase) * dur_bloque >= duracion_max:
                    break

        audio = np.concatenate(frase)
        return audio if len(audio) / TASA >= DURACION_MIN + SILENCIO_FIN else None

    def transcribir(self, audio: np.ndarray) -> str:
        segmentos, _ = self.modelo.transcribe(
            audio, language="es", beam_size=1, initial_prompt=self.prompt, vad_filter=True,
        )
        texto = " ".join(s.text for s in segmentos if s.no_speech_prob < 0.6).strip()
        if any(a in texto.lower() for a in ALUCINACIONES):
            return ""
        return texto

    def escuchar(self, espera_max: float | None = None, detener: threading.Event | None = None) -> str:
        audio = self.grabar_frase(espera_max, detener=detener)
        return self.transcribir(audio) if audio is not None else ""
