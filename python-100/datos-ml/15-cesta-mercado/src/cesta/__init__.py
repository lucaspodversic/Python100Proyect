"""Análisis de cesta de mercado (Apriori + reglas de asociación)."""

# apriori = algoritmo puro (sin pandas); datos = tickets; sugerencias = reglas → acciones de negocio.
from .apriori import Regla, apriori, generar_reglas
from .datos import cargar_tickets, generar_tickets
from .sugerencias import sugerencias_layout

__all__ = ["apriori", "generar_reglas", "Regla", "generar_tickets", "cargar_tickets", "sugerencias_layout"]
