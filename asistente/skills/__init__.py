from .base import Skill
from .apps import AppsSkill
from .sistema import SistemaSkill

# Registra aquí cada nueva habilidad (Gmail, Calendario, Spotify...).
SKILLS: list[Skill] = [
    AppsSkill(),
    SistemaSkill(),
]
