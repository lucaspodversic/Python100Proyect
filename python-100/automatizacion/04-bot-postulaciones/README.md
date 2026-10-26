# 04 · Bot de postulación automática a ofertas (versión ética, sitio mock)

El plan pedía un "auto-aplicador de LinkedIn". **Automatizar LinkedIn (o cualquier portal real) viola sus Términos de Servicio y puede terminar con la cuenta del usuario bloqueada.** Por eso este proyecto implementa el mismo bot de forma **genérica** y lo ejecuta contra un **sitio mock local** incluido en el proyecto, que imita el flujo de un portal: listado paginado → detalle → formulario de postulación.

## Qué demuestra
- **Patrón Page Object** (`paginas.py`): los selectores viven en clases por página.
- **Navegador inyectable** (`navegador.py`): el bot habla con un `Protocol`; hay un adaptador para **Selenium** y un `HttpNavegador` liviano (urllib + BeautifulSoup) que sigue links y envía formularios, para tests end-to-end sin navegador.
- **Reglas de decisión puras** (`perfil.py`): palabras obligatorias/deseables/excluidas (palabra completa, sin acentos), ubicación, remoto, salario mínimo, puntaje y motivos auditables.
- **Salvaguardas**: dry-run por defecto, máximo de postulaciones, pausa entre acciones (rate limiting), historial SQLite anti-duplicados y **bloqueo de cualquier URL que no sea 127.0.0.1/localhost**.

## Arquitectura
```
src/bot_postulaciones/
├── perfil.py      # Perfil, Oferta, Decision, evaluar() — lógica pura
├── navegador.py   # Navegador (Protocol), SeleniumNavegador, HttpNavegador
├── paginas.py     # PaginaListado, PaginaOferta, PaginaFormulario (Page Objects)
├── bot.py         # BotPostulaciones (orquestador), Registro (SQLite), validar_url_local
├── sitio_mock.py  # portal de empleo falso servido en 127.0.0.1 (http.server)
└── cli.py
perfil.ejemplo.json
```

## Instalación
```bash
pip install -e ".[dev]"            # opcional: pip install -e ".[selenium]"
```

## Uso
```bash
bot-postulaciones --perfil perfil.ejemplo.json              # levanta el mock y simula (dry-run)
bot-postulaciones --perfil perfil.ejemplo.json --postular   # postula en el mock
python -m bot_postulaciones.sitio_mock --puerto 8765        # servir el mock para verlo en el navegador
bot-postulaciones --perfil perfil.ejemplo.json --url http://127.0.0.1:8765/ofertas --selenium --postular
```

## Tests
```bash
pytest
```
- Reglas de decisión: tests unitarios puros.
- Flujo completo: el sitio mock se levanta en un puerto efímero de `127.0.0.1` y el bot lo recorre con `HttpNavegador`.
- Adaptador Selenium: se valida con un WebDriver falso (no requiere Chrome).

## Limitaciones
- Intencionalmente **no** incluye selectores, login ni URLs de portales reales y rechaza hosts no locales.
- El modo `--selenium` no se cubre en los tests automáticos (requiere Chrome + chromedriver).
- `HttpNavegador` no ejecuta JavaScript; alcanza para el mock, que es HTML plano.
