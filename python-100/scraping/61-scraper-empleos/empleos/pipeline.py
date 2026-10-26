"""Pipeline: descargar (respetando robots y ritmo) → parsear → filtrar → deduplicar → exportar."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .cliente import ClienteEducado
from .modelo import Oferta
from .parser import PerfilSelectores, parsear_html, parsear_jsonld


@dataclass(frozen=True)
class Filtro:
    """Criterios para quedarse sólo con las ofertas interesantes."""
    palabras: tuple[str, ...] = ()        # todas deben aparecer en título o etiquetas
    excluir: tuple[str, ...] = ()
    ubicacion: str = ""
    solo_remoto: bool = False
    salario_minimo: float | None = None

    def acepta(self, o: Oferta) -> bool:
        # Se busca en título y etiquetas, sin distinguir mayúsculas.
        texto = " ".join((o.titulo, *o.etiquetas)).lower()
        if any(p.lower() not in texto for p in self.palabras):
            return False
        if any(p.lower() in texto for p in self.excluir):
            return False
        # Las ofertas remotas pasan el filtro de ubicación (se pueden hacer desde cualquier lugar).
        if self.ubicacion and self.ubicacion.lower() not in o.ubicacion.lower() and not o.remoto:
            return False
        if self.solo_remoto and not o.remoto:
            return False
        # Sin salario publicado (0) no se cumple un mínimo exigido.
        if self.salario_minimo is not None and (o.salario_max or 0) < self.salario_minimo:
            return False
        return True


# Recorre la paginación, combina JSON-LD y CSS, filtra y deduplica.
def ejecutar_pipeline(cliente: ClienteEducado, url_inicio: str, perfil: PerfilSelectores | None = None,
                      filtro: Filtro = Filtro(), max_paginas: int = 5) -> list[Oferta]:
    # clave → oferta; el dict conserva el orden de aparición.
    vistas: dict[str, Oferta] = {}
    url: str | None = url_inicio
    paginas = 0
    # Se detiene sin enlace "siguiente" o al llegar al tope de páginas.
    while url and paginas < max_paginas:
        # Cada pedido pasa por robots.txt y el rate limiting del cliente.
        html = cliente.get(url).texto()
        paginas += 1
        ofertas = parsear_jsonld(html, url)
        siguiente = None
        if perfil:
            por_css, siguiente = parsear_html(html, perfil, url)
            ofertas = ofertas or por_css  # JSON-LD tiene prioridad si existe
        for o in ofertas:
            if filtro.acepta(o):
                # setdefault: si la oferta se repite en otra página, se queda la primera.
                vistas.setdefault(o.clave, o)
        url = siguiente
    return list(vistas.values())


# CSV o JSON según la extensión; las etiquetas se unen en un solo texto.
def exportar(ofertas: list[Oferta], ruta: Path) -> Path:
    ruta = Path(ruta)
    filas = [asdict(o) | {"etiquetas": ", ".join(o.etiquetas)} for o in ofertas]
    if ruta.suffix == ".json":
        ruta.write_text(json.dumps(filas, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with ruta.open("w", newline="", encoding="utf-8") as f:
            # Columnas en el mismo orden que los campos de Oferta.
            w = csv.DictWriter(f, fieldnames=list(Oferta.__dataclass_fields__))
            w.writeheader()
            w.writerows(filas)
    return ruta
