# 68 · Comparador de precios de vuelos

Parser **genérico** de resultados de vuelos (HTML con perfil de selectores CSS, o JSON de una API con
mapeo de claves), comparación por precio/duración/equilibrio, filtros y **historial con alertas de baja**.

> ⚠️ **Términos de uso.** Aerolíneas y buscadores (Google Flights, Skyscanner, Despegar, etc.)
> prohíben en general la extracción automatizada y usan medidas anti-bot. Este proyecto **no apunta
> a ningún sitio por defecto** ni intenta evadir protecciones: usa un User-Agent honesto, respeta
> robots.txt y espera 5 s entre pedidos. Para datos reales usá vías oficiales:
> **Amadeus for Developers (Self-Service Flight Offers Search)**, **Duffel**, **Kiwi Tequila**, las APIs
> NDC de las aerolíneas o exports propios de tu agencia. `parsear_json` está pensado para esas respuestas.

## Qué demuestra
- Normalización de precios internacionales (`US$ 1.234,50`, `€1,234.50`, `ARS 98.500`) con `Decimal`.
- Duraciones heterogéneas (`2h 05m`, `95 min`, ISO 8601 `PT2H35M`) y escalas en texto.
- Parser dirigido por datos: cambiar de fuente = cambiar un JSON, no el código. Tarjetas rotas se reportan sin abortar.
- Criterio "equilibrio": precio + valor del tiempo de viaje.
- Historial CSV append-only y detección de precios por debajo del mínimo histórico.

## Arquitectura
```
vuelos/
  cliente.py   # ClienteEducado (robots.txt, UA honesto, rate limiting)
  modelo.py    # Vuelo, parsear_precio, parsear_duracion, parsear_escalas
  parser.py    # PerfilVuelos, parsear_html, parsear_json
  comparar.py  # Criterio, ordenar, filtrar, resumen_por_aerolinea, HistorialPrecios
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m vuelos --archivo export.html --perfil perfil.json --max-escalas 0 --orden equilibrio
python -m vuelos --url https://mi-agencia.example/resultados --perfil perfil.json --historial precios.csv
```
Ejemplo de perfil en `tests/fixtures/perfil.json`. Exit codes: 0 ok, 1 error, 2 sin vuelos, 3 bloqueado por robots.txt.

## Tests
```bash
pytest
```
Todo contra fixtures locales y un servidor en `127.0.0.1`.

## Limitaciones
- No ejecuta JavaScript (la mayoría de buscadores cargan resultados dinámicamente → usar su API).
- No convierte monedas; compará ofertas en la misma moneda.
- Sólo ida; para ida y vuelta, modelá cada tramo o extendé `Vuelo`.
