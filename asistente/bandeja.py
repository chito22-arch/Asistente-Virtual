"""Icono en la bandeja del sistema (junto al reloj) con Jarvis funcionando en segundo plano.

El color indica el estado: verde escuchando, naranja pensando, azul hablando,
gris cargando o silenciado, rojo error. Doble clic: escribir una orden.
"""
import os
import threading
import traceback
from pathlib import Path

import pystray
from PIL import Image, ImageDraw, ImageFont

from . import __version__, interfaz, windows
from .servicios import microfonos
from .core import procesar
from .voz.bucle import BucleVoz

COLORES = {
    "cargando": (140, 140, 140), "escuchando": (46, 160, 67), "pensando": (230, 150, 20),
    "hablando": (40, 120, 220), "silenciado": (110, 110, 110), "error": (200, 50, 50),
}
TEXTOS = {
    "cargando": "cargando…", "escuchando": "escuchando", "pensando": "pensando…",
    "hablando": "hablando", "silenciado": "micrófono silenciado", "error": "error (mira el registro)",
}


def dibujar_icono(estado: str, tam: int = 64) -> Image.Image:
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, tam - 2, tam - 2), fill=COLORES.get(estado, COLORES["error"]))
    try:
        fuente = ImageFont.truetype("segoeuib.ttf", int(tam * 0.6))
    except OSError:
        fuente = ImageFont.load_default()
    d.text((tam / 2, tam / 2), "J", fill="white", font=fuente, anchor="mm")
    if estado == "silenciado":
        d.line((10, tam - 10, tam - 10, 10), fill=(220, 50, 50), width=max(3, tam // 10))
    return img


def guardar_icono(ruta: Path) -> None:
    ruta.parent.mkdir(exist_ok=True)
    dibujar_icono("escuchando", 256).save(ruta, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)])


class DialogoConfirmacion:
    """Confirmaciones con ventanas cuando la orden se escribió desde el icono."""

    def __init__(self, raiz, titulo: str) -> None:
        self.raiz, self.titulo = raiz, titulo

    def preguntar(self, pregunta: str) -> str:
        from tkinter import messagebox

        return "sí" if messagebox.askyesno(self.titulo, pregunta, parent=self.raiz) else "no"


class Bandeja:
    def __init__(self, nombre: str) -> None:
        self.nombre = nombre
        self.bucle = BucleVoz(nombre, al_cambiar_estado=self._mostrar_estado)
        self._dialogo_abierto = threading.Lock()
        self.icono = pystray.Icon("jarvis", dibujar_icono("cargando"), self._titulo("cargando"), self._menu())

    # --- menú -------------------------------------------------------------

    def _titulo(self, estado: str) -> str:
        return f"{self.nombre} v{__version__} — {TEXTOS.get(estado, estado)}"

    def _menu(self) -> pystray.Menu:
        Item = pystray.MenuItem
        return pystray.Menu(
            Item(lambda _: self._titulo(self.bucle.estado), None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Escribir una orden…", self._escribir, default=True),
            Item("Silenciar micrófono", self._alternar_silencio, checked=lambda _: self.bucle.silenciado),
            Item("Micrófono", pystray.Menu(self._opciones_micro)),
            Item("Iniciar con Windows", self._alternar_inicio, checked=lambda _: windows.inicio_automatico()),
            Item("Abrir registro", lambda: os.startfile(windows.REGISTRO)),
            pystray.Menu.SEPARATOR,
            Item("Salir", self._salir),
        )

    def _mostrar_estado(self, estado: str) -> None:
        self.icono.icon = dibujar_icono(estado)
        self.icono.title = self._titulo(estado)
        self.icono.update_menu()

    def _alternar_silencio(self) -> None:
        self.bucle.silenciar(not self.bucle.silenciado)
        self._mostrar_estado("silenciado" if self.bucle.silenciado else "escuchando")

    def _opciones_micro(self):
        """Submenú (se genera cada vez que se abre): predeterminado de Windows + cada micrófono."""
        Item = pystray.MenuItem
        actual = microfonos.actual()

        def elegir(nombre: str):
            def accion() -> None:
                microfonos.elegir(nombre)
                self.icono.notify(f"Micrófono: {microfonos.nombre_en_uso()}", self.nombre)
                self.icono.update_menu()
            return accion

        yield Item("Predeterminado de Windows", elegir(""), checked=lambda _: microfonos.actual() is None,
                   radio=True)
        for m in microfonos.listar():
            yield Item(m.nombre, elegir(m.nombre), checked=lambda _, m=m: microfonos.actual() == m, radio=True)
        if actual is None and microfonos.configurado():
            yield Item(f"«{microfonos.configurado()}» (no conectado)", None, enabled=False)

    def _alternar_inicio(self) -> None:
        try:
            windows.activar_inicio_automatico(not windows.inicio_automatico())
        except Exception as e:
            self.icono.notify(f"No pude cambiar el inicio automático: {e}", self.nombre)
        self.icono.update_menu()

    def _salir(self) -> None:
        self.bucle.parar()
        self.icono.stop()

    # --- escribir una orden ----------------------------------------------

    def _escribir(self) -> None:
        if self._dialogo_abierto.acquire(blocking=False):
            threading.Thread(target=self._dialogo, daemon=True).start()

    def _dialogo(self) -> None:
        import tkinter as tk
        from tkinter import messagebox, simpledialog

        try:
            raiz = tk.Tk()
            raiz.withdraw()
            raiz.attributes("-topmost", True)
            interfaz.usar_en_este_hilo(DialogoConfirmacion(raiz, self.nombre))
            texto = simpledialog.askstring(self.nombre, "¿Qué necesitas?", parent=raiz)
            if texto and texto.strip():
                print(f"  (escrito) {texto}")
                respuesta = procesar(texto)
                print(respuesta)
                messagebox.showinfo(self.nombre, respuesta, parent=raiz)
            raiz.destroy()
        except Exception:
            traceback.print_exc()
        finally:
            self._dialogo_abierto.release()

    # --- arranque ---------------------------------------------------------

    def ejecutar(self) -> None:
        self.icono.run(setup=self._en_marcha)  # bloquea hasta "Salir"

    def _en_marcha(self, icono: pystray.Icon) -> None:
        """Se ejecuta en otro hilo: carga la IA y la voz y se queda escuchando."""
        icono.visible = True
        try:
            from .ia import preparar_ia

            from .servicios import recordatorios

            recordatorios.gestor().suscribir(lambda texto: icono.notify(texto, f"⏰ {self.nombre}"))
            estado_ia = preparar_ia(self.nombre)
            self.bucle.preparar()
            icono.notify(f"Listo. Di «{self.nombre}» seguido de una orden.\n{estado_ia.splitlines()[0]}",
                         self.nombre)
            self.bucle.ejecutar()
        except Exception as e:
            traceback.print_exc()
            self._mostrar_estado("error")
            icono.notify(f"Error: {e}. Más detalles en «Abrir registro».", self.nombre)
            return
        icono.stop()  # se despidió por voz ("apágate")
