import re
from datetime import date, datetime, time, timedelta

from googleapiclient.errors import HttpError

from ..servicios.google_auth import FaltanCredenciales, servicio
from ..utils import fechas
from .base import Skill

DURACION_POR_DEFECTO = timedelta(hours=1)

RE_CREAR = re.compile(
    r"^(?:crea(?:r|me)?|añade|anade|agenda(?:r|me)?|programa(?:r)?|pon(?:me)?|apunta(?:r|me)?)\s+"
    r"(?:un |una |el |la )?(evento|reuni[oó]n|cita|recordatorio)\b",
    re.I,
)
RE_CONSULTA = re.compile(
    r"\b(agenda|calendario|eventos|reuniones|citas|qu[eé] tengo|tengo algo|estoy libre)\b", re.I
)

RE_CONSULTA_SIMPLE = re.compile(
    r"(?:qu[eé] tengo|mi agenda|agenda|calendario)(?: para| de| del)?"
    r"(?: hoy| mañana| pasado mañana| esta semana| la semana| el (?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))?"
)


class CalendarioSkill(Skill):
    nombre = "calendario"
    descripcion = (
        "Calendario: 'qué tengo hoy', 'agenda de esta semana', 'qué tengo el viernes', "
        "'crea una reunión con Ana mañana a las 10', 'crea un evento Dentista el 3/12 a las 17:30 durante 30 minutos'"
    )

    def puede_manejar(self, texto: str) -> bool:
        if RE_CREAR.search(texto):
            return True
        return bool(RE_CONSULTA.search(texto)) and not re.search(r"\b(correos?|emails?)\b", texto)

    def directo(self, texto: str) -> bool:
        return bool(RE_CONSULTA_SIMPLE.fullmatch(texto))

    def ejecutar(self, texto: str, original: str) -> str:
        try:
            if m := RE_CREAR.search(original):
                return self._crear(original, m)
            return self._consultar(texto)
        except FaltanCredenciales as e:
            return str(e)
        except HttpError as e:
            return f"Error de Google Calendar: {e.reason}"

    # --- consultar --------------------------------------------------------

    def _consultar(self, texto: str) -> str:
        hoy = date.today()
        if "semana" in texto:
            desde, dias, titulo = hoy, 7, "Próximos 7 días"
        else:
            dia, _ = fechas.buscar_fecha(texto, hoy)
            if dia is None and re.search(r"\b(agenda|calendario|eventos|reuniones|citas)\b", texto) \
                    and not re.search(r"\bqu[eé] tengo\b", texto):
                desde, dias, titulo = hoy, 7, "Próximos 7 días"
            else:
                desde, dias, titulo = dia or hoy, 1, None
        return self.consultar(desde, dias, titulo)

    def consultar(self, desde: date, dias: int = 1, titulo: str | None = None) -> str:
        """Lista los eventos de `dias` días a partir de `desde`."""
        hoy = date.today()
        if titulo is None:
            if dias == 1:
                titulo = "Hoy" if desde == hoy else ("Mañana" if desde == hoy + timedelta(days=1)
                                                     else fechas.formatear_dia(desde))
            else:
                titulo = f"Del {fechas.formatear_dia(desde)} al {fechas.formatear_dia(desde + timedelta(days=dias - 1))}"

        inicio = datetime.combine(desde, datetime.min.time()).astimezone()
        fin = inicio + timedelta(days=dias)
        eventos = servicio("calendar", "v3").events().list(
            calendarId="primary", timeMin=inicio.isoformat(), timeMax=fin.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=25,
        ).execute().get("items", [])

        if not eventos:
            return f"{titulo}: no tienes nada en el calendario."
        lineas = [f"{titulo}:"]
        for ev in eventos:
            lineas.append("  - " + _describir(ev, mostrar_dia=dias > 1))
        return "\n".join(lineas)

    # --- crear ------------------------------------------------------------

    def _crear(self, original: str, m_crear: re.Match) -> str:
        tipo = m_crear.group(1).lower()
        resto = original[m_crear.end():]

        dia, m_fecha = fechas.buscar_fecha(resto, date.today())
        hora, m_hora = fechas.buscar_hora(resto)
        duracion, m_dur = fechas.buscar_duracion(resto)
        if dia is None and hora is None:
            return "¿Para cuándo? Ejemplo: 'crea una reunión con Ana mañana a las 10'."
        dia = dia or date.today()

        titulo = fechas.quitar(resto, m_fecha, m_hora, m_dur).strip(" :,.-")
        titulo = re.sub(r"^(?:llamad[oa]|titulad[oa]|de|para|sobre)\s+", "", titulo, flags=re.I)
        nombre_tipo = {"reunion": "Reunión", "reunión": "Reunión"}.get(tipo, tipo.capitalize())
        if not titulo:
            titulo = nombre_tipo
        elif titulo.lower().startswith("con ") or tipo in ("reunión", "reunion", "cita"):
            titulo = f"{nombre_tipo} {titulo}"
        return self.crear_evento(titulo, dia, hora, duracion)

    def crear_evento(self, titulo: str, dia: date, hora: time | None = None,
                     duracion: timedelta | None = None) -> str:
        """Crea el evento tras pedir confirmación. Sin hora = evento de día completo."""
        if hora is None:  # evento de día completo
            cuerpo = {"summary": titulo, "start": {"date": dia.isoformat()},
                      "end": {"date": (dia + timedelta(days=1)).isoformat()}}
            cuando = f"{fechas.formatear_dia(dia)} (todo el día)"
        else:
            inicio = datetime.combine(dia, hora).astimezone()
            fin = inicio + (duracion or DURACION_POR_DEFECTO)
            if inicio < datetime.now().astimezone():
                return f"Las {hora:%H:%M} de {fechas.formatear_dia(dia)} ya pasaron. Indica otra fecha u hora."
            cuerpo = {"summary": titulo, "start": {"dateTime": inicio.isoformat()},
                      "end": {"dateTime": fin.isoformat()}}
            cuando = f"{fechas.formatear_dia(dia)} de {inicio:%H:%M} a {fin:%H:%M}"

        if not self.confirmar(f"Evento: {titulo}\nCuándo: {cuando}\n¿Lo añado al calendario?"):
            return "Evento cancelado."
        servicio("calendar", "v3").events().insert(calendarId="primary", body=cuerpo).execute()
        return f"Añadido: {titulo}, {cuando}."


def _describir(ev: dict, mostrar_dia: bool) -> str:
    titulo = ev.get("summary", "(sin título)")
    ini, fin = ev["start"], ev["end"]
    if "date" in ini:  # día completo
        dia = date.fromisoformat(ini["date"])
        return f"{fechas.formatear_dia(dia) + ' ' if mostrar_dia else ''}todo el día — {titulo}"
    a = datetime.fromisoformat(ini["dateTime"]).astimezone()
    b = datetime.fromisoformat(fin["dateTime"]).astimezone()
    prefijo = fechas.formatear_dia(a.date()) + " " if mostrar_dia else ""
    return f"{prefijo}{a:%H:%M}–{b:%H:%M} {titulo}"
