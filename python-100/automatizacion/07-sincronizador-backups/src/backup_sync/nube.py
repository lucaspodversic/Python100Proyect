"""Adaptadores de nube: AWS S3 y Google Drive.

Ambos reciben el *cliente* ya construido (inyección de dependencias), así
los tests usan clientes falsos y no se necesita red ni credenciales. Para
crear clientes reales ver ``crear_cliente_s3`` / ``crear_servicio_drive``.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class S3Almacenamiento:
    """Backend S3 usando la API de ``boto3.client('s3')``."""

    # ``Any`` a propósito: no queremos importar boto3 sólo para el tipo; basta con que el objeto
    # tenga los métodos usados (put_object, get_object, delete_object, list_objects_v2).
    cliente: Any
    bucket: str
    prefijo: str = ""  # carpeta lógica dentro del bucket

    def _k(self, clave: str) -> str:
        # "laptop" o "laptop/" → "laptop/clave": se normaliza la barra final para no duplicarla.
        return f"{self.prefijo.rstrip('/')}/{clave}" if self.prefijo else clave

    def listar(self, prefijo: str = "") -> list[str]:
        """Pagina ``list_objects_v2`` (devuelve hasta 1000 claves por página)."""
        claves: list[str] = []
        kwargs: dict[str, Any] = {"Bucket": self.bucket, "Prefix": self._k(prefijo)}
        while True:
            r = self.cliente.list_objects_v2(**kwargs)
            # Largo del prefijo lógico: se recorta para devolver claves relativas al backend.
            base = len(self._k(""))
            claves += [o["Key"][base:] for o in r.get("Contents", [])]
            # S3 devuelve como máximo 1000 claves por respuesta; con IsTruncated hay que seguir
            # pidiendo con el ContinuationToken. Sin este bucle, backups grandes quedarían incompletos.
            if not r.get("IsTruncated"):
                return sorted(claves)
            kwargs["ContinuationToken"] = r["NextContinuationToken"]

    def subir(self, clave: str, datos: bytes) -> None:
        # Cifrado del lado del servidor activado por defecto.
        self.cliente.put_object(Bucket=self.bucket, Key=self._k(clave), Body=datos, ServerSideEncryption="AES256")

    def descargar(self, clave: str) -> bytes:
        # "Body" es un stream (StreamingBody): se lee completo a bytes.
        return self.cliente.get_object(Bucket=self.bucket, Key=self._k(clave))["Body"].read()

    def borrar(self, clave: str) -> None:
        self.cliente.delete_object(Bucket=self.bucket, Key=self._k(clave))

    def existe(self, clave: str) -> bool:
        # Se usa listar con la clave como prefijo (no head_object) para que el fake no necesite más API;
        # se compara igualdad exacta porque el prefijo también devuelve "clave-otra".
        return clave in self.listar(clave)


def crear_cliente_s3() -> Any:  # pragma: no cover - requiere boto3 y credenciales
    """Crea un cliente real; las credenciales salen de la cadena estándar de AWS."""
    import boto3

    return boto3.client("s3")


@dataclass
class DriveAlmacenamiento:
    """Backend Google Drive (API v3) dentro de una carpeta.

    Drive no tiene claves jerárquicas: guardamos la clave completa como
    nombre del archivo dentro de ``carpeta_id`` y cacheamos nombre -> id.
    """

    servicio: Any
    carpeta_id: str
    # Convierte bytes en el "media body" que espera la API. Inyectable para
    # tests (por defecto usa MediaIoBaseUpload de googleapiclient).
    fabrica_media: Callable[[bytes], Any] | None = None
    # Caché nombre → fileId: Drive opera por ID, no por ruta.
    _ids: dict[str, str] = field(default_factory=dict)

    def _media(self, datos: bytes) -> Any:
        # En tests se inyecta una fábrica trivial (bytes → bytes) y no hace falta googleapiclient.
        if self.fabrica_media is not None:
            return self.fabrica_media(datos)
        from googleapiclient.http import MediaIoBaseUpload  # pragma: no cover - dependencia opcional

        return MediaIoBaseUpload(io.BytesIO(datos), mimetype="application/octet-stream")  # pragma: no cover

    def _refrescar(self) -> None:
        # Se reconstruye la caché desde cero: si alguien borró archivos en Drive, no quedan IDs viejos.
        self._ids.clear()
        token = None
        while True:
            r = self.servicio.files().list(
                # Sólo archivos de nuestra carpeta y que no estén en la papelera.
                q=f"'{self.carpeta_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name)", pageToken=token,
            ).execute()
            self._ids.update({f["name"]: f["id"] for f in r.get("files", [])})
            # Paginación de Drive: sin nextPageToken se llegó a la última página.
            token = r.get("nextPageToken")
            if not token:
                return

    def listar(self, prefijo: str = "") -> list[str]:
        self._refrescar()
        return sorted(n for n in self._ids if n.startswith(prefijo))

    def subir(self, clave: str, datos: bytes) -> None:
        media = self._media(datos)
        if clave not in self._ids:
            self._refrescar()  # puede existir aunque no esté en caché
        # Si el archivo ya existe se ACTUALIZA (mismo fileId); Drive permite nombres repetidos,
        # así que crear de nuevo produciría duplicados.
        if clave in self._ids:
            self.servicio.files().update(fileId=self._ids[clave], media_body=media).execute()
        else:
            f = self.servicio.files().create(body={"name": clave, "parents": [self.carpeta_id]},
                                             media_body=media, fields="id").execute()
            self._ids[clave] = f["id"]

    def descargar(self, clave: str) -> bytes:
        # Caché fría (p. ej. otra instancia): se refresca antes de buscar el ID.
        if clave not in self._ids:
            self._refrescar()
        return bytes(self.servicio.files().get_media(fileId=self._ids[clave]).execute())

    def borrar(self, clave: str) -> None:
        if clave not in self._ids:
            self._refrescar()
        # Borrar algo inexistente no falla (idempotente, como en los otros backends).
        if clave in self._ids:
            self.servicio.files().delete(fileId=self._ids.pop(clave)).execute()

    def existe(self, clave: str) -> bool:
        return clave in self.listar(clave)


def crear_servicio_drive(credenciales_json: str) -> Any:  # pragma: no cover
    """Servicio Drive con una cuenta de servicio (archivo JSON de Google Cloud)."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    cred = service_account.Credentials.from_service_account_file(
        # Scope "drive.file": la cuenta de servicio sólo ve los archivos que ella misma creó
        # (mínimo privilegio), no todo el Drive.
        credenciales_json, scopes=["https://www.googleapis.com/auth/drive.file"])
    return build("drive", "v3", credentials=cred)
