"""Constructores de 'payloads' estándar que los teléfonos entienden.

- WiFi: formato de facto `WIFI:T:WPA;S:<ssid>;P:<clave>;;` (ZXing).
  Los caracteres \\ ; , : " deben escaparse con barra invertida.
- vCard 3.0 para contactos.
- mailto: con asunto y cuerpo codificados en URL.
"""
from __future__ import annotations

from urllib.parse import quote

# Valores admitidos para T: en el formato WIFI de ZXing.
SEGURIDADES = {"WPA", "WEP", "nopass"}


def _escapar_wifi(t: str) -> str:
    """Antepone "\\" a los caracteres especiales del formato WIFI."""
    # La barra invertida va primero: si no, se volverían a escapar las barras recién agregadas.
    for c in '\\;,:"':
        t = t.replace(c, "\\" + c)
    return t


def contenido_wifi(ssid: str, clave: str = "", seguridad: str = "WPA", oculta: bool = False) -> str:
    """Texto para que el teléfono se conecte a la red al escanear el código."""
    if seguridad not in SEGURIDADES:
        raise ValueError(f"Seguridad debe ser una de {sorted(SEGURIDADES)}")
    # Caso borde: red WPA/WEP sin clave no tiene sentido.
    if seguridad != "nopass" and not clave:
        raise ValueError("Una red protegida necesita clave")
    partes = [f"T:{seguridad}", f"S:{_escapar_wifi(ssid)}"]
    if seguridad != "nopass":
        # Las redes abiertas no llevan el campo P.
        partes.append(f"P:{_escapar_wifi(clave)}")
    if oculta:
        # H:true indica red oculta (no anuncia el SSID).
        partes.append("H:true")
    # El formato termina con doble punto y coma.
    return "WIFI:" + ";".join(partes) + ";;"


def _escapar_vcard(t: str) -> str:
    """Escapa "\\", ",", ";" y saltos de línea, como pide vCard 3.0."""
    return t.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def contenido_vcard(nombre: str, apellido: str = "", telefono: str = "", email: str = "",
                    organizacion: str = "", url: str = "") -> str:
    """Arma una tarjeta de contacto vCard 3.0 con los campos no vacíos."""
    lineas = ["BEGIN:VCARD", "VERSION:3.0",
              # N = apellido;nombre;segundos nombres;prefijo;sufijo. FN = nombre completo para mostrar.
              f"N:{_escapar_vcard(apellido)};{_escapar_vcard(nombre)};;;",
              f"FN:{_escapar_vcard((nombre + ' ' + apellido).strip())}"]
    # Los campos opcionales vacíos se omiten.
    if organizacion:
        lineas.append(f"ORG:{_escapar_vcard(organizacion)}")
    if telefono:
        lineas.append(f"TEL;TYPE=CELL:{telefono}")
    if email:
        lineas.append(f"EMAIL:{email}")
    if url:
        lineas.append(f"URL:{url}")
    lineas.append("END:VCARD")
    return "\n".join(lineas)


def contenido_email(destino: str, asunto: str = "", cuerpo: str = "") -> str:
    """Enlace mailto: con asunto y cuerpo codificados para URL."""
    # quote() codifica espacios y acentos; los parámetros vacíos no se agregan.
    params = "&".join(f"{k}={quote(v)}" for k, v in (("subject", asunto), ("body", cuerpo)) if v)
    return f"mailto:{destino}" + (f"?{params}" if params else "")
