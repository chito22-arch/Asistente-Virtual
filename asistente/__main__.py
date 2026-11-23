"""Punto de entrada.

    python -m asistente          -> modo texto
    python -m asistente --voz    -> modo voz (di "<nombre>, <orden>")
"""
import argparse
import os
import sys
import threading

if not __package__:
    # Ejecutado como archivo suelto (p. ej. con el botón ▶ de VS Code): se relanza como
    # módulo con el Python del entorno .venv, que es el que tiene las librerías instaladas.
    # Sin argumentos arranca en modo voz; usa --texto para el modo escrito.
    import subprocess
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    venv = raiz / ".venv" / "Scripts" / "python.exe"
    python = str(venv) if venv.exists() else sys.executable
    args = sys.argv[1:] or ["--voz"]
    sys.exit(subprocess.call([python, "-m", "asistente", *args], cwd=raiz))

from dotenv import load_dotenv

from . import __version__, interfaz
from .core import normalizar, procesar

DESPEDIDAS = {"salir", "exit", "adiós", "adios", "apágate", "apagate", "hasta luego"}
# Órdenes que, dichas mientras habla, solo sirven para callarlo (no pausan Spotify, etc.).
CALLAR = {"para", "calla", "cállate", "callate", "silencio", "basta", "stop", "vale", "ya", "ok"}
MAX_CARACTERES_VOZ = 300  # las respuestas más largas se leen resumidas; el resto queda en pantalla
INTERRUPCION_TROZO = 3.0  # segundos de audio que se analizan mientras habla


def modo_texto(nombre: str) -> None:
    print(f"{nombre} v{__version__} — MODO TEXTO (no usa el micrófono). Escribe 'ayuda' o 'salir'.")
    while True:
        try:
            texto = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto.lower() in DESPEDIDAS:
            break
        print(procesar(texto))
    print("¡Hasta luego!")


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
        from .voz.activacion import buscar_interrupcion

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


def modo_voz(nombre: str) -> None:
    from .voz.activacion import extraer_comando
    from .voz.habla import Hablante
    from .voz.oido import Oido

    oido = Oido(nombre)
    print("Calibrando micrófono: guarda silencio un segundo...")
    oido.calibrar()
    voz = Voz(oido, Hablante(), nombre)
    interfaz.usar(voz)

    print(f"{nombre} v{__version__} — MODO VOZ. Micrófono: {oido.nombre_micro} (umbral {oido.umbral:.3f})")
    print(f"Di '{nombre}, ayuda' o '{nombre}, apágate'.")
    print(f"Para cortarle mientras habla: di '{nombre}' o pulsa Esc. Ctrl+C para salir.")
    pendiente = voz.hablar("Hola, ¿en qué te ayudo?")
    try:
        while True:
            if pendiente is not None:
                comando, pendiente = pendiente, None
                if normalizar(comando) in CALLAR:
                    continue
            else:
                print("🎤 Escuchando...", end="\r", flush=True)
                frase = oido.escuchar()
                if not frase:
                    continue
                print(f"  (oído) {frase}")
                comando = extraer_comando(frase, nombre)
                if comando is None:
                    continue  # no iba dirigido al asistente

            if not normalizar(comando):
                voz.hablante.decir("¿Sí?")
                comando = oido.escuchar(espera_max=6)
                print(f"  (oído) {comando or '...'}")
                if not comando:
                    continue
            if normalizar(comando) in DESPEDIDAS:
                break
            if normalizar(comando) in CALLAR:
                continue
            pendiente = voz.mostrar(procesar(comando))
    except KeyboardInterrupt:
        pass
    voz.hablante.decir("Hasta luego.")
    print("¡Hasta luego!")


def main() -> None:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="asistente", description="Asistente virtual para PC")
    parser.add_argument("--voz", action="store_true", help="controlar el asistente hablando")
    parser.add_argument("--texto", action="store_true", help="modo escrito (por defecto con python -m)")
    args = parser.parse_args()

    nombre = os.getenv("NOMBRE_ASISTENTE", "Asistente")
    modo_voz(nombre) if args.voz else modo_texto(nombre)


if __name__ == "__main__":
    main()
