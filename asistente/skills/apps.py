import os
import re
import subprocess
import webbrowser

from .base import Skill

# Alias -> comando de Windows. Amplía esta lista con tus aplicaciones.
APLICACIONES = {
    "bloc de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador": "explorer",
    "paint": "mspaint",
    "cmd": "cmd",
    "terminal": "wt",
    "chrome": "chrome",
    "edge": "msedge",
    "word": "winword",
    "excel": "excel",
    "spotify": "spotify:",
    "configuracion": "ms-settings:",
    "configuración": "ms-settings:",
}

WEBS = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
}

PATRON = re.compile(r"^(abre|abrir|inicia|iniciar|ejecuta|lanza)\s+(?:el |la |los |las )?(.+)$")


class AppsSkill(Skill):
    nombre = "apps"
    descripcion = "Abre aplicaciones y webs: 'abre calculadora', 'abre youtube'"

    def puede_manejar(self, texto: str) -> bool:
        return bool(PATRON.match(texto))

    def ejecutar(self, texto: str) -> str:
        objetivo = PATRON.match(texto).group(2).strip()

        if objetivo in WEBS:
            webbrowser.open(WEBS[objetivo])
            return f"Abriendo {objetivo} en el navegador."

        comando = APLICACIONES.get(objetivo)
        if comando is None:
            return f"No conozco la aplicación '{objetivo}'. Añádela en asistente/skills/apps.py."

        try:
            if comando.endswith(":"):
                os.startfile(comando)  # protocolos tipo spotify: o ms-settings:
            else:
                subprocess.Popen(f'start "" {comando}', shell=True)
            return f"Abriendo {objetivo}."
        except OSError as e:
            return f"No pude abrir {objetivo}: {e}"
