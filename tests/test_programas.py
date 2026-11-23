"""Pruebas de la búsqueda de programas instalados (con una lista falsa, sin abrir nada)."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from asistente import core
from asistente.core import procesar
from asistente.servicios import programas
from asistente.servicios.programas import Catalogo, Programa, buscar, es_util

LISTA = [
    Programa("Google Chrome", "Chrome"),
    Programa("Discord", "com.squirrel.Discord.Discord"),
    Programa("Visual Studio Code", "Microsoft.VisualStudioCode"),
    Programa("Bloc de notas", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
    Programa("Configuración", "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel"),
    Programa("Fotos", "Microsoft.Windows.Photos_8wekyb3d8bbwe!App"),
    Programa("Epic Games Launcher", "{6D809377}\\Epic Games\\Launcher\\EpicGamesLauncher.exe"),
    Programa("Big Walk", "steam://rungameid/1478500"),
    Programa("Word", "Microsoft.Office.WINWORD.EXE.15"),
    Programa("WordPad", "{6D809377}\\Windows NT\\Accessories\\wordpad.exe"),
    Programa("VLC media player", "{6D809377}\\VideoLAN\\VLC\\vlc.exe"),
]


def nombre(consulta):
    p, _ = buscar(consulta, LISTA)
    return p.nombre if p else None


class TestBusqueda(unittest.TestCase):
    def test_exacto_y_sin_tildes(self):
        self.assertEqual(nombre("discord"), "Discord")
        self.assertEqual(nombre("configuracion"), "Configuración")
        self.assertEqual(nombre("bloc de notas"), "Bloc de notas")

    def test_parte_del_nombre(self):
        self.assertEqual(nombre("chrome"), "Google Chrome")
        self.assertEqual(nombre("visual studio"), "Visual Studio Code")
        self.assertEqual(nombre("epic games"), "Epic Games Launcher")
        self.assertEqual(nombre("vlc"), "VLC media player")

    def test_prefiere_el_nombre_exacto(self):
        self.assertEqual(nombre("word"), "Word")

    def test_tolera_errores_de_transcripcion(self):
        self.assertEqual(nombre("discor"), "Discord")
        self.assertEqual(nombre("big walks"), "Big Walk")

    def test_no_se_inventa_programas(self):
        p, _ = buscar("photoshop", LISTA)
        self.assertIsNone(p)
        self.assertIsNone(nombre("hola que tal"))

    def test_filtra_lo_que_no_es_un_programa(self):
        self.assertFalse(es_util(Programa("Git Release Notes", "C:\\Git\\ReleaseNotes.html")))
        self.assertFalse(es_util(Programa("Git FAQs", "https://gitforwindows.org/faq")))
        self.assertFalse(es_util(Programa("Desinstalar Steam", "C:\\Steam\\uninstall.exe")))
        self.assertFalse(es_util(Programa("emulador", "C:\\Users\\x\\Downloads\\emulador.zip")))
        self.assertTrue(es_util(Programa("Big Walk", "steam://rungameid/1478500")))


class TestCatalogo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.archivo = Path(self.dir.name) / "p.json"
        self.llamadas = 0

    def listar(self):
        self.llamadas += 1
        return LISTA + [Programa("Algo Readme", "C:\\readme.txt")]

    def test_cache_en_disco(self):
        Catalogo(self.archivo, self.listar).programas
        otro = Catalogo(self.archivo, self.listar)
        self.assertEqual(len(otro.programas), len(LISTA))  # sin la basura
        self.assertEqual(self.llamadas, 1)  # el segundo leyó la caché

    def test_si_no_lo_encuentra_refresca_una_vez(self):
        cat = Catalogo(self.archivo, self.listar)
        cat.programas
        cat._actualizado = time.time() - 3600  # caché de hace una hora
        cat.buscar("photoshop")
        self.assertEqual(self.llamadas, 2)
        cat.buscar("photoshop")  # justo después no vuelve a preguntar a Windows
        self.assertEqual(self.llamadas, 2)


class TestSkill(unittest.TestCase):
    def setUp(self):
        dir_ = tempfile.TemporaryDirectory()
        self.addCleanup(dir_.cleanup)
        cat = Catalogo(Path(dir_.name) / "p.json", lambda: LISTA)
        patch.object(programas, "_catalogo", cat).start()
        self.abrir = patch.object(programas, "abrir").start()
        self.explorer = patch("asistente.skills.apps.subprocess.Popen").start()
        self.addCleanup(patch.stopall)

    def test_abre_programa_instalado(self):
        self.assertEqual(procesar("Abre Discord"), "Abriendo Discord.")
        self.assertEqual(self.abrir.call_args.args[0].nombre, "Discord")
        self.assertEqual(procesar("abre el programa visual studio code"), "Abriendo Visual Studio Code.")
        self.assertEqual(procesar("ábreme el chrome"), "Abriendo Google Chrome.")

    def test_carpetas(self):
        self.assertEqual(procesar("abre la carpeta de descargas"), "Abriendo carpeta de descargas.")
        self.explorer.assert_called_once_with(["explorer.exe", "shell:Downloads"])
        procesar("abre fotos")  # es la app, no la carpeta
        self.assertEqual(self.abrir.call_args.args[0].nombre, "Fotos")

    def test_no_encontrado_con_sugerencias(self):
        self.assertEqual(procesar("abre wordpat"), "Abriendo WordPad.")  # error pequeño: lo entiende
        r = procesar("abre photoshop")
        self.assertTrue(r.startswith("No encuentro «photoshop»"))
        self.abrir.assert_called_once()  # solo el WordPad

    def test_directo_solo_si_lo_encuentra(self):
        from asistente.skills.apps import AppsSkill

        skill = next(s for s in core.SKILLS if isinstance(s, AppsSkill))
        self.assertTrue(skill.directo("abre discord"))
        self.assertTrue(skill.directo("abre la carpeta descargas"))
        self.assertFalse(skill.directo("abre el programa para editar fotos de adobe"))  # a la IA


if __name__ == "__main__":
    unittest.main()
