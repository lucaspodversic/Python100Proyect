"""Conexiones remotas detrás de una interfaz común.

- ConexionSSH: implementación real con paramiko (import perezoso).
- ConexionDryRun: no ejecuta nada; registra los comandos que correría.
Los tests usan un fake propio con la misma interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
# Resultado de un comando remoto: código de salida, stdout y stderr.
class ResultadoComando:
    codigo: int
    salida: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        # Convención Unix: 0 = éxito.
        return self.codigo == 0


# Interfaz común: SSH real, dry-run y los fakes de los tests la cumplen sin heredar.
class Conexion(Protocol):
    def ejecutar(self, comando: str) -> ResultadoComando: ...
    def cerrar(self) -> None: ...


class ConexionDryRun:
    """Simula la conexión: útil para revisar el plan antes de desplegar."""

    def __init__(self, respuestas: dict[str, ResultadoComando] | None = None):
        self.comandos: list[str] = []
        # Respuestas opcionales por prefijo de comando (p. ej. para simular el resultado de "ls").
        self.respuestas = respuestas or {}

    def ejecutar(self, comando: str) -> ResultadoComando:
        self.comandos.append(comando)
        # En dry-run devolvemos éxito; si se configuró una respuesta por prefijo, se usa
        for prefijo, r in self.respuestas.items():
            if comando.startswith(prefijo):
                return r
        return ResultadoComando(0, "")

    def cerrar(self) -> None:
        pass


class ConexionSSH:
    """Conexión real por SSH usando paramiko.

    Seguridad: se cargan los known_hosts del sistema y se RECHAZAN hosts
    desconocidos (RejectPolicy) para evitar ataques man-in-the-middle.
    """

    def __init__(self, host: str, usuario: str, puerto: int = 22, clave: str | None = None,
                 timeout: float = 15.0):
        # Así el paquete funciona (plan/tests) aunque paramiko no esté instalado.
        import paramiko  # import perezoso: dependencia opcional

        self._cliente = paramiko.SSHClient()
        # ~/.ssh/known_hosts: sólo se conecta a servidores cuya clave ya se verificó antes.
        self._cliente.load_system_host_keys()
        self._cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
        # Autenticación por clave (key_filename) o por el agente SSH; nunca se guardan contraseñas.
        self._cliente.connect(host, port=puerto, username=usuario, key_filename=clave, timeout=timeout)

    def ejecutar(self, comando: str) -> ResultadoComando:
        _, out, err = self._cliente.exec_command(comando)
        # Bloquea hasta que el comando remoto termina y devuelve su código de salida.
        codigo = out.channel.recv_exit_status()
        return ResultadoComando(codigo, out.read().decode(), err.read().decode())

    def cerrar(self) -> None:
        self._cliente.close()
