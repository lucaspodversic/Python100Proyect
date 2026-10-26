"""Dashboard de finanzas personales."""

# datos = carga/normalización del CSV; analisis = cálculos puros; graficos y app = visualización.
from .datos import categorizar, cargar_movimientos, generar_demo
from .analisis import gastos_por_categoria, kpis, resumen_mensual, control_presupuesto

__all__ = ["cargar_movimientos", "categorizar", "generar_demo", "resumen_mensual", "gastos_por_categoria",
           "kpis", "control_presupuesto"]
