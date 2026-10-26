# 56 · Ahorcado

El juego del ahorcado en consola, con arte ASCII de 7 etapas y categorías.

## Qué demuestra
- Lógica pura (`Partida`) sin E/S → fácil de testear.
- Manejo correcto del español: las tildes y la diéresis no cuentan
  (`u` descubre `ü`), pero la **ñ** es una letra propia.
- Arriesgar la palabra completa (un error suma un fallo).
- Entrada, salida y azar inyectables.

## Arquitectura
```
ahorcado/
  palabras.py  # PALABRAS por categoría, ETAPAS ASCII
  logica.py    # Partida, Resultado, normalizar
  consola.py   # bucle de juego y CLI
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m ahorcado
python -m ahorcado -c programación
```
Código de salida 0 si ganás, 1 si perdés.

## Tests
```bash
pytest
```

## Limitaciones
- Banco de palabras pequeño embebido; se puede extender en `palabras.py`.
