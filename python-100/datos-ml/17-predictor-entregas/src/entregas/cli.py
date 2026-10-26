"""CLI::

    predictor-entregas evaluar
    predictor-entregas entrenar --salida modelo.joblib
    predictor-entregas predecir --modelo modelo.joblib --distancia 4.2 --hora 21 --clima lluvia --vehiculo moto
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .datos import generar_pedidos
from .modelo import PredictorEntregas, evaluar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="predictor-entregas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # evaluar no lleva opciones: compara el modelo contra los baselines con datos sintéticos.
    sub.add_parser("evaluar")
    e = sub.add_parser("entrenar")
    e.add_argument("--salida", type=Path, default=Path("modelo_entregas.joblib"))
    e.add_argument("--n", type=int, default=3000)
    p = sub.add_parser("predecir")
    p.add_argument("--modelo", type=Path, required=True)
    p.add_argument("--distancia", type=float, required=True)
    p.add_argument("--hora", type=int, default=20)
    p.add_argument("--dia", type=int, default=2, help="0=lunes … 6=domingo")
    # choices = las mismas categorías del generador; otra opción sería ignorada por el One-Hot.
    p.add_argument("--clima", default="despejado", choices=["despejado", "nublado", "lluvia", "tormenta"])
    p.add_argument("--vehiculo", default="moto", choices=["moto", "auto", "bici"])
    p.add_argument("--activos", type=int, default=1)
    p.add_argument("--preparacion", type=float, default=14)
    a = ap.parse_args(argv)

    if a.cmd == "evaluar":
        # Alineado a 24 caracteres para leer las métricas como una tabla.
        for k, v in evaluar(generar_pedidos()).items():
            print(f"{k:24s} {v:8.3f}")
    elif a.cmd == "entrenar":
        m = PredictorEntregas().entrenar(generar_pedidos(a.n))
        m.guardar(a.salida)
        print(f"Modelo guardado en {a.salida}\nImportancias:\n{m.importancias().head(6).round(3).to_string()}")
    else:
        m = PredictorEntregas.cargar(a.modelo)
        # Los nombres de los argumentos se traducen a las columnas del modelo (--dia → dia_semana, etc.).
        print(m.predecir_uno(distancia_km=a.distancia, hora=a.hora, dia_semana=a.dia, clima=a.clima,
                             vehiculo=a.vehiculo, pedidos_activos=a.activos, preparacion_min=a.preparacion).texto())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
