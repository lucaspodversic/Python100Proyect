"""desplegador: sube una app a un VPS usando Git + SSH con releases atómicos."""
# API pública: configuración, conexiones (real y simulada) y el orquestador.
from .config import ConfigDespliegue
from .conexion import ConexionDryRun, ConexionSSH, ResultadoComando
from .despliegue import Desplegador, ErrorDespliegue

__all__ = ["ConfigDespliegue", "ConexionDryRun", "ConexionSSH", "ResultadoComando",
           "Desplegador", "ErrorDespliegue"]
