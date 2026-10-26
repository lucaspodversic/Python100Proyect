# 88 · Gestor de contraseñas con GUI (Tkinter + cryptography)

Bóveda local de contraseñas cifrada con **AES-256-GCM**, con la clave derivada de una contraseña maestra mediante **scrypt**. La interfaz Tkinter permite buscar, crear, editar y eliminar entradas, generar contraseñas y medir su fortaleza. Además, **el portapapeles se limpia solo** y **la bóveda se bloquea por inactividad**.

## Qué demuestra

- **Criptografía correcta con la librería `cryptography`**:
  - Usa scrypt (N=2¹⁷, r=8, p=1, ~128 MiB) con una sal aleatoria de 16 bytes por bóveda.
  - Usa AES-GCM con un nonce nuevo de 96 bits en cada guardado.
  - La cabecera (formato, versión, parámetros del KDF, sal y nonce) se autentica como **AAD**: si alguien la altera para bajar el costo del KDF, el descifrado falla.
  - Una contraseña errónea y un archivo manipulado dan el mismo error genérico.
  - Los parámetros del KDF se acotan, así que un archivo malicioso no puede pedir 64 GiB de RAM ni parámetros débiles.
- **Archivo**: se escribe de forma atómica (temporal + `fsync` + `os.replace`) con permisos `0600`, y no contiene nada en claro (ni sitios ni usuarios).
- **Portapapeles seguro** (`CopiaSegura`):
  - Se borra a los 20 s, pero **solo si todavía contiene nuestro secreto**: no pisa lo que el usuario haya copiado después.
  - Cada copia nueva invalida el temporizador de la anterior.
  - También se limpia al bloquear y al salir.
- **Bloqueo automático** tras 5 minutos sin teclado ni ratón: la bóveda (y la clave) se descartan de memoria.
- **Generador** con `secrets` (CSPRNG):
  - Garantiza al menos un carácter de cada clase mediante rechazo y reintento, sin sesgo.
  - Tiene una opción para evitar caracteres ambiguos.
- **Otras ayudas**:
  - Medidor de fortaleza orientativo.
  - Detección de contraseñas reutilizadas, sin revelarlas.
  - La búsqueda nunca mira en las contraseñas.
- **Separación lógica / vista**:
  - `cripto.py`, `modelo.py` y `portapapeles.py` no importan Tkinter.
  - El portapapeles y el planificador son interfaces, con versiones falsas para los tests.

## Arquitectura

```
boveda/
├── cripto.py        # ParametrosKdf, Cifrador (scrypt + AES-GCM + AAD), escribir_atomico
├── modelo.py        # Entrada, Boveda (CRUD, cambiar_maestra), generar, fortaleza
├── portapapeles.py  # Portapapeles (Protocol), PortapapelesTk, CopiaSegura, PortapapelesFalso
└── gui.py           # AppBoveda (desbloqueo, lista, diálogo de entrada, auto-bloqueo) y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m boveda                        # usa ~/.boveda-py100.boveda
python -m boveda /ruta/a/otra.boveda
```

Con doble clic sobre una entrada se copia la contraseña.

## Tests

```bash
pytest
```

- Los tests usan scrypt con N=2¹⁰ para ser rápidos; la app usa 2¹⁷.
- Se prueban alteraciones de los datos, del KDF, del nonce y de la versión, además del borrado del portapapeles con un planificador falso.
- El test de humo de la GUI recorre crear → agregar → copiar → bloqueo por inactividad. Se omite si no hay `DISPLAY`.

## Limitaciones

- Python no permite borrar secretos de la memoria de forma fiable: los `str` son inmutables y el recolector decide cuándo liberarlos. Un gestor profesional usa memoria bloqueada.
- Algunos gestores de portapapeles del sistema (historial de KDE o Windows) pueden guardar una copia antes de que la borremos.
- Sin sincronización ni 2FA. Si se olvida la contraseña maestra, no hay recuperación: es intencional.
- El medidor de fortaleza es una heurística. Para una estimación seria se usaría `zxcvbn`.
