# 44 · Generador de contraseñas seguras

CLI para crear contraseñas robustas y personalizables, y frases de contraseña.

## Qué demuestra
- Uso de `secrets` (CSPRNG del sistema), nunca `random`.
- Garantía de al menos un carácter por cada clase habilitada + mezcla final.
- Cálculo de entropía teórica (`largo × log2(alfabeto)`) y clasificación.

## Arquitectura
```
genpass/
  nucleo.py  # Opciones, generar, generar_frase, entropia_bits, fortaleza
  cli.py     # argparse
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
python -m genpass -l 24 -n 5 --entropia
python -m genpass --sin-simbolos --sin-ambiguos -l 12
python -m genpass --frase 6
```

## Tests
```bash
pytest
```

## Limitaciones
- La lista de palabras de frases es corta (~60): para máxima entropía usá
  más palabras o una lista diceware completa.
