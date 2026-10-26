"""Tests del portapapeles con borrado automático (planificador falso)."""
from boveda.portapapeles import CopiaSegura, PortapapelesFalso


class Planificador:
    """Reemplazo de ``after``: guarda las tareas y las ejecuta cuando el test lo pide."""
    def __init__(self):
        """Sin tareas pendientes."""
        self.tareas = []

    def __call__(self, ms, fn):
        """Registra (ms, función) como haría ``after``."""
        self.tareas.append((ms, fn))

    def ejecutar_todo(self):
        """Simula que pasó el tiempo: ejecuta y vacía las tareas."""
        for _ms, fn in self.tareas:
            fn()
        self.tareas.clear()


def test_se_borra_al_expirar():
    """15 s → se programa a 15000 ms y al vencer queda vacío."""
    pp, plan = PortapapelesFalso(), Planificador()
    c = CopiaSegura(pp, plan, segundos=15)
    c.copiar("secreto")
    assert pp.contenido == "secreto" and plan.tareas[0][0] == 15000
    plan.ejecutar_todo()
    assert pp.contenido == ""


def test_no_pisa_lo_que_el_usuario_copio_despues():
    """Si el usuario copió otra cosa, el borrado no la toca."""
    pp, plan = PortapapelesFalso(), Planificador()
    c = CopiaSegura(pp, plan)
    c.copiar("secreto")
    pp.escribir("receta de cocina")          # el usuario copió otra cosa
    plan.ejecutar_todo()
    assert pp.contenido == "receta de cocina"


def test_copia_nueva_invalida_temporizador_anterior():
    """El temporizador de la primera copia no borra la segunda antes de tiempo."""
    pp, plan = PortapapelesFalso(), Planificador()
    c = CopiaSegura(pp, plan)
    c.copiar("uno")
    primera = plan.tareas.pop(0)[1]
    c.copiar("dos")
    primera()                                # el temporizador viejo no borra "dos" antes de tiempo
    assert pp.contenido == "dos"
    plan.ejecutar_todo()
    assert pp.contenido == ""


def test_limpiar_ahora():
    """Borrado inmediato (al bloquear o salir)."""
    pp, plan = PortapapelesFalso(), Planificador()
    c = CopiaSegura(pp, plan)
    c.copiar("x")
    c.limpiar_ahora()
    assert pp.contenido == ""
