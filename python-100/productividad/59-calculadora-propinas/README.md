# 59 · Calculadora de propinas

Calcula la propina y divide la cuenta entre varias personas **sin perder centavos**.

## Qué demuestra
- Aritmética monetaria con `decimal.Decimal` y redondeo comercial (`ROUND_HALF_UP`).
- Reparto exacto: `$100 / 3 = 33,34 + 33,33 + 33,33` (la suma siempre cierra).
- Opciones reales: impuesto aparte, propina antes/después de impuestos,
  redondear el total hacia arriba (la diferencia va a la propina y se informa el % efectivo).
- Acepta coma decimal (`12,50`) y muestra formato `$1.234,50`.

## Arquitectura
```
propinas/
  calculo.py  # Cuenta, Resultado, calcular, repartir
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m propinas 85,40 -p 15 -n 2
python -m propinas 1234 -p 10 -n 4 --redondear 100
python -m propinas 100 --impuesto 21 --sobre-impuesto
```

## Tests
```bash
pytest
```

## Limitaciones
- Una sola moneda y formato rioplatense en la salida.
