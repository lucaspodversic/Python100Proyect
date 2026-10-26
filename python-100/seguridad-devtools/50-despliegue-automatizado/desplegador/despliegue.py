"""Orquestación del despliegue con el patrón "releases + symlink".

Estructura en el servidor:
    {ruta_base}/releases/20260101120000-abc1234/   ← un directorio por despliegue
    {ruta_base}/current -> releases/<último>        ← symlink que usa el servicio

Pasos:
 1. (local) Verificar que el árbol git esté limpio y obtener el commit.
 2. Clonar el commit exacto en un release nuevo.
 3. Ejecutar comandos de build dentro del release.
 4. Cambiar el symlink `current` de forma ATÓMICA (ln + mv -T).
 5. Reiniciar el servicio y chequear salud.
 6. Si la salud falla → rollback al release anterior.
 7. Borrar releases viejos (conserva N).
Todos los valores interpolados en comandos remotos se escapan con shlex.quote.
"""
from __future__ import annotations

import datetime as dt
import logging
import shlex
import subprocess
from typing import Callable, Sequence

from .config import ConfigDespliegue
from .conexion import Conexion

log = logging.getLogger("desplegador")
# Alias corto: todo valor interpolado en un comando remoto pasa por q() (evita inyección de shell).
q = shlex.quote
# Recibe los argumentos de git y devuelve su stdout ya sin espacios sobrantes.
GitLocal = Callable[[Sequence[str]], str]


class ErrorDespliegue(Exception):
    """Fallo en algún paso; el mensaje indica cuál."""


def git_local_real(args: Sequence[str]) -> str:
    """Ejecuta git localmente sin shell."""
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


