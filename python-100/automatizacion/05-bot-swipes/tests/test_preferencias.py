"""Tests de las reglas puras de decisión."""

from bot_swipes.preferencias import Perfil, Preferencias, decidir

# Mismas preferencias que el test e2e, para que ambos niveles de test sean coherentes.
PREF = Preferencias(25, 35, 20, ["senderismo", "cine"], 1, ["fumador"])


def perfil(**kw: object) -> Perfil:
    # Perfil base aceptable (30 años, 5 km, interés "Cine"); cada test cambia un solo campo.
    base = dict(id="x", nombre="N", edad=30, distancia_km=5, bio="hola", intereses=["Cine"])
    base.update(kw)
    return Perfil(**base)  # type: ignore[arg-type]


def test_like_con_intereses_insensible_a_mayusculas_y_acentos() -> None:
    # Ambos intereses coinciden tras normalizar → afinidad 2.
    v = decidir(perfil(intereses=["CINE", "Sénderismo"]), PREF)
    assert v.like and v.afinidad == 2


def test_reglas_de_descarte() -> None:
    # Una línea por regla de descarte: edad, distancia (21 > 20), palabra excluida,
    # sin intereses en común (cocina) y bio vacía cuando se exige.
    assert "edad" in decidir(perfil(edad=40), PREF).motivo
    assert "distancia" in decidir(perfil(distancia_km=21), PREF).motivo
    assert "fumador" in decidir(perfil(bio="Fumador social"), PREF).motivo
    assert not decidir(perfil(intereses=["cocina"]), PREF).like
    assert not decidir(perfil(bio="  "), Preferencias(requiere_bio=True)).like


def test_limites_inclusivos() -> None:
    # Bordes exactos: edad mínima 25, máxima 35 y distancia 20 km se aceptan.
    assert decidir(perfil(edad=25, distancia_km=20), PREF).like
    assert decidir(perfil(edad=35), PREF).like
