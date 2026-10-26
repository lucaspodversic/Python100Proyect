"""Bucle con webcam (OpenCV). Opcional: no se usa en los tests.

Uso: ``python -m asistencia.camara galeria.json asistencia.db``
Teclas: q = salir.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .galeria import Galeria
from .pipeline import ExtractorFaceRecognition
from .registro import Registro
from .sistema import Sistema


def main(argv: list[str] | None = None) -> int:
    """Bucle de cámara real (opcional, requiere opencv y face_recognition): carga la galería,
    abre la cámara 0 y procesa fotogramas hasta Ctrl+C, mostrando los fichajes. Devuelve
    2 si faltan argumentos y 1 si no hay cámara. No se ejecuta en los tests.
    """
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2:
        print(__doc__)
        return 2
    import cv2  # dependencia opcional
    sistema = Sistema(ExtractorFaceRecognition(), Galeria.cargar(Path(argv[0])), Registro(argv[1]))
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("No se pudo abrir la cámara", file=sys.stderr)
        return 1
    try:
        n = 0
        while True:
            ok, frame = cam.read()
            if not ok:
                break
            n += 1
            if n % 5 == 0:  # analizar 1 de cada 5 fotogramas: la detección es costosa
                pequeño = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                for f in sistema.procesar(pequeño):
                    print(f"{f.momento:%H:%M:%S} {f.tipo:7} {f.persona}")
            cv2.imshow("Asistencia (q para salir)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cam.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
