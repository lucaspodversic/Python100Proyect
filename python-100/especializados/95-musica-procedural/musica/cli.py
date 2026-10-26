r"""CLI.

    python -m musica --semilla 7 --tonica D --modo dorica --compases 16 --tempo 90 \\
        --wav pieza.wav --midi pieza.mid --reproducir
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .composicion import Compositor
from .sintesis import a_midi, guardar_wav, renderizar
from .teoria import ESCALAS, nombre_nota


def main(argv: list[str] | None = None) -> int:
    """Compone una pieza con los parámetros dados, imprime un resumen (tonalidad, progresión en
    números romanos, duración) y opcionalmente guarda WAV/MIDI o la reproduce. Un
    parámetro inválido (tónica, tempo, compases) termina con ``ap.error``: uso y código 2.
    """
    ap = argparse.ArgumentParser(prog="musica", description="Compositor procedural")
    ap.add_argument("--semilla", type=int)
    ap.add_argument("--tonica", default="C")
    ap.add_argument("--modo", default="mayor", choices=list(ESCALAS))
    ap.add_argument("--compases", type=int, default=8)
    ap.add_argument("--tempo", type=int, default=100)
    ap.add_argument("--wav", type=Path)
    ap.add_argument("--midi", type=Path)
    ap.add_argument("--reproducir", action="store_true")
    a = ap.parse_args(argv)
    try:
        pieza = Compositor(a.tonica, a.modo, a.tempo, a.semilla).componer(a.compases)
    except ValueError as e:
        ap.error(str(e))
    romanos = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
    print(f"{a.tonica} {a.modo}, {a.tempo} bpm, {pieza.segundos:.1f} s")
    print("Progresión:", " – ".join(romanos[g] for g in pieza.progresion))
    print("Melodía:", " ".join(nombre_nota(n.altura) for n in pieza.melodia[:16]), "…")
    if a.midi:
        a.midi.write_bytes(a_midi(pieza))
        print(f"MIDI: {a.midi}")
    if a.wav or a.reproducir:
        señal = renderizar(pieza)
        if a.wav:
            guardar_wav(señal, a.wav)
            print(f"WAV: {a.wav}")
        if a.reproducir:
            from .reproductor import reproducir
            reproducir(señal)
    return 0
