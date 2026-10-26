"""Genera un pcap sintético y determinista con wrpcap (no hay captura real en los tests)."""
import pytest
from scapy.layers.inet import ICMP, IP, TCP, UDP
from scapy.layers.inet6 import ICMPv6EchoRequest, IPv6
from scapy.layers.l2 import ARP, Ether
from scapy.packet import Raw
from scapy.utils import wrpcap

T0 = 1_760_000_000.0


def _paquetes():
    """Arma 13 paquetes sintéticos con tiempos fijos a partir de T0 (= 1 760 000 000, un epoch
    arbitrario). Índices 0-4: 5 HTTPS 10.0.0.5→93.184.216.34 de 100 B de carga (t =
    0..0.4). 5-7: 3 respuestas de 1000 B (t = 0.5..0.7). 8-9: consulta y respuesta DNS.
    10: ICMP. 11: ARP. 12: ICMPv6 sobre IPv6 (t = 3.0). Así el pico cae en el segundo T0
    (8 paquetes) y la duración es de 3 s.
    """
    ps = []
    def add(p, t):
        """Fija el timestamp del paquete (lo que pcap guarda) y lo agrega a la lista."""
        p.time = T0 + t
        ps.append(p)
    e = Ether(src="02:00:00:00:00:01", dst="02:00:00:00:00:02")
    for i in range(5):  # 5 HTTPS cliente→servidor de 100 bytes de carga
        add(e / IP(src="10.0.0.5", dst="93.184.216.34") / TCP(sport=50000 + i, dport=443) / Raw(b"x" * 100), i * 0.1)
    for i in range(3):  # 3 respuestas grandes
        add(e / IP(src="93.184.216.34", dst="10.0.0.5") / TCP(sport=443, dport=50000) / Raw(b"y" * 1000), 0.5 + i * 0.1)
    add(e / IP(src="10.0.0.5", dst="1.1.1.1") / UDP(sport=53000, dport=53) / Raw(b"q" * 30), 1.0)
    add(e / IP(src="1.1.1.1", dst="10.0.0.5") / UDP(sport=53, dport=53000) / Raw(b"r" * 60), 1.1)
    add(e / IP(src="10.0.0.5", dst="10.0.0.1") / ICMP(), 2.0)
    add(Ether() / ARP(psrc="10.0.0.1", pdst="10.0.0.5"), 2.5)
    add(e / IPv6(src="fe80::1", dst="fe80::2") / ICMPv6EchoRequest(), 3.0)
    return ps


@pytest.fixture
def paquetes():
    """Los paquetes en memoria."""
    return _paquetes()


@pytest.fixture
def pcap(tmp_path):
    """Los mismos paquetes escritos en un .pcap temporal, para probar la lectura de archivos."""
    ruta = tmp_path / "muestra.pcap"
    wrpcap(str(ruta), _paquetes())
    return ruta
