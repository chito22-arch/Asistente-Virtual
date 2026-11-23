from .base import Skill
from .apps import AppsSkill
from .calendario import CalendarioSkill
from .cerrar import CerrarSkill
from .gmail import GmailSkill
from .recordatorios import RecordatoriosSkill
from .sistema import SistemaSkill
from .spotify import SpotifySkill

# Registra aquí cada nueva habilidad. El orden importa: gana la primera que entienda el comando
# (por eso "abre gmail" lo maneja AppsSkill, "cierra spotify" CerrarSkill, "pon un temporizador"
# RecordatoriosSkill, "ponme una cita" CalendarioSkill y "pon Queen" SpotifySkill).
SKILLS: list[Skill] = [
    AppsSkill(),
    CerrarSkill(),
    RecordatoriosSkill(),
    CalendarioSkill(),
    SpotifySkill(),
    GmailSkill(),
    SistemaSkill(),
]
