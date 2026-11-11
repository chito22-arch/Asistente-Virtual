from .base import Skill
from .apps import AppsSkill
from .gmail import GmailSkill
from .sistema import SistemaSkill

# Registra aquí cada nueva habilidad. El orden importa: gana la primera que entienda el comando
# (por eso "abre gmail" lo maneja AppsSkill y "revisa mi correo" GmailSkill).
SKILLS: list[Skill] = [
    AppsSkill(),
    GmailSkill(),
    SistemaSkill(),
]
