"""Interfaz Tkinter del editor. La ventana se crea solo en :func:`main`."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .nucleo import (Documento, ErrorEditor, Recientes, buscar, estadisticas,
                     offset_a_indice_tk, reemplazar, siguiente)

RECIENTES = Path.home() / ".config" / "editor-py100" / "recientes.json"


class AppEditor(ttk.Frame):
    """Ventana del editor: área de texto con scroll, barra de estado y menús. Toda operación
    sobre archivos o búsquedas delega en ``nucleo``; esta clase solo traduce entre
    widgets Tk y esas funciones puras.
    """
    def __init__(self, maestro: tk.Tk, recientes: Recientes | None = None) -> None:
        """Arranca con un documento vacío. ``recientes`` se inyecta en los tests para no tocar
        el archivo de configuración real del usuario.
        """
        super().__init__(maestro)
        self.raiz = maestro
        self.doc = Documento()
        self.recientes = recientes or Recientes.cargar(RECIENTES)
        self.estado = tk.StringVar()
        self._construir()
        self._actualizar_estado()

    # ------------------------------------------------------------ construcción
    def _construir(self) -> None:
        """Crea el Text (con deshacer nativo de Tk), la barra de desplazamiento, la etiqueta de
        estado, el resaltado de hallazgos, los atajos y los menús.
        """
        self.texto = tk.Text(self, undo=True, wrap="word", font=("TkFixedFont", 11))
        barra = ttk.Scrollbar(self, command=self.texto.yview)
        self.texto.configure(yscrollcommand=barra.set)
        self.texto.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        ttk.Label(self, textvariable=self.estado, anchor="w").grid(row=1, column=0, columnspan=2, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.texto.tag_configure("hallazgo", background="yellow")
        # <<Modified>> se dispara al cambiar el texto; lo usamos para el título y la barra.
        self.texto.bind("<<Modified>>", self._al_modificar)
        self.texto.bind("<KeyRelease>", lambda _e: self._actualizar_estado())

        menu = tk.Menu(self.raiz)
        archivo = tk.Menu(menu, tearoff=False)
        archivo.add_command(label="Nuevo", accelerator="Ctrl+N", command=self.nuevo)
        archivo.add_command(label="Abrir…", accelerator="Ctrl+O", command=self.dialogo_abrir)
        archivo.add_command(label="Guardar", accelerator="Ctrl+S", command=self.guardar)
        archivo.add_command(label="Guardar como…", command=self.guardar_como)
        self.menu_recientes = tk.Menu(archivo, tearoff=False)
        archivo.add_cascade(label="Recientes", menu=self.menu_recientes)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.salir)
        editar = tk.Menu(menu, tearoff=False)
        editar.add_command(label="Deshacer", accelerator="Ctrl+Z", command=lambda: self.texto.event_generate("<<Undo>>"))
        editar.add_command(label="Rehacer", accelerator="Ctrl+Y", command=lambda: self.texto.event_generate("<<Redo>>"))
        editar.add_command(label="Buscar…", accelerator="Ctrl+F", command=self.dialogo_buscar)
        editar.add_command(label="Reemplazar todo…", accelerator="Ctrl+H", command=self.dialogo_reemplazar)
        editar.add_command(label="Ir a línea…", accelerator="Ctrl+G", command=self.dialogo_ir_a)
        menu.add_cascade(label="Archivo", menu=archivo)
        menu.add_cascade(label="Editar", menu=editar)
        self.raiz.config(menu=menu)
        for tecla, cmd in (("n", self.nuevo), ("o", self.dialogo_abrir), ("s", self.guardar),
                           ("f", self.dialogo_buscar), ("h", self.dialogo_reemplazar), ("g", self.dialogo_ir_a)):
            self.raiz.bind(f"<Control-{tecla}>", lambda _e, c=cmd: (c(), "break")[1])
        self.raiz.protocol("WM_DELETE_WINDOW", self.salir)
        self._refrescar_recientes()

    # ------------------------------------------------------------ sincronización
    def _contenido(self) -> str:
        """Texto completo del widget, sin el salto de línea final que Tk agrega siempre."""
        return self.texto.get("1.0", "end-1c")  # "end-1c" quita el \n que Tk añade

    def _al_modificar(self, _e: object = None) -> None:
        """Sincroniza el modelo con el widget. Hay que volver a poner la bandera 'modified' en
        False porque Tk solo emite <<Modified>> cuando la bandera cambia de False a
        True.
        """
        self.doc.texto = self._contenido()
        self.texto.edit_modified(False)  # rearmar el evento
        self._actualizar_estado()

    def _actualizar_estado(self) -> None:
        """Recalcula la barra de estado (línea/columna del cursor, palabras, caracteres,
        codificación) y el título, con '*' si hay cambios sin guardar. Tk numera
        columnas desde 0; se muestra desde 1.
        """
        self.doc.texto = self._contenido()
        est = estadisticas(self.doc.texto)
        linea, col = self.texto.index("insert").split(".")
        self.estado.set(f"Ln {linea}, Col {int(col) + 1} | {est['palabras']} palabras | "
                        f"{est['caracteres']} caracteres | {self.doc.codificacion}")
        self.raiz.title(f"{'*' if self.doc.modificado else ''}{self.doc.nombre} — Editor")

    def _refrescar_recientes(self) -> None:
        """Reconstruye el submenú Archivos recientes (más reciente primero)."""
        self.menu_recientes.delete(0, "end")
        for r in self.recientes.rutas:
            self.menu_recientes.add_command(label=r, command=lambda p=r: self.abrir(Path(p)))

    # ------------------------------------------------------------ archivos
    def _confirmar_descartar(self) -> bool:
        """Si hay cambios sin guardar, pregunta. Devuelve True si se puede continuar."""
        if not self.doc.modificado:
            return True
        r = messagebox.askyesnocancel("Cambios sin guardar", f"¿Guardar cambios en {self.doc.nombre}?")
        if r is None:
            return False
        return self.guardar() if r else True

    def _poner_documento(self, doc: Documento) -> None:
        """Reemplaza el documento mostrado. Se reinicia la pila de deshacer para que Ctrl+Z no
        'deshaga' la apertura y muestre el archivo anterior.
        """
        self.doc = doc
        self.texto.delete("1.0", "end")
        self.texto.insert("1.0", doc.texto)
        self.texto.edit_reset()  # el historial de deshacer no cruza documentos
        self._actualizar_estado()

    def nuevo(self) -> None:
        """Documento vacío, preguntando antes si hay cambios sin guardar."""
        if self._confirmar_descartar():
            self._poner_documento(Documento())

    def abrir(self, ruta: Path) -> bool:
        """Abre ``ruta`` (detectando codificación y fin de línea). Devuelve False si el usuario
        canceló o el archivo no se pudo leer (binario, permisos); en ese caso
        muestra el error y no toca el documento actual.
        """
        if not self._confirmar_descartar():
            return False
        try:
            self._poner_documento(Documento.abrir(ruta))
        except (OSError, ErrorEditor) as e:
            messagebox.showerror("No se pudo abrir", str(e))
            return False
        self.recientes.agregar(ruta)
        self._refrescar_recientes()
        return True

    def dialogo_abrir(self) -> None:
        """Diálogo de selección de archivo → abrir."""
        ruta = filedialog.askopenfilename()
        if ruta:
            self.abrir(Path(ruta))

    def guardar(self) -> bool:
        """Ctrl+S: si el documento nunca se guardó, pide nombre (Guardar como)."""
        if self.doc.ruta is None:
            return self.guardar_como()
        return self._guardar_en(None)

    def guardar_como(self) -> bool:
        """Pide un nombre de archivo y guarda ahí; False si se cancela."""
        ruta = filedialog.asksaveasfilename(defaultextension=".txt")
        return self._guardar_en(Path(ruta)) if ruta else False

    def _guardar_en(self, ruta: Path | None) -> bool:
        """Guarda (escritura atómica en ``nucleo``) y actualiza recientes y título. Ante error
        lo muestra y devuelve False sin perder el texto en pantalla.
        """
        self.doc.texto = self._contenido()
        try:
            destino = self.doc.guardar(ruta)
        except (OSError, ErrorEditor, UnicodeEncodeError) as e:
            messagebox.showerror("No se pudo guardar", str(e))
            return False
        self.recientes.agregar(destino)
        self._refrescar_recientes()
        self._actualizar_estado()
        return True

    def salir(self) -> None:
        """Cierra la ventana si no hay cambios o el usuario acepta descartarlos."""
        if self._confirmar_descartar():
            self.raiz.destroy()

    # ------------------------------------------------------------ búsqueda
    def resaltar(self, consulta: str, **opciones: bool) -> int:
        """Marca todas las coincidencias y selecciona la siguiente al cursor."""
        self.texto.tag_remove("hallazgo", "1.0", "end")
        contenido = self._contenido()
        try:
            hallazgos = buscar(contenido, consulta, **opciones)
        except ErrorEditor as e:
            messagebox.showerror("Buscar", str(e))
            return 0
        for ini, fin in hallazgos:
            self.texto.tag_add("hallazgo", f"1.0+{ini}c", f"1.0+{fin}c")
        cursor = len(self.texto.get("1.0", "insert"))
        prox = siguiente(hallazgos, cursor)
        if prox:
            self.texto.mark_set("insert", offset_a_indice_tk(contenido, prox[1]))
            self.texto.see("insert")
        return len(hallazgos)

    def dialogo_buscar(self) -> None:
        """Pide un texto, resalta todas las coincidencias y muestra cuántas hay."""
        consulta = simpledialog.askstring("Buscar", "Texto a buscar:", parent=self.raiz)
        if consulta:
            n = self.resaltar(consulta)
            self.estado.set(f"{n} coincidencia(s)")

    def reemplazar_todo(self, consulta: str, nuevo: str, **opciones: bool) -> int:
        """Reemplaza todas las coincidencias y devuelve cuántas fueron. El texto se reescribe
        completo dentro de un único bloque de deshacer, así un Ctrl+Z revierte el
        reemplazo entero.
        """
        try:
            texto, n = reemplazar(self._contenido(), consulta, nuevo, **opciones)
        except ErrorEditor as e:
            messagebox.showerror("Reemplazar", str(e))
            return 0
        if n:
            # Un solo bloque de deshacer para todo el reemplazo: se apagan los
            # separadores automáticos (Tk pondría uno entre delete e insert).
            self.texto.configure(autoseparators=False)
            self.texto.edit_separator()
            self.texto.delete("1.0", "end-1c")
            self.texto.insert("1.0", texto)
            self.texto.edit_separator()
            self.texto.configure(autoseparators=True)
            self._actualizar_estado()
        return n

    def dialogo_reemplazar(self) -> None:
        """Pide texto a buscar y su reemplazo (el reemplazo puede ser vacío; solo None
        significa cancelar).
        """
        consulta = simpledialog.askstring("Reemplazar", "Buscar:", parent=self.raiz)
        if not consulta:
            return
        nuevo = simpledialog.askstring("Reemplazar", "Reemplazar por:", parent=self.raiz)
        if nuevo is not None:
            messagebox.showinfo("Reemplazar", f"{self.reemplazar_todo(consulta, nuevo)} reemplazo(s)")

    def dialogo_ir_a(self) -> None:
        """Mueve el cursor al principio de la línea pedida (acotada a las existentes) y la hace
        visible.
        """
        total = int(self.texto.index("end-1c").split(".")[0])
        n = simpledialog.askinteger("Ir a línea", f"Línea (1-{total}):", minvalue=1, maxvalue=total, parent=self.raiz)
        if n:
            self.texto.mark_set("insert", f"{n}.0")
            self.texto.see("insert")


def main() -> None:
    """Punto de entrada: crea la ventana y, si se pasó un archivo por argumento, lo abre."""
    raiz = tk.Tk()
    raiz.geometry("800x600")
    app = AppEditor(raiz)
    app.pack(fill="both", expand=True)
    if len(sys.argv) > 1:
        app.abrir(Path(sys.argv[1]))
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
