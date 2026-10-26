"""Modelo de la bóveda: entradas en memoria, persistidas cifradas en disco."""
from __future__ import annotations

import json
import os
import secrets
import string
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .cripto import N_POR_DEFECTO, cifrar, descifrar


@dataclass
class Entrada:
    """Una credencial guardada."""

    # Nombre visible (se respeta mayúsc./minúsc.); la clave del dict es su versión en minúsculas.
    servicio: str
    usuario: str
    contrasena: str
    notas: str = ""


@dataclass
class Boveda:
    """Colección de entradas protegidas por una contraseña maestra."""

    # La maestra vive sólo en memoria mientras la bóveda está abierta; nunca se escribe en disco.
    ruta: Path
    maestra: str
    # Costo de scrypt para el PRÓXIMO guardado (al abrir, el costo real se lee del encabezado).
    n_kdf: int = N_POR_DEFECTO
    entradas: dict[str, Entrada] = field(default_factory=dict)

    # ---------- persistencia ----------
    @classmethod
    def crear(cls, ruta: Path, maestra: str, n_kdf: int = N_POR_DEFECTO) -> "Boveda":
        """Crea una bóveda vacía. Falla si ya existe para no pisarla."""
        # No pisar: sobrescribir una bóveda existente perdería todas sus credenciales.
        if Path(ruta).exists():
            raise FileExistsError(f"Ya existe {ruta}")
        # Mínimo de 8 caracteres: scrypt frena la fuerza bruta, pero una maestra corta sigue siendo débil.
        if len(maestra) < 8:
            raise ValueError("La contraseña maestra debe tener al menos 8 caracteres")
        b = cls(Path(ruta), maestra, n_kdf)
        # Se escribe de inmediato: así el archivo existe y el siguiente `crear` lo detecta.
        b.guardar()
        return b

    @classmethod
    def abrir(cls, ruta: Path, maestra: str, n_kdf: int = N_POR_DEFECTO) -> "Boveda":
        """Abre y descifra una bóveda existente."""
        # descifrar() falla con ErrorDescifrado ANTES de llegar a json si la maestra es incorrecta.
        datos = json.loads(descifrar(Path(ruta).read_bytes(), maestra))
        # El JSON guarda dicts planos; se reconstruyen los dataclasses.
        entradas = {k: Entrada(**v) for k, v in datos["entradas"].items()}
        return cls(Path(ruta), maestra, n_kdf, entradas)

    def guardar(self) -> None:
        """Cifra y escribe de forma atómica (archivo temporal + replace)."""
        # Todo el contenido (incluidos los nombres de servicio) va cifrado: no se filtran metadatos.
        plano = json.dumps({"entradas": {k: asdict(v) for k, v in self.entradas.items()}}).encode()
        # Archivo temporal en la misma carpeta: os.replace es atómico sólo dentro del mismo sistema de archivos.
        tmp = self.ruta.with_suffix(self.ruta.suffix + ".tmp")
        tmp.write_bytes(cifrar(plano, self.maestra, self.n_kdf))
        os.replace(tmp, self.ruta)  # evita bóvedas corruptas si se corta a mitad
        try:
            os.chmod(self.ruta, 0o600)  # sólo el dueño puede leerla
        # En sistemas sin permisos POSIX (p. ej. algunos montajes Windows) chmod puede fallar: no es fatal.
        except OSError:
            pass

    # ---------- operaciones ----------
    def agregar(self, entrada: Entrada, reemplazar: bool = False) -> None:
        # Claves sin distinguir mayúsculas: "GitHub" y "github" son el mismo servicio.
        clave = entrada.servicio.lower()
        if clave in self.entradas and not reemplazar:
            raise KeyError(f"Ya existe una entrada para {entrada.servicio}")
        # Sólo modifica memoria: el llamador decide cuándo guardar (permite agrupar cambios).
        self.entradas[clave] = entrada

    def obtener(self, servicio: str) -> Entrada:
        # KeyError si no existe: la CLI lo traduce a un mensaje y exit 1.
        return self.entradas[servicio.lower()]

    def eliminar(self, servicio: str) -> None:
        del self.entradas[servicio.lower()]

    def buscar(self, texto: str) -> list[Entrada]:
        """Búsqueda por subcadena en servicio o usuario (sin mirar contraseñas)."""
        # Nunca se busca dentro de las contraseñas: evitaría filtrarlas por coincidencias.
        t = texto.lower()
        return [e for e in self.entradas.values() if t in e.servicio.lower() or t in e.usuario.lower()]

    def cambiar_maestra(self, nueva: str) -> None:
        """Re-cifra todo con una nueva contraseña maestra (y nueva sal)."""
        if len(nueva) < 8:
            raise ValueError("La contraseña maestra debe tener al menos 8 caracteres")
        # guardar() genera sal y nonce nuevos: la clave anterior deja de servir por completo.
        self.maestra = nueva
        self.guardar()


def generar_contrasena(largo: int = 20) -> str:
    """Genera una contraseña aleatoria con `secrets` (CSPRNG)."""
    # Letras, dígitos y símbolos comunes aceptados por casi todos los sitios.
    alfabeto = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    # secrets (y no random): random es predecible y no apto para secretos.
    return "".join(secrets.choice(alfabeto) for _ in range(largo))
