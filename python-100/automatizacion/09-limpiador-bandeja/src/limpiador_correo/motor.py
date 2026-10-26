"""Motor de reglas: evalúa, agrupa acciones y las aplica en lote."""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .gmail import ClienteCorreo
from .modelos import Accion, Condicion, Correo, Regla


def cargar_reglas(origen: Path | list[dict[str, Any]]) -> list[Regla]:
    """Carga reglas desde un JSON (o lista ya parseada)."""
    # Acepta archivo o lista ya parseada (útil en tests). Claves "si"/"entonces" se pasan como
    # kwargs a los dataclasses: una clave mal escrita produce TypeError inmediato (falla rápido).
    datos = json.loads(origen.read_text(encoding="utf-8")) if isinstance(origen, Path) else origen
    return [Regla(r["nombre"], Condicion(**r.get("si", {})), Accion(**r.get("entonces", {})), r.get("detener", True))
            for r in datos]


@dataclass
class Reporte:
    """Resumen: cuántos correos tocó cada regla y qué acciones se aplicaron."""

    revisados: int = 0
    # defaultdict conserva el orden de inserción → el resumen respeta el orden de las reglas.
    por_regla: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    protegidos: int = 0
    dry_run: bool = False

    def resumen(self) -> str:
        lineas = [f"{'[dry-run] ' if self.dry_run else ''}Revisados: {self.revisados} (protegidos: {self.protegidos})"]
        lineas += [f"  {r}: {len(ids)}" for r, ids in self.por_regla.items()]
        return "\n".join(lineas)


@dataclass
class Motor:
    cliente: ClienteCorreo
    reglas: list[Regla]
    remitentes_protegidos: list[str] = field(default_factory=list)  # nunca se tocan (jefe, banco...)

    def _protegido(self, c: Correo) -> bool:
        # Protecciones: remitentes VIP (por subcadena) y cualquier correo destacado por el usuario.
        return any(p.lower() in c.email_remitente for p in self.remitentes_protegidos) or "STARRED" in c.etiquetas

    def clasificar(self, correos: list[Correo], ahora: dt.datetime) -> dict[str, list[Correo]]:
        """Asigna correos a reglas (puro: no llama al cliente)."""
        asignados: dict[str, list[Correo]] = defaultdict(list)
        for c in correos:
            if self._protegido(c):
                continue
            for r in self.reglas:
                if r.condicion.cumple(c, ahora):
                    asignados[r.nombre].append(c)
                    # Primera regla que coincide gana (como los filtros de Gmail/Outlook), salvo detener=False.
                    if r.detener:
                        break
        return asignados

    def ejecutar(self, consulta: str = "in:inbox", maximo: int = 500, dry_run: bool = True,
                 ahora: dt.datetime | None = None) -> Reporte:
        ahora = ahora or dt.datetime.now()
        # Se obtienen todos primero y luego se clasifica: así el dry-run muestra el plan completo.
        correos = [self.cliente.obtener(i) for i in self.cliente.listar(consulta, maximo)]
        rep = Reporte(revisados=len(correos), dry_run=dry_run)
        rep.protegidos = sum(self._protegido(c) for c in correos)
        por_nombre = {r.nombre: r for r in self.reglas}
        for nombre, lista in self.clasificar(correos, ahora).items():
            ids = [c.id for c in lista]
            rep.por_regla[nombre] = ids
            if dry_run:
                continue
            a = por_nombre[nombre].accion
            # La papelera excluye el resto de acciones (no tiene sentido etiquetar algo que se descarta).
            if a.papelera:
                for i in ids:
                    self.cliente.papelera(i)
                continue
            agregar = [self.cliente.id_etiqueta(e) for e in a.etiquetar]
            agregar += ["STARRED"] if a.destacar else []
            # En Gmail "archivar" = quitar INBOX y "marcar leído" = quitar UNREAD.
            quitar = (["INBOX"] if a.archivar else []) + (["UNREAD"] if a.marcar_leido else [])
            # Una sola llamada batchModify por regla, no una por correo: menos cuota y latencia.
            if agregar or quitar:
                self.cliente.modificar(ids, agregar, quitar)  # una sola llamada por regla
        return rep
