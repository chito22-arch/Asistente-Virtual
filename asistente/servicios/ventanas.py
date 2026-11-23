"""Programas abiertos: qué ventanas hay, de qué programa son y cómo cerrarlos.

Cerrar = pedir a cada ventana que se cierre (como pulsar la X), así el programa puede
preguntarte si quieres guardar. Forzar = terminar el proceso (solo con confirmación).
"""
import ctypes
import ctypes.wintypes as wt
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import psutil

from .programas import puntuar

user32 = ctypes.windll.user32
version = ctypes.windll.version
dwmapi = ctypes.windll.dwmapi

WM_CLOSE = 0x0010
GW_OWNER = 4
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14

SIMILITUD_MIN = 0.78
PESO_TITULO = 0.85  # el título de una ventana puede ser cualquier cosa ("Discord - Google Chrome")
MARCO_UWP = "applicationframehost.exe"  # aloja apps de la Tienda: cada ventana es una app distinta

# Nunca se fuerzan: el sistema dejaría de funcionar (o Jarvis se cerraría a sí mismo).
PROTEGIDOS = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
    "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "sihost.exe", "fontdrvhost.exe",
    "taskhostw.exe", "ctfmon.exe", "applicationframehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "shellexperiencehost.exe", "textinputhost.exe", "runtimebroker.exe", "lockapp.exe",
}


@dataclass
class Abierto:
    """Un programa con ventanas visibles."""
    pids: set[int]
    exe: str  # "discord.exe"
    descripcion: str  # "Discord" (descripción del ejecutable)
    titulos: list[str] = field(default_factory=list)
    ventanas: list[int] = field(default_factory=list)
    uwp: bool = False  # app de la Tienda dentro de ApplicationFrameHost
    alias: list[str] = field(default_factory=list)  # nombre en el menú Inicio ("Notepad" -> "Bloc de notas")

    @property
    def nombre(self) -> str:
        if self.uwp and self.titulos:
            return self.titulos[0]
        if self.alias:
            return self.alias[0]
        nombre = self.descripcion or Path(self.exe).stem.capitalize()
        # "WhatsApp.Root" -> si alguna ventana se titula "WhatsApp", queda mejor dicho así.
        corto = next((t for t in self.titulos if len(t) <= 25 and t.lower() in nombre.lower()), None)
        return corto or nombre


# --- ventanas -----------------------------------------------------------------

def _es_ventana_de_programa(hwnd) -> bool:
    if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    oculta = ctypes.c_int(0)  # apps de la Tienda suspendidas: "visibles" pero ocultas
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(oculta), ctypes.sizeof(oculta))
    return not oculta.value and user32.GetWindowTextLengthW(hwnd) > 0


