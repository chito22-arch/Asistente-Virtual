from datetime import datetime

from .base import Skill


class SistemaSkill(Skill):
    nombre = "sistema"
    descripcion = "Hora y fecha: 'qué hora es', 'qué día es'"

    def puede_manejar(self, texto: str) -> bool:
        return "hora" in texto or "fecha" in texto or "qué día" in texto or "que dia" in texto

    def directo(self, texto: str) -> bool:
        return texto in ("qué hora es", "que hora es", "qué día es", "que dia es", "qué día es hoy",
                         "que dia es hoy", "qué fecha es", "que fecha es", "la hora", "hora")

    def ejecutar(self, texto: str, original: str) -> str:
        ahora = datetime.now()
        if "hora" in texto:
            return f"Son las {ahora:%H:%M}."
        return f"Hoy es {ahora:%d/%m/%Y}."
