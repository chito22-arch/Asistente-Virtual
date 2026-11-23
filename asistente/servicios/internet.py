"""Información de internet sin cuentas ni APIs de pago.

- Búsquedas y noticias: DuckDuckGo (librería `ddgs`).
- El tiempo: Open-Meteo (https://open-meteo.com), gratuito y sin clave.
"""
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser

from ..utils import fechas

REGION = "es-es"
TIEMPO_ESPERA = 10


@dataclass
class Resultado:
    titulo: str
    url: str
    texto: str
    fecha: str = ""
    fuente: str = ""  # periódico, en las noticias

    @property
    def dominio(self) -> str:
        return urllib.parse.urlparse(self.url).netloc.removeprefix("www.")


class SinConexion(Exception):
    pass


# --- búsquedas -----------------------------------------------------------------

PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "un", "una", "en", "que", "qué", "y", "a", "por", "para",
                   "con", "su", "sus", "es", "al"}


def _simplificar(consulta: str) -> str:
    """'hora del partido del Real Madrid' -> 'hora partido Real Madrid' (a veces encuentra más)."""
    return " ".join(p for p in consulta.split() if p.lower() not in PALABRAS_VACIAS)


def buscar(consulta: str, n: int = 5) -> list[Resultado]:
    """Los buscadores gratuitos fallan a ratos: se reintenta con otros y con la frase simplificada."""
    from ddgs import DDGS

    intentos = [(consulta, "auto"), (consulta, "google"), (_simplificar(consulta), "auto")]
    error = None
    for texto, motor in dict.fromkeys(intentos):
        try:
            datos = DDGS(timeout=TIEMPO_ESPERA).text(texto, region=REGION, max_results=n, backend=motor) or []
        except Exception as e:
            if "no results" not in str(e).lower():
                error = e
            continue
        if datos:
            return [Resultado(d.get("title", ""), d.get("href", ""), d.get("body", "")) for d in datos]
    if error is not None:
        raise SinConexion(str(error)) from error
    return []


def noticias(tema: str = "", n: int = 5) -> list[Resultado]:
    """Noticias recientes (de hoy; si no hay, de esta semana), las más nuevas primero."""
    from ddgs import DDGS

    consulta = tema or "noticias España"
    for periodo in ("d", "w"):
        try:
            datos = DDGS(timeout=TIEMPO_ESPERA).news(consulta, region=REGION, timelimit=periodo, max_results=n * 2)
        except Exception as e:
            if "no results" in str(e).lower():
                continue
            raise SinConexion(str(e)) from e
        datos = [d for d in datos or [] if not TITULAR_VACIO.search(d.get("title", ""))]
        if datos:
            datos = sorted(datos, key=lambda d: d.get("date", ""), reverse=True)[:n]
            return [Resultado(d.get("title", ""), d.get("url", ""), d.get("body", ""),
                              d.get("date", "")[:10], d.get("source", "")) for d in datos]
    return []


# Portadas genéricas que aparecen como "noticia": no dicen nada.
TITULAR_VACIO = re.compile(r"^\s*(?:[uú]ltimas noticias|noticias de (?:hoy|[uú]ltima hora)|[uú]ltima hora|"
                           r"portada|noticias de hoy,? \w+ \d+)\b", re.I)


# --- leer páginas ------------------------------------------------------------------

class _Parrafos(HTMLParser):
    """Saca el texto de los párrafos, encabezados y listas de una página (sin menús ni scripts)."""
    UTILES = {"p", "li", "h1", "h2", "h3", "td"}
    IGNORAR = {"script", "style", "nav", "footer", "header", "aside", "form"}

    def __init__(self) -> None:
        super().__init__()
        self.bloques: list[str] = []
        self._actual: list[str] = []
        self._dentro = 0
        self._ignorar = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR:
            self._ignorar += 1
        elif tag in self.UTILES:
            self._dentro += 1

    def handle_endtag(self, tag):
        if tag in self.IGNORAR:
            self._ignorar = max(0, self._ignorar - 1)
        elif tag in self.UTILES and self._dentro:
            self._dentro -= 1
            texto = " ".join("".join(self._actual).split())
            if len(texto) > 40:
                self.bloques.append(texto)
            self._actual = []

    def handle_data(self, data):
        if self._dentro and not self._ignorar:
            self._actual.append(data)


def leer_pagina(url: str, consulta: str, max_caracteres: int = 1200) -> str:
    """Párrafos de la página que mencionan lo buscado (vacío si no se puede leer)."""
    peticion = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                                    "Accept-Language": "es-ES,es;q=0.9"})
    try:
        with urllib.request.urlopen(peticion, timeout=6) as r:
            if "html" not in r.headers.get("Content-Type", ""):
                return ""
            html = r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return ""
    lector = _Parrafos()
    try:
        lector.feed(html)
    except Exception:
        return ""
    palabras = {p for p in re.findall(r"\w+", consulta.lower()) if len(p) > 3}
    relevantes = [b for b in lector.bloques if any(p in b.lower() for p in palabras)] or lector.bloques[:3]
    texto, total = [], 0
    for bloque in relevantes:
        if total + len(bloque) > max_caracteres:
            break
        texto.append(bloque)
        total += len(bloque)
    return " ".join(texto)


