"""Planificación y ejecución de movimientos de archivos.

Se separa en dos fases para poder ofrecer *dry-run*:

1. ``planificar`` recorre el origen y construye una lista de ``Movimiento``
   sin tocar nada.
2. ``ejecutar`` aplica el plan y escribe un registro JSON que permite
   ``deshacer`` la operación completa.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .clasificador import Modo, clasificar, renombrar

# Nombre del archivo de registro que se guarda en la carpeta destino.
REGISTRO = ".organizador_registro.json"


# frozen=True: un movimiento planificado es inmutable y hasheable; se serializa con ``asdict``.
# Guardamos rutas como ``str`` (no Path) para que el JSON del registro sea directo.
@dataclass(frozen=True)
class Movimiento:
    """Un movimiento planificado: de ``origen`` a ``destino`` (rutas absolutas)."""

    origen: str
    destino: str


def _ruta_libre(destino: Path, reservadas: set[Path]) -> Path:
    """Devuelve una ruta que no exista ni esté reservada por el plan.

    Si ``foto.jpg`` ya existe, prueba ``foto (1).jpg``, ``foto (2).jpg``...
    Así nunca sobrescribimos archivos del usuario.
    """
    # ``reservadas`` cubre el caso de dos archivos del MISMO plan que irían al mismo nombre
    # (todavía no existen en disco, así que ``exists()`` no alcanza para detectarlo).
    candidato = destino
    n = 1
    while candidato.exists() or candidato in reservadas:
        candidato = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        n += 1
    return candidato


def planificar(
    origen: Path,
    destino: Path | None = None,
    modo: Modo = "tipo",
    plantilla: str | None = None,
    recursivo: bool = False,
    incluir_ocultos: bool = False,
) -> list[Movimiento]:
    """Construye el plan de movimientos sin modificar el disco.

    :param origen: carpeta a organizar.
    :param destino: carpeta raíz destino (por defecto, la misma de origen).
    :param modo: criterio de clasificación (ver ``clasificar``).
    :param plantilla: plantilla de renombrado opcional.
    :param recursivo: si es ``True`` también procesa subcarpetas.
    :param incluir_ocultos: procesa archivos que empiezan con punto.
    """
    # Rutas absolutas y resueltas: evita comparar "./a" con "/home/x/a" como si fueran distintas.
    origen = origen.resolve()
    destino = (destino or origen).resolve()
    # "**/*" recorre subcarpetas; con "*" sólo el primer nivel.
    patron = "**/*" if recursivo else "*"
    # Ordenamos para que el plan (y los índices de renombrado) sean deterministas.
    archivos = sorted(p for p in origen.glob(patron) if p.is_file())
    plan: list[Movimiento] = []
    reservadas: set[Path] = set()
    # El índice arranca en 1 porque es lo que espera un humano en "foto_001.jpg".
    for indice, archivo in enumerate(archivos, start=1):
        if archivo.name == REGISTRO:
            continue  # nunca movemos nuestro propio registro
        if not incluir_ocultos and archivo.name.startswith("."):
            continue
        # Carpeta destino absoluta = raíz destino + carpeta relativa según el modo.
        carpeta = destino / clasificar(archivo, modo)
        # Si el archivo ya está en una subcarpeta de clasificación, lo salteamos
        # para que correr el script dos veces sea idempotente.
        if archivo.parent == carpeta:
            continue
        nombre = renombrar(archivo, plantilla, indice)
        # Nunca sobrescribimos: si el nombre está ocupado se agrega " (n)".
        final = _ruta_libre(carpeta / nombre, reservadas)
        reservadas.add(final)
        plan.append(Movimiento(str(archivo), str(final)))
    return plan


def ejecutar(plan: list[Movimiento], registro: Path | None = None) -> int:
    """Aplica el plan moviendo los archivos; devuelve cuántos movió.

    Si se indica ``registro``, guarda allí la lista de movimientos realizados
    (formato JSON) para poder revertirlos con ``deshacer``.
    """
    # Sólo registramos los movimientos que efectivamente se hicieron: si uno falla a mitad
    # de camino, la excepción se propaga y el registro no se escribe (decisión simple y explícita).
    hechos: list[Movimiento] = []
    for mov in plan:
        destino = Path(mov.destino)
        # Creamos la carpeta destino bajo demanda (exist_ok evita error si ya existe).
        destino.parent.mkdir(parents=True, exist_ok=True)
        # shutil.move funciona incluso entre distintos sistemas de archivos.
        shutil.move(mov.origen, destino)
        hechos.append(mov)
    # ensure_ascii=False conserva tildes y ñ legibles en el JSON.
    if registro is not None:
        registro.write_text(
            json.dumps([asdict(m) for m in hechos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return len(hechos)


def deshacer(registro: Path) -> int:
    """Revierte los movimientos guardados en ``registro``.

    Se recorren en orden inverso para respetar dependencias. Devuelve la
    cantidad de archivos restaurados y elimina el registro al terminar.
    """
    datos = json.loads(registro.read_text(encoding="utf-8"))
    restaurados = 0
    # Orden inverso: si hubo renombres encadenados, se deshacen en el orden opuesto al aplicado.
    for item in reversed(datos):
        actual, original = Path(item["destino"]), Path(item["origen"])
        # Caso borde: si el usuario borró/movió el archivo o ya existe algo en el origen, lo saltamos
        # en lugar de sobrescribir; por eso el total restaurado puede ser menor al registrado.
        if actual.exists() and not original.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(actual), original)
            restaurados += 1
    # Borramos el registro para que un segundo ``deshacer`` no intente revertir dos veces.
    registro.unlink()
    return restaurados
