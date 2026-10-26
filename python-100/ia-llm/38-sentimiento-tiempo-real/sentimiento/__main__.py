"""Demo: python -m sentimiento <archivo.jsonl> <consulta> [ciclos]  (fuente local, sin red)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sentimiento.fuentes import FuenteArchivo
from sentimiento.llm import crear_proveedor
from sentimiento.monitor import Monitor


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print(__doc__); return
    # Con el proveedor falso se pasa llm=None: así se usa directamente el léxico
    # en lugar de un "LLM" que no sabe clasificar.
    m = Monitor([FuenteArchivo(argv[0])], argv[1], llm=None if crear_proveedor().nombre == "falso" else crear_proveedor())
    # Reloj simulado: arranca en la fecha de la primera publicación del archivo
    # y avanza 5 minutos por ciclo (cada ciclo "llegan" 5 publicaciones nuevas).
    primera = json.loads(Path(argv[0]).read_text(encoding="utf-8").splitlines()[0])
    t = datetime.fromisoformat(primera["fecha"])
    for i in range(int(argv[2]) if len(argv) > 2 else 4):
        alerta = m.ciclo(t + timedelta(minutes=5 * i))
        print(f"ciclo {i}: {m.metricas()}" + (f"  🚨 ALERTA {alerta.proporcion_negativa:.0%} negativo" if alerta else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
