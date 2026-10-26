# 81 · Calculadora científica (Tkinter)

Calculadora de escritorio con **Tkinter**. Evalúa expresiones completas (`2^10 + sqrt(16)`), trabaja en grados o radianes y tiene memoria e historial.

## Qué demuestra

- **Evaluador seguro sin `eval`**:
  - La expresión se convierte en un árbol con `ast.parse` y se recorre admitiendo solo números, operadores, constantes (`pi`, `e`, `tau`, `ans`) y una lista blanca de funciones.
  - Entradas como `__import__('os').system(...)` se rechazan.
- **Protección ante abusos**: el exponente está limitado (`9**99999` no cuelga la app), el factorial también (máx. 1000) y la expresión no puede superar 500 caracteres.
- **Errores amigables**: división por cero, errores de dominio (`sqrt(-1)`) y resultados no finitos se muestran como `Error: …` sin cerrar la app.
- **Separación lógica / vista**: `motor.py` no importa Tkinter y se testea sin pantalla. `gui.py` solo crea la ventana dentro de `main()`.
- Funciones: `sin cos tan asin acos atan sqrt cbrt ln log log2 exp abs fact round`. También acepta `^`, `×`, `÷` y `π`.
- **Memoria** (MC, M+, M-, MR) e **historial**: con doble clic recuperás un resultado anterior.

## Arquitectura

```
calc/
├── motor.py     # Calculadora (evaluador AST, modo DEG/RAD, memoria, historial) + formatear()
├── gui.py       # AppCalculadora (ttk.Frame) y main()
└── __main__.py  # python -m calc
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m calc
```

En Linux puede hacer falta instalar Tk aparte: `sudo apt install python3-tk`. Podés escribir la expresión con el teclado y pulsar Enter.

## Tests

```bash
pytest
```

- `test_motor.py` prueba la lógica, la seguridad y los errores. No necesita pantalla.
- `test_gui.py` incluye un test de humo que crea la ventana. Si no hay `DISPLAY` (por ejemplo, en CI sin Xvfb), se **omite** automáticamente. Para correrlo en un servidor: `xvfb-run pytest`.

## Limitaciones

- Trabaja con `float`, así que hereda la precisión de doble precisión (unos 15 dígitos). Para precisión arbitraria habría que usar `decimal` o `mpmath`.
- No tiene números complejos ni gráficas de funciones.
