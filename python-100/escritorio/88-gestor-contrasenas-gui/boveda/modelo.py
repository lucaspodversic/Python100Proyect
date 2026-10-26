"""Modelo de la bóveda: entradas, búsqueda, generador y fortaleza de contraseñas."""
from __future__ import annotations

import math
import secrets
import string
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .cripto import Cifrador, ErrorBoveda, ParametrosKdf, escribir_atomico

LONGITUD_MINIMA_MAESTRA = 10


@dataclass
class Entrada:
    """Una credencial guardada. ``id`` es un UUID aleatorio (estable aunque cambie el sitio) y
    ``modificada`` una marca UTC en ISO 8601.
    """
    sitio: str
    usuario: str
    clave: str
    notas: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    modificada: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))


class Boveda:
    """Bóveda abierta en memoria. Se crea con :meth:`crear` o :meth:`abrir`."""

    def __init__(self, ruta: Path, cifrador: Cifrador, entradas: list[Entrada]) -> None:
        """Bóveda abierta: ruta del archivo, cifrador con la clave derivada y las entradas
        descifradas en memoria.
        """
        self.ruta, self._cifrador, self.entradas = ruta, cifrador, entradas

    @classmethod
    def crear(cls, ruta: Path, maestra: str, kdf: ParametrosKdf = ParametrosKdf()) -> "Boveda":
        """Crea una bóveda nueva y vacía. No pisa un archivo existente (se perderían datos) y
        exige una maestra de largo mínimo.
        """
        if ruta.exists():
            raise ErrorBoveda("ya existe una bóveda en esa ruta")
        validar_maestra(maestra)
        b = cls(ruta, Cifrador.nuevo(maestra, kdf), [])
        b.guardar()
        return b

    @classmethod
    def abrir(cls, ruta: Path, maestra: str) -> "Boveda":
        """Lee y descifra el archivo. Maestra incorrecta o archivo alterado → ErrorBoveda."""
        cifrador, datos = Cifrador.abrir(ruta.read_bytes(), maestra)
        return cls(ruta, cifrador, [Entrada(**e) for e in datos.get("entradas", [])])

    def guardar(self) -> None:
        """Cifra todo y escribe de forma atómica (temporal + reemplazo) con permisos 0600."""
        escribir_atomico(self.ruta, self._cifrador.cifrar({"entradas": [asdict(e) for e in self.entradas]}))

    def cambiar_maestra(self, actual: str, nueva: str) -> None:
        """Re-cifra con nueva sal y clave. Exige la actual (por si alguien usa la sesión abierta)."""
        Cifrador.abrir(self.ruta.read_bytes(), actual)  # lanza si la actual es incorrecta
        validar_maestra(nueva)
        self._cifrador = Cifrador.nuevo(nueva, self._cifrador.kdf)
        self.guardar()

    # ------------------------------------------------------------ CRUD
    def agregar(self, entrada: Entrada) -> Entrada:
        """Agrega una entrada (sitio y contraseña obligatorios) y guarda."""
        if not entrada.sitio.strip() or not entrada.clave:
            raise ValueError("sitio y contraseña son obligatorios")
        self.entradas.append(entrada)
        self.guardar()
        return entrada

    def actualizar(self, id_: str, **cambios: str) -> Entrada:
        """Modifica solo campos editables; ``id`` y ``modificada`` no se pueden pisar desde
        afuera. Actualiza la marca de tiempo y guarda.
        """
        e = self.obtener(id_)
        for k, v in cambios.items():
            if k not in {"sitio", "usuario", "clave", "notas"}:
                raise ValueError(f"campo no editable: {k}")
            setattr(e, k, v)
        e.modificada = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.guardar()
        return e

    def eliminar(self, id_: str) -> None:
        """Borra la entrada y guarda."""
        self.entradas.remove(self.obtener(id_))
        self.guardar()

    def obtener(self, id_: str) -> Entrada:
        """Busca por id; KeyError si no existe."""
        for e in self.entradas:
            if e.id == id_:
                return e
        raise KeyError(id_)

    def buscar(self, texto: str = "") -> list[Entrada]:
        """Busca en sitio/usuario/notas (nunca en la contraseña), ordenado por sitio."""
        t = texto.lower()
        return sorted((e for e in self.entradas if t in f"{e.sitio}\n{e.usuario}\n{e.notas}".lower()),
                      key=lambda e: e.sitio.lower())

    def reutilizadas(self) -> dict[str, list[str]]:
        """Contraseñas usadas en más de un sitio (sitio por grupo, sin revelar la clave)."""
        grupos: dict[str, list[str]] = {}
        for e in self.entradas:
            grupos.setdefault(e.clave, []).append(e.sitio)
        return {f"grupo {i + 1}": s for i, s in enumerate(v for v in grupos.values() if len(v) > 1)}


def validar_maestra(maestra: str) -> None:
    """Exige LONGITUD_MINIMA_MAESTRA caracteres: es la única defensa si alguien se lleva el
    archivo.
    """
    if len(maestra) < LONGITUD_MINIMA_MAESTRA:
        raise ErrorBoveda(f"la contraseña maestra debe tener al menos {LONGITUD_MINIMA_MAESTRA} caracteres")


# ---------------------------------------------------------------- generador
AMBIGUOS = set("Il1O0o")


def generar(longitud: int = 20, mayusculas: bool = True, digitos: bool = True, simbolos: bool = True,
            evitar_ambiguos: bool = False) -> str:
    """Genera con ``secrets`` (CSPRNG) garantizando al menos un carácter de cada clase pedida."""
    clases = [string.ascii_lowercase]
    if mayusculas:
        clases.append(string.ascii_uppercase)
    if digitos:
        clases.append(string.digits)
    if simbolos:
        clases.append("!@#$%^&*()-_=+[]{};:,.?")
    if evitar_ambiguos:
        clases = ["".join(c for c in cl if c not in AMBIGUOS) for cl in clases]
    if not 8 <= longitud <= 128:
        raise ValueError("longitud entre 8 y 128")
    alfabeto = "".join(clases)
    while True:
        clave = "".join(secrets.choice(alfabeto) for _ in range(longitud))
        # Rechazo y reintento: mantiene la distribución uniforme (no "forzamos" posiciones).
        if all(any(c in cl for c in clave) for cl in clases):
            return clave


def entropia_bits(clave: str) -> float:
    """Estimación simple: longitud × log2(tamaño del alfabeto usado)."""
    alfabeto = 0
    for cl in (string.ascii_lowercase, string.ascii_uppercase, string.digits):
        if any(c in cl for c in clave):
            alfabeto += len(cl)
    if any(not c.isascii() or not c.isalnum() for c in clave):
        alfabeto += 33
    return round(len(clave) * math.log2(alfabeto), 1) if alfabeto else 0.0


def fortaleza(clave: str) -> str:
    """Etiqueta orientativa; patrones obvios (repeticiones, comunes) bajan a "muy débil"."""
    comunes = {"password", "123456", "qwerty", "contraseña", "admin", "letmein", "111111"}
    if len(set(clave)) <= 2 or clave.lower() in comunes:
        return "muy débil"
    bits = entropia_bits(clave)
    for umbral, etiqueta in ((100, "muy fuerte"), (70, "fuerte"), (50, "aceptable"), (30, "débil")):
        if bits >= umbral:
            return etiqueta
    return "muy débil"
