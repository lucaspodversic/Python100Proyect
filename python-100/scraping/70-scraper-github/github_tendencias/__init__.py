"""github_tendencias: repos en tendencia usando la API REST oficial de GitHub (no scraping de HTML)."""
# API pública: cliente de búsqueda, modelo Repo y salidas (ranking, Markdown, CSV).
from .api import ApiGitHub, LimiteExcedido, Repo, construir_consulta
from .ranking import exportar_csv, markdown, ordenar_por_ritmo

__all__ = ["ApiGitHub", "LimiteExcedido", "Repo", "construir_consulta", "exportar_csv", "markdown", "ordenar_por_ritmo"]
