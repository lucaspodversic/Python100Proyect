"""Escaneo TCP connect() con hilos.

AVISO: escanear sistemas sin autorización puede ser ilegal. Esta
herramienta NO tiene objetivo por defecto: el usuario debe indicar
explícitamente un host que le pertenezca o que esté autorizado a auditar.

Se usa el método "connect" (handshake completo) porque no requiere
privilegios de root y es el menos intrusivo.
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable

# Nombres de servicios comunes (sólo informativo)
SERVICIOS = {21: "ftp", 22: "ssh", 25: "smtp", 53: "dns", 80: "http", 110: "pop3",
             143: "imap", 443: "https", 3306: "mysql", 5432: "postgres", 6379: "redis", 8080: "http-alt"}
# Máximo de un puerto TCP (16 bits); el 0 está reservado.
LIMITE_PUERTOS = 65535


# Hereda de str: .value se serializa directo a JSON.
class EstadoPuerto(str, Enum):
    ABIERTO = "abierto"
    CERRADO = "cerrado"   # el host respondió RST (conexión rechazada)
    FILTRADO = "filtrado"  # timeout: posible firewall


@dataclass(frozen=True)
# Inmutable: los resultados vienen de hilos distintos y no deben modificarse después.
class ResultadoPuerto:
    puerto: int
    estado: EstadoPuerto
    servicio: str = ""
    banner: str = ""


def parsear_puertos(texto: str) -> list[int]:
    """Convierte '22,80,8000-8010' en una lista ordenada sin duplicados."""
    puertos: set[int] = set()
    # Cada parte es un puerto suelto ("22") o un rango inclusivo ("8000-8010").
    for parte in texto.split(","):
        parte = parte.strip()
        # Tolera comas sobrantes ("22,,80" o "22,").
        if not parte:
            continue
        if "-" in parte:
            # split("-", 1): "1-2-3" falla en int("2-3") con ValueError, que es lo deseado.
            ini, fin = (int(x) for x in parte.split("-", 1))
            if ini > fin:
                raise ValueError(f"Rango invertido: {parte}")
            # El set elimina duplicados entre partes solapadas ("20-23,22").
            puertos.update(range(ini, fin + 1))
        else:
            puertos.add(int(parte))
    # Caso borde: texto vacío, puerto 0 o mayor a 65535.
    if not puertos or min(puertos) < 1 or max(puertos) > LIMITE_PUERTOS:
        raise ValueError("Los puertos deben estar entre 1 y 65535")
    return sorted(puertos)


def probar_puerto(host: str, puerto: int, timeout: float = 0.5, leer_banner: bool = False) -> ResultadoPuerto:
    """Intenta conectar a un puerto y clasifica el resultado."""
    # El nombre es sólo una pista por número de puerto: no se verifica qué servicio corre realmente.
    servicio = SERVICIOS.get(puerto, "")
    try:
        # Handshake TCP completo: si se establece, el puerto está abierto.
        with socket.create_connection((host, puerto), timeout=timeout) as s:
            banner = ""
            if leer_banner:
                # Algunos servicios (ssh, smtp) envían un saludo al conectar
                s.settimeout(timeout)
                try:
                    # Se leen como máximo 256 bytes y no se envía nada: lectura pasiva del saludo.
                    banner = s.recv(256).decode("utf-8", "replace").strip()
                # Servicio que no saluda (p. ej. HTTP espera al cliente): banner vacío, sigue abierto.
                except (socket.timeout, OSError):
                    banner = ""
            return ResultadoPuerto(puerto, EstadoPuerto.ABIERTO, servicio, banner)
    # RST inmediato: hay host pero nadie escucha en ese puerto.
    except ConnectionRefusedError:
        return ResultadoPuerto(puerto, EstadoPuerto.CERRADO, servicio)
    # Sin respuesta en el plazo: típico de un firewall que descarta paquetes.
    except (socket.timeout, TimeoutError):
        return ResultadoPuerto(puerto, EstadoPuerto.FILTRADO, servicio)
    # Otros errores de red (host inalcanzable, sin ruta): se reportan como filtrado.
    except OSError:
        return ResultadoPuerto(puerto, EstadoPuerto.FILTRADO, servicio)


def escanear(host: str, puertos: Iterable[int], hilos: int = 50, timeout: float = 0.5,
             leer_banner: bool = False,
             sonda: Callable[..., ResultadoPuerto] = probar_puerto) -> list[ResultadoPuerto]:
    """Escanea los puertos en paralelo y devuelve resultados ordenados.

    `sonda` se puede reemplazar en tests para no tocar la red.
    """
    # Defensa en profundidad: además de la CLI, la librería también exige un host explícito.
    if not host:
        raise ValueError("Debe indicarse un host explícito (no hay objetivo por defecto)")
    ip = socket.gethostbyname(host)  # resolvemos una sola vez
    # Las conexiones son I/O: los hilos esperan en paralelo (el GIL no es un problema aquí).
    # max(1, hilos) evita un error si se pasa 0 o un negativo.
    with ThreadPoolExecutor(max_workers=max(1, hilos)) as pool:
        resultados = list(pool.map(lambda p: sonda(ip, p, timeout, leer_banner), puertos))
    # pool.map ya conserva el orden de entrada, pero se ordena por puerto por si la entrada no lo estaba.
    return sorted(resultados, key=lambda r: r.puerto)
