import os

from dotenv import load_dotenv

from . import __version__
from .core import procesar


def main() -> None:
    load_dotenv()
    nombre = os.getenv("NOMBRE_ASISTENTE", "Asistente")
    print(f"{nombre} v{__version__} listo. Escribe 'ayuda' o 'salir'.")

    while True:
        try:
            texto = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto.lower() in ("salir", "exit"):
            break
        print(procesar(texto))

    print("¡Hasta luego!")


if __name__ == "__main__":
    main()
