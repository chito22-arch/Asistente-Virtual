"""Interpreta fechas, horas y duraciones escritas en español.

Ejemplos: "mañana", "pasado mañana", "el viernes", "25/12", "3 de marzo",
"a las 17:30", "a las 5 de la tarde", "a las 9 y media", "durante 2 horas".
"""
import re
from datetime import date, time, timedelta

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_SIN_TILDE = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_DIA = "|".join(DIAS + DIAS_SIN_TILDE)
_MES = "|".join(MESES)

# Cada patrón incluye las palabras de enlace ("el", "para el"...) para poder quitarlo del título.
RE_PASADO_MANANA = re.compile(r"(?:para )?\bpasado mañana\b", re.I)
RE_MANANA = re.compile(r"(?:para )?(?<!la )(?<!de )\bmañana\b", re.I)
RE_HOY = re.compile(r"(?:para )?\bhoy\b", re.I)
RE_DIA_SEMANA = re.compile(rf"(?:para )?(?:el |este |el próximo |el proximo |próximo |proximo )?\b({_DIA})\b", re.I)
RE_NUMERICA = re.compile(r"(?:para )?(?:el )?\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", re.I)
RE_TEXTO = re.compile(rf"(?:para )?(?:el )?\b(\d{{1,2}}) de ({_MES})(?: de (\d{{4}}))?\b", re.I)

RE_HORA = re.compile(
    r"\ba (?:las|la) (\d{1,2})(?:[:.](\d{2}))?(?: (y media|y cuarto|menos cuarto))?"
    r"(?: ?(?:h|hrs?|horas?)\b)?(?: (?:de la|por la) (mañana|tarde|noche))?",
    re.I,
)
RE_DURACION = re.compile(r"\b(?:durante|por|de) (\d+) (horas?|minutos?|min)\b", re.I)


def _proximo_dia_semana(hoy: date, indice: int) -> date:
    dias = (indice - hoy.weekday()) % 7
    return hoy + timedelta(days=dias or 7)


def _construir(hoy: date, dia: int, mes: int, anio: int | None) -> date | None:
    try:
        f = date(anio or hoy.year, mes, dia)
    except ValueError:
        return None
    if anio is None and f < hoy:
        f = f.replace(year=f.year + 1)
    return f


def buscar_fecha(texto: str, hoy: date) -> tuple[date | None, re.Match | None]:
    """Devuelve (fecha, coincidencia) o (None, None) si el texto no menciona ninguna fecha."""
    if m := RE_PASADO_MANANA.search(texto):
        return hoy + timedelta(days=2), m
    if m := RE_MANANA.search(texto):
        return hoy + timedelta(days=1), m
    if m := RE_HOY.search(texto):
        return hoy, m
    if m := RE_TEXTO.search(texto):
        anio = int(m.group(3)) if m.group(3) else None
        return _construir(hoy, int(m.group(1)), MESES.index(m.group(2).lower()) + 1, anio), m
    if m := RE_NUMERICA.search(texto):
        anio = int(m.group(3)) if m.group(3) else None
        if anio is not None and anio < 100:
            anio += 2000
        return _construir(hoy, int(m.group(1)), int(m.group(2)), anio), m
    if m := RE_DIA_SEMANA.search(texto):
        nombre = m.group(1).lower()
        indice = DIAS.index(nombre) if nombre in DIAS else DIAS_SIN_TILDE.index(nombre)
        return _proximo_dia_semana(hoy, indice), m
    return None, None


def buscar_hora(texto: str) -> tuple[time | None, re.Match | None]:
    m = RE_HORA.search(texto)
    if not m:
        return None, None
    h, minutos = int(m.group(1)), int(m.group(2) or 0)
    extra, momento = (m.group(3) or "").lower(), (m.group(4) or "").lower()
    if extra == "y media":
        minutos = 30
    elif extra == "y cuarto":
        minutos = 15
    elif extra == "menos cuarto":
        h, minutos = h - 1, 45
    if momento in ("tarde", "noche") and h < 12:
        h += 12
    if not (0 <= h < 24 and 0 <= minutos < 60):
        return None, None
    return time(h, minutos), m


def buscar_duracion(texto: str) -> tuple[timedelta | None, re.Match | None]:
    m = RE_DURACION.search(texto)
    if not m:
        return None, None
    n = int(m.group(1))
    return (timedelta(hours=n) if m.group(2).lower().startswith("hora") else timedelta(minutes=n)), m


def quitar(texto: str, *coincidencias: re.Match | None) -> str:
    """Elimina del texto los fragmentos encontrados (fecha, hora...) para dejar solo el título."""
    tramos = sorted((m.span() for m in coincidencias if m), reverse=True)
    for ini, fin in tramos:
        texto = texto[:ini] + " " + texto[fin:]
    return re.sub(r"\s+", " ", texto).strip()


def formatear_dia(f: date) -> str:
    return f"{DIAS_CORTOS[f.weekday()]} {f:%d/%m}"
