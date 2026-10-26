"""Tests de las reglas de decisión (funciones puras)."""

from __future__ import annotations

from bot_postulaciones.perfil import Oferta, Perfil, contiene, evaluar

# Perfil base: "python" obligatoria; docker y fastapi deseables; excluye "guardias".
PERFIL = Perfil("Ana", "ana@ej.invalid", "Hola", obligatorias=["python"], deseables=["docker", "fastapi"],
                excluidas=["guardias"], ubicaciones=["Buenos Aires"], salario_minimo=2500)


def oferta(**kw: object) -> Oferta:
    # Oferta base que CUMPLE todo; cada test cambia un solo campo para aislar una regla.
    base = dict(id="1", titulo="Dev Python", empresa="X", ubicacion="Buenos Aires", modalidad="presencial",
                salario=3000, descripcion="Python y Docker")
    base.update(kw)
    return Oferta(**base)  # type: ignore[arg-type]


def test_contiene_palabra_completa_y_sin_acentos() -> None:
    assert contiene("Experiencia en JAVA", "java")
    # Palabra completa: "java" dentro de "javascript" no cuenta. "Programación" coincide sin tilde
    # y "c#" funciona pese a terminar en símbolo.
    assert not contiene("JavaScript", "java")
    assert contiene("Programación", "programacion")
    assert contiene("C# y .NET", "c#")


def test_aplica_y_suma_deseables() -> None:
    # Puntaje = 1 (una obligatoria) + 1 (docker aparece; fastapi no) = 2.0.
    d = evaluar(oferta(), PERFIL)
    assert d.aplicar and d.puntaje == 2.0 and "+1 deseable: docker" in d.motivos


def test_remoto_suma_y_ignora_ubicacion() -> None:
    # Remoto ignora la ubicación (Lima) y suma 0.5: 1 + 1 + 0.5 = 2.5.
    d = evaluar(oferta(modalidad="remoto", ubicacion="Lima"), PERFIL)
    assert d.aplicar and d.puntaje == 2.5


def test_reglas_eliminatorias() -> None:
    # Una línea por regla eliminatoria: excluida, falta obligatoria, ubicación, salario bajo
    # (1000 < 2500) y remoto cuando el perfil no lo acepta.
    assert not evaluar(oferta(descripcion="Python con guardias"), PERFIL).aplicar
    assert not evaluar(oferta(titulo="Dev Java", descripcion="Java"), PERFIL).aplicar
    assert not evaluar(oferta(ubicacion="Córdoba"), PERFIL).aplicar
    assert not evaluar(oferta(salario=1000), PERFIL).aplicar
    sin_remoto = Perfil("A", "a@b", "c", obligatorias=["python"], acepta_remoto=False)
    assert not evaluar(oferta(modalidad="remoto"), sin_remoto).aplicar


def test_salario_desconocido_no_descarta_y_puntaje_minimo() -> None:
    assert evaluar(oferta(salario=None), PERFIL).aplicar
    # Con puntaje_minimo=5 la oferta base (puntaje 1, sin deseables) no alcanza y el último
    # motivo explica por qué.
    exigente = Perfil("A", "a@b", "c", obligatorias=["python"], puntaje_minimo=5)
    d = evaluar(oferta(), exigente)
    assert not d.aplicar and "puntaje" in d.motivos[-1]
