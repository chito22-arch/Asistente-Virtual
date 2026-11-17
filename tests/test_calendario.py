"""Pruebas del intérprete de fechas y de la skill de Calendar (API falsa, sin credenciales)."""
import unittest
from datetime import date, datetime, time, timedelta
from unittest.mock import MagicMock, patch

from asistente.core import procesar
from asistente.skills.calendario import CalendarioSkill
from asistente.utils import fechas

HOY = date(2026, 11, 17)  # martes


class TestFechas(unittest.TestCase):
    def fecha(self, texto):
        return fechas.buscar_fecha(texto, HOY)[0]

    def test_relativas(self):
        self.assertEqual(self.fecha("hoy"), HOY)
        self.assertEqual(self.fecha("mañana"), date(2026, 11, 18))
        self.assertEqual(self.fecha("pasado mañana"), date(2026, 11, 19))

    def test_manana_como_momento_del_dia_no_es_fecha(self):
        self.assertIsNone(self.fecha("a las 9 de la mañana"))
        self.assertIsNone(self.fecha("el finde por la mañana"))

    def test_dia_semana(self):
        self.assertEqual(self.fecha("el viernes"), date(2026, 11, 20))
        self.assertEqual(self.fecha("el martes"), date(2026, 11, 24))  # hoy es martes: el siguiente
        self.assertEqual(self.fecha("el miercoles"), date(2026, 11, 18))

    def test_numericas_y_texto(self):
        self.assertEqual(self.fecha("el 3/12"), date(2026, 12, 3))
        self.assertEqual(self.fecha("el 5/1"), date(2027, 1, 5))  # ya pasó este año
        self.assertEqual(self.fecha("el 25 de diciembre"), date(2026, 12, 25))
        self.assertEqual(self.fecha("10/02/2027"), date(2027, 2, 10))

    def test_horas(self):
        h = lambda t: fechas.buscar_hora(t)[0]
        self.assertEqual(h("a las 10"), time(10, 0))
        self.assertEqual(h("a las 17:30"), time(17, 30))
        self.assertEqual(h("a las 5 de la tarde"), time(17, 0))
        self.assertEqual(h("a las 9 y media de la mañana"), time(9, 30))
        self.assertEqual(h("a la 1 menos cuarto"), time(0, 45))
        self.assertIsNone(h("a las 25"))

    def test_duracion(self):
        self.assertEqual(fechas.buscar_duracion("durante 2 horas")[0], timedelta(hours=2))
        self.assertEqual(fechas.buscar_duracion("durante 30 minutos")[0], timedelta(minutes=30))


class TestCalendario(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.eventos = self.api.events.return_value
        self.eventos.list.return_value.execute.return_value = {"items": [
            {"summary": "Dentista", "start": {"dateTime": "2026-11-17T17:30:00+01:00"},
             "end": {"dateTime": "2026-11-17T18:00:00+01:00"}},
            {"summary": "Cumpleaños", "start": {"date": "2026-11-17"}, "end": {"date": "2026-11-18"}},
        ]}
        p = patch("asistente.skills.calendario.servicio", return_value=self.api)
        p.start()
        self.addCleanup(p.stop)
        self.confirmar = patch.object(CalendarioSkill, "confirmar", return_value=True).start()
        self.addCleanup(patch.stopall)

    def insertado(self):
        return self.eventos.insert.call_args.kwargs["body"]

    def test_que_tengo_hoy(self):
        r = procesar("¿Qué tengo hoy?")
        self.assertIn("Dentista", r)
        self.assertIn("todo el día — Cumpleaños", r)

    def test_agenda_semana(self):
        procesar("agenda de esta semana")
        k = self.eventos.list.call_args.kwargs
        dias = datetime.fromisoformat(k["timeMax"]) - datetime.fromisoformat(k["timeMin"])
        self.assertEqual(dias, timedelta(days=7))

    def test_crear_reunion(self):
        r = procesar("Crea una reunión con Ana mañana a las 10")
        cuerpo = self.insertado()
        self.assertEqual(cuerpo["summary"], "Reunión con Ana")
        inicio = datetime.fromisoformat(cuerpo["start"]["dateTime"])
        fin = datetime.fromisoformat(cuerpo["end"]["dateTime"])
        self.assertEqual(inicio.date(), date.today() + timedelta(days=1))
        self.assertEqual(inicio.time(), time(10, 0))
        self.assertEqual(fin - inicio, timedelta(hours=1))
        self.assertTrue(r.startswith("Añadido"))

    def test_crear_con_titulo_y_duracion(self):
        procesar("crea un evento Revisión del coche pasado mañana a las 5 de la tarde durante 30 minutos")
        cuerpo = self.insertado()
        self.assertEqual(cuerpo["summary"], "Revisión del coche")
        fin = datetime.fromisoformat(cuerpo["end"]["dateTime"])
        self.assertEqual(fin.time(), time(17, 30))

    def test_crear_todo_el_dia(self):
        procesar("añade un evento Vacaciones el 25 de diciembre")
        cuerpo = self.insertado()
        self.assertEqual(cuerpo["summary"], "Vacaciones")
        self.assertIn("date", cuerpo["start"])

    def test_crear_sin_fecha_pregunta(self):
        self.assertIn("¿Para cuándo?", procesar("crea un evento"))
        self.eventos.insert.assert_not_called()

    def test_cancelar(self):
        self.confirmar.return_value = False
        self.assertEqual(procesar("crea una cita médico mañana a las 9"), "Evento cancelado.")
        self.eventos.insert.assert_not_called()

    def test_correo_sigue_en_gmail(self):
        with patch("asistente.skills.gmail.servicio") as gmail:
            gmail.return_value.users.return_value.messages.return_value.list.return_value \
                .execute.return_value = {}
            self.assertIn("Correos que coinciden", procesar("busca correos sobre agenda"))


if __name__ == "__main__":
    unittest.main()
