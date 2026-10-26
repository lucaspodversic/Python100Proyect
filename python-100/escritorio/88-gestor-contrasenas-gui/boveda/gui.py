"""Interfaz Tkinter del gestor. La ventana se crea solo en :func:`main`.

Flujo: pantalla de desbloqueo (abrir o crear bóveda) → lista de entradas.
Se **bloquea sola** tras ``INACTIVIDAD_S`` sin teclado/ratón: se descarta la
bóveda de memoria y se limpia el portapapeles.
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from .cripto import ErrorBoveda, ParametrosKdf
from .modelo import Boveda, Entrada, fortaleza, generar
from .portapapeles import CopiaSegura, Portapapeles, PortapapelesTk

RUTA_POR_DEFECTO = Path.home() / ".boveda-py100.boveda"
INACTIVIDAD_S = 300
SEGUNDOS_PORTAPAPELES = 20


class AppBoveda(ttk.Frame):
    """Interfaz de la bóveda: pantalla de desbloqueo/creación y pantalla principal con
    búsqueda, tabla, copia segura al portapapeles y bloqueo automático por inactividad.
    """
    def __init__(self, maestro: tk.Tk, ruta: Path, kdf: ParametrosKdf = ParametrosKdf(),
                 portapapeles: Portapapeles | None = None, reloj: Callable[[], float] = time.monotonic) -> None:
        """Portapapeles y reloj se inyectan para poder probar sin tocar el portapapeles real ni
        esperar minutos. Toda tecla o clic reinicia el contador de inactividad;
        cerrar la ventana limpia el portapapeles.
        """
        super().__init__(maestro, padding=8)
        self.raiz, self.ruta, self.kdf, self.reloj = maestro, ruta, kdf, reloj
        self.boveda: Boveda | None = None
        self.copia = CopiaSegura(portapapeles or PortapapelesTk(maestro), self.after, SEGUNDOS_PORTAPAPELES)
        self.estado = tk.StringVar()
        self._ultima_actividad = reloj()
        # Cualquier tecla o clic cuenta como actividad.
        maestro.bind_all("<Key>", self._actividad, add="+")
        maestro.bind_all("<Button>", self._actividad, add="+")
        maestro.protocol("WM_DELETE_WINDOW", self.salir)
        self.pantalla_desbloqueo()
        self._vigilar()

    # ------------------------------------------------------------ utilidades
    def _limpiar(self) -> None:
        """Destruye los widgets de la pantalla actual antes de dibujar otra."""
        for w in self.winfo_children():
            w.destroy()

    def _actividad(self, _e: object = None) -> None:
        """Registra el instante de la última interacción del usuario."""
        self._ultima_actividad = self.reloj()

    def _vigilar(self) -> None:
        """Cada segundo: si la bóveda está abierta y pasaron INACTIVIDAD_S sin actividad, la
        bloquea.
        """
        if self.boveda is not None and self.reloj() - self._ultima_actividad >= INACTIVIDAD_S:
            self.bloquear()
        self.after(1000, self._vigilar)

    # ------------------------------------------------------------ desbloqueo
    def pantalla_desbloqueo(self) -> None:
        """Pide la maestra (oculta). Si el archivo no existe es una bóveda nueva y pide
        repetirla para evitar errores de tipeo que la dejarían inaccesible.
        """
        self._limpiar()
        existe = self.ruta.exists()
        ttk.Label(self, text=("Desbloquear " if existe else "Crear ") + str(self.ruta)).pack(anchor="w")
        self.var_maestra = tk.StringVar()
        entrada = ttk.Entry(self, textvariable=self.var_maestra, show="•", width=40)
        entrada.pack(fill="x", pady=4)
        entrada.focus_set()
        if not existe:
            ttk.Label(self, text="Repetir contraseña maestra").pack(anchor="w")
            self.var_repetir = tk.StringVar()
            ttk.Entry(self, textvariable=self.var_repetir, show="•").pack(fill="x", pady=4)
        entrada.bind("<Return>", lambda _e: self.desbloquear())
        ttk.Button(self, text="Abrir" if existe else "Crear bóveda", command=self.desbloquear).pack()
        ttk.Label(self, textvariable=self.estado, foreground="red").pack()

    def desbloquear(self) -> bool:
        """Abre o crea la bóveda. Borra la maestra del widget enseguida. Los errores (clave
        incorrecta, no coinciden, archivo dañado) van a la barra de estado. Devuelve
        True si quedó abierta.
        """
        maestra = self.var_maestra.get()
        self.var_maestra.set("")  # no dejar la maestra en el widget
        try:
            if self.ruta.exists():
                self.boveda = Boveda.abrir(self.ruta, maestra)
            else:
                if maestra != self.var_repetir.get():
                    raise ErrorBoveda("las contraseñas no coinciden")
                self.boveda = Boveda.crear(self.ruta, maestra, self.kdf)
        except (ErrorBoveda, OSError) as e:
            self.estado.set(str(e))
            return False
        self.estado.set("")
        self._actividad()
        self.pantalla_principal()
        return True

    def bloquear(self) -> None:
        """Limpia el portapapeles, suelta la bóveda (y con ella la clave) y vuelve a pedir la
        maestra.
        """
        self.copia.limpiar_ahora()
        self.boveda = None  # la clave derivada se libera con el objeto
        self.estado.set("Bóveda bloqueada")
        self.pantalla_desbloqueo()

    def salir(self) -> None:
        """Al cerrar, no deja secretos en el portapapeles."""
        self.copia.limpiar_ahora()
        self.raiz.destroy()

    # ------------------------------------------------------------ principal
    def pantalla_principal(self) -> None:
        """Barra con buscador y acciones, tabla de sitio/usuario (las contraseñas nunca se
        muestran en la tabla) y atajos para copiar.
        """
        self._limpiar()
        barra = ttk.Frame(self)
        barra.pack(fill="x")
        self.var_buscar = tk.StringVar()
        self.var_buscar.trace_add("write", lambda *_: self.refrescar())
        ttk.Entry(barra, textvariable=self.var_buscar).pack(side="left", fill="x", expand=True)
        for texto, cmd in (("Nueva", lambda: self.editar(None)), ("Editar", self._editar_sel),
                           ("Eliminar", self.eliminar_sel), ("Bloquear", self.bloquear)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left")
        self.tabla = ttk.Treeview(self, columns=("sitio", "usuario"), show="headings", height=14)
        self.tabla.heading("sitio", text="Sitio")
        self.tabla.heading("usuario", text="Usuario")
        self.tabla.pack(fill="both", expand=True, pady=4)
        self.tabla.bind("<Double-1>", lambda _e: self.copiar_clave_sel())
        abajo = ttk.Frame(self)
        abajo.pack(fill="x")
        ttk.Button(abajo, text="Copiar usuario", command=self.copiar_usuario_sel).pack(side="left")
        ttk.Button(abajo, text="Copiar contraseña", command=self.copiar_clave_sel).pack(side="left")
        ttk.Label(abajo, textvariable=self.estado).pack(side="left", padx=8)
        self.refrescar()

    def refrescar(self) -> None:
        """Rellena la tabla según el filtro de búsqueda; el iid de cada fila es el id de la
        entrada.
        """
        if self.boveda is None:
            return
        self.tabla.delete(*self.tabla.get_children())
        for e in self.boveda.buscar(self.var_buscar.get()):
            self.tabla.insert("", "end", iid=e.id, values=(e.sitio, e.usuario))

    def _seleccion(self) -> Entrada | None:
        """Entrada seleccionada en la tabla, o None."""
        sel = self.tabla.selection()
        return self.boveda.obtener(sel[0]) if sel and self.boveda else None

    def copiar_clave_sel(self) -> None:
        """Copia la contraseña seleccionada; se borra sola del portapapeles a los
        SEGUNDOS_PORTAPAPELES.
        """
        if (e := self._seleccion()) is not None:
            self.copia.copiar(e.clave)
            self.estado.set(f"Contraseña copiada; se borrará en {SEGUNDOS_PORTAPAPELES} s")

    def copiar_usuario_sel(self) -> None:
        """Copia el usuario seleccionado."""
        if (e := self._seleccion()) is not None:
            self.copia.copiar(e.usuario)

    def eliminar_sel(self) -> None:
        """Elimina la entrada seleccionada previa confirmación."""
        if (e := self._seleccion()) is not None and messagebox.askyesno("Eliminar", f"¿Eliminar {e.sitio}?"):
            self.boveda.eliminar(e.id)
            self.refrescar()

    def _editar_sel(self) -> None:
        """Abre el diálogo de edición de la entrada seleccionada."""
        if (e := self._seleccion()) is not None:
            self.editar(e)

    def editar(self, entrada: Entrada | None) -> tk.Toplevel:
        """Diálogo para crear/editar una entrada, con generador y medidor de fortaleza."""
        dlg = tk.Toplevel(self)
        dlg.title("Entrada")
        dlg.transient(self.raiz)
        vars_ = {k: tk.StringVar(value=getattr(entrada, k) if entrada else "") for k in ("sitio", "usuario", "clave", "notas")}
        for fila, (k, etiqueta) in enumerate((("sitio", "Sitio"), ("usuario", "Usuario"), ("clave", "Contraseña"), ("notas", "Notas"))):
            ttk.Label(dlg, text=etiqueta).grid(row=fila, column=0, sticky="w")
            ttk.Entry(dlg, textvariable=vars_[k], width=36, show="•" if k == "clave" else "").grid(row=fila, column=1)
        medidor = tk.StringVar()
        vars_["clave"].trace_add("write", lambda *_: medidor.set(f"Fortaleza: {fortaleza(vars_['clave'].get())}"))
        ttk.Label(dlg, textvariable=medidor).grid(row=4, column=1, sticky="w")
        ttk.Button(dlg, text="Generar", command=lambda: vars_["clave"].set(generar())).grid(row=2, column=2)

        def aceptar() -> None:
            """Valida y guarda (alta o modificación); si falta un campo obligatorio avisa y
            deja el diálogo abierto.
            """
            datos = {k: v.get() for k, v in vars_.items()}
            try:
                if entrada is None:
                    self.boveda.agregar(Entrada(**datos))
                else:
                    self.boveda.actualizar(entrada.id, **datos)
            except ValueError as err:
                messagebox.showerror("Entrada", str(err), parent=dlg)
                return
            dlg.destroy()
            self.refrescar()

        ttk.Button(dlg, text="Guardar", command=aceptar).grid(row=5, column=1, sticky="e")
        dlg.vars, dlg.aceptar = vars_, aceptar  # accesibles desde tests
        return dlg


def main() -> None:
    """Punto de entrada: ruta de la bóveda opcional como primer argumento."""
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RUTA_POR_DEFECTO
    raiz = tk.Tk()
    raiz.title("Gestor de contraseñas")
    AppBoveda(raiz, ruta).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
