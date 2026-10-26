"""Orquestador: procesa una carpeta de PDFs y separa OK / revisión / duplicados."""

from __future__ import annotations

import csv
import datetime as dt
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .contabilidad import SistemaContable
from .extractor import extraer_datos, texto_pdf
from .validacion import validar


@dataclass
class Resultado:
    registradas: list[str] = field(default_factory=list)
    duplicadas: list[str] = field(default_factory=list)
    revision: dict[str, list[str]] = field(default_factory=dict)  # archivo -> problemas


@dataclass
class Procesador:
    contabilidad: SistemaContable
    # "hoy" inyectable para que la validación de fecha futura sea determinista en tests.
    hoy: dt.date | None = None
    mover: bool = False  # si True mueve a procesadas/ o revision/

    def procesar_carpeta(self, carpeta: Path) -> Resultado:
        r = Resultado()
        # Orden alfabético: resultados reproducibles y, ante duplicados, gana el primer archivo.
        for pdf in sorted(carpeta.glob("*.pdf")):
            try:
                d = extraer_datos(texto_pdf(pdf))
                problemas = validar(d, self.hoy)
            # Se registra sólo el nombre de la excepción: suficiente para la revisión y sin volcar trazas.
            except Exception as e:  # PDF corrupto/cifrado: no frena el lote
                problemas = [f"error leyendo PDF: {e.__class__.__name__}"]
                d = None
            if problemas or d is None:
                r.revision[pdf.name] = problemas
                destino = "revision"
            # Duplicado = mismo proveedor + número (ya registrado antes o en este mismo lote).
            elif self.contabilidad.existe(d.proveedor or "", d.numero or ""):
                r.duplicadas.append(pdf.name)
                destino = "revision"
            else:
                self.contabilidad.registrar(d, pdf.name)
                r.registradas.append(pdf.name)
                destino = "procesadas"
            # Duplicadas también van a revision/: una persona decide si es un reenvío o un error.
            if self.mover:
                (carpeta / destino).mkdir(exist_ok=True)
                shutil.move(str(pdf), carpeta / destino / pdf.name)
        return r


def exportar_revision(r: Resultado, ruta: Path) -> None:
    """CSV para que una persona revise lo que no pasó la validación."""
    # utf-8-sig (con BOM) para que Excel abra bien los acentos; newline="" lo exige el módulo csv.
    with ruta.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["archivo", "problemas"])
        for archivo, probs in r.revision.items():
            w.writerow([archivo, "; ".join(probs)])
        for archivo in r.duplicadas:
            w.writerow([archivo, "duplicada"])
