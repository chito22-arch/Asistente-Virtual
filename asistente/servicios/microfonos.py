"""Qué micrófono usa Jarvis. Se elige por nombre y se guarda en .env (MICROFONO=...).

Se graba con la API "MME" de Windows (convierte a 16 kHz sin problemas), pero MME corta
los nombres a 31 letras, así que el nombre completo se toma de las otras APIs.
"""
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import sounddevice as sd

from .programas import normalizar, puntuar

ENV = Path(__file__).resolve().parents[2] / ".env"
POR_DEFECTO = ""  # vacío = el micrófono predeterminado de Windows
OCULTOS = re.compile(r"asignador de sonido|controlador primario|mezcla est[eé]reo|stereo mix|l[ií]nea de entrada", re.I)
PALABRAS_AURICULARES = re.compile(r"auricular|headset|headphone|hands-free|cascos|airpods|buds", re.I)

# Mientras haya un stream de audio abierto no se puede refrescar la lista de dispositivos.
EN_USO = threading.RLock()


@dataclass(frozen=True)
class Microfono:
    indice: int
    nombre: str

    @property
    def es_auricular(self) -> bool:
        return bool(PALABRAS_AURICULARES.search(self.nombre))


_suscriptores: list[Callable[[str], None]] = []
_cache: list[Microfono] | None = None


def _leer_dispositivos() -> list[Microfono]:
    apis = sd.query_hostapis()
    dispositivos = list(enumerate(sd.query_devices()))
    entradas = [(i, d) for i, d in dispositivos if d["max_input_channels"] > 0]
    mme = [(i, d) for i, d in entradas if apis[d["hostapi"]]["name"] == "MME"]
    otros = [d["name"] for i, d in entradas if apis[d["hostapi"]]["name"] != "MME" and "\n" not in d["name"]]
    resultado = []
    for i, d in mme:
        if OCULTOS.search(d["name"]):
            continue
        completo = max((n for n in otros if n.startswith(d["name"])), key=len, default=d["name"])
        resultado.append(Microfono(i, completo))
    return resultado


def listar(refrescar: bool = False) -> list[Microfono]:
    """Micrófonos disponibles. refrescar=True detecta los recién conectados (si no hay audio en uso)."""
    global _cache
    if refrescar and EN_USO.acquire(blocking=False):
        try:
            sd._terminate()
            sd._initialize()
            _cache = None
        finally:
            EN_USO.release()
    if _cache is None:
        _cache = _leer_dispositivos()
    return _cache


def configurado() -> str:
    return os.getenv("MICROFONO", POR_DEFECTO).strip()


def buscar(consulta: str, lista: list[Microfono] | None = None) -> list[Microfono]:
    """Micrófonos que encajan con lo pedido ("auriculares", "oppo", "2", "realtek")."""
    lista = listar() if lista is None else lista
    consulta = consulta.strip()
    if consulta.isdigit():
        n = int(consulta)
        return [lista[n - 1]] if 1 <= n <= len(lista) else []
    c = normalizar(consulta)
    if re.search(r"\b(auriculares?|cascos|headset|bluetooth|inalambric)", c):
        return [m for m in lista if m.es_auricular]
    if re.search(r"\b(ordenador|pc|portatil|integrado|del equipo|tarjeta)\b", c):
        return [m for m in lista if "realtek" in m.nombre.lower() or not m.es_auricular][:1]
    exactos = [m for m in lista if c and c in normalizar(m.nombre)]
    if exactos:
        return exactos
    puntuados = sorted(((puntuar(consulta, m.nombre), m) for m in lista), key=lambda x: x[0], reverse=True)
    return [m for p, m in puntuados[:1] if p >= 0.6]


def actual() -> Microfono | None:
    """El micrófono configurado si está conectado; None = el predeterminado de Windows."""
    nombre = configurado()
    if not nombre:
        return None
    return next((m for m in listar() if m.nombre == nombre), None) or \
        next((m for m in listar() if normalizar(nombre) in normalizar(m.nombre)), None)


def nombre_predeterminado() -> str:
    """Nombre completo del micrófono predeterminado de Windows."""
    try:
        corto = sd.query_devices(kind="input")["name"]
    except Exception:
        return "el de Windows"
    return next((m.nombre for m in listar() if m.nombre.startswith(corto)), corto)


def nombre_en_uso() -> str:
    if m := actual():
        return m.nombre
    return f"{nombre_predeterminado()} (predeterminado de Windows)"


def indice() -> int | None:
    m = actual()
    return m.indice if m else None


def elegir(nombre: str) -> None:
    """Guarda la elección (vacío = predeterminado) y avisa a quien escuche (el bucle de voz recalibra)."""
    os.environ["MICROFONO"] = nombre
    try:
        from dotenv import set_key

        if ENV.exists():
            set_key(str(ENV), "MICROFONO", nombre, quote_mode="never")
    except Exception:
        pass
    for funcion in list(_suscriptores):
        funcion(nombre)


def suscribir(funcion: Callable[[str], None]) -> None:
    _suscriptores.append(funcion)
