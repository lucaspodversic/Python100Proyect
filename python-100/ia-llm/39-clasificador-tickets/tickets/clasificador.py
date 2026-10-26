"""Clasificación de tickets en un conjunto CERRADO de etiquetas.

Restringir las etiquetas es clave en producción: el LLM solo puede elegir
entre categorías válidas (se valida su JSON) y, si no, se usa un clasificador
por palabras clave. Cada categoría se mapea a un equipo (ruteo).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from tickets.llm import ErrorLLM, Mensaje, ProveedorLLM

# Cada categoría tiene su equipo destino y palabras clave con peso: 3 =
# señal fuerte ("factura"), 1 = débil o ambigua ("app", "correo"). Las
# claves van normalizadas (sin tildes): "contrasena", "debito", "caido".
CATEGORIAS: dict[str, dict] = {
    "facturacion": {"equipo": "Finanzas",
                    "claves": {"factura": 3, "cobro": 3, "cobraron": 3, "reembolso": 3, "pago": 2, "tarjeta": 2, "precio": 1, "debito": 2}},
    "tecnico": {"equipo": "Soporte N2",
                "claves": {"error": 3, "falla": 3, "no funciona": 3, "caido": 3, "lento": 2, "bug": 3, "app": 1, "se cierra": 3}},
    "cuenta": {"equipo": "Soporte N1",
               "claves": {"contrasena": 3, "login": 3, "acceso": 2, "bloqueada": 3, "usuario": 1, "email": 1, "iniciar sesion": 3}},
    "envios": {"equipo": "Logística",
               "claves": {"envio": 3, "paquete": 3, "llego": 2, "entrega": 3, "seguimiento": 3, "demora": 2, "correo": 1}},
    # "otro" no tiene claves: solo se elige cuando ninguna otra suma puntos.
    "otro": {"equipo": "Soporte N1", "claves": {}},
}
PRIORIDADES = ("baja", "media", "alta", "critica")
# Pesos de urgencia que se suman; definen la prioridad en por_claves.
URGENCIA = {"urgente": 2, "ya": 1, "inmediato": 2, "todos los clientes": 3, "produccion": 3, "no puedo": 1,
            "perdi": 1, "fraude": 3, "hoy": 1}

EJEMPLOS = [  # few-shot: guían el formato y el criterio del modelo
    ("Me cobraron dos veces la suscripción", "facturacion", "alta"),
    ("¿Cómo cambio mi foto de perfil?", "cuenta", "baja"),
]


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    # Minúsculas, sin tildes y sin signos: "¡No funciona!" => "no funciona".
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in t if not unicodedata.combining(c))))


@dataclass(frozen=True)
class Clasificacion:
    categoria: str
    prioridad: str
    confianza: float
    equipo: str
    origen: str   # "llm" | "claves"


def _coincide(texto: str, clave: str) -> bool:
    # \b solo al inicio: coincide por prefijo ("cobro" también encuentra
    # "cobros") pero no en medio de otra palabra ("ya" no matchea "playa").
    return re.search(rf"\b{re.escape(clave)}", texto) is not None


def por_claves(texto: str) -> Clasificacion:
    """Suma pesos de palabras clave; confianza = proporción del puntaje ganador."""
    t = normalizar(texto)
    puntajes = {c: sum(p for k, p in d["claves"].items() if _coincide(t, k)) for c, d in CATEGORIAS.items()}
    total = sum(puntajes.values())
    # Ante empate, max se queda con la primera en el orden del diccionario.
    categoria = max(puntajes, key=puntajes.get) if total else "otro"   # type: ignore[arg-type]
    urg = sum(p for k, p in URGENCIA.items() if _coincide(t, k))
    # Con urgencia: 1 + urg // 2 (1 => media, 2-3 => alta, 4+ => crítica),
    # tope en el índice 3. Sin urgencia: media si es un problema reconocido,
    # baja si no se identificó nada (consulta general).
    prioridad = PRIORIDADES[min(3, 1 + urg // 2)] if urg else ("media" if total else "baja")
    # Confianza = peso de la ganadora / total. Sin señales, 0,3 fijo (bajo).
    conf = round(puntajes[categoria] / total, 2) if total else 0.3
    return Clasificacion(categoria, prioridad, conf, CATEGORIAS[categoria]["equipo"], "claves")


def construir_prompt(texto: str) -> list[Mensaje]:
    # En f-strings, {{ y }} son llaves literales del JSON de ejemplo.
    ejemplos = "\n".join(f'Ticket: {t}\n{{"categoria": "{c}", "prioridad": "{p}", "confianza": 0.9}}'
                         for t, c, p in EJEMPLOS)
    sistema = (f"Clasificá tickets de soporte. Categorías válidas: {', '.join(CATEGORIAS)}. "
               f"Prioridades válidas: {', '.join(PRIORIDADES)}. Respondé SOLO JSON.\n{ejemplos}")
    # Se recorta el ticket a 3000 caracteres para acotar el costo.
    return [Mensaje("system", sistema), Mensaje("user", f"Ticket: {texto[:3000]}")]


def clasificar(texto: str, llm: ProveedorLLM | None = None, confianza_minima: float = 0.5) -> Clasificacion:
    """LLM si está disponible y su salida es válida y confiable; si no, palabras clave."""
    if llm is not None:
        try:
            salida = llm.completar(construir_prompt(texto), max_tokens=80)
            # No codicioso: toma el primer objeto JSON aunque el modelo agregue texto
            # antes ("Claro: {...}") o después.
            d = json.loads(re.search(r"\{.*?\}", salida, re.S).group(0))  # type: ignore[union-attr]
            cat, pri = str(d["categoria"]).lower(), str(d["prioridad"]).lower()
            conf = float(d.get("confianza", 0.5))
            # Tres condiciones: etiqueta válida, prioridad válida y confianza
            # suficiente. Si alguna falla se descarta la respuesta del LLM.
            if cat in CATEGORIAS and pri in PRIORIDADES and conf >= confianza_minima:
                return Clasificacion(cat, pri, round(min(conf, 1.0), 2), CATEGORIAS[cat]["equipo"], "llm")
        except (ErrorLLM, AttributeError, ValueError, KeyError, TypeError):
            pass
    return por_claves(texto)
