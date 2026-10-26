# 02 · Sistema de alertas por email

Vigila una carpeta (local o compartida) y **envía un email al equipo** cuando un informe o archivo de datos crítico se crea, modifica o elimina.

## Qué demuestra
- Detección de cambios por instantáneas con hash SHA-256 (sin falsos positivos por "touch").
- Inyección de dependencias: el canal de notificación es una interfaz (`Protocol`).
- Configuración segura por variables de entorno (sin credenciales en el código).
- Estado persistente para no repetir alertas tras reiniciar.

## Arquitectura
```
src/alertas/
├── vigilante.py    # tomar_instantanea(), comparar(), Vigilante (revisar/vigilar)
├── notificador.py  # Notificador (Protocol), SMTPNotificador (smtplib), FakeNotificador
└── cli.py          # argparse, modo --dry-run que imprime en consola
```

## Instalación
```bash
pip install -e ".[dev]"
```

## Uso
```bash
export ALERTAS_SMTP_HOST=smtp.miempresa.com ALERTAS_SMTP_USUARIO=bot ALERTAS_SMTP_CLAVE=...
alertas /mnt/compartida/informes --patron "*.xlsx" --patron "*.csv" \
        --para equipo@miempresa.com --intervalo 300 --estado estado.json
alertas ./datos --para yo@test --iteraciones 1 --dry-run   # prueba sin enviar
```

## Tests
```bash
pytest
```
No abren sockets: usan `FakeNotificador` y un `SMTPFalso` que imita `smtplib.SMTP`.

## Limitaciones
- Polling (no eventos del SO): la latencia es el intervalo elegido. Es intencional, para que funcione en carpetas de red.
- Calcula el hash de cada archivo vigilado en cada pasada; para carpetas gigantes conviene restringir con `--patron`.
