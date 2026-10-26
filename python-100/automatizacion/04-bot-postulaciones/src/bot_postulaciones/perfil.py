"""Reglas de decisión PURAS: ¿esta oferta encaja con el perfil?

No depende del navegador ni de la red, así que se testea exhaustivamente
con datos en memoria.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar palabras clave de forma robusta."""
    # NFKD separa "ó" en "o" + tilde combinante; al codificar a ASCII con "ignore" se pierde la tilde.
    # Efecto secundario aceptado: la "ñ" se vuelve "n".
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_acentos.lower()


def contiene(texto: str, palabra: str) -> bool:
    """Búsqueda por palabra completa (``java`` no matchea ``javascript``)."""
    # Lookarounds en vez de \b: "c#" y "c++" terminan en símbolos que \b no trata como palabra.
    # Exigimos que antes y después NO haya letra/dígito/+/#, así "java" no coincide con "javascript".
    return re.search(rf"(?<![\w+#]){re.escape(normalizar(palabra))}(?![\w+#])", normalizar(texto)) is not None


@dataclass
class Perfil:
    """Perfil predefinido del candidato y sus preferencias de búsqueda."""

    nombre: str
    email: str
    carta: str
    obligatorias: list[str] = field(default_factory=list)  # todas deben aparecer
    deseables: list[str] = field(default_factory=list)  # suman puntaje
    excluidas: list[str] = field(default_factory=list)  # descartan la oferta
    ubicaciones: list[str] = field(default_factory=list)  # vacío = cualquiera
    acepta_remoto: bool = True
    salario_minimo: int | None = None
    puntaje_minimo: float = 0.0


@dataclass
class Oferta:
    """Oferta tal como se lee del sitio."""

    id: str
    titulo: str
    empresa: str
    ubicacion: str
    modalidad: str  # "remoto" | "presencial" | "hibrido"
    salario: int | None = None
    descripcion: str = ""


@dataclass
class Decision:
    """Resultado de evaluar una oferta, con los motivos (auditabilidad)."""

    aplicar: bool
    puntaje: float
    motivos: list[str]


def evaluar(oferta: Oferta, perfil: Perfil) -> Decision:
    """Aplica las reglas en orden; la primera regla eliminatoria corta."""
    texto = f"{oferta.titulo} {oferta.descripcion}"
    motivos: list[str] = []
    # Orden de reglas: excluidas → obligatorias → modalidad → ubicación → salario → puntaje.
    # Las eliminatorias van primero y devuelven un único motivo claro.
    for palabra in perfil.excluidas:
        if contiene(texto, palabra):
            return Decision(False, 0, [f"contiene palabra excluida: {palabra}"])
    faltantes = [p for p in perfil.obligatorias if not contiene(texto, p)]
    if faltantes:
        return Decision(False, 0, [f"faltan obligatorias: {', '.join(faltantes)}"])
    es_remoto = normalizar(oferta.modalidad) == "remoto"
    if es_remoto and not perfil.acepta_remoto:
        return Decision(False, 0, ["el perfil no acepta remoto"])
    # La ubicación sólo importa si NO es remoto; coincidencia por subcadena normalizada
    # ("buenos aires" coincide con "CABA, Buenos Aires").
    if not es_remoto and perfil.ubicaciones and not any(
        normalizar(u) in normalizar(oferta.ubicacion) for u in perfil.ubicaciones
    ):
        return Decision(False, 0, [f"ubicación no aceptada: {oferta.ubicacion}"])
    # Salario no informado (None) NO descarta: muchas ofertas reales no lo publican.
    if perfil.salario_minimo is not None and oferta.salario is not None and oferta.salario < perfil.salario_minimo:
        return Decision(False, 0, [f"salario {oferta.salario} < mínimo {perfil.salario_minimo}"])
    # Puntaje: 1 punto por obligatoria + 1 por cada deseable + 0.5 si es remoto.
    puntaje = float(len(perfil.obligatorias))
    for p in perfil.deseables:
        if contiene(texto, p):
            puntaje += 1
            motivos.append(f"+1 deseable: {p}")
    if es_remoto:
        puntaje += 0.5
        motivos.append("+0.5 remoto")
    if puntaje < perfil.puntaje_minimo:
        return Decision(False, puntaje, motivos + [f"puntaje {puntaje} < {perfil.puntaje_minimo}"])
    # Si no sumó deseables ni remoto, igual dejamos un motivo legible.
    return Decision(True, puntaje, motivos or ["cumple los requisitos"])
