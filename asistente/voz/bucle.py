"""Bucle del modo voz, controlable desde fuera (consola o icono de la bandeja).

Estados que notifica: cargando, escuchando, pensando, hablando, silenciado, error.
"""
import threading
from typing import Callable

from .. import __version__, interfaz
from ..core import normalizar, procesar

DESPEDIDAS = {"salir", "exit", "adiós", "adios", "apágate", "apagate", "hasta luego"}
# Órdenes que, dichas mientras habla, solo sirven para callarlo (no pausan Spotify, etc.).
CALLAR = {"para", "calla", "cállate", "callate", "silencio", "basta", "stop", "vale", "ya", "ok"}
MAX_CARACTERES_VOZ = 300  # las respuestas más largas se leen resumidas; el resto queda en pantalla
INTERRUPCION_TROZO = 3.0  # segundos de audio que se analizan mientras habla


def recortar_para_voz(texto: str, limite: int = MAX_CARACTERES_VOZ) -> str:
    """Se queda con las primeras líneas que quepan en el límite (al menos la primera)."""
    lineas = texto.splitlines()
    elegidas = [lineas[0]] if lineas else []
    for linea in lineas[1:]:
        if sum(len(x) for x in elegidas) + len(linea) > limite:
            return "\n".join(elegidas) + "\nTienes el resto en pantalla."
        elegidas.append(linea)
    return "\n".join(elegidas)


class Voz:
    """Interfaz de voz: muestra y dice las respuestas; se puede interrumpir diciendo su nombre."""

    def __init__(self, oido, hablante, nombre: str) -> None:
        self.oido, self.hablante, self.nombre = oido, hablante, nombre

    def hablar(self, texto: str) -> str | None:
        """Dice el texto escuchando a la vez. Si lo interrumpes, devuelve lo que dijiste tras su nombre."""
        from .activacion import buscar_interrupcion

        parar = threading.Event()
        oido_tras_nombre: list[str] = []
        # Si el propio texto contiene el nombre, su eco no debe interrumpirle.
        vigilar_nombre = self.nombre.lower() not in texto.lower()

        def vigilar() -> None:
            while vigilar_nombre and not parar.is_set():
                audio = self.oido.grabar_frase(duracion_max=INTERRUPCION_TROZO, detener=parar)
                if audio is None or parar.is_set():
                    continue
                orden = buscar_interrupcion(self.oido.transcribir(audio), self.nombre)
                if orden is not None:
                    oido_tras_nombre.append(orden)
                    parar.set()

        hilo = threading.Thread(target=vigilar, daemon=True)
        hilo.start()
        self.hablante.decir(texto, parar)
        parar.set()
        hilo.join()

        if not oido_tras_nombre:
            return None  # terminó de hablar, o lo cortaste con Esc/espacio
        orden = oido_tras_nombre[0]
        if orden:  # puede que siguieras hablando cuando se cortó el trozo de audio
            if resto := self.oido.escuchar(espera_max=1.0):
                orden = f"{orden} {resto}"
        print(f"  (interrumpido) {orden or '...'}")
        return orden

    def mostrar(self, texto: str) -> str | None:
        print(texto)
        return self.hablar(recortar_para_voz(texto))

    def preguntar(self, pregunta: str) -> str:
        print(pregunta)
        self.hablante.decir(recortar_para_voz(pregunta))
        respuesta = self.oido.escuchar(espera_max=8)
        print(f"  (oído) {respuesta or '...'}")
        return respuesta


class BucleVoz:
    def __init__(self, nombre: str, al_cambiar_estado: Callable[[str], None] = lambda e: None) -> None:
        self.nombre = nombre
        self._notificar = al_cambiar_estado
        self.estado = "cargando"
        self._salir = threading.Event()
        self._silenciado = threading.Event()
        self._despertar = threading.Event()  # corta una escucha en curso (silenciar / salir)
        self.voz: Voz | None = None

    # --- control desde fuera ---------------------------------------------

    @property
    def silenciado(self) -> bool:
        return self._silenciado.is_set()

    def silenciar(self, activar: bool) -> None:
        (self._silenciado.set if activar else self._silenciado.clear)()
        self._despertar.set()
        if activar and self.voz:
            self.voz.hablante.callar()

    def parar(self) -> None:
        self._salir.set()
        self._despertar.set()
        if self.voz:
            self.voz.hablante.callar()

    # --- funcionamiento ---------------------------------------------------

    def _estado(self, estado: str) -> None:
        if estado != self.estado:
            self.estado = estado
            self._notificar(estado)

    def preparar(self) -> None:
        from .habla import Hablante
        from .oido import Oido

        self._estado("cargando")
        oido = Oido(self.nombre)
        print("Calibrando micrófono: guarda silencio un segundo...")
        oido.calibrar()
        self.voz = Voz(oido, Hablante(), self.nombre)
        interfaz.usar(self.voz)
        print(f"{self.nombre} v{__version__} — MODO VOZ. Micrófono: {oido.nombre_micro} (umbral {oido.umbral:.3f})")
        print(f"Di '{self.nombre}, ayuda' o '{self.nombre}, apágate'.")

    def ejecutar(self, saludo: str = "Hola, ¿en qué te ayudo?") -> None:
        """Escucha y responde hasta que se llame a parar() o digas 'apágate'."""
        from .activacion import extraer_comando

        voz, oido = self.voz, self.voz.oido
        self._estado("hablando")
        pendiente = voz.hablar(saludo)

        while not self._salir.is_set():
            if self._silenciado.is_set():
                self._estado("silenciado")
                self._despertar.wait()
                self._despertar.clear()
                continue

            if pendiente is not None:
                comando, pendiente = pendiente, None
                if normalizar(comando) in CALLAR:
                    continue
            else:
                self._estado("escuchando")
                print("🎤 Escuchando...", end="\r", flush=True)
                frase = oido.escuchar(detener=self._despertar)
                if self._despertar.is_set():
                    self._despertar.clear()
                    continue
                if not frase:
                    continue
                print(f"  (oído) {frase}")
                comando = extraer_comando(frase, self.nombre)
                if comando is None:
                    continue  # no iba dirigido al asistente

            if not normalizar(comando):
                self._estado("hablando")
                voz.hablante.decir("¿Sí?")
                self._estado("escuchando")
                comando = oido.escuchar(espera_max=6, detener=self._despertar)
                print(f"  (oído) {comando or '...'}")
                if not comando:
                    continue
            if normalizar(comando) in DESPEDIDAS:
                break
            if normalizar(comando) in CALLAR:
                continue

            self._estado("pensando")
            respuesta = procesar(comando)
            self._estado("hablando")
            pendiente = voz.mostrar(respuesta)

        if not self._salir.is_set():  # se despidió por voz
            self._estado("hablando")
            voz.hablante.decir("Hasta luego.")
        print("¡Hasta luego!")
