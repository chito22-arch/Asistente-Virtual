from .skills import SKILLS


def normalizar(texto: str) -> str:
    return texto.replace("﻿", "").lower().strip().rstrip("?.!¡¿").lstrip("¿¡")


def procesar(texto: str) -> str:
    """Envía el comando a la primera habilidad que sepa manejarlo."""
    texto = normalizar(texto)
    if texto in ("ayuda", "help"):
        return "Puedo hacer esto:\n" + "\n".join(f"  - {s.descripcion}" for s in SKILLS)

    for skill in SKILLS:
        if skill.puede_manejar(texto):
            return skill.ejecutar(texto)
    return "No entendí el comando. Escribe 'ayuda' para ver lo que sé hacer."
