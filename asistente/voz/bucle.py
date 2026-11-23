"""Bucle del modo voz, controlable desde fuera (consola o icono de la bandeja).

Estados que notifica: cargando, escuchando, pensando, hablando, silenciado, error.
"""
import queue
import threading
from typing import Callable

from .. import __version__, interfaz
from ..core import normalizar, procesar
from ..servicios import microfonos, recordatorios

DESPEDIDAS = {"salir", "exit", "adiós", "adios", "apágate", "apagate", "hasta luego"}
# Órdenes que, dichas mientras habla, solo sirven para callarlo (no pausan Spotify, etc.).
CALLAR = {"para", "calla", "cállate", "callate", "silencio", "basta", "stop", "vale", "ya", "ok"}
MAX_CARACTERES_VOZ = 300  # las respuestas más largas se leen resumidas; el resto queda en pantalla
INTERRUPCION_TROZO = 3.0  # segundos de audio que se analizan mientras habla


def recortar_para_voz(texto: str, limite: int = MAX_CARACTERES_VOZ) -> str:
    """Se queda con las primeras líneas que quepan en el límite (al menos la primera)."""
    lineas = [linea for linea in texto.splitlines() if not linea.startswith("Fuentes:")]  # solo en pantalla
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
                try:
                    audio = self.oido.grabar_frase(duracion_max=INTERRUPCION_TROZO, detener=parar)
                except Exception:  # micrófono no disponible: se puede seguir hablando sin vigilar
                    return
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
        self._despertar = threading.Event()  # corta una escucha en curso (silenciar / salir / aviso)
        self._avisos: queue.Queue[str] = queue.Queue()
        self._cambio_micro = threading.Event()
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

    def avisar(self, texto: str) -> None:
        """Pide decir un aviso (recordatorio) en cuanto se pueda. Seguro desde cualquier hilo."""
        self._avisos.put(texto)
        self._despertar.set()

    def _micro_cambiado(self, _nombre: str) -> None:
        """Se eligió otro micrófono (por voz o desde el icono): recalibrar antes de volver a escuchar."""
        self._cambio_micro.set()
        self._despertar.set()

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
        if microfonos.configurado() and microfonos.actual() is None:
            self.avisar(f"No encuentro el micrófono «{microfonos.configurado()}»; uso el de Windows.")
        print("Calibrando micrófono: guarda silencio un segundo...")
        oido.calibrar()
        self.voz = Voz(oido, Hablante(), self.nombre)
        interfaz.usar(self.voz)
        recordatorios.gestor().suscribir(self.avisar)
        microfonos.suscribir(self._micro_cambiado)
        print(f"{self.nombre} v{__version__} — MODO VOZ. Micrófono: {oido.nombre_micro} (umbral {oido.umbral:.3f})")
        print(f"Di '{self.nombre}, ayuda' o '{self.nombre}, apágate'.")

    def _recalibrar(self) -> None:
        self._estado("cargando")
        try:
            self.voz.oido.calibrar()
            print(f"Micrófono: {microfonos.nombre_en_uso()} (umbral {self.voz.oido.umbral:.3f})")
        except Exception as e:
            self._fallo_micro(e)
            return
        if self.voz.oido.sin_senal is True:
            self.avisar(f"No me llega ningún sonido de {microfonos.nombre_en_uso()}. ¿Está conectado? "
                        f"Puedes volver al de Windows diciendo: usa el micrófono predeterminado.")

    def _fallo_micro(self, error: Exception) -> None:
        print(f"Error con el micrófono {microfonos.nombre_en_uso()}: {error}")
        if microfonos.configurado():
            nombre = microfonos.configurado()
            microfonos.elegir("")  # vuelve al predeterminado de Windows (y recalibra)
            self.avisar(f"Ya no puedo usar el micrófono «{nombre}». Vuelvo al de Windows.")
        else:
            self._salir.wait(2)  # el de Windows tampoco va: reintentar sin saturar

    def ejecutar(self, saludo: str = "Hola, ¿en qué te ayudo?") -> None:
        """Escucha y responde hasta que se llame a parar() o digas 'apágate'."""
        from .activacion import extraer_comando

        voz, oido = self.voz, self.voz.oido
        self._estado("hablando")
        pendiente = voz.hablar(saludo)

        while not self._salir.is_set():
            while not self._avisos.empty():  # recordatorios vencidos: se dicen aunque esté silenciado
                aviso = self._avisos.get()
                recordatorios.sonar()
                self._estado("hablando")
                if self._silenciado.is_set():
                    voz.hablante.decir(aviso)  # sin escuchar: el micrófono está silenciado
                else:
                    pendiente = voz.hablar(aviso) or pendiente

            if self._cambio_micro.is_set():
                self._cambio_micro.clear()
                self._recalibrar()
                continue

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
                try:
                    frase = oido.escuchar(detener=self._despertar)
                except Exception as e:  # micrófono desconectado (p. ej. auriculares Bluetooth apagados)
                    self._fallo_micro(e)
                    continue
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
