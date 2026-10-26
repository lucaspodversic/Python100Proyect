"""Fuentes de publicaciones detrás de una interfaz común (`FuenteFeed`).

- `FuenteArchivo`: lee un JSONL local (demos y tests).
- `FuenteReddit`: búsqueda pública JSON de Reddit.
- `FuenteTwitter`: API v2 de X/Twitter (recent search), token por env X_BEARER_TOKEN.

Los clientes HTTP son inyectables: los tests usan `httpx.MockTransport` con
fixtures y nunca salen a la red. Usá las APIs oficiales respetando sus términos
y límites de uso.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Publicacion:
    id: str
    texto: str
    autor: str
    fecha: datetime
    fuente: str


# Protocol (tipado estructural): cualquier objeto con `nombre` y
# `obtener()` sirve como fuente, sin heredar de nada.
class FuenteFeed(Protocol):
    nombre: str

    def obtener(self, consulta: str) -> list[Publicacion]: ...


class FuenteArchivo:
    """Cada llamada devuelve el siguiente 'lote' (simula publicaciones que van llegando)."""
    nombre = "archivo"

    def __init__(self, ruta: str | Path, tamano_lote: int = 5) -> None:
        self._filas = [json.loads(l) for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip()]
        self._pos, self.tamano_lote = 0, tamano_lote

    def obtener(self, consulta: str) -> list[Publicacion]:
        lote = self._filas[self._pos:self._pos + self.tamano_lote]
        self._pos += len(lote)
        # Filtro simple por subcadena sin distinguir mayúsculas. Ojo: el puntero
        # avanza aunque se filtren filas (como un feed real: lo leído no vuelve).
        c = consulta.lower()
        return [Publicacion(f["id"], f["texto"], f.get("autor", "?"), datetime.fromisoformat(f["fecha"]), self.nombre)
                for f in lote if c in f["texto"].lower()]


class FuenteReddit:
    nombre = "reddit"

    def __init__(self, cliente: httpx.Client | None = None, subreddit: str = "all") -> None:
        # Reddit exige un User-Agent descriptivo
        self._cliente = cliente or httpx.Client(timeout=20, headers={"User-Agent": "monitor-sentimiento/1.0"})
        self.subreddit = subreddit

    def obtener(self, consulta: str) -> list[Publicacion]:
        r = self._cliente.get(f"https://www.reddit.com/r/{self.subreddit}/search.json",
                              params={"q": consulta, "sort": "new", "restrict_sr": "1", "limit": 50})
        r.raise_for_status()
        salida = []
        for hijo in r.json()["data"]["children"]:
            d = hijo["data"]
            # En Reddit se analiza título + cuerpo; el id lleva prefijo de fuente
            # para que no choque con ids de otras redes en la deduplicación.
            texto = f"{d.get('title', '')} {d.get('selftext', '')}".strip()
            salida.append(Publicacion(f"reddit:{d['id']}", texto, d.get("author", "?"),
                                      datetime.fromtimestamp(d["created_utc"], tz=timezone.utc), self.nombre))
        return salida


class FuenteTwitter:
    nombre = "twitter"

    def __init__(self, cliente: httpx.Client | None = None) -> None:
        self._cliente = cliente or httpx.Client(timeout=20)
        self._desde_id: str | None = None   # paginación incremental: solo lo nuevo

    def obtener(self, consulta: str) -> list[Publicacion]:
        token = os.environ.get("X_BEARER_TOKEN")
        if not token:
            raise RuntimeError("Falta X_BEARER_TOKEN")
        # Se excluyen retweets para no contar varias veces la misma opinión.
        params = {"query": f"{consulta} -is:retweet", "max_results": 50, "tweet.fields": "created_at,author_id"}
        if self._desde_id:
            params["since_id"] = self._desde_id
        r = self._cliente.get("https://api.twitter.com/2/tweets/search/recent", params=params,
                              headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        datos = r.json()
        if nuevo := datos.get("meta", {}).get("newest_id"):
            self._desde_id = nuevo
        return [Publicacion(f"tw:{t['id']}", t["text"], t.get("author_id", "?"),
                            # El replace de "Z" mantiene compatibilidad con fromisoformat de Python < 3.11.
                            datetime.fromisoformat(t["created_at"].replace("Z", "+00:00")), self.nombre)
                for t in datos.get("data", [])]
