from abc import ABC, abstractmethod


class Skill(ABC):
    """Una habilidad del asistente. Cada integración (apps, Gmail, Spotify...) es una Skill."""

    nombre: str = "skill"
    descripcion: str = ""

    @abstractmethod
    def puede_manejar(self, texto: str) -> bool:
        """Devuelve True si esta habilidad entiende el comando (texto ya en minúsculas)."""

    @abstractmethod
    def ejecutar(self, texto: str, original: str) -> str:
        """Ejecuta el comando y devuelve la respuesta.

        texto: comando normalizado (minúsculas). original: tal como lo escribió el usuario,
        útil cuando hay que conservar mayúsculas (asunto o cuerpo de un correo).
        """

    def confirmar(self, pregunta: str) -> bool:
        """Pide confirmación antes de acciones irreversibles (enviar, borrar...)."""
        return input(f"{pregunta} (s/n) ").strip().lower() in ("s", "si", "sí", "y", "yes")
