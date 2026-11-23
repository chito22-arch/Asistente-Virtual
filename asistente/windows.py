"""Integración con Windows: accesos directos, arranque automático, instancia única y registro."""
import ctypes
import os
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / ".jarvis"  # registro e icono (ignorado por git)
REGISTRO = DATOS / "jarvis.log"
ICONO = DATOS / "jarvis.ico"
PYTHONW = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
NOMBRE_ACCESO = "Jarvis.lnk"
MAX_REGISTRO = 1_000_000  # bytes; al superarlo se empieza de nuevo

_mutex = None  # se mantiene vivo mientras dure el proceso


def instancia_unica() -> bool:
    """True si no hay otro Jarvis (voz o bandeja) en marcha. Dos a la vez se pelearían por el micrófono."""
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\JarvisAsistenteVirtual")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def redirigir_salida_a_registro() -> None:
    """Con pythonw no hay consola: todo lo que se imprime va a .jarvis/jarvis.log."""
    DATOS.mkdir(exist_ok=True)
    if REGISTRO.exists() and REGISTRO.stat().st_size > MAX_REGISTRO:
        REGISTRO.unlink()
    fichero = open(REGISTRO, "a", encoding="utf-8", buffering=1)
    fichero.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
    sys.stdout = sys.stderr = fichero


def aviso(titulo: str, texto: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40 | 0x40000)  # información, siempre encima


# --- accesos directos -------------------------------------------------------

def _carpeta_especial(nombre: str) -> Path:
    import comtypes.client

    return Path(comtypes.client.CreateObject("WScript.Shell", dynamic=True).SpecialFolders(nombre))


def acceso_inicio_windows() -> Path:
    return _carpeta_especial("Startup") / NOMBRE_ACCESO


def crear_acceso(ruta: Path) -> Path:
    import comtypes.client

    from .bandeja import guardar_icono

    guardar_icono(ICONO)
    shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
    acceso = shell.CreateShortcut(str(ruta))
    acceso.TargetPath = str(PYTHONW if PYTHONW.exists() else Path(sys.executable).with_name("pythonw.exe"))
    acceso.Arguments = "-m asistente --bandeja"
    acceso.WorkingDirectory = str(RAIZ)
    acceso.IconLocation = str(ICONO)
    acceso.Description = "Asistente virtual Jarvis"
    acceso.Save()
    return ruta


def instalar() -> list[Path]:
    """Accesos directos en el menú Inicio y en el escritorio."""
    return [crear_acceso(_carpeta_especial("Programs") / NOMBRE_ACCESO),
            crear_acceso(_carpeta_especial("Desktop") / NOMBRE_ACCESO)]


def inicio_automatico() -> bool:
    return acceso_inicio_windows().exists()


def activar_inicio_automatico(activar: bool) -> None:
    ruta = acceso_inicio_windows()
    if activar:
        crear_acceso(ruta)
    elif ruta.exists():
        os.remove(ruta)
