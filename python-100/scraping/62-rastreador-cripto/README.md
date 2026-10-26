# 62 · Rastreador de precios de criptomonedas

Consulta precios en la **API pública oficial de CoinGecko**, guarda un historial CSV
y avisa cuando hay variaciones fuertes o se cruzan precios objetivo.

## Qué demuestra
- Uso de una **API oficial** en vez de scrapear HTML (`/simple/price`).
- Cliente educado: User-Agent honesto, `robots.txt`, intervalo mínimo entre pedidos
  (6 s por defecto; en modo vigilancia, mínimo 60 s entre pasadas).
- Reglas de alerta puras: variación % vs. última lectura, cruce de precio (sólo al cruzar)
  y variación de 24 h.
- Notificador intercambiable (consola; fácil de extender a email/Slack).

## Arquitectura
```
cripto/
  cliente.py    # ClienteEducado
  api.py        # ApiCoinGecko, Cotizacion
  historial.py  # CSV
  alertas.py    # ReglaVariacion, evaluar, NotificadorConsola
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m cripto bitcoin ethereum --divisa eur
python -m cripto bitcoin --umbral 3 --mayor 100000 --vigilar 300
export COINGECKO_API_KEY=...   # opcional (clave "demo" gratuita)
```

## Tests
```bash
pytest
```
La API se simula con un servidor local en `127.0.0.1` que sirve fixtures JSON; no se contacta CoinGecko.

## Limitaciones
- Respeta el límite del plan gratuito; para mayor frecuencia hace falta un plan pago.
- No es asesoramiento financiero.
