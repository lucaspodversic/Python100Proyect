"""Tests del parser de líneas y lectura de archivos."""
import gzip
from datetime import timedelta, timezone

from logweb.parser import abrir, leer, parsear_fecha, parsear_linea

COMBINED = ('127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /a%20b.gif?x=1 HTTP/1.0" 200 2326 '
            '"http://ejemplo.com/inicio" "Mozilla/4.08 [en] (Win98; I ;Nav)"')


def test_combined_completo():
    """El ejemplo de la documentación de Apache: todos los campos, ruta decodificada y query separada."""
    r = parsear_linea(COMBINED)
    assert r is not None
    assert (r.ip, r.usuario, r.metodo, r.ruta, r.query, r.protocolo) == ("127.0.0.1", "frank", "GET", "/a b.gif", "x=1", "HTTP/1.0")
    assert (r.estado, r.bytes, r.referer, r.agente) == (200, 2326, "http://ejemplo.com/inicio", "Mozilla/4.08 [en] (Win98; I ;Nav)")
    assert r.fecha.utcoffset() == timedelta(hours=-7)


def test_common_log_format_sin_referer_ni_agente():
    """CLF (sin los dos campos finales) también se acepta; bytes "-" se toma como 0."""
    r = parsear_linea('10.0.0.1 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 304 -')
    assert r and r.referer is None and r.agente is None and r.bytes == 0 and r.usuario is None


def test_comillas_escapadas_y_campos_extra():
    r"""Nginx escapa comillas como \\" dentro del user-agent; un campo extra al final ($request_time) se ignora."""
    r = parsear_linea('1.2.3.4 - - [01/Jan/2026:00:00:00 +0000] "GET / HTTP/1.1" 200 1 "-" "Agente \\"raro\\"" 0.123')
    assert r and r.agente == 'Agente \\"raro\\"'


def test_lineas_invalidas():
    """Basura, fecha imposible, mes inexistente y petición de un solo token → None (no excepción)."""
    assert parsear_linea("hola mundo") is None
    assert parsear_linea('1.1.1.1 - - [99/Foo/2026:00:00:00 +0000] "GET / HTTP/1.1" 200 1') is None
    assert parsear_linea('1.1.1.1 - - [01/Jan/2026:00:00:00 +0000] "\\x16\\x03" 400 1') is None


def test_http09_dos_tokens():
    """Una petición "GET /" sin protocolo (HTTP/0.9) es válida."""
    r = parsear_linea('1.1.1.1 - - [01/Jan/2026:00:00:00 +0000] "GET /" 200 1')
    assert r and r.protocolo == "HTTP/0.9"


def test_fecha_independiente_del_locale():
    """'Oct' se interpreta sin depender del locale del sistema; la zona se respeta."""
    d = parsear_fecha("01/Oct/2026:12:00:00 +0200")
    assert d.astimezone(timezone.utc).hour == 10 and d.month == 10


def test_leer_fixtures(apache, nginx):
    """Apache: 16 válidas + 1 inválida. Nginx: 6 + 1 (el handshake TLS). La IPv6 se parsea bien."""
    a = leer(abrir(apache))
    assert (len(a.registros), a.invalidas) == (16, 1) and a.ejemplos_invalidos == ["esto no es una línea de log"]
    n = leer(abrir(nginx))
    assert (len(n.registros), n.invalidas) == (6, 1)
    assert any(r.ip == "2001:db8::1" for r in n.registros)


def test_lineas_vacias_no_cuentan(tmp_path):
    """Líneas en blanco (p. ej. al final del archivo) no se cuentan como inválidas."""
    lec = leer(["\n", "   \n", COMBINED + "\n"])
    assert (len(lec.registros), lec.invalidas) == (1, 0)


def test_gz_transparente(tmp_path, apache):
    """Un log rotado y comprimido (access.log.1.gz) se lee igual que el original."""
    gz = tmp_path / "access.log.1.gz"
    gz.write_bytes(gzip.compress(apache.read_bytes()))
    assert len(leer(abrir(gz)).registros) == 16
