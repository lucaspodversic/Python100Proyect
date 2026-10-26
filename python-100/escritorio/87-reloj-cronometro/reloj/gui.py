"""Interfaz Tkinter con pestañas: Reloj, Cronómetro, Temporizador y Alarmas.

La ventana se crea solo en :func:`main`. Un único bucle ``after`` cada
50 ms actualiza todas las pestañas y comprueba temporizador y alarmas.
"""
from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import messagebox, ttk

from .tiempo import Alarma, Cronometro, Temporizador, formatear, parsear_duracion

TICK_MS = 50
FUENTE = ("TkFixedFont", 32)


class AppReloj(ttk.Notebook):
    """Aplicación con cuatro pestañas (reloj, cronómetro, temporizador, alarmas). Toda la
    lógica de tiempo está en ``reloj.tiempo``; esta clase solo refresca etiquetas y
    reacciona a botones.
    """
    def __init__(self, maestro: tk.Tk, ahora: Callable[[], datetime] = datetime.now,
                 monotonico: Callable[[], float] = time.monotonic,
                 avisar: Callable[[str], None] | None = None) -> None:
        """Los relojes se inyectan: ``ahora`` (hora de pared, para reloj y alarmas) y
        ``monotonico`` (para medir duraciones sin saltos por cambios de hora del
        sistema). Los tests pasan relojes falsos y un ``avisar`` que solo registra.
        """
        super().__init__(maestro)
        self.raiz = maestro
        self.ahora = ahora
        self.crono = Cronometro(monotonico)
        self.temp: Temporizador | None = None
        self.monotonico = monotonico
        self.alarmas: list[Alarma] = []
        # avisar se puede sustituir en tests (para no abrir un messagebox modal).
        self.avisar = avisar or self._avisar_por_defecto
        self.avisos: list[str] = []
        self._pestana_reloj()
        self._pestana_crono()
        self._pestana_temporizador()
        self._pestana_alarmas()
        self._tick()

    # ------------------------------------------------------------ pestañas
    def _pestana_reloj(self) -> None:
        """Pestaña Reloj: hora grande y fecha."""
        f = ttk.Frame(self, padding=20)
        self.txt_reloj = tk.StringVar()
        self.txt_fecha = tk.StringVar()
        ttk.Label(f, textvariable=self.txt_reloj, font=FUENTE).pack()
        ttk.Label(f, textvariable=self.txt_fecha).pack()
        self.add(f, text="Reloj")

    def _pestana_crono(self) -> None:
        """Pestaña Cronómetro: tiempo con centésimas, botones y lista de vueltas (la más
        reciente arriba).
        """
        f = ttk.Frame(self, padding=20)
        self.txt_crono = tk.StringVar(value=formatear(0, True))
        ttk.Label(f, textvariable=self.txt_crono, font=FUENTE).pack()
        b = ttk.Frame(f)
        b.pack()
        self.btn_crono = ttk.Button(b, text="Iniciar", command=self.crono_alternar)
        self.btn_crono.pack(side="left")
        ttk.Button(b, text="Vuelta", command=self.crono_vuelta).pack(side="left")
        ttk.Button(b, text="Reiniciar", command=self.crono_reiniciar).pack(side="left")
        self.lista_vueltas = tk.Listbox(f, height=8)
        self.lista_vueltas.pack(fill="both", expand=True, pady=6)
        self.add(f, text="Cronómetro")

    def _pestana_temporizador(self) -> None:
        """Pestaña Temporizador: duración editable (acepta '90', '5:00', '1h 30m'), cuenta
        regresiva y barra de progreso.
        """
        f = ttk.Frame(self, padding=20)
        self.entrada_temp = tk.StringVar(value="5:00")
        ttk.Entry(f, textvariable=self.entrada_temp, justify="center").pack()
        self.txt_temp = tk.StringVar(value="--:--:--")
        ttk.Label(f, textvariable=self.txt_temp, font=FUENTE).pack()
        self.barra_temp = ttk.Progressbar(f, maximum=1.0)
        self.barra_temp.pack(fill="x", pady=4)
        b = ttk.Frame(f)
        b.pack()
        ttk.Button(b, text="Iniciar/Pausar", command=self.temp_alternar).pack(side="left")
        ttk.Button(b, text="Reiniciar", command=self.temp_reiniciar).pack(side="left")
        self.add(f, text="Temporizador")

    def _pestana_alarmas(self) -> None:
        """Pestaña Alarmas: hora HH:MM + etiqueta, lista y botones para activar/desactivar o
        eliminar.
        """
        f = ttk.Frame(self, padding=20)
        fila = ttk.Frame(f)
        fila.pack(fill="x")
        self.entrada_alarma = tk.StringVar(value="07:00")
        self.etiqueta_alarma = tk.StringVar()
        ttk.Entry(fila, textvariable=self.entrada_alarma, width=6).pack(side="left")
        ttk.Entry(fila, textvariable=self.etiqueta_alarma).pack(side="left", fill="x", expand=True)
        ttk.Button(fila, text="Agregar", command=self.agregar_alarma).pack(side="left")
        self.lista_alarmas = tk.Listbox(f, height=8)
        self.lista_alarmas.pack(fill="both", expand=True, pady=6)
        b = ttk.Frame(f)
        b.pack()
        ttk.Button(b, text="Activar/Desactivar", command=self.alternar_alarma).pack(side="left")
        ttk.Button(b, text="Eliminar", command=self.eliminar_alarma).pack(side="left")
        self.add(f, text="Alarmas")

    # ------------------------------------------------------------ cronómetro
    def crono_alternar(self) -> None:
        """Iniciar/pausar el cronómetro con el mismo botón; el rótulo indica la próxima acción."""
        (self.crono.pausar if self.crono.corriendo else self.crono.iniciar)()
        self.btn_crono.config(text="Pausar" if self.crono.corriendo else "Continuar")

    def crono_vuelta(self) -> None:
        """Registra una vuelta (solo si corre) y la agrega arriba de la lista con su tiempo
        parcial.
        """
        if self.crono.corriendo:
            p = self.crono.vuelta()
            self.lista_vueltas.insert(0, f"Vuelta {len(self.crono.vueltas)}: {formatear(p, True)}")

    def crono_reiniciar(self) -> None:
        """Pone el cronómetro en cero y borra las vueltas."""
        self.crono.reiniciar()
        self.lista_vueltas.delete(0, "end")
        self.btn_crono.config(text="Iniciar")

    # ------------------------------------------------------------ temporizador
    def temp_alternar(self) -> None:
        """Si no hay temporizador (o ya terminó) crea uno con la duración escrita; si el texto
        es inválido lo indica sin lanzar. Luego alterna iniciar/pausar.
        """
        if self.temp is None or self.temp.terminado:
            try:
                self.temp = Temporizador(parsear_duracion(self.entrada_temp.get()), self.monotonico)
            except ValueError as e:
                self.txt_temp.set("formato inválido")
                self.avisos.append(str(e))
                return
        (self.temp.pausar if self.temp.corriendo else self.temp.iniciar)()

    def temp_reiniciar(self) -> None:
        """Descarta el temporizador actual y limpia la pantalla."""
        self.temp = None
        self.txt_temp.set("--:--:--")
        self.barra_temp["value"] = 0

    # ------------------------------------------------------------ alarmas
    def agregar_alarma(self) -> None:
        """Valida HH:MM y agrega la alarma; un formato inválido se informa con un diálogo."""
        try:
            alarma = Alarma.desde_texto(self.entrada_alarma.get(), self.etiqueta_alarma.get().strip())
        except ValueError as e:
            messagebox.showerror("Alarma", str(e))
            return
        self.alarmas.append(alarma)
        self._refrescar_alarmas()

    def _seleccion_alarma(self) -> int | None:
        """Índice de la alarma seleccionada en la lista, o None."""
        sel = self.lista_alarmas.curselection()
        return sel[0] if sel else None

    def alternar_alarma(self) -> None:
        """Activa/desactiva la alarma seleccionada sin borrarla."""
        if (i := self._seleccion_alarma()) is not None:
            self.alarmas[i].activa = not self.alarmas[i].activa
            self._refrescar_alarmas()

    def eliminar_alarma(self) -> None:
        """Borra la alarma seleccionada."""
        if (i := self._seleccion_alarma()) is not None:
            del self.alarmas[i]
            self._refrescar_alarmas()

    def _refrescar_alarmas(self) -> None:
        """Redibuja la lista de alarmas con su descripción legible."""
        self.lista_alarmas.delete(0, "end")
        for a in self.alarmas:
            self.lista_alarmas.insert("end", a.descripcion())

    # ------------------------------------------------------------ bucle
    def _avisar_por_defecto(self, mensaje: str) -> None:
        """Aviso real: pitido, trae la ventana al frente y muestra un diálogo."""
        self.raiz.bell()
        self.raiz.deiconify()
        self.raiz.lift()
        messagebox.showinfo("⏰", mensaje)

    def actualizar(self) -> None:
        """Refresca textos y dispara avisos. Separado de ``_tick`` para testearlo."""
        ahora = self.ahora()
        self.txt_reloj.set(f"{ahora:%H:%M:%S}")
        self.txt_fecha.set(f"{ahora:%d/%m/%Y}")
        self.txt_crono.set(formatear(self.crono.transcurrido(), True))
        if self.temp is not None:
            self.txt_temp.set(formatear(self.temp.restante() + 0.999))  # redondeo hacia arriba
            self.barra_temp["value"] = self.temp.progreso()
            if self.temp.comprobar():
                self.avisar("¡Tiempo cumplido!")
        for a in self.alarmas:
            if a.debe_sonar(ahora):
                self.avisar(f"Alarma {a.hora:%H:%M} {a.etiqueta}".strip())

    def _tick(self) -> None:
        """Bucle de refresco: actualiza todo y se reprograma cada TICK_MS con ``after``."""
        self.actualizar()
        self.after(TICK_MS, self._tick)


def main() -> None:
    """Punto de entrada de la aplicación."""
    raiz = tk.Tk()
    raiz.title("Reloj")
    AppReloj(raiz).pack(fill="both", expand=True)
    raiz.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
