"""Tests offline: carpetas temporales + notificador y SMTP falsos."""

from __future__ import annotations

from pathlib import Path

import pytest

from alertas import FakeNotificador, SMTPConfig, SMTPNotificador, Vigilante, comparar, tomar_instantanea
from alertas.cli import main


def test_instantanea_filtra_por_patron(tmp_path: Path) -> None:
    # Sólo el .xlsx coincide con el patrón; el .txt debe quedar fuera de la instantánea.
    (tmp_path / "informe.xlsx").write_text("a")
    (tmp_path / "notas.txt").write_text("b")
    inst = tomar_instantanea(tmp_path, ["*.xlsx"])
    assert list(inst) == ["informe.xlsx"]


def test_comparar_detecta_los_tres_tipos(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("1")
    (tmp_path / "b.csv").write_text("1")
    # Línea base con a.csv y b.csv; después se produce un cambio de cada tipo.
    antes = tomar_instantanea(tmp_path)
    (tmp_path / "a.csv").write_text("2")  # modificado
    (tmp_path / "b.csv").unlink()  # eliminado
    (tmp_path / "c.csv").write_text("3")  # creado
    tipos = {(c.tipo, c.ruta) for c in comparar(antes, tomar_instantanea(tmp_path))}
    # Comparamos como conjunto de (tipo, ruta) para no depender del orden de los cambios.
    assert tipos == {("modificado", "a.csv"), ("eliminado", "b.csv"), ("creado", "c.csv")}


def test_reescritura_sin_cambio_de_contenido_no_alerta(tmp_path: Path) -> None:
    f = tmp_path / "a.csv"
    f.write_text("igual")
    antes = tomar_instantanea(tmp_path)
    # Caso borde clave: reescribir el mismo contenido no debe disparar una alerta (falso positivo).
    f.write_text("igual")  # cambia mtime, no el hash
    assert comparar(antes, tomar_instantanea(tmp_path)) == []


def test_vigilante_primera_pasada_es_linea_base(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("1")
    fake = FakeNotificador()
    # Dominio .test reservado (RFC 2606): nunca resuelve a un servidor real.
    v = Vigilante(tmp_path, fake, ["equipo@empresa.test"])
    # Primera pasada: establece la línea base y no notifica nada.
    assert v.revisar() == []
    assert fake.enviados == []
    (tmp_path / "a.csv").write_text("2")
    cambios = v.revisar()
    assert [c.tipo for c in cambios] == ["modificado"]
    # El asunto dice "1 cambio(s)"; el cuerpo lista el archivo; los destinatarios se respetan.
    asunto, cuerpo, para = fake.enviados[0]
    assert "1 cambio" in asunto and "a.csv" in cuerpo and para == ["equipo@empresa.test"]


def test_estado_persistente_entre_reinicios(tmp_path: Path) -> None:
    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "a.csv").write_text("1")
    estado = tmp_path / "estado.json"
    # Primer "proceso": guarda la línea base en estado.json (fuera de la carpeta vigilada,
    # si no el propio estado aparecería como archivo modificado).
    Vigilante(datos, FakeNotificador(), ["x@y.test"], estado=estado).revisar()
    (datos / "a.csv").write_text("2")
    fake = FakeNotificador()
    # Un vigilante "nuevo" (proceso reiniciado) detecta el cambio gracias al estado.
    assert len(Vigilante(datos, fake, ["x@y.test"], estado=estado).revisar()) == 1
    assert len(fake.enviados) == 1


def test_bucle_con_dormir_inyectado(tmp_path: Path) -> None:
    # ``dormir`` inyectado: en vez de esperar de verdad, registramos los segundos pedidos.
    esperas: list[float] = []
    v = Vigilante(tmp_path, FakeNotificador(), ["x@y.test"])
    v.vigilar(intervalo=5, iteraciones=3, dormir=esperas.append)
    # 3 iteraciones → 2 esperas (no se duerme después de la última).
    assert esperas == [5, 5]


class SMTPFalso:
    """Imita smtplib.SMTP registrando las llamadas (no abre sockets)."""

    # Atributo de CLASE: guarda cada conexión creada para que el test la inspeccione después.
    instancias: list["SMTPFalso"] = []

    def __init__(self, host: str, puerto: int) -> None:
        self.host, self.puerto, self.llamadas, self.mensajes = host, puerto, [], []
        SMTPFalso.instancias.append(self)

    def __enter__(self) -> "SMTPFalso":
        return self

    # Al salir del ``with`` el SMTP real envía QUIT; lo registramos para verificar el cierre.
    def __exit__(self, *exc: object) -> None:
        self.llamadas.append("quit")

    def starttls(self) -> None:
        self.llamadas.append("starttls")

    def login(self, u: str, c: str) -> None:
        self.llamadas.append(f"login:{u}")

    def send_message(self, msg: object) -> None:
        self.mensajes.append(msg)


def test_smtp_notificador_usa_tls_login_y_envia() -> None:
    # Credenciales ficticias; el SMTP falso nunca abre un socket.
    cfg = SMTPConfig("smtp.empresa.test", 587, "bot", "secreto", "bot@empresa.test")
    SMTPNotificador(cfg, fabrica=SMTPFalso).enviar("Asunto ñ", "Cuerpo", ["a@b.test", "c@d.test"])
    s = SMTPFalso.instancias[-1]
    assert (s.host, s.puerto) == ("smtp.empresa.test", 587)
    # Verifica el ORDEN de seguridad: TLS antes del login, y el cierre al final.
    assert s.llamadas == ["starttls", "login:bot", "quit"]
    msg = s.mensajes[0]
    assert msg["To"] == "a@b.test, c@d.test" and msg["Subject"] == "Asunto ñ"


def test_config_desde_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    # monkeypatch restaura el entorno al terminar el test (no contamina otros tests).
    monkeypatch.setenv("ALERTAS_SMTP_HOST", "mail.test")
    monkeypatch.setenv("ALERTAS_SMTP_PUERTO", "2525")
    monkeypatch.setenv("ALERTAS_SMTP_STARTTLS", "0")
    cfg = SMTPConfig.desde_entorno()
    assert (cfg.host, cfg.puerto, cfg.starttls) == ("mail.test", 2525, False)


def test_cli_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.csv").write_text("1")
    # Una única iteración en dry-run: no duerme, no abre SMTP y termina con código 0.
    assert main([str(tmp_path), "--para", "x@y.test", "--iteraciones", "1", "--dry-run"]) == 0
