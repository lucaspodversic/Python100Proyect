"""Interfaz Tkinter del conversor. La ventana se crea solo en :func:`main`.

La conversión es "en vivo": cualquier cambio de valor o unidad recalcula.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .unidades import MAGNITUDES, ErrorConversion, convertir, formatear, parsear, tabla_conversiones


class AppConversor(ttk.Frame):
    """Ventana del conversor: magnitud, valor, unidad origen ⇄ destino, resultado y una tabla
    con el valor en todas las unidades. Convierte en vivo mientras se escribe.
    """
    def __init__(self, maestro: tk.Misc) -> None:
        """Crea las variables y engancha ``trace_add`` sobre unidad origen, destino y valor:
        cualquier cambio recalcula, sin botón 'Convertir'.
        """
        super().__init__(maestro, padding=10)
        self.magnitud = tk.StringVar(value="longitud")
        self.de = tk.StringVar()
        self.a = tk.StringVar()
        self.valor = tk.StringVar(value="1")
        self.resultado = tk.StringVar()
        self._construir()
        self._cambiar_magnitud()
        for var in (self.de, self.a, self.valor):
            var.trace_add("write", lambda *_: self.recalcular())

    def _construir(self) -> None:
        """Arma la grilla de controles y la tabla (Treeview) de equivalencias."""
        ttk.Label(self, text="Magnitud").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(self, textvariable=self.magnitud, values=list(MAGNITUDES), state="readonly")
        cb.grid(row=0, column=1, columnspan=3, sticky="ew")
        cb.bind("<<ComboboxSelected>>", lambda _e: self._cambiar_magnitud())

        ttk.Entry(self, textvariable=self.valor, width=16, justify="right").grid(row=1, column=0, pady=6)
        self.cb_de = ttk.Combobox(self, textvariable=self.de, state="readonly", width=8)
        self.cb_de.grid(row=1, column=1)
        ttk.Button(self, text="⇄", width=3, command=self.intercambiar).grid(row=1, column=2, padx=4)
        self.cb_a = ttk.Combobox(self, textvariable=self.a, state="readonly", width=8)
        self.cb_a.grid(row=1, column=3)
        ttk.Label(self, textvariable=self.resultado, font=("TkDefaultFont", 14, "bold")).grid(
            row=2, column=0, columnspan=4, sticky="w")

        self.tabla = ttk.Treeview(self, columns=("unidad", "valor"), show="headings", height=9)
        self.tabla.heading("unidad", text="Unidad")
        self.tabla.heading("valor", text="Valor")
        self.tabla.grid(row=3, column=0, columnspan=4, sticky="nsew", pady=(8, 0))

    def _cambiar_magnitud(self) -> None:
        """Al elegir otra magnitud, recarga las unidades disponibles y preselecciona las dos
        primeras (origen ≠ destino si hay más de una).
        """
        simbolos = list(MAGNITUDES[self.magnitud.get()])
        self.cb_de["values"] = self.cb_a["values"] = simbolos
        self.de.set(simbolos[0])
        self.a.set(simbolos[1] if len(simbolos) > 1 else simbolos[0])
        self.recalcular()

    def intercambiar(self) -> None:
        """Botón ⇄: invierte origen y destino; las trazas recalculan solas."""
        de, a = self.de.get(), self.a.get()
        self.de.set(a)
        self.a.set(de)

    def recalcular(self) -> None:
        """Recalcula resultado y tabla; los errores se muestran, no se lanzan."""
        self.tabla.delete(*self.tabla.get_children())
        if not (self.de.get() and self.a.get()):
            return
        try:
            v = parsear(self.valor.get())
            r = convertir(v, self.magnitud.get(), self.de.get(), self.a.get())
        except ErrorConversion as e:
            self.resultado.set(f"⚠ {e}")
            return
        self.resultado.set(f"= {formatear(r)} {self.a.get()}")
        for fila in tabla_conversiones(v, self.magnitud.get(), self.de.get()):
            self.tabla.insert("", "end", values=fila)


def main() -> None:
    """Punto de entrada de la aplicación."""
    raiz = tk.Tk()
    raiz.title("Conversor de unidades")
    AppConversor(raiz).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