def buscar_a_fondo(consulta: str, n: int = 5, paginas: int = 2) -> list[Resultado]:
    """Búsqueda + lectura en paralelo de las primeras páginas (para datos que no salen en el resumen)."""
    resultados = buscar(consulta, n)
    hilos = []
    for r in resultados[:paginas]:
        def leer(r=r):
            if extra := leer_pagina(r.url, consulta):
                r.texto = f"{r.texto} … {extra}"
        hilo = threading.Thread(target=leer, daemon=True)
        hilo.start()
        hilos.append(hilo)
    for hilo in hilos:
        hilo.join(timeout=7)
    return resultados


def para_ia(resultados: list[Resultado]) -> str:
    """Resultados numerados para que la IA responda con ellos."""
    if not resultados:
        return "La búsqueda no ha devuelto resultados."
    return "\n".join(f"[{i}] {r.titulo} ({r.fuente or r.dominio}{', ' + r.fecha if r.fecha else ''}): {r.texto}"
                     for i, r in enumerate(resultados, 1))


def fuentes(resultados: list[Resultado], n: int = 3) -> str:
    return "Fuentes: " + ", ".join(dict.fromkeys(r.dominio for r in resultados[:n] if r.dominio))


# --- el tiempo -------------------------------------------------------------------

CODIGOS_TIEMPO = {
    0: "despejado", 1: "casi despejado", 2: "parcialmente nublado", 3: "nublado", 45: "niebla", 48: "niebla",
    51: "llovizna débil", 53: "llovizna", 55: "llovizna intensa", 61: "lluvia débil", 63: "lluvia",
    65: "lluvia intensa", 66: "lluvia helada", 67: "lluvia helada", 71: "nieve débil", 73: "nieve",
    75: "nieve intensa", 77: "granizo fino", 80: "chubascos", 81: "chubascos", 82: "chubascos fuertes",
    85: "chubascos de nieve", 86: "chubascos de nieve", 95: "tormenta", 96: "tormenta con granizo",
    99: "tormenta con granizo",
}


def _get_json(url: str, params: dict) -> dict:
    peticion = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                      headers={"User-Agent": "AsistenteVirtual/1.5"})
    try:
        with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA) as r:
            return json.loads(r.read().decode("utf-8"))
    except OSError as e:
        raise SinConexion(str(e)) from e


def ciudad_por_defecto() -> str:
    return os.getenv("CIUDAD", "").strip()


def tiempo(ciudad: str = "", dia: date | None = None) -> str:
    ciudad = ciudad.strip() or ciudad_por_defecto()
    if not ciudad:
        return "¿De qué ciudad? Di por ejemplo 'qué tiempo hace en Madrid' (o pon CIUDAD=... en .env)."
    lugares = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                        {"name": ciudad, "count": 1, "language": "es"}).get("results") or []
    if not lugares:
        return f"No encuentro la ciudad «{ciudad}»."
    lugar = lugares[0]
    datos = _get_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": lugar["latitude"], "longitude": lugar["longitude"], "timezone": "auto", "forecast_days": 16,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    nombre = lugar["name"]
    hoy = date.fromisoformat(datos["daily"]["time"][0])
    dia = dia or hoy
    if dia == hoy and "current" in datos:
        actual = datos["current"]
        ahora = (f"Ahora en {nombre}: {round(actual['temperature_2m'])} grados, "
                 f"{CODIGOS_TIEMPO.get(actual['weather_code'], 'tiempo variable')}. ")
    else:
        ahora = ""
    dias = datos["daily"]["time"]
    if dia.isoformat() not in dias:
        return f"Solo tengo la previsión de los próximos {len(dias)} días."
    i = dias.index(dia.isoformat())
    d = datos["daily"]
    cuando = "Hoy" if dia == hoy else ("Mañana" if (dia - hoy).days == 1 else
                                      f"El {fechas.DIAS[dia.weekday()]} {dia.day}")
    lluvia = d["precipitation_probability_max"][i]
    return (f"{ahora}{cuando}{'' if ahora else ' en ' + nombre}: {CODIGOS_TIEMPO.get(d['weather_code'][i], 'variable')}, "
            f"entre {round(d['temperature_2m_min'][i])} y {round(d['temperature_2m_max'][i])} grados"
            + (f", {lluvia}% de probabilidad de lluvia." if lluvia is not None else "."))
