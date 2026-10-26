# 94 · Intérprete de un lenguaje sencillo: *Calc*

Intérprete completo de un lenguaje minimalista: una calculadora con variables, booleanos, `if … then … else`, funciones definidas por el usuario (con recursión) y funciones matemáticas internas. Está construido con las fases clásicas de un compilador: **lexer → parser → AST → evaluador**.

```
calc> def fact(n) = if n <= 1 then 1 else n * fact(n - 1)
calc> fact(20)
2432902008176640000
calc> r = 3; pi * r ^ 2
28.2743338823
calc> 1 / (r - 3)
error de ejecución en 1:3: división por cero
```

## Qué demuestra

- **Lexer** escrito a mano: números (`1_000`, `2.5e-1`), identificadores, palabras clave, operadores de 1 y 2 caracteres, comentarios `#`, y `;` o salto de línea como separador. Cada token lleva línea y columna.
- **Parser Pratt** (precedencia de operadores) con una gramática documentada en `parser.py`:
  - `^` es asociativo a derecha y liga más que el menos unario: `-2^2 = -4`, `2^3^2 = 512`.
  - Las comparaciones no se encadenan, con un mensaje que sugiere `and`.
- **AST** con dataclasses inmutables.
- **Evaluador** por recorrido del árbol:
  - Booleanos separados de los números.
  - Cortocircuito en `and`/`or`.
  - `/` exacta devuelve un entero.
  - Ámbitos: los parámetros tapan a las globales, que en una función solo se leen.
- **Errores con posición** (`error de sintaxis en 1:4: …`) en las tres fases.
- **Límites de seguridad**: exponente máximo, tamaño de entero, profundidad de recursión (200), y constantes y funciones internas protegidas. Nunca se usa `eval` de Python.

## Arquitectura

```
calc/
├── lexer.py      # tokenizar → [Token(tipo, valor, linea, col)]
├── ast.py        # nodos: Numero, Booleano, Variable, Unario, Binario, Si, Llamada, Asignacion, DefFuncion
├── parser.py     # Parser Pratt → Programa
├── evaluador.py  # Interprete (globales, funciones, internas, límites), formatear
├── errores.py    # ErrorLexico, ErrorSintaxis, ErrorEjecucion (con línea:col)
└── cli.py        # REPL (:vars, :funcs, :salir), archivo o -e
ejemplos/factorial.calc
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m calc                              # REPL
python -m calc ejemplos/factorial.calc
python -m calc -e "if 2 > 1 then sqrt(2) else 0"
```

## Tests

```bash
pytest
```

Cubren el lexer, la forma del AST y la precedencia, una tabla de evaluaciones, el ámbito y la recursión, el cortocircuito, 13 errores de ejecución, los errores de sintaxis con posición exacta, el REPL (con entrada simulada) y la CLI.

## Limitaciones

- Es un intérprete de árbol: es simple y claro, pero lento comparado con un bytecode.
- No hay cadenas, listas, bucles ni asignación dentro de funciones: el lenguaje es puramente de expresiones, a propósito.
- La recursión usa la pila de Python; el límite de 200 niveles evita el `RecursionError`.
- Los flotantes son IEEE 754 (`0.1 + 0.2` se muestra como `0.3` porque se formatea con 12 cifras).
