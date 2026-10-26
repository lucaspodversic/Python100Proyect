"""Uso: python -m correo mensaje.eml "intención de la respuesta" [tono]
Imprime prioridad, resumen y guarda borrador.eml (NO envía nada)."""
import sys
from pathlib import Path

from correo.asistente import construir_borrador, priorizar, redactar_respuesta, resumir
from correo.llm import crear_proveedor
from correo.parser import leer_eml


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print(__doc__); return
    c, llm = leer_eml(argv[0]), crear_proveedor()
    if llm.nombre == "falso":
        print("(modo demo: LLM falso; el resumen y el borrador serán de prueba)")
    p = priorizar(c)
    print(f"Prioridad: {p.nivel} ({', '.join(p.motivos) or 'sin señales'})\n{resumir(c, llm)}")
    cuerpo = redactar_respuesta(c, llm, argv[1], argv[2] if len(argv) > 2 else "cordial")
    # Se escribe un .eml para abrir/revisar en el cliente de correo; jamás se envía.
    Path("borrador.eml").write_bytes(bytes(construir_borrador(c, cuerpo, ("Yo", "yo@ejemplo.com"))))
    print("Borrador guardado en borrador.eml")


if __name__ == "__main__":
    main(sys.argv[1:])