class Desplegador:
    """Ejecuta los pasos del despliegue y el rollback sobre una conexión remota."""
    def __init__(self, cfg: ConfigDespliegue, conexion: Conexion, git: GitLocal = git_local_real,
                 ahora: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc)):
        # `ahora` inyectable: los tests fijan la fecha y el nombre del release es predecible.
        self.cfg, self.cx, self.git, self.ahora = cfg, conexion, git, ahora
        # Sin "/" final para que las concatenaciones no produzcan "//".
        self.base = cfg.ruta_base.rstrip("/")

    # --------- utilidades ---------
    def _remoto(self, comando: str, paso: str) -> str:
        """Ejecuta un comando remoto y aborta si falla."""
        # Cada comando queda registrado con el nombre de su paso.
        log.info("[%s] %s", paso, comando)
        r = self.cx.ejecutar(comando)
        if not r.ok:
            raise ErrorDespliegue(f"Falló '{paso}' (código {r.codigo}): {r.error.strip()}")
        return r.salida

    def verificar_local(self) -> str:
        """Exige árbol limpio y que la rama local coincida; devuelve el commit."""
        # --porcelain devuelve texto sólo si hay cambios: se exige desplegar exactamente lo commiteado.
        if self.git(["status", "--porcelain"]):
            raise ErrorDespliegue("Hay cambios sin commitear: hacé commit antes de desplegar")
        rama = self.git(["rev-parse", "--abbrev-ref", "HEAD"])
        if rama != self.cfg.rama:
            raise ErrorDespliegue(f"Estás en '{rama}', se despliega '{self.cfg.rama}'")
        # Hash completo: se hace checkout de ese commit exacto aunque la rama remota avance mientras tanto.
        return self.git(["rev-parse", "HEAD"])

    def listar_releases(self) -> list[str]:
        """Nombres de los releases en el servidor, ordenados (el nombre empieza con fecha)."""
        # "|| true": la primera vez la carpeta no existe y no debe considerarse un error.
        salida = self._remoto(f"ls -1 {q(self.base + '/releases')} 2>/dev/null || true", "listar")
        return sorted(l for l in salida.split() if l)

    def _apuntar_current(self, release_dir: str) -> None:
        """Symlink atómico: se crea uno temporal y se renombra sobre `current`."""
        # ln -sfn crea el symlink temporal; mv -T lo renombra sobre `current` con rename(2), que es atómico:
        # el servicio nunca ve un `current` inexistente ni a medio escribir.
        tmp = f"{self.base}/current.tmp"
        self._remoto(f"ln -sfn {q(release_dir)} {q(tmp)} && mv -Tf {q(tmp)} {q(self.base + '/current')}", "symlink")

    # --------- flujo principal ---------
    def desplegar(self) -> str:
        # Paso 1: todo lo local se verifica antes de tocar el servidor.
        commit = self.verificar_local()
        # Nombre = fecha UTC + commit corto: ordenable cronológicamente y trazable.
        nombre = f"{self.ahora():%Y%m%d%H%M%S}-{commit[:7]}"
        rel = f"{self.base}/releases/{nombre}"
        # Se recuerdan los releases previos para poder volver al último si la salud falla.
        anteriores = self.listar_releases()
        self._remoto(f"mkdir -p {q(self.base + '/releases')}", "preparar")
        # Paso 2: clonar la rama y fijar el commit exacto verificado localmente.
        self._remoto(f"git clone --quiet --branch {q(self.cfg.rama)} {q(self.cfg.repo)} {q(rel)}"
                     f" && git -C {q(rel)} checkout --quiet {q(commit)}", "clonar")
        try:
            for cmd in self.cfg.comandos_build:
                # Los comandos de build vienen de la config del dueño: se ejecutan tal cual
                self._remoto(f"cd {q(rel)} && {cmd}", "build")
        # Build fallido: se borra el release a medias y se relanza el error; `current` nunca se tocó.
        except ErrorDespliegue:
            self._remoto(f"rm -rf {q(rel)}", "limpiar-fallido")  # no dejamos releases rotos
            raise
        # Paso 4: a partir de aquí el nuevo release es el activo.
        self._apuntar_current(rel)
        try:
            # Paso 5: reinicio y chequeo de salud (ambos opcionales).
            if self.cfg.comando_reinicio:
                self._remoto(self.cfg.comando_reinicio, "reiniciar")
            if self.cfg.comando_salud:
                self._remoto(self.cfg.comando_salud, "salud")
        except ErrorDespliegue as exc:
            # Paso 6: rollback automático al release previo más reciente (si existe).
            if anteriores:
                log.error("Salud fallida: rollback a %s", anteriores[-1])
                self._apuntar_current(f"{self.base}/releases/{anteriores[-1]}")
                if self.cfg.comando_reinicio:
                    # Sin _remoto: si este reinicio también falla, se informa el error original y no uno nuevo.
                    self.cx.ejecutar(self.cfg.comando_reinicio)
            raise ErrorDespliegue(f"Despliegue revertido: {exc}") from exc
        # Paso 7: sólo se limpia tras un despliegue sano.
        self.limpiar_viejos()
        return nombre

    def rollback(self) -> str:
        """Vuelve al release anterior al actual."""
        rels = self.listar_releases()
        # readlink devuelve la ruta destino de `current`; nos quedamos con el último componente (nombre del release).
        actual = self._remoto(f"readlink {q(self.base + '/current')}", "leer-current").strip().rsplit("/", 1)[-1]
        # Caso borde: no hay current, apunta a algo desconocido o ya es el release más viejo.
        if actual not in rels or rels.index(actual) == 0:
            raise ErrorDespliegue("No hay release anterior al que volver")
        destino = rels[rels.index(actual) - 1]
        self._apuntar_current(f"{self.base}/releases/{destino}")
        if self.cfg.comando_reinicio:
            self._remoto(self.cfg.comando_reinicio, "reiniciar")
        return destino

    def limpiar_viejos(self) -> list[str]:
        """Borra los releases más viejos y conserva los N más recientes; devuelve los borrados."""
        rels = self.listar_releases()
        # Con releases_a_conservar <= 0 no se borra nada: con un negativo, rels[:-(-1)] = rels[:1] borraría releases por error.
        sobran = rels[:-self.cfg.releases_a_conservar] if self.cfg.releases_a_conservar > 0 else []
        for r in sobran:
            self._remoto(f"rm -rf {q(self.base + '/releases/' + r)}", "limpiar")
        return sobran
