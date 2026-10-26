# 100 proyectos en Python

Son 100 proyectos independientes en Python. Cada uno tiene su `pyproject.toml`, su carpeta `tests/` con pytest, un README y un `.gitignore`. El código lleva type hints y está comentado en detalle en español.

## Cómo usar

```bash
cd automatizacion/01-organizador-archivos
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # o: pip install -r requirements*.txt según el proyecto
pytest
```

Los tests corren sin conexión y dan siempre el mismo resultado. Los servicios externos (LLMs, Gmail, SMTP, S3, APIs de terceros) se reemplazan por versiones simuladas, el scraping usa páginas de ejemplo locales o un servidor en 127.0.0.1 y las bases de datos son SQLite. Las claves se leen solo de variables de entorno.

## Resumen

| Categoría | Proyectos | Tests |
|---|---|---|
| Automatización + Datos/ML | 01–20 | 153 |
| Web/APIs + IA/LLMs | 21–40 | 238 |
| Seguridad/DevTools + Productividad + Scraping | 41–70 | 310 |
| Negocio + Escritorio/GUI + Especializados | 71–100 | 519 |
| **Total** | **100** | **1220** |

## Índice

### automatizacion

- [01-organizador-archivos](automatizacion/01-organizador-archivos/)
- [02-alertas-email](automatizacion/02-alertas-email/)
- [03-scraper-competencia](automatizacion/03-scraper-competencia/)
- [04-bot-postulaciones](automatizacion/04-bot-postulaciones/)
- [05-bot-swipes](automatizacion/05-bot-swipes/)
- [06-informes-pdf](automatizacion/06-informes-pdf/)
- [07-sincronizador-backups](automatizacion/07-sincronizador-backups/)
- [08-monitor-vuelos](automatizacion/08-monitor-vuelos/)
- [09-limpiador-bandeja](automatizacion/09-limpiador-bandeja/)
- [10-facturacion](automatizacion/10-facturacion/)

### datos-ml

- [11-predictor-vivienda](datos-ml/11-predictor-vivienda/)
- [12-sentimiento-clientes](datos-ml/12-sentimiento-clientes/)
- [13-segmentacion-clientes](datos-ml/13-segmentacion-clientes/)
- [14-recomendador-peliculas](datos-ml/14-recomendador-peliculas/)
- [15-cesta-mercado](datos-ml/15-cesta-mercado/)
- [16-dashboard-finanzas](datos-ml/16-dashboard-finanzas/)
- [17-predictor-entregas](datos-ml/17-predictor-entregas/)
- [18-cnn-plantas](datos-ml/18-cnn-plantas/)
- [19-series-ventas](datos-ml/19-series-ventas/)
- [20-deteccion-fraude](datos-ml/20-deteccion-fraude/)

### web

- [21-api-tareas](web/21-api-tareas/)
- [22-blog-autenticacion](web/22-blog-autenticacion/)
- [23-tienda-online](web/23-tienda-online/)
- [24-chat-tiempo-real](web/24-chat-tiempo-real/)
- [25-acortador-urls](web/25-acortador-urls/)
- [26-api-inventario](web/26-api-inventario/)
- [27-reservas-citas](web/27-reservas-citas/)
- [28-portafolio-dinamico](web/28-portafolio-dinamico/)
- [29-foro-discusion](web/29-foro-discusion/)
- [30-formularios-dinamicos](web/30-formularios-dinamicos/)

### ia-llm

- [31-chatbot-atencion](ia-llm/31-chatbot-atencion/)
- [32-rag-documentos](ia-llm/32-rag-documentos/)
- [33-notas-reuniones](ia-llm/33-notas-reuniones/)
- [34-asistente-email](ia-llm/34-asistente-email/)
- [35-nl-a-sql](ia-llm/35-nl-a-sql/)
- [36-simulador-entrevistas](ia-llm/36-simulador-entrevistas/)
- [37-gateway-llm](ia-llm/37-gateway-llm/)
- [38-sentimiento-tiempo-real](ia-llm/38-sentimiento-tiempo-real/)
- [39-clasificador-tickets](ia-llm/39-clasificador-tickets/)
- [40-resumen-articulos](ia-llm/40-resumen-articulos/)

### seguridad-devtools

- [41-contrasenas-comprometidas](seguridad-devtools/41-contrasenas-comprometidas/)
- [42-gestor-contrasenas](seguridad-devtools/42-gestor-contrasenas/)
- [43-escaner-puertos](seguridad-devtools/43-escaner-puertos/)
- [44-generador-contrasenas](seguridad-devtools/44-generador-contrasenas/)
- [45-cifrador-archivos](seguridad-devtools/45-cifrador-archivos/)
- [46-linter-python](seguridad-devtools/46-linter-python/)
- [47-generador-docs](seguridad-devtools/47-generador-docs/)
- [48-gestor-venvs](seguridad-devtools/48-gestor-venvs/)
- [49-monitor-servidores](seguridad-devtools/49-monitor-servidores/)
- [50-despliegue-automatizado](seguridad-devtools/50-despliegue-automatizado/)

