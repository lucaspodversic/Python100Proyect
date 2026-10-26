"""Tests con SSH y git falsos: nunca se conecta a un servidor real."""
import datetime as dt

import pytest

from desplegador import ConfigDespliegue, ConexionDryRun, Desplegador, ErrorDespliegue, ResultadoComando
from desplegador.cli import ejecutar

# Commit falso: sus primeros 7 caracteres (abc1234) forman parte del nombre del release.
COMMIT = "abc1234def5678"


def git_ok(args):
    """Git falso con árbol limpio, en la rama main y con HEAD en COMMIT."""
    return {"status": "", "rev-parse": "main" if "--abbrev-ref" in args else COMMIT}[args[0]]


class SSHFalso:
    """Simula un servidor con estado mínimo (lista de releases y symlink)."""

    def __init__(self, releases=(), fallar=None):
        self.releases = list(releases)
        self.current = None
        self.comandos = []
        # Subcadenas de comandos que deben fallar (para simular errores en un paso concreto).
        self.fallar = fallar or ()

    def ejecutar(self, c):
        self.comandos.append(c)
        for f in self.fallar:
            if f in c:
                return ResultadoComando(1, "", f"fallo simulado: {f}")
        if c.startswith("ls -1"):
            return ResultadoComando(0, "\n".join(self.releases))
        # El destino es el 7.º token: git clone --quiet --branch RAMA REPO DESTINO.
        if c.startswith("git clone"):
            self.releases.append(c.split()[6].rsplit("/", 1)[-1])
        # El tercer token es la ruta del release al que apunta el symlink.
        if c.startswith("ln -sfn"):
            self.current = c.split()[2]
        if c.startswith("rm -rf") and "/releases/" in c:
            n = c.split()[-1].rsplit("/", 1)[-1]
            if n in self.releases: self.releases.remove(n)
        if c.startswith("readlink"):
            return ResultadoComando(0, self.current or "")
        return ResultadoComando(0)

    def cerrar(self): pass


def cfg(**kw):
    """Configuración base del test; los kwargs pisan campos puntuales."""
    base = dict(host="h", usuario="u", repo="git@x:y/z.git", ruta_base="/srv/app",
                comandos_build=["make build"], comando_reinicio="systemctl restart app",
                comando_salud="curl -f localhost/health", releases_a_conservar=2)
    base.update(kw)
    return ConfigDespliegue(**base)


# Fecha fija → release "20260102030405-abc1234".
AHORA = lambda: dt.datetime(2026, 1, 2, 3, 4, 5)


# Nombre esperado, current actualizado, checkout del commit exacto y build dentro del release.
def test_despliegue_exitoso():
    ssh = SSHFalso(["20250101000000-aaaaaaa"])
    nombre = Desplegador(cfg(), ssh, git_ok, AHORA).desplegar()
    assert nombre == "20260102030405-abc1234"
    assert ssh.current == f"/srv/app/releases/{nombre}"
    assert any("checkout --quiet abc1234def5678" in c for c in ssh.comandos)
    assert any(c.startswith("cd /srv/app/releases/") and c.endswith("make build") for c in ssh.comandos)


# 3 viejos + 1 nuevo con conservar=2 → quedan el más reciente viejo y el nuevo.
def test_conserva_n_releases():
    ssh = SSHFalso(["2024-a", "2024-b", "2024-c"])
    Desplegador(cfg(), ssh, git_ok, AHORA).desplegar()
    assert ssh.releases == ["2024-c", "20260102030405-abc1234"]


# Con cambios sin commitear no se envía ni un comando al servidor.
def test_arbol_sucio_aborta_sin_tocar_servidor():
    sucio = lambda a: " M archivo.py" if a[0] == "status" else "main"
    ssh = SSHFalso()
    with pytest.raises(ErrorDespliegue, match="sin commitear"):
        Desplegador(cfg(), ssh, sucio, AHORA).desplegar()
    assert ssh.comandos == []


def test_rama_incorrecta():
    otra = lambda a: "" if a[0] == "status" else "feature"
    with pytest.raises(ErrorDespliegue, match="feature"):
        Desplegador(cfg(), SSHFalso(), otra, AHORA).desplegar()


# El release roto se borra y current nunca se cambió.
def test_build_fallido_limpia_release():
    ssh = SSHFalso(["viejo"], fallar=["make build"])
    with pytest.raises(ErrorDespliegue, match="build"):
        Desplegador(cfg(), ssh, git_ok, AHORA).desplegar()
    assert ssh.releases == ["viejo"] and ssh.current is None


# Salud fallida → current vuelve al release "viejo".
def test_salud_fallida_hace_rollback():
    ssh = SSHFalso(["viejo"], fallar=["curl -f"])
    with pytest.raises(ErrorDespliegue, match="revertido"):
        Desplegador(cfg(), ssh, git_ok, AHORA).desplegar()
    assert ssh.current == "/srv/app/releases/viejo"


# r2 → r1; con un único release no hay a dónde volver.
def test_rollback_manual():
    ssh = SSHFalso(["r1", "r2"]); ssh.current = "/srv/app/releases/r2"
    assert Desplegador(cfg(), ssh, git_ok, AHORA).rollback() == "r1"
    ssh2 = SSHFalso(["r1"]); ssh2.current = "/srv/app/releases/r1"
    with pytest.raises(ErrorDespliegue):
        Desplegador(cfg(), ssh2, git_ok, AHORA).rollback()


# El ";rm -rf /" queda dentro de comillas simples: es parte del nombre, no un comando.
def test_escapa_valores_peligrosos():
    ssh = SSHFalso()
    Desplegador(cfg(ruta_base="/srv/mi app;rm -rf /", rama="main"), ssh, git_ok, AHORA).desplegar()
    assert all("'/srv/mi app;rm -rf /" in c for c in ssh.comandos if "mkdir" in c)


# ConexionDryRun sólo registra: el plan incluye el listado y el clone.
def test_dry_run_no_conecta():
    d = ConexionDryRun()
    Desplegador(cfg(), d, git_ok, AHORA).desplegar()
    assert d.comandos[0].startswith("ls -1") and any("git clone" in c for c in d.comandos)


# TOML mínimo con rama por defecto "main"; "plan" imprime los comandos.
def test_config_toml_y_cli_plan(tmp_path, capsys):
    t = tmp_path / "deploy.toml"
    t.write_text('[deploy]\nhost="h"\nusuario="u"\nrepo="r"\nruta_base="/srv/a"\n')
    assert ConfigDespliegue.desde_toml(t).rama == "main"
    assert ejecutar(["plan", "--config", str(t)], git=git_ok) == 0
    assert "git clone" in capsys.readouterr().out


# Salud fallida y sin releases previos (no hay rollback posible) → exit 1.
def test_cli_deploy_con_fabrica(tmp_path):
    t = tmp_path / "deploy.toml"
    t.write_text('[deploy]\nhost="h"\nusuario="u"\nrepo="r"\nruta_base="/srv/a"\ncomando_salud="curl -f x"\n')
    ssh = SSHFalso(fallar=["curl -f"])
    assert ejecutar(["deploy", "--config", str(t)], fabrica_conexion=lambda c: ssh, git=git_ok) == 1
