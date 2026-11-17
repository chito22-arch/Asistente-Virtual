"""Pruebas de la skill de Spotify con un cliente falso (no necesita cuenta ni claves)."""
import unittest
from unittest.mock import MagicMock, patch

from spotipy.exceptions import SpotifyException

from asistente.core import procesar
from asistente.skills.calendario import CalendarioSkill


def cancion(nombre, artista, uri="spotify:track:1"):
    return {"name": nombre, "uri": uri, "artists": [{"name": artista}]}


class TestSpotify(unittest.TestCase):
    def setUp(self):
        self.sp = MagicMock()
        self.sp.devices.return_value = {"devices": [{"id": "pc1", "is_active": True, "type": "Computer"}]}
        self.sp.search.return_value = {"tracks": {"items": [cancion("Bohemian Rhapsody", "Queen")]}}
        patch("asistente.skills.spotify.cliente", return_value=self.sp).start()
        self.addCleanup(patch.stopall)

    def test_poner_cancion(self):
        r = procesar("Pon Bohemian Rhapsody")
        self.assertEqual(r, "Reproduciendo Bohemian Rhapsody de Queen.")
        self.sp.start_playback.assert_called_once_with(device_id="pc1", uris=["spotify:track:1"])

    def test_cancion_con_artista(self):
        procesar("pon despacito de luis fonsi")
        q = self.sp.search.call_args_list[0].kwargs["q"]
        self.assertEqual(q, "track:despacito artist:luis fonsi")

    def test_musica_de_artista(self):
        self.sp.search.return_value = {"artists": {"items": [{"name": "Bad Bunny", "uri": "spotify:artist:9"}]}}
        r = procesar("pon música de bad bunny")
        self.assertEqual(r, "Reproduciendo música de Bad Bunny.")
        self.sp.start_playback.assert_called_once_with(device_id="pc1", context_uri="spotify:artist:9")

    def test_mi_playlist(self):
        self.sp.current_user_playlists.return_value = {"items": [{"name": "Gym 2026", "uri": "spotify:playlist:g"}]}
        r = procesar("pon la playlist gym")
        self.assertEqual(r, "Reproduciendo la playlist Gym 2026.")
        self.sp.search.assert_not_called()

    def test_controles(self):
        self.assertEqual(procesar("pausa"), "Música en pausa.")
        self.assertEqual(procesar("siguiente canción"), "Siguiente canción.")
        self.assertEqual(procesar("anterior"), "Canción anterior.")
        self.assertEqual(procesar("pon música"), "Reanudando la música.")

    def test_volumen(self):
        self.assertEqual(procesar("volumen 40"), "Volumen al 40%.")
        self.sp.current_playback.return_value = {"device": {"volume_percent": 95}}
        self.assertEqual(procesar("sube el volumen"), "Volumen al 100%.")
        self.assertEqual(procesar("baja el volumen"), "Volumen al 85%.")

    def test_que_suena(self):
        self.sp.current_playback.return_value = {"is_playing": True, "item": cancion("Yesterday", "The Beatles")}
        self.assertEqual(procesar("¿Qué suena?"), "Sonando: Yesterday de The Beatles.")

    def test_sin_premium(self):
        self.sp.start_playback.side_effect = SpotifyException(403, -1, "Premium required")
        self.assertIn("Premium", procesar("pon algo de música"))

    def test_sin_dispositivo(self):
        self.sp.devices.return_value = {"devices": []}
        with patch("asistente.servicios.spotify.os.startfile"), patch("asistente.servicios.spotify.time.sleep"), \
                patch("asistente.servicios.spotify.time.monotonic", side_effect=[0, 1, 99]):
            self.assertIn("No encuentro ningún Spotify", procesar("siguiente"))

    def test_ponme_evento_sigue_en_calendario(self):
        with patch.object(CalendarioSkill, "_crear", return_value="cal") as crear:
            self.assertEqual(procesar("ponme una cita mañana a las 9"), "cal")
        crear.assert_called_once()

    def test_abre_spotify_sigue_siendo_app(self):
        with patch("asistente.skills.apps.os.startfile") as abrir:
            procesar("abre spotify")
        abrir.assert_called_once_with("spotify:")


if __name__ == "__main__":
    unittest.main()
