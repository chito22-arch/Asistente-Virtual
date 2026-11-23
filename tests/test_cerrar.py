"""Pruebas de cerrar programas, con ventanas simuladas (no se cierra nada de verdad)."""
import unittest
from unittest.mock import MagicMock, patch

from asistente.core import procesar
from asistente.ia import herramientas
from asistente.servicios import ventanas
from asistente.servicios.ventanas import Abierto
from asistente.skills.cerrar import CerrarSkill

ABIERTOS = [
    Abierto({10}, "discord.exe", "Discord", ["#juegos | amigos - Discord"], [101]),
    Abierto({20}, "opera.exe", "Opera GX Internet Browser", ["Discord - Opera", "YouTube"], [201, 202]),
    Abierto({30}, "code.exe", "Visual Studio Code", ["main.py - Proyecto - Visual Studio Code"], [301]),
    Abierto({40}, "whatsapp.root.exe", "WhatsApp.Root", ["WhatsApp"], [401]),
    Abierto({50}, "applicationframehost.exe", "Calculadora", ["Calculadora"], [501], uwp=True),
    Abierto({60}, "soffice.bin", "LibreOffice", ["CV.odt - LibreOffice Writer"], [601]),
]


def buscar(consulta):
    a = ventanas.buscar(consulta, ABIERTOS)
    return a.nombre if a else None


class TestBuscar(unittest.TestCase):
    def test_por_nombre_del_programa(self):
        self.assertEqual(buscar("discord"), "Discord")
        self.assertEqual(buscar("opera"), "Opera GX Internet Browser")
        self.assertEqual(buscar("visual studio code"), "Visual Studio Code")
        self.assertEqual(buscar("libreoffice"), "LibreOffice")

    def test_nombre_bonito(self):
        self.assertEqual(buscar("whatsapp"), "WhatsApp")  # no "WhatsApp.Root"
        self.assertEqual(buscar("calculadora"), "Calculadora")

    def test_el_titulo_de_una_pestana_no_gana_al_programa(self):
        # Opera tiene una pestaña "Discord - Opera", pero Discord es el programa Discord.
        self.assertEqual(ventanas.buscar("discord", ABIERTOS).exe, "discord.exe")

    def test_no_cierra_lo_que_no_esta(self):
        self.assertIsNone(buscar("spotify"))
        self.assertIsNone(buscar("hola"))

    def test_no_fuerza_procesos_de_windows(self):
        with self.assertRaises(PermissionError):
            ventanas.forzar("explorer.exe")


class TestSkill(unittest.TestCase):
    def setUp(self):
        patch.object(ventanas, "abiertos", return_value=ABIERTOS).start()
        self.pedir = patch.object(ventanas, "pedir_cierre").start()
        self.esperar = patch.object(ventanas, "esperar_cierre", return_value="cerrado").start()
        self.forzar = patch.object(ventanas, "forzar", return_value=3).start()
        self.fondo = patch.object(ventanas, "en_segundo_plano", return_value=[]).start()
        self.confirmar = patch.object(CerrarSkill, "confirmar", return_value=True).start()
        self.addCleanup(patch.stopall)

    def test_cerrar(self):
        self.assertEqual(procesar("Cierra Discord"), "He cerrado Discord.")
        self.assertEqual(self.pedir.call_args.args[0].exe, "discord.exe")
        self.forzar.assert_not_called()
        self.confirmar.assert_not_called()  # cerrar normal no pregunta: el programa pedirá guardar si hace falta

    def test_variantes(self):
        procesar("ciérrame el programa de whatsapp")
        self.assertEqual(self.pedir.call_args.args[0].exe, "whatsapp.root.exe")
        procesar("cierra la ventana del visual studio code")
        self.assertEqual(self.pedir.call_args.args[0].exe, "code.exe")

    def test_queda_en_segundo_plano(self):
        self.esperar.return_value = "segundo_plano"
        r = procesar("cierra discord")
        self.assertIn("sigue en segundo plano", r)
        self.assertIn("a la fuerza", r)

    def test_pregunta_si_guardar(self):
        self.esperar.return_value = "abierto"
        self.assertIn("guardar", procesar("cierra libreoffice"))

    def test_forzar_pide_confirmacion(self):
        r = procesar("cierra discord a la fuerza")
        self.confirmar.assert_called_once()
        self.forzar.assert_called_once_with("discord.exe")
        self.assertEqual(r, "Cerrado del todo (3 procesos).")

    def test_forzar_cancelado(self):
        self.confirmar.return_value = False
        self.assertEqual(procesar("mata opera"), "Vale, no lo cierro.")
        self.forzar.assert_not_called()

    def test_app_de_la_tienda_nunca_se_mata(self):
        procesar("cierra calculadora a la fuerza")
        self.forzar.assert_not_called()  # cerraría todas las apps de la Tienda
        self.pedir.assert_called_once()

    def test_solo_en_segundo_plano(self):
        proceso = MagicMock()
        proceso.name.return_value = "Spotify.exe"
        self.fondo.return_value = [proceso]
        r = procesar("cierra spotify")
        self.confirmar.assert_called_once()
        self.forzar.assert_called_once_with("spotify.exe")
        self.assertIn("Cerrado del todo", r)

    def test_no_abierto(self):
        r = procesar("cierra photoshop")
        self.assertTrue(r.startswith("No veo «photoshop» abierto. Tienes abiertos:"))

    def test_no_se_cierra_a_si_mismo(self):
        self.assertIn("apágate", procesar("cierra jarvis"))

    def test_listar(self):
        r = procesar("¿qué programas tengo abiertos?")
        self.assertIn("Discord", r)
        self.assertIn("WhatsApp", r)

    def test_no_choca_con_spotify_ni_recordatorios(self):
        with patch("asistente.skills.spotify.cliente"):
            self.assertIn("leatorio", procesar("quita aleatorio"))
        self.pedir.assert_not_called()

    def test_herramienta_ia(self):
        self.assertEqual(herramientas.ejecutar("cerrar_aplicacion", {"nombre": "Opera"}),
                         "He cerrado Opera GX Internet Browser.")
        self.assertIn("Tienes abiertos", herramientas.ejecutar("programas_abiertos", {}))


if __name__ == "__main__":
    unittest.main()
