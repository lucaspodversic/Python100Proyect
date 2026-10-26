"""Corpus de entrenamiento.

- ``generar_corpus``: reseñas sintéticas por plantillas (combinando aspecto,
  opinión y cierre). Sirve para entrenar sin descargar datos.
- ``cargar_reseñas_reales``: ~60 reseñas escritas a mano, estilo rioplatense e
  informal, usadas como conjunto de **evaluación** independiente (nunca se
  entrena con ellas en los tests).

Con datos reales se reemplaza por un CSV ``texto,etiqueta`` (p. ej. el corpus
TASS o reseñas propias etiquetadas).
"""

from __future__ import annotations

import random
from importlib import resources

import pandas as pd

ETIQUETAS = ("positivo", "negativo", "neutro")

# Plantillas: aspecto + opinión de la clase + cierre. Los aspectos son compartidos entre
# clases, así el modelo aprende que la polaridad está en la opinión y no en el tema.
ASPECTOS = ["la atención", "el envío", "el producto", "la calidad", "el precio", "el soporte", "la app",
            "el vendedor", "la entrega", "el empaque", "la comida", "el servicio"]
OPINIONES = {
    "positivo": ["fue excelente", "me encantó", "fue rapidísimo", "superó mis expectativas", "es muy buena",
                 "estuvo genial", "funciona perfecto", "es de primera", "vale cada peso", "fue impecable",
                 "me gustó mucho", "fue súper amable"],
    "negativo": ["fue pésimo", "llegó roto", "es una estafa", "fue lentísimo", "no funciona", "es malísima",
                 "me decepcionó", "no me gustó", "fue un desastre", "nunca llegó", "es carísimo para lo que es",
                 "no lo recomiendo"],
    "neutro": ["llegó en la fecha indicada", "es como se describe", "fue normal", "cumple lo básico",
               "no tengo comentarios", "es estándar", "está dentro de lo esperado", "fue correcto",
               "es igual al de la foto", "tiene el tamaño indicado"],
}
# El cierre vacío ("") hace que algunas reseñas terminen sin coletilla, como en la realidad.
CIERRES = {
    "positivo": ["¡Volvería a comprar!", "Recomendado 100%.", "Gracias!!", "Cinco estrellas.", ""],
    "negativo": ["No compro más.", "Quiero mi plata de vuelta.", "Una vergüenza.", "Cero estrellas.", ""],
    "neutro": ["Nada más que agregar.", "Ok.", "Veremos con el uso.", ""],
}


def generar_corpus(n_por_clase: int = 200, semilla: int = 0) -> pd.DataFrame:
    # Random propio con semilla: corpus idéntico en cada corrida sin tocar el estado global.
    rng = random.Random(semilla)
    filas = []
    for etiqueta in ETIQUETAS:
        for _ in range(n_por_clase):
            frase = f"{rng.choice(ASPECTOS).capitalize()} {rng.choice(OPINIONES[etiqueta])}. {rng.choice(CIERRES[etiqueta])}"
            # 30% de reseñas con dos oraciones: varía la longitud de los textos.
            if rng.random() < 0.3:  # segunda oración de la misma polaridad
                frase += f" También {rng.choice(ASPECTOS)} {rng.choice(OPINIONES[etiqueta])}."
            filas.append((frase.strip(), etiqueta))
    # Se mezclan las clases (si no, quedarían en bloques ordenados por etiqueta).
    rng.shuffle(filas)
    return pd.DataFrame(filas, columns=["texto", "etiqueta"])


def cargar_reseñas_reales() -> pd.DataFrame:
    # importlib.resources encuentra el CSV dentro del paquete instalado, sin depender del directorio actual.
    with resources.files("sentimiento").joinpath("datos/reseñas_evaluacion.csv").open(encoding="utf-8") as f:
        return pd.read_csv(f)
