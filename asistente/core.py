from .skills import SKILLS


def normalizar(texto: str) -> str:
    return texto.lower().strip().rstrip("?.!¡¿").lstrip("¿¡")


def procesar(original: str) -> str:
    """Envía el comando a la primera habilidad que sepa manejarlo."""
    original = original.replace("﻿", "").strip()
    texto = normalizar(original)
    if texto in ("ayuda", "help"):
        return ("Puedo abrir aplicaciones, revisar tu correo y tu calendario, controlar Spotify "
                "y decirte la hora. Ejemplos:\n" + "\n".join(f"  - {s.descripcion}" for s in SKILLS))

    for skill in SKILLS:
        if skill.puede_manejar(texto):
            return skill.ejecutar(texto, original)
    return "No entendí el comando. Escribe 'ayuda' para ver lo que sé hacer."
