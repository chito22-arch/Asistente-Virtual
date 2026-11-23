import base64
import re
from email.message import EmailMessage
from email.utils import parseaddr

from googleapiclient.errors import HttpError

from ..servicios.google_auth import FaltanCredenciales, servicio
from .base import Skill

MAX_RESULTADOS = 5

RE_LEER = re.compile(r"\blee(?:r)? (?:el )?(?:correo|email|mensaje) (?:n[uú]mero )?(\d+)")
RE_BUSCAR = re.compile(r"\bbusca(?:r)? (?:los )?(?:correos?|emails?|mensajes?) (de|sobre|con) (.+)")
RE_ENVIAR = re.compile(
    r"env[ií]a(?:r|le)? (?:un )?(?:correo|email|mensaje) a (\S+@\S+)\s+asunto:?\s*(.+?)\s+mensaje:?\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


class GmailSkill(Skill):
    nombre = "gmail"
    descripcion = (
        "Gmail: 'revisa mi correo', 'lee el correo 2', 'busca correos de juan', "
        "'envía un correo a x@y.com asunto: Hola mensaje: ...'"
    )

    def __init__(self) -> None:
        self.ultimos: list[str] = []  # ids de la última lista mostrada, para "lee el correo N"

    def puede_manejar(self, texto: str) -> bool:
        return bool(re.search(r"\b(correos?|emails?|gmail|bandeja)\b", texto))

    def ejecutar(self, texto: str, original: str) -> str:
        try:
            if m := RE_ENVIAR.search(original):
                return self._enviar(*(g.strip() for g in m.groups()))
            if m := RE_LEER.search(texto):
                return self._leer(int(m.group(1)))
            if m := RE_BUSCAR.search(texto):
                tipo, termino = m.groups()
                consulta = f"from:{termino}" if tipo == "de" else termino
                return self._listar(consulta, f"Correos que coinciden con '{termino}'")
            if texto.startswith(("envía", "envia", "enviar", "manda")):
                return "Formato: envía un correo a alguien@mail.com asunto: ... mensaje: ..."
            return self._listar("is:unread in:inbox", "Correos no leídos")
        except FaltanCredenciales as e:
            return str(e)
        except HttpError as e:
            return f"Error de Gmail: {e.reason}"

    # --- acciones ---------------------------------------------------------

    def _listar(self, consulta: str, titulo: str) -> str:
        gmail = servicio("gmail", "v1")
        resp = gmail.users().messages().list(userId="me", q=consulta, maxResults=MAX_RESULTADOS).execute()
        mensajes = resp.get("messages", [])
        self.ultimos = [m["id"] for m in mensajes]
        if not mensajes:
            return f"{titulo}: ninguno."

        lineas = [f"{titulo}:"]
        for i, m in enumerate(mensajes, 1):
            datos = gmail.users().messages().get(
                userId="me", id=m["id"], format="metadata", metadataHeaders=["From", "Subject"]
            ).execute()
            cab = _cabeceras(datos)
            remitente = parseaddr(cab.get("From", ""))[0] or cab.get("From", "?")
            lineas.append(f"  {i}. {remitente} — {cab.get('Subject', '(sin asunto)')}")
        lineas.append("Di 'lee el correo N' para abrir uno.")
        return "\n".join(lineas)

    def _leer(self, n: int) -> str:
        if not 1 <= n <= len(self.ultimos):
            return "Primero pide la lista ('revisa mi correo') y elige un número de ella."
        gmail = servicio("gmail", "v1")
        msg_id = self.ultimos[n - 1]
        datos = gmail.users().messages().get(userId="me", id=msg_id, format="full").execute()
        cab = _cabeceras(datos)
        cuerpo = _texto_plano(datos["payload"]) or datos.get("snippet", "")
        gmail.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()

        if len(cuerpo) > 1500:
            cuerpo = cuerpo[:1500] + "\n[...]"
        return f"De: {cab.get('From')}\nAsunto: {cab.get('Subject')}\n\n{cuerpo.strip()}"

    def _enviar(self, para: str, asunto: str, cuerpo: str) -> str:
        if not self.confirmar(f"Para: {para}\nAsunto: {asunto}\nMensaje: {cuerpo}\n¿Envío este correo?"):
            return "Envío cancelado."

        correo = EmailMessage()
        correo["To"] = para
        correo["Subject"] = asunto
        correo.set_content(cuerpo)
        raw = base64.urlsafe_b64encode(correo.as_bytes()).decode()
        servicio("gmail", "v1").users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"Correo enviado a {para}."


def _cabeceras(datos: dict) -> dict:
    return {h["name"]: h["value"] for h in datos.get("payload", {}).get("headers", [])}


def _texto_plano(parte: dict) -> str:
    """Busca recursivamente la parte text/plain del mensaje y la decodifica."""
    if parte.get("mimeType") == "text/plain" and parte.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(parte["body"]["data"]).decode("utf-8", errors="replace")
    for sub in parte.get("parts", []):
        if texto := _texto_plano(sub):
            return texto
    return ""
