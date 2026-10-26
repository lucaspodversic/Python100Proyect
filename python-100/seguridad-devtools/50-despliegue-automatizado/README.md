# 50 · Script de despliegue automatizado

Sube una aplicación a un servidor (VPS) usando **Git + SSH**, con releases
atómicos, chequeo de salud y **rollback automático**.

## Qué demuestra
- Patrón *releases + symlink* (como Capistrano): `releases/<fecha>-<commit>` y `current → release`.
- Cambio de symlink **atómico** (`ln -sfn` + `mv -T`): cero archivos a medio copiar.
- Verificaciones locales (árbol limpio, rama correcta) antes de tocar el servidor.
- Build fallido → se borra el release; salud fallida → rollback al anterior.
- `shlex.quote` en todos los valores interpolados (evita inyección de comandos).
- SSH detrás de una interfaz: `ConexionSSH` (paramiko, con `RejectPolicy` contra MITM),
  `ConexionDryRun` y fakes en tests.

## Arquitectura
```
desplegador/
  config.py      # ConfigDespliegue (deploy.toml)
  conexion.py    # Conexion (Protocol), ConexionSSH, ConexionDryRun
  despliegue.py  # Desplegador: desplegar, rollback, limpiar_viejos
  cli.py         # deploy | rollback | plan  (+ --dry-run)
deploy.example.toml
```

## Instalación
```bash
pip install -e ".[dev,ssh]"   # 'ssh' instala paramiko para uso real
cp deploy.example.toml deploy.toml
```

## Uso
```bash
python -m desplegador plan              # dry-run: muestra los comandos, no conecta
python -m desplegador deploy
python -m desplegador rollback
```
Requisitos en el servidor: `git`, acceso de lectura al repo (deploy key) y el host
en tu `~/.ssh/known_hosts` (los hosts desconocidos se rechazan).

## Tests
```bash
pytest
```
Git local y SSH son fakes: **no hay conexiones reales**.

## Limitaciones
- Un único servidor por ejecución (sin orquestación multi-host ni migraciones de BD).
- Los `comandos_build` se ejecutan tal cual: son responsabilidad de quien escribe la config.
