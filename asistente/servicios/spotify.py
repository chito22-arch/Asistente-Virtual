"""Conexión con la API de Spotify (spotipy + OAuth).

Las claves se leen de .env (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI).
La primera vez se abre el navegador para autorizar; el token se guarda en .cache-spotify
(ignorado por git) y se renueva solo.
"""
import os
import time
from functools import lru_cache
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

RAIZ = Path(__file__).resolve().parents[2]
CACHE = RAIZ / ".cache-spotify"

SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
])


class FaltaConfigSpotify(Exception):
    pass


@lru_cache
def cliente() -> spotipy.Spotify:
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not client_id or not secret:
        raise FaltaConfigSpotify(
            "Faltan SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en .env (ver README, sección 'Configurar Spotify')."
        )
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=secret,
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
        scope=SCOPES,
        cache_handler=spotipy.CacheFileHandler(cache_path=str(CACHE)),
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def dispositivo(sp: spotipy.Spotify, espera: float = 12.0) -> str | None:
    """Devuelve el id de un dispositivo donde reproducir.

    Prefiere el activo; si no hay, usa este PC. Si Spotify está cerrado, lo abre y espera a que aparezca.
    """
    for intento in range(2):
        dispositivos = sp.devices().get("devices", [])
        if activo := next((d for d in dispositivos if d["is_active"]), None):
            return activo["id"]
        if dispositivos:
            pc = next((d for d in dispositivos if d["type"] == "Computer"), dispositivos[0])
            return pc["id"]
        if intento == 0:
            os.startfile("spotify:")
            limite = time.monotonic() + espera
            while time.monotonic() < limite:
                time.sleep(1)
                if sp.devices().get("devices"):
                    break
    return None
