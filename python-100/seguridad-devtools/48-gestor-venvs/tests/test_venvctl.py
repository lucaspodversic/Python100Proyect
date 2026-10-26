"""Tests con carpeta temporal; pip se reemplaza por un ejecutor falso."""
import pytest

from venvctl import ErrorGestor, Gestor
from venvctl.cli import ejecutar


# Registra cada comando en vez de ejecutarlo; para "freeze" devuelve una salida fija.
class EjecutorFalso:
    def __init__(self):
        self.comandos = []

    def __call__(self, cmd):
        self.comandos.append(list(cmd))
        return "requests==2.0\n" if "freeze" in cmd else "ok"


# Escribe sólo lo que el gestor inspecciona: bin/python y pyvenv.cfg con una versión conocida.
def creador_falso(ruta, con_pip):
    """Simula `venv`: crea la estructura mínima."""
    (ruta / "bin").mkdir(parents=True)
    (ruta / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.12.1\n")
    (ruta / "bin" / "python").write_text("")


@pytest.fixture
# Gestor aislado en una carpeta temporal, sin procesos ni red.
def gestor(tmp_path):
    return Gestor(tmp_path / "envs", EjecutorFalso(), creador_falso)


# listar devuelve orden alfabético ("b" antes de "proy-a").
def test_crear_listar_eliminar(gestor):
    gestor.crear("proy-a", con_pip=False); gestor.crear("b")
    assert gestor.listar() == ["b", "proy-a"]
    gestor.eliminar("b")
    assert gestor.listar() == ["proy-a"]


# El comando es [python, "-m", "pip", "install", ...paquetes].
def test_crear_con_paquetes_llama_pip(gestor):
    gestor.crear("x", ["requests", "rich"])
    cmd = gestor.ejecutor.comandos[0]
    assert cmd[1:4] == ["-m", "pip", "install"] and cmd[-2:] == ["requests", "rich"]


def test_congelar(gestor):
    gestor.crear("x")
    assert gestor.congelar("x") == "requests==2.0\n"


# Path traversal, separador de carpeta, vacío, oculto y más de 64 caracteres.
@pytest.mark.parametrize("malo", ["../fuera", "a/b", "", ".oculto", "x" * 70])
def test_nombres_invalidos(gestor, malo):
    with pytest.raises(ErrorGestor):
        gestor.crear(malo)


# Crear dos veces, eliminar o instalar en un entorno inexistente → ErrorGestor.
def test_duplicado_y_inexistente(gestor):
    gestor.crear("x")
    with pytest.raises(ErrorGestor):
        gestor.crear("x")
    with pytest.raises(ErrorGestor):
        gestor.eliminar("nada")
    with pytest.raises(ErrorGestor):
        gestor.instalar("nada", ["a"])


# Una carpeta sin pyvenv.cfg dentro de la base nunca se borra.
def test_no_borra_carpetas_que_no_son_venv(gestor):
    (gestor.base / "importante").mkdir(parents=True)
    with pytest.raises(ErrorGestor):
        gestor.eliminar("importante")
    assert (gestor.base / "importante").exists()


# La versión 3.12.1 sale del pyvenv.cfg escrito por creador_falso.
def test_activar_e_info(gestor):
    gestor.crear("x")
    assert gestor.comando_activar("x").endswith("bin/activate")
    assert gestor.comando_activar("x", "fish").endswith("activate.fish")
    assert gestor.info("x").version_python == "3.12.1"


def test_venv_real_sin_pip(tmp_path):
    """Crea un venv real (sin pip para que sea rápido) con el módulo estándar."""
    # Creador real (módulo venv) pero sin pip: no hace falta red.
    g = Gestor(tmp_path / "envs", EjecutorFalso())
    g.crear("real", con_pip=False)
    assert g.listar() == ["real"] and g.python("real").exists()


# Flujo completo por CLI; tras eliminar, "activar" falla con exit 1.
def test_cli(gestor, capsys):
    assert ejecutar(["crear", "demo"], gestor) == 0
    assert ejecutar(["listar"], gestor) == 0
    assert "demo" in capsys.readouterr().out
    assert ejecutar(["info", "demo"], gestor) == 0
    assert ejecutar(["eliminar", "demo", "-y"], gestor) == 0
    assert ejecutar(["activar", "demo"], gestor) == 1
