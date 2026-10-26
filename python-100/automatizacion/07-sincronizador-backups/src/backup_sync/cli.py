"""CLI::

    backup-sync ~/Documentos --carpeta /mnt/nas/backup
    backup-sync ~/Documentos --s3 mi-bucket --prefijo laptop/ --espejo
    backup-sync ~/Documentos --drive CARPETA_ID --credenciales sa.json
    backup-sync ~/Documentos --carpeta /mnt/nas/backup --restaurar ./recuperado
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .almacenamiento import Almacenamiento, CarpetaAlmacenamiento
from .sincronizador import Sincronizador


def construir_destino(a: argparse.Namespace) -> Almacenamiento:
    # Prioridad de destinos: carpeta → S3 → Drive. Las dependencias de nube se importan sólo
    # si se piden, así la herramienta funciona sin boto3 ni googleapiclient instalados.
    if a.carpeta:
        return CarpetaAlmacenamiento(a.carpeta)
    if a.s3:  # pragma: no cover - requiere boto3
        from .nube import S3Almacenamiento, crear_cliente_s3

        return S3Almacenamiento(crear_cliente_s3(), a.s3, a.prefijo)
    if a.drive:  # pragma: no cover - requiere google-api-python-client
        from .nube import DriveAlmacenamiento, crear_servicio_drive

        return DriveAlmacenamiento(crear_servicio_drive(a.credenciales), a.drive)
    # SystemExit con mensaje: argparse no puede expresar "exactamente uno de estos" con valores.
    raise SystemExit("Indicá un destino: --carpeta, --s3 o --drive")


def main(argv: list[str] | None = None) -> int:
    # RawDescriptionHelpFormatter conserva los saltos de línea de los ejemplos del docstring.
    ap = argparse.ArgumentParser(prog="backup-sync", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origen", type=Path)
    ap.add_argument("--carpeta", type=Path)
    ap.add_argument("--s3")
    ap.add_argument("--prefijo", default="")
    ap.add_argument("--drive")
    ap.add_argument("--credenciales")
    # --espejo borra en el destino lo eliminado localmente (sin él, el backup sólo crece).
    ap.add_argument("--espejo", action="store_true")
    # Por defecto se versiona: antes de pisar o borrar algo remoto se guarda una copia.
    ap.add_argument("--sin-versiones", action="store_true")
    ap.add_argument("--excluir", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restaurar", type=Path)
    a = ap.parse_args(argv)
    s = Sincronizador(a.origen, construir_destino(a), espejo=a.espejo, versionar=not a.sin_versiones)
    # Los patrones del usuario se SUMAN a los por defecto (*.tmp, ~$*, .DS_Store, Thumbs.db).
    s.excluir += a.excluir
    if a.restaurar:
        print(f"Restaurados {s.restaurar(a.restaurar)} archivos en {a.restaurar}")
        return 0
    # Resumen de una línea apto para logs de cron.
    plan = s.sincronizar(dry_run=a.dry_run)
    pref = "[dry-run] " if a.dry_run else ""
    print(f"{pref}nuevos={len(plan.subir)} actualizados={len(plan.actualizar)} "
          f"borrados={len(plan.borrar)} sin_cambios={plan.sin_cambios}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
