"""Tests offline: todo sale de paquetes sintéticos; la captura en vivo se prueba con sniff
simulado.
"""
import json

import pytest

from trafico import fuentes
from trafico.analisis import Estadisticas, clasificar
from trafico.cli import main
from trafico.fuentes import ErrorFuente, capturar_vivo, leer_pcap
from trafico.informe import a_texto, humano


def test_clasificar(paquetes):
    """Cada paquete devuelve (protocolo, origen, destino, puerto de servicio). En la respuesta
    DNS el puerto de servicio es 53 aunque sea el puerto de origen: se elige el puerto
    conocido, no el efímero.
    """
    assert clasificar(paquetes[0]) == ("TCP", "10.0.0.5", "93.184.216.34", 443)
    assert clasificar(paquetes[8])[0::3] == ("UDP", 53)
    assert clasificar(paquetes[10])[0] == "ICMP"
    assert clasificar(paquetes[11])[:3] == ("ARP", "10.0.0.1", "10.0.0.5")
    assert clasificar(paquetes[12])[0] == "ICMPv6"


def test_leer_pcap_equivale_a_lista(pcap, paquetes):
    """Leer el pcap da lo mismo que procesar la lista: 13 paquetes, mismos bytes y duración de
    3 s (de t=0 a t=3.0).
    """
    a = Estadisticas().agregar_todos(leer_pcap(pcap))
    b = Estadisticas().agregar_todos(paquetes)
    assert a.paquetes == b.paquetes == 13
    assert a.bytes == b.bytes
    assert abs(a.duracion - 3.0) < 1e-6


def test_estadisticas_por_ip_y_protocolo(paquetes):
    """TCP = 5+3 = 8; quien más bytes envía es el servidor (3×1000 B); 10.0.0.5 aparece en 12
    paquetes (todos menos el IPv6); el puerto 443 suma los 8 TCP; la conversación
    principal es cliente↔servidor y el pico está en el segundo T0, que concentra los 8
    paquetes TCP (bps = bytes × 8).
    """
    e = Estadisticas().agregar_todos(paquetes)
    assert e.por_protocolo == {"TCP": 8, "UDP": 2, "ICMP": 1, "ARP": 1, "ICMPv6": 1}
    assert e.bytes_origen.most_common(1)[0][0] == "93.184.216.34"  # quien más envía (respuestas grandes)
    assert e.paquetes_ip["10.0.0.5"] == 12
    assert e.puertos["TCP/443 (https)"] == 8 and e.puertos["UDP/53 (dns)"] == 2
    (par, _), = e.conversaciones.most_common(1)
    assert par == ("10.0.0.5", "93.184.216.34")
    seg, pico = e.pico_bps()
    assert seg == 1_760_000_000 and pico == e.por_segundo[seg] * 8


def test_seudonimizar_estable_y_oculta(paquetes):
    """Con seudonimización las IP reales no aparecen en el informe y, con la misma clave, el
    seudónimo es estable (HMAC), así se pueden comparar informes.
    """
    e = Estadisticas(seudonimizar=True, clave=b"k" * 16).agregar_todos(paquetes)
    texto = a_texto(e)
    assert "10.0.0.5" not in texto and "ip-" in texto
    e2 = Estadisticas(seudonimizar=True, clave=b"k" * 16).agregar_todos(paquetes)
    assert e.bytes_origen == e2.bytes_origen


def test_humano():
    """Unidades binarias: 1536 B = 1.5 KiB; 3·1024³ = 3.0 GiB."""
    assert humano(500) == "500 B" and humano(1536) == "1.5 KiB" and humano(3 * 1024 ** 3) == "3.0 GiB"


def test_cli_texto_y_json(pcap, capsys):
    """La CLI produce el informe de texto (con nombres de servicio) y un JSON con los mismos
    totales.
    """
    assert main(["pcap", str(pcap), "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "Protocolos" in out and "TCP" in out and "https" in out
    assert main(["pcap", str(pcap), "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["paquetes"] == 13 and d["protocolos"]["TCP"]["paquetes"] == 8


def test_pcap_inexistente_o_invalido(tmp_path, capsys):
    """Archivo inexistente → código 1 (sin traceback); archivo que no es pcap → ErrorFuente."""
    assert main(["pcap", str(tmp_path / "no.pcap")]) == 1
    malo = tmp_path / "malo.pcap"
    malo.write_bytes(b"esto no es un pcap")
    with pytest.raises(ErrorFuente):
        list(leer_pcap(malo))


def test_vivo_exige_interfaz_propia(monkeypatch):
    """Solo se captura en interfaces que existen en ESTA máquina y con una cantidad de paquetes
    acotada.
    """
    monkeypatch.setattr(fuentes, "interfaces", lambda: ["lo", "eth0"])
    with pytest.raises(ErrorFuente, match="desconocida"):
        capturar_vivo("wlan-ajena")
    with pytest.raises(ErrorFuente, match="rango"):
        capturar_vivo("lo", cuenta=0)


def test_vivo_sin_permisos_da_mensaje_claro(monkeypatch):
    """Sin privilegios, sniff lanza PermissionError y se traduce a un mensaje que explica qué
    hacer. Además se verifica que NO se pide modo promiscuo.
    """
    import scapy.sendrecv
    monkeypatch.setattr(fuentes, "interfaces", lambda: ["lo"])
    def sniff_falso(**kw):
        """Reemplazo de sniff: verifica los argumentos y simula falta de permisos."""
        assert kw["iface"] == "lo" and kw["promisc"] is False
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(scapy.sendrecv, "sniff", sniff_falso)
    with pytest.raises(ErrorFuente, match="privilegios"):
        capturar_vivo("lo", cuenta=5)
