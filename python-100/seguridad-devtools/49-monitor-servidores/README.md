# 49 · Bot de monitoreo de servidores

Vigila **CPU, memoria y disco** y envía alertas a **Slack** y/o **Discord** cuando
superan un umbral.

## Qué demuestra
- Lectura de métricas sólo con la librería estándar (`/proc/stat`, `/proc/meminfo`, `shutil.disk_usage`).
- Lógica de alertas con **lecturas consecutivas** (anti picos), **enfriamiento** (anti spam) y
  mensajes de **recuperación**.
- Notificadores por webhook detrás de una interfaz `Transporte` (testeable sin red).
- Webhooks como secretos en variables de entorno, sólo por HTTPS.

## Arquitectura
```
monitor/
  metricas.py       # Metricas, ProveedorLinux, uso_cpu, uso_memoria
  reglas.py         # Umbrales, Alerta, EvaluadorAlertas
  notificadores.py  # TransporteHTTP, NotificadorSlack, NotificadorDiscord
  bot.py            # ciclo() y bucle principal
```

## Instalación y uso
```bash
pip install -e ".[dev]"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python -m monitor --cpu 85 --memoria 90 --disco 80 --intervalo 30
```
Sugerencia: ejecutarlo como servicio `systemd`.

## Tests
```bash
pytest
```
Métricas con fixtures, reloj falso para el enfriamiento y un servidor HTTP en
`127.0.0.1` para probar el transporte real. Ningún pedido a Slack/Discord.

## Limitaciones
- Métricas de CPU/memoria sólo en Linux (en otros SO, implementar otro `ProveedorMetricas`, p. ej. con `psutil`).
- Monitorea el host local; para varios servidores, ejecutar un agente en cada uno.
