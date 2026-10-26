"""Presentación de las estadísticas: tabla de texto o JSON."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .analisis import Estadisticas


def humano(n: float) -> str:
    """Bytes en unidades binarias legibles: 1536 → '1.5 KiB'."""
    for unidad in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024 or unidad == "GiB":
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} GiB"  # pragma: no cover


def a_dict(e: Estadisticas, top: int = 10) -> dict:
    """Resumen serializable: totales, tasas, pico (con su hora en UTC) y los top N de cada
    categoría.
    """
    pico_seg, pico = e.pico_bps()
    return {
        "paquetes": e.paquetes, "bytes": e.bytes, "duracion_s": round(e.duracion, 3),
        "tasa_media_bps": round(e.tasa_media_bps(), 1), "pico_bps": pico,
        "pico_utc": datetime.fromtimestamp(pico_seg, timezone.utc).isoformat() if e.paquetes else None,
        "protocolos": {p: {"paquetes": n, "bytes": e.bytes_protocolo[p]} for p, n in e.por_protocolo.most_common()},
        "top_origen_bytes": e.bytes_origen.most_common(top),
        "top_destino_bytes": e.bytes_destino.most_common(top),
        "top_ip_paquetes": e.paquetes_ip.most_common(top),
        "top_puertos": e.puertos.most_common(top),
        "top_conversaciones": [[a, b, n] for (a, b), n in e.conversaciones.most_common(top)],
    }


def a_json(e: Estadisticas, top: int = 10) -> str:
    """Resumen en JSON legible (sin escapar acentos)."""
    return json.dumps(a_dict(e, top), ensure_ascii=False, indent=2)


def a_texto(e: Estadisticas, top: int = 10) -> str:
    """Informe de texto con tablas alineadas: protocolos con porcentaje, IPs, puertos y
    conversaciones.
    """
    d = a_dict(e, top)
    lineas = [f"Paquetes: {e.paquetes}   Bytes: {humano(e.bytes)}   Duración: {e.duracion:.2f} s",
              f"Tasa media: {d['tasa_media_bps'] / 1000:.1f} kbit/s   Pico: {d['pico_bps'] / 1000:.1f} kbit/s", ""]

    def tabla(titulo: str, filas: list[tuple[str, str]]) -> None:
        """Agrega una tabla con título, la primera columna alineada a la izquierda y la segunda
        a la derecha.
        """
        lineas.append(titulo)
        ancho = max((len(f[0]) for f in filas), default=0)
        lineas.extend(f"  {a.ljust(ancho)}  {b:>12}" for a, b in filas)
        lineas.append("")

    total = e.paquetes or 1
    tabla("Protocolos (paquetes, %):", [(p, f"{v['paquetes']} ({100 * v['paquetes'] / total:.1f}%)")
                                        for p, v in d["protocolos"].items()])
    tabla("Top IP origen (bytes):", [(ip, humano(n)) for ip, n in d["top_origen_bytes"]])
    tabla("Top IP destino (bytes):", [(ip, humano(n)) for ip, n in d["top_destino_bytes"]])
    tabla("Top puertos (paquetes):", [(p, str(n)) for p, n in d["top_puertos"]])
    tabla("Top conversaciones (bytes):", [(f"{a} ↔ {b}", humano(n)) for a, b, n in d["top_conversaciones"]])
    return "\n".join(lineas).rstrip() + "\n"
