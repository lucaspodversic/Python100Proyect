"""GUI Tkinter: barras en un Canvas animadas con ``after()``.

Importar este módulo no abre ventanas (Tk se crea en :func:`main`), así que
es importable sin display. La lógica vive en :mod:`ordenvis.reproductor`.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .algoritmos import ALGORITMOS, COMPLEJIDAD
from .reproductor import Reproductor, arreglo_aleatorio

COLORES = {"": "#5b8def", "comparar": "#f2c94c", "intercambiar": "#eb5757", "escribir": "#bb6bd9", "ordenado": "#27ae60"}
COLOR_FINAL = "#27ae60"


class AppOrden(ttk.Frame):
    """Ventana del visualizador: selector de algoritmo y tipo de datos, tamaño,
    Nuevo/Play/Paso, velocidad y un Canvas con una barra por elemento. Toda la lógica
    está en Reproductor; esta clase solo dibuja y programa los cuadros con after().
    """
    def __init__(self, master: tk.Misc, n: int = 60, semilla: int | None = None) -> None:
        """Crea las variables Tk, arma los controles y genera el primer arreglo. ``semilla``
        fija los datos (los tests la usan para ser deterministas).
        """
        super().__init__(master, padding=6)
        self.semilla = semilla
        self.var_alg = tk.StringVar(value="Quicksort")
        self.var_modo = tk.StringVar(value="aleatorio")
        self.var_n = tk.IntVar(value=n)
        self.var_vel = tk.IntVar(value=5)          # pasos por cuadro
        self.var_info = tk.StringVar()
        self._job: str | None = None
        self._armar()
        self.nuevo()

    def _armar(self) -> None:
        """Barra de controles arriba, Canvas en el centro y línea de información abajo. Cambiar
        de algoritmo reinicia con el MISMO arreglo, para comparar algoritmos con los
        mismos datos.
        """
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        ttk.Combobox(barra, textvariable=self.var_alg, values=list(ALGORITMOS), state="readonly", width=12).pack(side="left")
        ttk.Combobox(barra, textvariable=self.var_modo, values=["aleatorio", "casi", "invertido", "pocos"],
                     state="readonly", width=10).pack(side="left", padx=4)
        ttk.Spinbox(barra, from_=5, to=300, textvariable=self.var_n, width=5).pack(side="left")
        ttk.Button(barra, text="Nuevo", command=self.nuevo).pack(side="left", padx=4)
        self.btn_play = ttk.Button(barra, text="▶ Play", command=self.alternar)
        self.btn_play.pack(side="left")
        ttk.Button(barra, text="Paso", command=lambda: self.paso(1)).pack(side="left", padx=4)
        ttk.Label(barra, text="Velocidad").pack(side="left")
        ttk.Scale(barra, from_=1, to=200, variable=self.var_vel, orient="horizontal", length=120).pack(side="left")
        self.canvas = tk.Canvas(self, width=720, height=360, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=6)
        self.canvas.bind("<Configure>", lambda _e: self.dibujar())
        ttk.Label(self, textvariable=self.var_info).pack(anchor="w")
        self.var_alg.trace_add("write", lambda *_: self.nuevo(mismo_arreglo=True))

    # ----- acciones -----
    def nuevo(self, mismo_arreglo: bool = False) -> None:
        """Pausa y crea un Reproductor nuevo: con un arreglo nuevo (tamaño acotado a 5-300) o
        con el mismo de antes si ``mismo_arreglo``.
        """
        self.pausar()
        datos = self.rep.inicial if mismo_arreglo and hasattr(self, "rep") else \
            arreglo_aleatorio(max(5, min(300, int(self.var_n.get()))), self.semilla, self.var_modo.get())
        self.rep = Reproductor(datos, self.var_alg.get())
        self.dibujar()

    def alternar(self) -> None:
        """Play/Pausa. Darle Play a un orden ya terminado lo reinicia desde el arreglo
        original.
        """
        if self._job:
            self.pausar()
        else:
            if self.rep.terminado:
                self.rep.reiniciar()
            self.btn_play.config(text="⏸ Pausa")
            self._tick()

    def pausar(self) -> None:
        """Cancela el after() pendiente (si lo hay) y repone el texto del botón. Se llama
        también desde ``nuevo`` antes de que exista el botón, por eso el hasattr.
        """
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if hasattr(self, "btn_play"):
            self.btn_play.config(text="▶ Play")

    def paso(self, n: int) -> None:
        """Avanza n pasos y redibuja."""
        self.rep.avanzar(n)
        self.dibujar()

    def _tick(self) -> None:
        """Un cuadro de la animación: avanza 'velocidad' pasos y se reprograma cada 16 ms (unos
        60 cuadros por segundo) hasta terminar.
        """
        self.paso(max(1, int(self.var_vel.get())))
        if self.rep.terminado:
            self._job = None
            self.btn_play.config(text="▶ Play")
        else:
            self._job = self.after(16, self._tick)   # ≈60 cuadros por segundo

    # ----- dibujo -----
    def dibujar(self) -> None:
        """Redibuja todas las barras, con la altura proporcional al valor. Colores: verde =
        ordenado (todo verde al terminar), amarillo/rojo/violeta = los índices del
        último paso según su tipo y azul = el resto. Abajo se muestran las
        estadísticas y la complejidad teórica.
        """
        c, r = self.canvas, self.rep
        c.delete("all")
        w, h = max(c.winfo_width(), 50), max(c.winfo_height(), 50)
        n, maximo = len(r.valores), max(r.valores)
        ancho = w / n
        for i, v in enumerate(r.valores):
            if r.terminado or i in r.ordenados:
                color = COLOR_FINAL
            elif i in r.activos:
                color = COLORES[r.tipo_activo]
            else:
                color = COLORES[""]
            alto = (h - 10) * v / maximo
            c.create_rectangle(i * ancho, h - alto, (i + 1) * ancho - (1 if ancho > 3 else 0), h, fill=color, width=0)
        s = r.stats
        self.var_info.set(f"{r.algoritmo} — {COMPLEJIDAD[r.algoritmo]} | n={n} | comparaciones {s.comparaciones} · "
                          f"intercambios {s.intercambios} · escrituras {s.escrituras}" + (" | ✔ terminado" if r.terminado else ""))


def main(argv: list[str] | None = None) -> int:
    """Abre la ventana principal."""
    raiz = tk.Tk()
    raiz.title("Visualizador de ordenamiento")
    AppOrden(raiz).pack(fill="both", expand=True)
    raiz.mainloop()
    return 0
