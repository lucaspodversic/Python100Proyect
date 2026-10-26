# 52 · Organizador de descargas

Monitorea tu carpeta de Descargas y mueve los archivos a subcarpetas según su
tipo o nombre (Imágenes, Documentos, Facturas…).

## Qué demuestra
- Motor de reglas ordenadas (extensión + regex sobre el nombre).
- Vigilancia por **sondeo** sin dependencias, con chequeo de **estabilidad**
  (no mueve archivos que todavía se descargan) e ignorando `.crdownload`, `.part`, etc.
- Movimientos seguros: nunca sobrescribe (`archivo (1).ext`).
- Modo simulación y **deshacer** la última pasada (historial JSON).

## Arquitectura
```
organizador/
  reglas.py  # Regla, REGLAS_POR_DEFECTO, destino_para
  motor.py   # Organizador: organizar, vigilar, deshacer
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m organizador ~/Downloads --simular
python -m organizador ~/Downloads
python -m organizador ~/Downloads --vigilar --intervalo 10
python -m organizador ~/Downloads --deshacer
python -m organizador ~/Downloads --reglas mis_reglas.json
```
`mis_reglas.json`:
```json
[{"carpeta": "Facturas", "extensiones": ["pdf"], "patron": "factura"},
 {"carpeta": "Fotos", "extensiones": ["jpg", "png"]}]
```

## Tests
```bash
pytest
```

## Limitaciones
- El sondeo tiene una latencia igual al intervalo; para eventos instantáneos se puede usar `watchdog`.
- Sólo organiza la raíz de la carpeta (no recorre subcarpetas).
