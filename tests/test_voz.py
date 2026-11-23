"""Pruebas de la parte de voz que no necesitan micrófono ni altavoces."""
import threading
import unittest
from unittest.mock import MagicMock, patch

from asistente import interfaz
from asistente.__main__ import Voz, recortar_para_voz
from asistente.core import procesar
from asistente.skills.gmail import GmailSkill
from asistente.voz.activacion import buscar_interrupcion, extraer_comando
from asistente.voz.habla import limpiar_para_voz


class TestActivacion(unittest.TestCase):
    def test_con_orden(self):
        self.assertEqual(extraer_comando("Jarvis, pon música de Queen.", "Jarvis"), "pon música de Queen")
        self.assertEqual(extraer_comando("Oye Jarvis ¿qué tengo hoy?", "Jarvis"), "qué tengo hoy")

    def test_transcripciones_aproximadas(self):
        self.assertEqual(extraer_comando("Yarvis abre Spotify", "Jarvis"), "abre Spotify")
        self.assertEqual(extraer_comando("Charvis, pausa", "Jarvis"), "pausa")

    def test_solo_la_palabra(self):
        self.assertEqual(extraer_comando("Jarvis.", "Jarvis"), "")

    def test_no_dirigido_al_asistente(self):
        self.assertIsNone(extraer_comando("mañana voy al jardín", "Jarvis"))
        self.assertIsNone(extraer_comando("le dije a Jarvis que no", "Jarvis"))

    def test_interrupcion_a_mitad_de_frase(self):
        eco = "Spotify, pon Bohemian Rhapsody, pausa. Jarvis, para."
        self.assertEqual(buscar_interrupcion(eco, "Jarvis"), "para")
        self.assertEqual(buscar_interrupcion("revisa mi correo Jarvis", "Jarvis"), "")
        self.assertIsNone(buscar_interrupcion("revisa mi correo, lee el correo dos", "Jarvis"))


class HablanteFalso:
    """Simula que habla durante un rato y se puede cortar con el evento `parar`."""

    def __init__(self):
        self.dicho = []

    def decir(self, texto, parar=None):
        self.dicho.append(texto)
        return bool(parar and parar.wait(timeout=2))


class TestInterrumpir(unittest.TestCase):
    def setUp(self):
        self.oido = MagicMock()
        self.hablante = HablanteFalso()
        self.voz = Voz(self.oido, self.hablante, "Jarvis")
        patch("builtins.print").start()
        self.addCleanup(patch.stopall)

    def test_diciendo_su_nombre_se_calla_y_recoge_la_orden(self):
        self.oido.grabar_frase.return_value = "audio"
        self.oido.transcribir.return_value = "puedo abrir aplicaciones Jarvis pon música"
        self.oido.escuchar.return_value = "de Queen"
        self.assertEqual(self.voz.hablar("Puedo abrir aplicaciones..."), "pon música de Queen")

    def test_solo_su_nombre(self):
        self.oido.grabar_frase.return_value = "audio"
        self.oido.transcribir.return_value = "aplicaciones, Jarvis."
        self.assertEqual(self.voz.hablar("Puedo abrir aplicaciones..."), "")
        self.oido.escuchar.assert_not_called()

    def test_sin_interrupcion(self):
        evento_fin = threading.Event()
        self.oido.grabar_frase.side_effect = lambda **k: k["detener"].wait() and None
        self.hablante.decir = lambda texto, parar=None: evento_fin.set() or False
        self.assertIsNone(self.voz.hablar("Son las 10."))
        self.assertTrue(evento_fin.is_set())

    def test_su_propio_nombre_en_el_texto_no_le_interrumpe(self):
        self.hablante.decir = lambda texto, parar=None: False
        self.assertIsNone(self.voz.hablar("Hola, soy Jarvis"))
        self.oido.grabar_frase.assert_not_called()


class TestConfirmaciones(unittest.TestCase):
    def test_afirmativos(self):
        for r in ("Sí.", "sí, envíalo", "Vale", "claro que sí", "s", "Adelante"):
            self.assertTrue(interfaz.es_afirmativo(r), r)
        for r in ("No.", "no, espera", "", "cancela"):
            self.assertFalse(interfaz.es_afirmativo(r), r)

    def test_confirmar_por_voz(self):
        oido = MagicMock()
        oido.escuchar.return_value = "Sí, envíalo."
        hablante = HablanteFalso()
        interfaz.usar(Voz(oido, hablante, "Jarvis"))
        self.addCleanup(interfaz.usar, interfaz.Teclado())
        with patch("builtins.print"):
            self.assertTrue(GmailSkill().confirmar("¿Envío este correo?"))
        self.assertEqual(hablante.dicho, ["¿Envío este correo?"])


class TestTextoHablado(unittest.TestCase):
    def test_ayuda_resumida(self):
        voz = recortar_para_voz(procesar("ayuda"))
        self.assertTrue(voz.startswith("Puedo abrir aplicaciones"))
        self.assertTrue(voz.endswith("Tienes el resto en pantalla."))
        self.assertLess(len(voz), 400)

    def test_respuesta_corta_entera(self):
        self.assertEqual(recortar_para_voz("Son las 10:30."), "Son las 10:30.")

    def test_agenda(self):
        texto = "Próximos 7 días:\n  - sáb 21/11 todo el día — Cumpleaños\n  - lun 23/11 10:00–11:30 Dentista"
        voz = limpiar_para_voz(texto)
        self.assertIn("sábado 21 de noviembre todo el día , Cumpleaños", voz)
        self.assertIn("lunes 23 de noviembre de 10 a 11:30 Dentista", voz)
        self.assertNotIn("-", voz)


if __name__ == "__main__":
    unittest.main()
