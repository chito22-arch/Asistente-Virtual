import re
from datetime import date

from ..servicios import internet
from ..utils import fechas
from .base import Skill

RE_TIEMPO = re.compile(r"\b(?:qu[eé] )?tiempo (?:hace|har[aá]|va a hacer)\b|\bva a llover\b|\bllover[aá]\b"
                       r"|\b(?:qu[eé] )?temperatura\b|\bprevisi[oó]n del tiempo\b|\bel tiempo (?:de|en|para)\b")
RE_NOTICIAS = re.compile(r"\b(?:noticias|titulares)\b(?:\s+(?:de|sobre|del|de la)\s+(?P<tema>.+))?")
RE_BUSCAR = re.compile(
    r"^(?:busca|b[uú]scame|investiga|averigua)\s+(?:en (?:internet|google|la web)\s+)?(?P<q>.+?)"
    r"(?:\s+en (?:internet|google|la web))?$")
RE_CIUDAD = re.compile(r"\ben\s+(?:la ciudad de\s+)?(?P<ciudad>[a-záéíóúñü][a-záéíóúñü .'-]*?)\s*$", re.I)


class InternetSkill(Skill):
    nombre = "internet"
    descripcion = ("Internet: 'qué tiempo hace en Madrid', 'va a llover mañana', 'noticias de hoy', "
                   "'noticias sobre el Real Madrid', 'busca en internet ...' — y lo que no entienda, lo busca")

    def puede_manejar(self, texto: str) -> bool:
        return bool(RE_TIEMPO.search(texto) or RE_NOTICIAS.search(texto) or RE_BUSCAR.match(texto))

    def directo(self, texto: str) -> bool:
        # Con IA: el tiempo y los titulares van directos; las búsquedas las resume la IA.
        return bool(RE_TIEMPO.search(texto) or (RE_NOTICIAS.search(texto) and not RE_BUSCAR.match(texto)))

    def ejecutar(self, texto: str, original: str) -> str:
        try:
            if RE_TIEMPO.search(texto):
                return self.tiempo(original)
            if (m := RE_NOTICIAS.search(texto)) and not RE_BUSCAR.match(texto):
                return self.titulares((m["tema"] or "").strip())
            m = RE_BUSCAR.match(texto)
            return self.responder(m["q"] if m else original)
        except internet.SinConexion:
            return "No puedo conectarme a internet ahora mismo."

    # --- acciones -----------------------------------------------------------

    def tiempo(self, frase: str) -> str:
        dia, m_fecha = fechas.buscar_fecha(frase, date.today())
        sin_fecha = fechas.quitar(frase, m_fecha).strip(" ?¿.!¡")
        m = RE_CIUDAD.search(sin_fecha)
        return internet.tiempo(m["ciudad"].strip() if m else "", dia)

    def titulares(self, tema: str = "") -> str:
        tema = re.sub(r"\b(?:de |del )?(?:hoy|ayer|[uú]ltima hora|esta semana|este d[ií]a)\b", "", tema).strip()
        lista = internet.noticias(tema)
        if not lista:
            return f"No encuentro noticias recientes{' sobre ' + tema if tema else ''}."
        cabecera = f"Noticias{' sobre ' + tema if tema else ''}:"
        return cabecera + "\n" + "\n".join(f"  {i}. {r.titulo}" + (f" ({r.fuente})" if r.fuente else "")
                                           for i, r in enumerate(lista, 1))

    def responder(self, pregunta: str) -> str:
        """Sin IA: el mejor resultado de la búsqueda, tal cual."""
        resultados = internet.buscar(pregunta, n=3)
        if not resultados:
            return f"No he encontrado nada sobre «{pregunta}»."
        mejor = resultados[0]
        otros = "".join(f"\n  - {r.titulo} ({r.dominio})" for r in resultados[1:])
        return f"Según {mejor.dominio}: {mejor.texto}" + (f"\nMás resultados:{otros}" if otros else "")
