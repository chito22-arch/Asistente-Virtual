"""Pruebas de la elección de micrófono con dispositivos de audio simulados."""
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from asistente.core import procesar
from asistente.servicios import microfonos
from asistente.servicios.microfonos import Microfono

APIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WDM-KS"}]
DISPOSITIVOS = [
    {"name": "Asignador de sonido Microsoft - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": "Micrófono (Realtek(R) Audio)", "hostapi": 0, "max_input_channels": 2},
    {"name": "Microphone (Camo)", "hostapi": 0, "max_input_channels": 1},
    {"name": "Auriculares con micrófono (OPPO", "hostapi": 0, "max_input_channels": 1},
    {"name": "Altavoces (Realtek(R) Audio)", "hostapi": 0, "max_input_channels": 0},
    {"name": "Auriculares con micrófono (OPPO Enco Air4)", "hostapi": 1, "max_input_channels": 1},
    {"name": "Auriculares con micrófono (@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0\r\n;(JVC HA-A9T))",
     "hostapi": 2, "max_input_channels": 1},
]
LISTA = [Microfono(1, "Micrófono (Realtek(R) Audio)"), Microfono(2, "Microphone (Camo)"),
         Microfono(3, "Auriculares con micrófono (OPPO Enco Air4)"),
         Microfono(9, "Auriculares con micrófono (JVC HA-A9T)")]


class TestDispositivos(unittest.TestCase):
    def test_nombres_completos_y_sin_ruido(self):
        with patch("asistente.servicios.microfonos.sd.query_hostapis", return_value=APIS), \
                patch("asistente.servicios.microfonos.sd.query_devices", return_value=DISPOSITIVOS):
            lista = microfonos._leer_dispositivos()
        self.assertEqual([m.nombre for m in lista], [
            "Micrófono (Realtek(R) Audio)", "Microphone (Camo)", "Auriculares con micrófono (OPPO Enco Air4)"])
        self.assertEqual(lista[2].indice, 3)  # se graba por MME
        self.assertTrue(lista[2].es_auricular)

    def test_buscar(self):
        nombres = lambda q: [m.nombre for m in microfonos.buscar(q, LISTA)]
        self.assertEqual(nombres("2"), ["Microphone (Camo)"])
        self.assertEqual(nombres("oppo"), ["Auriculares con micrófono (OPPO Enco Air4)"])
        self.assertEqual(len(nombres("los auriculares")), 2)  # hay dos: hay que preguntar
        self.assertEqual(nombres("del ordenador"), ["Micrófono (Realtek(R) Audio)"])
        self.assertEqual(nombres("camo"), ["Microphone (Camo)"])
        self.assertEqual(nombres("7"), [])


class ConMicrofonosFalsos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        env = Path(self.dir.name) / ".env"
        env.write_text("NOMBRE_ASISTENTE=Jarvis\n", encoding="utf-8")
        self.env = env
        patch.object(microfonos, "ENV", env).start()
        patch.object(microfonos, "_cache", list(LISTA)).start()
        patch.object(microfonos, "listar", side_effect=lambda refrescar=False: list(LISTA)).start()
        patch.object(microfonos, "_suscriptores", []).start()
        patch("asistente.servicios.microfonos.sd.query_devices",
              return_value={"name": "Micrófono (Realtek(R) Audio)"}).start()
        patch.dict(os.environ, {"MICROFONO": ""}).start()
        self.addCleanup(patch.stopall)


