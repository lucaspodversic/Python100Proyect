"""Interfaz Tkinter del cliente de X. La ventana se crea solo en :func:`main`.

Las peticiones de red corren en un hilo; el resultado vuelve al hilo de Tk
mediante una cola revisada con ``after`` (Tkinter no es thread-safe).
"""
from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .api import ClienteXAPI, ErrorX, Post, ServicioFalso, ServicioX
from .control import Controlador
from .texto import LIMITE, restantes


class EjecutorHilo:
    """Ejecuta el trabajo en un hilo y entrega el callback en el hilo de Tk."""

    def __init__(self, widget: tk.Misc) -> None:
        """Cola de resultados que se vacía periódicamente desde el hilo de Tk."""
        self.widget = widget
        self.cola: queue.Queue = queue.Queue()
        self._revisar()

    def __call__(self, trabajo, al_terminar, al_fallar) -> None:
        """Corre ``trabajo`` en un hilo daemon. Tk no es thread-safe, así que el hilo NO toca
        widgets: deja el callback en la cola.
        """
        def correr() -> None:
            """Cuerpo del hilo: resultado o excepción a la cola."""
            try:
                r = trabajo()
            except Exception as e:
                self.cola.put((al_fallar, e))
            else:
                self.cola.put((al_terminar, r))
        threading.Thread(target=correr, daemon=True).start()

    def _revisar(self) -> None:
        """Cada 100 ms ejecuta en el hilo de Tk los callbacks pendientes."""
        while not self.cola.empty():
            fn, arg = self.cola.get_nowait()
            fn(arg)
        self.widget.after(100, self._revisar)


class AppX(ttk.Frame):
    """Ventana: redactor con contador de caracteres, búsqueda, lista de posts y paginación.
    Delega todo en ``Controlador``.
    """
    def __init__(self, maestro: tk.Tk, servicio: ServicioX, ejecutor=None) -> None:
        """``ejecutor`` se puede inyectar (los tests usan el sincrónico)."""
        super().__init__(maestro, padding=8)
        self.ctrl = Controlador(servicio, ejecutor or EjecutorHilo(self), self.redibujar)
        self.estado = tk.StringVar()
        self.contador = tk.StringVar(value=str(LIMITE))
        self.var_buscar = tk.StringVar()
        self.var_hilo = tk.BooleanVar()
        self._construir()

    def _construir(self) -> None:
        """Arma redactor, contador, opción de hilo, búsqueda, lista y botón 'Cargar más'."""
        self.redactor = tk.Text(self, height=4, wrap="word")
        self.redactor.pack(fill="x")
        self.redactor.bind("<KeyRelease>", lambda _e: self._contar())
        fila = ttk.Frame(self)
        fila.pack(fill="x")
        self.lbl_contador = ttk.Label(fila, textvariable=self.contador)
        self.lbl_contador.pack(side="left")
        ttk.Checkbutton(fila, text="Dividir en hilo", variable=self.var_hilo).pack(side="left", padx=6)
        ttk.Button(fila, text="Publicar", command=self.publicar).pack(side="right")

        busq = ttk.Frame(self)
        busq.pack(fill="x", pady=6)
        e = ttk.Entry(busq, textvariable=self.var_buscar)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _e: self.ctrl.buscar(self.var_buscar.get()))
        ttk.Button(busq, text="Buscar", command=lambda: self.ctrl.buscar(self.var_buscar.get())).pack(side="left")
        ttk.Button(busq, text="Mis posts", command=self.ctrl.cargar_propias).pack(side="left")

        self.lista = tk.Listbox(self, height=15)
        self.lista.pack(fill="both", expand=True)
        abajo = ttk.Frame(self)
        abajo.pack(fill="x")
        self.btn_mas = ttk.Button(abajo, text="Cargar más", command=self.ctrl.mas)
        self.btn_mas.pack(side="left")
        ttk.Label(abajo, textvariable=self.estado).pack(side="left", padx=6)

    def _texto(self) -> str:
        """Texto del redactor sin el salto de línea final que agrega Tk."""
        return self.redactor.get("1.0", "end-1c")

    def _contar(self) -> None:
        """Actualiza los caracteres restantes; en rojo si se pasó."""
        r = restantes(self._texto())
        self.contador.set(str(r))
        self.lbl_contador.configure(foreground="red" if r < 0 else "")

    def publicar(self) -> None:
        """Si es demasiado largo y no se pidió hilo, avisa. Si se publica, limpia el redactor."""
        texto = self._texto()
        if not self.var_hilo.get() and restantes(texto) < 0:
            messagebox.showwarning("Demasiado largo", "Activá «Dividir en hilo» o acortá el texto.")
            return
        if self.ctrl.publicar(texto, self.var_hilo.get()):
            self.redactor.delete("1.0", "end")
            self._contar()

    @staticmethod
    def _fila(p: Post) -> str:
        """Texto de una fila: '@autor: texto ♥N', en una sola línea."""
        autor = f"@{p.autor}: " if p.autor else ""
        return f"{autor}{p.texto.replace(chr(10), ' ')}  ♥{p.me_gusta}"

    def redibujar(self) -> None:
        """Refleja el estado del controlador; 'Cargar más' solo se habilita si hay cursor y
        nada en curso.
        """
        self.estado.set(self.ctrl.mensaje)
        self.lista.delete(0, "end")
        for p in self.ctrl.posts:
            self.lista.insert("end", self._fila(p))
        self.btn_mas.state(["!disabled"] if self.ctrl.cursor and not self.ctrl.ocupado else ["disabled"])


def main() -> None:
    """Punto de entrada. Con --demo usa el servicio falso (sin red ni token); sin token avisa
    cómo configurarlo.
    """
    raiz = tk.Tk()
    raiz.title("Cliente de X")
    if "--demo" in sys.argv:
        servicio: ServicioX = ServicioFalso(posts=[Post("1", "Hola desde el modo demo", "demo", me_gusta=3)])
    else:
        try:
            servicio = ClienteXAPI()
        except ErrorX as e:
            raiz.withdraw()
            messagebox.showerror("Cliente de X", f"{e}\n\nPodés probar sin red con: python -m clientex --demo")
            return
    app = AppX(raiz, servicio)
    app.pack(fill="both", expand=True)
    app.ctrl.conectar()
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
