# 99 · Análisis de logs de acceso Apache/Nginx

Herramienta de línea de comandos que lee logs de acceso de **Apache** y
**Nginx** (formatos *common* y *combined*, también comprimidos `.gz`) y genera
un informe de **visitas**, **errores** y **tráfico** en texto, JSON o HTML.

## Qué demuestra

- Parseo robusto con una expresión regular `re.VERBOSE` comentada: comillas
  escapadas, IPv6, campos extra de Nginx, CLF sin referer/agente, HTTP/0.9.
- Tolerancia a basura: las líneas inválidas se cuentan y se muestran ejemplos,
  no abortan el análisis.
- Fechas independientes del locale y normalizadas a UTC.
- Métricas con definiciones explícitas: peticiones, páginas vistas (sin
  estáticos ni bots), visitantes únicos (IP+UA) y **visitas** por sesión de
  30 minutos.
- Detección simple de escáneres (IPs con muchos 4xx).
- HTML autocontenido con escape de todo lo que viene del log (anti-XSS).

## Arquitectura

```
logweb/
├── parser.py    # PATRON, parsear_linea → Registro, parsear_fecha, abrir (.gz), leer → Lectura
├── analisis.py  # es_bot, es_estatico, tipo_dispositivo, analizar → Informe
├── informe.py   # a_texto (con histograma ASCII), a_json, a_html
└── cli.py       # archivos…, --formato, --salida, --top, --desde, --hasta
```

## Instalación y uso

```bash
pip install -e .        # sin dependencias externas
python -m logweb /var/log/nginx/access.log /var/log/nginx/access.log.1.gz
python -m logweb access.log --formato html --salida informe.html --desde 2026-10-01
python -m logweb access.log --formato json --top 20 > informe.json
```

Los logs del sistema suelen requerir permisos de lectura (`adm` en Debian):
copialos o usá `sudo` solo para leerlos.

## Tests

```bash
pip install pytest && python -m pytest
```

Usan dos logs de ejemplo en `tests/fixtures/` (Apache y Nginx) y cada número
esperado está justificado en el docstring del test (cómo se llega a 34075
bytes, 6 páginas vistas, 4 visitas, tasa de error 0.4375, etc.). También se
prueban `.gz`, filtros de fecha, escape HTML y errores del CLI.

## Limitaciones

- Solo formatos *common*/*combined* (y campos extra al final). Formatos
  personalizados con otro orden (`LogFormat` propio, JSON de Nginx) requieren
  adaptar `PATRON`.
- Visitantes únicos por IP+UA es una aproximación (NAT, VPN, IPs dinámicas).
- Detección de bots por palabras clave: los bots que imitan navegadores pasan.
- Todo se carga en memoria; para logs de muchos GB convendría agregar en
  streaming (las métricas ya son contadores, el cambio es acotado) o usar
  GoAccess.
- Sin geolocalización de IPs (requiere bases externas como GeoLite2).
