# 41 · Comprobador de contraseñas comprometidas

CLI que verifica si una contraseña aparece en filtraciones públicas usando la API
**Pwned Passwords** de Have I Been Pwned (HIBP).

## Qué demuestra
- Uso correcto del modelo **k-anonymity**: sólo se envían los 5 primeros caracteres
  del SHA-1; la contraseña y el hash completo nunca salen de tu máquina.
- Diseño con **inyección de dependencias** (`Protocol`) para testear sin red.
- Manejo del encabezado `Add-Padding` (entradas de relleno con conteo 0).

## Arquitectura
```
pwncheck/
  nucleo.py        # hash, división prefijo/sufijo, búsqueda (lógica pura)
  cliente_http.py  # cliente HTTPS real (urllib, User-Agent honesto)
  cli.py           # argparse + getpass, códigos de salida 0/1/2
```

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
python -m pwncheck                 # pide la contraseña sin eco
cat lista.txt | python -m pwncheck --stdin
```
Códigos de salida: `0` ninguna comprometida, `1` alguna comprometida, `2` error.

## Tests
```bash
pytest
```
Los tests usan un cliente falso: no se hace ningún pedido a internet.

## Limitaciones
- Requiere conexión a `api.pwnedpasswords.com` en uso real.
- Que una contraseña "no aparezca" no garantiza que sea segura.
