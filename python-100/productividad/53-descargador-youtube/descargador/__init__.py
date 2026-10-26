"""descargador: baja videos de YouTube en la calidad elegida (vía yt-dlp).

Uso permitido: sólo contenido propio, con licencia libre o con permiso
del titular, de acuerdo con los Términos de Servicio de YouTube.
"""
# API pública: lógica pura (modelo) y servicio con backend intercambiable.
from .modelo import Formato, InfoVideo, elegir_formato, nombre_seguro, validar_url
from .servicio import Descargador, BackendYtDlp

__all__ = ["Formato", "InfoVideo", "elegir_formato", "nombre_seguro", "validar_url",
           "Descargador", "BackendYtDlp"]
