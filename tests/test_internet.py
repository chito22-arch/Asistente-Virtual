"""Pruebas de búsquedas, noticias y el tiempo con internet simulado."""
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from asistente import core
from asistente.core import procesar
from asistente.ia import herramientas
from asistente.ia.agente import Agente
from asistente.ia.proveedores import Respuesta
from asistente.servicios import internet
from asistente.servicios.internet import Resultado
from asistente.voz.bucle import recortar_para_voz

RESULTADOS = [
    Resultado("¿Quién ganó el Mundial 2022?", "https://www.fifa.com/es/articulo", "Argentina ganó la Copa Mundial de Catar 2022."),
    Resultado("Final del Mundial", "https://www.marca.com/final", "Argentina venció a Francia en los penaltis."),
]
NOTICIAS = [Resultado("El Gobierno aprueba los presupuestos", "https://rtve.es/a", "...", "2026-11-23", "RTVE"),
            Resultado("Temporal de lluvia en el norte", "https://elpais.com/b", "...", "2026-11-23", "El País")]


class TestSinIA(unittest.TestCase):
    def setUp(self):
        self.buscar = patch.object(internet, "buscar", return_value=RESULTADOS).start()
        patch.object(internet, "noticias", return_value=NOTICIAS).start()
        self.tiempo = patch.object(internet, "tiempo", return_value="Hoy: soleado").start()
        self.addCleanup(patch.stopall)

    def test_lo_que_no_entiende_lo_busca(self):
        r = procesar("¿Quién ganó el mundial de 2022?")
        self.assertEqual(r.splitlines()[0], "Según fifa.com: Argentina ganó la Copa Mundial de Catar 2022.")
        self.assertIn("marca.com", r)

    def test_busqueda_explicita(self):
        procesar("busca en internet recetas de paella")
        self.buscar.assert_called_once_with("recetas de paella", n=3)

    def test_una_palabra_suelta_no_se_busca(self):
        self.assertIn("No entendí", procesar("patata"))
        self.buscar.assert_not_called()

    def test_sin_conexion(self):
        self.buscar.side_effect = internet.SinConexion("sin red")
        self.assertIn("no puedo buscarlo", procesar("cuántos habitantes tiene Lugo"))

    def test_noticias(self):
        r = procesar("dime las noticias de hoy")
        self.assertIn("1. El Gobierno aprueba los presupuestos (RTVE)", r)
        internet.noticias.assert_called_with("")

    def test_noticias_de_un_tema(self):
        procesar("noticias sobre el Real Madrid")
        internet.noticias.assert_called_with("el real madrid")

    def test_tiempo_con_ciudad_y_dia(self):
        procesar("¿Qué tiempo hará mañana en Sevilla?")
        self.tiempo.assert_called_once_with("Sevilla", date.today() + timedelta(days=1))

    def test_tiempo_sin_ciudad(self):
        procesar("va a llover hoy")
        self.tiempo.assert_called_once_with("", date.today())

    def test_gmail_sigue_mandando_en_correos(self):
        with patch("asistente.skills.gmail.servicio") as gmail:
            gmail.return_value.users.return_value.messages.return_value.list.return_value.execute.return_value = {}
            procesar("busca correos de amazon")
        self.buscar.assert_not_called()


class ModeloFalso:
    def __init__(self, *respuestas):
        self.respuestas, self.recibido = list(respuestas), []

    def chat(self, mensajes, herramientas_):
        self.recibido.append((list(mensajes), herramientas_))
        return self.respuestas.pop(0)


