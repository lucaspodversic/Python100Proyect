"""linter: analizador estático de malas prácticas basado en el módulo `ast`."""
# Importar reglas primero ejecuta sus decoradores y llena el catálogo REGLAS.
from .reglas import REGLAS, Hallazgo
from .motor import analizar_codigo, analizar_rutas

__all__ = ["REGLAS", "Hallazgo", "analizar_codigo", "analizar_rutas"]
