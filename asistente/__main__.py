"""Punto de entrada.

    python -m asistente              -> modo texto
    python -m asistente --voz        -> modo voz en la consola (di "<nombre>, <orden>")
    pythonw -m asistente --bandeja   -> en segundo plano, con icono junto al reloj
    python -m asistente --instalar   -> crea los accesos directos "Jarvis" (menú Inicio y escritorio)
"""
import argparse
import os
import sys

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

from . import __version__
from .core import procesar
from .voz.bucle import DESPEDIDAS, Voz, recortar_para_voz  # noqa: F401 (reexportados para los tests)


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


def modo_voz(nombre: str) -> None:
    from .voz.bucle import BucleVoz

    bucle = BucleVoz(nombre)
    bucle.preparar()
    print(f"Para cortarle mientras habla: di '{nombre}' o pulsa Esc. Ctrl+C para salir.")
    try:
        bucle.ejecutar()
    except KeyboardInterrupt:
        bucle.parar()
        print("¡Hasta luego!")


def main() -> None:
    parser = argparse.ArgumentParser(prog="asistente", description="Asistente virtual para PC")
    parser.add_argument("--voz", action="store_true", help="controlar el asistente hablando")
    parser.add_argument("--texto", action="store_true", help="modo escrito (por defecto con python -m)")
    parser.add_argument("--bandeja", action="store_true", help="en segundo plano con icono junto al reloj")
    parser.add_argument("--instalar", action="store_true", help="crear accesos directos en Inicio y escritorio")
    parser.add_argument("--sin-ia", action="store_true", help="no usar IA, solo comandos fijos")
    args = parser.parse_args()

    from . import windows

    if args.bandeja:
        windows.redirigir_salida_a_registro()  # con pythonw no hay consola
    elif hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(windows.RAIZ / ".env")

    if args.instalar:
        for ruta in windows.instalar():
            print(f"Acceso directo creado: {ruta}")
        return

    nombre = os.getenv("NOMBRE_ASISTENTE", "Asistente")
    if (args.voz or args.bandeja) and not windows.instancia_unica():
        print(f"{nombre} ya está en marcha (mira el icono junto al reloj). Ciérralo antes de abrir otro.")
        if args.bandeja:
            windows.aviso(nombre, f"{nombre} ya está en marcha.")
        return

    if args.sin_ia:
        os.environ["IA_PROVEEDOR"] = "ninguno"

    if args.bandeja:
        from .bandeja import Bandeja

        Bandeja(nombre).ejecutar()
        return

    from .ia import preparar_ia

    preparar_ia(nombre)
    modo_voz(nombre) if args.voz else modo_texto(nombre)


if __name__ == "__main__":
    main()
