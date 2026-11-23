"""Agente: entiende frases libres y decide qué herramienta usar.

La IA solo elige la herramienta y sus datos; el resultado de la herramienta es la respuesta.
Así un modelo local pequeño no puede inventarse correos ni eventos al "resumir".
Si no hace falta ninguna herramienta (charla, una cuenta...), responde la IA directamente.
"""
import json
import os

from . import herramientas

MAX_HISTORIAL = 12  # mensajes recordados (para "¿y el viernes?")
MAX_RESULTADO_HISTORIAL = 400  # caracteres de cada resultado que se recuerdan

SISTEMA = """Eres {nombre}, el asistente personal por voz de un PC con Windows. Hablas con tu usuario en España.
Reglas:
- Para correos, calendario, música o abrir programas llama SIEMPRE a la herramienta adecuada, también en preguntas de seguimiento como "¿y de Ryanair?" o "¿y el viernes?". Nunca respondas sobre eso de memoria.
- Si falta un dato imprescindible (por ejemplo una dirección de correo), pregúntalo; no lo inventes.
- Para fechas usa la tabla de abajo; "por la tarde" sin hora concreta = 17:00, "por la mañana" = 10:00, "a mediodía" = 13:00.
- No inventes duraciones: si el usuario no la dice, omite duracion_minutos.
- Si la petición no necesita herramientas (una pregunta general, una cuenta, charla), responde en español, en una o dos frases cortas, sin markdown ni emojis: tu respuesta se lee en voz alta.
- No ofrezcas cosas que no puedes hacer con tus herramientas.
{fechas}"""


class Agente:
    def __init__(self, proveedor, nombre: str = "Jarvis", mostrar=print) -> None:
        self.proveedor = proveedor
        self.nombre = nombre
        self.mostrar = mostrar
        self.historial: list[dict] = []

    def responder(self, peticion: str) -> str:
        sistema = SISTEMA.format(nombre=self.nombre, fechas=herramientas.contexto_fechas())
        usuario = {"role": "user", "content": peticion}
        r = self.proveedor.chat([{"role": "system", "content": sistema}, *self.historial, usuario],
                                herramientas.DEFINICIONES)

        if not r.llamadas:
            respuesta = r.texto or "No he sabido qué hacer con eso."
            self._recordar(usuario, {"role": "assistant", "content": respuesta})
            return respuesta

        resultados, mensajes_tool = [], []
        for nombre, args in r.llamadas:
            if os.getenv("IA_DEPURAR"):
                self.mostrar(f"  [IA] {nombre} {json.dumps(args, ensure_ascii=False)}")
            resultado = herramientas.ejecutar(nombre, args, peticion)
            resultados.append(resultado)
            mensajes_tool.append({"role": "tool", "tool_name": nombre,
                                  "content": resultado[:MAX_RESULTADO_HISTORIAL]})
        # Se recuerda la llamada y su resultado: así el modelo "ve" que hay que usar herramientas.
        self._recordar(usuario, r.mensaje, *mensajes_tool)
        return "\n".join(resultados)

    def _recordar(self, *mensajes: dict) -> None:
        historial = [*self.historial, *mensajes][-MAX_HISTORIAL:]
        while historial and historial[0]["role"] != "user":  # no empezar a mitad de un turno
            historial.pop(0)
        self.historial = historial
