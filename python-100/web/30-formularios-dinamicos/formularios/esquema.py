"""Definición de campos y validación de respuestas.

Un formulario es una lista de campos. Tipos soportados:
  texto, parrafo, email, numero, fecha, seleccion (una opción), casillas (varias).
Cada tipo tiene sus propias restricciones opcionales (min/max, largo, opciones).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# Literal: Pydantic rechaza cualquier tipo que no esté en esta lista.
TipoCampo = Literal["texto", "parrafo", "email", "numero", "fecha", "seleccion", "casillas"]
# Email "razonable": algo@algo.algo sin espacios. La única validación
# completa sería enviar un mail de confirmación.
PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Campo(BaseModel):
    """Un campo del formulario."""
    # Nombre interno: minúscula inicial, hasta 40 caracteres [a-z0-9_]. Es
    # seguro para usar como name en HTML, clave JSON y columna CSV.
    nombre: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$", description="Identificador interno")
    etiqueta: str = Field(min_length=1, max_length=200)
    tipo: TipoCampo
    requerido: bool = False
    opciones: list[str] = Field(default_factory=list)
    # minimo/maximo: solo aplican a "numero". largo_max: a los de texto.
    minimo: float | None = None
    maximo: float | None = None
    largo_max: int = Field(default=500, ge=1, le=10_000)

    @model_validator(mode="after")
    def _coherencia(self) -> "Campo":
        """Valida que la definición del campo tenga sentido."""
        # Una selección con una sola opción no es una pregunta.
        if self.tipo in ("seleccion", "casillas") and len(self.opciones) < 2:
            raise ValueError(f"El campo '{self.nombre}' necesita al menos 2 opciones")
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError(f"En '{self.nombre}' el mínimo supera al máximo")
        return self


class DefinicionFormulario(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    descripcion: str = ""
    campos: list[Campo] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _nombres_unicos(self) -> "DefinicionFormulario":
        # Nombres repetidos harían que un campo pise al otro en la respuesta.
        nombres = [c.nombre for c in self.campos]
        if len(nombres) != len(set(nombres)):
            raise ValueError("Los nombres de campo deben ser únicos")
        return self


def validar_respuesta(campos: list[Campo], datos: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Valida y normaliza una respuesta.

    Devuelve (valores_limpios, errores_por_campo). Si `errores` no está vacío,
    la respuesta debe rechazarse. Los campos desconocidos se ignoran.
    """
    limpio: dict[str, Any] = {}
    errores: dict[str, str] = {}
    for c in campos:
        # Se recorren los campos de la DEFINICIÓN (no los datos recibidos): así se
        # ignoran claves extra que mande el cliente.
        v = datos.get(c.nombre)
        # "Vacío" incluye no enviado, string vacío (form HTML) y lista vacía (casillas).
        vacio = v is None or v == "" or v == []
        if vacio:
            if c.requerido:
                errores[c.nombre] = "Campo obligatorio"
            # Un opcional vacío no se guarda (no aparece en la respuesta limpia).
            continue
        try:
            limpio[c.nombre] = _validar_valor(c, v)
        # Se juntan TODOS los errores en vez de cortar en el primero.
        except ValueError as e:
            errores[c.nombre] = str(e)
    return limpio, errores


def _validar_valor(c: Campo, v: Any) -> Any:
    """Valida un valor según el tipo del campo (lanza ValueError con el motivo)."""
    if c.tipo in ("texto", "parrafo", "email"):
        if not isinstance(v, str):
            raise ValueError("Debe ser texto")
        # Se quitan espacios de los bordes antes de medir el largo.
        v = v.strip()
        if len(v) > c.largo_max:
            raise ValueError(f"Máximo {c.largo_max} caracteres")
        if c.tipo == "email" and not PATRON_EMAIL.match(v):
            raise ValueError("Email inválido")
        return v
    if c.tipo == "numero":
        try:
            # Acepta 30 o "30" (en los formularios HTML todo llega como texto).
            n = float(v)
        except (TypeError, ValueError):
            raise ValueError("Debe ser un número") from None
        if c.minimo is not None and n < c.minimo:
            raise ValueError(f"Debe ser ≥ {c.minimo:g}")
        if c.maximo is not None and n > c.maximo:
            raise ValueError(f"Debe ser ≤ {c.maximo:g}")
        # 30.0 => 30 para que quede prolijo en JSON y CSV; 1.5 queda float.
        return int(n) if n.is_integer() else n
    if c.tipo == "fecha":
        try:
            # Se normaliza a AAAA-MM-DD; "ayer" o "2026-13-01" => error.
            return date.fromisoformat(str(v)).isoformat()
        except ValueError:
            raise ValueError("Fecha inválida (AAAA-MM-DD)") from None
    if c.tipo == "seleccion":
        if v not in c.opciones:
            raise ValueError("Opción inválida")
        return v
    # casillas: lista de opciones (sin repetir)
    # Si en el form HTML se marca una sola casilla puede llegar un string suelto.
    valores = v if isinstance(v, list) else [v]
    if any(x not in c.opciones for x in valores):
        raise ValueError("Opción inválida")
    # set() quita duplicados y se reordena según las opciones definidas, así
    # ["canela", "azúcar", "canela"] => ["azúcar", "canela"].
    return sorted(set(valores), key=c.opciones.index)
