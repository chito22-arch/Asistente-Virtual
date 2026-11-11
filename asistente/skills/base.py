from abc import ABC, abstractmethod


class Skill(ABC):
    """Una habilidad del asistente. Cada integración (apps, Gmail, Spotify...) es una Skill."""

    nombre: str = "skill"
    descripcion: str = ""

    @abstractmethod
    def puede_manejar(self, texto: str) -> bool:
        """Devuelve True si esta habilidad entiende el comando."""

    @abstractmethod
    def ejecutar(self, texto: str) -> str:
        """Ejecuta el comando y devuelve la respuesta para el usuario."""
