# 66 · Recolector de datos climáticos

Obtiene pronóstico (hasta 16 días) o datos históricos diarios de cualquier ciudad desde
la **API pública Open-Meteo**, calcula estadísticas, dibuja un gráfico ASCII y exporta CSV.

## Qué demuestra
- Uso de una **API pública oficial** (sin clave) en lugar de scrapear sitios del clima.
- Geocodificación → coordenadas → datos diarios (`temperature_2m_max/min`, `precipitation_sum`, viento).
- Estadísticas (medias, extremos con fecha, días de lluvia ≥ 1 mm) y gráfico de rangos en terminal.
- Cliente educado (User-Agent honesto, robots.txt, pausa entre pedidos); URLs base inyectables para tests.

## Arquitectura
```
clima/
  cliente.py   # ClienteEducado
  api.py       # ApiOpenMeteo, Lugar, DiaClima
  analisis.py  # estadisticas, grafico_ascii, guardar_csv
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m clima "Córdoba" --dias 7
python -m clima Madrid Lima --csv datos/
python -m clima "Buenos Aires" --desde 2026-01-01 --hasta 2026-01-31 --csv enero.csv
```

## Tests
```bash
pytest
```
Las tres APIs (geocoding, forecast, archive) se simulan en `127.0.0.1` con fixtures JSON.

## Limitaciones
- Open-Meteo es gratuita para uso no comercial; respetá su límite diario de llamadas.
- Si hay varias ciudades homónimas se toma el primer resultado; el país se muestra en la salida para verificarlo.
