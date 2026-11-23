import re
from datetime import date, datetime, time, timedelta

from ..servicios import recordatorios
from ..utils import fechas
from .base import Skill

HORA_POR_DEFECTO = time(9, 0)  # "recuérdame el viernes pagar la luz" sin hora

RE_CREAR = re.compile(
    r"^(?:recu[eé]rdame|av[ií]same|despi[eé]rtame|"
    r"(?:pon(?:me)?|crea(?:me)?|programa(?:me)?|activa)\s+(?:un |una )?(?:recordatorio|temporizador|alarma|aviso)|"
    r"(?:un |una )?(?:recordatorio|temporizador|alarma))\b",
    re.I,
)
RE_LISTAR = re.compile(
    r"\b(?:qu[eé]|cu[aá]les|mis|ver|lista(?:r)?(?: los| mis)?)\b.*\b(?:recordatorios|temporizador(?:es)?|alarmas|avisos)\b"
    r"|\bcu[aá]nto (?:le )?(?:queda|falta)\b")
RE_CANCELAR = re.compile(
    r"^(?:cancela|quita|borra|elimina|anula|para|det[eé]n|apaga)\b.*\b(recordatorios?|temporizador(?:es)?|alarmas?|avisos?)\b")
CONECTORES = re.compile(r"^(?:que|de|para|a|el|la|lo|los|las|me)\s+", re.I)


class RecordatoriosSkill(Skill):
    nombre = "recordatorios"
    descripcion = ("Recordatorios: 'avísame en 20 minutos', 'pon un temporizador de 5 minutos', "
                   "'recuérdame llamar a mamá en una hora', 'recuérdame mañana a las 9 pagar la luz', "
                   "'qué recordatorios tengo', 'cancela el temporizador'")

    def __init__(self) -> None:
        self._gestor = None

    @property
    def gestor(self) -> recordatorios.Gestor:
        return self._gestor or recordatorios.gestor()

    @gestor.setter
    def gestor(self, valor) -> None:
        self._gestor = valor

    def puede_manejar(self, texto: str) -> bool:
        return bool(RE_CREAR.search(texto) or RE_LISTAR.search(texto) or RE_CANCELAR.search(texto))

    def directo(self, texto: str) -> bool:
        # Si entendemos la hora sin ayuda, no hace falta la IA.
        if RE_LISTAR.search(texto) or RE_CANCELAR.search(texto):
            return True
        return bool(RE_CREAR.search(texto)) and interpretar(texto, datetime.now()) is not None

    def ejecutar(self, texto: str, original: str) -> str:
        if RE_CANCELAR.search(texto):
            return self._cancelar(texto)
        if RE_LISTAR.search(texto):
            return self.listar()
        datos = interpretar(original, datetime.now())
        if datos is None:
            return "¿Cuándo te aviso? Por ejemplo: 'avísame en 20 minutos' o 'recuérdame a las 6 sacar la basura'."
        if isinstance(datos, str):
            return datos
        return self.crear(*datos)

    # --- acciones (también las usa la IA) ----------------------------------

    def crear(self, cuando: datetime, mensaje: str, tipo: str, duracion: timedelta | None = None) -> str:
        ahora = datetime.now()
        if cuando <= ahora:
            return f"Las {cuando:%H:%M} ya pasaron. Dime otra hora."
        r = self.gestor.crear(cuando, mensaje, tipo, duracion)
        if tipo == "temporizador" and duracion:
            que = f"Temporizador de {fechas.duracion_legible(duracion)} en marcha"
            return f"{que}: te aviso a las {cuando:%H:%M}" + (f" para «{r.mensaje}»." if r.mensaje else ".")
        cuando_txt = r.describir(ahora).split(" — ", 1)[1]
        return f"Vale, te lo recuerdo {cuando_txt}: {r.mensaje}." if r.mensaje else f"Vale, te aviso {cuando_txt}."

    def listar(self) -> str:
        ahora = datetime.now()
        pendientes = self.gestor.pendientes()
        if not pendientes:
            return "No tienes recordatorios ni temporizadores pendientes."
        return "Pendientes:\n" + "\n".join(f"  {i}. {r.describir(ahora)}" for i, r in enumerate(pendientes, 1))

    def cancelar(self, numero: int | None = None, todos: bool = False, tipo: str | None = None) -> str:
        pendientes = self.gestor.pendientes(tipo)
        cual = {"temporizador": "temporizadores", "recordatorio": "recordatorios"}.get(tipo, "recordatorios ni temporizadores")
        if not pendientes:
            return f"No tienes {cual} pendientes."
        if todos:
            n = self.gestor.cancelar(pendientes)
            return f"Cancelados {n}." if n > 1 else "Cancelado."
        if numero is not None:
            if not 1 <= numero <= len(pendientes):
                return f"No hay ninguno con el número {numero}. Di 'qué recordatorios tengo' para ver la lista."
            elegido = pendientes[numero - 1]
        elif len(pendientes) == 1:
            elegido = pendientes[0]
        else:
            return "Tienes varios. Dime cuál cancelar:\n" + "\n".join(
                f"  {i}. {r.describir(datetime.now())}" for i, r in enumerate(pendientes, 1))
        self.gestor.cancelar([elegido])
        return f"Cancelado: {elegido.mensaje or 'el temporizador'}."

    def _cancelar(self, texto: str) -> str:
        m = RE_CANCELAR.search(texto)
        palabra = m.group(1)
        tipo = "temporizador" if palabra.startswith("temporizador") else None
        numero = re.search(r"\b(\d+)\b", texto)
        todos = bool(re.search(r"\btod[oa]s\b", texto))
        return self.cancelar(int(numero.group(1)) if numero else None, todos, tipo)


def interpretar(texto: str, ahora: datetime) -> tuple | str | None:
    """De "recuérdame llamar a mamá en una hora" saca (cuándo, mensaje, tipo, duración).

    None si no se entiende la hora; un texto si hay un problema que explicar.
    """
    m = RE_CREAR.search(texto)
    if not m:
        return None
    inicio = texto[:m.end()].lower()
    resto = texto[m.end():]
    tipo = "temporizador" if "temporizador" in inicio else "recordatorio"

    duracion, tramo = fechas.buscar_duracion_relativa(resto)
    if duracion:
        cuando, quitar = ahora + duracion, [tramo]
        if not tipo == "temporizador" and not _mensaje(resto, quitar):
            tipo = "temporizador"  # "avísame en 20 minutos" = temporizador
    else:
        dia, m_fecha = fechas.buscar_fecha(resto, ahora.date())
        hora, m_hora = fechas.buscar_hora(resto)
        if dia is None and hora is None:
            return None
        cuando = datetime.combine(dia or ahora.date(), hora or HORA_POR_DEFECTO)
        if dia is None and cuando <= ahora:
            cuando += timedelta(days=1)  # "a las 7" cuando ya pasaron: mañana
        quitar, duracion = [m_fecha, m_hora], None

    mensaje = _mensaje(resto, quitar)
    if not mensaje and inicio.startswith("despi"):
        mensaje = "¡Arriba! Hora de levantarse"
    return cuando, mensaje, tipo, duracion


def _mensaje(resto: str, quitar: list) -> str:
    mensaje = fechas.quitar(resto, *quitar).strip(" ,.;:¡!¿?")
    while (limpio := CONECTORES.sub("", mensaje)) != mensaje:
        mensaje = limpio
    return mensaje[:1].upper() + mensaje[1:] if mensaje else ""
