# 67 · Agregador de titulares de noticias

Lee varios feeds **RSS 2.0 / Atom 1.0**, quita duplicados, filtra por palabras clave o antigüedad
y muestra el resumen o lo envía por **email** (texto + HTML).

## Qué demuestra
- Parser RSS/Atom con `xml.etree` (stdlib) que rechaza DOCTYPE/ENTITY (protección XXE / *billion laughs*).
- Fechas RFC 822 e ISO 8601 normalizadas a UTC; resúmenes sin HTML y recortados.
- Deduplicación por enlace y por título normalizado (sin tildes ni mayúsculas).
- HTML del email con todo escapado (los títulos vienen de terceros).
- SMTP con STARTTLS detrás de una interfaz → testeable con un SMTP falso.
- Un feed caído no frena el resto; cliente educado (robots.txt, User-Agent honesto, pausa).

## Arquitectura
```
titulares/
  cliente.py   # ClienteEducado
  feeds.py     # Noticia, parsear_feed
  resumen.py   # agregar, filtrar, texto_resumen, html_resumen
  correo.py    # armar_mensaje, EnviadorSMTP, EnviadorConsola
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m titulares https://ejemplo.org/rss.xml https://otro.org/atom.xml --horas 24 --incluir python
export SMTP_HOST=smtp.ejemplo.org SMTP_USUARIO=yo SMTP_CLAVE=... SMTP_REMITENTE=yo@ejemplo.org
python -m titulares https://ejemplo.org/rss.xml --email yo@ejemplo.org
```
Se usan los feeds que publican los propios medios, que es la vía prevista para reutilizar titulares.

## Tests
```bash
pytest
```
Feeds de fixtures servidos desde `127.0.0.1` y un SMTP falso: no se envía ningún correo real.

## Limitaciones
- No soporta RSS 1.0 (RDF) ni extensiones como `media:content`.
- No guarda historial: para "sólo noticias nuevas" usá `--horas` en una tarea programada.
