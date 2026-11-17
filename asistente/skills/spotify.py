import re

from spotipy.exceptions import SpotifyException

from ..servicios.spotify import FaltaConfigSpotify, cliente, dispositivo
from .base import Skill

RE_PONER = re.compile(r"^(?:pon(?:me)?|reproduce|play|quiero escuchar|escuchar)\b\s*(.*)$")
RE_PAUSA = re.compile(r"^(?:pausa|pausar|para|det[eé]n|parar)\b(?: la)?(?: m[uú]sica| canci[oó]n| spotify)?$")
RE_REANUDAR = re.compile(r"^(?:reanuda|contin[uú]a|sigue|resume)\b(?: la)?(?: m[uú]sica| canci[oó]n| spotify)?$")
RE_SIGUIENTE = re.compile(r"^(?:siguiente|salta|pasa|cambia)\b(?: de)?(?: la)?(?: canci[oó]n| tema)?$")
RE_ANTERIOR = re.compile(r"^(?:anterior|atr[aá]s|la anterior|canci[oó]n anterior|vuelve a la anterior)$")
RE_QUE_SUENA = re.compile(r"\bqu[eé] (?:suena|est[aá] sonando|canci[oó]n es|canci[oó]n suena)\b")
RE_VOLUMEN = re.compile(r"\b(sube|baja|volumen)\b.*?\bvolumen\b|^volumen\b|^(sube|baja)\b")
RE_ALEATORIO = re.compile(r"\b(aleatorio|shuffle)\b")

GENERICO = {"", "música", "musica", "la música", "la musica", "algo", "spotify", "algo de música"}


