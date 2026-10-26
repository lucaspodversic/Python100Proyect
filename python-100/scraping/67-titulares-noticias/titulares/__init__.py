"""titulares: lee feeds RSS/Atom (formato oficial de sindicación) y arma un resumen."""
# API pública: parseo de feeds, agregación/formateo y envío por correo.
from .feeds import Noticia, parsear_feed
from .resumen import agregar, filtrar, texto_resumen, html_resumen
from .correo import EnviadorSMTP, armar_mensaje

__all__ = ["Noticia", "parsear_feed", "agregar", "filtrar", "texto_resumen", "html_resumen",
           "EnviadorSMTP", "armar_mensaje"]
