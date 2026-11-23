"""Pruebas de recordatorios y temporizadores (sin esperar de verdad: se simula la hora)."""
import tempfile
import threading
import time as reloj
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from asistente.core import procesar
from asistente.ia import herramientas
from asistente.servicios.recordatorios import Gestor
from asistente.skills import SKILLS
from asistente.skills.recordatorios import RecordatoriosSkill, interpretar
from asistente.utils import fechas

AHORA = datetime(2026, 11, 23, 17, 0)  # lunes


class TestDuraciones(unittest.TestCase):
    def dur(self, texto):
        return fechas.buscar_duracion_relativa(texto)[0]

    def test_formas(self):
        self.assertEqual(self.dur("en 20 minutos"), timedelta(minutes=20))
        self.assertEqual(self.dur("dentro de una hora y media"), timedelta(minutes=90))
        self.assertEqual(self.dur("de media hora"), timedelta(minutes=30))
        self.assertEqual(self.dur("en 1 hora y 20 minutos"), timedelta(minutes=80))
        self.assertEqual(self.dur("en cinco minutos"), timedelta(minutes=5))
        self.assertEqual(self.dur("en 2 horas y media"), timedelta(minutes=150))
        self.assertEqual(self.dur("de 90 segundos"), timedelta(seconds=90))
        self.assertEqual(self.dur("en un cuarto de hora"), timedelta(minutes=15))

    def test_no_confunde_otras_cosas(self):
        self.assertIsNone(self.dur("recuérdame de comprar pan"))
        self.assertIsNone(self.dur("en casa"))

    def test_legible(self):
        self.assertEqual(fechas.duracion_legible(timedelta(minutes=80)), "1 hora y 20 minutos")
        self.assertEqual(fechas.duracion_legible(timedelta(seconds=3725)), "1 hora, 2 minutos y 5 segundos")


class TestInterpretar(unittest.TestCase):
    def test_temporizador(self):
        cuando, mensaje, tipo, dur = interpretar("pon un temporizador de 5 minutos", AHORA)
        self.assertEqual((cuando, mensaje, tipo, dur), (AHORA + timedelta(minutes=5), "", "temporizador",
                                                        timedelta(minutes=5)))

    def test_avisame_sin_mensaje_es_temporizador(self):
        self.assertEqual(interpretar("avísame en 20 minutos", AHORA)[2], "temporizador")

    def test_recordatorio_relativo(self):
        cuando, mensaje, tipo, _ = interpretar("recuérdame llamar a mamá en una hora", AHORA)
        self.assertEqual((cuando, mensaje, tipo), (AHORA + timedelta(hours=1), "Llamar a mamá", "recordatorio"))

    def test_recordatorio_con_fecha_y_hora(self):
        cuando, mensaje, _, _ = interpretar("recuérdame mañana a las 9 pagar la luz", AHORA)
        self.assertEqual((cuando, mensaje), (datetime(2026, 11, 24, 9, 0), "Pagar la luz"))

    def test_hora_pasada_es_manana(self):
        cuando, mensaje, _, _ = interpretar("recuérdame que tengo que sacar la basura a las 8 de la mañana", AHORA)
        self.assertEqual(cuando, datetime(2026, 11, 24, 8, 0))
        self.assertEqual(mensaje, "Tengo que sacar la basura")

    def test_dia_sin_hora(self):
        cuando, _, _, _ = interpretar("recuérdame el viernes llevar el coche al taller", AHORA)
        self.assertEqual(cuando, datetime(2026, 11, 27, 9, 0))

    def test_despiertame(self):
        cuando, mensaje, _, _ = interpretar("despiértame a las 7", AHORA)
        self.assertEqual(cuando, datetime(2026, 11, 24, 7, 0))
        self.assertIn("Arriba", mensaje)

    def test_sin_hora(self):
        self.assertIsNone(interpretar("recuérdame comprar pan", AHORA))


