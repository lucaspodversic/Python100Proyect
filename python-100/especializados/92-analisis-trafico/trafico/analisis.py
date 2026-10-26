"""Acumulador de estadísticas de tráfico, en streaming y con memoria acotada.

Para cada paquete se clasifica:

* **protocolo**: TCP, UDP, ICMP, ICMPv6, ARP, otro-IP u otro;
* **IP origen y destino**: IPv4 o IPv6; ARP usa ``psrc``/``pdst``;
* **puerto de servicio**: el menor de los dos puertos, con nombre conocido
  (se asume que el efímero es el mayor);
* **conversación**: par de IPs sin orden.

Se cuentan paquetes y bytes (``len(paquete)`` = tamaño en el cable sin FCS).
Opcionalmente las IPs se **seudonimizan** con HMAC-SHA256 y una clave
aleatoria, para compartir informes sin exponer direcciones.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from scapy.layers.inet import ICMP, IP, TCP, UDP
from scapy.layers.inet6 import IPv6
from scapy.layers.l2 import ARP
from scapy.packet import Packet

SERVICIOS = {20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns", 67: "dhcp", 68: "dhcp",
             80: "http", 110: "pop3", 123: "ntp", 143: "imap", 443: "https", 445: "smb", 465: "smtps",
             587: "submission", 853: "dns-over-tls", 993: "imaps", 995: "pop3s", 1883: "mqtt", 3306: "mysql",
             3389: "rdp", 5353: "mdns", 5432: "postgres", 6379: "redis", 8080: "http-alt", 8443: "https-alt"}


def clasificar(p: Packet) -> tuple[str, str | None, str | None, int | None]:
    """Devuelve (protocolo, ip_origen, ip_destino, puerto_servicio)."""
    if ARP in p:
        return "ARP", p[ARP].psrc, p[ARP].pdst, None
    capa = IP if IP in p else IPv6 if IPv6 in p else None
    if capa is None:
        return "otro", None, None, None
    src, dst = p[capa].src, p[capa].dst
    for nombre, l4 in (("TCP", TCP), ("UDP", UDP)):
        if l4 in p:
            return nombre, src, dst, min(p[l4].sport, p[l4].dport)
    if ICMP in p:
        return "ICMP", src, dst, None
    if capa is IPv6 and p[IPv6].nh == 58:  # siguiente cabecera 58 = ICMPv6
        return "ICMPv6", src, dst, None
    return "otro-IP", src, dst, None


@dataclass
class Estadisticas:
    """Acumulador de estadísticas en una sola pasada (sirve para pcaps grandes o captura
    continua): totales, primer y último timestamp, contadores por protocolo, IP, puerto,
    conversación y bytes por segundo. Opcionalmente seudonimiza las IP.
    """
    seudonimizar: bool = False
    clave: bytes = field(default_factory=lambda: secrets.token_bytes(16))
    paquetes: int = 0
    bytes: int = 0
    primero: float | None = None
    ultimo: float | None = None
    por_protocolo: Counter = field(default_factory=Counter)        # paquetes
    bytes_protocolo: Counter = field(default_factory=Counter)
    bytes_origen: Counter = field(default_factory=Counter)
    bytes_destino: Counter = field(default_factory=Counter)
    paquetes_ip: Counter = field(default_factory=Counter)           # origen o destino
    puertos: Counter = field(default_factory=Counter)
    conversaciones: Counter = field(default_factory=Counter)        # bytes por par de IPs
    por_segundo: Counter = field(default_factory=Counter)           # bytes por segundo relativo

    def _ip(self, ip: str | None) -> str | None:
        """Con seudonimización reemplaza la IP por 'ip-' + 10 hex de HMAC-SHA256 con una clave
        aleatoria por ejecución: estable dentro del informe pero irreversible sin la
        clave.
        """
        if ip is None or not self.seudonimizar:
            return ip
        return "ip-" + hmac.new(self.clave, ip.encode(), hashlib.sha256).hexdigest()[:10]

    def agregar(self, p: Packet) -> None:
        """Procesa un paquete: tamaño, ventana de tiempo, clasificación y todos los contadores.
        La conversación se guarda con el par de IPs ordenado, así A→B y B→A suman
        juntos.
        """
        tam = len(p)
        t = float(p.time)
        self.paquetes += 1
        self.bytes += tam
        self.primero = t if self.primero is None else min(self.primero, t)
        self.ultimo = t if self.ultimo is None else max(self.ultimo, t)
        proto, src, dst, puerto = clasificar(p)
        src, dst = self._ip(src), self._ip(dst)
        self.por_protocolo[proto] += 1
        self.bytes_protocolo[proto] += tam
        if src:
            self.bytes_origen[src] += tam
            self.paquetes_ip[src] += 1
        if dst:
            self.bytes_destino[dst] += tam
            self.paquetes_ip[dst] += 1
        if src and dst:
            self.conversaciones[tuple(sorted((src, dst)))] += tam
        if puerto is not None:
            self.puertos[f"{proto}/{puerto} ({SERVICIOS.get(puerto, '?')})"] += 1
        self.por_segundo[int(t)] += tam

    def agregar_todos(self, paquetes: Iterable[Packet]) -> "Estadisticas":
        """Agrega una secuencia y devuelve self para encadenar."""
        for p in paquetes:
            self.agregar(p)
        return self

    @property
    def duracion(self) -> float:
        """Segundos entre el primer y el último paquete (0 si no hay)."""
        return (self.ultimo - self.primero) if self.paquetes else 0.0

    def tasa_media_bps(self) -> float:
        """Bits por segundo medios; con un solo instante se usa 1 s."""
        return self.bytes * 8 / max(self.duracion, 1.0)

    def pico_bps(self) -> tuple[int, float]:
        """(segundo epoch, bits/s) del segundo con más tráfico."""
        if not self.por_segundo:
            return (0, 0.0)
        seg, b = max(self.por_segundo.items(), key=lambda kv: (kv[1], -kv[0]))
        return seg, b * 8.0
