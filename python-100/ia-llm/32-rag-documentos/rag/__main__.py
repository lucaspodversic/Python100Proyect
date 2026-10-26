"""CLI:
  python -m rag indexar <carpeta> indice.json
  python -m rag preguntar indice.json "¿pregunta?"
"""
import sys

from rag.documentos import cargar_carpeta
from rag.embeddings import IndiceVectorial
import re

from rag.llm import ProveedorFalso, crear_proveedor
from rag.pipeline import RAG


def main(argv: list[str]) -> None:
    if len(argv) == 3 and argv[0] == "indexar":
        # Indexar una vez y guardar en JSON: preguntar después no re-lee los documentos.
        ind = IndiceVectorial(); ind.indexar(cargar_carpeta(argv[1])); ind.guardar(argv[2])
        print(f"Indexados {len(ind.fragmentos)} fragmentos")
    elif len(argv) == 3 and argv[0] == "preguntar":
        llm = crear_proveedor()
        if llm.nombre == "falso":
            # Modo demo sin LLM: devuelve la primera oración de la fuente [1] citándola
            def demo(ms):
                # ms[1] es el mensaje de usuario con "[1] (archivo) texto...": se toma la
                # primera oración (hasta . ! o ?) de la fuente 1.
                m = re.search(r"\[1\] \([^)]*\) (.+?[.!?])", ms[1].contenido)
                return f"{m.group(1)} [1]" if m else "NO_SE"
            llm = ProveedorFalso(funcion=demo)
            print("(modo demo: sin LLM configurado; usá LLM_PROVEEDOR=openai|anthropic)")
        r = RAG(IndiceVectorial.cargar(argv[1]), llm).preguntar(argv[2])
        print(r.texto)
        # Se muestran solo las fuentes efectivamente citadas, con su similitud.
        for c in r.citas:
            print(f"  [{c['n']}] {c['id']} (similitud {c['puntaje']})")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
