"""Firmas ciegas RSA (esquema de David Chaum, 1983).

Idea: el votante consigue que la autoridad le **firme** su papeleta sin que la
autoridad **vea** la papeleta. Después la presenta por un canal anónimo; la
urna verifica la firma (prueba de que un votante habilitado la obtuvo) pero no
puede vincularla con quién la pidió.

Notación (clave pública ``(n, e)``, privada ``d``):

1. Votante: ``m = FDH(papeleta)`` y un factor aleatorio ``r`` coprimo con ``n``.
2. Votante cega:   ``m' = m · r^e mod n``           → se lo manda a la autoridad.
3. Autoridad firma: ``s' = (m')^d = m^d · r mod n``  → no conoce ``m``.
4. Votante desciega: ``s = s' · r⁻¹ mod n = m^d``   → firma RSA normal de ``m``.
5. Cualquiera verifica: ``s^e mod n == FDH(papeleta)``.

¿Por qué "RSA de libro" y no RSA-PSS? Porque PSS/PKCS#1 v1.5 agregan padding
aleatorio *después* de ver el mensaje, lo que impide cegar. El estándar moderno
para esto es RFC 9474 (RSA Blind Signatures); acá usamos su núcleo con FDH:
hashear el mensaje a un número del tamaño de ``n`` evita la maleabilidad
multiplicativa del RSA crudo (con FDH no se pueden combinar firmas válidas
para fabricar otra).

**IMPORTANTE:** la clave de firma ciega debe usarse SOLO para esto. Si se
reutilizara para descifrar u otras firmas, firmar "a ciegas" equivale a un
oráculo de descifrado.
"""
from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric import rsa

# Separador de dominio: el mismo hash nunca coincide con el de otro protocolo.
DOMINIO = b"votacion-segura/fdh/v1"


@dataclass(frozen=True)
class ClavePublica:
    """Lo único que se publica: módulo ``n`` y exponente ``e``."""

    n: int
    e: int

    @property
    def bytes_modulo(self) -> int:
        # Largo de n en bytes (256 para RSA-2048); se usa para serializar firmas.
        return (self.n.bit_length() + 7) // 8

    def huella(self) -> str:
        """Identificador corto de la clave (para que el votante confirme que es la correcta)."""
        return hashlib.sha256(f"{self.n}:{self.e}".encode()).hexdigest()[:16]


def fdh(mensaje: bytes, n: int) -> int:
    """Full Domain Hash: expande SHA-256 con un contador (estilo MGF1) hasta el
    largo de ``n`` y reduce módulo ``n``. Así el resultado se distribuye en todo
    ``Z_n`` y no solo en los primeros 256 bits."""
    largo = (n.bit_length() + 7) // 8
    salida = b""
    contador = 0
    while len(salida) < largo:
        salida += hashlib.sha256(DOMINIO + contador.to_bytes(4, "big") + mensaje).digest()
        contador += 1
    return int.from_bytes(salida[:largo], "big") % n


class Autoridad:
    """Tiene la clave privada y firma valores cegados. No ve las papeletas."""

    def __init__(self, bits: int = 2048, clave: rsa.RSAPrivateKey | None = None) -> None:
        # e = 65537 es el exponente público estándar. 2048 bits es el mínimo
        # recomendable hoy; los tests usan 1024 solo por velocidad.
        self._clave = clave or rsa.generate_private_key(public_exponent=65537, key_size=bits)
        priv = self._clave.private_numbers()
        self._d = priv.d
        self.publica = ClavePublica(priv.public_numbers.n, priv.public_numbers.e)

    def firmar_cegado(self, cegado: int) -> int:
        """``s' = m'^d mod n``. Rechaza valores fuera de rango (0, 1 o ≥ n no son cegados válidos)."""
        n = self.publica.n
        if not 1 < cegado < n:
            raise ValueError("valor cegado fuera de rango")
        return pow(cegado, self._d, n)


def verificar(publica: ClavePublica, mensaje: bytes, firma: int) -> bool:
    """``s^e mod n == FDH(m)``. Devuelve False ante firmas fuera de rango en vez de lanzar."""
    if not 0 < firma < publica.n:
        return False
    return pow(firma, publica.e, publica.n) == fdh(mensaje, publica.n)


# ---------- lado del votante ----------

def factor_cegado(n: int) -> int:
    """Elige ``r`` uniforme en [2, n-1] con mcd(r, n) = 1 (si no, r no tendría inverso)."""
    while True:
        r = secrets.randbelow(n - 2) + 2
        if math.gcd(r, n) == 1:
            return r


def cegar(publica: ClavePublica, mensaje: bytes, r: int) -> int:
    """Paso 2: ``m · r^e mod n``. Para la autoridad es indistinguible de un número al azar."""
    return fdh(mensaje, publica.n) * pow(r, publica.e, publica.n) % publica.n


def descegar(publica: ClavePublica, firma_cegada: int, r: int) -> int:
    """Paso 4: multiplicar por ``r⁻¹ mod n`` (pow con exponente -1 calcula el inverso modular)."""
    return firma_cegada * pow(r, -1, publica.n) % publica.n
