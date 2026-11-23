from abc import ABC, abstractmethod

from .. import interfaz


class Skill(ABC):
    """Una habilidad del asistente. Cada integración (apps, Gmail, Spotify...) es una Skill."""

    nombre: str = "skill"
    descripcion: str = ""

    @abstractmethod
    def puede_manejar(self, texto: str) -> bool:
        """Devuelve True si esta habilidad entiende el comando (texto ya en minúsculas)."""

    def directo(self, texto: str) -> bool:
        """True si es un comando simple e inequívoco que no necesita pasar por la IA."""
        return False

    @abstractmethod
    def ejecutar(self, texto: str, original: str) -> str:
        """Ejecuta el comando y devuelve la respuesta.

        texto: comando normalizado (minúsculas). original: tal como lo escribió el usuario,
        útil cuando hay que conservar mayúsculas (asunto o cuerpo de un correo).
        """

    def confirmar(self, pregunta: str) -> bool:
        """Pide confirmación antes de acciones irreversibles (enviar, crear...), por teclado o por voz."""
        return interfaz.es_afirmativo(interfaz.obtener().preguntar(pregunta))