class TestSkill(ConMicrofonosFalsos):
    def test_listar(self):
        r = procesar("¿qué micrófonos hay?")
        self.assertIn("3. Auriculares con micrófono (OPPO Enco Air4)", r)
        self.assertIn("predeterminado de Windows", r)

    def test_cambiar_y_guardar(self):
        avisados = []
        microfonos.suscribir(avisados.append)
        r = procesar("usa el micrófono de los OPPO")
        self.assertTrue(r.startswith("Vale, ahora te escucho por Auriculares con micrófono (OPPO Enco Air4)."))
        self.assertIn("Bluetooth", r)  # aviso de calidad de sonido
        self.assertIn("MICROFONO=Auriculares con micrófono (OPPO Enco Air4)", self.env.read_text(encoding="utf-8"))
        self.assertEqual(avisados, ["Auriculares con micrófono (OPPO Enco Air4)"])
        self.assertEqual(procesar("qué micrófono usas"), "Te escucho por Auriculares con micrófono (OPPO Enco Air4).")
        self.assertIn("(en uso)", procesar("lista de micrófonos"))

    def test_varios_pregunta_cual(self):
        r = procesar("escúchame por los auriculares")
        self.assertTrue(r.startswith("Hay varios"))
        self.assertIn("3. Auriculares con micrófono (OPPO", r)
        self.assertIn("4. Auriculares con micrófono (JVC", r)
        self.assertEqual(microfonos.configurado(), "")  # no cambió nada

    def test_por_numero_y_volver_al_predeterminado(self):
        procesar("usa el micrófono 2")
        self.assertEqual(microfonos.configurado(), "Microphone (Camo)")
        self.assertNotIn("Bluetooth", procesar("usa el micrófono 1"))
        r = procesar("usa el micrófono predeterminado")
        self.assertEqual(microfonos.configurado(), "")
        self.assertIn("predeterminado de Windows", r)

    def test_no_existe(self):
        self.assertTrue(procesar("usa el micrófono del móvil de mi primo").startswith("No encuentro el micrófono"))

    def test_desconectado_usa_el_de_windows(self):
        os.environ["MICROFONO"] = "Auriculares Sony"
        self.assertIsNone(microfonos.actual())
        self.assertIsNone(microfonos.indice())


class TestBucle(ConMicrofonosFalsos):
    def bucle(self, escuchar):
        from asistente.voz.bucle import BucleVoz

        bucle = BucleVoz("Jarvis")
        voz = MagicMock()
        voz.hablar.return_value = None
        voz.oido.escuchar.side_effect = escuchar
        bucle.voz = voz
        microfonos.suscribir(bucle._micro_cambiado)
        patch("builtins.print").start()
        return bucle

    def arrancar(self, bucle) -> threading.Thread:
        hilo = threading.Thread(target=bucle.ejecutar, daemon=True)
        hilo.start()
        self.addCleanup(hilo.join, 3)
        self.addCleanup(bucle.parar)  # se para aunque el test falle
        return hilo

    def test_recalibra_al_cambiar(self):
        def escuchar(espera_max=None, detener=None):
            detener.wait(timeout=2)
            return ""

        bucle = self.bucle(escuchar)
        self.arrancar(bucle)
        time.sleep(0.1)
        bucle.voz.oido.calibrar.assert_not_called()
        microfonos.elegir("Microphone (Camo)")
        time.sleep(0.2)
        bucle.voz.oido.calibrar.assert_called()

    def test_avisa_si_no_llega_sonido(self):
        def escuchar(espera_max=None, detener=None):
            detener.wait(timeout=2)
            return ""

        bucle = self.bucle(escuchar)
        bucle.voz.oido.sin_senal = True  # p. ej. Camo sin el móvil conectado
        bucle.voz.oido.umbral = 0.006
        self.arrancar(bucle)
        time.sleep(0.1)
        microfonos.elegir("Microphone (Camo)")
        time.sleep(0.3)
        dichos = [c.args[0] for c in bucle.voz.hablar.call_args_list]
        self.assertTrue(any("No me llega ningún sonido" in d for d in dichos), dichos)

    def test_si_falla_vuelve_al_de_windows(self):
        os.environ["MICROFONO"] = "Auriculares con micrófono (OPPO Enco Air4)"
        llamadas = []

        def escuchar(espera_max=None, detener=None):
            llamadas.append(microfonos.configurado())
            if len(llamadas) == 1:
                raise OSError("Device unavailable")
            detener.wait(timeout=2)
            return ""

        bucle = self.bucle(escuchar)
        hilo = self.arrancar(bucle)
        time.sleep(0.3)
        bucle.parar()
        hilo.join(timeout=3)
        self.assertEqual(microfonos.configurado(), "")
        dichos = [c.args[0] for c in bucle.voz.hablar.call_args_list]
        self.assertTrue(any("Vuelvo al de Windows" in d for d in dichos), dichos)


if __name__ == "__main__":
    unittest.main()
