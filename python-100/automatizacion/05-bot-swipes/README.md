# 05 · Bot de "swipes" (demostración de Selenium/Page Object con app mock)

El plan pedía automatizar Tinder. **Automatizar Tinder (o cualquier app de citas real) viola sus Términos de Servicio y puede provocar el baneo de la cuenta**; además involucra datos personales de terceros. Por eso el bot es **genérico** y opera contra una **app de citas MOCK local** con perfiles ficticios, incluida en el proyecto.

## Qué demuestra
- **Page Object** (`paginas.py`) para la pantalla de swipe.
- **Navegador inyectable**: adaptador Selenium o `HttpNavegador` (urllib + BeautifulSoup) para tests end-to-end sin navegador.
- **Reglas puras y auditables** (`preferencias.py`): rango de edad, distancia, intereses en común (sin acentos/mayúsculas), palabras excluidas en la bio.
- **Salvaguardas**: dry-run por defecto, máximo de likes, pausa entre swipes y rechazo de cualquier host no local.

## Arquitectura
```
src/bot_swipes/
├── preferencias.py  # Perfil, Preferencias, Veredicto, decidir()
├── navegador.py     # Navegador (Protocol), SeleniumNavegador, HttpNavegador
├── paginas.py       # PaginaPerfiles (Page Object)
├── bot.py           # BotSwipes: bucle con límites
├── sitio_mock.py    # app de citas falsa en 127.0.0.1
└── cli.py
```

## Instalación
```bash
pip install -e ".[dev]"          # opcional: ".[selenium]"
```

## Uso
```bash
bot-swipes --edad 25 35 --distancia 20 --interes cine --interes senderismo           # dry-run
bot-swipes --edad 25 35 --interes cine --excluir fumador --max-likes 3 --swipear      # swipea en el mock
python -m bot_swipes.sitio_mock --puerto 8766   # ver la app mock en el navegador
```

## Tests
```bash
pytest
```
Reglas: unitarios puros. Flujo: app mock en un puerto efímero de `127.0.0.1` recorrida con `HttpNavegador`.

## Limitaciones
- No incluye selectores ni login de apps reales, a propósito.
- El modo `--selenium` no se testea automáticamente (requiere Chrome + chromedriver).
- En dry-run sólo puede evaluarse el primer perfil (la app no avanza sin un swipe real).
