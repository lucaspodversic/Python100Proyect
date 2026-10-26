"""Reglas de decisión puras: ¿like o pass?"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


def _norm(t: str) -> str:
    """Minúsculas sin acentos."""
    # NFKD + ASCII "ignore" quita tildes ("Sénderismo" → "senderismo"); strip() quita espacios.
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower().strip()


@dataclass
class Perfil:
    """Perfil mostrado por la app (datos ficticios en el mock)."""

    id: str
    nombre: str
    edad: int
    distancia_km: float
    bio: str = ""
    intereses: list[str] = field(default_factory=list)


@dataclass
class Preferencias:
    """Criterios del usuario."""

    edad_min: int = 18
    edad_max: int = 99
    distancia_max_km: float = 50
    intereses: list[str] = field(default_factory=list)
    # 0 = no exige intereses en común.
    intereses_minimos: int = 0  # cuántos intereses en común como mínimo
    palabras_excluidas: list[str] = field(default_factory=list)
    requiere_bio: bool = False


@dataclass
class Veredicto:
    """Decisión y motivo (para el log y para auditar el bot)."""

    like: bool
    motivo: str
    afinidad: int = 0  # cantidad de intereses en común


def decidir(p: Perfil, pref: Preferencias) -> Veredicto:
    """Evalúa un perfil contra las preferencias, regla por regla."""
    # Comparación encadenada con límites INCLUSIVOS (25 y 35 entran en el rango [25, 35]).
    if not pref.edad_min <= p.edad <= pref.edad_max:
        return Veredicto(False, f"edad {p.edad} fuera de [{pref.edad_min}, {pref.edad_max}]")
    # Estrictamente mayor: un perfil exactamente en el límite (20 km con máximo 20) se acepta.
    if p.distancia_km > pref.distancia_max_km:
        return Veredicto(False, f"distancia {p.distancia_km} km > {pref.distancia_max_km} km")
    # Una bio sólo con espacios cuenta como vacía.
    if pref.requiere_bio and not p.bio.strip():
        return Veredicto(False, "sin biografía")
    bio = _norm(p.bio)
    # Búsqueda por subcadena normalizada: "fumador" encuentra "Fumador social".
    for palabra in pref.palabras_excluidas:
        if _norm(palabra) in bio:
            return Veredicto(False, f"bio contiene '{palabra}'")
    # Intersección de conjuntos normalizados: no importan mayúsculas, tildes ni duplicados.
    comunes = {_norm(i) for i in p.intereses} & {_norm(i) for i in pref.intereses}
    if len(comunes) < pref.intereses_minimos:
        return Veredicto(False, f"{len(comunes)} intereses en común < {pref.intereses_minimos}", len(comunes))
    # Se informan los intereses comunes ordenados (salida determinista) o "-" si no hay.
    return Veredicto(True, f"ok ({len(comunes)} intereses en común: {', '.join(sorted(comunes)) or '-'})", len(comunes))
