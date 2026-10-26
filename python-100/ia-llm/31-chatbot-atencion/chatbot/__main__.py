"""Chat por consola: `python -m chatbot` (usa LLM_PROVEEDOR=openai|anthropic|falso)."""
from pathlib import Path

from chatbot.bot import Chatbot
from chatbot.faq import BaseFAQ
from chatbot.llm import crear_proveedor


def main() -> None:
    faq = BaseFAQ.desde_json(Path(__file__).parent.parent / "datos" / "faq.json")
    bot = Chatbot(faq, crear_proveedor(), empresa="Tienda Demo")
    print("Escribí 'salir' para terminar.")
    # Operador morsa: lee y compara en la misma condición del while.
    while (texto := input("> ")).lower() != "salir":
        r = bot.responder(texto)
        print(f"[{r.fuente}{' · ESCALAR' if r.escalar else ''}] {r.texto}")


if __name__ == "__main__":
    main()
