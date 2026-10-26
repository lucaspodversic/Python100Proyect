# 57 · Generador de códigos QR

Convierte texto, URLs, credenciales WiFi, contactos (vCard) o un mailto en un
código QR (PNG, JPG o SVG), con colores y logo opcional.

## Qué demuestra
- Uso de `qrcode` + Pillow; SVG vectorial con `SvgPathImage`.
- Payloads estándar con **escapado correcto** (WiFi formato ZXing, vCard 3.0, mailto).
- Logo centrado con corrección de errores **H** forzada para mantener legibilidad.
- Vista previa ASCII en la terminal.

## Arquitectura
```
generador_qr/
  contenidos.py  # contenido_wifi, contenido_vcard, contenido_email
  generador.py   # OpcionesQR, matriz, generar_imagen, guardar
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m generador_qr texto "https://python.org"                 # ASCII en terminal
python -m generador_qr -o web.png --color "#1a237e" texto "https://python.org"
python -m generador_qr -o wifi.png wifi "MiCasa" --clave "s3creta"
python -m generador_qr -o yo.svg vcard Ana --apellido Pérez --telefono +5491100000000
python -m generador_qr -o logo.png --logo marca.png texto "hola"
```

## Tests
```bash
pytest
```
Se verifican payloads, dimensiones, patrones de posición y colores (sin lector QR externo).

## Limitaciones
- No incluye decodificación (requeriría `pyzbar` + la librería nativa zbar).
- Colores con poco contraste o invertidos pueden no ser leídos por algunos lectores.
