# 42 · Gestor de contraseñas seguro

Bóveda local de credenciales cifrada con una contraseña maestra.

## Qué demuestra
- Criptografía **real y auditada** con la librería `cryptography`:
  - **scrypt** (KDF memoria-dura) con sal aleatoria de 16 bytes por guardado.
  - **AES-256-GCM** con nonce aleatorio de 12 bytes; el encabezado va como AAD,
    así que cualquier alteración del archivo se detecta.
- Escritura **atómica** (archivo temporal + `os.replace`) y permisos `0600`.
- CLI que nunca muestra contraseñas en listados.

## Arquitectura
```
boveda/
  cripto.py   # derivar_clave / cifrar / descifrar (formato BVD1)
  boveda.py   # Entrada, Boveda (crear/abrir/guardar/agregar/buscar/cambiar_maestra)
  cli.py      # init | add | get | list | rm
```
Formato: `MAGIC "BVD1" | versión | log2(n) | sal(16) | nonce(12) | cifrado+tag`.

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
python -m boveda init
python -m boveda add github lucas --generar 24
python -m boveda list
python -m boveda get github
```
`--archivo` cambia la ruta (por defecto `~/.boveda.bin`). La variable
`BOVEDA_MAESTRA` evita el prompt (sólo para automatización; menos seguro).

## Tests
```bash
pytest
```
Los tests usan un costo de scrypt reducido (n=2^10) sólo para velocidad.

## Limitaciones
- Proyecto educativo, sin auditoría externa. Para uso diario preferí Bitwarden/KeePassXC.
- La contraseña descifrada vive en memoria de Python (no se puede borrar de forma fiable).
