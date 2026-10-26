# 78 · Mesa de ayuda (sistema de tickets)

Backend de soporte técnico con **FastAPI + SQLAlchemy + SQLite**. Incluye una **máquina de estados** explícita, **SLA** por prioridad, asignación automática balanceada por carga, toma atómica de tickets y notas internas.

## Qué demuestra

- **Máquina de estados declarativa**: un diccionario `TRANSICIONES` mapea cada `(estado, nuevo_estado)` a los roles autorizados. Toda transición se valida y queda en el historial.

  ```
  abierto → en_progreso ⇄ esperando_cliente
                ↓
            resuelto → cerrado
                ↓ (≤ 7 días)
             abierto
  ```

  Cuando el cliente comenta en un ticket que estaba "esperando cliente", pasa solo a "en progreso".
- **SLA** de primera respuesta y de resolución:

  | Prioridad | Primera respuesta | Resolución |
  |---|---|---|
  | urgente | 1 h | 4 h |
  | alta | 4 h | 24 h |
  | media | 8 h | 3 días |
  | baja | 24 h | 7 días |

  Hay un endpoint `/tickets/incumplidos` para supervisión. Si cambia la prioridad, los plazos se recalculan.
- **Asignación balanceada**: cada ticket nuevo va al agente con menos tickets activos.
- **Toma atómica**: `UPDATE … WHERE agente_id IS NULL`. Si varios agentes intentan tomar el mismo ticket a la vez, solo uno lo consigue (hay un test con hilos).
- **Privacidad**:
  - Las notas internas son invisibles para el cliente.
  - Un cliente solo ve sus propios tickets; los ajenos le dan 404.
  - Un agente no puede operar tickets asignados a otro agente.

## Arquitectura

```
app/
├── modelos.py   # Ticket, Comentario (interno), Cambio (historial)
├── servicio.py  # TRANSICIONES, SLA, balanceo, tomar(), comentar()
└── main.py      # rutas; reloj inyectable
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export SOPORTE_ADMIN_PASSWORD="clave-segura"
uvicorn app.main:app --reload
```

El admin promueve usuarios a agentes con `PATCH /usuarios/{id}/rol {"rol": "agente"}`.

## Tests

```bash
pytest
```

## Limitaciones

- El SLA se mide en horas corridas, sin calendario laboral ni feriados, y no se pausa en "esperando cliente".
- No hay notificaciones por email, adjuntos ni plantillas de respuesta.
