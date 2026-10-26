"""Cliente de correo: interfaz + adaptador Gmail API v1 + fake en memoria.

``GmailCliente`` recibe el ``service`` de ``googleapiclient.discovery.build``
(inyectado). Usa ``batchModify`` (hasta 1000 ids por llamada) para minimizar
cuota y latencia.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from .modelos import Correo

# gmail.modify permite etiquetar, archivar y mover a la papelera, pero NO borrar para siempre
# (eso requiere el scope completo https://mail.google.com/). Mínimo privilegio.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # NO pide borrado permanente


class ClienteCorreo(Protocol):
    def listar(self, consulta: str, maximo: int) -> list[str]: ...

    def obtener(self, id_: str) -> Correo: ...

    def id_etiqueta(self, nombre: str) -> str: ...

    def modificar(self, ids: list[str], agregar: list[str], quitar: list[str]) -> None: ...

    def papelera(self, id_: str) -> None: ...


@dataclass
class GmailCliente:
    service: Any
    usuario: str = "me"
    _etiquetas: dict[str, str] | None = None

    def listar(self, consulta: str, maximo: int) -> list[str]:
        ids: list[str] = []
        token = None
        # Paginación: se piden páginas de hasta 500 (máximo de la API) sin pasarse del total pedido.
        while len(ids) < maximo:
            r = self.service.users().messages().list(userId=self.usuario, q=consulta, pageToken=token,
                                                     maxResults=min(500, maximo - len(ids))).execute()
            # Una bandeja vacía no trae la clave "messages": de ahí el .get con lista vacía.
            ids += [m["id"] for m in r.get("messages", [])]
            token = r.get("nextPageToken")
            if not token:
                break
        return ids[:maximo]

    def obtener(self, id_: str) -> Correo:
        # format="metadata" trae sólo encabezados (sin cuerpo): mucho más rápido y barato en cuota.
        m = self.service.users().messages().get(userId=self.usuario, id=id_, format="metadata",
                                                metadataHeaders=["From", "Subject", "Date"]).execute()
        # Encabezados normalizados a minúsculas: los servidores mandan "Date", "DATE"...
        h = {x["name"].lower(): x["value"] for x in m["payload"].get("headers", [])}
        try:
            # Fecha "naive" para poder restarla al ``ahora`` naive del motor (se pierde la zona horaria,
            # aceptable para reglas en días).
            fecha = parsedate_to_datetime(h["date"]).replace(tzinfo=None)
        except (KeyError, TypeError, ValueError):
            # Fallback: internalDate está en milisegundos desde epoch (UTC).
            fecha = dt.datetime.fromtimestamp(int(m.get("internalDate", 0)) / 1000, dt.timezone.utc).replace(tzinfo=None)
        partes = m["payload"].get("parts", [])
        return Correo(id=m["id"], remitente=h.get("from", ""), asunto=h.get("subject", ""), fecha=fecha,
                      etiquetas=m.get("labelIds", []), tamano=int(m.get("sizeEstimate", 0)),
                      # Con format="metadata" las partes traen filename: un nombre no vacío indica adjunto.
                      tiene_adjuntos=any(p.get("filename") for p in partes))

    def id_etiqueta(self, nombre: str) -> str:
        """Devuelve el id de una etiqueta, creándola si no existe (las de sistema ya existen)."""
        # Caché perezosa: se lista una sola vez y luego se reutiliza (evita una llamada por correo).
        if self._etiquetas is None:
            r = self.service.users().labels().list(userId=self.usuario).execute()
            self._etiquetas = {e["name"]: e["id"] for e in r.get("labels", [])}
        if nombre not in self._etiquetas:
            nueva = self.service.users().labels().create(userId=self.usuario, body={
                "name": nombre, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).execute()
            self._etiquetas[nombre] = nueva["id"]
        return self._etiquetas[nombre]

    def modificar(self, ids: list[str], agregar: list[str], quitar: list[str]) -> None:
        # Lotes de 1000 ids: 2500 correos → 3 llamadas (1000, 1000, 500).
        for i in range(0, len(ids), 1000):  # límite de batchModify
            self.service.users().messages().batchModify(userId=self.usuario, body={
                "ids": ids[i:i + 1000], "addLabelIds": agregar, "removeLabelIds": quitar}).execute()

    def papelera(self, id_: str) -> None:
        # trash (recuperable 30 días), nunca delete: un error de regla se puede deshacer.
        self.service.users().messages().trash(userId=self.usuario, id=id_).execute()


def crear_servicio(credenciales: str = "credentials.json", token: str = "token.json") -> Any:  # pragma: no cover
    """Flujo OAuth de escritorio (abre el navegador la primera vez y guarda token.json)."""
    import os

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # token.json guarda el refresh token: sólo la primera vez se abre el navegador.
    cred = Credentials.from_authorized_user_file(token, SCOPES) if os.path.exists(token) else None
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            # port=0 elige un puerto libre para el callback local de OAuth.
            cred = InstalledAppFlow.from_client_secrets_file(credenciales, SCOPES).run_local_server(port=0)
        with open(token, "w", encoding="utf-8") as f:
            f.write(cred.to_json())
    return build("gmail", "v1", credentials=cred)


@dataclass
class FakeCliente:
    """Bandeja en memoria para tests y demos."""

    correos: dict[str, Correo] = field(default_factory=dict)
    papelera_ids: list[str] = field(default_factory=list)
    llamadas_modificar: int = 0

    def listar(self, consulta: str, maximo: int) -> list[str]:
        # El fake sólo entiende "in:inbox"; cualquier otra consulta devuelve todo.
        ids = [i for i, c in self.correos.items() if "INBOX" in c.etiquetas or consulta != "in:inbox"]
        return ids[:maximo]

    def obtener(self, id_: str) -> Correo:
        return self.correos[id_]

    def id_etiqueta(self, nombre: str) -> str:
        return nombre  # en el fake el id es el nombre

    def modificar(self, ids: list[str], agregar: list[str], quitar: list[str]) -> None:
        self.llamadas_modificar += 1
        for i in ids:
            c = self.correos[i]
            # Imita Gmail: se quitan etiquetas y se agregan nuevas al final sin duplicar.
            c.etiquetas = [e for e in c.etiquetas if e not in quitar] + [e for e in agregar if e not in c.etiquetas]

    def papelera(self, id_: str) -> None:
        self.papelera_ids.append(id_)
        # En Gmail, mandar a la papelera equivale a agregar TRASH y sacar de INBOX.
        self.modificar([id_], ["TRASH"], ["INBOX"])
