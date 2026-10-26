"""Generador de informes PDF a partir de una base de datos SQL."""

# Pipeline del paquete: datos (SQL) → gráficos (PNG con matplotlib) → informe (PDF con fpdf2);
# programador agrega la ejecución periódica.
from .datos import Repositorio, crear_base_demo
from .graficos import grafico_barras, grafico_linea
from .informe import generar_informe
from .programador import Programacion, proxima_ejecucion

__all__ = ["Repositorio", "crear_base_demo", "grafico_barras", "grafico_linea",
           "generar_informe", "Programacion", "proxima_ejecucion"]
