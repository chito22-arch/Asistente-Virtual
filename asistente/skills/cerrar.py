import re

from ..servicios import ventanas
from .base import Skill

RE_CERRAR = re.compile(
    r"^(?:cierra(?:me)?|ci[eé]rrame|cerrar|sal de|salte de|mata|finaliza)\s+"
    r"(?P<forzar>(?:a la fuerza|del todo|forzando|de golpe)\s+)?"
    r"(?:el |la |los |las |mi |)(?:programa |aplicaci[oó]n |app |ventana (?:de |del )?|juego )?(?:de |del )?"
    r"(?P<nombre>.+?)(?P<forzar2>\s+(?:a la fuerza|del todo|forzando|de golpe))?$")
RE_LISTAR = re.compile(r"\bqu[eé] (?:programas|aplicaciones|ventanas|apps) (?:tengo |hay )?abiert[oa]s\b"
                       r"|\b(?:programas|aplicaciones|ventanas) abiert[oa]s\b")
NO_CERRABLES = {"jarvis", "el asistente", "asistente", "todo", "todos", "todas", "windows", "el ordenador",
                "el pc", "la sesion", "la sesión", "sesion", "sesión"}


class CerrarSkill(Skill):
    nombre = "cerrar"
    descripcion = ("Cerrar programas: 'cierra discord', 'cierra el bloc de notas', "
                   "'cierra spotify a la fuerza', 'qué programas tengo abiertos'")

    def puede_manejar(self, texto: str) -> bool:
        return bool(RE_CERRAR.match(texto) or RE_LISTAR.search(texto))

    def directo(self, texto: str) -> bool:
        if RE_LISTAR.search(texto):
            return True
        m = RE_CERRAR.match(texto)
        if not m:
            return False
        nombre = m["nombre"].strip()
        return nombre in NO_CERRABLES or ventanas.buscar(nombre) is not None or bool(ventanas.en_segundo_plano(nombre))

    def ejecutar(self, texto: str, original: str) -> str:
        if RE_LISTAR.search(texto):
            return self.listar()
        m = RE_CERRAR.match(texto)
        return self.cerrar(m["nombre"].strip(), bool(m["forzar"] or m["forzar2"] or texto.startswith("mata")))

    # --- acciones (también las usa la IA) ----------------------------------

    def listar(self) -> str:
        nombres = sorted({a.nombre for a in ventanas.abiertos()}, key=str.lower)
        if not nombres:
            return "No veo ningún programa con ventanas abiertas."
        return "Tienes abiertos: " + ", ".join(nombres) + "."

    def cerrar(self, nombre: str, forzar: bool = False) -> str:
        if nombre.lower() in NO_CERRABLES:
            return "Eso no lo cierro yo. Para apagarme, di 'apágate'."

        abierto = ventanas.buscar(nombre)
        if abierto and not forzar:
            ventanas.pedir_cierre(abierto)
            resultado = ventanas.esperar_cierre(abierto)
            if resultado == "cerrado":
                return f"He cerrado {abierto.nombre}."
            if resultado == "segundo_plano":
                return (f"He cerrado la ventana de {abierto.nombre}, pero sigue en segundo plano. "
                        f"Di 'cierra {nombre} a la fuerza' para cerrarlo del todo.")
            return f"Le he pedido a {abierto.nombre} que se cierre. Puede que te esté preguntando si quieres guardar."

        exe = abierto.exe if abierto else None
        if exe is None:
            procesos = ventanas.en_segundo_plano(nombre)
            if not procesos:
                return f"No veo «{nombre}» abierto. " + self.listar()
            exe = procesos[0].name().lower()
            if not forzar and not self.confirmar(
                    f"{nombre.capitalize()} no tiene ventanas, pero sigue en segundo plano. ¿Lo cierro del todo?"):
                return "Vale, lo dejo como está."
        elif not self.confirmar(f"Voy a cerrar {abierto.nombre} a la fuerza: perderás lo que no hayas guardado. "
                                f"¿Seguro?"):
            return "Vale, no lo cierro."

        if abierto and abierto.uwp:
            ventanas.pedir_cierre(abierto)  # las apps de la Tienda no se pueden "matar" sin afectar a otras
            return f"He cerrado {abierto.nombre}."
        try:
            n = ventanas.forzar(exe)
        except PermissionError as e:
            return str(e)
        return f"Cerrado del todo ({n} proceso{'s' if n != 1 else ''})." if n else "Ya estaba cerrado."
