"""Errores con posición (línea:columna) para mensajes útiles."""
from __future__ import annotations


class ErrorCalc(Exception):
    """Error del lenguaje con fase y posición: 'error de sintaxis en 1:4: …'. Las subclases
    solo cambian la fase.
    """
    fase = "error"

    def __init__(self, mensaje: str, linea: int = 0, col: int = 0) -> None:
        """Guarda mensaje y posición (línea 0 = sin posición)."""
        self.mensaje, self.linea, self.col = mensaje, linea, col
        super().__init__(str(self))

    def __str__(self) -> str:
        """Formato 'fase en L:C: mensaje'."""
        pos = f" en {self.linea}:{self.col}" if self.linea else ""
        return f"{self.fase}{pos}: {self.mensaje}"


class ErrorLexico(ErrorCalc):
    """Carácter o número inválido al tokenizar."""
    fase = "error léxico"


class ErrorSintaxis(ErrorCalc):
    """Tokens válidos pero en un orden que la gramática no acepta."""
    fase = "error de sintaxis"


class ErrorEjecucion(ErrorCalc):
    """Error al evaluar: tipos, división por cero, variable no definida, límites, etc."""
    fase = "error de ejecución"
