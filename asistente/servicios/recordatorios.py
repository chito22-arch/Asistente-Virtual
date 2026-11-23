"""Recordatorios y temporizadores: se guardan en disco y un hilo avisa cuando vencen.

Quien quiera enterarse de los avisos (voz, consola, icono de la bandeja) se suscribe con
`gestor().suscribir(funcion)`; la función recibe el texto del aviso.
"""
import json
import threading
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from ..utils import fechas

ARCHIVO = Path(__file__).resolve().parents[2] / ".jarvis" / "recordatorios.json"
RETRASO_AVISABLE = timedelta(minutes=2)  # más tarde que esto se indica "era para las..."


@dataclass
class Recordatorio:
    id: int
    cuando: datetime
    mensaje: str  # puede estar vacío en un temporizador
    tipo: str  # "temporizador" o "recordatorio"
    duracion_seg: int | None = None  # solo temporizadores

    def texto_aviso(self, ahora: datetime) -> str:
        if self.mensaje:
            texto = f"Recordatorio: {self.mensaje}."
        else:
            texto = f"¡Tiempo! Se acabó el temporizador de {fechas.duracion_legible(timedelta(seconds=self.duracion_seg or 0))}."
        if ahora - self.cuando > RETRASO_AVISABLE:
            texto += f" (Era para las {self.cuando:%H:%M}" + (
                f" del {fechas.formatear_dia(self.cuando.date())})" if self.cuando.date() != ahora.date() else ")")
        return texto

    def describir(self, ahora: datetime) -> str:
        """Texto para listarlo: 'Llamar a mamá — a las 18:20 (en 15 minutos)'."""
        nombre = self.mensaje or f"Temporizador de {fechas.duracion_legible(timedelta(seconds=self.duracion_seg or 0))}"
        falta = self.cuando - ahora
        cuando = f"a las {self.cuando:%H:%M}" if self.cuando.date() == ahora.date() else \
            f"el {fechas.formatear_dia(self.cuando.date())} a las {self.cuando:%H:%M}"
        if falta < timedelta(hours=12):
            cuando += f" (en {fechas.duracion_legible(timedelta(seconds=max(0, round(falta.total_seconds()))))})"
        return f"{nombre} — {cuando}"


class Gestor:
    def __init__(self, archivo: Path = ARCHIVO) -> None:
        self.archivo = archivo
        self._lock = threading.RLock()
        self._items: list[Recordatorio] = []
        self._suscriptores: list[Callable[[str], None]] = []
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._cargar()

    # --- persistencia -----------------------------------------------------

    def _cargar(self) -> None:
        if not self.archivo.exists():
            return
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
            self._items = [Recordatorio(**{**d, "cuando": datetime.fromisoformat(d["cuando"])}) for d in datos]
        except (ValueError, KeyError, TypeError):
            traceback.print_exc()
            self._items = []

    def _guardar(self) -> None:
        self.archivo.parent.mkdir(exist_ok=True)
        datos = [{**asdict(r), "cuando": r.cuando.isoformat()} for r in self._items]
        self.archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- operaciones ------------------------------------------------------

    def crear(self, cuando: datetime, mensaje: str = "", tipo: str = "recordatorio",
              duracion: timedelta | None = None) -> Recordatorio:
        with self._lock:
            nuevo = Recordatorio(max((r.id for r in self._items), default=0) + 1, cuando, mensaje.strip(), tipo,
                                 int(duracion.total_seconds()) if duracion else None)
            self._items.append(nuevo)
            self._guardar()
            return nuevo

    def pendientes(self, tipo: str | None = None) -> list[Recordatorio]:
        with self._lock:
            return sorted((r for r in self._items if tipo in (None, r.tipo)), key=lambda r: r.cuando)

    def cancelar(self, recordatorios: list[Recordatorio]) -> int:
        ids = {r.id for r in recordatorios}
        with self._lock:
            antes = len(self._items)
            self._items = [r for r in self._items if r.id not in ids]
            self._guardar()
            return antes - len(self._items)

    # --- avisos -----------------------------------------------------------

    def suscribir(self, funcion: Callable[[str], None]) -> None:
        self._suscriptores.append(funcion)

    def revisar(self, ahora: datetime | None = None) -> list[str]:
        """Dispara los vencidos. Devuelve los textos avisados."""
        ahora = ahora or datetime.now()
        with self._lock:
            vencidos = [r for r in self._items if r.cuando <= ahora]
            if not vencidos:
                return []
            self._items = [r for r in self._items if r.cuando > ahora]
            self._guardar()
        textos = [r.texto_aviso(ahora) for r in sorted(vencidos, key=lambda r: r.cuando)]
        for texto in textos:
            print(f"⏰ {texto}")
            for funcion in list(self._suscriptores):
                try:
                    funcion(texto)
                except Exception:
                    traceback.print_exc()
        return textos

    def iniciar(self) -> None:
        """Vigila en segundo plano (una comprobación por segundo)."""
        if self._hilo and self._hilo.is_alive():
            return
        self._parar.clear()

        def vigilar() -> None:
            while not self._parar.wait(1):
                self.revisar()

        self._hilo = threading.Thread(target=vigilar, daemon=True, name="recordatorios")
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()


_gestor: Gestor | None = None


def gestor() -> Gestor:
    global _gestor
    if _gestor is None:
        _gestor = Gestor()
    return _gestor


def sonar() -> None:
    """Sonido de aviso de Windows (no falla fuera de Windows)."""
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass
