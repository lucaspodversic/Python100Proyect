# 45 · Encriptador / desencriptador de archivos

Utilidad para cifrar archivos de cualquier tamaño con **AES-256-GCM**.

## Qué demuestra
- Cripto real con `cryptography`: **scrypt** (sal aleatoria) + **AES-256-GCM**.
- Cifrado **por bloques (streaming)** de 64 KiB: no carga el archivo entero en memoria.
- Construcción *STREAM*: nonce = prefijo aleatorio | contador | bandera final,
  así se detectan bloques **alterados, reordenados o truncados**.
- Descifrado a un temporal que sólo se publica si todo verificó (nunca queda
  texto plano no autenticado).

## Arquitectura
```
cifrador/
  nucleo.py  # cifrar_flujo / descifrar_flujo / cifrar_archivo / descifrar_archivo
  cli.py     # cifrar | descifrar
```
Formato: `"AESF" | versión | log2(n) | sal(16) | prefijo_nonce(7) | bloques(datos+tag16)`.

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
python -m cifrador cifrar informe.pdf          # genera informe.pdf.aesf
python -m cifrador descifrar informe.pdf.aesf  # recupera informe.pdf
```
`CIFRADOR_CLAVE` permite pasar la contraseña por entorno (sólo automatización).

## Tests
```bash
pytest
```

## Limitaciones
- Proyecto educativo; para uso profesional considerá `age` o GPG.
- No borra de forma segura el original (en SSD no es fiable hacerlo).
