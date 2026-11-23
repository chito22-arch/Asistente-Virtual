import re

from ..servicios import microfonos
from .base import Skill

RE_LISTAR = re.compile(r"\bqu[eé] micr[oó]fonos\b|\blista (?:de )?(?:los )?micr[oó]fonos\b|\bmicr[oó]fonos disponibles\b")
RE_ACTUAL = re.compile(r"\bqu[eé] micr[oó]fono (?:usas|est[aá]s usando|tienes|es)\b|\bcu[aá]l es (?:el|tu) micr[oó]fono\b"
                       r"|\bpor d[oó]nde me (?:escuchas|oyes)\b")
RE_CAMBIAR = re.compile(
    r"^(?:usa|utiliza|cambia(?: a| al)?|pon|elige|selecciona)\s+(?:el |otro )?micr[oó]fono\s*"
    r"(?:de los |de las |del |de la |de |n[uú]mero )?(?P<cual>.+)$"
    r"|^esc[uú]chame (?:por|con|desde) (?:el |los |las |la |mis )?(?:micr[oó]fono (?:de |del |de los )?)?(?P<cual2>.+)$")
RE_PREDETERMINADO = re.compile(r"predeterminado|por defecto|de windows|normal|el de siempre")

AVISO_BLUETOOTH = (" Ojo: con el micrófono de unos auriculares Bluetooth, mientras te escucho el sonido "
                   "de los auriculares baja de calidad. Es una limitación del Bluetooth.")


class MicrofonoSkill(Skill):
    nombre = "microfono"
    descripcion = ("Micrófono: 'qué micrófonos hay', 'qué micrófono usas', 'usa el micrófono de los auriculares', "
                   "'usa el micrófono 2', 'usa el micrófono predeterminado'")

    def puede_manejar(self, texto: str) -> bool:
        return bool(RE_LISTAR.search(texto) or RE_ACTUAL.search(texto) or RE_CAMBIAR.match(texto))

    def directo(self, texto: str) -> bool:
        return self.puede_manejar(texto)

    def ejecutar(self, texto: str, original: str) -> str:
        if m := RE_CAMBIAR.match(texto):
            return self.cambiar((m["cual"] or m["cual2"]).strip())
        if RE_LISTAR.search(texto):
            return self.listar()
        return f"Te escucho por {microfonos.nombre_en_uso()}."

    def listar(self) -> str:
        lista = microfonos.listar(refrescar=True)
        en_uso = microfonos.actual()
        lineas = [f"  {i}. {m.nombre}{'  (en uso)' if m == en_uso else ''}" for i, m in enumerate(lista, 1)]
        pie = "" if en_uso else f"\nAhora uso el predeterminado de Windows: {microfonos.nombre_predeterminado()}."
        return "Micrófonos:\n" + "\n".join(lineas) + pie + "\nDi 'usa el micrófono 2' para cambiar."

    def cambiar(self, cual: str) -> str:
        if RE_PREDETERMINADO.search(cual):
            microfonos.elegir("")
            return f"Vale, uso el micrófono predeterminado de Windows: {microfonos.nombre_predeterminado()}."
        lista = microfonos.listar(refrescar=True)
        encontrados = microfonos.buscar(cual, lista)
        if not encontrados:
            return f"No encuentro el micrófono «{cual}». " + self.listar()
        if len(encontrados) > 1:
            numeros = [f"{lista.index(m) + 1}. {m.nombre}" for m in encontrados]
            return "Hay varios:\n  " + "\n  ".join(numeros) + "\n¿Cuál? Di 'usa el micrófono' y el número."
        elegido = encontrados[0]
        microfonos.elegir(elegido.nombre)
        return f"Vale, ahora te escucho por {elegido.nombre}." + (AVISO_BLUETOOTH if elegido.es_auricular else "")
