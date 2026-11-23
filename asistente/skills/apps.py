import os
import re
import subprocess
import webbrowser

from ..servicios import programas
from .base import Skill

# Herramientas de Windows que siempre existen: van directas (p. ej. "cmd" no debe abrir "Git CMD").
APLICACIONES = {
    "bloc de notas": "notepad", "notepad": "notepad", "calculadora": "calc", "explorador": "explorer",
    "explorador de archivos": "explorer", "paint": "mspaint", "cmd": "cmd", "símbolo del sistema": "cmd",
    "configuracion": "ms-settings:", "configuración": "ms-settings:", "ajustes": "ms-settings:",
}

# Apodos -> nombre con el que aparece en el menú Inicio.
APODOS = {
    "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
    "el navegador": "google chrome", "navegador": "google chrome", "correo de outlook": "outlook",
    "administrador de tareas": "administrador de tareas", "tareas": "administrador de tareas",
}

WEBS = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
}

CARPETAS = {
    "descargas": "shell:Downloads", "documentos": "shell:Personal", "escritorio": "shell:Desktop",
    "imagenes": "shell:My Pictures", "imágenes": "shell:My Pictures", "fotos": None,  # "fotos" es la app
    "musica": "shell:My Music", "música": "shell:My Music", "videos": "shell:My Video",
    "vídeos": "shell:My Video", "papelera": "shell:RecycleBinFolder",
}

PATRON = re.compile(r"^(?:abre|[aá]breme|abrir|inicia|iniciar|ejecuta|lanza|arranca)\s+(.+)$")
RE_ARTICULO = re.compile(
    r"^(?:el |la |los |las |mi |mis |un |una |)(?:programa |aplicaci[oó]n |app |juego |navegador )?(?:de |del )?")
RE_CARPETA = re.compile(r"^(?:la |mi |mis |)?(?:carpeta (?:de |del )?(?:mis |la |las |los )?)?(.+)$")


def _objetivo(texto: str) -> str | None:
    m = PATRON.match(texto)
    return RE_ARTICULO.sub("", m.group(1).strip(), count=1).strip() if m else None


def _carpeta(texto: str) -> str | None:
    m = PATRON.match(texto)
    if not m:
        return None
    nombre = RE_CARPETA.match(m.group(1).strip()).group(1).strip()
    return CARPETAS.get(nombre)


class AppsSkill(Skill):
    nombre = "apps"
    descripcion = ("Abre cualquier programa instalado, carpetas y webs: 'abre discord', "
                   "'abre visual studio code', 'abre la carpeta descargas', 'abre youtube'")

    def puede_manejar(self, texto: str) -> bool:
        return bool(PATRON.match(texto))

    def directo(self, texto: str) -> bool:
        objetivo = _objetivo(texto)
        if objetivo is None:
            return False
        if _carpeta(texto) or objetivo in WEBS or objetivo in APLICACIONES:
            return True
        return programas.catalogo().buscar(APODOS.get(objetivo, objetivo))[0] is not None  # si no, a la IA

    def ejecutar(self, texto: str, original: str) -> str:
        objetivo = _objetivo(texto)
        if objetivo is None:
            return "¿Qué quieres que abra?"

        if carpeta := _carpeta(texto):
            subprocess.Popen(["explorer.exe", carpeta])
            return f"Abriendo {objetivo}."

        if objetivo in WEBS:
            webbrowser.open(WEBS[objetivo])
            return f"Abriendo {objetivo} en el navegador."

        if comando := APLICACIONES.get(objetivo):
            try:
                if comando.endswith(":"):
                    os.startfile(comando)  # protocolos tipo ms-settings:
                else:
                    subprocess.Popen(f'start "" {comando}', shell=True)
                return f"Abriendo {objetivo}."
            except OSError as e:
                return f"No pude abrir {objetivo}: {e}"

        programa, sugerencias = programas.catalogo().buscar(APODOS.get(objetivo, objetivo))
        if programa:
            try:
                programas.abrir(programa)
                return f"Abriendo {programa.nombre}."
            except OSError as e:
                return f"No pude abrir {programa.nombre}: {e}"

        if sugerencias:
            return f"No encuentro «{objetivo}» entre tus programas. ¿Quizá: {', '.join(sugerencias)}?"
        return f"No encuentro «{objetivo}» entre tus programas."
