"""Pipeline RAG: recuperar -> armar prompt con fuentes numeradas -> generar -> validar citas.

El LLM debe citar las fuentes como [1], [2]... Luego se verifica que cada cita
exista; las citas inventadas se eliminan y se informa. Si no se recupera nada
relevante, NO se llama al LLM (evita respuestas inventadas).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.embeddings import IndiceVectorial
from rag.llm import Mensaje, ProveedorLLM

SISTEMA = ("Respondé en español usando ÚNICAMENTE las fuentes numeradas. "
           "Citá cada afirmación con [n]. Si las fuentes no alcanzan, respondé exactamente: NO_SE")


@dataclass
class RespuestaRAG:
    texto: str
    citas: list[dict] = field(default_factory=list)     # fuentes efectivamente citadas
    citas_invalidas: list[int] = field(default_factory=list)
    con_respaldo: bool = True


class RAG:
    def __init__(self, indice: IndiceVectorial, llm: ProveedorLLM, k: int = 4) -> None:
        self.indice, self.llm, self.k = indice, llm, k

    def preguntar(self, pregunta: str) -> RespuestaRAG:
        recuperados = self.indice.buscar(pregunta, k=self.k)
        # Sin contexto relevante no se llama al LLM: no hay de dónde responder.
        if not recuperados:
            return RespuestaRAG("No encontré información sobre eso en los documentos.", con_respaldo=False)
        # Numeración desde 1 (es lo natural para citar: [1], [2]...).
        fuentes = "\n\n".join(f"[{i}] ({f.fuente}) {f.texto}" for i, (f, _) in enumerate(recuperados, 1))
        salida = self.llm.completar([Mensaje("system", SISTEMA),
                                     Mensaje("user", f"Fuentes:\n{fuentes}\n\nPregunta: {pregunta}")]).strip()
        # Palabra clave pedida en el prompt para "no sé": fácil de detectar.
        if salida.startswith("NO_SE"):
            return RespuestaRAG("Los documentos no contienen la respuesta.", con_respaldo=False)
        # Validación de citas: el LLM puede inventar [9] si solo hubo 4 fuentes.
        numeros = [int(n) for n in re.findall(r"\[(\d+)\]", salida)]
        validos = sorted({n for n in numeros if 1 <= n <= len(recuperados)})
        invalidos = sorted({n for n in numeros if not 1 <= n <= len(recuperados)})
        for n in invalidos:  # quitar citas a fuentes inexistentes
            salida = salida.replace(f"[{n}]", "")
        citas = [{"n": n, "id": recuperados[n - 1][0].id, "fuente": recuperados[n - 1][0].fuente,
                  "puntaje": recuperados[n - 1][1]} for n in validos]
        # Se normalizan los espacios que quedaron al borrar citas. Sin ninguna
        # cita válida la respuesta se marca como "sin respaldo".
        return RespuestaRAG(" ".join(salida.split()), citas, invalidos, con_respaldo=bool(validos))