class SpotifySkill(Skill):
    nombre = "spotify"
    descripcion = (
        "Spotify: 'pon Bohemian Rhapsody', 'pon música de Bad Bunny', 'pon la playlist Gym', "
        "'pausa', 'siguiente', 'qué suena', 'volumen 40', 'sube el volumen'"
    )

    def puede_manejar(self, texto: str) -> bool:
        return any(r.search(texto) for r in (RE_PONER, RE_PAUSA, RE_REANUDAR, RE_SIGUIENTE,
                                             RE_ANTERIOR, RE_QUE_SUENA, RE_VOLUMEN, RE_ALEATORIO))

    def ejecutar(self, texto: str, original: str) -> str:
        try:
            sp = cliente()
            if RE_QUE_SUENA.search(texto):
                return self._que_suena(sp)
            if RE_PAUSA.search(texto):
                sp.pause_playback()
                return "Música en pausa."
            if RE_SIGUIENTE.search(texto):
                sp.next_track(device_id=self._dispositivo(sp))
                return "Siguiente canción."
            if RE_ANTERIOR.search(texto):
                sp.previous_track(device_id=self._dispositivo(sp))
                return "Canción anterior."
            if RE_ALEATORIO.search(texto):
                activar = not re.search(r"\b(quita|desactiva|sin|apaga)\b", texto)
                sp.shuffle(activar, device_id=self._dispositivo(sp))
                return f"Aleatorio {'activado' if activar else 'desactivado'}."
            if RE_VOLUMEN.search(texto):
                return self._volumen(sp, texto)
            if RE_REANUDAR.search(texto):
                sp.start_playback(device_id=self._dispositivo(sp))
                return "Reanudando."
            if m := RE_PONER.search(texto):
                return self._poner(sp, m.group(1).strip())
            return "No entendí qué hacer en Spotify."
        except FaltaConfigSpotify as e:
            return str(e)
        except SinDispositivo:
            return "No encuentro ningún Spotify abierto. Abre la app de Spotify e inténtalo de nuevo."
        except SpotifyException as e:
            if e.http_status == 403:
                return "Spotify no lo permite: el control de reproducción requiere una cuenta Premium."
            if e.http_status == 404:
                return "No hay ningún reproductor activo. Abre Spotify y pon algo una vez."
            return f"Error de Spotify: {e.msg}"

    # --- acciones ---------------------------------------------------------

    def _dispositivo(self, sp) -> str:
        if not (d := dispositivo(sp)):
            raise SinDispositivo
        return d

    def _poner(self, sp, que: str) -> str:
        disp = self._dispositivo(sp)

        if que in GENERICO:
            sp.start_playback(device_id=disp)
            return "Reanudando la música."

        if m := re.match(r"^(?:la |mi )?(?:playlist|lista)(?: de reproducción)? (.+)$", que):
            nombre = m.group(1)
            playlist = self._buscar_mi_playlist(sp, nombre) or _primero(
                sp.search(q=nombre, type="playlist", limit=5), "playlists")
            if not playlist:
                return f"No encontré la playlist '{nombre}'."
            sp.start_playback(device_id=disp, context_uri=playlist["uri"])
            return f"Reproduciendo la playlist {playlist['name']}."

        if m := re.match(r"^(?:el )?(?:álbum|album|disco) (.+)$", que):
            album = _primero(sp.search(q=m.group(1), type="album", limit=1), "albums")
            if not album:
                return f"No encontré el álbum '{m.group(1)}'."
            sp.start_playback(device_id=disp, context_uri=album["uri"])
            return f"Reproduciendo el álbum {album['name']} de {_artistas(album)}."

        if m := re.match(r"^(?:música|musica|algo|canciones|temas) de (.+)$", que):
            artista = _primero(sp.search(q=m.group(1), type="artist", limit=1), "artists")
            if not artista:
                return f"No encontré al artista '{m.group(1)}'."
            sp.start_playback(device_id=disp, context_uri=artista["uri"])
            return f"Reproduciendo música de {artista['name']}."

        cancion = self._buscar_cancion(sp, re.sub(r"^(?:la canción|la cancion|el tema) ", "", que))
        if not cancion:
            return f"No encontré '{que}' en Spotify."
        sp.start_playback(device_id=disp, uris=[cancion["uri"]])
        return f"Reproduciendo {cancion['name']} de {_artistas(cancion)}."

    def _buscar_cancion(self, sp, que: str) -> dict | None:
        # "despacito de luis fonsi" -> primero busca título + artista; si no, búsqueda libre.
        if " de " in que:
            titulo, artista = que.rsplit(" de ", 1)
            if r := _primero(sp.search(q=f"track:{titulo} artist:{artista}", type="track", limit=1), "tracks"):
                return r
        return _primero(sp.search(q=que, type="track", limit=1), "tracks")

    def _buscar_mi_playlist(self, sp, nombre: str) -> dict | None:
        for p in sp.current_user_playlists(limit=50).get("items", []):
            if p and nombre.lower() in p["name"].lower():
                return p
        return None

    def _que_suena(self, sp) -> str:
        actual = sp.current_playback()
        if not actual or not actual.get("item"):
            return "Ahora mismo no suena nada."
        item = actual["item"]
        estado = "Sonando" if actual.get("is_playing") else "En pausa"
        return f"{estado}: {item['name']} de {_artistas(item)}."

    def _volumen(self, sp, texto: str) -> str:
        if m := re.search(r"(\d{1,3})", texto):
            nivel = int(m.group(1))
        else:
            actual = (sp.current_playback() or {}).get("device", {}).get("volume_percent")
            if actual is None:
                return "No puedo leer el volumen actual. Prueba con 'volumen 50'."
            nivel = actual + (10 if "sube" in texto else -10)
        nivel = max(0, min(100, nivel))
        sp.volume(nivel, device_id=self._dispositivo(sp))
        return f"Volumen al {nivel}%."


class SinDispositivo(Exception):
    pass


def _primero(resultado: dict, clave: str) -> dict | None:
    items = [i for i in resultado.get(clave, {}).get("items", []) if i]
    return items[0] if items else None


def _artistas(item: dict) -> str:
    return ", ".join(a["name"] for a in item.get("artists", [])) or "?"
