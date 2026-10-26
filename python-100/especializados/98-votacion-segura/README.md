# 98 · Backend de votación electrónica segura

API (FastAPI) de una elección con **anonimato** mediante firmas ciegas RSA,
**integridad** mediante una urna encadenada por hash, **un voto por persona**
mediante tokens de un solo uso y **auditoría pública** verificable.

> Proyecto didáctico. Una elección real requiere además verificación
> independiente, auditorías externas, canal anónimo real, resistencia a la
> coerción y un marco legal. Ver *Limitaciones*.

## Qué demuestra

| Propiedad | Mecanismo |
|-----------|-----------|
| Anonimato | Firma ciega de Chaum: la autoridad firma `m·r^e` sin ver `m`; el voto se deposita por otro canal sin identidad. |
| Un voto por persona | Token aleatorio de 192 bits por votante, guardado como SHA-256, marcado *usado* al emitir la firma (bajo lock). |
| Una firma, un voto | Número de serie de 256 bits dentro del mensaje firmado; columna `UNIQUE` en la urna. |
| No alteración del voto | El mensaje firmado incluye elección + serie + opción: cambiar cualquier campo invalida la firma. |
| Integridad de la urna | Cada bloque guarda el hash del anterior; la *cabeza* resume toda la urna. |
| Auditabilidad | `GET /auditoria`: cadena completa, recomputación de hashes, verificación de cada firma, votos ≤ firmas emitidas. |

## Arquitectura

```
votacion/
├── cripto.py    # FDH (SHA-256 expandido), Autoridad (firma cegada), cegar/descegar/verificar
├── urna.py      # Bloque, Urna (SQLite + lock), verificar_cadena
├── servicio.py  # Eleccion: padrón, estados, firmar, votar, resultados, auditar
├── cliente.py   # Votante: lado cliente (serie, r secreto, descegar y verificar)
└── api.py       # create_app(admin_token, …): endpoints y manejo de errores
```

Flujo:

```
Votante                         Autoridad (/firmar)               Urna (/votar, canal anónimo)
serie, opción, r
m = FDH(eleccion|serie|opción)
m' = m·r^e  ── token, m' ──▶   valida y quema el token
                ◀── s' ──────   s' = m'^d
s = s'·r⁻¹ ; verifica s
            ───────────── serie, opción, s ─────────────────▶  verifica s, serie única,
                                                               agrega bloque → recibo (hash)
```

## Instalación y uso

```bash
pip install -e '.[server]'
export VOTACION_ADMIN_TOKEN="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
python -m votacion                       # http://127.0.0.1:8000/docs
```

Ejemplo con el cliente en Python:

```python
from votacion.cliente import Votante
from votacion.cripto import ClavePublica
# info = GET /eleccion  →  pub = ClavePublica(int(info["clave_publica"]["n"], 16), info["clave_publica"]["e"])
v = Votante(pub, "eleccion-2026", "A")
# POST /eleccion/firmar {"token": TOKEN, "cegado": format(v.cegado(), "x")}
# POST /eleccion/votar  v.papeleta(int(resp["firma_cegada"], 16))
```

Verificá la **huella** de la clave pública por un canal independiente: una
autoridad que use claves distintas para cada votante podría distinguirlos.

## Tests

```bash
pip install -e '.[dev]' && python -m pytest
```

25 tests deterministas y offline (SQLite en memoria, clave de 1024 bits por
velocidad): aritmética RSA con el ejemplo de libro (n = 3233), ciclo
cegar/firmar/descegar, firmas inválidas, token de un solo uso, doble depósito,
cambio de opción, firma de otra elección, estados, anonimato en la base,
detección de manipulación/borrado/relleno en la auditoría, persistencia, y
la API completa (auth admin, validación, códigos 401/403/409/422).

## Limitaciones

- **Canal anónimo no incluido**: si `/votar` se llama desde la misma IP y
  segundos después de `/firmar`, se puede re-vincular por tiempo/IP. Hace
  falta Tor/mixnet y que el votante espere un tiempo aleatorio.
- **Sin resistencia a la coerción**: el votante puede demostrar su voto
  (serie + recibo), lo que permite comprarlo. Sistemas como Helios/Belenios
  usan cifrado homomórfico y re-voto para mitigarlo.
- La autoridad es única: si emite firmas a tokens inexistentes, la auditoría
  solo lo detecta si hay **más votos que firmas registradas**. Se puede
  mitigar con umbral (varias autoridades) y padrón público.
- RSA "de libro" + FDH sin el formato exacto de RFC 9474; no usar la clave
  para nada más que esta elección.
- Clave privada en memoria del proceso (en producción: HSM).
- uvicorn es extra opcional; los tests no levantan servidor.
