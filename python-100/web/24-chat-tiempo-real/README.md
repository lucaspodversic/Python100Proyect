# 24 · Chat en tiempo real (WebSockets)

## Qué demuestra
Comunicación bidireccional en tiempo real con **WebSockets en FastAPI**:
salas aisladas, difusión a todos los participantes, historial de los últimos
50 mensajes, avisos de entrada/salida, validación de nombres y mensajes, y
manejo de conexiones caídas.

## Arquitectura
```
chat/salas.py -> GestorSalas: conexiones por sala, historial (deque), difusión y validación
chat/app.py   -> crear_app(): WebSocket /ws/{sala}, REST /salas, cliente HTML en /
tests/        -> tests con TestClient.websocket_connect (sin servidor real)
```
Protocolo JSON: el cliente envía `{"texto": "..."}`; el servidor responde con
`{"tipo": "historial" | "mensaje" | "sistema" | "error", ...}`.

## Instalación
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Uso
```bash
uvicorn chat.app:app --reload
# Abrí http://127.0.0.1:8000/ en dos pestañas y entrá con nombres distintos.
```

## Tests
```bash
pytest
```

## Limitaciones
- Estado en memoria de un solo proceso: para escalar a varios workers hace falta un bus (Redis Pub/Sub).
- Sin autenticación real: el nombre de usuario lo elige el cliente.
