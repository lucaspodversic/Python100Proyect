# 48 · CLI para gestionar entornos virtuales

Crea, lista, activa, inspecciona y elimina entornos virtuales guardados en una
carpeta central (`~/.venvctl`, configurable con `VENVCTL_HOME`).

## Qué demuestra
- Uso del módulo estándar `venv` y de `subprocess` **sin shell** (sin inyección).
- Validación de nombres y defensa contra *path traversal*.
- Borrado seguro: sólo elimina carpetas que contienen `pyvenv.cfg`.
- Ejecutor/creador inyectables para tests sin instalar paquetes.

## Arquitectura
```
venvctl/
  gestor.py  # Gestor: crear, listar, eliminar, instalar, congelar, info, comando_activar
  cli.py
```

## Instalación y uso
```bash
pip install -e ".[dev]"
python -m venvctl crear datos pandas
python -m venvctl listar
eval "$(python -m venvctl activar datos)"     # bash/zsh
python -m venvctl congelar datos > requirements.txt
python -m venvctl eliminar datos -y
```

## Tests
```bash
pytest
```
Un test crea un venv real **sin pip** en una carpeta temporal; el resto usa fakes.

## Limitaciones
- Un proceso no puede activar la shell que lo lanzó: `activar` imprime el comando a evaluar.
- No gestiona versiones de Python (para eso: `pyenv`, `uv`).
