"""Uso: python -m nlsql base.db "¿pregunta?"   (python -m nlsql --demo demo.db crea una base)"""
import sys

from nlsql.demo import crear_base_demo
from nlsql.ejecutor import conectar_solo_lectura
from nlsql.llm import crear_proveedor
from nlsql.traductor import TraductorNLSQL


def main(argv: list[str]) -> None:
    if len(argv) == 2 and argv[0] == "--demo":
        crear_base_demo(argv[1]); print("Base creada"); return
    if len(argv) != 2:
        print(__doc__); return
    llm = crear_proveedor()
    # Traducir lenguaje natural requiere un LLM real: el falso no sabe SQL.
    if llm.nombre == "falso":
        print("Configurá LLM_PROVEEDOR=openai|anthropic y su clave (variable de entorno) para traducir."); return
    # Siempre solo lectura y con la columna sensible de la demo oculta.
    t = TraductorNLSQL(conectar_solo_lectura(argv[0]), llm, ocultas={"clientes.password_hash"})
    r = t.preguntar(argv[1])
    print(r.sql)
    print(r.error or "\n".join([" | ".join(r.columnas)] + [" | ".join(map(str, f)) for f in r.filas]))


if __name__ == "__main__":
    main(sys.argv[1:])
