"""Fuentes de paquetes: archivo pcap (streaming) o captura en vivo.

La captura en vivo:

* requiere privilegios (root o ``CAP_NET_RAW``);
* exige nombrar **explícitamente** una interfaz local existente;
* no activa el modo promiscuo por defecto, así que solo ve el tráfico propio
  del equipo.

Usala únicamente en equipos y redes propios o con autorización por escrito:
capturar tráfico ajeno puede ser delito.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from scapy.packet import Packet
from scapy.utils import PcapReader


class ErrorFuente(Exception):
    """No se pudo leer el pcap o capturar (archivo inválido, interfaz inexistente, sin
    permisos).
    """
    pass


def leer_pcap(ruta: str | Path) -> Iterator[Packet]:
    """Itera paquetes sin cargar el archivo completo en memoria (pcap y pcapng)."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorFuente(f"no existe: {ruta}")
    try:
        with PcapReader(str(ruta)) as lector:
            yield from lector
    except Exception as e:  # Scapy lanza Scapy_Exception u OSError genéricos ante archivos dañados
        if isinstance(e, ErrorFuente):
            raise
        raise ErrorFuente(f"no es un pcap válido: {e}") from e


def interfaces() -> list[str]:
    """Interfaces de red de esta máquina según Scapy."""
    from scapy.interfaces import get_if_list
    return list(get_if_list())


def capturar_vivo(interfaz: str, cuenta: int = 100, timeout: float = 30, filtro: str | None = None,
                  promiscuo: bool = False) -> list[Packet]:
    """Captura en la interfaz propia indicada. Lanza ErrorFuente con un mensaje claro si falla."""
    if interfaz not in interfaces():
        raise ErrorFuente(f"interfaz desconocida: {interfaz!r}; disponibles: {', '.join(interfaces())}")
    if not (1 <= cuenta <= 1_000_000):
        raise ErrorFuente("cuenta fuera de rango")
    from scapy.sendrecv import sniff
    try:
        return list(sniff(iface=interfaz, count=cuenta, timeout=timeout, filter=filtro, promisc=promiscuo,
                          store=True))
    except PermissionError as e:
        raise ErrorFuente("se necesitan privilegios de captura (root o CAP_NET_RAW)") from e
    except OSError as e:
        raise ErrorFuente(f"no se pudo capturar: {e}") from e
