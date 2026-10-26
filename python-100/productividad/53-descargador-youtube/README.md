# 53 · Descargador de videos de YouTube

Interfaz CLI que descarga videos en la calidad deseada (o sólo el audio).

> ⚖️ **Uso responsable**: los Términos de Servicio de YouTube prohíben descargar
> contenido salvo que la plataforma lo permita expresamente. Usá esta herramienta
> **sólo con contenido propio, con licencia libre (p. ej. Creative Commons) o con
> permiso del titular**. Para uso offline legítimo existe YouTube Premium.

## Qué demuestra
- **Backend intercambiable**: el plan original pedía `pytube`, pero suele romperse con
  cada cambio de YouTube; se usa **yt-dlp** detrás de la interfaz `Backend`.
- Lógica pura y testeada: validación estricta de URL (sin dominios "parecidos"),
  selección de formato (progresivo vs. video+audio), nombres de archivo seguros.
- Barra de progreso vía *hooks*.

## Arquitectura
```
descargador/
  modelo.py    # Formato, InfoVideo, validar_url, elegir_formato, nombre_seguro
  servicio.py  # Backend (Protocol), BackendYtDlp, Descargador
  cli.py
```

## Instalación
```bash
pip install -e ".[dev,ytdlp]"
# Para combinar video+audio en alta calidad hace falta ffmpeg en el PATH.
```

## Uso
```bash
python -m descargador "https://youtu.be/ID" --info
python -m descargador "https://youtu.be/ID" -c 720p -o videos/
python -m descargador "https://youtu.be/ID" -c audio
```

## Tests
```bash
pytest
```
Backend falso: no se realiza ningún pedido a YouTube.

## Limitaciones
- Sin GUI (la lógica está separada, se puede montar Tkinter encima).
- No descarga listas de reproducción (`noplaylist`) a propósito.
