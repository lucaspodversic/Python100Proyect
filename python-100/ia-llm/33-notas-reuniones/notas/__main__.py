"""Uso: python -m notas audio.mp3 [salida.md]   (o un .json de segmentos para probar sin audio)."""
import sys
from pathlib import Path

from notas.analisis import a_markdown, analizar
from notas.llm import crear_proveedor
from notas.transcripcion import TranscriptorFalso, TranscriptorWhisperAPI


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__); return
    entrada = Path(argv[0])
    # Un .json de segmentos permite probar todo el flujo sin audio ni clave.
    tr = TranscriptorFalso(fixture=entrada) if entrada.suffix == ".json" else TranscriptorWhisperAPI()
    md = a_markdown(analizar(tr.transcribir(entrada), crear_proveedor()), titulo=entrada.stem)
    # Con segundo argumento se guarda a archivo; si no, se imprime.
    Path(argv[1]).write_text(md, encoding="utf-8") if len(argv) > 1 else print(md)


if __name__ == "__main__":
    main(sys.argv[1:])
