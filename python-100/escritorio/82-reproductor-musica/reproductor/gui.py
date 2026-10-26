"""Interfaz Tkinter del reproductor. La ventana se crea solo en :func:`main`."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .audio import MotorAudio
from .control import Estado, Reproductor
from .lista import ListaReproduccion, Repetir, escanear

INTERVALO_MS = 500  # cada cuánto se comprueba si terminó la pista


class AppReproductor(ttk.Frame):
    """Ventana del reproductor: título, lista de pistas, botones de transporte, modos y
    volumen. No sabe nada de audio: delega todo en ``Reproductor``.
    """
    def __init__(self, maestro: tk.Misc, motor: MotorAudio) -> None:
        """Construye la interfaz y arranca el 'tick' periódico que detecta el fin de cada
        pista.
        """
        super().__init__(maestro, padding=8)
        self.rep = Reproductor(motor)
        self.titulo = tk.StringVar(value="—")
        self._construir()
        self._programar_tick()

    def _construir(self) -> None:
        """Arma los widgets. Los botones de transporte pasan por ``_accion`` para refrescar la
        vista después de cada comando.
        """
        ttk.Label(self, textvariable=self.titulo, font=("TkDefaultFont", 12, "bold")).pack(fill="x")
        self.lista = tk.Listbox(self, height=12, width=50)
        self.lista.pack(fill="both", expand=True, pady=4)
        self.lista.bind("<Double-Button-1>", self._doble_clic)

        botones = ttk.Frame(self)
        botones.pack(fill="x")
        for texto, cmd in (("⏮", self.rep.anterior), ("▶/⏸", self.rep.reproducir_pausar),
                           ("⏹", self.rep.detener), ("⏭", self.rep.siguiente)):
            ttk.Button(botones, text=texto, width=5, command=lambda c=cmd: self._accion(c)).pack(side="left")
        self.btn_aleatorio = ttk.Button(botones, text="Aleatorio: no", command=self._aleatorio)
        self.btn_aleatorio.pack(side="left", padx=4)
        self.btn_repetir = ttk.Button(botones, text="Repetir: no", command=self._repetir)
        self.btn_repetir.pack(side="left")
        ttk.Button(botones, text="Abrir carpeta…", command=self._abrir).pack(side="right")

        self.volumen = ttk.Scale(self, from_=0, to=1, value=self.rep.volumen,
                                 command=lambda v: self.rep.fijar_volumen(float(v)))
        self.volumen.pack(fill="x", pady=(4, 0))

    # ------------------------------------------------------------ helpers
    def cargar(self, rutas: list[Path]) -> None:
        """Reemplaza la lista de reproducción (también usado por tests)."""
        self.rep.detener()
        self.rep.lista = ListaReproduccion(rutas)
        self.lista.delete(0, "end")
        for r in rutas:
            self.lista.insert("end", r.stem)
        self._refrescar()

    def _accion(self, cmd) -> None:
        """Ejecuta un comando del controlador y actualiza título y selección."""
        cmd()
        self._refrescar()

    def _refrescar(self) -> None:
        """Sincroniza título y selección con el estado del controlador."""
        actual = self.rep.lista.actual
        icono = {Estado.REPRODUCIENDO: "▶", Estado.PAUSADO: "⏸", Estado.DETENIDO: "⏹"}[self.rep.estado]
        self.titulo.set(f"{icono} {actual.stem}" if actual else "—")
        self.lista.selection_clear(0, "end")
        if actual is not None:
            i = self.rep.lista.pistas.index(actual)
            self.lista.selection_set(i)
            self.lista.see(i)

    def _doble_clic(self, _e: object) -> None:
        """Reproduce la pista sobre la que se hizo doble clic (si hay selección)."""
        sel = self.lista.curselection()
        if sel:
            self._accion(lambda: self.rep.elegir(sel[0]))

    def _aleatorio(self) -> None:
        """Alterna el modo aleatorio y actualiza el rótulo del botón."""
        self.rep.lista.alternar_aleatorio()
        self.btn_aleatorio.config(text=f"Aleatorio: {'sí' if self.rep.lista.aleatorio else 'no'}")

    def _repetir(self) -> None:
        """Rota el modo de repetición no → todas → una → no (orden del Enum)."""
        modos = list(Repetir)
        self.rep.lista.repetir = modos[(modos.index(self.rep.lista.repetir) + 1) % len(modos)]
        self.btn_repetir.config(text=f"Repetir: {self.rep.lista.repetir.value}")

    def _abrir(self) -> None:
        """Pide una carpeta y carga todos los audios que encuentre (recursivo)."""
        carpeta = filedialog.askdirectory()
        if carpeta:
            self.cargar(escanear(Path(carpeta)))

    def _programar_tick(self) -> None:
        """Cada INTERVALO_MS pregunta al controlador si la pista terminó (para avanzar), avisa
        una sola vez de archivos que no se pudieron abrir y se reprograma con
        ``after`` (nunca bloquea el bucle de Tk).
        """
        self.rep.tick()
        if self.rep.errores:
            messagebox.showwarning("Archivos omitidos", "\n".join(self.rep.errores))
            self.rep.errores.clear()
        self._refrescar()
        self.after(INTERVALO_MS, self._programar_tick)


def main() -> None:
    """Punto de entrada: crea la ventana con el motor pygame y, si se pasó una carpeta por
    argumento, la carga.
    """
    from .audio import MotorPygame

    raiz = tk.Tk()
    raiz.title("Reproductor de música")
    app = AppReproductor(raiz, MotorPygame())
    app.pack(fill="both", expand=True)
    if len(sys.argv) > 1:
        app.cargar(escanear(Path(sys.argv[1])))
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
