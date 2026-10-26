"""Salidas del informe: texto para terminal, JSON y HTML autocontenido."""
from __future__ import annotations

import html
import json
from dataclasses import asdict

from .analisis import Informe


def humano(n: float) -> str:
    """Bytes en unidades binarias: 1536 → '1.5 KiB'."""
    for unidad in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unidad == "GiB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} TiB"  # inalcanzable, pero deja contento al type checker


def barra(valor: int, maximo: int, ancho: int = 30) -> str:
    """Barra ASCII proporcional (para el histograma por hora en la terminal)."""
    return "█" * round(ancho * valor / maximo) if maximo else ""


def a_texto(inf: Informe) -> str:
    """Informe legible en consola: resumen general y las tablas de top que no estén vacías."""
    if not inf.peticiones:
        return f"Sin peticiones válidas ({inf.invalidas} líneas inválidas)."
    l = [
        f"Período: {inf.primera} → {inf.ultima}",
        f"Peticiones: {inf.peticiones}   Tráfico: {humano(inf.bytes_totales)}   Líneas inválidas: {inf.invalidas}",
        f"Páginas vistas: {inf.paginas_vistas}   Visitas: {inf.visitas}   Visitantes únicos: {inf.visitantes_unicos}",
        f"Tasa de error (4xx+5xx): {inf.tasa_error:.1%}   Por clase: {inf.por_clase}",
        f"Dispositivos: {inf.dispositivos}",
    ]

    def tabla(titulo: str, filas: list[tuple[str, int]]) -> None:
        """Agrega una tabla 'cantidad  clave' si hay filas."""
        if filas:
            l.append(f"\n{titulo}")
            l.extend(f"  {n:6d}  {k}" for k, n in filas)

    tabla("Páginas más vistas", inf.top_paginas)
    tabla("404 más frecuentes", inf.top_404)
    tabla("Errores 5xx", inf.top_5xx)
    tabla("IPs con más peticiones", inf.top_ips)
    tabla("Referers", inf.top_referers)
    tabla(f"IPs sospechosas (muchos 4xx)", inf.sospechosos)
    if inf.trafico_por_hora:
        l.append("\nTráfico por hora (UTC)")
        m = max(inf.trafico_por_hora.values())
        l.extend(f"  {h}  {humano(b):>10}  {barra(b, m)}" for h, b in inf.trafico_por_hora.items())
    return "\n".join(l)


def a_json(inf: Informe) -> str:
    """Informe completo en JSON (UTF-8 legible, indentado)."""
    d = asdict(inf)
    d["por_estado"] = {str(k): v for k, v in inf.por_estado.items()}  # JSON exige claves string
    return json.dumps(d, ensure_ascii=False, indent=2)


def a_html(inf: Informe) -> str:
    """HTML sin JS ni CSS externos: se puede mandar por mail o abrir offline.
    Todo valor que viene del log se escapa (rutas, referers y UAs los controla el atacante → XSS)."""
    e = lambda x: html.escape(str(x))  # noqa: E731

    def tabla(titulo: str, filas) -> str:
        """Tabla HTML con las claves escapadas: las rutas y referers vienen del log, que
        controla cualquiera que haga una petición, así que sin escapar serían XSS.
        """
        cuerpo = "".join(f"<tr><td>{e(k)}</td><td>{n}</td></tr>" for k, n in filas)
        return f"<h2>{e(titulo)}</h2><table>{cuerpo}</table>" if filas else ""

    m = max(inf.peticiones_por_hora.values(), default=0)
    barras = "".join(f'<div class="b"><span>{e(h)}</span><i style="width:{100 * v / m:.0f}%"></i>{v}</div>'
                     for h, v in inf.peticiones_por_hora.items())
    return f"""<!doctype html><html lang="es"><meta charset="utf-8"><title>Informe de accesos</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:auto}}td{{padding:2px 8px}}
.b{{display:flex;gap:8px;align-items:center}}.b span{{width:130px}}.b i{{background:#4a7;height:12px;display:block}}</style>
<h1>Informe de accesos</h1>
<p>{e(inf.primera)} → {e(inf.ultima)}<br>Peticiones: {inf.peticiones} · Tráfico: {humano(inf.bytes_totales)} ·
Páginas vistas: {inf.paginas_vistas} · Visitas: {inf.visitas} · Visitantes: {inf.visitantes_unicos} ·
Errores: {inf.tasa_error:.1%}</p>
{tabla("Páginas más vistas", inf.top_paginas)}{tabla("404", inf.top_404)}{tabla("5xx", inf.top_5xx)}
{tabla("IPs", inf.top_ips)}{tabla("IPs sospechosas", inf.sospechosos)}<h2>Peticiones por hora (UTC)</h2>{barras}</html>"""
