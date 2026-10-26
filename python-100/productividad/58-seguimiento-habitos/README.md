# 58 · Seguimiento de hábitos

Registrá hábitos diarios (o de ciertos días de la semana) y mirá tus rachas,
porcentaje de cumplimiento y un mapa de calor en la terminal.

## Qué demuestra
- Cálculos puros de **racha actual / mejor racha / cumplimiento** con fechas inyectables.
- Hábitos programados por día de la semana: los días que no tocan no cortan la racha.
- El día de hoy sin marcar todavía no rompe la racha.
- Persistencia JSON con **escritura atómica** (temporal + `os.replace`).

## Arquitectura
```
habitos/
  modelo.py   # Habito, estadisticas, calendario
  almacen.py  # JSON
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m habitos nuevo leer
python -m habitos nuevo gimnasio --dias lmv
python -m habitos hecho leer
python -m habitos hecho leer --fecha 2026-10-20
python -m habitos ver
```
Salida de ejemplo:
```
leer: racha 5 (mejor 12) · 83% últimos 30 días · 40 en total
L █ █ · █
M █ █ █ █
...
```

## Tests
```bash
pytest
```

## Limitaciones
- Un único usuario; sin recordatorios (se puede combinar con cron).
