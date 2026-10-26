"""Tests SOLO contra 127.0.0.1 con sockets que abre el propio test."""
import json
import socket
import threading

import pytest

from escaner import EstadoPuerto, escanear, parsear_puertos
from escaner.cli import ejecutar
from escaner.nucleo import probar_puerto


@pytest.fixture
def servidor_local():
    """Abre un socket en 127.0.0.1 en un puerto libre y envía un banner."""
    # Puerto 0 = el SO elige uno libre: los tests no chocan con servicios reales de la máquina.
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(5)
    puerto = srv.getsockname()[1]
    parar = threading.Event()

    # Hilo que acepta conexiones y responde un banner tipo SSH, luego cierra.
    def atender():
        # accept con timeout para poder revisar periódicamente la señal de parada.
        srv.settimeout(0.2)
        while not parar.is_set():
            try:
                c, _ = srv.accept()
            except (socket.timeout, OSError):
                continue
            try:
                c.sendall(b"SSH-2.0-Prueba\r\n")
            finally:
                c.close()
    t = threading.Thread(target=atender, daemon=True); t.start()
    # Al terminar el test se detiene el hilo y se cierra el socket.
    yield puerto
    parar.set(); t.join(1); srv.close()


def puerto_cerrado() -> int:
    """Obtiene un puerto libre y lo libera: nadie escucha ahí."""
    # Se reserva un puerto libre y se suelta: queda un puerto donde (casi seguro) nadie escucha.
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


# Espacios, desorden y solapamiento (22 aparece dos veces) → lista ordenada única.
def test_parsear_puertos():
    assert parsear_puertos("80, 22,20-23") == [20, 21, 22, 23, 80]


# Puerto 0, fuera de rango, rango invertido y texto vacío.
@pytest.mark.parametrize("malo", ["0", "70000", "10-5", ""])
def test_parsear_invalidos(malo):
    with pytest.raises(ValueError):
        parsear_puertos(malo)


# Puerto abierto y banner leído del servidor de prueba.
def test_abierto_con_banner(servidor_local):
    r = probar_puerto("127.0.0.1", servidor_local, 1.0, leer_banner=True)
    assert r.estado is EstadoPuerto.ABIERTO and r.banner.startswith("SSH-2.0")


def test_cerrado():
    assert probar_puerto("127.0.0.1", puerto_cerrado(), 0.5).estado is EstadoPuerto.CERRADO


# Un abierto y un cerrado en el mismo escaneo concurrente.
def test_escanear_mezcla(servidor_local):
    cerrado = puerto_cerrado()
    res = escanear("127.0.0.1", [cerrado, servidor_local], hilos=4, timeout=0.5)
    estados = {r.puerto: r.estado for r in res}
    assert estados[servidor_local] is EstadoPuerto.ABIERTO
    assert estados[cerrado] is EstadoPuerto.CERRADO


def test_sin_host_falla():
    with pytest.raises(ValueError):
        escanear("", [80])


# Con una sonda falsa no se toca la red en absoluto.
def test_sonda_inyectable():
    from escaner.nucleo import ResultadoPuerto
    falsa = lambda h, p, t, b: ResultadoPuerto(p, EstadoPuerto.FILTRADO)
    assert all(r.estado is EstadoPuerto.FILTRADO for r in escanear("127.0.0.1", [1, 2], sonda=falsa))


# Sin --autorizado → exit 3 y ningún socket abierto.
def test_cli_exige_autorizacion(capsys):
    assert ejecutar(["--host", "127.0.0.1", "--puertos", "1"]) == 3


# Sin --host argparse aborta (SystemExit): no hay objetivo por defecto.
def test_cli_exige_host():
    with pytest.raises(SystemExit):
        ejecutar(["--autorizado"])


# Salida JSON parseable con el puerto abierto del servidor local.
def test_cli_json(servidor_local, capsys):
    assert ejecutar(["--host", "127.0.0.1", "--puertos", str(servidor_local), "--autorizado", "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos[0]["puerto"] == servidor_local and datos[0]["estado"] == "abierto"
