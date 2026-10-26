"""Métricas de evaluación: exactitud, precisión/recall/F1 por clase y matriz de confusión."""
from __future__ import annotations

from collections import Counter


def matriz_confusion(reales: list[str], predichas: list[str], etiquetas: list[str]) -> list[list[int]]:
    """filas = clase real, columnas = clase predicha."""
    idx = {e: i for i, e in enumerate(etiquetas)}
    m = [[0] * len(etiquetas) for _ in etiquetas]
    # strict=True: si las listas tienen distinto largo es un error (ValueError),
    # no se trunca en silencio.
    for r, p in zip(reales, predichas, strict=True):
        m[idx[r]][idx[p]] += 1
    return m


def reporte(reales: list[str], predichas: list[str], etiquetas: list[str]) -> dict:
    aciertos = sum(r == p for r, p in zip(reales, predichas, strict=True))
    vp = Counter(r for r, p in zip(reales, predichas) if r == p)
    pred = Counter(predichas)
    real = Counter(reales)
    por_clase = {}
    for e in etiquetas:
        # Precisión = aciertos de la clase / veces que se predijo esa clase.
        # Recall = aciertos / veces que la clase era la real. F1 = media armónica.
        # Los "if" evitan dividir por cero cuando una clase no aparece.
        precision = vp[e] / pred[e] if pred[e] else 0.0
        recall = vp[e] / real[e] if real[e] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        por_clase[e] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "soporte": real[e]}
    # F1 macro: promedio simple solo de las clases presentes en los datos,
    # para no hundir la métrica con clases sin ejemplos.
    con_soporte = [v["f1"] for v in por_clase.values() if v["soporte"]]
    return {"exactitud": round(aciertos / len(reales), 3) if reales else 0.0,
            "f1_macro": round(sum(con_soporte) / len(con_soporte), 3) if con_soporte else 0.0,
            "por_clase": por_clase, "matriz": matriz_confusion(reales, predichas, etiquetas)}


def tabla_matriz(m: list[list[int]], etiquetas: list[str]) -> str:
    """Matriz como texto alineado para la consola."""
    # Columnas de 7 caracteres; los encabezados se recortan a 6 para que entren.
    ancho = max(map(len, etiquetas)) + 1
    filas = ["real\\pred".ljust(ancho) + "".join(e[:6].rjust(7) for e in etiquetas)]
    filas += [e.ljust(ancho) + "".join(str(v).rjust(7) for v in fila) for e, fila in zip(etiquetas, m)]
    return "\n".join(filas)
