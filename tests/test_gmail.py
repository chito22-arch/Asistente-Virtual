"""Pruebas de la skill de Gmail con una API falsa (no necesita credenciales).

Ejecutar: python -m unittest discover tests
"""
import base64
import unittest
from unittest.mock import MagicMock, patch

from asistente.core import procesar
from asistente.skills import SKILLS
from asistente.skills.gmail import GmailSkill


def api_falsa():
    gmail = MagicMock()
    mensajes = gmail.users.return_value.messages.return_value
    mensajes.list.return_value.execute.return_value = {"messages": [{"id": "a1"}, {"id": "b2"}]}
    cuerpo = base64.urlsafe_b64encode("Hola Luis, nos vemos mañana.".encode()).decode()
    mensajes.get.return_value.execute.return_value = {
        "snippet": "Hola Luis",
        "payload": {
            "headers": [{"name": "From", "value": "Ana <ana@mail.com>"}, {"name": "Subject", "value": "Reunión"}],
            "mimeType": "multipart/alternative",
            "parts": [{"mimeType": "text/plain", "body": {"data": cuerpo}}],
        },
    }
    return gmail, mensajes


class TestGmail(unittest.TestCase):
    def setUp(self):
        self.gmail, self.mensajes = api_falsa()
        parche = patch("asistente.skills.gmail.servicio", return_value=self.gmail)
        parche.start()
        self.addCleanup(parche.stop)
        self.skill = next(s for s in SKILLS if isinstance(s, GmailSkill))
        self.skill.ultimos = []

    def test_no_leidos(self):
        r = procesar("Revisa mi correo")
        self.assertIn("1. Ana — Reunión", r)
        q = self.mensajes.list.call_args.kwargs["q"]
        self.assertEqual(q, "is:unread in:inbox")

    def test_buscar_de(self):
        procesar("busca correos de juan")
        self.assertEqual(self.mensajes.list.call_args.kwargs["q"], "from:juan")

    def test_leer_sin_lista(self):
        self.assertIn("Primero pide la lista", procesar("lee el correo 1"))

    def test_leer(self):
        procesar("revisa mi correo")
        r = procesar("lee el correo 2")
        self.assertIn("nos vemos mañana", r)
        self.mensajes.modify.assert_called_once()

    def test_enviar_conserva_mayusculas(self):
        with patch.object(GmailSkill, "confirmar", return_value=True):
            r = procesar("Envía un correo a ana@mail.com asunto: Hola Ana mensaje: Te llamo a las 5.")
        self.assertEqual(r, "Correo enviado a ana@mail.com.")
        raw = self.mensajes.send.call_args.kwargs["body"]["raw"]
        texto = base64.urlsafe_b64decode(raw).decode()
        self.assertIn("Subject: Hola Ana", texto)
        self.assertIn("Te llamo a las 5.", texto)

    def test_enviar_cancelado(self):
        with patch.object(GmailSkill, "confirmar", return_value=False):
            r = procesar("envía un correo a ana@mail.com asunto: x mensaje: y")
        self.assertEqual(r, "Envío cancelado.")
        self.mensajes.send.assert_not_called()

    def test_abre_gmail_sigue_siendo_app(self):
        with patch("asistente.skills.apps.webbrowser.open") as abrir:
            procesar("abre gmail")
        abrir.assert_called_once()


if __name__ == "__main__":
    unittest.main()
