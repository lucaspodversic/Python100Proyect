"""Clientes falsos que imitan boto3 (S3) y googleapiclient (Drive) en memoria."""

from __future__ import annotations

import io
import itertools
from typing import Any


class S3Falso:
    """Subconjunto de la API de boto3 S3 con paginación real (MaxKeys chico)."""

    # MaxKeys chico (2, o 1 en el test) obliga a ejercitar la paginación con apenas 3 objetos.
    def __init__(self, max_keys: int = 2) -> None:
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.max_keys = max_keys
        self.llamadas_put: list[dict[str, Any]] = []

    def put_object(self, Bucket: str, Key: str, Body: bytes, **kw: Any) -> None:  # noqa: N803
        self.buckets.setdefault(Bucket, {})[Key] = Body
        # Se guardan los kwargs extra para verificar, p. ej., que se pidió cifrado del lado servidor.
        self.llamadas_put.append({"Key": Key, **kw})

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        return {"Body": io.BytesIO(self.buckets[Bucket][Key])}

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.buckets.get(Bucket, {}).pop(Key, None)

    def list_objects_v2(self, Bucket: str, Prefix: str = "", ContinuationToken: str | None = None) -> dict[str, Any]:  # noqa: N803
        claves = sorted(k for k in self.buckets.get(Bucket, {}) if k.startswith(Prefix))
        # El token es simplemente el índice de inicio como texto (opaco para el cliente, como en S3).
        inicio = int(ContinuationToken or 0)
        pagina = claves[inicio: inicio + self.max_keys]
        r: dict[str, Any] = {"Contents": [{"Key": k} for k in pagina]}
        # Quedan claves después de esta página → respuesta truncada con token de continuación.
        if inicio + self.max_keys < len(claves):
            r.update(IsTruncated=True, NextContinuationToken=str(inicio + self.max_keys))
        return r


class _Req:
    """Imita un request de googleapiclient: se resuelve con execute()."""

    def __init__(self, resultado: Any) -> None:
        self._r = resultado

    def execute(self) -> Any:
        # Resultado diferido: delete() sólo borra cuando se llama a execute(), como la API real.
        return self._r() if callable(self._r) else self._r


class _Files:
    def __init__(self, drive: "DriveFalso") -> None:
        self.d = drive

    def list(self, q: str, fields: str, pageToken: str | None = None) -> _Req:  # noqa: N803
        # Páginas de 2 archivos fijas: con 3 archivos hay 2 páginas y se prueba nextPageToken.
        archivos = [{"id": i, "name": n} for i, (n, _) in sorted(self.d.archivos.items())]
        inicio = int(pageToken or 0)
        r: dict[str, Any] = {"files": archivos[inicio: inicio + 2]}
        if inicio + 2 < len(archivos):
            r["nextPageToken"] = str(inicio + 2)
        return _Req(r)

    def create(self, body: dict[str, Any], media_body: bytes, fields: str) -> _Req:
        # IDs secuenciales "id1", "id2"...: deterministas, a diferencia de los IDs aleatorios de Drive.
        nuevo = f"id{next(self.d.seq)}"
        self.d.archivos[nuevo] = (body["name"], media_body)
        return _Req({"id": nuevo})

    def update(self, fileId: str, media_body: bytes) -> _Req:  # noqa: N803
        nombre = self.d.archivos[fileId][0]
        self.d.archivos[fileId] = (nombre, media_body)
        return _Req({"id": fileId})

    def get_media(self, fileId: str) -> _Req:  # noqa: N803
        return _Req(self.d.archivos[fileId][1])

    def delete(self, fileId: str) -> _Req:  # noqa: N803
        return _Req(lambda: self.d.archivos.pop(fileId))


class DriveFalso:
    def __init__(self) -> None:
        self.archivos: dict[str, tuple[str, bytes]] = {}
        self.seq = itertools.count(1)

    def files(self) -> _Files:
        return _Files(self)
