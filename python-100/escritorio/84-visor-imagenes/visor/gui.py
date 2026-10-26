"""Interfaz Tkinter del visor. La ventana se crea solo en :func:`main`."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from .nucleo import ErrorImagen, Galeria, Vista, abrir, guardar_transformada, info, zoom_ajustado

INTERVALO_PRESENTACION_MS = 3000


class AppVisor(ttk.Frame):
    """Ventana del visor: barra de botones, lienzo y barra de estado. El estado de navegación
    (Galeria) y de visualización (Vista) vive en ``nucleo``; esta clase solo dibuja y
    conecta eventos.
    """
    def __init__(self, maestro: tk.Tk) -> None:
        """Arranca sin imagen. ``_foto`` guarda la PhotoImage actual: si no se mantiene una
        referencia en Python, Tk la libera y el lienzo queda en blanco (error
        clásico de Tkinter).
        """
        super().__init__(maestro)
        self.raiz = maestro
        self.galeria = Galeria()
        self.vista = Vista()
        self.imagen: Image.Image | None = None
        self._foto: ImageTk.PhotoImage | None = None  # referencia viva: si no, Tk la borra
        self._presentacion: str | None = None
        self.estado = tk.StringVar(value="Abrí una carpeta o imagen (Ctrl+O)")
        self._construir()

    def _construir(self) -> None:
        """Crea botones, lienzo y estado, y asocia atajos de teclado (flechas, +/-, 0, F5...).
        Al redimensionar la ventana se redibuja para mantener la imagen centrada.
        """
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        acciones = [("Abrir", self.dialogo_abrir), ("◀", lambda: self.mover(-1)), ("▶", lambda: self.mover(1)),
                    ("−", self.alejar), ("+", self.acercar), ("Ajustar", self.ajustar), ("1:1", self.real),
                    ("⟲", lambda: self.rotar(90)), ("⟳", lambda: self.rotar(-90)), ("⇋", self.espejo),
                    ("Presentación", self.alternar_presentacion), ("Guardar copia", self.dialogo_guardar)]
        for texto, cmd in acciones:
            ttk.Button(barra, text=texto, command=cmd).pack(side="left")
        self.lienzo = tk.Canvas(self, background="#222", highlightthickness=0)
        self.lienzo.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.estado, anchor="w").pack(fill="x")
        teclas = {"<Left>": lambda e: self.mover(-1), "<Right>": lambda e: self.mover(1),
                  "<plus>": lambda e: self.acercar(), "<minus>": lambda e: self.alejar(),
                  "<Control-o>": lambda e: self.dialogo_abrir(), "r": lambda e: self.rotar(-90),
                  "<space>": lambda e: self.alternar_presentacion()}
        for tecla, cmd in teclas.items():
            self.raiz.bind(tecla, cmd)
        # Rueda del ratón: Windows/macOS usan <MouseWheel>, X11 usa Button-4/5.
        self.lienzo.bind("<MouseWheel>", lambda e: self.acercar() if e.delta > 0 else self.alejar())
        self.lienzo.bind("<Button-4>", lambda e: self.acercar())
        self.lienzo.bind("<Button-5>", lambda e: self.alejar())

    # ------------------------------------------------------------ carga
    def cargar(self, ruta: Path) -> None:
        """Abre la carpeta de ``ruta`` como galería (o la carpeta misma si es un directorio) y
        muestra la imagen elegida ajustada a la ventana.
        """
        self.galeria = Galeria.desde(ruta)
        self._mostrar_actual(ajustar=True)

    def _mostrar_actual(self, ajustar: bool = False) -> None:
        """Abre la imagen actual; las que fallan se quitan de la galería y se sigue."""
        while (ruta := self.galeria.actual) is not None:
            try:
                self.imagen = abrir(ruta)
                break
            except ErrorImagen as e:
                self.estado.set(f"Omitida: {e}")
                self.galeria.quitar_actual()
        else:
            self.imagen = None
            self.lienzo.delete("all")
            return
        self.vista.reiniciar()
        if ajustar:
            self.ajustar()
        else:
            self.redibujar()

    def redibujar(self) -> None:
        """Renderiza la imagen con la vista actual (rotación, espejo, zoom), la centra en el
        lienzo y actualiza la barra de estado: posición en la galería, nombre,
        tamaño, formato y zoom.
        """
        if self.imagen is None:
            return
        render = self.vista.renderizar(self.imagen)
        self._foto = ImageTk.PhotoImage(render)
        self.lienzo.delete("all")
        cx, cy = max(self.lienzo.winfo_width(), 1) // 2, max(self.lienzo.winfo_height(), 1) // 2
        self.lienzo.create_image(cx, cy, image=self._foto, anchor="center")
        d = info(self.imagen, self.galeria.actual)
        self.estado.set(f"{self.galeria.pos + 1}/{len(self.galeria.rutas)}  {self.galeria.actual.name}  "
                        f"{d['ancho']}×{d['alto']} {d['formato']}  zoom {self.vista.zoom:.0%}")

    # ------------------------------------------------------------ acciones
    def mover(self, delta: int) -> None:
        """Imagen siguiente (+1) o anterior (-1), con vuelta; vuelve a ajustar el zoom."""
        self.galeria.mover(delta)
        self._mostrar_actual(ajustar=True)

    def acercar(self) -> None:
        """Zoom ×1.25 (acotado a ZOOM_MAX)."""
        self.vista.acercar(); self.redibujar()

    def alejar(self) -> None:
        """Zoom ÷1.25 (acotado a ZOOM_MIN)."""
        self.vista.alejar(); self.redibujar()

    def real(self) -> None:
        """Tamaño real (1 píxel de imagen = 1 píxel de pantalla)."""
        self.vista.zoom = 1.0; self.redibujar()

    def ajustar(self) -> None:
        """Zoom para que la imagen (ya rotada: una foto vertical ocupa distinto) entre en el
        lienzo. ``update_idletasks`` asegura que el lienzo ya tenga su tamaño real.
        """
        if self.imagen is None:
            return
        self.update_idletasks()
        w, h = self.vista.transformar(self.imagen).size
        self.vista.zoom = zoom_ajustado(w, h, self.lienzo.winfo_width(), self.lienzo.winfo_height())
        self.redibujar()

    def rotar(self, grados: int) -> None:
        """Rota en múltiplos de 90° y reajusta, porque al rotar cambian ancho y alto."""
        self.vista.rotar(grados); self.ajustar()

    def espejo(self) -> None:
        """Alterna el espejo horizontal."""
        self.vista.espejo_h = not self.vista.espejo_h; self.redibujar()

    def alternar_presentacion(self) -> None:
        """Inicia o detiene la presentación automática. Se guarda el id de ``after`` para poder
        cancelarla.
        """
        if self._presentacion:
            self.after_cancel(self._presentacion)
            self._presentacion = None
        else:
            self._avanzar_presentacion()

    def _avanzar_presentacion(self) -> None:
        """Pasa a la siguiente imagen y se reprograma (sin bloquear el bucle de Tk)."""
        self.mover(1)
        self._presentacion = self.after(INTERVALO_PRESENTACION_MS, self._avanzar_presentacion)

    def dialogo_abrir(self) -> None:
        """Diálogo para elegir una imagen; se carga su carpeta como galería."""
        ruta = filedialog.askopenfilename(filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff")])
        if ruta:
            self.cargar(Path(ruta))

    def dialogo_guardar(self) -> None:
        """Guarda una copia con las transformaciones aplicadas (rotación/espejo), nunca
        sobreescribe el original.
        """
        if self.imagen is None:
            return
        destino = filedialog.asksaveasfilename(defaultextension=".png")
        if destino:
            guardar_transformada(self.imagen, self.vista, Path(destino))


def main() -> None:
    """Punto de entrada. Si se pasa una ruta, se carga 100 ms después de mostrar la ventana
    para que el lienzo ya tenga tamaño y el ajuste sea correcto.
    """
    raiz = tk.Tk()
    raiz.title("Visor de imágenes")
    raiz.geometry("900x650")
    app = AppVisor(raiz)
    app.pack(fill="both", expand=True)
    if len(sys.argv) > 1:
        raiz.after(100, lambda: app.cargar(Path(sys.argv[1])))
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
