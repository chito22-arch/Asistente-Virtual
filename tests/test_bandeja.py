"""Pruebas del bucle de voz controlable, del icono y de las confirmaciones por hilo."""
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from asistente import interfaz
from asistente.bandeja import COLORES, dibujar_icono
from asistente.voz.bucle import BucleVoz


class OidoFalso:
    """Devuelve las frases preparadas; luego se queda "escuchando" hasta que lo despierten."""

    def __init__(self, *frases):
        self.frases = list(frases)

    def escuchar(self, espera_max=None, detener=None):
        if self.frases:
            return self.frases.pop(0)
        if detener:
            detener.wait(timeout=2)
        return ""


class HablanteFalso:
    def __init__(self):
        self.dicho = []

    def decir(self, texto, parar=None):
        self.dicho.append(texto)
        return False

    def callar(self):
        pass


def bucle_con(*frases):
    bucle = BucleVoz("Jarvis")
    voz = MagicMock()
    voz.oido = OidoFalso(*frases)
    voz.hablante = HablanteFalso()
    voz.hablar.return_value = None
    voz.mostrar.return_value = None
    bucle.voz = voz
    return bucle


class TestBucleVoz(unittest.TestCase):
    def setUp(self):
        patch("builtins.print").start()
        self.addCleanup(patch.stopall)

    def test_orden_y_despedida(self):
        bucle = bucle_con("Jarvis, qué hora es", "Jarvis, apágate")
        estados = []
        bucle._notificar = estados.append
        bucle.ejecutar()
        texto_mostrado = bucle.voz.mostrar.call_args.args[0]
        self.assertTrue(texto_mostrado.startswith("Son las"))
        self.assertIn("pensando", estados)
        self.assertEqual(bucle.voz.hablante.dicho[-1], "Hasta luego.")

    def test_ignora_frases_sin_su_nombre(self):
        bucle = bucle_con("qué hora es", "Jarvis, adiós")
        bucle.ejecutar()
        bucle.voz.mostrar.assert_not_called()

    def test_silenciar_y_parar_desde_otro_hilo(self):
        bucle = bucle_con()
        hilo = threading.Thread(target=bucle.ejecutar)
        hilo.start()
        time.sleep(0.1)
        self.assertEqual(bucle.estado, "escuchando")
        bucle.silenciar(True)
        time.sleep(0.1)
        self.assertEqual(bucle.estado, "silenciado")
        bucle.silenciar(False)
        time.sleep(0.1)
        self.assertEqual(bucle.estado, "escuchando")
        bucle.parar()
        hilo.join(timeout=3)
        self.assertFalse(hilo.is_alive())
        self.assertNotIn("Hasta luego.", bucle.voz.hablante.dicho)  # al salir desde el menú no habla


class TestIcono(unittest.TestCase):
    def test_un_color_por_estado(self):
        for estado, color in COLORES.items():
            img = dibujar_icono(estado)
            self.assertEqual(img.size, (64, 64))
            self.assertEqual(img.getpixel((32, 6))[:3], color, estado)


class TestInterfazPorHilo(unittest.TestCase):
    def test_cada_hilo_su_interfaz(self):
        global_, local = MagicMock(), MagicMock()
        interfaz.usar(global_)
        self.addCleanup(interfaz.usar, interfaz.Teclado())
        vista = {}

        def en_otro_hilo():
            interfaz.usar_en_este_hilo(local)
            vista["otro"] = interfaz.obtener()

        h = threading.Thread(target=en_otro_hilo)
        h.start()
        h.join()
        self.assertIs(vista["otro"], local)
        self.assertIs(interfaz.obtener(), global_)


if __name__ == "__main__":
    unittest.main()
