"""Modelos de lenguaje que puede usar el agente. Hoy: Ollama (local). Mañana: Claude, etc.

Todos devuelven una `Respuesta` común y aceptan mensajes en formato estilo OpenAI:
{"role": "system"|"user"|"assistant"|"tool", "content": ..., "tool_calls": [...]}.
"""
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Respuesta:
    texto: str
    llamadas: list[tuple[str, dict]] = field(default_factory=list)
    mensaje: dict = field(default_factory=dict)  # para añadir al historial tal cual


class IANoDisponible(Exception):
    pass


class Ollama:
    def __init__(self) -> None:
        import ollama

        self._ollama = ollama
        self.host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        self.modelo = os.getenv("IA_MODELO", "qwen3:8b")
        self.cliente = ollama.Client(host=self.host, timeout=90)
        self._acepta_think = True

    @property
    def nombre(self) -> str:
        return f"Ollama · {self.modelo}"

    def disponible(self) -> bool:
        """Comprueba que el servidor responde y tiene el modelo. Si Ollama está cerrado, lo arranca."""
        if not self._responde():
            ejecutable = shutil.which("ollama") or str(Path(os.getenv("LOCALAPPDATA", "")) / "Programs/Ollama/ollama.exe")
            if not Path(ejecutable).exists():
                return False
            subprocess.Popen([ejecutable, "serve"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            limite = time.monotonic() + 15
            while time.monotonic() < limite and not self._responde():
                time.sleep(0.5)
        try:
            modelos = {m.model for m in self.cliente.list().models}
        except Exception:
            return False
        return self.modelo in modelos or f"{self.modelo}:latest" in modelos

    def _responde(self) -> bool:
        try:
            self.cliente.list()
            return True
        except Exception:
            return False

    def precargar(self) -> None:
        """Carga el modelo en la GPU en segundo plano para que la primera respuesta sea rápida."""
        threading.Thread(target=lambda: self._seguro(
            lambda: self.cliente.generate(model=self.modelo, prompt="", keep_alive="30m")), daemon=True).start()

    @staticmethod
    def _seguro(fn):
        try:
            fn()
        except Exception:
            pass

    def chat(self, mensajes: list[dict], herramientas: list[dict]) -> Respuesta:
        kwargs = dict(model=self.modelo, messages=mensajes, tools=herramientas, keep_alive="30m",
                      options={"temperature": 0.2})
        try:
            if self._acepta_think:
                try:
                    r = self.cliente.chat(**kwargs, think=False)  # sin "razonamiento": mucho más rápido
                except self._ollama.ResponseError as e:
                    if "think" not in str(e).lower():
                        raise
                    self._acepta_think = False  # el modelo no admite ese parámetro (p. ej. llama3.1)
                    r = self.cliente.chat(**kwargs)
            else:
                r = self.cliente.chat(**kwargs)
        except Exception as e:
            raise IANoDisponible(str(e)) from e

        m = r.message
        llamadas = [(c.function.name, dict(c.function.arguments or {})) for c in (m.tool_calls or [])]
        mensaje = {"role": "assistant", "content": m.content or ""}
        if m.tool_calls:
            mensaje["tool_calls"] = [{"function": {"name": n, "arguments": a}} for n, a in llamadas]
        texto = re.sub(r"<think>.*?</think>", "", m.content or "", flags=re.S).strip()
        return Respuesta(texto, llamadas, mensaje)


def crear_proveedor():
    """Devuelve el proveedor configurado en .env (IA_PROVEEDOR) o None si está desactivado."""
    nombre = os.getenv("IA_PROVEEDOR", "ollama").lower()
    if nombre in ("", "ninguno", "no", "off"):
        return None
    if nombre == "ollama":
        return Ollama()
    raise ValueError(f"IA_PROVEEDOR desconocido: {nombre}")
