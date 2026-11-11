from datetime import datetime

from .base import Skill


class SistemaSkill(Skill):
    nombre = "sistema"
    descripcion = "Hora y fecha: 'qué hora es', 'qué día es'"

    def puede_manejar(self, texto: str) -> bool:
        return "hora" in texto or "fecha" in texto or "qué día" in texto or "que dia" in texto

    def ejecutar(self, texto: str, original: str) -> str:
        ahora = datetime.now()
        if "hora" in texto:
            return f"Son las {ahora:%H:%M}."
        return f"Hoy es {ahora:%d/%m/%Y}."
