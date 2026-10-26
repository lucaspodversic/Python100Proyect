"""Tests offline: FakeCliente y un ``service`` de Gmail falso (sin red ni OAuth)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from limpiador_correo import Correo, FakeCliente, GmailCliente, Motor, cargar_reglas

# "Ahora" fijo: las antigüedades en días de la bandeja son exactas.
AHORA = dt.datetime(2025, 6, 1, 12, 0)
# Se prueban las reglas de ejemplo reales del proyecto (4 reglas, ver reglas.ejemplo.json).
REGLAS = cargar_reglas(Path(__file__).parents[1] / "reglas.ejemplo.json")


def bandeja() -> FakeCliente:
    def c(id_: str, de: str, asunto: str, dias: int, **kw: Any) -> Correo:
        return Correo(id_, de, asunto, AHORA - dt.timedelta(days=dias), etiquetas=["INBOX", "UNREAD"], **kw)
    # Bandeja de 7 correos diseñada para ejercitar cada regla y cada caso borde:
    #   1: "% OFF" y 45 días > 30 → promo a la papelera
    #   2: promo de 3 días → todavía no (no cumple antigüedad)
    #   3: "Factura" con adjunto → Facturas
    #   4: dominio github.com → GitHub
    #   5: remitente protegido → no se toca aunque diga "Oferta" y tenga 90 días
    #   6: 20 MB > 10240 KB (10 MB) y 400 días > 365 → Adjuntos pesados
    #   7: subdominio de github.com, pero "newsletter" con 60 días → la regla 1 va primero y detiene
    correos = [
        c("1", "Tienda <ofertas@tienda.com>", "¡50% OFF sólo hoy!", 45),
        c("2", "Tienda <ofertas@tienda.com>", "Nuevo descuento", 3),  # reciente: no se toca
        c("3", "Proveedor <ventas@prov.com>", "Factura A-0001", 2, tiene_adjuntos=True),
        c("4", "GitHub <notifications@github.com>", "[repo] PR #12", 1),
        c("5", "Jefa <jefa@empresa.com>", "Oferta de proyecto", 90),  # protegida
        c("6", "Amigo <amigo@mail.com>", "Fotos", 400, tamano=20 * 1024 * 1024),
        c("7", "Alerts <x@alerts.github.com>", "newsletter", 60),  # subdominio + promo: gana la 1ª regla
    ]
    return FakeCliente({x.id: x for x in correos})


def test_clasificacion_dry_run_no_modifica() -> None:
    fake = bandeja()
    rep = Motor(fake, REGLAS, ["jefa@empresa.com"]).ejecutar(dry_run=True, ahora=AHORA)
    # 7 revisados, 1 protegido (la jefa); el correo 2 no cae en ninguna regla.
    assert rep.revisados == 7 and rep.protegidos == 1
    assert dict(rep.por_regla) == {"Promociones viejas a la papelera": ["1", "7"], "Facturas": ["3"],
                                   "Notificaciones de GitHub": ["4"], "Adjuntos pesados": ["6"]}
    assert fake.llamadas_modificar == 0 and fake.papelera_ids == []
    assert "[dry-run]" in rep.resumen()


def test_aplicar_acciones() -> None:
    fake = bandeja()
    Motor(fake, REGLAS, ["jefa@empresa.com"]).ejecutar(dry_run=False, ahora=AHORA)
    assert fake.papelera_ids == ["1", "7"]
    # Factura: se quitó INBOX (archivar) y UNREAD (leído); sólo queda la etiqueta nueva.
    assert fake.correos["3"].etiquetas == ["Finanzas/Facturas"]  # archivada y leída
    # GitHub: archivada (sin INBOX) pero sigue sin leer (la regla no marca leído).
    assert set(fake.correos["4"].etiquetas) == {"UNREAD", "Dev/GitHub"}
    # Pesados: sólo etiqueta, sigue en la bandeja para revisión manual.
    assert "INBOX" in fake.correos["6"].etiquetas and "Revisar/Pesados" in fake.correos["6"].etiquetas
    assert fake.correos["5"].etiquetas == ["INBOX", "UNREAD"]  # protegida
    assert fake.correos["2"].etiquetas == ["INBOX", "UNREAD"]


def test_destacados_estan_protegidos_y_detener_false() -> None:
    fake = bandeja()
    # El correo 1 se destaca → queda protegido aunque cumpla la regla de promociones.
    fake.correos["1"].etiquetas.append("STARRED")
    reglas = cargar_reglas([
        {"nombre": "a", "si": {"dominio": "github.com"}, "entonces": {"etiquetar": ["A"]}, "detener": False},
        {"nombre": "b", "si": {"remitente_contiene": "github"}, "entonces": {"etiquetar": ["B"]}},
        {"nombre": "promo", "si": {"remitente_contiene": "ofertas"}, "entonces": {"papelera": True}},
    ])
    rep = Motor(fake, reglas).ejecutar(dry_run=False, ahora=AHORA)
    # "a" tiene detener=False: 4 y 7 (dominio y subdominio de github.com) también llegan a "b".
    assert rep.por_regla["a"] == ["4", "7"] and rep.por_regla["b"] == ["4", "7"]
    # "promo" (remitente contiene "ofertas") alcanza 1 y 2, pero 1 está destacado.
    assert fake.papelera_ids == ["2"]  # el 1 está destacado


# ---------- Adaptador Gmail con un service falso ----------
class _Req:
    def __init__(self, resultado: Any) -> None:
        self.resultado = resultado

    def execute(self) -> Any:
        return self.resultado


class ServiceFalso:
    """Imita la cadena ``service.users().messages().list(...).execute()``."""

    def __init__(self) -> None:
        self.log: list[tuple[str, dict[str, Any]]] = []
        # Dos páginas: [a, b] con token y [c] sin token → listar debe juntar a, b, c.
        self.paginas = [{"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"}, {"messages": [{"id": "c"}]}]

    def users(self) -> "ServiceFalso":
        return self

    def messages(self) -> "ServiceFalso":
        return self

    def labels(self) -> "_Labels":
        return _Labels(self)

    def list(self, **kw: Any) -> _Req:
        self.log.append(("list", kw))
        return _Req(self.paginas[0 if kw["pageToken"] is None else 1])

    def get(self, **kw: Any) -> _Req:
        self.log.append(("get", kw))
        return _Req({"id": kw["id"], "labelIds": ["INBOX"], "sizeEstimate": 2048, "internalDate": "0", "payload": {
            "headers": [{"name": "From", "value": "Ana <ana@x.com>"}, {"name": "Subject", "value": "Hola"},
                        {"name": "Date", "value": "Mon, 05 May 2025 10:00:00 +0000"}],
            "parts": [{"filename": ""}, {"filename": "f.pdf"}]}})

    def batchModify(self, **kw: Any) -> _Req:  # noqa: N802 - nombre de la API
        self.log.append(("batchModify", kw))
        return _Req({})

    def trash(self, **kw: Any) -> _Req:
        self.log.append(("trash", kw))
        return _Req({})


class _Labels:
    def __init__(self, s: ServiceFalso) -> None:
        self.s = s

    def list(self, **kw: Any) -> _Req:
        # Sólo existe INBOX: pedir "Nueva" obliga a crearla (id "Label_9").
        return _Req({"labels": [{"name": "INBOX", "id": "INBOX"}]})

    def create(self, **kw: Any) -> _Req:
        self.s.log.append(("create_label", kw))
        return _Req({"id": "Label_9"})


def test_gmail_adaptador() -> None:
    s = ServiceFalso()
    g = GmailCliente(s)
    assert g.listar("in:inbox", 10) == ["a", "b", "c"]
    c = g.obtener("a")
    # "Mon, 05 May 2025 10:00:00 +0000" → 2025-05-05 10:00 naive; f.pdf cuenta como adjunto.
    assert c.email_remitente == "ana@x.com" and c.fecha == dt.datetime(2025, 5, 5, 10) and c.tiene_adjuntos
    assert g.id_etiqueta("Nueva") == "Label_9" and g.id_etiqueta("Nueva") == "Label_9"
    # Dos pedidos de la misma etiqueta → una sola creación gracias a la caché.
    assert sum(op == "create_label" for op, _ in s.log) == 1
    g.modificar([str(i) for i in range(2500)], ["X"], ["INBOX"])
    lotes = [kw["body"]["ids"] for op, kw in s.log if op == "batchModify"]
    # 2500 ids en lotes de 1000 → 1000 + 1000 + 500.
    assert [len(x) for x in lotes] == [1000, 1000, 500]
    g.papelera("a")
    assert s.log[-1] == ("trash", {"userId": "me", "id": "a"})
