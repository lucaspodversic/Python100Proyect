"""Lógica del gateway independiente de HTTP: ruteo, reintentos, caché, cuotas y uso."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Callable

from gateway.llm import ErrorLLM, Mensaje, ProveedorLLM


def estimar_tokens(texto: str) -> int:
    """Aproximación estándar: ~4 caracteres por token (sin depender de tokenizers)."""
    # Ej.: "Hola" (4 caracteres) => 1 token; 64 caracteres => 16. Mínimo 1.
    return max(1, len(texto) // 4)


class CacheLRU:
    """Caché LRU con capacidad fija (OrderedDict: mover al final = usado recientemente)."""

    def __init__(self, capacidad: int = 256) -> None:
        self.capacidad = capacidad
        self._datos: OrderedDict[str, dict] = OrderedDict()
        self.aciertos = self.fallos = 0

    def obtener(self, clave: str) -> dict | None:
        if clave in self._datos:
            # Leer una clave la marca como la más reciente (va al final).
            self._datos.move_to_end(clave); self.aciertos += 1
            return self._datos[clave]
        self.fallos += 1
        return None

    def guardar(self, clave: str, valor: dict) -> None:
        self._datos[clave] = valor
        self._datos.move_to_end(clave)
        # Al pasarse de capacidad se descarta el primero (el menos usado).
        if len(self._datos) > self.capacidad:
            self._datos.popitem(last=False)  # descarta el menos usado


class LimitadorTasa:
    """Token bucket por clave: `capacidad` pedidos de ráfaga, recarga `por_minuto`."""

    def __init__(self, por_minuto: int, reloj: Callable[[], float] = time.monotonic) -> None:
        # Cubeta de `por_minuto` fichas que se recarga a por_minuto/60 fichas por
        # segundo. Ej.: 60/min => ráfaga de 60 y luego 1 por segundo.
        self.capacidad, self.recarga = float(por_minuto), por_minuto / 60.0
        self.reloj = reloj
        self._cubetas: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def permitir(self, clave: str) -> bool:
        with self._lock:
            ahora = self.reloj()
            # Un cliente nuevo arranca con la cubeta llena. La recarga se calcula de
            # forma perezosa (solo al consultar), sin hilos ni timers.
            fichas, ultimo = self._cubetas.get(clave, (self.capacidad, ahora))
            fichas = min(self.capacidad, fichas + (ahora - ultimo) * self.recarga)
            # Se guarda igual el nuevo estado para no perder la recarga acumulada.
            if fichas < 1:
                self._cubetas[clave] = (fichas, ahora)
                return False
            self._cubetas[clave] = (fichas - 1, ahora)
            return True


@dataclass
class Ruta:
    """Un alias público (p. ej. 'rapido') con su cadena de proveedores de respaldo."""
    proveedores: list[ProveedorLLM]
    costo_por_1k: float = 0.0   # USD estimados por 1000 tokens (para el reporte de uso)


# Guarda la lista de errores para diagnóstico (y contar intentos en el 502).
class SinProveedores(RuntimeError):
    def __init__(self, errores: list[str]) -> None:
        super().__init__("; ".join(errores))
        self.errores = errores


@dataclass
class Gateway:
    rutas: dict[str, Ruta]
    reintentos: int = 2
    espera_base: float = 0.5
    dormir: Callable[[float], None] = time.sleep      # inyectable: los tests no esperan
    cache: CacheLRU = field(default_factory=CacheLRU)
    uso: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(
        lambda: {"pedidos": 0, "tokens_entrada": 0, "tokens_salida": 0, "costo_usd": 0.0, "desde_cache": 0}))

    def chat(self, cliente: str, alias: str, mensajes: list[Mensaje], temperatura: float = 0.0,
             max_tokens: int = 512) -> dict:
        if alias not in self.rutas:
            raise KeyError(alias)
        ruta = self.rutas[alias]
        # Solo se cachean respuestas deterministas (temperatura 0)
        # Clave de caché = hash de todo lo que determina la respuesta (alias,
        # max_tokens y la conversación completa). El cliente NO es parte de la
        # clave: dos clientes con la misma pregunta comparten la respuesta.
        clave = hashlib.sha256(json.dumps([alias, max_tokens, [(m.rol, m.contenido) for m in mensajes]],
                                          ensure_ascii=False).encode()).hexdigest()
        u = self.uso[cliente]
        # Con temperatura > 0 la respuesta es aleatoria a propósito: cachearla
        # cambiaría el comportamiento esperado. Un acierto no suma costo.
        if temperatura == 0 and (hit := self.cache.obtener(clave)):
            u["pedidos"] += 1; u["desde_cache"] += 1
            return {**hit, "cache": True}
        errores: list[str] = []
        for proveedor in ruta.proveedores:            # fallback en orden
            for intento in range(self.reintentos + 1):  # reintentos con backoff exponencial
                try:
                    texto = proveedor.completar(mensajes, temperatura=temperatura, max_tokens=max_tokens)
                except ErrorLLM as e:
                    errores.append(f"{proveedor.nombre}#{intento + 1}: {e}")
                    if intento < self.reintentos:
                        # Backoff: 0,5 s, 1 s, 2 s... No se duerme después del último intento.
                        self.dormir(self.espera_base * 2 ** intento)
                    continue
                # Costo estimado = (tokens entrada + salida) / 1000 x precio por 1k.
                t_in = sum(estimar_tokens(m.contenido) for m in mensajes)
                t_out = estimar_tokens(texto)
                u["pedidos"] += 1; u["tokens_entrada"] += t_in; u["tokens_salida"] += t_out
                u["costo_usd"] = round(u["costo_usd"] + (t_in + t_out) / 1000 * ruta.costo_por_1k, 6)
                resp = {"modelo": alias, "proveedor": proveedor.nombre, "contenido": texto,
                        # intentos = fallos previos (de cualquier proveedor) + el exitoso.
                        "uso": {"tokens_entrada": t_in, "tokens_salida": t_out}, "intentos": len(errores) + 1}
                if temperatura == 0:
                    self.cache.guardar(clave, resp)
                return {**resp, "cache": False}
        raise SinProveedores(errores)
