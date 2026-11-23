from .skills import SKILLS

# Agente de IA para frases libres. None = desactivado (solo comandos fijos). Lo activa __main__.
_agente = None


def activar_ia(agente) -> None:
    global _agente
    _agente = agente


def normalizar(texto: str) -> str:
    return texto.lower().strip().rstrip("?.!¡¿").lstrip("¿¡")


def procesar(original: str) -> str:
    """Decide quién responde.

    Con IA: los comandos simples e inequívocos van directos a su skill (instantáneo);
    todo lo demás lo interpreta la IA, que usa las skills como herramientas.
    Sin IA (o si falla): la primera skill que entienda el comando.
    """
    original = original.replace("﻿", "").strip()
    texto = normalizar(original)
    if texto in ("ayuda", "help"):
        return ("Puedo abrir aplicaciones, revisar tu correo y tu calendario, controlar Spotify "
                "y decirte la hora. Ejemplos:\n" + "\n".join(f"  - {s.descripcion}" for s in SKILLS)
                + ("\n  - Y con IA, frases libres: 'ponme algo tranquilo para trabajar', "
                   "'apúntame el dentista el jueves por la tarde'" if _agente else ""))

    if _agente is not None:
        for skill in SKILLS:
            if skill.directo(texto):
                return skill.ejecutar(texto, original)
        try:
            return _agente.responder(original)
        except Exception as e:  # IA caída: seguimos con los comandos fijos
            print(f"  (IA no disponible: {e}. Uso los comandos fijos.)")

    for skill in SKILLS:
        if skill.puede_manejar(texto):
            return skill.ejecutar(texto, original)
    return _buscar_en_internet(original)


def _buscar_en_internet(pregunta: str) -> str:
    """Último recurso: si nadie lo entiende, se busca en internet."""
    from .servicios.internet import SinConexion
    from .skills.internet import InternetSkill

    if len(pregunta.split()) < 2:  # una palabra suelta no es una pregunta
        return "No entendí el comando. Di 'ayuda' para ver lo que sé hacer."
    try:
        return next(s for s in SKILLS if isinstance(s, InternetSkill)).responder(pregunta)
    except SinConexion:
        return "No entendí el comando y no puedo buscarlo en internet ahora. Di 'ayuda' para ver lo que sé hacer."
