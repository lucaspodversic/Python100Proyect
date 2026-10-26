"""App FastAPI del chat.

- WebSocket:  /ws/{sala}?usuario=NOMBRE
- REST:       GET /salas, GET /salas/{sala}/usuarios
- HTML:       GET /  (cliente mínimo en el navegador)

Protocolo (JSON):
  cliente -> servidor: {"texto": "hola"}
  servidor -> cliente: {"tipo": "historial"|"mensaje"|"sistema"|"error", ...}
"""
from __future__ import annotations

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Toda la lógica de salas vive en salas.py; acá solo se traduce el protocolo.
from chat.salas import PATRON_NOMBRE, GestorSalas

# Cliente HTML embebido para probar el chat sin instalar nada más. Se sirve
# como string para no depender de archivos estáticos.
HTML = """<!doctype html><html lang="es"><meta charset="utf-8"><title>Chat</title>
<body><input id="sala" value="general"> <input id="usuario" placeholder="tu nombre">
<button onclick="entrar()">Entrar</button><ul id="log"></ul>
<input id="texto"><button onclick="enviar()">Enviar</button>
<script>
// Cliente mínimo: abre el WebSocket y muestra lo que llega (textContent evita XSS)
let ws;
function log(t){const li=document.createElement('li');li.textContent=t;document.getElementById('log').appendChild(li);}
function entrar(){
  const s=encodeURIComponent(document.getElementById('sala').value);
  const u=encodeURIComponent(document.getElementById('usuario').value);
  ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/${s}?usuario=${u}`);
  ws.onmessage=e=>{const m=JSON.parse(e.data);
    if(m.tipo==='historial') m.mensajes.forEach(x=>log(`${x.usuario}: ${x.texto}`));
    else if(m.tipo==='mensaje') log(`${m.usuario}: ${m.texto}`); else log(`* ${m.texto}`);};
}
function enviar(){ws.send(JSON.stringify({texto:document.getElementById('texto').value}));}
</script></body></html>"""


def crear_app() -> FastAPI:
    """Crea la app con su propio gestor de salas (aislado por instancia)."""
    app = FastAPI(title="Chat en tiempo real")
    gestor = GestorSalas()
    # app.state permite acceder al gestor desde fuera (inspección o tests).
    app.state.gestor = gestor

    @app.get("/", response_class=HTMLResponse)
    def inicio() -> str:
        return HTML

    @app.get("/salas")
    def salas():
        # sorted() para que el listado tenga un orden estable (alfabético).
        return [{"sala": n, "conectados": len(s.conexiones)} for n, s in sorted(gestor.salas.items())]

    @app.get("/salas/{sala}/usuarios")
    def usuarios(sala: str):
        return gestor.usuarios(sala)

    # El usuario llega como query string (?usuario=...) porque la API de
    # WebSocket del navegador no permite mandar headers personalizados.
    @app.websocket("/ws/{sala}")
    async def ws_chat(ws: WebSocket, sala: str, usuario: str = ""):
        # Validación previa a aceptar: código 1008 = violación de política
        if not PATRON_NOMBRE.match(sala) or not PATRON_NOMBRE.match(usuario):
            await ws.close(code=1008)
            return
        # Para poder explicar el motivo hay que aceptar primero (si no, el cliente
        # solo vería el cierre sin mensaje) y luego cerrar.
        if usuario in gestor.usuarios(sala):
            await ws.accept()
            await ws.send_json({"tipo": "error", "texto": "Ese nombre ya está en uso en la sala"})
            await ws.close(code=1008)
            return
        await gestor.conectar(ws, sala, usuario)
        try:
            # Bucle de recepción: corre hasta que el cliente se desconecta, momento en
            # que receive_text lanza WebSocketDisconnect.
            while True:
                crudo = await ws.receive_text()
                try:
                    # Se recibe como texto y se parsea a mano para poder responder un error
                    # amable en lugar de cortar la conexión si llega algo que no es JSON.
                    datos = json.loads(crudo)
                except json.JSONDecodeError:
                    # None hace que construir_mensaje devuelva "Formato inválido".
                    datos = None
                msg = gestor.construir_mensaje(usuario, datos)
                if isinstance(msg, str):
                    # Error solo para quien envió, no se difunde
                    await ws.send_json({"tipo": "error", "texto": msg})
                else:
                    # Mensaje válido: se guarda en el historial y se manda a toda la sala
                    # (incluido el emisor, que así confirma que su mensaje salió).
                    await gestor.difundir(sala, msg)
        # Desconexión normal (cerrar pestaña, red caída): se avisa al resto.
        except WebSocketDisconnect:
            await gestor.desconectar(ws, sala)

    return app


app = crear_app()
