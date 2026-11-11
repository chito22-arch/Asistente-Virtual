"""Autenticación OAuth con Google, compartida por Gmail y Calendar.

La primera vez abre el navegador para que autorices el acceso; después guarda
token.json y se renueva solo. credentials.json y token.json NO se suben a GitHub.
"""
from functools import lru_cache
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

RAIZ = Path(__file__).resolve().parents[2]
CREDENCIALES = RAIZ / "credentials.json"
TOKEN = RAIZ / "token.json"

# Se piden ya los permisos de Calendar para no tener que volver a autorizar en la siguiente fase.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


class FaltanCredenciales(Exception):
    pass


def obtener_credenciales() -> Credentials:
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENCIALES.exists():
            raise FaltanCredenciales(
                f"Falta {CREDENCIALES.name}. Descárgalo de Google Cloud Console "
                "(ver README, sección 'Configurar Google')."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


@lru_cache
def servicio(nombre: str, version: str):
    """Devuelve un cliente de la API de Google, p. ej. servicio('gmail', 'v1')."""
    return build(nombre, version, credentials=obtener_credenciales(), cache_discovery=False)
