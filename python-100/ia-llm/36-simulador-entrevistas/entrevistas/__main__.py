"""Uso: python -m entrevistas [rol] [nivel] [n_preguntas]   (ej.: backend junior 3)"""
import json
import sys

from entrevistas.banco import cargar_banco, seleccionar
from entrevistas.llm import crear_proveedor
from entrevistas.sesion import Sesion


def main(argv: list[str]) -> None:
    # Completa los argumentos faltantes con valores por defecto: si se pasó
    # solo el rol, se toman nivel y cantidad de la lista de defaults.
    rol, nivel, n = (argv + ["backend", "junior", "3"][len(argv):])[:3]
    s = Sesion(seleccionar(cargar_banco(), rol, nivel, int(n)), crear_proveedor())
    pregunta = s.iniciar()
    # responder() devuelve None como siguiente pregunta cuando se termina.
    while pregunta:
        print(f"\n🗣  {pregunta}")
        ev, pregunta = s.responder(input("> "))
        print(f"   Puntaje {ev.puntaje}/10 · mejoras: {'; '.join(ev.mejoras) or '-'}")
    print(json.dumps(s.informe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
