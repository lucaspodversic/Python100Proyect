"""Traduce reglas en acciones para la tienda."""

from __future__ import annotations

from .apriori import Regla


def sugerencias_layout(reglas: list[Regla], n: int = 5, lift_fuerte: float = 2.0) -> list[str]:
    """Una sugerencia por par de productos (evita repetir A→B y B→A)."""
    vistos: set[frozenset[str]] = set()
    salida = []
    for r in reglas:
        # A→B y B→A comparten la unión; las reglas vienen ordenadas por lift, así se queda la mejor.
        par = r.antecedente | r.consecuente
        if par in vistos:
            continue
        vistos.add(par)
        a, b = " + ".join(sorted(r.antecedente)), " + ".join(sorted(r.consecuente))
        # Lift ≥ 2 (el doble de lo esperado por azar): asociación fuerte → acción de layout/combo.
        # Si no, una sugerencia más suave basada en la confianza.
        if r.lift >= lift_fuerte:
            salida.append(f"Ubicar {b} cerca de {a} (lift {r.lift:.1f}); probar combo/promoción cruzada.")
        else:
            salida.append(f"Recomendar {b} en el checkout a quien lleva {a} (conf {r.confianza:.0%}).")
        if len(salida) >= n:
            break
    return salida
