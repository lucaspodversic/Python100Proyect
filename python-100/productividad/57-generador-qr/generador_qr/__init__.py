"""generador_qr: crea códigos QR (PNG/SVG) para texto, URLs, WiFi y contactos."""
# API pública: constructores de contenido y generación de imagen.
from .contenidos import contenido_wifi, contenido_vcard, contenido_email
from .generador import OpcionesQR, generar_imagen, guardar, matriz

__all__ = ["contenido_wifi", "contenido_vcard", "contenido_email",
           "OpcionesQR", "generar_imagen", "guardar", "matriz"]
