"""Interfaz Tkinter de la calculadora.

Importar este módulo **no** crea ventanas: la ventana se crea solo en
:func:`main`, de modo que los tests pueden importarlo sin pantalla.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .motor import Calculadora, ErrorCalculo, formatear

#: Disposición del teclado: (texto del botón, texto a insertar o acción).
TECLAS: list[list[tuple[str, str]]] = [
    [("sin", "sin("), ("cos", "cos("), ("tan", "tan("), ("√", "sqrt("), ("C", "<borrar>")],
    [("ln", "ln("), ("log", "log("), ("x^y", "^"), ("n!", "fact("), ("⌫", "<retroceso>")],
    [("7", "7"), ("8", "8"), ("9", "9"), ("÷", "÷"), ("(", "(")],
    [("4", "4"), ("5", "5"), ("6", "6"), ("×", "×"), (")", ")")],
    [("1", "1"), ("2", "2"), ("3", "3"), ("-", "-"), ("π", "π")],
    [("0", "0"), (".", "."), ("ans", "ans"), ("+", "+"), ("=", "<igual>")],
]


class AppCalculadora(ttk.Frame):
    """Marco principal: pantalla, teclado, memoria e historial."""

    def __init__(self, maestro: tk.Misc, calc: Calculadora | None = None) -> None:
        """Crea las variables Tk (pantalla y modo) y arma los widgets. Se puede inyectar una
        Calculadora para testear con estado preparado.
        """
        super().__init__(maestro, padding=8)
        self.calc = calc or Calculadora()
        self.entrada = tk.StringVar()
        self.estado = tk.StringVar(value="RAD")
        self._construir()

    def _construir(self) -> None:
        """Arma la pantalla (Entry), la barra de modo/memoria, la grilla de teclas definida en
        TECLAS y el historial. Cada botón solo llama a pulsar/memoria: toda la
        lógica vive en el motor.
        """
        pantalla = ttk.Entry(self, textvariable=self.entrada, font=("TkFixedFont", 16), justify="right")
        pantalla.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 6))
        pantalla.bind("<Return>", lambda _e: self.pulsar("<igual>"))
        pantalla.focus_set()
        self.pantalla = pantalla

        barra = ttk.Frame(self)
        barra.grid(row=1, column=0, columnspan=5, sticky="ew")
        ttk.Button(barra, textvariable=self.estado, width=5, command=self.alternar_modo).pack(side="left")
        # Botones de memoria: todos delegan en self.memoria(texto).
        for texto in ("MC", "M+", "M-", "MR"):
            ttk.Button(barra, text=texto, width=4, command=lambda t=texto: self.memoria(t)).pack(side="left")

        for f, fila in enumerate(TECLAS, start=2):
            for col, (texto, valor) in enumerate(fila):
                ttk.Button(self, text=texto, width=5, command=lambda v=valor: self.pulsar(v)).grid(
                    row=f, column=col, padx=1, pady=1, sticky="nsew")

        ttk.Label(self, text="Historial").grid(row=8, column=0, columnspan=5, sticky="w", pady=(6, 0))
        self.lista = tk.Listbox(self, height=5)
        self.lista.grid(row=9, column=0, columnspan=5, sticky="ew")
        # Doble clic en el historial recupera el resultado.
        self.lista.bind("<Double-Button-1>", self._recuperar)

    # ------------------------------------------------------------ acciones
    def pulsar(self, valor: str) -> None:
        """Procesa la pulsación de una tecla (también usado por los tests)."""
        if valor == "<borrar>":
            self.entrada.set("")
        elif valor == "<retroceso>":
            self.entrada.set(self.entrada.get()[:-1])
        elif valor == "<igual>":
            expresion = self.entrada.get()
            try:
                resultado = formatear(self.calc.evaluar(expresion))
            except ErrorCalculo as e:
                self.entrada.set(f"Error: {e}")
                return
            self.lista.insert(0, f"{expresion} = {resultado}")
            self.entrada.set(resultado)
        else:
            actual = self.entrada.get()
            if actual.startswith("Error"):
                actual = ""
            self.entrada.set(actual + valor)

    def alternar_modo(self) -> None:
        """Cambia entre radianes y grados; el texto del botón refleja el modo activo (RAD/DEG)."""
        self.calc.grados = not self.calc.grados
        self.estado.set("DEG" if self.calc.grados else "RAD")

    def memoria(self, accion: str) -> None:
        """Botones de memoria. MC borra, MR inserta el valor guardado en la pantalla, M+/M-
        evalúan lo escrito (vacío cuenta como 0) y lo suman/restan. Si la expresión
        es inválida se ignora en silencio: un botón de memoria no debería mostrar
        errores.
        """
        if accion == "MC":
            self.calc.memoria_borrar()
        elif accion == "MR":
            self.pulsar(formatear(self.calc.memoria))
        else:
            try:
                valor = self.calc.evaluar(self.entrada.get() or "0")
            except ErrorCalculo:
                return
            (self.calc.memoria_sumar if accion == "M+" else self.calc.memoria_restar)(valor)

    def _recuperar(self, _evento: object) -> None:
        """Doble clic en el historial: copia el resultado (lo que está después de ' = ') a la
        pantalla para seguir operando.
        """
        sel = self.lista.curselection()
        if sel:
            self.entrada.set(self.lista.get(sel[0]).rsplit(" = ", 1)[1])


def main() -> None:
    """Crea la ventana y arranca el bucle de eventos."""
    raiz = tk.Tk()
    raiz.title("Calculadora científica")
    AppCalculadora(raiz).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
