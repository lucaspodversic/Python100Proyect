# 07 · Sincronizador de backups a la nube

Respalda automáticamente carpetas críticas en **AWS S3**, **Google Drive** o una **carpeta** (NAS/disco externo) de forma **incremental**, con **versionado** y **restauración**.

## Qué demuestra
- Patrón *Strategy/Adapter*: un `Protocol` `Almacenamiento` y backends intercambiables (S3, Drive, carpeta, memoria).
- Sincronización incremental basada en un **manifiesto de hashes SHA-256** guardado en el destino: sólo se suben archivos nuevos o modificados, sin descargar nada para comparar.
- Versionado (`_versiones/<sello>/...`), modo espejo opcional, exclusiones glob, *dry-run*.
- Robustez: escrituras atómicas en carpeta, protección contra *path traversal*, manifiesto escrito al final (reintentable).
- Clientes de nube inyectados → tests sin red ni credenciales.

## Arquitectura
```
src/backup_sync/
├── almacenamiento.py  # Almacenamiento (Protocol), MemoriaAlmacenamiento, CarpetaAlmacenamiento
├── nube.py            # S3Almacenamiento (boto3), DriveAlmacenamiento (Drive API v3)
├── sincronizador.py   # Sincronizador: planificar / sincronizar / restaurar
└── cli.py
tests/fakes.py         # S3Falso y DriveFalso (imitan las APIs con paginación)
```

## Instalación
```bash
pip install -e ".[dev]"
pip install -e ".[s3]"      # para AWS S3
pip install -e ".[drive]"   # para Google Drive
```

## Uso
```bash
backup-sync ~/Documentos --carpeta /mnt/nas/backup --dry-run
backup-sync ~/Documentos --s3 mi-bucket --prefijo laptop/ --espejo
backup-sync ~/Documentos --drive <ID_CARPETA> --credenciales cuenta-servicio.json
backup-sync ~/Documentos --carpeta /mnt/nas/backup --restaurar ./recuperado
```
Credenciales de AWS: cadena estándar (`AWS_PROFILE`, `~/.aws/credentials`, rol IAM). Para Drive: cuenta de servicio con la carpeta compartida. Programalo con cron o el Programador de tareas.

## Tests
```bash
pytest
```
Usan almacenamiento en memoria, carpetas temporales y clientes S3/Drive falsos.

## Limitaciones
- Los adaptadores reales de S3 y Drive se validan contra fakes que imitan la API; no se probaron contra las nubes reales en este entorno (sin credenciales).
- Lee cada archivo completo en memoria para subirlo; para archivos de varios GB conviene subida multiparte (`upload_file` de boto3 / subida reanudable de Drive).
- No cifra del lado del cliente (S3 usa cifrado del lado del servidor AES256).
