"""Gestor de salas y conexiones WebSocket.

Cada sala mantiene el conjunto de conexiones activas y un historial acotado
(deque con tamaño máximo) para que quien entra vea los últimos mensajes.
"""
from __future__ import annotations

import re
import time
# deque(maxlen=N) descarta automáticamente lo más viejo: memoria acotada.
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

# Nombres permitidos para salas y usuarios: evita caracteres raros y abusos
# Letras (con acentos y ñ), dígitos, "_" y "-"; entre 1 y 24 caracteres.
# Al excluir "<", ">", espacios, etc. se evita inyectar HTML en los avisos.
PATRON_NOMBRE = re.compile(r"^[A-Za-z0-9_\-áéíóúñÁÉÍÓÚÑ]{1,24}$")
# Límites para que un cliente no pueda saturar memoria ni ancho de banda.
LARGO_MAX_MENSAJE = 1000
TAMANO_HISTORIAL = 50


@dataclass
class Sala:
    """Estado de una sala: conexiones (websocket -> usuario) e historial."""
    nombre: str
    # default_factory: cada Sala tiene su propio dict (no uno compartido).
    conexiones: dict[WebSocket, str] = field(default_factory=dict)
    historial: deque = field(default_factory=lambda: deque(maxlen=TAMANO_HISTORIAL))


# Estado en memoria de un solo proceso: con varios workers o servidores
# haría falta un bus compartido (p. ej. Redis pub/sub). Ver README.
class GestorSalas:
    """Registra conexiones y difunde mensajes dentro de cada sala."""

    def __init__(self) -> None:
        self.salas: dict[str, Sala] = {}

    def usuarios(self, sala: str) -> list[str]:
        """Lista ordenada de usuarios conectados a una sala."""
        s = self.salas.get(sala)
        # Sala inexistente => lista vacía (no error): simplifica a quien consulta.
        return sorted(s.conexiones.values()) if s else []

    async def conectar(self, ws: WebSocket, sala: str, usuario: str) -> None:
        """Acepta la conexión, envía el historial y avisa a la sala."""
        await ws.accept()
        # setdefault: crea la sala la primera vez que alguien entra.
        s = self.salas.setdefault(sala, Sala(sala))
        s.conexiones[ws] = usuario
        # El recién llegado recibe primero el historial y después el aviso de
        # entrada (que le llega también a él, porque ya está en conexiones).
        await ws.send_json({"tipo": "historial", "mensajes": list(s.historial)})
        await self.difundir(sala, {"tipo": "sistema", "texto": f"{usuario} entró a la sala",
                                   # guardar=False: los avisos de sistema no ensucian el historial.
                                   "usuarios": self.usuarios(sala)}, guardar=False)

    async def desconectar(self, ws: WebSocket, sala: str) -> None:
        """Quita la conexión; si la sala queda vacía la elimina."""
        s = self.salas.get(sala)
        if not s or ws not in s.conexiones:
            return
        # pop devuelve el nombre asociado a la conexión que se va.
        usuario = s.conexiones.pop(ws)
        if s.conexiones:
            await self.difundir(sala, {"tipo": "sistema", "texto": f"{usuario} salió de la sala",
                                       "usuarios": self.usuarios(sala)}, guardar=False)
        # Una sala vacía y sin historial se elimina; si tiene historial se conserva
        # para que quien vuelva a entrar lo vea.
        elif not s.historial:
            del self.salas[sala]

    async def difundir(self, sala: str, mensaje: dict[str, Any], guardar: bool = True) -> None:
        """Envía un mensaje a todas las conexiones de la sala."""
        s = self.salas.get(sala)
        if not s:
            return
        if guardar:
            s.historial.append(mensaje)
        # No se modifica el dict mientras se itera: se juntan las conexiones caídas
        # y se quitan al final. list(...) toma una copia por la misma razón.
        caidas: list[WebSocket] = []
        for ws in list(s.conexiones):
            try:
                await ws.send_json(mensaje)
            except Exception:  # conexión rota: se limpia después
                caidas.append(ws)
        for ws in caidas:
            s.conexiones.pop(ws, None)

    @staticmethod
    def construir_mensaje(usuario: str, datos: Any) -> dict[str, Any] | str:
        """Valida lo recibido del cliente. Devuelve el mensaje o un texto de error."""
        # Cualquier cosa que no sea {"texto": str} (lista, número, null) es inválida.
        if not isinstance(datos, dict) or not isinstance(datos.get("texto"), str):
            return "Formato inválido: se espera {\"texto\": \"...\"}"
        # Se recortan espacios: "   " cuenta como mensaje vacío.
        texto = datos["texto"].strip()
        if not texto:
            return "Mensaje vacío"
        if len(texto) > LARGO_MAX_MENSAJE:
            return f"Mensaje demasiado largo (máx. {LARGO_MAX_MENSAJE})"
        # El usuario lo pone el servidor (no el cliente): nadie puede hacerse pasar
        # por otro. ts = epoch con milisegundos.
        return {"tipo": "mensaje", "usuario": usuario, "texto": texto, "ts": round(time.time(), 3)}
