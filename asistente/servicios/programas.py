"""Catálogo de los programas instalados (todo lo que aparece en el menú Inicio).

Usa `Get-StartApps` de Windows, que incluye programas clásicos, apps de la Tienda y juegos de
Steam. Se guarda en .jarvis/programas.json y se refresca en segundo plano.
"""
import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

ARCHIVO = Path(__file__).resolve().parents[2] / ".jarvis" / "programas.json"
CADUCIDAD = 24 * 3600  # segundos; además se refresca al arrancar y si no encuentra algo
REFRESCO_MIN = 120  # no volver a preguntar a Windows más a menudo que esto
SIMILITUD_MIN = 0.78

# Entradas del menú Inicio que no son programas que alguien quiera "abrir".
RE_BASURA = re.compile(
    r"\b(uninstall|desinstalar|readme|release notes|documentation|documentaci[oó]n|help|ayuda de|faq|"
    r"error reporter|website|sitio web|license|licencia)\b", re.I)
EXTENSIONES_ARCHIVO = (".zip", ".rar", ".7z", ".chm", ".html", ".htm", ".url", ".txt", ".pdf")
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class Programa:
    nombre: str
    appid: str


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: 'Configuración' -> 'configuracion'."""
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9+#]+", " ", texto).strip()


def es_util(p: Programa) -> bool:
    appid = p.appid.lower()
    if appid.startswith(("http://", "https://")) or appid.endswith(EXTENSIONES_ARCHIVO):
        return False
    return not RE_BASURA.search(p.nombre)


class Catalogo:
    def __init__(self, archivo: Path = ARCHIVO, listar=None) -> None:
        self.archivo = archivo
        self._listar = listar or listar_de_windows
        self._lock = threading.Lock()
        self._programas: list[Programa] = []
        self._actualizado = 0.0
        self._cargar()

    def _cargar(self) -> None:
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
            self._programas = [Programa(**d) for d in datos["programas"]]
            self._actualizado = datos["actualizado"]
        except (OSError, ValueError, KeyError, TypeError):
            self._programas, self._actualizado = [], 0.0

    def refrescar(self) -> bool:
        """Vuelve a preguntar a Windows. False si se hizo hace muy poco o falla."""
        if time.time() - self._actualizado < REFRESCO_MIN and self._programas:
            return False
        try:
            nuevos = [p for p in self._listar() if es_util(p)]
        except Exception:
            return False
        with self._lock:
            self._programas, self._actualizado = nuevos, time.time()
            self.archivo.parent.mkdir(exist_ok=True)
            self.archivo.write_text(json.dumps({"actualizado": self._actualizado,
                                                "programas": [asdict(p) for p in nuevos]},
                                               ensure_ascii=False), encoding="utf-8")
        return True

    def refrescar_en_segundo_plano(self) -> None:
        threading.Thread(target=self.refrescar, daemon=True, name="programas").start()

    @property
    def programas(self) -> list[Programa]:
        if not self._programas or time.time() - self._actualizado > CADUCIDAD:
            self.refrescar()
        return self._programas

    def buscar(self, consulta: str) -> tuple[Programa | None, list[str]]:
        """Devuelve (programa, sugerencias). Si no lo encuentra, refresca una vez (quizá es nuevo)."""
        encontrado, sugerencias = buscar(consulta, self.programas)
        if encontrado is None and self.refrescar():
            encontrado, sugerencias = buscar(consulta, self._programas)
        return encontrado, sugerencias


def puntuar(consulta: str, nombre: str) -> float:
    """Parecido entre lo que se pidió y el nombre del programa (0 a 1)."""
    c, n = normalizar(consulta), normalizar(nombre)
    if not c or not n:
        return 0.0
    if c == n:
        return 1.0
    palabras = n.split()
    if f" {c} " in f" {n} ":  # "steam" en "steam", "code" en "visual studio code"
        return 0.95 - 0.01 * (len(palabras) - len(c.split()))  # mejor cuanto menos sobra
    if n.startswith(c) and len(c) >= 4:  # "photo" -> "photoshop"
        return 0.85
    siglas = "".join(p[0] for p in palabras if p)
    if len(c) >= 2 and c.replace(" ", "") == siglas:  # "vs code" no; "vlc" sí
        return 0.85
    return SequenceMatcher(None, c, n).ratio()


def buscar(consulta: str, programas: list[Programa]) -> tuple[Programa | None, list[str]]:
    if not programas:
        return None, []
    puntuados = sorted(((puntuar(consulta, p.nombre), -len(p.nombre), p) for p in programas),
                       key=lambda x: (x[0], x[1]), reverse=True)
    mejor_puntos, _, mejor = puntuados[0]
    if mejor_puntos >= SIMILITUD_MIN:
        return mejor, []
    sugerencias = list(dict.fromkeys(p.nombre for puntos, _, p in puntuados[:5] if puntos >= 0.6))[:3]
    return None, sugerencias


def abrir(p: Programa) -> None:
    if "://" in p.appid:  # steam://rungameid/..., com.epicgames.launcher://...
        os.startfile(p.appid)
    else:  # funciona para programas clásicos y apps de la Tienda
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{p.appid}"], creationflags=SIN_VENTANA)


def listar_de_windows() -> list[Programa]:
    comando = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
               "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    salida = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
                            capture_output=True, text=True, encoding="utf-8", timeout=30,
                            creationflags=SIN_VENTANA, check=True).stdout
    datos = json.loads(salida or "[]")
    if isinstance(datos, dict):
        datos = [datos]
    return [Programa(d["Name"], d["AppID"]) for d in datos if d.get("Name") and d.get("AppID")]


_catalogo: Catalogo | None = None


def catalogo() -> Catalogo:
    global _catalogo
    if _catalogo is None:
        _catalogo = Catalogo()
    return _catalogo
