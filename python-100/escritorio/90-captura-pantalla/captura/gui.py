"""Interfaz Tkinter de captura. La ventana se crea solo en :func:`main`.

Flujo:

1. Se elige el modo: pantalla completa o región.
2. Se espera el retardo opcional.
3. **Se oculta la ventana propia** para que no salga en la foto.
4. Se captura y se guarda.
5. Se muestra la miniatura.

Para elegir una región se abre una capa semitransparente a pantalla completa
sobre la que se arrastra un rectángulo. Esc cancela.
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from .archivos import FORMATOS, PLANTILLA_DEFECTO, Sesion
from .capturador import Capturador, CapturadorFalso, ErrorCaptura, Region, elegir_capturador

CARPETA_DEFECTO = Path.home() / "Capturas"


class SelectorRegion(tk.Toplevel):
    """Capa a pantalla completa para arrastrar un rectángulo. Llama a ``al_elegir(Region|None)``."""

    def __init__(self, maestro: tk.Misc, al_elegir) -> None:
        """Capa a pantalla completa semitransparente para arrastrar un rectángulo. Guarda
        coordenadas de pantalla (para capturar) y locales (para dibujar). Escape
        cancela.
        """
        super().__init__(maestro)
        self.al_elegir = al_elegir
        self.attributes("-fullscreen", True)
        try:
            self.attributes("-alpha", 0.3)  # no todos los gestores de ventanas lo soportan
        except tk.TclError:
            pass
        self.lienzo = tk.Canvas(self, cursor="crosshair", bg="grey20", highlightthickness=0)
        self.lienzo.pack(fill="both", expand=True)
        self._inicio: tuple[int, int] | None = None
        self._rect: int | None = None
        self.lienzo.bind("<ButtonPress-1>", lambda e: self.empezar(e.x_root, e.y_root, e.x, e.y))
        self.lienzo.bind("<B1-Motion>", lambda e: self.mover(e.x, e.y))
        self.lienzo.bind("<ButtonRelease-1>", lambda e: self.terminar(e.x_root, e.y_root))
        self.bind("<Escape>", lambda _e: self.cancelar())
        self.focus_force()

    def empezar(self, xr: int, yr: int, x: int = 0, y: int = 0) -> None:
        """Inicio del arrastre: guarda ambos sistemas de coordenadas y crea el rectángulo."""
        self._inicio = (xr, yr)
        self._local = (x, y)
        self._rect = self.lienzo.create_rectangle(x, y, x, y, outline="red", width=2)

    def mover(self, x: int, y: int) -> None:
        """Redimensiona el rectángulo mientras se arrastra."""
        if self._rect is not None:
            self.lienzo.coords(self._rect, *self._local, x, y)

    def terminar(self, xr: int, yr: int) -> None:
        """Normaliza la región (se puede arrastrar en cualquier dirección), cierra la capa y
        entrega la región, o None si es demasiado chica.
        """
        if not self._inicio:
            return
        region = Region.desde_puntos(*self._inicio, xr, yr)
        self.destroy()
        self.al_elegir(region if region.valida() else None)

    def cancelar(self) -> None:
        """Cierra la capa sin región."""
        self.destroy()
        self.al_elegir(None)


class AppCaptura(ttk.Frame):
    """Ventana principal: carpeta, plantilla de nombre, nombre puntual, formato, retardo,
    botones de pantalla completa o región, y una miniatura de la última captura.
    """
    def __init__(self, maestro: tk.Tk, capturador: Capturador, carpeta: Path = CARPETA_DEFECTO) -> None:
        """El capturador se inyecta (Pillow, mss o falso). Se guarda la miniatura en un
        atributo porque Tk descarta las imágenes sin referencia viva.
        """
        super().__init__(maestro, padding=10)
        self.raiz = maestro
        self.sesion = Sesion(capturador, carpeta)
        self.var_carpeta = tk.StringVar(value=str(carpeta))
        self.var_plantilla = tk.StringVar(value=PLANTILLA_DEFECTO)
        self.var_nombre = tk.StringVar()
        self.var_formato = tk.StringVar(value="png")
        self.var_retardo = tk.IntVar(value=0)
        self.estado = tk.StringVar(value=f"Backend: {capturador.nombre}")
        self._miniatura: ImageTk.PhotoImage | None = None  # referencia viva (si no, Tk la borra)
        self._construir()

    def _construir(self) -> None:
        """Arma el formulario de opciones, los botones y la vista previa."""
        f = ttk.Frame(self)
        f.pack(fill="x")
        filas = [("Carpeta", self.var_carpeta), ("Plantilla", self.var_plantilla), ("Nombre (opcional)", self.var_nombre)]
        for i, (txt, var) in enumerate(filas):
            ttk.Label(f, text=txt).grid(row=i, column=0, sticky="w")
            ttk.Entry(f, textvariable=var, width=40).grid(row=i, column=1, sticky="ew")
        ttk.Button(f, text="…", width=3, command=self._elegir_carpeta).grid(row=0, column=2)
        ttk.Label(f, text="Formato").grid(row=3, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.var_formato, values=sorted(FORMATOS), state="readonly",
                     width=6).grid(row=3, column=1, sticky="w")
        ttk.Label(f, text="Retardo (s)").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(f, from_=0, to=30, textvariable=self.var_retardo, width=5).grid(row=4, column=1, sticky="w")
        f.columnconfigure(1, weight=1)

        b = ttk.Frame(self)
        b.pack(fill="x", pady=8)
        ttk.Button(b, text="Pantalla completa", command=lambda: self.programar(None)).pack(side="left")
        ttk.Button(b, text="Región…", command=self.elegir_region).pack(side="left", padx=4)
        self.vista = ttk.Label(self)
        self.vista.pack()
        ttk.Label(self, textvariable=self.estado).pack(anchor="w")

    def _elegir_carpeta(self) -> None:
        """Diálogo para elegir la carpeta de destino."""
        d = filedialog.askdirectory(initialdir=self.var_carpeta.get())
        if d:
            self.var_carpeta.set(d)

    def elegir_region(self) -> None:
        """Oculta la ventana y abre el selector tras 150 ms, para que la propia app no salga en
        la captura.
        """
        self.raiz.withdraw()
        # Pequeña pausa para que el gestor de ventanas oculte la ventana antes de la capa.
        self.after(150, lambda: SelectorRegion(self.raiz, self._region_elegida))

    def _region_elegida(self, region: Region | None) -> None:
        """Callback del selector: si se canceló, vuelve a mostrar la ventana; si no, programa
        la captura.
        """
        if region is None:
            self.raiz.deiconify()
            self.estado.set("Selección cancelada")
            return
        self.programar(region, ya_oculta=True)

    def programar(self, region: Region | None, ya_oculta: bool = False) -> None:
        """Oculta la ventana, espera el retardo y captura."""
        if not ya_oculta:
            self.raiz.withdraw()
        try:
            retardo = max(0, int(self.var_retardo.get()))
        except (tk.TclError, ValueError):
            retardo = 0
        self.after(retardo * 1000 + 200, lambda: self.capturar_ahora(region))

    def capturar_ahora(self, region: Region | None) -> Path | None:
        """Toma los valores del formulario, captura y guarda. Los errores se muestran en un
        diálogo y la ventana siempre se vuelve a mostrar (finally). Devuelve la ruta
        o None.
        """
        s = self.sesion
        s.carpeta = Path(self.var_carpeta.get()).expanduser()
        s.plantilla = self.var_plantilla.get() or PLANTILLA_DEFECTO
        s.formato = self.var_formato.get()
        ruta = None
        try:
            ruta = s.capturar_y_guardar(region, self.var_nombre.get())
        except (ErrorCaptura, ValueError, OSError) as e:
            messagebox.showerror("Captura", str(e))
        finally:
            self.raiz.deiconify()
        if ruta:
            self.var_nombre.set("")  # el nombre personalizado es de un solo uso
            self._mostrar(ruta)
            self.estado.set(f"Guardada: {ruta}")
        return ruta

    def _mostrar(self, ruta: Path) -> None:
        """Muestra una miniatura de 360×220 como máximo (respetando proporción)."""
        from PIL import Image
        with Image.open(ruta) as img:
            img.thumbnail((360, 220))
            self._miniatura = ImageTk.PhotoImage(img)
        self.vista.configure(image=self._miniatura)


def main() -> None:
    """Punto de entrada. --demo usa el capturador falso (sirve sin pantalla real)."""
    raiz = tk.Tk()
    raiz.title("Captura de pantalla")
    capturador = CapturadorFalso() if "--demo" in sys.argv else elegir_capturador()
    AppCaptura(raiz, capturador).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
