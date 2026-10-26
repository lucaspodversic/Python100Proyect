# 09 · Limpiador de bandeja de entrada

Clasifica, etiqueta, archiva o manda a la papelera correos de **Gmail** según reglas definidas en JSON.

## Qué demuestra
- Motor de reglas declarativo (condiciones AND, `detener` para controlar la cascada).
- Integración con **Gmail API v1** (OAuth de escritorio, paginación, `batchModify` en lotes de 1000).
- Seguridad: dry-run por defecto, remitentes protegidos, los destacados nunca se tocan, sólo **papelera** (recuperable 30 días), scope `gmail.modify` (no permite borrado permanente).
- Inyección de dependencias: el motor sólo conoce la interfaz `ClienteCorreo`.

## Arquitectura
```
src/limpiador_correo/
├── modelos.py  # Correo, Condicion, Accion, Regla
├── motor.py    # cargar_reglas(), Motor.clasificar()/ejecutar(), Reporte
├── gmail.py    # ClienteCorreo (Protocol), GmailCliente, crear_servicio(), FakeCliente
└── cli.py
reglas.ejemplo.json
```

### Condiciones disponibles
`remitente_contiene`, `dominio` (incluye subdominios), `asunto_regex`, `mas_antiguo_que_dias`, `con_etiqueta`, `tamano_mayor_kb`, `tiene_adjuntos`.

### Acciones
`archivar`, `papelera`, `etiquetar` (crea la etiqueta si falta), `marcar_leido`, `destacar`.

## Instalación
```bash
pip install -e ".[dev,gmail]"
```
Creá un proyecto en Google Cloud, habilitá Gmail API y descargá `credentials.json` (OAuth, app de escritorio).

## Uso
```bash
limpiador-bandeja reglas.ejemplo.json                        # dry-run
limpiador-bandeja reglas.ejemplo.json --aplicar --proteger jefa@empresa.com
```

## Tests
```bash
pytest
```
Usa `FakeCliente` (bandeja en memoria) y un `service` falso que imita la cadena de llamadas de `googleapiclient`.

## Limitaciones
- `crear_servicio()` y la CLI real no se prueban (requieren OAuth interactivo); las librerías de Google no están instaladas en el entorno de tests.
- Se leen metadatos (no el cuerpo) por privacidad y velocidad; reglas sobre el contenido requerirían `format="full"`.
