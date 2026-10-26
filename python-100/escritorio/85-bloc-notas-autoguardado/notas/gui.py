"""Interfaz Tkinter del bloc de notas. La ventana se crea solo en :func:`main`."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .almacen import Almacen, Nota
from .autoguardado import Autoguardado

CARPETA = Path.home() / ".local" / "share" / "bloc-notas-py100"
SONDEO_MS = 250


class AppNotas(ttk.Frame):
    """Ventana: buscador + lista de notas a la izquierda, texto a la derecha, barra de estado
    abajo. Guarda sola usando ``Autoguardado`` y un sondeo con ``after``.
    """
    def __init__(self, maestro: tk.Tk, almacen: Almacen, auto: Autoguardado | None = None) -> None:
        """Recibe almacén y política de autoguardado por inyección (los tests usan una carpeta
        temporal y un reloj falso). Arranca el sondeo periódico.
        """
        super().__init__(maestro, padding=6)
        self.raiz = maestro
        self.almacen = almacen
        self.auto = auto or Autoguardado()
        self.actual: Nota | None = None
        self._ids: list[str] = []           # id de cada fila de la lista
        self._cargando = False              # evita marcar cambio al poner texto por código
        self.filtro = tk.StringVar()
        self.estado = tk.StringVar(value="Listo")
        self._construir()
        self.refrescar_lista()
        self._sondear()

    def _construir(self) -> None:
        """Crea buscador (filtra al escribir), lista, botones, área de texto y barra de estado;
        al cerrar la ventana se guarda antes de salir.
        """
        izq = ttk.Frame(self)
        izq.pack(side="left", fill="y")
        buscador = ttk.Entry(izq, textvariable=self.filtro)
        buscador.pack(fill="x")
        self.filtro.trace_add("write", lambda *_: self.refrescar_lista())
        self.lista = tk.Listbox(izq, width=30, exportselection=False)
        self.lista.pack(fill="y", expand=True)
        self.lista.bind("<<ListboxSelect>>", self._seleccionar)
        botones = ttk.Frame(izq)
        botones.pack(fill="x")
        ttk.Button(botones, text="Nueva", command=self.nueva).pack(side="left")
        ttk.Button(botones, text="Fijar", command=self.fijar).pack(side="left")
        ttk.Button(botones, text="Borrar", command=self.borrar).pack(side="left")

        der = ttk.Frame(self)
        der.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self.texto = tk.Text(der, wrap="word", undo=True, state="disabled")
        self.texto.pack(fill="both", expand=True)
        self.texto.bind("<<Modified>>", self._al_modificar)
        ttk.Label(der, textvariable=self.estado, anchor="w").pack(fill="x")
        self.raiz.protocol("WM_DELETE_WINDOW", self.cerrar)
        self.raiz.bind("<Control-n>", lambda _e: self.nueva())

    # ------------------------------------------------------------ lista
    def refrescar_lista(self) -> None:
        """Recarga la lista aplicando el filtro (fijadas primero y luego por fecha), conserva
        la selección de la nota abierta y avisa si hay archivos ilegibles.
        """
        self.lista.delete(0, "end")
        notas = self.almacen.listar(self.filtro.get())
        self._ids = [n.id for n in notas]
        for n in notas:
            self.lista.insert("end", ("📌 " if n.fijada else "") + n.titulo)
        if self.actual and self.actual.id in self._ids:
            self.lista.selection_set(self._ids.index(self.actual.id))
        if self.almacen.corruptas:
            self.estado.set(f"Atención: {len(self.almacen.corruptas)} nota(s) ilegible(s)")

    def _seleccionar(self, _e: object = None) -> None:
        """Abre la nota elegida, salvo que ya sea la actual (evita recargar y perder el
        cursor).
        """
        sel = self.lista.curselection()
        if sel and (self.actual is None or self._ids[sel[0]] != self.actual.id):
            self.abrir(self._ids[sel[0]])

    def abrir(self, id_: str) -> None:
        """Guarda la nota actual si tenía cambios y muestra otra. ``_cargando`` evita que
        insertar el texto por código cuente como una edición del usuario; se
        reinicia el deshacer para no mezclar notas.
        """
        self.guardar_ahora()  # nunca perder lo escrito al cambiar de nota
        self.actual = self.almacen.leer(id_)
        self._cargando = True
        self.texto.configure(state="normal")
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", self.actual.texto)
        self.texto.edit_reset()
        self.texto.edit_modified(False)
        self._cargando = False

    # ------------------------------------------------------------ guardado
    def _al_modificar(self, _e: object = None) -> None:
        """Cada edición real del usuario avisa al autoguardado. Se rearma la bandera 'modified'
        de Tk para recibir el próximo evento.
        """
        if self.texto.edit_modified():
            self.texto.edit_modified(False)
            if not self._cargando and self.actual is not None:
                self.auto.marcar_cambio()
                self.estado.set("Editando…")

    def guardar_ahora(self) -> None:
        """Guarda si hay cambios pendientes. Si el disco falla, se muestra el error y la racha
        sigue pendiente para reintentar en el próximo sondeo (no se pierde nada).
        """
        if self.actual is None or not self.auto.pendiente:
            return
        self.actual.texto = self.texto.get("1.0", "end-1c")
        try:
            self.almacen.guardar(self.actual)
        except OSError as e:
            # No se reinicia la racha: se reintentará en el siguiente sondeo.
            self.estado.set(f"¡Error al guardar! {e}")
            return
        self.auto.guardado()
        self.estado.set(f"Guardado {self.actual.modificada[11:19]} UTC")
        self.refrescar_lista()

    def _sondear(self) -> None:
        """Cada SONDEO_MS consulta la política de autoguardado y se reprograma."""
        if self.auto.debe_guardar():
            self.guardar_ahora()
        self.after(SONDEO_MS, self._sondear)

    # ------------------------------------------------------------ acciones
    def nueva(self) -> None:
        """Crea una nota vacía, limpia el filtro (si no, la nota nueva podría quedar oculta) y
        la abre con el foco en el texto.
        """
        nota = self.almacen.crear()
        self.filtro.set("")
        self.abrir(nota.id)
        self.refrescar_lista()
        self.texto.focus_set()

    def fijar(self) -> None:
        """Alterna 'fijada' (las fijadas van arriba) sin tocar la fecha de modificación."""
        if self.actual:
            self.guardar_ahora()
            self.actual.fijada = not self.actual.fijada
            self.almacen.guardar(self.actual, tocar=False)
            self.refrescar_lista()

    def borrar(self) -> None:
        """Previa confirmación, manda la nota a la papelera y deja el editor vacío y
        deshabilitado.
        """
        if self.actual and messagebox.askyesno("Borrar", f"¿Mover «{self.actual.titulo}» a la papelera?"):
            self.almacen.borrar(self.actual.id)
            self.auto.guardado()
            self.actual = None
            self.texto.delete("1.0", "end")
            self.texto.configure(state="disabled")
            self.refrescar_lista()

    def cerrar(self) -> None:
        """Al cerrar la ventana: guardar lo pendiente y salir."""
        self.guardar_ahora()
        self.raiz.destroy()


def main() -> None:
    """Punto de entrada con la carpeta de notas por defecto del usuario."""
    raiz = tk.Tk()
    raiz.title("Bloc de notas")
    raiz.geometry("800x500")
    AppNotas(raiz, Almacen(CARPETA)).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
