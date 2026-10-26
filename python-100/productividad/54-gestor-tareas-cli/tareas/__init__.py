"""tareas: gestor de tareas por línea de comandos sobre SQLite."""
# API pública: modelo de dominio y repositorio SQLite.
from .modelo import Prioridad, Tarea, parsear_fecha
from .repositorio import Repositorio

__all__ = ["Prioridad", "Tarea", "parsear_fecha", "Repositorio"]
