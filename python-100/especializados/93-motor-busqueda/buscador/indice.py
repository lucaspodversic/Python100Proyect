"""Índice invertido con posiciones y ranking BM25.

Estructura::

    postings[término][doc_id] = [posiciones…]
    docs[doc_id] = {"titulo", "ruta", "longitud", "texto", "mtime"}

**BM25** (Robertson/Spärck Jones), para cada término *t* de la consulta::

    idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5))
    score += idf · tf·(k1+1) / (tf + k1·(1 - b + b·len/len_media))

Con ``k1=1.5`` y ``b=0.75``, la frecuencia satura (repetir una palabra cien
veces no gana cien veces más) y los documentos largos se penalizan
suavemente. Además, cada término que aparece en el **título** suma un bonus
de ``BONUS_TITULO·idf``, y cada frase exacta encontrada suma ``BONUS_FRASE``.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .consulta import Consulta, parsear
from .texto import plegar, raiz, tokens_con_posicion, STOPWORDS

K1, B = 1.5, 0.75
BONUS_TITULO = 0.5
BONUS_FRASE = 1.0
EXTENSIONES = {".txt", ".md", ".rst"}
VERSION = 1


@dataclass(frozen=True)
class Resultado:
    """Un resultado: id del documento (ruta relativa), título, puntuación BM25 y fragmento con
    los términos resaltados.
    """
    doc_id: str
    titulo: str
    puntuacion: float
    fragmento: str


class Indice:
    """Índice invertido con posiciones: término → {documento → [posiciones]}. Las posiciones
    permiten buscar frases exactas. Además guarda el texto y metadatos de cada documento
    (para fragmentos e indexación incremental) y los términos del título (que reciben un
    bonus).
    """
    def __init__(self) -> None:
        """Índice vacío."""
        self.postings: dict[str, dict[str, list[int]]] = defaultdict(dict)
        self.docs: dict[str, dict] = {}
        self.titulos: dict[str, set[str]] = {}

    # ---------- construcción ----------
    def agregar(self, doc_id: str, texto: str, titulo: str = "", ruta: str = "", mtime: float = 0.0) -> None:
        """Agrega o reemplaza un documento."""
        if doc_id in self.docs:
            self.quitar(doc_id)
        tp = tokens_con_posicion(texto)
        for t, pos in tp:
            self.postings[t].setdefault(doc_id, []).append(pos)
        titulo = titulo or doc_id
        self.docs[doc_id] = {"titulo": titulo, "ruta": ruta, "longitud": len(tp), "texto": texto, "mtime": mtime}
        self.titulos[doc_id] = {t for t, _ in tokens_con_posicion(titulo)}

    def quitar(self, doc_id: str) -> bool:
        """Quita un documento de todas sus listas de postings y borra los términos que quedan
        sin documentos, para que el índice no crezca con basura al reindexar.
        """
        if doc_id not in self.docs:
            return False
        for t in {t for t, _ in tokens_con_posicion(self.docs[doc_id]["texto"])}:
            self.postings[t].pop(doc_id, None)
            if not self.postings[t]:
                del self.postings[t]
        del self.docs[doc_id]
        self.titulos.pop(doc_id, None)
        return True

    def indexar_carpeta(self, carpeta: Path) -> dict[str, int]:
        """Indexa incrementalmente: solo (re)lee archivos nuevos o modificados y quita los borrados."""
        carpeta = Path(carpeta)
        vistos, stats = set(), {"nuevos": 0, "actualizados": 0, "sin_cambios": 0, "eliminados": 0}
        for ruta in sorted(carpeta.rglob("*")):
            if ruta.suffix.lower() not in EXTENSIONES or not ruta.is_file():
                continue
            doc_id = ruta.relative_to(carpeta).as_posix()
            vistos.add(doc_id)
            mtime = ruta.stat().st_mtime
            previo = self.docs.get(doc_id)
            if previo and previo["mtime"] == mtime:
                stats["sin_cambios"] += 1
                continue
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            self.agregar(doc_id, texto, titulo=_titulo(texto, ruta), ruta=str(ruta), mtime=mtime)
            stats["actualizados" if previo else "nuevos"] += 1
        for doc_id in set(self.docs) - vistos:
            self.quitar(doc_id)
            stats["eliminados"] += 1
        return stats

    # ---------- búsqueda ----------
    @property
    def longitud_media(self) -> float:
        """Longitud media de los documentos en términos (la normalización de BM25 la necesita)."""
        return sum(d["longitud"] for d in self.docs.values()) / len(self.docs) if self.docs else 0.0

    def idf(self, t: str) -> float:
        """IDF de BM25 en la variante de Lucene: log(1 + (N - df + 0.5)/(df + 0.5)). El '1 +'
        garantiza que nunca sea negativo, aunque el término esté en más de la mitad
        de los documentos.
        """
        n, df = len(self.docs), len(self.postings.get(t, {}))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _bm25(self, t: str, doc_id: str) -> float:
        """Aporte de un término a un documento: idf · tf·(k1+1) / (tf + k1·(1 - b +
        b·largo/largo_medio)). La frecuencia satura (repetir mucho una palabra rinde
        cada vez menos) y los documentos largos se penalizan según b.
        """
        tf = len(self.postings.get(t, {}).get(doc_id, []))
        if not tf:
            return 0.0
        norm = 1 - B + B * self.docs[doc_id]["longitud"] / (self.longitud_media or 1)
        return self.idf(t) * tf * (K1 + 1) / (tf + K1 * norm)

    def _tiene_frase(self, frase: list[tuple[str, int]], doc_id: str) -> bool:
        """True si para alguna aparición del primer término todos los demás están en inicio +
        desplazamiento. Es una búsqueda posicional exacta: el orden importa.
        """
        primero, _ = frase[0]
        for inicio in self.postings.get(primero, {}).get(doc_id, []):
            if all(inicio + off in self.postings.get(t, {}).get(doc_id, ()) for t, off in frase[1:]):
                return True
        return False

    def buscar(self, consulta: str | Consulta, limite: int = 10) -> list[Resultado]:
        """Candidatos = documentos con algún término positivo, intersecados con los
        obligatorios, menos los excluidos, y filtrados por frases. Cada candidato
        puntúa con BM25 (más el bonus por título) y se ordena por puntaje
        descendente, desempatando por id para que el resultado sea determinista.
        """
        c = parsear(consulta) if isinstance(consulta, str) else consulta
        if c.vacia:
            return []
        positivos = c.positivos()
        # Candidatos: documentos con algún término positivo.
        candidatos = set().union(*(self.postings.get(t, {}).keys() for t in positivos))
        for t in c.obligatorios:
            candidatos &= set(self.postings.get(t, {}))
        for t in c.excluidos:
            candidatos -= set(self.postings.get(t, {}))
        candidatos = {d for d in candidatos if all(self._tiene_frase(f, d) for f in c.frases)}
        resultados = []
        for d in candidatos:
            s = sum(self._bm25(t, d) for t in dict.fromkeys(positivos))
            s += sum(BONUS_TITULO * self.idf(t) for t in set(positivos) & self.titulos[d])
            s += BONUS_FRASE * len(c.frases)
            resultados.append((s, d))
        # Orden: puntuación desc, luego id para que sea determinista.
        resultados.sort(key=lambda x: (-x[0], x[1]))
        return [Resultado(d, self.docs[d]["titulo"], round(s, 4), fragmento(self.docs[d]["texto"], set(positivos)))
                for s, d in resultados[:limite]]

    # ---------- persistencia ----------
    def guardar(self, ruta: Path) -> None:
        """Guarda solo los documentos (texto y metadatos) con una versión; los postings se
        reconstruyen al cargar. Es más simple y nunca queda inconsistente.
        """
        datos = {"version": VERSION, "docs": self.docs}  # el índice se reconstruye al cargar (más simple y robusto)
        Path(ruta).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta: Path) -> "Indice":
        """Carga y reindexa en memoria. Una versión distinta pide reindexar en lugar de leer
        datos mal.
        """
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if datos.get("version") != VERSION:
            raise ValueError("versión de índice incompatible; reindexá")
        ind = cls()
        for doc_id, d in datos["docs"].items():
            ind.agregar(doc_id, d["texto"], d["titulo"], d["ruta"], d["mtime"])
        return ind


def _titulo(texto: str, ruta: Path) -> str:
    """Primera línea no vacía (sin '#' de Markdown) o el nombre del archivo."""
    for linea in texto.splitlines():
        if linea.strip():
            return linea.strip().lstrip("#").strip()[:120]
    return ruta.stem


_PAL = re.compile(r"\w+", re.UNICODE)


def fragmento(texto: str, raices: set[str], ventana: int = 20, marca: tuple[str, str] = ("[", "]")) -> str:
    """Fragmento de ~``ventana`` palabras con más coincidencias, resaltándolas."""
    palabras = list(_PAL.finditer(texto))
    if not palabras:
        return ""
    coincide = [(w := plegar(m.group())) not in STOPWORDS and raiz(w) in raices for m in palabras]
    mejor, mejor_n = 0, -1
    n = sum(coincide[:ventana])
    for i in range(max(1, len(palabras) - ventana + 1)):
        if i:
            n += (coincide[i + ventana - 1] if i + ventana - 1 < len(palabras) else 0) - coincide[i - 1]
        if n > mejor_n:
            mejor, mejor_n = i, n
    fin = min(len(palabras), mejor + ventana)
    partes, cursor = [], palabras[mejor].start()
    for k in range(mejor, fin):
        m = palabras[k]
        partes.append(texto[cursor:m.start()])
        partes.append(f"{marca[0]}{m.group()}{marca[1]}" if coincide[k] else m.group())
        cursor = m.end()
    pre = "…" if mejor > 0 else ""
    post = "…" if fin < len(palabras) else ""
    return pre + " ".join("".join(partes).split()) + post
