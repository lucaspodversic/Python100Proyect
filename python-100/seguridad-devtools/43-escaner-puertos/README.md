# 43 · Escáner de puertos simple

Escáner TCP (método *connect*) concurrente para **auditorías básicas de hosts propios**.

> ⚠️ **Aviso legal y ético**: escanear equipos o redes sin autorización puede ser
> ilegal en tu país y viola los términos de muchos proveedores. Usalo sólo sobre
> máquinas tuyas o con **autorización por escrito**. La herramienta **no tiene
> objetivo por defecto**: exige `--host` y la confirmación `--autorizado`.

## Qué demuestra
- Sockets TCP con timeouts y clasificación abierto / cerrado / filtrado.
- Concurrencia con `ThreadPoolExecutor`.
- Lectura opcional de banners (ssh, smtp…).
- "Sonda" inyectable para tests sin red.

## Arquitectura
```
escaner/
  nucleo.py  # parsear_puertos, probar_puerto, escanear
  cli.py     # argparse, salida tabla o JSON, exige --autorizado
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
python -m escaner --host 127.0.0.1 --puertos 1-1024 --autorizado
python -m escaner --host mi-servidor.local --puertos 22,80,443 --banner --json --autorizado
```

## Tests
```bash
pytest
```
Todos los tests corren **sólo contra 127.0.0.1**, con sockets abiertos por el propio test.

## Limitaciones
- No hace escaneo SYN, UDP ni detección de SO (para eso existe `nmap`).
- Un "filtrado" puede ser también un host caído o lento.