def _ventanas() -> list[tuple[int, int, str]]:
    """(hwnd, pid, título) de las ventanas principales visibles."""
    resultado = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cada(hwnd, _):
        if _es_ventana_de_programa(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            resultado.append((hwnd, pid.value, buf.value))
        return True

    user32.EnumWindows(cada, 0)
    return resultado


@lru_cache(maxsize=256)
def descripcion_exe(ruta: str) -> str:
    """'Descripción del archivo' de un .exe (p. ej. Code.exe -> 'Visual Studio Code')."""
    try:
        tam = version.GetFileVersionInfoSizeW(ruta, None)
        if not tam:
            return ""
        datos = ctypes.create_string_buffer(tam)
        if not version.GetFileVersionInfoW(ruta, 0, tam, datos):
            return ""
        ptr, largo = ctypes.c_void_p(), wt.UINT()
        if not version.VerQueryValueW(datos, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(largo)):
            return ""
        idioma, pagina = ctypes.cast(ptr, ctypes.POINTER(wt.WORD * 2)).contents
        clave = f"\\StringFileInfo\\{idioma:04x}{pagina:04x}\\FileDescription"
        if not version.VerQueryValueW(datos, clave, ctypes.byref(ptr), ctypes.byref(largo)) or not largo.value:
            return ""
        return ctypes.wstring_at(ptr).strip()  # hasta el primer nulo (el largo no es fiable)
    except OSError:
        return ""


def _info_proceso(pid: int) -> tuple[str, str]:
    """(exe en minúsculas, descripción)."""
    try:
        proceso = psutil.Process(pid)
        try:
            ruta = proceso.exe()
        except (psutil.AccessDenied, OSError):
            return proceso.name().lower(), ""
        return Path(ruta).name.lower(), descripcion_exe(ruta)
    except psutil.Error:
        return "", ""


def abiertos() -> list[Abierto]:
    """Programas con ventanas visibles, agrupados por ejecutable."""
    propios = _pids_propios()
    por_exe: dict[str, Abierto] = {}
    resultado: list[Abierto] = []
    for hwnd, pid, titulo in _ventanas():
        if pid in propios:
            continue
        exe, desc = _info_proceso(pid)
        if not exe:
            continue
        if exe == MARCO_UWP:
            resultado.append(Abierto({pid}, exe, titulo, [titulo], [hwnd], uwp=True))
            continue
        a = por_exe.setdefault(exe, Abierto(set(), exe, desc))
        a.pids.add(pid)
        a.titulos.append(titulo)
        a.ventanas.append(hwnd)
    for a in por_exe.values():
        a.alias = _alias_menu_inicio(a.exe)
    return list(por_exe.values()) + resultado


def _alias_menu_inicio(exe: str) -> list[str]:
    """Nombres del menú Inicio cuyo identificador contiene el del ejecutable (notepad -> 'Bloc de notas')."""
    from .programas import catalogo, normalizar

    raiz = normalizar(Path(exe).stem).replace(" ", "")
    if len(raiz) < 4:
        return []
    try:
        lista = catalogo().programas
    except Exception:
        return []
    return [p.nombre for p in lista if raiz in normalizar(p.appid).replace(" ", "")][:3]


def _pids_propios() -> set[int]:
    try:
        yo = psutil.Process(os.getpid())
        return {yo.pid, *(p.pid for p in yo.parents())}
    except psutil.Error:
        return {os.getpid()}


# --- búsqueda -----------------------------------------------------------------

def puntuacion(consulta: str, a: Abierto) -> float:
    nombres = [a.descripcion, Path(a.exe).stem, *a.alias]
    titulos = max((puntuar(consulta, t) for t in a.titulos), default=0.0)
    return max([puntuar(consulta, n) for n in nombres if n] + [titulos if a.uwp else titulos * PESO_TITULO])


def buscar(consulta: str, lista: list[Abierto] | None = None) -> Abierto | None:
    lista = abiertos() if lista is None else lista
    puntuados = sorted(((puntuacion(consulta, a), a) for a in lista), key=lambda x: x[0], reverse=True)
    if puntuados and puntuados[0][0] >= SIMILITUD_MIN:
        return puntuados[0][1]
    return None


def en_segundo_plano(consulta: str) -> list[psutil.Process]:
    """Procesos sin ventana (p. ej. Discord en la bandeja) cuyo programa se parece a la consulta."""
    propios = _pids_propios()
    candidatos: dict[str, list[psutil.Process]] = {}
    puntos: dict[str, float] = {}
    for p in psutil.process_iter(["name", "exe"]):
        nombre = (p.info["name"] or "").lower()
        if not nombre or nombre in PROTEGIDOS or p.pid in propios:
            continue
        if nombre not in puntos:
            desc = descripcion_exe(p.info["exe"]) if p.info["exe"] else ""
            puntos[nombre] = max(puntuar(consulta, Path(nombre).stem), puntuar(consulta, desc) if desc else 0.0)
        if puntos[nombre] >= SIMILITUD_MIN:
            candidatos.setdefault(nombre, []).append(p)
    if not candidatos:
        return []
    mejor = max(candidatos, key=lambda n: puntos[n])
    return candidatos[mejor]


# --- cerrar -------------------------------------------------------------------

def pedir_cierre(a: Abierto) -> None:
    for hwnd in a.ventanas:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def esperar_cierre(a: Abierto, segundos: float = 3.0) -> str:
    """'cerrado', 'segundo_plano' (sin ventanas pero el proceso sigue) o 'abierto' (p. ej. pregunta si guardar)."""
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if not any(user32.IsWindow(h) and user32.IsWindowVisible(h) for h in a.ventanas):
            break
        time.sleep(0.2)
    else:
        return "abierto"
    if a.uwp:
        return "cerrado"
    time.sleep(0.5)
    return "segundo_plano" if any(psutil.pid_exists(p) for p in a.pids) else "cerrado"


def forzar(exe: str) -> int:
    """Termina todos los procesos de ese ejecutable. Devuelve cuántos."""
    exe = exe.lower()
    if exe in PROTEGIDOS:
        raise PermissionError(f"{exe} es parte de Windows; no lo cierro a la fuerza.")
    propios = _pids_propios()
    procesos = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == exe
                and p.pid not in propios]
    for p in procesos:
        try:
            p.terminate()
        except psutil.Error:
            pass
    psutil.wait_procs(procesos, timeout=3)
    return len(procesos)
