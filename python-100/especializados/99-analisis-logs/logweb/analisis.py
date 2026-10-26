"""Métricas sobre registros ya parseados.

Definiciones (las aclaramos porque cada herramienta usa las suyas):

* **Petición (hit)**: cada línea válida.
* **Página vista**: petición GET/HEAD con estado 2xx/304 a algo que NO es un
  recurso estático (css, js, imágenes, fuentes…) y que no hace un bot.
* **Visitante único**: par (IP, user-agent) distinto. Es una aproximación:
  NAT/proxies juntan personas, y una persona puede cambiar de IP.
* **Visita (sesión)**: secuencia de páginas vistas del mismo visitante sin
  pausas mayores a 30 minutos (convención de Google Analytics y otras).
* **Bot**: user-agent que contiene marcas típicas (bot, crawler, spider…).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import PurePosixPath

from .parser import Registro

ESTATICOS = {".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf", ".map"}
MARCAS_BOT = ("bot", "crawler", "spider", "slurp", "curl", "wget", "python-requests", "httpclient", "scrapy")
INACTIVIDAD = timedelta(minutes=30)


def es_bot(agente: str | None) -> bool:
    """Detecta crawlers y clientes automatizados buscando marcas conocidas (bot, spider, curl,
    python-requests…) en el user-agent, sin distinguir mayúsculas.
    """
    # Sin user-agent también lo tratamos como automatizado (los navegadores siempre lo envían).
    return agente is None or any(m in agente.lower() for m in MARCAS_BOT)


def es_estatico(ruta: str) -> bool:
    """True para recursos estáticos (CSS, JS, imágenes, fuentes) según la extensión, que no
    cuentan como páginas vistas.
    """
    return PurePosixPath(ruta).suffix.lower() in ESTATICOS


def tipo_dispositivo(agente: str | None) -> str:
    """Clasificación grosera por user-agent: bot / móvil / escritorio."""
    if es_bot(agente):
        return "bot"
    a = agente.lower()  # type: ignore[union-attr]
    return "móvil" if any(m in a for m in ("mobile", "android", "iphone", "ipad")) else "escritorio"


def es_pagina_vista(r: Registro) -> bool:
    """Página vista 'humana': GET/HEAD con respuesta 2xx o 304 (en caché del navegador), que no
    sea un recurso estático ni venga de un bot.
    """
    return (r.metodo in ("GET", "HEAD") and (200 <= r.estado < 300 or r.estado == 304)
            and not es_estatico(r.ruta) and not es_bot(r.agente))


@dataclass
class Informe:
    """Todas las métricas del análisis. Es un dataclass para poder exportarlo directo a JSON
    con asdict.
    """
    peticiones: int = 0
    bytes_totales: int = 0
    paginas_vistas: int = 0
    visitantes_unicos: int = 0
    visitas: int = 0
    primera: str = ""
    ultima: str = ""
    por_estado: dict[int, int] = field(default_factory=dict)
    por_clase: dict[str, int] = field(default_factory=dict)     # "2xx", "4xx"…
    tasa_error: float = 0.0                                       # (4xx + 5xx) / peticiones
    top_paginas: list[tuple[str, int]] = field(default_factory=list)
    top_404: list[tuple[str, int]] = field(default_factory=list)
    top_5xx: list[tuple[str, int]] = field(default_factory=list)
    top_ips: list[tuple[str, int]] = field(default_factory=list)
    top_referers: list[tuple[str, int]] = field(default_factory=list)
    dispositivos: dict[str, int] = field(default_factory=dict)
    trafico_por_hora: dict[str, int] = field(default_factory=dict)   # "2026-10-01 13h" (UTC) → bytes
    peticiones_por_hora: dict[str, int] = field(default_factory=dict)
    metodos: dict[str, int] = field(default_factory=dict)
    sospechosos: list[tuple[str, int]] = field(default_factory=list)  # IPs con muchos 4xx
    invalidas: int = 0


def analizar(registros: Iterable[Registro], top: int = 10, umbral_sospecha: int = 5, invalidas: int = 0) -> Informe:
    """Una sola pasada sobre los registros ordenados por fecha. Visitante = par (IP, user-
    agent); una visita termina tras 30 min sin páginas vistas. Los 'sospechosos' son IPs
    con ``umbral_sospecha`` o más respuestas 4xx (típico de escaneos). Los top se
    desempatan por clave para que el resultado no dependa del orden de entrada.
    """
    regs = sorted(registros, key=lambda r: r.fecha)  # ordenar es necesario para calcular sesiones
    inf = Informe(invalidas=invalidas)
    if not regs:
        return inf
    estados, clases, paginas, n404, n5xx, ips, refs, disp, metodos = (Counter() for _ in range(9))
    bytes_hora: dict[str, int] = defaultdict(int)
    pet_hora: dict[str, int] = defaultdict(int)
    errores_ip: Counter[str] = Counter()
    visitantes: set[tuple[str, str | None]] = set()
    ultima_vista: dict[tuple[str, str | None], object] = {}

    for r in regs:
        inf.peticiones += 1
        inf.bytes_totales += r.bytes
        estados[r.estado] += 1
        clases[f"{r.estado // 100}xx"] += 1
        ips[r.ip] += 1
        metodos[r.metodo] += 1
        # Agrupamos por hora en UTC para que logs de servidores en distintas zonas sean comparables.
        hora = r.fecha.astimezone(timezone.utc).strftime("%Y-%m-%d %Hh")
        bytes_hora[hora] += r.bytes
        pet_hora[hora] += 1
        if r.estado == 404:
            n404[r.ruta] += 1
        if r.estado >= 500:
            n5xx[r.ruta] += 1
        if 400 <= r.estado < 500:
            errores_ip[r.ip] += 1
        if r.referer and not r.referer.startswith("-"):
            refs[r.referer] += 1
        clave = (r.ip, r.agente)
        disp[tipo_dispositivo(r.agente)] += 1
        if es_pagina_vista(r):
            inf.paginas_vistas += 1
            paginas[r.ruta] += 1
            visitantes.add(clave)
            previa = ultima_vista.get(clave)
            # Nueva visita si es la primera página de este visitante o pasó más de 30 min.
            if previa is None or r.fecha - previa > INACTIVIDAD:  # type: ignore[operator]
                inf.visitas += 1
            ultima_vista[clave] = r.fecha

    inf.visitantes_unicos = len(visitantes)
    inf.primera, inf.ultima = regs[0].fecha.isoformat(), regs[-1].fecha.isoformat()
    inf.por_estado = dict(sorted(estados.items()))
    inf.por_clase = dict(sorted(clases.items()))
    inf.tasa_error = round((clases["4xx"] + clases["5xx"]) / inf.peticiones, 4)
    # most_common desempata por orden de inserción; ordenamos por (-cuenta, clave) para que sea determinista.
    orden = lambda c: sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))[:top]  # noqa: E731
    inf.top_paginas, inf.top_404, inf.top_5xx = orden(paginas), orden(n404), orden(n5xx)
    inf.top_ips, inf.top_referers = orden(ips), orden(refs)
    inf.dispositivos, inf.metodos = dict(sorted(disp.items())), dict(sorted(metodos.items()))
    inf.trafico_por_hora, inf.peticiones_por_hora = dict(sorted(bytes_hora.items())), dict(sorted(pet_hora.items()))
    inf.sospechosos = [(ip, n) for ip, n in orden(errores_ip) if n >= umbral_sospecha]
    return inf