class TestConIA(unittest.TestCase):
    def setUp(self):
        patch.object(internet, "buscar", return_value=RESULTADOS).start()
        patch.object(internet, "leer_pagina", return_value="").start()
        self.addCleanup(patch.stopall)

    def test_busca_y_resume_con_fuentes(self):
        modelo = ModeloFalso(
            Respuesta("", [("buscar_internet", {"consulta": "ganador mundial 2022"})], {"role": "assistant", "content": ""}),
            Respuesta("Lo ganó Argentina, que venció a Francia en los penaltis.", [], {}))
        r = Agente(modelo).responder("¿quién ganó el último mundial?")
        self.assertEqual(r, "Lo ganó Argentina, que venció a Francia en los penaltis.\nFuentes: fifa.com, marca.com")
        mensajes, tools = modelo.recibido[1]
        self.assertEqual(tools, [])  # la segunda pasada solo responde
        self.assertIn("Argentina ganó", mensajes[-2]["content"])  # recibe los resultados completos
        self.assertIn("SOLO la información", mensajes[-1]["content"])

    def test_las_fuentes_no_se_leen_en_voz_alta(self):
        self.assertEqual(recortar_para_voz("Lo ganó Argentina.\nFuentes: fifa.com"), "Lo ganó Argentina.")

    def test_el_tiempo_va_directo(self):
        agente = MagicMock()
        core.activar_ia(agente)
        self.addCleanup(core.activar_ia, None)
        with patch.object(internet, "tiempo", return_value="Hoy: soleado"):
            self.assertEqual(procesar("qué tiempo hace en Madrid"), "Hoy: soleado")
        agente.responder.assert_not_called()

    def test_herramienta_tiempo_usa_la_fecha_del_usuario(self):
        with patch.object(internet, "tiempo", return_value="ok") as tiempo:
            herramientas.ejecutar("tiempo", {"ciudad": "Bilbao", "fecha": "1999-01-01"}, "¿lloverá pasado mañana en Bilbao?")
        tiempo.assert_called_once_with("Bilbao", date.today() + timedelta(days=2))


class TestLeerPaginas(unittest.TestCase):
    def test_saca_los_parrafos_relevantes(self):
        html = ("<html><nav><p>Menú con Valencia y más cosas del menú de la web</p></nav><script>x()</script>"
                "<p>Valencia es la tercera ciudad de España, con unos 800.000 habitantes en el municipio.</p>"
                "<p>Este párrafo habla de otra cosa completamente diferente y no importa nada.</p></html>")
        lector = internet._Parrafos()
        lector.feed(html)
        self.assertEqual(len(lector.bloques), 2)  # el menú no cuenta
        respuesta = MagicMock()
        respuesta.headers.get.return_value = "text/html"
        respuesta.headers.get_content_charset.return_value = "utf-8"
        respuesta.read.return_value = html.encode()
        respuesta.__enter__.return_value = respuesta
        with patch("urllib.request.urlopen", return_value=respuesta):
            texto = internet.leer_pagina("https://x.es", "habitantes de Valencia")
        self.assertEqual(texto, "Valencia es la tercera ciudad de España, con unos 800.000 habitantes en el municipio.")

    def test_titulares_vacios_fuera(self):
        self.assertTrue(internet.TITULAR_VACIO.search("Últimas noticias"))
        self.assertTrue(internet.TITULAR_VACIO.search("Noticias de hoy, viernes 30 de octubre"))
        self.assertFalse(internet.TITULAR_VACIO.search("El Gobierno aprueba los presupuestos"))


class TestTiempo(unittest.TestCase):
    def test_formato(self):
        hoy = date.today().isoformat()
        respuestas = [
            {"results": [{"name": "Sevilla", "latitude": 37.4, "longitude": -6.0}]},
            {"current": {"temperature_2m": 18.4, "weather_code": 1},
             "daily": {"time": [hoy], "weather_code": [61], "temperature_2m_min": [9.2],
                       "temperature_2m_max": [19.6], "precipitation_probability_max": [43]}},
        ]
        with patch.object(internet, "_get_json", side_effect=respuestas):
            r = internet.tiempo("Sevilla")
        self.assertEqual(r, "Ahora en Sevilla: 18 grados, casi despejado. "
                            "Hoy: lluvia débil, entre 9 y 20 grados, 43% de probabilidad de lluvia.")

    def test_sin_ciudad_pregunta(self):
        with patch.dict("os.environ", {"CIUDAD": ""}):
            self.assertIn("¿De qué ciudad?", internet.tiempo(""))


if __name__ == "__main__":
    unittest.main()