### productividad

- [51-pdf-a-audiolibro](productividad/51-pdf-a-audiolibro/)
- [52-organizador-descargas](productividad/52-organizador-descargas/)
- [53-descargador-youtube](productividad/53-descargador-youtube/)
- [54-gestor-tareas-cli](productividad/54-gestor-tareas-cli/)
- [55-juego-2048](productividad/55-juego-2048/)
- [56-ahorcado](productividad/56-ahorcado/)
- [57-generador-qr](productividad/57-generador-qr/)
- [58-seguimiento-habitos](productividad/58-seguimiento-habitos/)
- [59-calculadora-propinas](productividad/59-calculadora-propinas/)
- [60-generador-memes](productividad/60-generador-memes/)

### scraping

- [61-scraper-empleos](scraping/61-scraper-empleos/)
- [62-rastreador-cripto](scraping/62-rastreador-cripto/)
- [63-extractor-wikipedia](scraping/63-extractor-wikipedia/)
- [64-scraper-resenas](scraping/64-scraper-resenas/)
- [65-monitor-cambios-web](scraping/65-monitor-cambios-web/)
- [66-datos-climaticos](scraping/66-datos-climaticos/)
- [67-titulares-noticias](scraping/67-titulares-noticias/)
- [68-scraper-vuelos](scraping/68-scraper-vuelos/)
- [69-tablas-pdf-excel](scraping/69-tablas-pdf-excel/)
- [70-scraper-github](scraping/70-scraper-github/)

### negocio

- [71-reservas-hotel](negocio/71-reservas-hotel/)
- [72-inventario-tienda](negocio/72-inventario-tienda/)
- [73-rrhh-empleados](negocio/73-rrhh-empleados/)
- [74-cursos-online](negocio/74-cursos-online/)
- [75-reserva-vuelos](negocio/75-reserva-vuelos/)
- [76-gestor-proyectos](negocio/76-gestor-proyectos/)
- [77-pasarela-pagos](negocio/77-pasarela-pagos/)
- [78-mesa-ayuda](negocio/78-mesa-ayuda/)
- [79-encuestas](negocio/79-encuestas/)
- [80-cms](negocio/80-cms/)

### escritorio

- [81-calculadora-cientifica](escritorio/81-calculadora-cientifica/)
- [82-reproductor-musica](escritorio/82-reproductor-musica/)
- [83-editor-texto](escritorio/83-editor-texto/)
- [84-visor-imagenes](escritorio/84-visor-imagenes/)
- [85-bloc-notas-autoguardado](escritorio/85-bloc-notas-autoguardado/)
- [86-conversor-unidades](escritorio/86-conversor-unidades/)
- [87-reloj-cronometro](escritorio/87-reloj-cronometro/)
- [88-gestor-contrasenas-gui](escritorio/88-gestor-contrasenas-gui/)
- [89-cliente-x](escritorio/89-cliente-x/)
- [90-captura-pantalla](escritorio/90-captura-pantalla/)

### especializados

- [100-snake-pong](especializados/100-snake-pong/)
- [91-asistencia-facial](especializados/91-asistencia-facial/)
- [92-analisis-trafico](especializados/92-analisis-trafico/)
- [93-motor-busqueda](especializados/93-motor-busqueda/)
- [94-interprete-calc](especializados/94-interprete-calc/)
- [95-musica-procedural](especializados/95-musica-procedural/)
- [96-visualizador-ordenamiento](especializados/96-visualizador-ordenamiento/)
- [97-detector-yolo](especializados/97-detector-yolo/)
- [98-votacion-segura](especializados/98-votacion-segura/)
- [99-analisis-logs](especializados/99-analisis-logs/)

## Notas

- Son proyectos educativos y no están auditados para producción.
- Los bots 04 (LinkedIn) y 05 (Tinder) y los scrapers 61, 64 y 68 corren solo contra sitios simulados o páginas de ejemplo locales. Automatizar los sitios reales viola sus términos de uso.
- El escáner de puertos (43) y el analizador de tráfico (92) son para equipos y redes propios o con autorización.
- Los modelos de ML se entrenan con datos sintéticos, así que sus métricas no reflejan el rendimiento con datos reales.
- Los tests de interfaz gráfica (81–90) necesitan una pantalla, que puede ser virtual con Xvfb. Sin pantalla esos tests se saltean.

Licencia: MIT.
