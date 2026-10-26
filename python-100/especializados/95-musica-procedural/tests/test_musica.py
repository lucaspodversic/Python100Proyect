"""Tests deterministas: las piezas se generan con semillas fijas y el audio se analiza
numéricamente (no se escucha).
"""
import wave

import numpy as np
import pytest

from musica.cli import main
from musica.composicion import RANGO_MELODIA, Compositor, progresion
from musica.sintesis import TASA, _vlq, a_midi, envolvente, guardar_wav, renderizar
from musica.teoria import Escala, frecuencia, nombre_nota, tonica_midi
import random


def test_teoria():
    """Tónicas por nombre inglés, con bemoles o en solfeo (La = A = 69). Do mayor: I = C-E-G
    (60, 64, 67), V = G-B-D (67, 71, 74) y vii° = B-D-F (71, 74, 77). Los grados -1 y 7
    dan B3 (59) y C5 (72). La menor: A-C-E (69, 72, 76).
    """
    assert tonica_midi("C") == 60 and tonica_midi("A") == 69 and tonica_midi("Bb") == 70 and tonica_midi("La") == 69
    assert frecuencia(69) == 440 and round(frecuencia(60), 2) == 261.63
    assert nombre_nota(61) == "C#4"
    do = Escala(60)
    assert do.acorde(0) == (60, 64, 67) and do.acorde(4) == (67, 71, 74) and do.acorde(6) == (71, 74, 77)
    assert do.grado(-1) == 59 and do.grado(7) == 72
    la_menor = Escala(69, "menor")
    assert la_menor.acorde(0) == (69, 72, 76)
    with pytest.raises(ValueError):
        Escala(60, "lidia-inventada")


@pytest.mark.parametrize("semilla", range(5))
def test_progresion_cadencia(semilla):
    """Para varias semillas la progresión de 8 compases empieza en I y termina en V–I (cadencia
    perfecta).
    """
    p = progresion(random.Random(semilla), 8)
    assert len(p) == 8 and p[0] == 0 and p[-2:] == [4, 0]


@pytest.mark.parametrize("semilla, modo", [(1, "mayor"), (2, "menor"), (3, "dorica"), (4, "mixolidia")])
def test_reglas_melodia(semilla, modo):
    """Verifica las reglas de composición para varias semillas y modos: todas las notas están
    en la escala y en el rango, cada compás suma exactamente 4 tiempos, los tiempos
    fuertes son notas del acorde, termina en la tónica, ningún salto supera la octava y
    más del 40 % de los movimientos son de a lo sumo un tono.
    """
    c = Compositor("D", modo, 120, semilla)
    pieza = c.componer(8)
    esc = c.escala
    assert all(esc.contiene(n.altura) for n in pieza.melodia)                # todo en la escala
    assert all(RANGO_MELODIA[0] <= n.altura <= RANGO_MELODIA[1] for n in pieza.melodia)
    for compas, grado in enumerate(pieza.progresion):                        # compases completos
        notas = [n for n in pieza.melodia if compas * 4 <= n.inicio < compas * 4 + 4]
        assert sum(n.duracion for n in notas) == 4
        fuertes = [n for n in notas if (n.inicio - compas * 4) in (0, 2)]   # tiempos fuertes = notas del acorde
        assert fuertes and all(n.altura % 12 in esc.clases_acorde(grado) for n in fuertes)
    assert (pieza.melodia[-1].altura - esc.tonica) % 12 == 0                 # termina en la tónica
    saltos = [abs(b.altura - a.altura) for a, b in zip(pieza.melodia, pieza.melodia[1:])]
    assert max(saltos) <= 12 and sum(s <= 2 for s in saltos) / len(saltos) > 0.4  # mayoría por grado conjunto


def test_determinista_por_semilla():
    """Misma semilla → misma pieza; otra semilla → otra melodía."""
    a = Compositor(semilla=42).componer(8)
    b = Compositor(semilla=42).componer(8)
    c = Compositor(semilla=43).componer(8)
    assert a.melodia == b.melodia and a.bajo == b.bajo
    assert a.melodia != c.melodia


def test_validaciones():
    """Tempo 10 fuera de rango, 2 compases (el mínimo es 3: I + cadencia V–I) y tónica 'H'
    inválida.
    """
    with pytest.raises(ValueError):
        Compositor(tempo=10)
    with pytest.raises(ValueError):
        Compositor().componer(2)
    with pytest.raises(ValueError):
        Compositor("H")


def test_envolvente():
    """La envolvente arranca y termina en 0 (sin clics), no supera 1 y funciona aun con muy
    pocas muestras.
    """
    e = envolvente(1000)
    assert len(e) == 1000 and e[0] == 0 and abs(e[-1]) < 1e-9 and e.max() <= 1
    assert len(envolvente(10)) == 10


def test_render_y_wav(tmp_path):
    """4 compases a 120 bpm = 8 s, más 0.5 s de cola para que las notas se apaguen.
    Normalizado: el pico queda entre 0.85 y 1, sin saturar. El WAV es mono de 16 bits
    con todas las muestras.
    """
    pieza = Compositor(semilla=1, tempo=120).componer(4)   # 16 tiempos a 120 bpm = 8 s
    s = renderizar(pieza)
    assert len(s) == int((8 + 0.5) * TASA)
    assert 0.85 < np.max(np.abs(s)) <= 1.0                   # normalizado sin saturar
    ruta = guardar_wav(s, tmp_path / "x.wav")
    with wave.open(str(ruta)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, TASA, len(s))


def test_midi():
    """Cantidades de longitud variable (VLQ) del estándar MIDI: 7 bits por byte con el bit alto
    como 'continúa' (128 → 81 00). El archivo tiene cabecera MThd, una pista MTrk con su
    longitud correcta y termina con el evento de fin de pista (FF 2F 00). 0x90 = note-on
    en el canal 0.
    """
    assert _vlq(0) == b"\x00" and _vlq(127) == b"\x7f" and _vlq(128) == b"\x81\x00" and _vlq(0x0FFFFFFF) == b"\xff\xff\xff\x7f"
    pieza = Compositor(semilla=5).componer(4)
    m = a_midi(pieza)
    assert m[:4] == b"MThd" and m[14:18] == b"MTrk" and m.endswith(b"\xff\x2f\x00")
    assert int.from_bytes(m[18:22], "big") == len(m) - 22
    total = len(pieza.melodia) + len(pieza.bajo) + len(pieza.acordes)
    assert m.count(b"\x90") >= total // 3  # hay note-on en el canal de la melodía


def test_cli(tmp_path, capsys):
    """La CLI muestra la progresión en romanos (empieza en I y cierra V – I) y escribe WAV y
    MIDI válidos.
    """
    assert main(["--semilla", "3", "--compases", "4", "--wav", str(tmp_path / "a.wav"),
                 "--midi", str(tmp_path / "a.mid")]) == 0
    out = capsys.readouterr().out
    assert "Progresión: I" in out and "V – I" in out
    assert (tmp_path / "a.wav").stat().st_size > 1000 and (tmp_path / "a.mid").read_bytes()[:4] == b"MThd"


def test_reproducir_con_driver_dummy(monkeypatch):
    """Con el driver de audio 'dummy' de SDL se ejercita la reproducción sin placa de sonido."""
    pytest.importorskip("pygame")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")  # sin placa de sonido real
    from musica.reproductor import reproducir
    reproducir(np.zeros(TASA // 10))