class TestGestor(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.archivo = Path(self.dir.name) / "r.json"
        self.gestor = Gestor(self.archivo)
        patch("builtins.print").start()
        self.addCleanup(patch.stopall)

    def test_se_guarda_y_se_carga(self):
        self.gestor.crear(AHORA + timedelta(hours=1), "Llamar", "recordatorio")
        otro = Gestor(self.archivo)
        self.assertEqual([r.mensaje for r in otro.pendientes()], ["Llamar"])

    def test_avisa_al_vencer_y_lo_borra(self):
        avisos = []
        self.gestor.suscribir(avisos.append)
        self.gestor.crear(AHORA + timedelta(minutes=5), "", "temporizador", timedelta(minutes=5))
        self.assertEqual(self.gestor.revisar(AHORA), [])
        self.gestor.revisar(AHORA + timedelta(minutes=5))
        self.assertEqual(avisos, ["¡Tiempo! Se acabó el temporizador de 5 minutos."])
        self.assertEqual(self.gestor.pendientes(), [])

    def test_aviso_atrasado(self):
        avisos = []
        self.gestor.suscribir(avisos.append)
        self.gestor.crear(AHORA, "Pagar la luz", "recordatorio")
        self.gestor.revisar(AHORA + timedelta(hours=3))
        self.assertEqual(avisos, ["Recordatorio: Pagar la luz. (Era para las 17:00)"])

    def test_hilo_avisa_solo(self):
        avisos = []
        self.gestor.suscribir(avisos.append)
        self.gestor.crear(datetime.now() + timedelta(milliseconds=300), "Ya", "recordatorio")
        self.gestor.iniciar()
        self.addCleanup(self.gestor.detener)
        reloj.sleep(1.6)
        self.assertEqual(avisos, ["Recordatorio: Ya."])


class TestSkill(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.skill = next(s for s in SKILLS if isinstance(s, RecordatoriosSkill))
        self.skill.gestor = Gestor(Path(self.dir.name) / "r.json")
        self.addCleanup(setattr, self.skill, "gestor", None)

    def test_crear_listar_cancelar(self):
        r = procesar("Pon un temporizador de 10 minutos")
        self.assertTrue(r.startswith("Temporizador de 10 minutos en marcha"))
        procesar("recuérdame llamar a mamá en una hora")
        lista = procesar("¿qué recordatorios tengo?")
        self.assertIn("1. Temporizador de 10 minutos", lista)
        self.assertIn("2. Llamar a mamá", lista)
        self.assertIn("Tienes varios", procesar("cancela el recordatorio"))
        self.assertEqual(procesar("cancela el recordatorio 2"), "Cancelado: Llamar a mamá.")
        self.assertEqual(procesar("cancela el temporizador"), "Cancelado: el temporizador.")
        self.assertEqual(procesar("qué recordatorios tengo"), "No tienes recordatorios ni temporizadores pendientes.")

    def test_cancelar_todos(self):
        procesar("avísame en 5 minutos")
        procesar("avísame en 10 minutos")
        self.assertEqual(procesar("cancela todos los temporizadores"), "Cancelados 2.")

    def test_no_choca_con_otras_skills(self):
        self.assertIn("en marcha", procesar("pon un temporizador de 1 minuto"))  # no es Spotify
        self.assertIn("te lo recuerdo", procesar("ponme un recordatorio mañana a las 10 de ir al banco"))

    def test_directo_si_entiende_la_hora(self):
        self.assertTrue(self.skill.directo("avísame en 20 minutos"))
        self.assertFalse(self.skill.directo("recuérdame lo del banco"))  # va a la IA

    def test_herramienta_ia(self):
        r = herramientas.ejecutar("recordatorio_crear", {"mensaje": "Sacar la ropa", "minutos": 99},
                                  "recuérdame sacar la ropa en 40 minutos")
        self.assertIn("Sacar la ropa", r)
        pendiente = self.skill.gestor.pendientes()[0]
        self.assertAlmostEqual((pendiente.cuando - datetime.now()).total_seconds(), 2400, delta=5)

    def test_herramienta_ia_hora(self):
        herramientas.ejecutar("recordatorio_crear", {"mensaje": "Banco", "fecha": "2099-01-01", "hora": "10:00"}, "")
        self.assertEqual(self.skill.gestor.pendientes()[0].cuando, datetime(2099, 1, 1, 10, 0))


class TestAvisoEnModoVoz(unittest.TestCase):
    def test_el_bucle_dice_el_aviso(self):
        from asistente.voz.bucle import BucleVoz

        bucle = BucleVoz("Jarvis")
        voz = MagicMock()
        voz.hablar.return_value = None
        dicho = threading.Event()
        voz.hablar.side_effect = lambda t: (dicho.set() if t.startswith("Recordatorio") else None)

        def escuchar(espera_max=None, detener=None):
            detener.wait(timeout=2)
            return ""

        voz.oido.escuchar.side_effect = escuchar
        bucle.voz = voz
        with patch("builtins.print"), patch("asistente.voz.bucle.recordatorios.sonar"):
            hilo = threading.Thread(target=bucle.ejecutar)
            hilo.start()
            reloj.sleep(0.1)
            bucle.avisar("Recordatorio: Llamar.")
            self.assertTrue(dicho.wait(timeout=2))
            bucle.parar()
            hilo.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
