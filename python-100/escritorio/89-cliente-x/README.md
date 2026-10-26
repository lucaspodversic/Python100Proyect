# 89 · Cliente de X (Twitter) de escritorio

Cliente Tkinter que usa la **API oficial v2 de X** para:

- ver tus publicaciones;
- buscar publicaciones recientes;
- publicar, con un contador de caracteres ponderado como el de X y la opción de dividir un texto largo en un **hilo numerado**.

## Qué demuestra

- **Interfaz + implementaciones**:
  - El controlador y la GUI solo conocen `ServicioX` (un `Protocol`).
  - `ClienteXAPI` habla con `https://api.x.com/2`.
  - `ServicioFalso` funciona en memoria y sirve para tests y para el modo `--demo`.
- **Token fuera del código**:
  - Se lee de `X_USER_ACCESS_TOKEN` (para publicar) o de `X_BEARER_TOKEN` (solo lectura).
  - `repr()` del cliente nunca lo muestra.
- **Manejo de errores de la API**:
  - 401 y 403 se traducen a mensajes claros.
  - 429 calcula los segundos de espera a partir de `x-rate-limit-reset`.
  - Los errores de red se envuelven.
- **Paginación** con `next_token` y el botón «Cargar más».
- **Longitud ponderada** al estilo twitter-text:
  - Las URL cuentan 23.
  - CJK y emojis cuentan 2.
  - El texto se normaliza a NFC.
- **Hilos**: el texto se divide sin cortar palabras, y cada parte se publica como respuesta a la anterior.
- **GUI sin congelarse**: la red corre en un hilo y el resultado vuelve a Tk por una cola revisada con `after` (Tkinter no es thread-safe). El ejecutor se inyecta, y en los tests es síncrono.

## Arquitectura

```
clientex/
├── api.py      # ServicioX (Protocol), ClienteXAPI (httpx), ServicioFalso, errores
├── texto.py    # longitud ponderada, validar, dividir_en_hilo
├── control.py  # Controlador (estado + orquestación, sin Tkinter), ejecutor síncrono
└── gui.py      # AppX, EjecutorHilo y main()
```

## Instalación y uso

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m clientex --demo                 # sin red ni token
export X_USER_ACCESS_TOKEN="..."          # token OAuth 2.0 de usuario (tweet.read users.read tweet.write)
python -m clientex
```

- Los tokens se obtienen en el portal de desarrolladores de X (developer.x.com).
- Un *Bearer token* de aplicación (`X_BEARER_TOKEN`) permite leer, pero **no publicar**.
- No subas tokens al repositorio: usá variables de entorno o un gestor de secretos.

## Tests

```bash
pytest
```

**Ningún test usa la red.**

- El cliente real se prueba con `httpx.MockTransport`, que verifica la ruta, los parámetros, el cuerpo JSON y la cabecera `Authorization`.
- El controlador se prueba con `ServicioFalso`.
- El test de humo de la GUI se omite si no hay `DISPLAY`.

## Limitaciones

- No implementa el flujo OAuth 2.0 PKCE para obtener el token: se asume que ya lo tenés.
- El acceso a la API de X depende de tu plan, que tiene cuotas y precios que cambian. La búsqueda reciente y la publicación pueden no estar incluidas en el nivel gratuito.
- No hay timeline «Para vos» (no existe en la API pública), ni subida de medios, ni streaming.
- La longitud ponderada es una aproximación de twitter-text: no detecta URLs sin esquema (`ejemplo.com`).
