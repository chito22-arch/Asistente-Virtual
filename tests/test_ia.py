"""Pruebas del agente de IA con un modelo falso (no necesita Ollama)."""
import unittest
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from asistente import core
from asistente.ia import herramientas
from asistente.ia.agente import Agente
from asistente.ia.proveedores import Respuesta
from asistente.skills.calendario import CalendarioSkill
from asistente.skills.spotify import SpotifySkill


class ModeloFalso:
    """Devuelve respuestas preparadas en orden y guarda lo que recibe."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.recibido = []

    def chat(self, mensajes, herramientas_):
        self.recibido.append(list(mensajes))
        return self.respuestas.pop(0)


def llamada(nombre, **args):
    return Respuesta("", [(nombre, args)], {"role": "assistant", "content": ""})


def texto(t):
    return Respuesta(t, [], {"role": "assistant", "content": t})


class TestAgente(unittest.TestCase):
    def test_el_resultado_de_la_herramienta_es_la_respuesta(self):
        modelo = ModeloFalso(llamada("gmail_buscar", consulta="is:important newer_than:1d"))
        with patch.object(herramientas, "ejecutar", return_value="Correos: ninguno.") as ej:
            r = Agente(modelo).responder("¿tengo algún correo importante de hoy?")
        self.assertEqual(r, "Correos: ninguno.")
        ej.assert_called_once_with("gmail_buscar", {"consulta": "is:important newer_than:1d"},
                                   "¿tengo algún correo importante de hoy?")
        self.assertEqual(len(modelo.recibido), 1)  # una sola llamada al modelo

    def test_el_historial_incluye_las_herramientas(self):
        modelo = ModeloFalso(llamada("gmail_buscar", consulta="from:amazon"), texto("x"))
        agente = Agente(modelo)
        with patch.object(herramientas, "ejecutar", return_value="Correos: 1. Amazon"):
            agente.responder("¿me ha escrito amazon?")
        agente.responder("¿y ryanair?")
        roles = [m["role"] for m in modelo.recibido[1][1:]]
        self.assertEqual(roles, ["user", "assistant", "tool", "user"])

    def test_recuerda_la_conversacion(self):
        modelo = ModeloFalso(texto("Hola."), texto("Te llamas Luis."))
        agente = Agente(modelo)
        agente.responder("Me llamo Luis")
        agente.responder("¿Cómo me llamo?")
        contenidos = [m["content"] for m in modelo.recibido[1]]
        self.assertIn("Me llamo Luis", contenidos)

    def test_sistema_incluye_fechas(self):
        modelo = ModeloFalso(texto("ok"))
        Agente(modelo).responder("hola")
        self.assertIn(date.today().isoformat(), modelo.recibido[0][0]["content"])


class TestHerramientas(unittest.TestCase):
    def setUp(self):
        self.cal = next(s for s in herramientas.SKILLS if isinstance(s, CalendarioSkill))

    def test_la_fecha_del_usuario_manda(self):
        hoy = date.today()
        jueves = hoy + timedelta(days=(3 - hoy.weekday()) % 7 or 7)
        with patch.object(self.cal, "crear_evento", return_value="ok") as crear:
            herramientas.ejecutar("calendario_crear",
                                  {"titulo": "Dentista", "fecha": "1999-01-01", "hora": "tarde", "duracion_minutos": 30},
                                  "apúntame el dentista el jueves por la tarde")
        crear.assert_called_once_with("Dentista", jueves, time(17), None)

    def test_hora_explicita_del_usuario(self):
        with patch.object(self.cal, "crear_evento", return_value="ok") as crear:
            herramientas.ejecutar("calendario_crear", {"titulo": "Cena", "fecha": "2030-05-05", "hora": "20:00"},
                                  "cena con Ana el 5/5/2030 a las 9 de la noche durante 2 horas")
        crear.assert_called_once_with("Cena", date(2030, 5, 5), time(21), timedelta(hours=2))

    def test_spotify_usa_el_interprete_de_texto(self):
        spotify = next(s for s in herramientas.SKILLS if isinstance(s, SpotifySkill))
        with patch.object(spotify, "ejecutar", return_value="ok") as ej:
            herramientas.ejecutar("spotify_reproducir", {"tipo": "playlist", "consulta": "lofi para trabajar"})
        ej.assert_called_once_with("pon la playlist lofi para trabajar", "pon la playlist lofi para trabajar")

    def test_enviar_sin_direccion(self):
        r = herramientas.ejecutar("gmail_enviar", {"para": "Ana", "asunto": "x", "mensaje": "y"})
        self.assertIn("No tengo la dirección", r)

    def test_error_se_devuelve_como_texto(self):
        r = herramientas.ejecutar("gmail_leer", {"numero": "no-es-un-numero"})
        self.assertTrue(r.startswith("Error al ejecutar gmail_leer"))


class TestEnrutado(unittest.TestCase):
    def setUp(self):
        self.agente = MagicMock()
        self.agente.responder.return_value = "respuesta IA"
        core.activar_ia(self.agente)
        self.addCleanup(core.activar_ia, None)

    def test_comandos_simples_no_pasan_por_la_ia(self):
        with patch("asistente.skills.spotify.cliente"):
            core.procesar("pausa")
        core.procesar("¿qué hora es?")
        self.agente.responder.assert_not_called()

    def test_frases_libres_van_a_la_ia(self):
        for frase in ("ponme algo tranquilo para trabajar", "apúntame el dentista el jueves",
                      "¿tengo algún correo importante?"):
            self.assertEqual(core.procesar(frase), "respuesta IA")

    def test_si_la_ia_falla_usa_los_comandos_fijos(self):
        self.agente.responder.side_effect = ConnectionError("Ollama caído")
        with patch("builtins.print"), patch.object(CalendarioSkill, "_crear", return_value="fijo"):
            self.assertEqual(core.procesar("crea un evento Dentista mañana a las 10"), "fijo")


if __name__ == "__main__":
    unittest.main()
